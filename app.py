import os
import psycopg2
from psycopg2.extras import DictCursor
from flask import Flask, render_template, request, redirect, url_for, session, send_file
from datetime import datetime
import pandas as pd
import io

app = Flask(__name__)

app.secret_key = os.environ.get('SECRET_KEY', 'super-secret-key-change-me')

CRM_USERNAME = os.environ.get('CRM_USERNAME', 'admin')
CRM_PASSWORD = os.environ.get('CRM_PASSWORD', 'Mayer2026') 

DATABASE_URL = os.environ.get('DATABASE_URL')

def get_db_connection():
    conn = psycopg2.connect(DATABASE_URL, sslmode='require')
    return conn

def init_db():
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS clients (
            id SERIAL PRIMARY KEY,
            name TEXT NOT NULL,
            country TEXT,
            address TEXT,
            contact_person TEXT,
            position TEXT,
            phone TEXT,
            email TEXT,
            website TEXT,
            buyer_type TEXT,
            brands TEXT,
            contact_person_2 TEXT,
            position_2 TEXT,
            phone_2 TEXT,
            email_2 TEXT,
            interest_level TEXT,
            next_event_date TEXT,
            next_event_type TEXT
        )
    ''')
    
    cursor.execute("SELECT column_name FROM information_schema.columns WHERE table_name='clients'")
    existing_columns = [row[0] for row in cursor.fetchall()]
    
    new_fields = {
        'website': 'TEXT',
        'buyer_type': 'TEXT',
        'brands': 'TEXT',
        'position': 'TEXT',
        'contact_person_2': 'TEXT',
        'position_2': 'TEXT',
        'phone_2': 'TEXT',
        'email_2': 'TEXT',
        'interest_level': 'TEXT',
        'next_event_date': 'TEXT',
        'next_event_type': 'TEXT'
    }
    
    for field, f_type in new_fields.items():
        if field not in existing_columns:
            cursor.execute(f"ALTER TABLE clients ADD COLUMN {field} {f_type};")

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS negotiations (
            id SERIAL PRIMARY KEY,
            client_id INTEGER,
            date TEXT,
            result TEXT,
            FOREIGN KEY (client_id) REFERENCES clients (id) ON DELETE CASCADE
        )
    ''')
    
    conn.commit()
    cursor.close()
    conn.close()

if DATABASE_URL:
    init_db()

def login_required(f):
    from functools import wraps
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('logged_in'):
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

@app.route('/login', methods=['GET', 'POST'])
def login():
    error = None
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        if username == CRM_USERNAME and password == CRM_PASSWORD:
            session['logged_in'] = True
            return redirect(url_for('index'))
        else:
            error = 'Невірний логін або пароль'
    return render_template('login.html', error=error)

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

@app.route('/')
@login_required
def index():
    search_query = request.args.get('search', '').strip()
    country_filter = request.args.get('country', '').strip()
    
    conn = get_db_connection()
    
    # Автоматичний переклад країн з російської на українську на рівні бази
    with conn.cursor() as fix_cursor:
        fix_cursor.execute("""
            UPDATE clients 
            SET country = CASE 
                WHEN LOWER(country) IN ('польша', 'polska', 'poland') THEN 'Польща'
                WHEN LOWER(country) IN ('украина', 'ukraine') THEN 'Україна'
                WHEN LOWER(country) IN ('германия', 'deutschland', 'germany') THEN 'Німеччина'
                WHEN LOWER(country) IN ('словакия', 'slovakia') THEN 'Словаччина'
                WHEN LOWER(country) IN ('чехия', 'czechia', 'czech republic') THEN 'Чехія'
                WHEN LOWER(country) IN ('литва', 'lithuania') THEN 'Литва'
                WHEN LOWER(country) IN ('латвия', 'latvia') THEN 'Латвія'
                WHEN LOWER(country) IN ('эстония', 'estonia') THEN 'Естонія'
                WHEN LOWER(country) IN ('венгрия', 'hungary') THEN 'Угорщина'
                WHEN LOWER(country) IN ('румыния', 'romania') THEN 'Румунія'
                WHEN LOWER(country) IN ('молдова', 'moldova') THEN 'Молдова'
                ELSE country 
            END
            WHERE country IS NOT NULL AND country != '';
        """)
        conn.commit()
    
    # 1. Окремий простий курсор для збору списку унікальних країн
    country_cursor = conn.cursor()
    country_cursor.execute("SELECT DISTINCT country FROM clients WHERE country IS NOT NULL AND country != '' ORDER BY country ASC")
    countries = [row[0] for row in country_cursor.fetchall()]
    country_cursor.close()
    
    # --- ЛІЧИЛЬНИКИ ДЛЯ СТАТИСТИКИ ---
    stats_cursor = conn.cursor()
    
    # Загальна кількість
    stats_cursor.execute("SELECT COUNT(*) FROM clients")
    total_clients = stats_cursor.fetchone()[0]
    
    # Кількість по рівнях зацікавленості
    stats_cursor.execute("SELECT interest_level, COUNT(*) FROM clients GROUP BY interest_level")
    raw_interest = stats_cursor.fetchall()
    interest_stats = {'немає зацікавленості': 0, 'середня зацікавленість': 0, 'зацікавленість': 0}
    for row in raw_interest:
        status = row[0] if row[0] else 'немає зацікавленості'
        if status in interest_stats:
            interest_stats[status] = row[1]
            
    # Кількість по країнах
    stats_cursor.execute("SELECT country, COUNT(*) FROM clients WHERE country IS NOT NULL AND country != '' GROUP BY country ORDER BY COUNT(*) DESC")
    country_stats = stats_cursor.fetchall()
    
    stats_cursor.close()
    # ---------------------------------
    
    # 2. Використовуємо DictCursor для безпечного читання повнотекстових ключів клієнтів
    cursor = conn.cursor(cursor_factory=DictCursor)
    sql = """
        SELECT c.*, 
               (SELECT MAX(n.date)::TEXT FROM negotiations n WHERE n.client_id = c.id) AS last_activity 
        FROM clients c 
        WHERE 1=1
    """
    params = []
    
    if search_query:
        sql += " AND (LOWER(c.name) LIKE LOWER(%s) OR LOWER(c.contact_person) LIKE LOWER(%s) OR LOWER(c.brands) LIKE LOWER(%s))"
        params.extend([f"%{search_query}%", f"%{search_query}%", f"%{search_query}%"])
        
    if country_filter:
        sql += " AND c.country = %s"
        params.append(country_filter)
        
    today_str = datetime.now().strftime("%Y-%m-%d")
    sql += f" ORDER BY (CASE WHEN c.next_event_date = '{today_str}' THEN 0 ELSE 1 END), (CASE WHEN (SELECT MAX(n.date) FROM negotiations n WHERE n.client_id = c.id) IS NULL THEN 1 ELSE 0 END), (SELECT MAX(n.date) FROM negotiations n WHERE n.client_id = c.id) DESC, c.name ASC"
    
    cursor.execute(sql, params)
    raw_clients = cursor.fetchall()
    
    clients = []
    for row in raw_clients:
        clients.append({
            'id': row['id'],
            'name': row['name'] if row['name'] else '',
            'country': row['country'] if row['country'] else '',
            'address': row['address'] if row['address'] else '',
            'contact_person': row['contact_person'] if row['contact_person'] else '',
            'position': row['position'] if row['position'] else '',
            'phone': row['phone'] if row['phone'] else '',
            'email': row['email'] if row['email'] else '',
            'website': row['website'] if row['website'] else '',
            'buyer_type': row['buyer_type'] if row['buyer_type'] else '',
            'brands': row['brands'] if row['brands'] else '',
            'interest_level': row['interest_level'] if row['interest_level'] else 'немає зацікавленості',
            'last_activity': row['last_activity'] if row['last_activity'] else '',
            'next_event_date': row['next_event_date'] if row['next_event_date'] else '',
            'next_event_type': row['next_event_type'] if row['next_event_type'] else ''
        })
    
    cursor.close()
    conn.close()
    
    return render_template(
        'index.html', 
        clients=clients, 
        countries=countries, 
        search_query=search_query, 
        country_filter=country_filter,
        total_clients=total_clients,
        interest_stats=interest_stats,
        country_stats=country_stats,
        today_date=today_str
    )

@app.route('/add_client', methods=['POST'])
@login_required
def add_client():
    name = request.form.get('name')
    country = request.form.get('country', '')
    address = request.form.get('address', '')
    buyer_type = request.form.get('buyer_type', '')
    interest_level = request.form.get('interest_level', 'немає зацікавленості')
    website = request.form.get('website', '')
    next_event_date = request.form.get('next_event_date', '')
    next_event_type = request.form.get('next_event_type', '')
    
    selected_brands = request.form.getlist('brands')
    brands = ", ".join(selected_brands) if selected_brands else ""
    
    contact_person = request.form.get('contact_person', '')
    position = request.form.get('position', '')
    phone = request.form.get('phone', '')
    email = request.form.get('email', '')
    
    contact_person_2 = request.form.get('contact_person_2', '')
    position_2 = request.form.get('position_2', '')
    phone_2 = request.form.get('phone_2', '')
    email_2 = request.form.get('email_2', '')
    
    if name:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            """INSERT INTO clients (name, country, address, contact_person, position, phone, email, website, buyer_type, brands, 
                                   contact_person_2, position_2, phone_2, email_2, interest_level, next_event_date, next_event_type) 
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
            (name, country, address, contact_person, position, phone, email, website, buyer_type, brands,
             contact_person_2, position_2, phone_2, email_2, interest_level, next_event_date, next_event_type)
        )
        conn.commit()
        cursor.close()
        conn.close()
    return redirect(url_for('index'))

@app.route('/edit_client/<int:client_id>', methods=['POST'])
@login_required
def edit_client(client_id):
    name = request.form.get('name')
    country = request.form.get('country', '')
    address = request.form.get('address', '')
    buyer_type = request.form.get('buyer_type', '')
    interest_level = request.form.get('interest_level', 'немає зацікавленості')
    website = request.form.get('website', '')
    next_event_date = request.form.get('next_event_date', '')
    next_event_type = request.form.get('next_event_type', '')
    
    selected_brands = request.form.getlist('brands')
    brands = ", ".join(selected_brands) if selected_brands else ""
    
    contact_person = request.form.get('contact_person', '')
    position = request.form.get('position', '')
    phone = request.form.get('phone', '')
    email = request.form.get('email', '')
    
    contact_person_2 = request.form.get('contact_person_2', '')
    position_2 = request.form.get('position_2', '')
    phone_2 = request.form.get('phone_2', '')
    email_2 = request.form.get('email_2', '')
    
    if name:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            """UPDATE clients SET name=%s, country=%s, address=%s, contact_person=%s, position=%s, phone=%s, email=%s, 
                                  website=%s, buyer_type=%s, brands=%s, contact_person_2=%s, position_2=%s, 
                                  phone_2=%s, email_2=%s, interest_level=%s, next_event_date=%s, next_event_type=%s WHERE id=%s""",
            (name, country, address, contact_person, position, phone, email, website, buyer_type, brands,
             contact_person_2, position_2, phone_2, email_2, interest_level, next_event_date, next_event_type, client_id)
        )
        conn.commit()
        cursor.close()
        conn.close()
    return redirect(url_for('client_detail', client_id=client_id))

@app.route('/client/<int:client_id>', methods=['GET', 'POST'])
@login_required
def client_detail(client_id):
    conn = get_db_connection()
    cursor = conn.cursor(cursor_factory=DictCursor)
    
    if request.method == 'POST':
        result_text = request.form.get('result')
        if result_text:
            current_date = datetime.now().strftime("%Y-%m-%d %H:%M")
            cursor.execute(
                "INSERT INTO negotiations (client_id, date, result) VALUES (%s, %s, %s)",
                (client_id, current_date, result_text)
            )
            conn.commit()
        return redirect(url_for('client_detail', client_id=client_id))
    
    cursor.execute("SELECT * FROM clients WHERE id = %s", (client_id,))
    raw_client = cursor.fetchone()
    
    client = dict(raw_client) if raw_client else {}
    fields_to_check = ['buyer_type', 'brands', 'website', 'country', 'address', 
                       'contact_person', 'position', 'phone', 'email', 
                       'contact_person_2', 'position_2', 'phone_2', 'email_2', 
                       'interest_level', 'next_event_date', 'next_event_type']
    for field in fields_to_check:
        if field not in client or client[field] is None:
            if field == 'interest_level':
                client[field] = 'немає зацікавленості'
            else:
                client[field] = ''
    
    cursor.execute("SELECT * FROM negotiations WHERE client_id = %s ORDER BY id DESC", (client_id,))
    history = cursor.fetchall()
    
    cursor.close()
    conn.close()
    return render_template('client.html', client=client, history=history)

@app.route('/edit_negotiation/<int:neg_id>', methods=['POST'])
@login_required
def edit_negotiation(neg_id):
    client_id = request.form.get('client_id')
    result_text = request.form.get('result')
    
    if result_text:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("UPDATE negotiations SET result = %s WHERE id = %s", (result_text, neg_id))
        conn.commit()
        cursor.close()
        conn.close()
    return redirect(url_for('client_detail', client_id=client_id))

@app.route('/delete_negotiation/<int:neg_id>', methods=['POST'])
@login_required
def delete_negotiation(neg_id):
    client_id = request.form.get('client_id')
    
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM negotiations WHERE id = %s", (neg_id,))
    conn.commit()
    cursor.close()
    conn.close()
    return redirect(url_for('client_detail', client_id=client_id))

@app.route('/export_excel')
@login_required
def export_excel():
    conn = get_db_connection()
    
    query = """
        SELECT c.name AS "Назва компанії", c.interest_level AS "Зацікавленість", c.buyer_type AS "Тип покупця", c.brands AS "Пріоритетні бренди",
               c.website AS "Веб-сайт", c.country AS "Країна", c.address AS "Адреса",
               c.contact_person AS "Контактна особа 1", c.position AS "Посада 1", c.phone AS "Телефон 1", c.email AS "Email 1",
               c.contact_person_2 AS "Контактна особа 2", c.position_2 AS "Посада 2", c.phone_2 AS "Телефон 2", c.email_2 AS "Email 2",
               c.next_event_date AS "Дата наступної події", c.next_event_type AS "Вид наступної події"
        FROM clients c ORDER BY c.name ASC
    """
    df = pd.read_sql(query, conn)
    conn.close()
    
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='Клієнти Mayer CRM')
    output.seek(0)
    
    return send_file(
        output,
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        as_attachment=True,
        download_name=f'Mayer_CRM_Clients_{datetime.now().strftime("%Y-%m-%d")}.xlsx'
    )

@app.route('/import_excel', methods=['POST'])
@login_required
def import_excel():
    if 'excel_file' not in request.files:
        return redirect(url_for('index'))
    
    file = request.files['excel_file']
    if file.filename == '':
        return redirect(url_for('index'))
        
    if file and (file.filename.endswith('.xlsx') or file.filename.endswith('.xls')):
        try:
            df = pd.read_excel(file)
            
            mapping = {
                'Назва компанії': 'name', 'Company Name': 'name', 'Назва': 'name', 'Name': 'name',
                'Зацікавленість': 'interest_level', 'Interest Level': 'interest_level',
                'Тип покупця': 'buyer_type', 'Buyer Type': 'buyer_type',
                'Пріоритетні бренди': 'brands', 'Brands': 'brands', 'Бренди': 'brands',
                'Веб-сайт': 'website', 'Website': 'website', 'Сайт': 'website',
                'Країна': 'country', 'Country': 'country',
                'Адреса': 'address', 'Address': 'address',
                'Контактна особа 1': 'contact_person', 'Contact Person 1': 'contact_person', 'Контакт 1': 'contact_person',
                'Посада 1': 'position', 'Position 1': 'position',
                'Телефон 1': 'phone', 'Phone 1': 'phone',
                'Email 1': 'email', 'Mail 1': 'email',
                'Контактна особа 2': 'contact_person_2', 'Contact Person 2': 'contact_person_2', 'Контакт 2': 'contact_person_2',
                'Посада 2': 'position_2', 'Position 2': 'position_2',
                'Телефон 2': 'phone_2', 'Phone 2': 'phone_2',
                'Email 2': 'email_2', 'Mail 2': 'email_2',
                'Дата наступної події': 'next_event_date',
                'Вид наступної події': 'next_event_type'
            }
            
            renamed_cols = {}
            for col in df.columns:
                cleaned_col = str(col).strip()
                if cleaned_col in mapping:
                    renamed_cols[col] = mapping[cleaned_col]
            
            df = df.rename(columns=renamed_cols)
            
            if 'name' not in df.columns:
                return "Помилка: У файлі Excel не знайдено оголошення компанії ('Назва компанії')"
            
            conn = get_db_connection()
            cursor = conn.cursor(cursor_factory=DictCursor)
            
            for _, row in df.iterrows():
                name = str(row['name']).strip() if pd.notnull(row['name']) else ''
                if not name:
                    continue
                
                interest_level = str(row['interest_level']).strip() if 'interest_level' in df.columns and pd.notnull(row['interest_level']) else 'немає зацікавленості'
                buyer_type = str(row['buyer_type']).strip() if 'buyer_type' in df.columns and pd.notnull(row['buyer_type']) else ''
                brands = str(row['brands']).strip() if 'brands' in df.columns and pd.notnull(row['brands']) else ''
                website = str(row['website']).strip() if 'website' in df.columns and pd.notnull(row['website']) else ''
                country = str(row['country']).strip() if 'country' in df.columns and pd.notnull(row['country']) else ''
                address = str(row['address']).strip() if 'address' in df.columns and pd.notnull(row['address']) else ''
                
                contact_person = str(row['contact_person']).strip() if 'contact_person' in df.columns and pd.notnull(row['contact_person']) else ''
                position = str(row['position']).strip() if 'position' in df.columns and pd.notnull(row['position']) else ''
                phone = str(row['phone']).strip() if 'phone' in df.columns and pd.notnull(row['phone']) else ''
                email = str(row['email']).strip() if 'email' in df.columns and pd.notnull(row['email']) else ''
                
                contact_person_2 = str(row['contact_person_2']).strip() if 'contact_person_2' in df.columns and pd.notnull(row['contact_person_2']) else ''
                position_2 = str(row['position_2']).strip() if 'position_2' in df.columns and pd.notnull(row['position_2']) else ''
                phone_2 = str(row['phone_2']).strip() if 'phone_2' in df.columns and pd.notnull(row['phone_2']) else ''
                email_2 = str(row['email_2']).strip() if 'email_2' in df.columns and pd.notnull(row['email_2']) else ''
                
                next_event_date = str(row['next_event_date']).strip() if 'next_event_date' in df.columns and pd.notnull(row['next_event_date']) else ''
                next_event_type = str(row['next_event_type']).strip() if 'next_event_type' in df.columns and pd.notnull(row['next_event_type']) else ''
                
                cursor.execute("SELECT id FROM clients WHERE LOWER(name) = LOWER(%s)", (name,))
                existing = cursor.fetchone()
                
                if existing:
                    cursor.execute(
                        """UPDATE clients SET country=%s, address=%s, contact_person=%s, position=%s, phone=%s, email=%s,
                                              website=%s, buyer_type=%s, brands=%s, contact_person_2=%s, position_2=%s,
                                              phone_2=%s, email_2=%s, interest_level=%s, next_event_date=%s, next_event_type=%s WHERE id=%s""",
                        (country, address, contact_person, position, phone, email, website, buyer_type, brands,
                         contact_person_2, position_2, phone_2, email_2, interest_level, next_event_date, next_event_type, existing['id'])
                    )
                else:
                    cursor.execute(
                        """INSERT INTO clients (name, country, address, contact_person, position, phone, email, website, buyer_type, brands,
                                               contact_person_2, position_2, phone_2, email_2, interest_level, next_event_date, next_event_type)
                           VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                        (name, country, address, contact_person, position, phone, email, website, buyer_type, brands,
                         contact_person_2, position_2, phone_2, email_2, interest_level, next_event_date, next_event_type)
                    )
            
            conn.commit()
            cursor.close()
            conn.close()
            
        except Exception as e:
            return f"Помилка при обробці файлу: {str(e)}"
            
    return redirect(url_for('index'))

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
