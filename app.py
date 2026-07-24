import os
import json
import re
import psycopg2
from psycopg2.extras import DictCursor
from flask import Flask, render_template, request, redirect, url_for, session, send_file, jsonify
from datetime import datetime
import pandas as pd
import io
import smtplib
import imaplib
import email
from email.mime.text import MIMEText
from email.header import Header, decode_header

app = Flask(__name__)

app.secret_key = os.environ.get('SECRET_KEY', 'super-secret-key-change-me')

CRM_USERNAME = os.environ.get('CRM_USERNAME', 'admin')
CRM_PASSWORD = os.environ.get('CRM_PASSWORD', 'Mayer2026') 

DATABASE_URL = os.environ.get('DATABASE_URL')

# Конфігурація бізнес-пошти Хостинг Україна з Render
MAIL_SERVER = os.environ.get('MAIL_SERVER', 'mail.adm.tools')
MAIL_PORT = 465  # Безпечний SSL порт
MAIL_USERNAME = os.environ.get('MAIL_USERNAME')
MAIL_PASSWORD = os.environ.get('MAIL_PASSWORD')

def get_db_connection():
    conn = psycopg2.connect(DATABASE_URL, sslmode='require')
    return conn

# ========================================================
# ГАРАНТОВАНЕ ВИЗНАЧЕННЯ ДЕКОРАТОРА НА САМОМУ ВЕРХУ КОДУ
# ========================================================
def login_required(f):
    from functools import wraps
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('logged_in'):
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

# БЕЗПЕЧНИЙ ДЕКОДЕР ТІЛА ЛИСТА ДЛЯ IMAP РОБОТА
def decode_email_body(msg):
    body = ""
    if msg.is_multipart():
        for part in msg.walk():
            content_type = part.get_content_type()
            content_disposition = str(part.get("Content-Disposition"))
            if content_type == "text/plain" and "attachment" not in content_disposition:
                charset = part.get_content_charset() or 'utf-8'
                try:
                    payload = part.get_payload(decode=True)
                    body = payload.decode(charset, errors='ignore')
                    break
                except Exception:
                    pass
    else:
        charset = msg.get_content_charset() or 'utf-8'
        try:
            payload = msg.get_payload(decode=True)
            body = payload.decode(charset, errors='ignore')
        except Exception:
            body = "[Помилка декодування тексту листа]"
            
    return body.strip()

# ВНУТРІШНЯ ФУНКЦІЯ ВІДПРАВКИ HTML-ПОШТИ (Банер на початку листа)
def send_email_notification(to_email, subject, body_text, promo_banner=False):
    if not MAIL_USERNAME or not MAIL_PASSWORD:
        print("⚠️ Налаштування пошти відсутні в змінних оточення Render!")
        return False
    try:
        html_body = body_text
        logo_url = "https://my-crm-q24n.onrender.com/static/logotipnew.png" 
        banner_url = "https://my-crm-q24n.onrender.com/static/promo_en.jpg"

        banner_html = ""
        if promo_banner:
            banner_html = f"""
            <div style="margin-bottom: 25px;">
                <img src="{banner_url}" alt="MAYER PRO Promotion" style="max-width: 100%; height: auto; display: block; border-radius: 4px; border: 1px solid #dee2e6;">
            </div>
            """

        html_content = f"""
        <html>
        <body style="font-family: 'Aptos', Calibri, Arial, sans-serif; color: #212529; line-height: 1.5;">
            {banner_html}
            <div style="font-size: 15px; margin-bottom: 30px;">
                {html_body}
            </div>
            <hr style="border: none; border-top: 1px solid #dee2e6; margin-top: 30px; margin-bottom: 20px;">
            <table border="0" cellpadding="0" cellspacing="0" style="color: #212529;">
                <tr>
                    <td style="vertical-align: top; padding-right: 20px;">
                        <img src="{logo_url}" alt="Mayer Pro Logo" width="220" style="display: block; max-width: 100%; height: auto;">
                    </td>
                    <td style="vertical-align: top; border-left: 2px solid #dc3545; padding-left: 15px; font-size: 16px;">
                        <span style="color: #6c757d; font-style: italic;">Z poważaniem / Kindly regards</span><br><br>
                        <strong style="font-size: 18px;">Dmytro Petrychenko</strong><br>
                        <span style="color: #495057; font-weight: 500;">Regional spare parts manager</span><br>
                        <strong style="color: #dc3545;">MAYER PRO S.r.o.</strong><br>
                        📱 +421 907 933 441<br>
                        📱 +48 501 166 523<br>
                        🌐 <a href="https://mayer-pro.com/en" target="_blank" style="color: #0d6efd; text-decoration: none;">mayer-pro.com/en</a><br>
                        📧 <a href="mailto:sales@mayer-pro.com" style="color: #0d6efd; text-decoration: none;">sales@mayer-pro.com</a>
                    </td>
                </tr>
                <tr>
                    <td colspan="2" style="padding-top: 15px; font-size: 12px; color: #6c757d; border-top: 1px dashed #dee2e6; margin-top: 15px;">
                        <strong>Mayer Pro s.r.o.</strong> | Address: Jegenesska, 9, 82103 Bratislava, Slovakia<br>
                        <strong>VAT-nr:</strong> SK 2121592088
                    </td>
                </tr>
            </table>
        </body>
        </html>
        """

        msg = MIMEText(html_content, 'html', 'utf-8')
        msg['Subject'] = Header(subject, 'utf-8')
        msg['From'] = MAIL_USERNAME
        msg['To'] = to_email
        
        server = smtplib.SMTP_SSL(MAIL_SERVER, MAIL_PORT)
        server.login(MAIL_USERNAME, MAIL_PASSWORD)
        server.sendmail(MAIL_USERNAME, [to_email], msg.as_string())
        server.quit()
        return True
    except Exception as e:
        print(f"❌ Помилка SMTP відправки: {str(e)}")
        return False

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
        'website': 'TEXT', 'buyer_type': 'TEXT', 'brands': 'TEXT', 'position': 'TEXT',
        'contact_person_2': 'TEXT', 'position_2': 'TEXT', 'phone_2': 'TEXT', 'email_2': 'TEXT',
        'interest_level': 'TEXT', 'next_event_date': 'TEXT', 'next_event_type': 'TEXT', 'mayer_reg': 'TEXT',
        'whatsapp_1': 'TEXT', 'whatsapp_2': 'TEXT'
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
            author TEXT,
            FOREIGN KEY (client_id) REFERENCES clients (id) ON DELETE CASCADE
        )
    ''')

    cursor.execute("SELECT column_name FROM information_schema.columns WHERE table_name='negotiations'")
    existing_neg_columns = [row[0] for row in cursor.fetchall()]
    if 'author' not in existing_neg_columns:
        cursor.execute("ALTER TABLE negotiations ADD COLUMN author TEXT DEFAULT 'Продажі';")

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS tasks (
            id SERIAL PRIMARY KEY,
            text TEXT NOT NULL,
            deadline TEXT,
            author TEXT DEFAULT 'Продажі',
            status TEXT DEFAULT 'in_progress'
        )
    ''')

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

    # СТВОРЕННЯ ТАБЛИЦІ ДЛЯ УПУЩЕНОГО ПОПИТУ
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS lost_demand (
            id SERIAL PRIMARY KEY,
            client_id INTEGER,
            article TEXT NOT NULL,
            title TEXT,
            quantity INTEGER DEFAULT 1,
            status TEXT DEFAULT 'lost',
            note TEXT,
            created_at TEXT,
            FOREIGN KEY (client_id) REFERENCES clients (id) ON DELETE CASCADE
        )
    ''')
    
    conn.commit()
    cursor.close()
    conn.close()

if DATABASE_URL:
    init_db()

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
    
    # ЗЧИТУВАННЯ СТАТИСТИКИ УПУЩЕНОГО ПОПИТУ
    dict_cursor.execute("""
        SELECT ld.*, c.name as client_name 
        FROM lost_demand ld 
        LEFT JOIN clients c ON ld.client_id = c.id 
        ORDER BY ld.id DESC
    """)
    raw_demand = dict_cursor.fetchall()
    lost_demand_list = [dict(d) for d in raw_demand]

    # ТОП ДЕФІЦИТНИХ АРТИКУЛІВ (Групування за артикулом)
    dict_cursor.execute("""
        SELECT article, title, COUNT(*) as request_count, SUM(quantity) as total_qty
        FROM lost_demand
        GROUP BY article, title
        ORDER BY request_count DESC, total_qty DESC
        LIMIT 10
    """)
    top_demand_raw = dict_cursor.fetchall()
    top_demand = [dict(t) for t in top_demand_raw]

    dict_cursor.execute("SELECT id, name FROM clients ORDER BY name ASC")
    all_selector_clients = dict_cursor.fetchall()

    dict_cursor.execute("SELECT id, text, deadline, author, status FROM tasks ORDER BY id DESC")
    tasks_raw = dict_cursor.fetchall()
    tasks = [dict(t) for t in tasks_raw]

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
        json_tasks=json.dumps(tasks, ensure_ascii=False),
        lost_demand_list=lost_demand_list,
        top_demand=top_demand
    )

# МАРШРУТ ДОДАВАННЯ УПУЩЕНОГО ПОПИТУ
@app.route('/add_lost_demand', methods=['POST'])
@login_required
def add_lost_demand():
    client_id = request.form.get('client_id')
    article = request.form.get('article', '').strip()
    title = request.form.get('title', '').strip()
    quantity = request.form.get('quantity', 1)
    status = request.form.get('status', 'lost')
    note = request.form.get('note', '').strip()
    created_at = datetime.now().strftime("%Y-%m-%d %H:%M")
    
    if article:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO lost_demand (client_id, article, title, quantity, status, note, created_at) VALUES (%s, %s, %s, %s, %s, %s, %s)",
            (client_id if client_id else None, article, title, quantity, status, note, created_at)
        )
        conn.commit()
        cursor.close()
        conn.close()
        
    if client_id:
        return redirect(url_for('client_detail', client_id=client_id))
    return redirect(url_for('index', tab='demand'))

# МАРШРУТ ВИДАЛЕННЯ НОТАТКИ ДЕФІЦИТУ
@app.route('/delete_lost_demand/<int:demand_id>', methods=['POST'])
@login_required
def delete_lost_demand(demand_id):
    client_id = request.form.get('client_id')
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM lost_demand WHERE id = %s", (demand_id,))
    conn.commit()
    cursor.close()
    conn.close()
    
    if client_id:
        return redirect(url_for('client_detail', client_id=client_id))
    return redirect(url_for('index', tab='demand'))

@app.route('/send_client_email', methods=['POST'])
@login_required
def send_client_email():
    client_id = request.form.get('client_id')
    to_email = request.form.get('email', '').strip()
    subject = request.form.get('subject', '').strip()
    body_text = request.form.get('body', '').strip()
    promo_banner = request.form.get('promo_banner') == 'on'
    
    if to_email and body_text:
        success = send_email_notification(to_email, subject, body_text, promo_banner=promo_banner)
        if success:
            current_date = datetime.now().strftime("%Y-%m-%d %H:%M")
            conn = get_db_connection()
            cursor = conn.cursor()
            
            banner_log = " (+ Англійський промо-банер)" if promo_banner else ""
            log_text = f"Надіслано фірмовий HTML-Email{banner_log}. Тема: \"{subject}\""
            
            cursor.execute(
                "INSERT INTO negotiations (client_id, date, result, author) VALUES (%s, %s, %s, %s)",
                (client_id, current_date, log_text, 'Продажі')
            )
            conn.commit()
            cursor.close()
            conn.close()
    return redirect(url_for('client_detail', client_id=client_id))

@app.route('/sync_emails', methods=['POST'])
@login_required
def sync_emails():
    if not MAIL_USERNAME or not MAIL_PASSWORD:
        return jsonify({'success': False, 'message': 'Налаштування IMAP відсутні на Render!'})
    try:
        mail = imaplib.IMAP4_SSL('mail.adm.tools', 993)
        mail.login(MAIL_USERNAME, MAIL_PASSWORD)
        mail.select("INBOX")
        
        status, response_data = mail.search(None, 'UNSEEN')
        email_ids = response_data[0].split()
        
        if not email_ids:
            mail.close()
            mail.logout()
            return jsonify({'success': True, 'message': 'Вхідна скринька перевірена. Нових листів від дилерів немає.'})

        conn = get_db_connection()
        cursor = conn.cursor()
        imported_count = 0

        for e_id in email_ids:
            _, msg_data = mail.fetch(e_id, '(RFC822)')
            raw_email = msg_data[0][1]
            msg = email.message_from_bytes(raw_email)
            
            from_header = msg.get("From", "")
            from_email = email.utils.parseaddr(from_header)[1].lower().strip()
            
            subject_header = msg.get("Subject", "")
            subject_decoded = ""
            for part, encoding in decode_header(subject_header):
                if isinstance(part, bytes):
                    subject_decoded += part.decode(encoding or 'utf-8', errors='ignore')
                else:
                    subject_decoded += str(part)
            
            cursor.execute(
                "SELECT id FROM clients WHERE LOWER(email) = %s OR LOWER(email_2) = %s",
                (from_email, from_email)
            )
            client_row = cursor.fetchone()
            
            if client_row:
                client_id = client_row[0]
                email_body = decode_email_body(msg)
                
                final_history_text = f"[📩 Вхідний лист] Тема: \"{subject_decoded.strip()}\"\n\n{email_body}"
                current_date = datetime.now().strftime("%Y-%m-%d %H:%M")
                
                cursor.execute(
                    "INSERT INTO negotiations (client_id, date, result, author) VALUES (%s, %s, %s, %s)",
                    (client_id, current_date, final_history_text, 'Продажі')
                )
                mail.store(e_id, '+FLAGS', '\\Seen')
                imported_count += 1
        
        conn.commit()
        cursor.close()
        conn.close()
        mail.close()
        mail.logout()
        
        return jsonify({'success': True, 'message': f'Синхронізація завершена! Успішно імпортовано відповідей: {imported_count}'})
    except Exception as e:
        return jsonify({'success': False, 'message': f'Помилка IMAP: {str(e)}'})

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
        contact_type = request.form.get('contact_type', 'call')
        
        type_tags = {
            'call': '[📞 Дзвінок] ',
            'visit': '[🚗 Візит] ',
            'email': '[✉️ Лист] '
        }
        prefix = type_tags.get(contact_type, '')
        
        if result_text:
            final_text = f"{prefix}{result_text}"
            current_date = datetime.now().strftime("%Y-%m-%d %H:%M")
            cursor.execute(
                "INSERT INTO negotiations (client_id, date, result, author) VALUES (%s, %s, %s, %s)",
                (client_id, current_date, final_text, author)
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

    # Отримання упущеного попиту по конкретному клієнту
    cursor.execute("SELECT * FROM lost_demand WHERE client_id = %s ORDER BY id DESC", (client_id,))
    client_lost_demand = cursor.fetchall()
    
    cursor.close()
    conn.close()
    return render_template('client.html', client=client, history=history, client_lost_demand=client_lost_demand)

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
    try:
        cursor.execute("DELETE FROM negotiations WHERE id = %s", (neg_id,))
        conn.commit()
    except Exception as e:
        print(f"❌ Помилка видалення активності з бази: {str(e)}")
        conn.rollback()
    finally:
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
