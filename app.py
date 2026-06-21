import os
import psycopg2
from psycopg2.extras import DictCursor
from flask import Flask, render_template, request, redirect, url_for, session
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime

app = Flask(__name__)

# Секретний ключ для сесій (захист авторизації)
app.secret_key = os.environ.get('SECRET_KEY', 'super-secret-key-change-me')

# Логін та пароль для входу в CRM (можна буде змінити в налаштуваннях сервера)
CRM_USERNAME = os.environ.get('CRM_USERNAME', 'admin')
# У реальному житті краще зберігати хеш, але для старту задамо простий пароль через змінні
CRM_PASSWORD = os.environ.get('CRM_PASSWORD', 'Plonaris2026') 

DATABASE_URL = os.environ.get('DATABASE_URL')

def get_db_connection():
    """Підключення до бази даних PostgreSQL"""
    conn = psycopg2.connect(DATABASE_URL, sslmode='require')
    return conn

def init_db():
    """Ініціалізація таблиць у PostgreSQL"""
    conn = get_db_connection()
    cursor = conn.cursor()
    # Таблиця клієнтів
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS clients (
            id SERIAL PRIMARY KEY,
            name TEXT NOT NULL,
            address TEXT,
            phone TEXT,
            email TEXT
        )
    ''')
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

# Ініціалізуємо БД, якщо підключено URL
if DATABASE_URL:
    init_db()

# Декоратор для захисту сторінок (перевірка чи залогінений користувач)
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
    """Сторінка входу"""
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
    """Головна сторінка зі списком клієнтів"""
    conn = get_db_connection()
    cursor = conn.cursor(cursor_factory=DictCursor)
    cursor.execute("SELECT * FROM clients ORDER BY name ASC")
    clients = cursor.fetchall()
    cursor.close()
    conn.close()
    return render_template('index.html', clients=clients)

@app.route('/add_client', methods=['POST'])
@login_required
def add_client():
    name = request.form.get('name')
    address = request.form.get('address')
    phone = request.form.get('phone')
    email = request.form.get('email')
    
    if name:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO clients (name, address, phone, email) VALUES (%s, %s, %s, %s)",
            (name, address, phone, email)
        )
        conn.commit()
        cursor.close()
        conn.close()
    return redirect(url_for('index'))

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

if __name__ == '__main__':
    # На сервері порт підтягується автоматично
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
