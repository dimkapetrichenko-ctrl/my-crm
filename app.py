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
            deal_stage TEXT,
            history TEXT,
            planned_revenue NUMERIC(15,2) DEFAULT 0,
            actual_revenue NUMERIC(15,2) DEFAULT 0
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS tasks (
            id SERIAL PRIMARY KEY,
            text TEXT NOT NULL,
            author TEXT NOT NULL,
            due_date TEXT NOT NULL,
            status TEXT DEFAULT 'pending',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    conn.commit()
    cursor.close()
    conn.close()

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
            error = 'Невірне ім\'я користувача або пароль'
    return render_template('login.html', error=error)

@app.route('/logout')
def logout():
    session.pop('logged_in', None)
    return redirect(url_for('login'))

@app.route('/')
@login_required
def index():
    search_query = request.args.get('search', '').strip()
    country_filter = request.args.get('country', '').strip()
    brand_filter = request.args.get('brand', '').strip()
    stage_filter = request.args.get('stage', '').strip()
    
    conn = get_db_connection()
    cursor = conn.cursor(cursor_factory=DictCursor)
    
    cursor.execute("SELECT DISTINCT country FROM clients WHERE country IS NOT EXISTS OR country != '' ORDER BY country ASC")
    countries = [r['country'] for r in cursor.fetchall() if r['country']]
    
    base_query = "SELECT * FROM clients WHERE 1=1"
    params = []
    
    if search_query:
        base_query += " AND (name ILIKE %s OR contact_person ILIKE %s OR email ILIKE %s OR phone ILIKE %s)"
        q = f"%{search_query}%"
        params.extend([q, q, q, q])
        
    if country_filter:
        base_query += " AND country = %s"
        params.append(country_filter)
        
    if brand_filter:
        base_query += " AND brands ILIKE %s"
        params.append(f"%{brand_filter}%")
        
    if stage_filter:
        base_query += " AND deal_stage = %s"
        params.append(stage_filter)
        
    base_query += " ORDER BY name ASC"
    
    cursor.execute(base_query, params)
    clients = cursor.fetchall()
    
    cursor.execute("SELECT SUM(planned_revenue) AS total_planned, SUM(actual_revenue) AS total_actual FROM clients")
    totals = cursor.fetchone()
    total_planned = totals['total_planned'] or 0
    total_actual = totals['total_actual'] or 0
    
    cursor.execute("SELECT * FROM clients WHERE next_event_date IS NOT NULL AND next_event_date != ''")
    calendar_clients = [dict(r) for r in cursor.fetchall()]
    
    cursor.execute("SELECT * FROM tasks WHERE status = 'pending' ORDER BY due_date ASC, id ASC")
    pending_tasks = [dict(r) for r in cursor.fetchall()]
    
    cursor.close()
    conn.close()
    
    return render_template('index.html', 
                           clients=clients, 
                           countries=countries,
                           selected_country=country_filter,
                           selected_brand=brand_filter,
                           selected_stage=stage_filter,
                           search_query=search_query,
                           total_planned=total_planned,
                           total_actual=total_actual,
                           calendar_clients_json=json.dumps(calendar_clients),
                           pending_tasks=pending_tasks)

@app.route('/api/tasks_calendar')
@login_required
def api_tasks_calendar():
    conn = get_db_connection()
    cursor = conn.cursor(cursor_factory=DictCursor)
    cursor.execute("SELECT id, text, author, due_date, status FROM tasks WHERE status = 'pending'")
    tasks = [dict(r) for r in cursor.fetchall()]
    cursor.close()
    conn.close()
    return jsonify(tasks)

@app.route('/add_client', methods=['POST'])
@login_required
def add_client():
    name = request.form.get('name')
    country = request.form.get('country')
    address = request.form.get('address')
    contact_person = request.form.get('contact_person')
    position = request.form.get('position')
    phone = request.form.get('phone')
    email = request.form.get('email')
    website = request.form.get('website')
    buyer_type = request.form.get('buyer_type')
    brands = request.form.get('brands')
    contact_person_2 = request.form.get('contact_person_2')
    position_2 = request.form.get('position_2')
    phone_2 = request.form.get('phone_2')
    email_2 = request.form.get('email_2')
    interest_level = request.form.get('interest_level')
    next_event_date = request.form.get('next_event_date')
    next_event_type = request.form.get('next_event_type')
    deal_stage = request.form.get('deal_stage', 'Початковий контакт')
    
    try:
        planned_revenue = float(request.form.get('planned_revenue', 0) or 0)
        actual_revenue = float(request.form.get('actual_revenue', 0) or 0)
    except ValueError:
        planned_revenue = 0
        actual_revenue = 0
        
    history_entry = f"[{datetime.now().strftime('%d.%m.%Y %H:%M')}] Картку створено. Етап: {deal_stage}."
    history_json = json.dumps([history_entry], ensure_ascii=False)
    
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO clients (name, country, address, contact_person, position, phone, email, website, 
                             buyer_type, brands, contact_person_2, position_2, phone_2, email_2, 
                             interest_level, next_event_date, next_event_type, deal_stage, history,
                             planned_revenue, actual_revenue)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
    ''', (name, country, address, contact_person, position, phone, email, website,
          buyer_type, brands, contact_person_2, position_2, phone_2, email_2,
          interest_level, next_event_date, next_event_type, deal_stage, history_json,
          planned_revenue, actual_revenue))
    
    conn.commit()
    cursor.close()
    conn.close()
    return redirect(url_for('index'))

@app.route('/client/<int:client_id>')
@login_required
def client_detail(client_id):
    conn = get_db_connection()
    cursor = conn.cursor(cursor_factory=DictCursor)
    cursor.execute("SELECT * FROM clients WHERE id = %s", (client_id,))
    client = cursor.fetchone()
    cursor.close()
    conn.close()
    
    if not client:
        return "Клієнта не знайдено", 404
        
    try:
        history_list = json.loads(client['history'] or '[]')
    except:
        history_list = [client['history']] if client['history'] else []
        
    return render_template('detail.html', client=client, history=history_list)

@app.route('/edit_client/<int:client_id>', methods=['POST'])
@login_required
def edit_client(client_id):
    conn = get_db_connection()
    cursor = conn.cursor(cursor_factory=DictCursor)
    cursor.execute("SELECT * FROM clients WHERE id = %s", (client_id,))
    old_client = cursor.fetchone()
    
    if not old_client:
        cursor.close()
        conn.close()
        return "Клієнта не знайдено", 404
        
    name = request.form.get('name')
    country = request.form.get('country')
    address = request.form.get('address')
    contact_person = request.form.get('contact_person')
    position = request.form.get('position')
    phone = request.form.get('phone')
    email = request.form.get('email')
    website = request.form.get('website')
    buyer_type = request.form.get('buyer_type')
    brands = request.form.get('brands')
    contact_person_2 = request.form.get('contact_person_2')
    position_2 = request.form.get('position_2')
    phone_2 = request.form.get('phone_2')
    email_2 = request.form.get('email_2')
    interest_level = request.form.get('interest_level')
    next_event_date = request.form.get('next_event_date')
    next_event_type = request.form.get('next_event_type')
    deal_stage = request.form.get('deal_stage')
    
    try:
        planned_revenue = float(request.form.get('planned_revenue', 0) or 0)
        actual_revenue = float(request.form.get('actual_revenue', 0) or 0)
    except ValueError:
        planned_revenue = 0
        actual_revenue = 0

    changes = []
    if old_client['deal_stage'] != deal_stage:
        changes.append(f"Етап: {old_client['deal_stage']} ➡️ {deal_stage}")
    if float(old_client['planned_revenue'] or 0) != planned_revenue:
        changes.append(f"План: {old_client['planned_revenue']} ➡️ {planned_revenue} EUR")
    if float(old_client['actual_revenue'] or 0) != actual_revenue:
        changes.append(f"Факт: {old_client['actual_revenue']} ➡️ {actual_revenue} EUR")
    if old_client['next_event_date'] != next_event_date or old_client['next_event_type'] != next_event_type:
        changes.append(f"Подія: {next_event_date} ({next_event_type})")
        
    try:
        history_list = json.loads(old_client['history'] or '[]')
    except:
        history_list = [old_client['history']] if old_client['history'] else []
        
    if changes:
        entry = f"[{datetime.now().strftime('%d.%m.%Y %H:%M')}] Зміни: " + ", ".join(changes)
        history_list.append(entry)
        
    history_json = json.dumps(history_list, ensure_ascii=False)
    
    cursor.execute('''
        UPDATE clients
        SET name=%s, country=%s, address=%s, contact_person=%s, position=%s, phone=%s, email=%s, website=%s,
            buyer_type=%s, brands=%s, contact_person_2=%s, position_2=%s, phone_2=%s, email_2=%s,
            interest_level=%s, next_event_date=%s, next_event_type=%s, deal_stage=%s, history=%s,
            planned_revenue=%s, actual_revenue=%s
        WHERE id=%s
    ''', (name, country, address, contact_person, position, phone, email, website,
          buyer_type, brands, contact_person_2, position_2, phone_2, email_2,
          interest_level, next_event_date, next_event_type, deal_stage, history_json,
          planned_revenue, actual_revenue, client_id))
    
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

@app.route('/add_comment/<int:client_id>', methods=['POST'])
@login_required
def add_comment(client_id):
    comment_text = request.form.get('comment', '').strip()
    if not comment_text:
        return redirect(url_for('client_detail', client_id=client_id))
        
    conn = get_db_connection()
    cursor = conn.cursor(cursor_factory=DictCursor)
    cursor.execute("SELECT history FROM clients WHERE id = %s", (client_id,))
    client = cursor.fetchone()
    
    try:
        history_list = json.loads(client['history'] or '[]')
    except:
        history_list = [client['history']] if client['history'] else []
        
    entry = f"[{datetime.now().strftime('%d.%m.%Y %H:%M')}] Коментар: {comment_text}"
    history_list.append(entry)
    history_json = json.dumps(history_list, ensure_ascii=False)
    
    cursor.execute("UPDATE clients SET history = %s WHERE id = %s", (history_json, client_id))
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
        df.to_excel(writer, index=False, sheet_name='Clients')
    output.seek(0)
    
    return send_file(output, download_name="Mayer_Pro_CRM_Export.xlsx", as_attachment=True)

@app.route('/add_task', methods=['POST'])
@login_required
def add_task():
    text = request.form.get('text')
    author = request.form.get('author')
    due_date = request.form.get('due_date')
    
    if text and author and due_date:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("INSERT INTO tasks (text, author, due_date) VALUES (%s, %s, %s)", (text, author, due_date))
        conn.commit()
        cursor.close()
        conn.close()
    return redirect(url_for('index'))

@app.route('/complete_task/<int:task_id>', methods=['POST'])
@login_required
def complete_task(task_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE tasks SET status = 'completed' WHERE id = %s", (task_id,))
    conn.commit()
    cursor.close()
    conn.close()
    return redirect(url_for('index'))

@app.route('/delete_task/<int:task_id>', methods=['POST'])
@login_required
def delete_task(task_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM tasks WHERE id = %s", (task_id,))
    conn.commit()
    cursor.close()
    conn.close()
    return redirect(url_for('index'))

if __name__ == '__main__':
    app.run(debug=True)
