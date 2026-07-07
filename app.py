import os
import sqlite3
from flask import Flask, render_template, request, redirect, url_for, flash
from datetime import datetime

app = Flask(__name__)
app.secret_key = 'super_secret_key_for_mayer_pro_crm'
DATABASE = 'crm.db'

def get_db_connection():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # 1. Таблиця клієнтів (якщо не існує)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS clients (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT EXISTS,
            interest_level TEXT,
            mayer_reg TEXT,
            buyer_type TEXT,
            brands TEXT,
            website TEXT,
            country TEXT,
            address TEXT,
            contact_person TEXT,
            position TEXT,
            phone TEXT,
            whatsapp_1 TEXT,
            email TEXT,
            contact_person_2 TEXT,
            position_2 TEXT,
            phone_2 TEXT,
            whatsapp_2 TEXT,
            email_2 TEXT,
            next_event_date TEXT,
            next_event_type TEXT,
            planned_revenue REAL DEFAULT 0,
            actual_revenue REAL DEFAULT 0,
            revenue_month TEXT
        )
    ''')
    
    # 2. Таблиця історії перемовин з новим полем author
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS negotiations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            client_id INTEGER,
            date TEXT,
            result TEXT,
            author TEXT,
            FOREIGN KEY(client_id) REFERENCES clients(id)
        )
    ''')
    
    # АВТО-АПГРЕЙД БАЗИ ДАНИХ:
    # Перевіряємо, чи є вже колонка 'author' в таблиці negotiations. Якщо немає — додаємо її.
    try:
        cursor.execute("SELECT author FROM negotiations LIMIT 1")
    except sqlite3.OperationalError:
        print("🔧 Оновлення бази даних: додавання колонки 'author' в таблицю negotiations...")
        cursor.execute("ALTER TABLE negotiations ADD COLUMN author TEXT DEFAULT 'Продажі'")
        conn.commit()
        
    conn.commit()
    conn.close()

# Ініціалізація бази даних при запуску додатка
init_db()

@app.route('/', methods=['GET'])
def index():
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Отримуємо фільтр місяця (за замовчуванням 'all')
    month_filter = request.args.get('month_filter', 'all')
    
    # Базовий запит для списку клієнтів
    if month_filter and month_filter != 'all':
        cursor.execute('SELECT * FROM clients WHERE revenue_month = ? ORDER BY name ASC', (month_filter,))
    else:
        cursor.execute('SELECT * FROM clients ORDER BY name ASC')
    clients = cursor.execute('SELECT * FROM clients ORDER BY name ASC').fetchall() # Повний список для таблиці
    
    # Фільтровані клієнти для фінансових підрахунків
    if month_filter and month_filter != 'all':
        filtered_clients = [c for c in clients if c['revenue_month'] == month_filter]
    else:
        filtered_clients = clients

    # Підрахунок фінансових підсумків
    total_planned = sum(c['planned_revenue'] if c['planned_revenue'] else 0 for c in filtered_clients)
    total_actual = sum(c['actual_revenue'] if c['actual_revenue'] else 0 for c in filtered_clients)
    total_remaining = total_planned - total_actual
    
    # Отримуємо сьогоднішню дату для підсвічування дій
    today_str = datetime.now().strftime('%Y-%m-%d')
    
    conn.close()
    return render_template('index.html', 
                           clients=clients, 
                           month_filter=month_filter,
                           total_planned=total_planned,
                           total_actual=total_actual,
                           total_remaining=total_remaining,
                           today_str=today_str)

@app.route('/add_client', methods=['POST'])
def add_client():
    name = request.form.get('name')
    interest_level = request.form.get('interest_level', 'не опрацьовано')
    mayer_reg = request.form.get('mayer_reg', 'Ні')
    buyer_type = request.form.get('buyer_type', 'не вказано')
    
    # Збір обраних брендів у рядок через кому
    brands_list = request.form.getlist('brands')
    brands = ', '.join(brands_list) if brands_list else ''
    
    website = request.form.get('website')
    country = request.form.get('country')
    address = request.form.get('address')
    
    contact_person = request.form.get('contact_person')
    position = request.form.get('position')
    phone = request.form.get('phone')
    whatsapp_1 = request.form.get('whatsapp_1')
    email = request.form.get('email')
    
    contact_person_2 = request.form.get('contact_person_2')
    position_2 = request.form.get('position_2')
    phone_2 = request.form.get('phone_2')
    whatsapp_2 = request.form.get('whatsapp_2')
    email_2 = request.form.get('email_2')
    
    next_event_date = request.form.get('next_event_date')
    next_event_type = request.form.get('next_event_type')
    
    # Фінансові поля
    planned_revenue = request.form.get('planned_revenue', 0)
    actual_revenue = request.form.get('actual_revenue', 0)
    revenue_month = request.form.get('revenue_month', '')
    
    try:
        planned_revenue = float(planned_revenue) if planned_revenue else 0.0
        actual_revenue = float(actual_revenue) if actual_revenue else 0.0
    except ValueError:
        planned_revenue = 0.0
        actual_revenue = 0.0

    if name:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO clients (
                name, interest_level, mayer_reg, buyer_type, brands, website, country, address,
                contact_person, position, phone, whatsapp_1, email,
                contact_person_2, position_2, phone_2, whatsapp_2, email_2,
                next_event_date, next_event_type, planned_revenue, actual_revenue, revenue_month
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            name, interest_level, mayer_reg, buyer_type, brands, website, country, address,
            contact_person, position, phone, whatsapp_1, email,
            contact_person_2, position_2, phone_2, whatsapp_2, email_2,
            next_event_date, next_event_type, planned_revenue, actual_revenue, revenue_month
        ))
        conn.commit()
        conn.close()
        flash('Клієнта успішно додано!', 'success')
    else:
        flash('Назва компанії є обовʼязковою!', 'danger')
        
    return redirect(url_for('index'))

@app.route('/client/<int:client_id>', methods=['GET', 'POST'])
def client_detail(client_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Обробка додавання нового запису в історію перемовин
    if request.method == 'POST':
        result = request.form.get('result')
        author = request.form.get('author', 'Продажі') # Отримуємо роль автора (за замовчуванням Продажі)
        
        if result:
            current_time = datetime.now().strftime('%Y-%m-%d %H:%M')
            cursor.execute(
                'INSERT INTO negotiations (client_id, date, result, author) VALUES (?, ?, ?, ?)',
                (client_id, current_time, result, author)
            )
            conn.commit()
            flash('Запис додано до історії!', 'success')
            return redirect(url_for('client_detail', client_id=client_id))
            
    # Завантаження даних про клієнта та його історію перемовин
    client = cursor.execute('SELECT * FROM clients WHERE id = ?', (client_id,)).fetchone()
    history = cursor.execute('SELECT * FROM negotiations WHERE client_id = ? ORDER BY id DESC', (client_id,)).fetchall()
    conn.close()
    
    if not client:
        flash('Клієнта не знайдено!', 'danger')
        return redirect(url_for('index'))
        
    return render_template('client.html', client=client, history=history)

@app.route('/edit_client/<int:client_id>', methods=['POST'])
def edit_client(client_id):
    name = request.form.get('name')
    interest_level = request.form.get('interest_level')
    mayer_reg = request.form.get('mayer_reg')
    buyer_type = request.form.get('buyer_type')
    
    brands_list = request.form.getlist('brands')
    brands = ', '.join(brands_list) if brands_list else ''
    
    website = request.form.get('website')
    country = request.form.get('country')
    address = request.form.get('address')
    
    contact_person = request.form.get('contact_person')
    position = request.form.get('position')
    phone = request.form.get('phone')
    whatsapp_1 = request.form.get('whatsapp_1')
    email = request.form.get('email')
    
    contact_person_2 = request.form.get('contact_person_2')
    position_2 = request.form.get('position_2')
    phone_2 = request.form.get('phone_2')
    whatsapp_2 = request.form.get('whatsapp_2')
    email_2 = request.form.get('email_2')
    
    next_event_date = request.form.get('next_event_date')
    next_event_type = request.form.get('next_event_type')
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute('''
        UPDATE clients SET 
            name=?, interest_level=?, mayer_reg=?, buyer_type=?, brands=?, website=?, country=?, address=?,
            contact_person=?, position=?, phone=?, whatsapp_1=?, email=?,
            contact_person_2=?, position_2=?, phone_2=?, whatsapp_2=?, email_2=?,
            next_event_date=?, next_event_type=?
        WHERE id=?
    ''', (
        name, interest_level, mayer_reg, buyer_type, brands, website, country, address,
        contact_person, position, phone, whatsapp_1, email,
        contact_person_2, position_2, phone_2, whatsapp_2, email_2,
        next_event_date, next_event_type, client_id
    ))
    
    conn.commit()
    conn.close()
    flash('Картку клієнта успішно оновлено!', 'success')
    return redirect(url_for('client_detail', client_id=client_id))

@app.route('/update_revenue/<int:client_id>', methods=['POST'])
def update_revenue(client_id):
    planned_revenue = request.form.get('planned_revenue', 0)
    actual_revenue = request.form.get('actual_revenue', 0)
    revenue_month = request.form.get('revenue_month', '')
    
    try:
        planned_revenue = float(planned_revenue) if planned_revenue else 0.0
        actual_revenue = float(actual_revenue) if actual_revenue else 0.0
    except ValueError:
        planned_revenue = 0.0
        actual_revenue = 0.0
        
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        UPDATE clients SET planned_revenue=?, actual_revenue=?, revenue_month=? WHERE id=?
    ''', (planned_revenue, actual_revenue, revenue_month, client_id))
    conn.commit()
    conn.close()
    
    flash('Фінансові показники оновлено!', 'success')
    return redirect(url_for('index'))

@app.route('/edit_negotiation/<int:neg_id>', methods=['POST'])
def edit_negotiation(neg_id):
    client_id = request.form.get('client_id')
    new_result = request.form.get('result')
    
    if new_result:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('UPDATE negotiations SET result = ? WHERE id = ?', (new_result, neg_id))
        conn.commit()
        conn.close()
        flash('Запис в історії успішно відредаговано!', 'success')
        
    return redirect(url_for('client_detail', client_id=client_id))

@app.route('/delete_negotiation/<int:neg_id>', methods=['POST'])
def delete_negotiation(neg_id):
    client_id = request.form.get('client_id')
    
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('DELETE FROM negotiations WHERE id = ?', (neg_id,))
    conn.commit()
    conn.close()
    
    flash('Запис видалено з історії.', 'warning')
    return redirect(url_for('client_detail', client_id=client_id))

@app.route('/delete_client/<int:client_id>', methods=['POST'])
def delete_client(client_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    # Видаляємо спочатку історію перемовин, щоб не залишати сміття в базі
    cursor.execute('DELETE FROM negotiations WHERE client_id = ?', (client_id,))
    # Видаляємо самого клієнта
    cursor.execute('DELETE FROM clients WHERE id = ?', (client_id,))
    conn.commit()
    conn.close()
    
    flash('Клієнта та всю історію його активностей остаточно видалено!', 'danger')
    return redirect(url_for('index'))

if __name__ == '__main__':
    # Працюємо на порті 5000 (стандарт для Flask) або тому, який видасть Render
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=True)
