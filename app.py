import os
import json
import psycopg2
from psycopg2.extras import DictCursor
from flask import Flask, render_template, request, redirect, url_for, session, send_file, jsonify
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
            next_event_type TEXT,
            mayer_reg TEXT,
            whatsapp_1 TEXT,
            whatsapp_2 TEXT
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
        'next_event_type': 'TEXT',
        'mayer_reg': 'TEXT',
        'whatsapp_1': 'TEXT',
        'whatsapp_2': 'TEXT'
    }
    
    for field, f_type in new_fields.items():
        if field not in existing_columns:
            cursor.execute(f"ALTER TABLE clients ADD COLUMN {field} {f_type};")

    # СТВОРЕННЯ ТАБЛИЦІ ПЕРЕМОВИН З ПОЛЕМ AUTHOR
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS negotiations (
            id SERIAL PRIMARY KEY,
            client_id INTEGER,
            date TEXT,
            result TEXT,
            author TEXT,
            FOREIGN KEY (client_id) REFERENCES clients (id) ON DELETE CASCADE
        )
    ''')

    # АВТОМАТИЧНЕ ДОДАВАННЯ КОЛОНКИ AUTHOR, ЯКЩО ВОНА ЩЕ НЕ ІСНУЄ В POSTGRES
    cursor.execute("SELECT column_name FROM information_schema.columns WHERE table_name='negotiations'")
    existing_neg_columns = [row[0] for row in cursor.fetchall()]
    if 'author' not in existing_neg_columns:
        cursor.execute("ALTER TABLE negotiations ADD COLUMN author TEXT DEFAULT 'Продажі';")

    # СТВОРЕННЯ ТАБЛИЦІ ЗАВДАНЬ (ПЛАНЕР)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS tasks (
            id SERIAL PRIMARY KEY,
            text TEXT NOT NULL,
            deadline TEXT,
            author TEXT DEFAULT 'Продажі',
            status TEXT DEFAULT 'in_progress'
        )
    ''')

    # СТВОРЕННЯ ТАБЛИЦІ РІЧНОГО ПЛАНУ SALES_PLANS
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS sales_plans (
            id SERIAL PRIMARY KEY,
            client_id INTEGER NOT NULL,
            planned_amount NUMERIC(12, 2) DEFAULT 0,
            month_name TEXT,
            actual_amount NUMERIC(12, 2) DEFAULT 0,
            payment_date TEXT,
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
    interest_filter = request.args.get('interest', '').strip()
    country_filter = request.args.get('country', '').strip()
    finance_month_filter = request.args.get('finance_month', '').strip()
    
    conn = get_db_connection()
    
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
        
        fix_cursor.execute("""
            UPDATE clients 
            SET interest_level = 'не опрацьовано' 
            WHERE id NOT IN (SELECT DISTINCT client_id FROM negotiations);
        """)
        
        conn.commit()
    
    country_cursor = conn.cursor()
    # ВИПРАВЛЕНО СИНТАКСИС КРАЇН: IS NOT NULL ЗАМІСТЬ IS NOT EXISTS
    country_cursor.execute("SELECT DISTINCT country FROM clients WHERE country IS NOT NULL AND country != '' ORDER BY country ASC")
    countries = [row[0] for row in country_cursor.fetchall()]
    country_cursor.close()
    
    stats_cursor = conn.cursor()
    stats_cursor.execute("SELECT COUNT(*) FROM clients")
    total_clients = stats_cursor.fetchone()[0]
    
    stats_cursor.execute("SELECT interest_level, COUNT(*) FROM clients GROUP BY interest_level")
    raw_interest = stats_cursor.fetchall()
    
    interest_stats = {'не опрацьовано': 0, 'немає зацікавленості': 0, 'середня зацікавленість': 0, 'зацікавленість': 0}
    for row in raw_interest:
        status = row[0] if row[0] else 'не опрацьовано'
        if status in interest_stats:
            interest_stats[status] = row[1]
            
    stats_cursor.execute("SELECT country, COUNT(*) FROM clients WHERE country IS NOT NULL AND country != '' GROUP BY country ORDER BY COUNT(*) DESC")
    country_stats = stats_cursor.fetchall()

    stats_cursor.execute("SELECT buyer_type, COUNT(*) FROM clients WHERE buyer_type IS NOT NULL AND buyer_type != 'не вказано' AND buyer_type != '' GROUP BY buyer_type ORDER BY COUNT(*) DESC")
    buyer_type_stats = stats_cursor.fetchall()
    stats_cursor.close()
    
    # ФІНАНСОВИЙ БЛОК: СТАТИСТИКА ТА ФІЛЬТР МІСЯЦІВ
    dict_cursor = conn.cursor(cursor_factory=DictCursor)
    finance_sql = """
        SELECT sp.id, sp.client_id, sp.planned_amount, sp.month_name, sp.actual_amount, sp.payment_date,
               c.name as client_name, c.country as client_country
        FROM sales_plans sp
        JOIN clients c ON sp.client_id = c.id
    """
    finance_params = []
    if finance_month_filter:
        finance_sql += " WHERE sp.month_name = %s"
        finance_params.append(finance_month_filter)
        
    finance_sql += " ORDER BY sp.id DESC"
    dict_cursor.execute(finance_sql, finance_params)
    finance_rows = dict_cursor.fetchall()
    
    total_planned = 0
    total_actual = 0
    finance_plans = []
    for row in finance_rows:
        p_amt = float(row['planned_amount'] or 0)
        a_amt = float(row['actual_amount'] or 0)
        total_planned += p_amt
        total_actual += a_amt
        finance_plans.append({
            'id': row['id'], 'client_id': row['client_id'], 'client_name': row['client_name'],
            'country': row['client_country'] if row['client_country'] else '-',
            'planned_amount': p_amt, 'month_name': row['month_name'] if row['month_name'] else '-',
            'actual_amount': a_amt, 'payment_date': row['payment_date'] if row['payment_date'] else '-'
        })
    total_remaining = total_planned - total_actual
    
    dict_cursor.execute("SELECT id, name FROM clients ORDER BY name ASC")
    all_selector_clients = dict_cursor.fetchall()

    # ЗБІР АКТИВНИХ ЗАВДАНЬ ДЛЯ КАЛЕНДАРЯ ЗАДАЧНИКА
    dict_cursor.execute("SELECT id, text, deadline, author, status FROM tasks ORDER BY id DESC")
    tasks_raw = dict_cursor.fetchall()
    tasks = [dict(t) for t in tasks_raw]

    # НЕЗАЛЕЖНИЙ ЗБІР ДАНИХ ДЛЯ КАЛЕНДАРЯ КЛІЄНТІВ
    cal_cursor = conn.cursor(cursor_factory=DictCursor)
    cal_cursor.execute("SELECT id, name, country, contact_person, phone, next_event_date, next_event_type FROM clients WHERE next_event_date IS NOT NULL AND next_event_date != ''")
    all_raw_cal = cal_cursor.fetchall()
    
    clients_js_data = []
    busy_dates = []
    for r in all_raw_cal:
        c_date = str(r['next_event_date'])
        busy_dates.append(c_date)
        clients_js_data.append({
            'id': int(r['id']),
            'name': str(r['name']).replace('"', '\\"').replace("'", "\\'"),
            'country': str(r['country']).replace('"', '\\"').replace("'", "\\'") if r['country'] else '',
            'contact_person': str(r['contact_person']).replace('"', '\\"').replace("'", "\\'") if r['contact_person'] else '',
            'phone': str(r['phone']) if r['phone'] else '',
            'next_event_date': c_date,
            'next_event_type': str(r['next_event_type']) if r['next_event_type'] else ''
        })
    cal_cursor.close()
    
    cursor = conn.cursor(cursor_factory=DictCursor)
    sql = """
        SELECT c.*, 
               (SELECT MAX(n.date)::TEXT FROM negotiations n WHERE n.client_id = c.id) AS last_activity 
        FROM clients c 
        WHERE 1=1
    """
    params = []
    
    if search_query:
        sql += " AND (LOWER(c.name) LIKE LOWER(%s) OR LOWER(c.contact_person) LIKE LOWER(%s) OR LOWER(c.brands) LIKE LOWER(%s) OR LOWER(c.country) LIKE LOWER(%s) OR LOWER(c.buyer_type) LIKE LOWER(%s))"
        params.extend([f"%{search_query}%", f"%{search_query}%", f"%{search_query}%", f"%{search_query}%", f"%{search_query}%"])
        
    if interest_filter:
        sql += " AND c.interest_level = %s"
        params.append(interest_filter)
        
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
            'id': int(row['id']),
            'name': row['name'] if row['name'] else '',
            'country': row['country'] if row['country'] else '',
            'address': row['address'] if row['address'] else '',
            'contact_person': row['contact_person'] if row['contact_person'] else '',
            'position': row['position'] if row['position'] else '',
            'phone': row['phone'] if row['phone'] else '',
            'email': row['email'] if row['email'] else '',
            'website': row['website'] if row['website'] else '',
            'buyer_type': row['buyer_type'] if row['buyer_type'] else 'не вказано',
            'brands': row['brands'] if row['brands'] else '-',
            'interest_level': row['interest_level'] if row['interest_level'] else 'не опрацьовано',
            'last_activity': row['last_activity'] if row['last_activity'] else '',
            'next_event_date': str(row['next_event_date']) if row['next_event_date'] else '',
            'next_event_type': str(row['next_event_type']) if row['next_event_type'] else '',
            'mayer_reg': row['mayer_reg'] if row['mayer_reg'] else 'Ні'
        })
    cursor.close()
    dict_cursor.close()
    conn.close()
    
    json_clients = json.dumps(clients_js_data, ensure_ascii=False)
    json_busy_dates = json.dumps(busy_dates, ensure_ascii=False)
    
    return render_template(
        'index.html', 
        clients=clients, 
        countries=countries, 
        all_selector_clients=all_selector_clients,
        search_query=search_query, 
        interest_filter=interest_filter,
        country_filter=country_filter,
        finance_month_filter=finance_month_filter,
        total_clients=total_clients,
        interest_stats=interest_stats,
        country_stats=country_stats,
        buyer_type_stats=buyer_type_stats,
        finance_plans=finance_plans, 
        total_planned=total_planned, 
        total_actual=total_actual, 
        total_remaining=total_remaining,
        json_clients=json_clients,
        json_busy_dates=json_busy_dates,
        today_date=today_str,
        tasks=tasks,
        json_tasks=json.dumps(tasks, ensure_ascii=False)
    )

# МАРШРУТИ ПЛАНЕРА ЗАВДАНЬ
@app.route('/add_task', methods=['POST'])
@login_required
def add_task():
    text = request.form.get('text')
    deadline = request.form.get('deadline', '')
    author = request.form.get('author', 'Продажі')
    if text and deadline:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("INSERT INTO tasks (text, deadline, author, status) VALUES (%s, %s, %s, 'in_progress')", (text, deadline, author))
        conn.commit()
        cursor.close()
        conn.close()
    return redirect(url_for('index', tab='tasks'))

@app.route('/toggle_task/<int:task_id>', methods=['POST'])
@login_required
def toggle_task(task_id):
    current_status = request.form.get('current_status')
    new_status = 'completed' if current_status == 'in_progress' else 'in_progress'
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE tasks SET status=%s WHERE id=%s", (new_status, task_id))
    conn.commit()
    cursor.close()
    conn.close()
    return redirect(url_for('index', tab='tasks'))

@app.route('/delete_task/<int:task_id>', methods=['POST'])
@login_required
def delete_task(task_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM tasks WHERE id=%s", (task_id,))
    conn.commit()
    cursor.close()
    conn.close()
    return redirect(url_for('index', tab='tasks'))

@app.route('/add_client', methods=['POST'])
@login_required
def add_client():
    name = request.form.get('name')
    country = request.form.get('country', '')
    address = request.form.get('address', '')
    buyer_type = request.form.get('buyer_type', '')
    interest_level = request.form.get('interest_level', 'не опрацьовано')
    website = request.form.get('website', '')
    next_event_date = request.form.get('next_event_date', '')
    next_event_type = request.form.get('next_event_type', '')
    mayer_reg = request.form.get('mayer_reg', 'Ні')
    whatsapp_1 = request.form.get('whatsapp_1', '')
    whatsapp_2 = request.form.get('whatsapp_2', '')
    
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
                                   contact_person_2, position_2, phone_2, email_2, interest_level, next_event_date, next_event_type, mayer_reg, whatsapp_1, whatsapp_2) 
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
            (name, country, address, contact_person, position, phone, email, website, buyer_type, brands,
             contact_person_2, position_2, phone_2, email_2, interest_level, next_event_date, next_event_type, mayer_reg, whatsapp_1, whatsapp_2)
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
    interest_level = request.form.get('interest_level', 'не опрацьовано')
    website = request.form.get('website', '')
    next_event_date = request.form.get('next_event_date', '')
    next_event_type = request.form.get('next_event_type', '')
    mayer_reg = request.form.get('mayer_reg', 'Ні')
    whatsapp_1 = request.form.get('whatsapp_1', '')
    whatsapp_2 = request.form.get('whatsapp_2', '')
    
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
                                  phone_2=%s, email_2=%s, interest_level=%s, next_event_date=%s, next_event_type=%s, mayer_reg=%s, whatsapp_1=%s, whatsapp_2=%s WHERE id=%s""",
            (name, country, address, contact_person, position, phone, email, website, buyer_type, brands,
             contact_person_2, position_2, phone_2, email_2, interest_level, next_event_date, next_event_type, mayer_reg, whatsapp_1, whatsapp_2, client_id)
        )
        conn.commit()
        cursor.close()
        conn.close()
    return redirect(url_for('client_detail', client_id=client_id))

@app.route('/delete_client/<int:client_id>', methods=['POST'])
@login_required
def delete_client(client_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM clients WHERE id = %s", (client_id,))
    conn.commit()
    cursor.close()
    conn.close()
    return redirect(url_for('index'))

@app.route('/add_finance_plan', methods=['POST'])
@login_required
def add_finance_plan():
    client_id = request.form.get('client_id')
    planned_amount = request.form.get('planned_amount', 0)
    month_name = request.form.get('month_name', '')
    actual_amount = request.form.get('actual_amount', 0)
    payment_date = request.form.get('payment_date', '')
    if client_id:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("INSERT INTO sales_plans (client_id, planned_amount, month_name, actual_amount, payment_date) VALUES (%s, %s, %s, %s, %s)", (client_id, planned_amount if planned_amount else 0, month_name, actual_amount if actual_amount else 0, payment_date))
        conn.commit()
        cursor.close()
        conn.close()
    return redirect(url_for('index', tab='finance', finance_month=month_name))

@app.route('/edit_finance_plan/<int:plan_id>', methods=['POST'])
@login_required
def edit_finance_plan(plan_id):
    planned_amount = request.form.get('planned_amount', 0)
    month_name = request.form.get('month_name', '')
    actual_amount = request.form.get('actual_amount', 0)
    payment_date = request.form.get('payment_date', '')
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE sales_plans SET planned_amount=%s, month_name=%s, actual_amount=%s, payment_date=%s WHERE id=%s", (planned_amount if planned_amount else 0, month_name, actual_amount if actual_amount else 0, payment_date, plan_id))
    conn.commit()
    cursor.close()
    conn.close()
    return redirect(url_for('index', tab='finance', finance_month=month_name))

@app.route('/delete_finance_plan/<int:plan_id>', methods=['POST'])
@login_required
def delete_finance_plan(plan_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM sales_plans WHERE id=%s", (plan_id,))
    conn.commit()
    cursor.close()
    conn.close()
    return redirect(url_for('index', tab='finance'))

@app.route('/client/<int:client_id>', methods=['GET', 'POST'])
@login_required
def client_detail(client_id):
    conn = get_db_connection()
    cursor = conn.cursor(cursor_factory=DictCursor)
    
    if request.method == 'POST':
        result_text = request.form.get('result')
        author = request.form.get('author', 'Продажі') 
        if result_text:
            current_date = datetime.now().strftime("%Y-%m-%d %H:%M")
            cursor.execute(
                "INSERT INTO negotiations (client_id, date, result, author) VALUES (%s, %s, %s, %s)",
                (client_id, current_date, result_text, author)
            )
            conn.commit()
        return redirect(url_for('client_detail', client_id=client_id))
        
    cursor.execute("SELECT * FROM clients WHERE id = %s", (client_id,))
    raw_client = cursor.fetchone()
    
    client = dict(raw_client) if raw_client else {}
    fields_to_check = ['buyer_type', 'brands', 'website', 'country', 'address', 
                       'contact_person', 'position', 'phone', 'email', 
                       'contact_person_2', 'position_2', 'phone_2', 'email_2', 
                       'interest_level', 'next_event_date', 'next_event_type', 'mayer_reg', 'whatsapp_1', 'whatsapp_2']
    for field in fields_to_check:
        if field not in client or client[field] is None:
            if field == 'interest_level':
                client[field] = 'не опрацьовано'
            elif field == 'mayer_reg':
                client[field] = 'Ні'
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
               c.contact_person AS "Контактна особа 1", c.position AS "Посада 1", c.phone AS "Телефон 1", c.whatsapp_1 AS "WhatsApp 1", c.email AS "Email 1",
               c.contact_person_2 AS "Контактна особа 2", c.position_2 AS "Посада 2", c.phone_2 AS "Телефон 2", c.whatsapp_2 AS "WhatsApp 2", c.email_2 AS "Email 2",
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

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
