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

def send_raw_html_email(to_email, subject, html_content):
    if not MAIL_USERNAME or not MAIL_PASSWORD:
        return False
    try:
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
        print(f"❌ Помилка відправки HTML шаблону: {str(e)}")
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
        json_clients=json.dumps(clients_js_data, ensure_ascii=False),
        json_busy_dates=json.dumps(busy_dates, ensure_ascii=False),
        today_date=today_str,
        tasks=tasks,
        json_tasks=json.dumps(tasks, ensure_ascii=False),
        lost_demand_list=lost_demand_list,
        top_demand=top_demand,
        notes_list=notes_list
    )

@app.route('/send_client_email', methods=['POST'])
@login_required
def send_client_email():
    client_id = request.form.get('client_id')
    to_email = request.form.get('email', '').strip()
    subject = request.form.get('subject', '').strip()
    body_text = request.form.get('body', '').strip()
    template_type = request.form.get('template_type', 'standard').strip()
    promo_banner = request.form.get('promo_banner') == 'on'
    
    if to_email:
        success = False
        
        if template_type == 'price_inquiry':
            html_content = '''<!DOCTYPE html>
<html lang="en">
<head><meta charset="UTF-8"><style>
  body { margin: 0; padding: 0; background-color: #F4F5F7; font-family: Arial, Helvetica, sans-serif; }
  table { border-spacing: 0; border-collapse: collapse; }
  td { padding: 0; }
  .button { background-color: #E31E24; color: #FFFFFF !important; text-decoration: none; padding: 13px 26px; font-size: 15px; font-weight: bold; border-radius: 4px; display: inline-block; }
</style></head>
<body style="margin: 0; padding: 20px 0; background-color: #F4F5F7;">
  <center>
    <table width="600" cellpadding="0" cellspacing="0" style="width: 600px; max-width: 600px; background-color: #FFFFFF; border-radius: 8px; overflow: hidden; box-shadow: 0 2px 8px rgba(0,0,0,0.06);">
      <tr>
        <td style="padding: 18px 32px; border-bottom: 2px solid #F0F2F5; text-align: left; background-color: #FFFFFF;">
          <a href="https://mayer-pro.com" target="_blank"><img src="https://mayer-pro.com/image/catalog/logo/logo2.png" alt="MAYER-PRO" width="160" style="display: block; width: 160px; height: auto; border: 0;"></a>
        </td>
      </tr>
      <tr>
        <td style="padding: 32px 32px 24px 32px; color: #1F2428; line-height: 1.6;">
          <h1 style="margin: 0 0 16px 0; font-size: 20px; font-weight: bold; color: #111827;">Hello,</h1>
          <p style="margin: 0 0 16px 0; font-size: 15px; color: #4B5563;">Thank you for reaching out and for your interest in our products.</p>
          <p style="margin: 0 0 20px 0; font-size: 15px; color: #4B5563;"><strong>MAYER-PRO</strong> is a direct manufacturer of high-wear tillage and seeding spare parts under our own brand. We manufacture parts fully compatible with <strong>Väderstad, Horsch, Kverneland, and Maschio Gaspardo</strong> machinery. All orders are fulfilled directly from our European warehouse in Slovakia.</p>
          <div style="background-color: #F9FAFB; border-left: 4px solid #E31E24; padding: 14px 18px; margin-bottom: 16px; border-radius: 0 4px 4px 0;">
            <p style="margin: 0 0 8px 0; font-size: 14px; font-weight: bold; color: #111827;">1. For which machinery would you like to receive our MAYER-PRO compatible parts price list?</p>
            <p style="margin: 0; font-size: 14px; color: #4B5563; line-height: 1.8;">◻️ Parts compatible with Väderstad<br>◻️ Parts compatible with Horsch<br>◻️ Parts compatible with Kverneland<br>◻️ Parts compatible with Maschio Gaspardo</p>
          </div>
          <div style="background-color: #F9FAFB; border-left: 4px solid #E31E24; padding: 14px 18px; margin-bottom: 16px; border-radius: 0 4px 4px 0;">
            <p style="margin: 0 0 8px 0; font-size: 14px; font-weight: bold; color: #111827;">2. Target purchase volume:</p>
            <p style="margin: 0 0 6px 0; font-size: 13px; color: #E31E24; font-weight: 600;">* Minimum initial order: 600 €</p>
          </div>
          <table cellpadding="0" cellspacing="0" style="margin: 10px 0;">
            <tr><td align="center" style="border-radius: 4px;" bgcolor="#E31E24">
              <a href="mailto:sales@mayer-pro.com?subject=MAYER-PRO%20Partner%20Inquiry" target="_blank" class="button">Reply to this Email &rarr;</a>
            </td></tr>
          </table>
        </td>
      </tr>
      <tr>
        <td style="padding: 24px 32px; background-color: #FAFAFB; border-top: 1px solid #ECEFF2; font-size: 14px; color: #6B7280; line-height: 1.5;">
          <p style="margin: 0 0 4px 0; font-weight: bold; color: #111827; font-size: 15px;">Dmytro Petrychenko</p>
          <p style="margin: 0 0 12px 0; color: #E31E24; font-weight: 600;">Business Development & Sales Manager | MAYER-PRO</p>
          <p style="margin: 0; font-size: 13px;">💬 WhatsApp: <a href="https://wa.me/421907933441" style="color: #4B5563;">+421 907 933 441</a><br>✉️ Email: sales@mayer-pro.com</p>
        </td>
      </tr>
    </table>
  </center>
</body>
</html>'''
            success = send_raw_html_email(to_email, subject or "MAYER-PRO | Pricing & Partnership Inquiry", html_content)

        elif template_type == 'catalog_download':
            html_content = '''<!DOCTYPE html>
<html lang="en">
<head><meta charset="UTF-8"><style>
  body { margin: 0; padding: 0; background-color: #F4F5F7; font-family: Arial, Helvetica, sans-serif; }
  table { border-spacing: 0; border-collapse: collapse; }
  td { padding: 0; }
  .button { background-color: #E31E24; color: #FFFFFF !important; text-decoration: none; padding: 14px 28px; font-size: 15px; font-weight: bold; border-radius: 4px; display: inline-block; }
</style></head>
<body style="margin: 0; padding: 20px 0; background-color: #F4F5F7;">
  <center>
    <table width="600" cellpadding="0" cellspacing="0" style="width: 600px; max-width: 600px; background-color: #FFFFFF; border-radius: 8px; overflow: hidden; box-shadow: 0 2px 8px rgba(0,0,0,0.06);">
      <tr>
        <td style="padding: 18px 32px; border-bottom: 2px solid #F0F2F5; text-align: left; background-color: #FFFFFF;">
          <a href="https://mayer-pro.com" target="_blank"><img src="https://mayer-pro.com/image/catalog/logo/logo2.png" alt="MAYER-PRO" width="170" style="display: block; width: 170px; height: auto; border: 0;"></a>
        </td>
      </tr>
      <tr>
        <td><img src="https://mayer-pro.com/image/catalog/banner/1-en.jpg" alt="MAYER-PRO" width="600" style="width: 100%; max-width: 600px; height: auto; display: block; border: 0;"></td>
      </tr>
      <tr>
        <td style="padding: 36px 32px 28px 32px; color: #1F2428; line-height: 1.6;">
          <h1 style="margin: 0 0 16px 0; font-size: 22px; font-weight: bold; color: #111827;">Hello,</h1>
          <p style="margin: 0 0 16px 0; font-size: 15px; color: #4B5563;">Thank you for downloading the <strong>MAYER-PRO</strong> catalogue!</p>
          <p style="margin: 0 0 16px 0; font-size: 15px; color: #4B5563;">We manufacture and supply high-quality agricultural spare parts compatible with <strong>Väderstad, Horsch, Kverneland, and Maschio Gaspardo</strong>, with stock located in Slovakia.</p>
          <div style="background-color: #F9FAFB; border-left: 4px solid #E31E24; padding: 14px 16px; margin: 20px 0; border-radius: 0 4px 4px 0;">
            <p style="margin: 0; font-size: 14px; color: #1F2428; font-weight: 600;">Would you like to receive partner pricing for the parts relevant to your business?</p>
          </div>
          <table cellpadding="0" cellspacing="0" style="margin: 28px 0 12px 0;">
            <tr><td align="center" style="border-radius: 4px;" bgcolor="#E31E24">
              <a href="mailto:sales@mayer-pro.com?subject=Request%20for%20Partner%20Pricing%20MAYER-PRO" target="_blank" class="button">Request Partner Pricing &rarr;</a>
            </td></tr>
          </table>
        </td>
      </tr>
      <tr>
        <td style="padding: 24px 32px; background-color: #FAFAFB; border-top: 1px solid #ECEFF2; font-size: 14px; color: #6B7280; line-height: 1.5;">
          <p style="margin: 0 0 4px 0; font-weight: bold; color: #111827; font-size: 15px;">Dmytro Petrychenko</p>
          <p style="margin: 0 0 12px 0; color: #E31E24; font-weight: 600;">Business Development & Sales Manager | MAYER-PRO</p>
          <p style="margin: 0; font-size: 13px;">💬 WhatsApp: <a href="https://wa.me/421907933441" style="color: #4B5563;">+421 907 933 441</a><br>✉️ Email: sales@mayer-pro.com</p>
        </td>
      </tr>
    </table>
  </center>
</body>
</html>'''
            success = send_raw_html_email(to_email, subject or "MAYER-PRO Partner Pricing", html_content)

        else:
            success = send_email_notification(to_email, subject, body_text, promo_banner=promo_banner)

        if success:
            current_date = datetime.now().strftime("%Y-%m-%d %H:%M")
            conn = get_db_connection()
            cursor = conn.cursor()
            log_text = f"Надіслано шаблон листа: [{template_type}]. Тема: \"{subject}\""
            cursor.execute(
                "INSERT INTO negotiations (client_id, date, result, author) VALUES (%s, %s, %s, %s)",
                (client_id, current_date, log_text, 'Продажі')
            )
            conn.commit()
            cursor.close()
            conn.close()
            
    return redirect(url_for('client_detail', client_id=client_id))

# решта маршрутів app.py без змін...
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
            'unanswered': '[📵 Недодзвон] ',
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
                       'interest_level', 'next_event_date', 'next_event_type', 'mayer_reg', 'whatsapp_1', 'whatsapp_2',
                       'is_active', 'deactivation_reason', 'deal_stage', 'aftermarket_companies']
    for field in fields_to_check:
        if field not in client or client[field] is None:
            if field == 'interest_level': client[field] = 'не опрацьовано'
            elif field == 'deal_stage': client[field] = 'none'
            elif field == 'mayer_reg': client[field] = 'Ні'
            elif field == 'is_active': client[field] = True
            else: client[field] = ''
    
    cursor.execute("SELECT COUNT(*), COALESCE(SUM(actual_amount), 0) FROM sales_plans WHERE client_id = %s AND actual_amount > 0", (client_id,))
    deal_stats_row = cursor.fetchone()
    deal_count = deal_stats_row[0] if deal_stats_row else 0
    deal_total_sum = float(deal_stats_row[1]) if deal_stats_row else 0.0

    cursor.execute("SELECT * FROM negotiations WHERE client_id = %s ORDER BY id DESC", (client_id,))
    history = cursor.fetchall()

    cursor.execute("SELECT * FROM lost_demand WHERE client_id = %s ORDER BY id DESC", (client_id,))
    client_lost_demand = cursor.fetchall()

    cursor.execute("""
        SELECT next_event_date, COUNT(*) 
        FROM clients 
        WHERE next_event_date IS NOT NULL AND next_event_date != '' AND is_active IS NOT FALSE
        GROUP BY next_event_date
    """)
    events_by_date = dict(cursor.fetchall())
    json_events_by_date = json.dumps(events_by_date, ensure_ascii=False)

    cursor.close()
    conn.close()
    return render_template(
        'client.html', 
        client=client, 
        history=history, 
        client_lost_demand=client_lost_demand, 
        json_events_by_date=json_events_by_date,
        deal_count=deal_count,
        deal_total_sum=deal_total_sum
    )

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
