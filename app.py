import os
import psycopg2
from psycopg2.extras import DictCursor
from flask import Flask, render_template, request, redirect, url_for, session, send_file
from datetime import datetime
import pandas as pd
import io

app = Flask(__name__)

# Секретний ключ для захисту сесій входу
app.secret_key = os.environ.get('SECRET_KEY', 'super-secret-key-change-me')

# Логін та пароль із змінних оточення Render
CRM_USERNAME = os.environ.get('CRM_USERNAME', 'admin')
CRM_PASSWORD = os.environ.get('CRM_PASSWORD', 'Mayer2026') 

DATABASE_URL = os.environ.get('DATABASE_URL')

def get_db_connection():
    conn = psycopg2.connect(DATABASE_URL, sslmode='require')
    return conn

def init_db():
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Створюємо таблицю клієнтів з усіма необхідними полями
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS clients (
            id SERIAL PRIMARY KEY,
            name TEXT NOT NULL,
            country TEXT,
            address TEXT,
            contact_person TEXT,
            phone TEXT,
            email TEXT
        )
    ''')
    
    # Автоматична міграція бази даних (додавання нових колонок, якщо вони відсутні)
    cursor.execute("SELECT column_name FROM information_schema.columns WHERE table_name='clients'")
    existing_columns = [row[0] for row in cursor.fetchall()]
    
    if 'country' not in existing_columns:
        cursor.execute("ALTER TABLE clients ADD COLUMN country TEXT;")
    if 'address' not in existing_columns:
        cursor.execute("ALTER TABLE clients ADD COLUMN address TEXT;")
    if 'contact_person' not in existing_columns:
        cursor.execute("ALTER TABLE clients ADD COLUMN contact_person TEXT;")

    # Таблиця історії перемовин
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

# Декоратор для захисту маршрутів (вхід обов'язковий)
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
    
    # Отримуємо список унікальних країн для фільтра
    cursor.execute("SELECT DISTINCT country FROM clients WHERE country IS NOT NULL AND country != '' ORDER BY country ASC")
    countries = [row['country'] for row in cursor.fetchall()]
    
    # Головний SQL-запит для пошуку та фільтрації
    sql = "SELECT * FROM clients WHERE 1=1"
    params = []
    
    if search_query:
        sql += " AND (LOWER(name) LIKE LOWER(%s) OR LOWER(contact_person) LIKE LOWER(%s))"
        params.extend([f"%{search_query}%", f"%{search_query}%"])
        
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
    country = request.form.get('country')
    address = request.form.get('address')
    contact_person = request.form.get('contact_person')
    phone = request.form.get('phone')
    email = request.form.get('email')
    
    if name:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO clients (name, country, address, contact_person, phone, email) VALUES (%s, %s, %s, %s, %s, %s)",
            (name, country, address, contact_person, phone, email)
        )
        conn.commit()
        cursor.close()
        conn.close()
    return redirect(url_for('index'))

@app.route('/edit_client/<int:client_id>', methods=['POST'])
@login_required
def edit_client(client_id):
    name = request.form.get('name')
    country = request.form.get('country')
    address = request.form.get('address')
    contact_person = request.form.get('contact_person')
    phone = request.form.get('phone')
    email = request.form.get('email')
    
    if name:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE clients SET name=%s, country=%s, address=%s, contact_person=%s, phone=%s, email=%s WHERE id=%s",
            (name, country, address, contact_person, phone, email, client_id)
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
    client = cursor.fetchone()
    
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
        SELECT c.name AS "Назва компанії", c.country AS "Країна", c.address AS "Адреса",
               c.contact_person AS "Відповідальна особа", c.phone AS "Телефон", c.email AS "Email"
        FROM clients c ORDER BY c.name ASC
    """
    # Виправлено механічну помилку read_sql_out -> read_sql
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
