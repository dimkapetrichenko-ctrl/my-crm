import os
import re
import json
import psycopg2
from psycopg2.extras import DictCursor
from flask import Flask, render_template, request, redirect, url_for, session, send_file, jsonify
from datetime import datetime, timedelta
import pandas as pd
import io
import smtplib
import imaplib
import email
from email.mime.text import MIMEText
from email.header import Header, decode_header
import requests
from bs4 import BeautifulSoup
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

app = Flask(__name__)

app.secret_key = os.environ.get('SECRET_KEY', 'super-secret-key-change-me')

CRM_USERNAME = os.environ.get('CRM_USERNAME', 'admin')
CRM_PASSWORD = os.environ.get('CRM_PASSWORD', 'Mayer2026') 

DATABASE_URL = os.environ.get('DATABASE_URL')
GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY')

MAIL_SERVER = os.environ.get('MAIL_SERVER', 'mail.adm.tools')
MAIL_PORT = 465
MAIL_USERNAME = os.environ.get('MAIL_USERNAME')
MAIL_PASSWORD = os.environ.get('MAIL_PASSWORD')

def get_db_connection():
    conn = psycopg2.connect(DATABASE_URL, sslmode='require')
    return conn

def login_required(f):
    from functools import wraps
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('logged_in'):
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

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

def make_links_clickable(text):
    """Автоматично перетворює посилання у тексті на активні клікабельні HTML-теги <a>"""
    url_pattern = re.compile(r'(https?://[^\s<]+|www\.[^\s<]+)')
    
    def replace_url(match):
        url = match.group(0)
        trailing = ""
        while url and url[-1] in '.,!?;:)':
            trailing = url[-1] + trailing
            url = url[:-1]
            
        href = url if url.startswith('http') else 'http://' + url
        return f'<a href="{href}" target="_blank" style="color: #0d6efd; text-decoration: underline; font-weight: 500;">{url}</a>{trailing}'
    
    return url_pattern.sub(replace_url, text)

def format_text_to_html(raw_text):
    """Розбиває текст на чіткі абзаци та перетворює посилання на активні"""
    raw_text = raw_text.strip().replace("\r\n", "\n").replace("\r", "\n")
    text_with_links = make_links_clickable(raw_text)
    
    paragraphs = text_with_links.split("\n\n")
    html_paragraphs = []
    for p in paragraphs:
        if p.strip():
            p_formatted = p.strip().replace("\n", "<br>")
            html_paragraphs.append(f'<p style="margin: 0 0 16px 0; line-height: 1.6;">{p_formatted}</p>')
            
    return "".join(html_paragraphs)

def send_email_notification(to_email, subject, body_text, promo_banner=False):
    if not MAIL_USERNAME or not MAIL_PASSWORD:
        print("⚠️ Налаштування пошти відсутні в змінних оточення Render!")
        return False
    try:
        html_body = format_text_to_html(body_text)

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
        <body style="font-family: 'Aptos', Calibri, Arial, sans-serif; color: #212529; font-size: 15px;">
            {banner_html}
            <div style="margin-bottom: 30px;">
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
            whatsapp_2 TEXT,
            is_active BOOLEAN DEFAULT TRUE,
            deactivation_reason TEXT,
            deal_stage TEXT DEFAULT 'none',
            aftermarket_companies TEXT
        )
    ''')
    
    cursor.execute("SELECT column_name FROM information_schema.columns WHERE table_name='clients'")
    existing_columns = [row[0] for row in cursor.fetchall()]
    
    new_fields = {
        'website': 'TEXT', 'buyer_type': 'TEXT', 'brands': 'TEXT', 'position': 'TEXT',
        'contact_person_2': 'TEXT', 'position_2': 'TEXT', 'phone_2': 'TEXT', 'email_2': 'TEXT',
        'interest_level': 'TEXT', 'next_event_date': 'TEXT', 'next_event_type': 'TEXT', 'mayer_reg': 'TEXT',
        'whatsapp_1': 'TEXT', 'whatsapp_2': 'TEXT', 'is_active': 'BOOLEAN DEFAULT TRUE', 'deactivation_reason': 'TEXT',
        'deal_stage': "TEXT DEFAULT 'none'",
        'aftermarket_companies': 'TEXT'
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

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS notes (
            id SERIAL PRIMARY KEY,
            title TEXT,
            content TEXT NOT NULL,
            tag TEXT DEFAULT 'Нотатка',
            ink_color TEXT DEFAULT '#1e3a8a',
            created_at TEXT
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
    status_view = request.args.get('status_view', 'active').strip()
    
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
    stats_cursor.execute("SELECT COUNT(*) FROM clients WHERE is_active IS NOT FALSE")
    total_clients = stats_cursor.fetchone()[0]
    
    stats_cursor.execute("SELECT interest_level, COUNT(*) FROM clients WHERE is_active IS NOT FALSE GROUP BY interest_level")
    raw_interest = stats_cursor.fetchall()
    
    interest_stats = {'не опрацьовано': 0, 'немає зацікавленості': 0, 'середня зацікавленість': 0, 'зацікавленість': 0}
    for row in raw_interest:
        status = row[0] if row[0] else 'не опрацьовано'
        if status in interest_stats:
            interest_stats[status] = row[1]
            
    stats_cursor.execute("SELECT country, COUNT(*) FROM clients WHERE country IS NOT NULL AND country != '' AND is_active IS NOT FALSE GROUP BY country ORDER BY COUNT(*) DESC")
    country_stats = stats_cursor.fetchall()

    stats_cursor.execute("SELECT buyer_type, COUNT(*) FROM clients WHERE buyer_type IS NOT NULL AND buyer_type != 'не вказано' AND buyer_type != '' AND is_active IS NOT FALSE GROUP BY buyer_type ORDER BY COUNT(*) DESC")
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
    
    dict_cursor.execute("""
        SELECT ld.*, c.name as client_name 
        FROM lost_demand ld 
        LEFT JOIN clients c ON ld.client_id = c.id 
        ORDER BY ld.id DESC
    """)
    raw_demand = dict_cursor.fetchall()
    lost_demand_list = [dict(d) for d in raw_demand]

    dict_cursor.execute("""
        SELECT article, title, COUNT(*) as request_count, SUM(quantity) as total_qty
        FROM lost_demand
        GROUP BY article, title
        ORDER BY request_count DESC, total_qty DESC
        LIMIT 10
    """)
    top_demand_raw = dict_cursor.fetchall()
    top_demand = [dict(t) for t in top_demand_raw]

    dict_cursor.execute("SELECT * FROM notes ORDER BY id DESC")
    notes_raw = dict_cursor.fetchall()
    notes_list = [dict(n) for n in notes_raw]

    dict_cursor.execute("SELECT id, name FROM clients WHERE is_active IS NOT FALSE ORDER BY name ASC")
    all_selector_clients = dict_cursor.fetchall()

    dict_cursor.execute("SELECT id, text, deadline, author, status FROM tasks ORDER BY id DESC")
    tasks_raw = dict_cursor.fetchall()
    tasks = [dict(t) for t in tasks_raw]

    cal_cursor = conn.cursor(cursor_factory=DictCursor)
    cal_cursor.execute("SELECT id, name, country, contact_person, phone, next_event_date, next_event_type FROM clients WHERE next_event_date IS NOT NULL AND next_event_date != '' AND is_active IS NOT FALSE")
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
               (SELECT MAX(n.date)::TEXT FROM negotiations n WHERE n.client_id = c.id) AS last_activity,
               (SELECT n.result FROM negotiations n WHERE n.client_id = c.id ORDER BY n.id DESC LIMIT 1) AS last_activity_text
        FROM clients c 
        WHERE 1=1
    """
    params = []
    
    if status_view == 'active':
        sql += " AND c.is_active IS NOT FALSE"
    elif status_view == 'archived':
        sql += " AND c.is_active IS FALSE"

    if search_query:
        sql += " AND (LOWER(c.name) LIKE LOWER(%s) OR LOWER(c.contact_person) LIKE LOWER(%s) OR LOWER(c.brands) LIKE LOWER(%s) OR LOWER(c.country) LIKE LOWER(%s) OR LOWER(c.buyer_type) LIKE LOWER(%s) OR LOWER(c.aftermarket_companies) LIKE LOWER(%s))"
        params.extend([f"%{search_query}%", f"%{search_query}%", f"%{search_query}%", f"%{search_query}%", f"%{search_query}%", f"%{search_query}%"])
        
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
            'aftermarket_companies': row['aftermarket_companies'] if row['aftermarket_companies'] else '',
            'interest_level': row['interest_level'] if row['interest_level'] else 'не опрацьовано',
            'deal_stage': row['deal_stage'] if row['deal_stage'] else 'none',
            'last_activity': row['last_activity'] if row['last_activity'] else '',
            'last_activity_text': row['last_activity_text'] if row['last_activity_text'] else '',
            'next_event_date': str(row['next_event_date']) if row['next_event_date'] else '',
            'next_event_type': str(row['next_event_type']) if row['next_event_type'] else '',
            'mayer_reg': row['mayer_reg'] if row['mayer_reg'] else 'Ні',
            'is_active': row['is_active'] if row['is_active'] is not None else True,
            'deactivation_reason': row['deactivation_reason'] if row['deactivation_reason'] else ''
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
        status_view=status_view,
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
        top_demand=top_demand,
        notes_list=notes_list
    )

@app.route('/import_clients_excel', methods=['POST'])
@login_required
def import_clients_excel():
    file = request.files.get('excel_file')
    default_country = request.form.get('default_country', 'Чехія').strip() or 'Чехія'
    default_buyer_type = request.form.get('default_buyer_type', 'Дилер сг техніки').strip()

    if not file or file.filename == '':
        return redirect(url_for('index'))

    try:
        df = pd.read_excel(file, header=None)

        first_row_str = " ".join(df.iloc[0].astype(str).tolist()).lower()
        if 'назва' in first_row_str or 'компания' in first_row_str or 'name' in first_row_str or '№' in first_row_str:
            df = df.iloc[1:]

        conn = get_db_connection()
        cursor = conn.cursor()
        current_date = datetime.now().strftime("%Y-%m-%d %H:%M")

        for _, row in df.iterrows():
            vals = [str(x).strip() if pd.notna(x) else '' for x in row.tolist()]
            if not vals or not any(vals):
                continue

            # Формат таблиці:
            # 0: №, 1: Назва, 2: Бренди, 3: Сайт, 4: Контактна особа, 5: Email, 6: Телефон, 7: Коментар
            if len(vals) >= 7 and vals[0].isdigit():
                name = vals[1]
                brands = vals[2]
                website = vals[3]
                contact_person = vals[4]
                email_val = vals[5]
                phone = vals[6]
                if phone and not phone.startswith('+'):
                    phone = '+' + phone
                comment = vals[7] if len(vals) > 7 else ''
            else:
                name = vals[0]
                brands = vals[1] if len(vals) > 1 else ''
                website = vals[2] if len(vals) > 2 else ''
                contact_person = vals[3] if len(vals) > 3 else ''
                email_val = vals[4] if len(vals) > 4 else ''
                phone = vals[5] if len(vals) > 5 else ''
                if phone and not phone.startswith('+'):
                    phone = '+' + phone
                comment = vals[6] if len(vals) > 6 else ''

            if not name or name.lower() in ['назва', 'компанія', 'nan']:
                continue

            cursor.execute("SELECT id FROM clients WHERE LOWER(name) = LOWER(%s)", (name,))
            existing = cursor.fetchone()

            if not existing:
                cursor.execute("""
                    INSERT INTO clients (
                        name, country, website, buyer_type, brands, 
                        contact_person, phone, email, interest_level, 
                        deal_stage, mayer_reg, is_active
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, 'none', 'Ні', TRUE)
                    RETURNING id
                """, (
                    name, default_country, website, default_buyer_type, 
                    brands, contact_person, phone, email_val, 'не опрацьовано'
                ))
                new_client_id = cursor.fetchone()[0]

                if comment:
                    note_text = f"📋 [ІМПОРТ З БАЗИ]: {comment}"
                    cursor.execute("""
                        INSERT INTO negotiations (client_id, date, result, author)
                        VALUES (%s, %s, %s, %s)
                    """, (new_client_id, current_date, note_text, 'CEO'))

        conn.commit()
        cursor.close()
        conn.close()

    except Exception as e:
        print(f"❌ Помилка імпорту клієнтів: {e}")

    return redirect(url_for('index'))

@app.route('/add_note', methods=['POST'])
@login_required
def add_note():
    title = request.form.get('title', '').strip()
    content = request.form.get('content', '').strip()
    tag = request.form.get('tag', 'Нотатка').strip()
    ink_color = request.form.get('ink_color', '#1e3a8a').strip()
    
    if content:
        conn = get_db_connection()
        cursor = conn.cursor()
        created_at = datetime.now().strftime("%Y-%m-%d %H:%M")
        cursor.execute(
            "INSERT INTO notes (title, content, tag, ink_color, created_at) VALUES (%s, %s, %s, %s, %s)",
            (title if title else 'Без назви', content, tag, ink_color, created_at)
        )
        conn.commit()
        cursor.close()
        conn.close()
    return redirect(url_for('index', tab='notepad'))

@app.route('/edit_note/<int:note_id>', methods=['POST'])
@login_required
def edit_note(note_id):
    title = request.form.get('title', '').strip()
    content = request.form.get('content', '').strip()
    tag = request.form.get('tag', 'Нотатка').strip()
    ink_color = request.form.get('ink_color', '#1e3a8a').strip()
    
    if content:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE notes SET title = %s, content = %s, tag = %s, ink_color = %s WHERE id = %s",
            (title if title else 'Без назви', content, tag, ink_color, note_id)
        )
        conn.commit()
        cursor.close()
        conn.close()
    return redirect(url_for('index', tab='notepad'))

@app.route('/delete_note/<int:note_id>', methods=['POST'])
@login_required
def delete_note(note_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM notes WHERE id = %s", (note_id,))
    conn.commit()
    cursor.close()
    conn.close()
    return redirect(url_for('index', tab='notepad'))

@app.route('/toggle_client_status/<int:client_id>', methods=['POST'])
@login_required
def toggle_client_status(client_id):
    action = request.form.get('action')
    reason = request.form.get('reason', '').strip()
    
    conn = get_db_connection()
    cursor = conn.cursor()
    current_date = datetime.now().strftime("%Y-%m-%d %H:%M")
    
    if action == 'deactivate':
        cursor.execute("UPDATE clients SET is_active = FALSE, deactivation_reason = %s WHERE id = %s", (reason, client_id))
        log_text = f"⛔ [ДЕАКТИВАЦІЯ ЛІДА] Клієнта переведено в архів. Причина: {reason or 'Не вказано'}"
        cursor.execute("INSERT INTO negotiations (client_id, date, result, author) VALUES (%s, %s, %s, %s)", (client_id, current_date, log_text, 'CEO'))
    else:
        cursor.execute("UPDATE clients SET is_active = TRUE, deactivation_reason = NULL WHERE id = %s", (client_id,))
        log_text = "🟢 [АКТИВАЦІЯ ЛІДА] Клієнта відновлено з архіву в активну базу."
        cursor.execute("INSERT INTO negotiations (client_id, date, result, author) VALUES (%s, %s, %s, %s)", (client_id, current_date, log_text, 'CEO'))
        
    conn.commit()
    cursor.close()
    conn.close()
    return redirect(url_for('client_detail', client_id=client_id))

@app.route('/add_quick_sale/<int:client_id>', methods=['POST'])
@login_required
def add_quick_sale(client_id):
    amount = request.form.get('amount', 0)
    invoice_no = request.form.get('invoice_no', '').strip()
    payment_date = request.form.get('payment_date', '').strip()
    month_name = request.form.get('month_name', '').strip()
    next_action_days = int(request.form.get('next_action_days', 7))
    
    if not payment_date:
        payment_date = datetime.now().strftime("%Y-%m-%d")
        
    ukr_months = ["Січень", "Лютий", "Березень", "Квітень", "Травень", "Червень", "Липень", "Серпень", "Вересень", "Жовтень", "Листопад", "Грудень"]
    if not month_name:
        month_idx = datetime.now().month - 1
        month_name = ukr_months[month_idx]
        
    try:
        amt_val = float(amount)
    except Exception:
        amt_val = 0.0
        
    if amt_val > 0:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute(
            "SELECT id, actual_amount, planned_amount FROM sales_plans WHERE client_id = %s ORDER BY id DESC LIMIT 1",
            (client_id,)
        )
        existing_plan = cursor.fetchone()
        
        if existing_plan:
            plan_id = existing_plan[0]
            current_actual = float(existing_plan[1] or 0)
            new_actual = current_actual + amt_val
            cursor.execute(
                "UPDATE sales_plans SET actual_amount = %s, payment_date = %s WHERE id = %s",
                (new_actual, payment_date, plan_id)
            )
        else:
            cursor.execute(
                "INSERT INTO sales_plans (client_id, planned_amount, month_name, actual_amount, payment_date) VALUES (%s, %s, %s, %s, %s)",
                (client_id, 0.0, month_name, amt_val, payment_date)
            )
        
        try:
            p_date_obj = datetime.strptime(payment_date, "%Y-%m-%d")
            next_date = (p_date_obj + timedelta(days=next_action_days)).strftime("%Y-%m-%d")
        except Exception:
            next_date = (datetime.now() + timedelta(days=next_action_days)).strftime("%Y-%m-%d")
            
        cursor.execute(
            "UPDATE clients SET deal_stage = 'paid_shipped', next_event_date = %s, next_event_type = 'call' WHERE id = %s",
            (next_date, client_id)
        )
        
        inv_text = f" Рахунок/ТТН: {invoice_no}." if invoice_no else ""
        current_dt = datetime.now().strftime("%Y-%m-%d %H:%M")
        log_text = f"💰 [ОПЛАТА] Надійшло {amt_val:,.2f} EUR.{inv_text} Автоматично призначено контроль отримання товару на {next_date}."
        
        cursor.execute(
            "INSERT INTO negotiations (client_id, date, result, author) VALUES (%s, %s, %s, %s)",
            (client_id, current_dt, log_text, 'Продажі')
        )
        
        conn.commit()
        cursor.close()
        conn.close()
        
    return redirect(url_for('client_detail', client_id=client_id))

@app.route('/detect_brands_ai/<int:client_id>', methods=['POST'])
@login_required
def detect_brands_ai(client_id):
    if not GEMINI_API_KEY:
        return jsonify({'success': False, 'message': 'Змінна GEMINI_API_KEY не налаштована в Render!'})
        
    conn = get_db_connection()
    cursor = conn.cursor(cursor_factory=DictCursor)
    cursor.execute("SELECT id, name, website, brands, aftermarket_companies FROM clients WHERE id = %s", (client_id,))
    client = cursor.fetchone()
    
    if not client or not client['website']:
        cursor.close()
        conn.close()
        return jsonify({'success': False, 'message': 'У клієнта відсутній веб-сайт для аналізу!'})
        
    client_name = client['name']
    site_url = client['website'].strip()
    if not site_url.startswith('http'):
        site_url = "http://" + site_url

    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36'
    }
    extracted_text = ""
    
    try:
        page_res = requests.get(site_url, headers=headers, timeout=8, verify=False)
        if page_res.status_code == 200:
            soup = BeautifulSoup(page_res.text, 'html.parser')
            
            alts = [img.get('alt', '') for img in soup.find_all('img') if img.get('alt')]
            titles = [a.get('title', '') for a in soup.find_all('a') if a.get('title')]
            meta_brand_text = " ".join(alts + titles)

            for element in soup(["script", "style", "svg", "noscript"]):
                element.extract()
                
            raw_page_text = soup.get_text(separator=' ', strip=True)
            extracted_text = f"{meta_brand_text} {raw_page_text}"[:40000]
    except Exception as e:
        print(f"Помилка завантаження HTML {site_url}: {e}")

    prompt = f"""
    Проаналізуй наведений нижче контент сайту/магазину запчастин '{client_name}' ({site_url}):

    --- КОНТЕНТ САЙТУ ТА КАТАЛОГУ ---
    {extracted_text if extracted_text else "Текст сайту недоступний, використовуй точні знання про асортимент компанії " + client_name}
    --- КІНЕЦЬ КОНТЕНТУ ---

    Завдання 1: Визнач наявність запчастин або техніки до наступних брендів (враховуй різні форми написання та популярні агрегати):
    - Vaderstad (враховуй: Vaderstad, Väderstad, Rapid, Carrier, TopDown, Tempo)
    - Gaspardo (враховуй: Gaspardo, Maschio Gaspardo)
    - Horsch (враховуй: Horsch, Pronto, Joker, Terrano, Tiger, Maestro)
    - Kverneland (враховуй: Kverneland, Accord, Rau, Qualidisc, Exacta)
    - Pottinger (враховуй: Pottinger, Pöttinger, Terradisc, Synkro, Lion, Aerosem)

    Завдання 2: Визнач співпрацю з відомими aftermarket операторами / виробниками замінників:
    - Granit Parts (враховуй: Granit, Granit Parts, Granit-Parts)
    - Kramp
    - Industriehof (враховуй: Industriehof Scherenbostel)
    - Bepco
    - Bellota
    - Frank Walz (враховуй: Frank Walz, Frank Original)
    - Molbro
    - Waryński (враховуй: Waryński, Warynski)
    - Premium Parts

    Вимоги до результату:
    Поверни ВИКЛЮЧНО JSON-об'єкт строго у такому форматі:
    {{
        "brands": ["Vaderstad", "Gaspardo", "Kverneland"],
        "aftermarket": ["Granit Parts", "Kramp", "Waryński"]
    }}
    Дозволені значення для brands: "Vaderstad", "Gaspardo", "Horsch", "Kverneland", "Pottinger".
    Дозволені значення для aftermarket: "Granit Parts", "Kramp", "Industriehof", "Bepco", "Bellota", "Frank Walz", "Molbro", "Waryński", "Premium Parts".
    Без markdown (без ```), без лапок на початку/кінці і без жодних додаткових пояснень.
    """
    
    try:
        host = "generativelanguage.googleapis.com"
        model_path = "v1beta/models/gemini-3.6-flash:generateContent"
        url = "https://" + host + "/" + model_path + "?key=" + str(GEMINI_API_KEY).strip()
        
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"temperature":
