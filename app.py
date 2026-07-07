import os
import json  # Обов'язковий імпорт бібліотеки json для календаря!
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
    
    # 1. Таблиця клієнтів
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS clients (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
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
    
    # 2. Таблиця історії перемовин
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS negotiations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            client_id INTEGER,
            date TEXT,
            result TEXT,
            author TEXT,
            FOREIGN KEY(client_id) REFERENCES clients (id) ON DELETE CASCADE
        )
    ''')
    
    # Автоматичний апгрейд полей таблиці історії перемовин
    try:
        cursor.execute("SELECT author FROM negotiations LIMIT 1")
    except sqlite3.OperationalError:
        print("🔧 Оновлення бази даних: додавання колонки 'author'...")
        cursor.execute("ALTER TABLE negotiations ADD COLUMN author TEXT DEFAULT 'Продажі'")
        conn.commit()
        
    conn.commit()
    cursor.close()
    conn.close()

# Ініціалізація бази даних при старті
init_db()

@app.route('/', methods=['GET'])
def index():
    conn = get_db_connection()
    cursor = conn.cursor()
    
    search_query = request.args.get('search', '').strip()
    interest_filter = request.args.get('interest', '').strip()
    country_filter = request.args.get('country', '').strip()
    finance_month_filter = request.args.get('finance_month', '').strip()
    
    # Збір аналітики для лівої панелі контрагентів
    cursor.execute("SELECT COUNT(*) FROM clients")
    total_clients = cursor.fetchone()[0]
    
    cursor.execute("SELECT interest_level, COUNT(*) FROM clients GROUP BY interest_level")
    raw_interest = cursor.fetchall()
    interest_stats = {'не опрацьовано': 0, 'немає зацікавленості': 0, 'середня зацікавленість': 0, 'зацікавленість': 0}
    for row in raw_interest:
        status = row[0] if row[0] else 'не опрацьовано'
        if status in interest_stats:
            interest_stats[status] = row[1]
            
    cursor.execute("SELECT country, COUNT(*) FROM clients WHERE country IS NOT NULL AND country != '' GROUP BY country ORDER BY COUNT(*) DESC")
    country_stats = cursor.fetchall()

    cursor.execute("SELECT buyer_type, COUNT(*) FROM clients WHERE buyer_type IS NOT NULL AND buyer_type != 'не вказано' AND buyer_type != '' GROUP BY buyer_type ORDER BY COUNT(*) DESC")
    buyer_type_stats = cursor.fetchall()
    
    # Генерація списку для вибору клієнтів у фінансовому плані
    all_selector_clients = cursor.execute("SELECT id, name FROM clients ORDER BY name ASC").fetchall()
    
    # Основна побудова SQL запиту для клієнтів
    sql = "SELECT * FROM clients WHERE 1=1"
    params = []
    
    if search_query:
        sql += " AND (LOWER(name) LIKE LOWER(?) OR LOWER(contact_person) LIKE LOWER(?) OR LOWER(brands) LIKE LOWER(?) OR LOWER(country) LIKE LOWER(?))"
        params.extend([f"%{search_query}%", f"%{search_query}%", f"%{search_query}%", f"%{search_query}%"])
    if interest_filter:
        sql += " AND interest_level = ?"
        params.append(interest_filter)
    if country_filter:
        sql += " AND country = ?"
        params.append(country_filter)
        
    sql += " ORDER BY name ASC"
    cursor.execute(sql, params)
    raw_clients = cursor.fetchall()
    
    clients = []
    for row in raw_clients:
        # Зчитуємо останню подію для кожного контрагента
        last_act_row = cursor.execute("SELECT MAX(date) FROM negotiations WHERE client_id = ?", (row['id'],)).fetchone()
        last_activity = last_act_row[0] if last_act_row and last_act_row[0] else ''
        
        clients.append({
            'id': row['id'], 'name': row['name'], 'country': row['country'] if row['country'] else '', 'address': row['address'] if row['address'] else '',
            'contact_person': row['contact_person'] if row['contact_person'] else '', 'position': row['position'] if row['position'] else '', 'phone': row['phone'] if row['phone'] else '',
            'whatsapp_1': row['whatsapp_1'] if row['whatsapp_1'] else '', 'email': row['email'] if row['email'] else '', 'contact_person_2': row['contact_person_2'] if row['contact_person_2'] else '',
            'position_2': row['position_2'] if row['position_2'] else '', 'phone_2': row['phone_2'] if row['phone_2'] else '', 'whatsapp_2': row['whatsapp_2'] if row['whatsapp_2'] else '',
            'email_2': row['email_2'] if row['email_2'] else '', 'next_event_date': row['next_event_date'] if row['next_event_date'] else '', 'next_event_type': row['next_event_type'] if row['next_event_type'] else '',
            'buyer_type': row['buyer_type'] if row['buyer_type'] else 'не вказано', 'brands': row['brands'] if row['brands'] else '-',
            'interest_level': row['interest_level'] if row['interest_level'] else 'не опрацьовано', 'mayer_reg': row['mayer_reg'] if row['mayer_reg'] else 'Ні',
            'planned_revenue': float(row['planned_revenue'] or 0), 'actual_revenue': float(row['actual_revenue'] or 0), 'revenue_month': row['revenue_month'] if row['revenue_month'] else '',
            'last_activity': last_activity
        })
        
    # Блок фінансів: збір даних та фільтрація
    finance_plans = []
    for c in clients:
        if c['planned_revenue'] > 0 or c['actual_revenue'] > 0:
            if not finance_month_filter or finance_month_filter == c['revenue_month']:
                # Мапимо структуру під очікування шаблону річного плану
                finance_plans.append({
                    'id': c['id'], 'client_id': c['id'], 'client_name': c['name'], 'country': c['country'] if c['country'] else '-',
                    'planned_amount': c['planned_revenue'], 'actual_amount': c['actual_revenue'], 'month_name': c['revenue_month'] if c['revenue_month'] else '-',
                    'payment_date': '-'
                })
                
    total_planned = sum(f['planned_amount'] for f in finance_plans)
    total_actual = sum(f['actual_amount'] for f in finance_plans)
    total_remaining = total_planned - total_actual
    
    # Дані для календаря дій JavaScript
    clients_js_data = []
    busy_dates = []
    for c in clients:
        if c['next_event_date']:
            busy_dates.append(c['next_event_date'])
            clients_js_data.append({
                'id': c['id'], 'name': c['name'].replace("'", "\\'").replace('"', '\\"'), 'country': c['country'],
                'next_event_date': c['next_event_date'], 'next_event_type': c['next_event_type']
            })
            
    json_clients = json.dumps(clients_js_data, ensure_ascii=False)
    json_busy_dates = json.dumps(busy_dates, ensure_ascii=False)
    today_str = datetime.now().strftime('%Y-%m-%d')
    
    cursor.close()
    conn.close()
    return render_template(
        'index.html', clients=clients, all_selector_clients=all_selector_clients,
        search_query=search_query, interest_filter=interest_filter, country_filter=country_filter,
        finance_month_filter=finance_month_filter, total_clients=total_clients, interest_stats=interest_stats,
        country_stats=country_stats, buyer_type_stats=buyer_type_stats, finance_plans=finance_plans,
        total_planned=total_planned, total_actual=total_actual, total_remaining=total_remaining,
        json_clients=json_clients, json_busy_dates=json_busy_dates, today_date=today_str
    )

@app.route('/add_client', methods=['POST'])
def add_client():
    name = request.form.get('name')
    interest_level = request.form.get('interest_level', 'не опрацьовано')
    mayer_reg = request.form.get('mayer_reg', 'Ні')
    buyer_type = request.form.get('buyer_type', 'не вказано')
    
    brands_list = request.form.getlist('brands')
    brands = ', '.join(brands_list) if brands_list else ''
    
    website = request.form.get('website', '')
    country = request.form.get('country', '')
    address = request.form.get('address', '')
    
    contact_person = request.form.get('contact_person', '')
    position = request.form.get('position', '')
    phone = request.form.get('phone', '')
    whatsapp_1 = request.form.get('whatsapp_1', '')
    email = request.form.get('email', '')
    
    contact_person_2 = request.form.get('contact_person_2', '')
    position_2 = request.form.get('position_2', '')
    phone_2 = request.form.get('phone_2', '')
    whatsapp_2 = request.form.get('whatsapp_2', '')
    email_2 = request.form.get('email_2', '')
    
    next_event_date = request.form.get('next_event_date', '')
    next_event_type = request.form.get('next_event_type', '')
    
    if name:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO clients (
                name, interest_level, mayer_reg, buyer_type, brands, website, country, address,
                contact_person, position, phone, whatsapp_1, email,
                contact_person_2, position_2, phone_2, whatsapp_2, email_2,
                next_event_date, next_event_type
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            name, interest_level, mayer_reg, buyer_type, brands, website, country, address,
            contact_person, position, phone, whatsapp_1, email,
            contact_person_2, position_2, phone_2, whatsapp_2, email_2,
            next_event_date, next_event_type
        ))
        conn.commit()
        cursor.close()
        conn.close()
    return redirect(url_for('index'))

@app.route('/edit_client/<int:client_id>', methods=['POST'])
def edit_client(client_id):
    name = request.form.get('name')
    interest_level = request.form.get('interest_level')
    mayer_reg = request.form.get('mayer_reg')
    buyer_type = request.form.get('buyer_type')
    
    brands_list = request.form.getlist('brands')
    brands = ', '.join(brands_list) if brands_list else ''
    
    website = request.form.get('website', '')
    country = request.form.get('country', '')
    address = request.form.get('address', '')
    
    contact_person = request.form.get('contact_person', '')
    position = request.form.get('position', '')
    phone = request.form.get('phone', '')
    whatsapp_1 = request.form.get('whatsapp_1', '')
    email = request.form.get('email', '')
    
    contact_person_2 = request.form.get('contact_person_2', '')
    position_2 = request.form.get('position_2', '')
    phone_2 = request.form.get('phone_2', '')
    whatsapp_2 = request.form.get('whatsapp_2', '')
    email_2 = request.form.get('email_2', '')
    
    next_event_date = request.form.get('next_event_date', '')
    next_event_type = request.form.get('next_event_type', '')
    
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
    cursor.close()
    conn.close()
    return redirect(url_for('client_detail', client_id=client_id))

@app.route('/add_finance_plan', methods=['POST'])
def add_finance_plan():
    client_id = request.form.get('client_id')
    planned_amount = request.form.get('planned_amount', 0)
    month_name = request.form.get('month_name', '')
    actual_amount = request.form.get('actual_amount', 0)
    
    try:
        planned_amount = float(planned_amount) if planned_amount else 0.0
        actual_amount = float(actual_amount) if actual_amount else 0.0
    except ValueError:
        planned_amount = 0.0
        actual_amount = 0.0
        
    if client_id:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('''
            UPDATE clients SET planned_revenue=?, actual_revenue=?, revenue_month=? WHERE id=?
        ''', (planned_amount, actual_amount, month_name, client_id))
        conn.commit()
        cursor.close()
        conn.close()
    return redirect(url_for('index', finance_month=month_name))

@app.route('/edit_finance_plan/<int:plan_id>', methods=['POST'])
def edit_finance_plan(plan_id):
    planned_amount = request.form.get('planned_amount', 0)
    month_name = request.form.get('month_name', '')
    actual_amount = request.form.get('actual_amount', 0)
    
    try:
        planned_amount = float(planned_amount) if planned_amount else 0.0
        actual_amount = float(actual_amount) if actual_amount else 0.0
    except ValueError:
        planned_amount = 0.0
        actual_amount = 0.0
        
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        UPDATE clients SET planned_revenue=?, actual_revenue=?, revenue_month=? WHERE id=?
    ''', (planned_amount, actual_amount, month_name, plan_id))
    conn.commit()
    cursor.close()
    conn.close()
    return redirect(url_for('index', finance_month=month_name))

@app.route('/delete_finance_plan/<int:plan_id>', methods=['POST'])
def delete_finance_plan(plan_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('UPDATE clients SET planned_revenue=0, actual_revenue=0, revenue_month=\'\' WHERE id=?', (plan_id,))
    conn.commit()
    cursor.close()
    conn.close()
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
        cursor.close()
        conn.close()
    return redirect(url_for('client_detail', client_id=client_id))

@app.route('/delete_negotiation/<int:neg_id>', methods=['POST'])
def delete_negotiation(neg_id):
    client_id = request.form.get('client_id')
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('DELETE FROM negotiations WHERE id = ?', (neg_id,))
    conn.commit()
    cursor.close()
    conn.close()
    return redirect(url_for('client_detail', client_id=client_id))

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
