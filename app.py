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
            phone TEXT,
            email TEXT,
            website TEXT,
            buyer_type TEXT,
            brands TEXT,
            contact_person_2 TEXT,
            position_2 TEXT,
            phone_2 TEXT,
            email_2 TEXT,
            interest_level TEXT
        )
    ''')
    
    cursor.execute("SELECT column_name FROM information_schema.columns WHERE table_name='clients'")
    existing_columns = [row[0] for row in cursor.fetchall()]
    
    new_fields = {
        'website': 'TEXT',
        'buyer_type': 'TEXT',
        'brands': 'TEXT',
        'contact_person_2': 'TEXT',
        'position_2': 'TEXT',
        'phone_2': 'TEXT',
        'email_2': 'TEXT',
        'interest_level': 'TEXT'
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
    cursor = conn.cursor(cursor_factory=DictCursor)
    
    cursor.execute("SELECT DISTINCT country FROM clients WHERE country IS NOT NULL AND country != '' ORDER BY country ASC")
    countries = [row['country'] for row in cursor.fetchall()]
    
    sql = "SELECT * FROM clients WHERE 1=1"
    params = []
    
    if search_query:
        sql += " AND (LOWER(name) LIKE LOWER(%s) OR LOWER(contact_person) LIKE LOWER(%s) OR LOWER(brands) LIKE LOWER(%s))"
        params.extend([f"%{search_query}%", f"%{search_query}%", f"%{search_query}%"])
        
    if country_filter:
        sql += " AND country = %s"
        params.append(country_filter)
        
    sql += " ORDER BY name ASC"
    
    cursor.execute(sql, params)
    clients = cursor.fetchall()
    
    cursor.close()
    conn.close()
    return render_template('index.html', clients=clients, countries=countries, search_query=search_query, country_filter=country_filter)

@app.route('/add_client', methods=['POST'])
@login_required
def add_client():
    name = request.form.get('name')
    country = request.form.get('country', '')
    address = request.form.get('address', '')
    contact_person = request.form.get('contact_person', '')
    phone = request.form.get('phone', '')
    email = request.form.get('email', '')
    website = request.form.get('website', '')
    buyer_type = request.form.get('buyer_type', '')
    interest_level = request.form.get('interest_level', 'немає зацікавленості')
    
    selected_brands = request.form.getlist('brands')
    brands = ", ".join(selected_brands) if selected_brands else ""
    
    contact_person_2 = request.form.get('contact_person_2', '')
    position_2 = request.form.get('position_2', '')
    phone_2 = request.form.get('phone_2', '')
    email_2 = request.form.get('email_2', '')
    
    if name:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            """INSERT INTO clients (name, country, address, contact_person, phone, email, website, buyer_type, brands, 
                                   contact_person_2, position_2, phone_2, email_2, interest_level) 
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
            (name, country, address, contact_person, phone, email, website, buyer_type, brands,
             contact_person_2, position_2, phone_2, email_2, interest_level)
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
    contact_person = request.form.get('contact_person', '')
    phone = request.form.get('phone', '')
    email = request.form.get('email', '')
    website = request.form.get('website', '')
    buyer_type = request.form.get('buyer_type', '')
    interest_level = request.form.get('interest_level', 'немає зацікавленості')
    
    selected_brands = request.form.getlist('brands')
    brands = ", ".join(selected_brands) if selected_brands else ""
    
    contact_person_2 = request.form.get('contact_person_2', '')
    position_2 = request.form.get('position_2', '')
    phone_2 = request.form.get('phone_2', '')
    email_2 = request.form.get('email_2', '')
    
    if name:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            """UPDATE clients SET name=%s, country=%s, address=%s, contact_person=%s, phone=%s, email=%s, 
                                  website=%s, buyer_type=%s, brands=%s, contact_person_2=%s, position_2=%s, 
                                  phone_2=%s, email_2=%s, interest_level=%s WHERE id=%s""",
            (name, country, address, contact_person, phone, email, website, buyer_type, brands,
             contact_person_2, position_2, phone_2, email_2, interest_level, client_id)
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
                       'contact_person', 'phone', 'email', 
                       'contact_person_2', 'position_2', 'phone_2', 'email_2', 'interest_level']
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
               c.contact_person AS "Контактна особа 1", c.phone AS "Телефон 1", c.email AS "Email 1",
               c.contact_person_2 AS "Контактна особа 2", c.position_2 AS "Посада 2", c.phone_2 AS "Телефон 2", c.email_2 AS "Email 2"
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

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
