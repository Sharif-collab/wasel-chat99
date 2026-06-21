# -*- coding: utf-8 -*-
"""
واصل شات - المرحلة 35 - إصلاح حفظ تفاعلات الحالات نهائياً
تشغيل في Termux:
    pip install flask werkzeug
    python wasel_chat_STAGE35_STATUS_REACTION_DB_FIXED.py
ثم افتح:
    http://127.0.0.1:5000
"""

import os
import sqlite3
import random
import html
import re
import time
import secrets
import smtplib
from email.mime.text import MIMEText
from email.header import Header
escape = html.escape
from datetime import datetime, date, timedelta
from functools import wraps
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from flask import Flask, request, redirect, url_for, session, g, send_from_directory, jsonify, abort

APP_NAME = "واصل شات"
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "wasel_chat_new.db")
UPLOAD_DIR = os.path.join(BASE_DIR, "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)

app = Flask(__name__)

def load_secret_key():
    env_key = os.environ.get("WASEL_SECRET_KEY")
    if env_key and len(env_key) >= 32:
        return env_key
    key_file = os.path.join(BASE_DIR, ".wasel_secret_key")
    if os.path.exists(key_file):
        try:
            return open(key_file, "r", encoding="utf-8").read().strip()
        except Exception:
            pass
    key = secrets.token_hex(32)
    try:
        with open(key_file, "w", encoding="utf-8") as f:
            f.write(key)
    except Exception:
        pass
    return key

app.secret_key = load_secret_key()
app.config["UPLOAD_FOLDER"] = UPLOAD_DIR
app.config["MAX_CONTENT_LENGTH"] = 80 * 1024 * 1024
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
app.config["SESSION_COOKIE_SECURE"] = bool(os.environ.get("WASEL_HTTPS"))

LOGIN_ATTEMPTS = {}

EMAIL_HOST = os.environ.get("EMAIL_HOST", "smtp.gmail.com")
EMAIL_PORT = int(os.environ.get("EMAIL_PORT", "587") or 587)
EMAIL_USER = os.environ.get("EMAIL_USER", "")
EMAIL_PASS = os.environ.get("EMAIL_PASS", "")
EMAIL_FROM = os.environ.get("EMAIL_FROM", APP_NAME)

ALLOWED_EXT = {"png", "jpg", "jpeg", "gif", "webp", "mp4", "webm", "mp3", "wav", "ogg", "pdf", "doc", "docx", "txt", "zip"}


COUNTRIES = [
    {"flag":"🇾🇪","name":"اليمن","en":"Yemen","code":"+967","local_re":r"7\d{8}","min":9,"max":9},
    {"flag":"🇸🇦","name":"السعودية","en":"Saudi Arabia","code":"+966","local_re":r"5\d{8}","min":9,"max":9},
    {"flag":"🇦🇪","name":"الإمارات","en":"United Arab Emirates","code":"+971","local_re":r"5\d{8}","min":9,"max":9},
    {"flag":"🇴🇲","name":"عمان","en":"Oman","code":"+968","local_re":r"[279]\d{7}","min":8,"max":8},
    {"flag":"🇶🇦","name":"قطر","en":"Qatar","code":"+974","local_re":r"[3567]\d{7}","min":8,"max":8},
    {"flag":"🇰🇼","name":"الكويت","en":"Kuwait","code":"+965","local_re":r"[569]\d{7}","min":8,"max":8},
    {"flag":"🇧🇭","name":"البحرين","en":"Bahrain","code":"+973","local_re":r"[36]\d{7}","min":8,"max":8},
    {"flag":"🇪🇬","name":"مصر","en":"Egypt","code":"+20","local_re":r"1\d{9}","min":10,"max":10},
    {"flag":"🇯🇴","name":"الأردن","en":"Jordan","code":"+962","local_re":r"7\d{8}","min":9,"max":9},
    {"flag":"🇮🇶","name":"العراق","en":"Iraq","code":"+964","local_re":r"7\d{9}","min":10,"max":10},
    {"flag":"🇵🇸","name":"فلسطين","en":"Palestine","code":"+970","local_re":r"5\d{8}","min":9,"max":9},
    {"flag":"🇸🇾","name":"سوريا","en":"Syria","code":"+963","local_re":r"9\d{8}","min":9,"max":9},
    {"flag":"🇱🇧","name":"لبنان","en":"Lebanon","code":"+961","local_re":r"[37]\d{7}|8\d{6}","min":7,"max":8},
    {"flag":"🇸🇩","name":"السودان","en":"Sudan","code":"+249","local_re":r"9\d{8}","min":9,"max":9},
    {"flag":"🇹🇷","name":"تركيا","en":"Turkey","code":"+90","local_re":r"5\d{9}","min":10,"max":10},
    {"flag":"🇮🇳","name":"الهند","en":"India","code":"+91","local_re":r"[6-9]\d{9}","min":10,"max":10},
    {"flag":"🇵🇰","name":"باكستان","en":"Pakistan","code":"+92","local_re":r"3\d{9}","min":10,"max":10},
    {"flag":"🇺🇸","name":"أمريكا","en":"United States","code":"+1","local_re":r"[2-9]\d{9}","min":10,"max":10},
    {"flag":"🇬🇧","name":"بريطانيا","en":"United Kingdom","code":"+44","local_re":r"7\d{9}","min":10,"max":10},
]
COUNTRY_BY_CODE = {c['code']: c for c in COUNTRIES}


def clean_digits(value):
    return re.sub(r"\D+", "", value or "")


def parse_country_value(value, fallback_code='+967'):
    raw = (value or '').strip()
    for c in COUNTRIES:
        if c['code'] in raw or c['name'] in raw or c['en'].lower() in raw.lower() or clean_digits(c['code']) == clean_digits(raw):
            return c
    return COUNTRY_BY_CODE.get(fallback_code, COUNTRIES[0])


def country_display(country):
    c = country if isinstance(country, dict) else parse_country_value(country)
    return f"{c['flag']} {c['name']} {c['code']}"


def country_datalist_html():
    opts = ''.join([f"<option value='{h(country_display(c))}'>{h(c['en'])}</option>" for c in COUNTRIES])
    return f"<datalist id='country_list'>{opts}</datalist>"


def country_picker_html(field_name='country_picker', selected='+967', picker_id='countryPicker'):
    current = parse_country_value(selected)
    rows = []
    for c in COUNTRIES:
        label = country_display(c)
        search = (c['name'] + ' ' + c['en'] + ' ' + c['code'] + ' ' + clean_digits(c['code'])).lower()
        rows.append(
            f"<button type='button' class='countryRow' data-target='{h(field_name)}' data-label='{h(label)}' data-search='{h(search)}' onclick=\"selectCountry(this)\">"
            f"<span class='countryFlag'>{h(c['flag'])}</span><span class='countryName'>{h(c['name'])}<small>{h(c['en'])}</small></span><b>{h(c['code'])}</b></button>"
        )
    return f"""
    <input type='hidden' name='{h(field_name)}' id='{h(field_name)}' value='{h(country_display(current))}'>
    <button type='button' class='countrySelect' onclick="openCountryPicker('{h(picker_id)}','{h(field_name)}')">
        <span id='{h(field_name)}_label'>{h(country_display(current))}</span><b>›</b>
    </button>
    <div class='countryModal' id='{h(picker_id)}'>
        <div class='countrySheet'>
            <div class='countryHead'><button type='button' class='icon' onclick="closeCountryPicker('{h(picker_id)}')">×</button><b>اختيار الدولة</b></div>
            <div class='countrySearch'><input type='search' oninput="filterCountries('{h(picker_id)}', this.value)" placeholder='بحث باسم الدولة أو رمزها'></div>
            <div class='countryList'>{''.join(rows)}</div>
        </div>
    </div>
    """


def normalize_phone_by_country(phone, country_value='+967'):
    c = parse_country_value(country_value)
    digits = clean_digits(phone)
    code_digits = clean_digits(c['code'])
    if digits.startswith('00' + code_digits):
        return None, None, c, 'اكتب الرقم بدون رمز الدولة'
    if digits.startswith(code_digits) and len(digits) > c.get('max', 15):
        return None, None, c, 'اكتب الرقم بدون رمز الدولة'
    if not digits:
        return None, None, c, 'أدخل رقم الهاتف'
    if not re.fullmatch(c['local_re'], digits):
        return None, None, c, 'رقم الهاتف غير صحيح حسب الدولة المختارة'
    full = c['code'] + digits
    return digits, full, c, ''


def h(value):
    return escape(str(value or ""), quote=True)


def normalize_yemeni_phone(phone):
    local, full, c, err = normalize_phone_by_country(phone, '+967')
    return local if local and c['code'] == '+967' else None


def phone_lookup_values(raw):
    """يعيد قيم محتملة للبحث: رقم محلي، رقم كامل، بريد أو اسم مستخدم."""
    value = (raw or '').strip().lower()
    if not value:
        return []
    vals = {value}
    digits = clean_digits(value)
    if digits:
        vals.add(digits)
        for c in COUNTRIES:
            code = clean_digits(c['code'])
            if digits.startswith(code):
                local = digits[len(code):]
                vals.add(local)
                vals.add(c['code'] + local)
            else:
                vals.add(c['code'] + digits)
    return [v for v in vals if v]


def csrf_token():
    token = session.get("_csrf_token")
    if not token:
        token = secrets.token_urlsafe(32)
        session["_csrf_token"] = token
    return token


def inject_csrf(html_text):
    token = csrf_token()
    hidden = f"<input type='hidden' name='_csrf_token' value='{token}'>"
    return re.sub(r"(<form\b[^>]*method=['\"]post['\"][^>]*>)", r"\1" + hidden, html_text, flags=re.I)


@app.before_request
def security_before_request():
    if request.method == "POST":
        if request.path.startswith('/call_signal'):
            return None
        # طلبات AJAX الخاصة بتفاعلات الحالة/ردود الحالة تعمل من الهاتف بدون كسر بسبب CSRF أو كاش المتصفح
        if re.fullmatch(r'/status/\d+/react', request.path) or re.fullmatch(r'/status/\d+/reply_msg/\d+/(react|edit|delete)', request.path):
            return None
        sent = request.form.get("_csrf_token") or request.headers.get("X-CSRFToken")
        expected = session.get("_csrf_token")
        if not expected or sent != expected:
            abort(400)
    return None


@app.after_request
def security_headers(resp):
    resp.headers.setdefault("X-Content-Type-Options", "nosniff")
    resp.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
    resp.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    resp.headers.setdefault("Permissions-Policy", "camera=(self), microphone=(self), geolocation=()")
    return resp


@app.errorhandler(400)
def bad_request_error(e):
    return page("<div class='top'><a class='icon' href='/chats'>‹</a><b>طلب غير صحيح</b></div><div class='card'>انتهت صلاحية الصفحة أو الطلب غير آمن. ارجع وافتح الصفحة من جديد.</div>"), 400


@app.errorhandler(413)
def file_too_large(e):
    return page("<div class='top'><a class='icon' href='/chats'>‹</a><b>الملف كبير</b></div><div class='card'>حجم الملف أكبر من المسموح. اختر ملفًا أصغر.</div>"), 413


@app.errorhandler(500)
def internal_error(e):
    return page("<div class='top'><a class='icon' href='/chats'>‹</a><b>حدث خطأ</b></div><div class='card'>حدث خطأ داخلي. أعد تشغيل الصفحة، وإذا تكرر الخطأ أرسل آخر سطر من Termux.</div>"), 500


def db():
    if "db" not in g:
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row
    return g.db


@app.teardown_appcontext
def close_db(_=None):
    con = g.pop("db", None)
    if con:
        con.close()


def init_db():
    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()
    cur.executescript("""
    CREATE TABLE IF NOT EXISTS users(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        username TEXT UNIQUE,
        email TEXT UNIQUE,
        phone TEXT UNIQUE,
        password_hash TEXT NOT NULL,
        avatar TEXT,
        about TEXT DEFAULT 'مرحباً، أستخدم واصل',
        online INTEGER DEFAULT 0,
        created_at TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS contacts(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        contact_id INTEGER NOT NULL,
        pinned INTEGER DEFAULT 0,
        archived INTEGER DEFAULT 0,
        muted INTEGER DEFAULT 0,
        blocked INTEGER DEFAULT 0,
        note TEXT,
        created_at TEXT NOT NULL,
        UNIQUE(user_id, contact_id)
    );
    CREATE TABLE IF NOT EXISTS address_book(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        saved_name TEXT NOT NULL,
        identifier TEXT NOT NULL,
        identifier_type TEXT DEFAULT 'unknown',
        country TEXT,
        linked_user_id INTEGER,
        created_at TEXT NOT NULL,
        updated_at TEXT,
        UNIQUE(user_id, identifier)
    );
    CREATE TABLE IF NOT EXISTS messages(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        sender_id INTEGER NOT NULL,
        receiver_id INTEGER NOT NULL,
        body TEXT,
        file_name TEXT,
        file_type TEXT,
        reply_to INTEGER,
        starred INTEGER DEFAULT 0,
        deleted_for_sender INTEGER DEFAULT 0,
        deleted_for_receiver INTEGER DEFAULT 0,
        deleted_for_all INTEGER DEFAULT 0,
        reaction TEXT,
        is_read INTEGER DEFAULT 0,
        read_at TEXT,
        edited_at TEXT,
        created_at TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS statuses(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        text TEXT,
        file_name TEXT,
        created_at TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS status_views(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        status_id INTEGER NOT NULL,
        viewer_id INTEGER NOT NULL,
        viewed_at TEXT NOT NULL,
        UNIQUE(status_id, viewer_id)
    );
    CREATE TABLE IF NOT EXISTS status_reactions(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        status_id INTEGER NOT NULL,
        user_id INTEGER NOT NULL,
        owner_id INTEGER NOT NULL,
        emoji TEXT NOT NULL,
        reacted_at TEXT NOT NULL,
        UNIQUE(status_id, user_id)
    );
    CREATE TABLE IF NOT EXISTS status_replies(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        status_id INTEGER NOT NULL,
        sender_id INTEGER NOT NULL,
        owner_id INTEGER NOT NULL,
        body TEXT NOT NULL,
        created_at TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS calls(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        caller_id INTEGER NOT NULL,
        receiver_id INTEGER NOT NULL,
        call_type TEXT NOT NULL,
        status TEXT DEFAULT 'منتهية',
        created_at TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS call_signals(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        call_id INTEGER NOT NULL,
        user_id INTEGER NOT NULL,
        data TEXT NOT NULL,
        created_at TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS notifications(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        actor_id INTEGER,
        text TEXT NOT NULL,
        link TEXT,
        is_read INTEGER DEFAULT 0,
        created_at TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS reset_codes(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ident TEXT NOT NULL,
        code TEXT NOT NULL,
        expires_at TEXT NOT NULL,
        used INTEGER DEFAULT 0,
        created_at TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS email_verify_codes(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        email TEXT NOT NULL,
        code TEXT NOT NULL,
        expires_at TEXT NOT NULL,
        used INTEGER DEFAULT 0,
        created_at TEXT NOT NULL
    );
    """)

    # ترقية قواعد البيانات القديمة بدون حذف أي بيانات
    def add_col(table, col, definition):
        try:
            cols = [r[1] for r in cur.execute(f"PRAGMA table_info({table})").fetchall()]
            if col not in cols:
                cur.execute(f"ALTER TABLE {table} ADD COLUMN {col} {definition}")
        except Exception:
            pass
    add_col('messages', 'is_read', 'INTEGER DEFAULT 0')
    add_col('messages', 'read_at', 'TEXT')
    add_col('messages', 'edited_at', 'TEXT')
    add_col('messages', 'pinned', 'INTEGER DEFAULT 0')
    add_col('messages', 'reminder_at', 'TEXT')
    add_col('contacts', 'nickname', 'TEXT')
    add_col('contacts', 'last_opened_at', 'TEXT')
    add_col('contacts', 'disappearing_timer', 'INTEGER DEFAULT 0')
    add_col('users', 'gender', 'TEXT')
    add_col('users', 'birth_date', 'TEXT')
    add_col('users', 'country', 'TEXT')
    add_col('users', 'phone_country_code', 'TEXT')
    add_col('users', 'phone_full', 'TEXT')
    add_col('users', 'is_verified', 'INTEGER DEFAULT 0')
    add_col('users', 'email_verified_at', 'TEXT')
    add_col('users', 'privacy_last_seen', "TEXT DEFAULT 'everyone'")
    add_col('users', 'privacy_avatar', "TEXT DEFAULT 'everyone'")
    add_col('statuses', 'privacy', "TEXT DEFAULT 'public'")
    add_col('statuses', 'expires_at', 'TEXT')
    add_col('statuses', 'bg', "TEXT DEFAULT 'blue'")
    add_col('statuses', 'last_viewed_at', 'TEXT')
    add_col('statuses', 'views_count_cache', 'INTEGER DEFAULT 0')
    add_col('status_reactions', 'owner_id', 'INTEGER')
    add_col('status_reactions', 'emoji', 'TEXT')
    add_col('status_reactions', 'reacted_at', 'TEXT')
    add_col('status_reactions', 'user_id', 'INTEGER')
    add_col('status_reactions', 'status_id', 'INTEGER')
    try:
        cur.execute("DELETE FROM status_reactions WHERE id NOT IN (SELECT MAX(id) FROM status_reactions GROUP BY status_id,user_id)")
        cur.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_status_reactions_unique ON status_reactions(status_id,user_id)")
    except Exception:
        pass

    add_col('status_replies', 'parent_id', 'INTEGER')
    add_col('status_replies', 'to_user_id', 'INTEGER')
    add_col('status_replies', 'is_owner_reply', 'INTEGER DEFAULT 0')
    add_col('status_replies', 'reaction', 'TEXT')
    add_col('status_replies', 'edited_at', 'TEXT')
    add_col('calls', 'accepted_at', 'TEXT')
    add_col('calls', 'ended_at', 'TEXT')
    add_col('calls', 'duration_seconds', 'INTEGER DEFAULT 0')
    add_col('calls', 'declined_by', 'INTEGER')
    add_col('messages', 'reminder_done', 'INTEGER DEFAULT 0')
    add_col('notifications', 'type', "TEXT DEFAULT 'general'")
    add_col('notifications', 'priority', "TEXT DEFAULT 'normal'")
    add_col('users', 'notify_messages', 'INTEGER DEFAULT 1')
    add_col('users', 'notify_statuses', 'INTEGER DEFAULT 1')
    add_col('users', 'notify_calls', 'INTEGER DEFAULT 1')
    add_col('users', 'theme_mode', "TEXT DEFAULT 'dark'")
    add_col('users', 'font_size', "TEXT DEFAULT 'normal'")
    add_col('users', 'accent_color', "TEXT DEFAULT 'blue'")
    add_col('users', 'media_autodownload', 'INTEGER DEFAULT 1')
    add_col('users', 'save_media_gallery', 'INTEGER DEFAULT 0')
    add_col('users', 'read_receipts', 'INTEGER DEFAULT 1')
    add_col('users', 'service_chat_enabled', 'INTEGER DEFAULT 1')
    add_col('users', 'service_status_enabled', 'INTEGER DEFAULT 1')
    add_col('users', 'service_calls_enabled', 'INTEGER DEFAULT 1')
    add_col('users', 'cover_photo', 'TEXT')
    add_col('users', 'location', 'TEXT')
    add_col('users', 'website', 'TEXT')
    add_col('users', 'profile_visibility', "TEXT DEFAULT 'everyone'")
    add_col('users', 'last_login_at', 'TEXT')
    add_col('users', 'last_logout_at', 'TEXT')
    add_col('address_book', 'identifier_type', "TEXT DEFAULT 'unknown'")
    add_col('address_book', 'linked_user_id', 'INTEGER')
    add_col('address_book', 'updated_at', 'TEXT')
    add_col('address_book', 'country_code', 'TEXT')
    add_col('address_book', 'phone_full', 'TEXT')
    con.commit()
    con.close()


def now():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def h(value):
    return html.escape(str(value or ""), quote=True)


def make_code():
    return str(random.randint(100000, 999999))

def age_from_birth(birth):
    try:
        y, m, d = [int(x) for x in birth.split('-')]
        born = date(y, m, d)
        today = date.today()
        return today.year - born.year - ((today.month, today.day) < (born.month, born.day))
    except Exception:
        return None

def notify(user_id, actor_id, text, link=None, typ='general', priority='normal'):
    try:
        user_id = int(user_id)
        u = db().execute('SELECT notify_messages,notify_statuses,notify_calls FROM users WHERE id=?', (user_id,)).fetchone()
        if u:
            if typ == 'message' and not u['notify_messages']:
                return
            if typ == 'status' and not u['notify_statuses']:
                return
            if typ == 'call' and not u['notify_calls']:
                return
        db().execute("INSERT INTO notifications(user_id,actor_id,text,link,type,priority,created_at) VALUES(?,?,?,?,?,?,?)", (user_id, actor_id, text, link, typ, priority, now()))
        db().commit()
    except Exception:
        pass


def smtp_ready():
    return bool(EMAIL_HOST and EMAIL_PORT and EMAIL_USER and EMAIL_PASS)


def send_mail(to_email, subject, body):
    if not smtp_ready():
        return False, "SMTP غير مضبوط"
    try:
        msg = MIMEText(body, "plain", "utf-8")
        msg["Subject"] = Header(subject, "utf-8")
        msg["From"] = str(Header(EMAIL_FROM, "utf-8")) + f" <{EMAIL_USER}>"
        msg["To"] = to_email
        with smtplib.SMTP(EMAIL_HOST, EMAIL_PORT, timeout=20) as server:
            server.starttls()
            server.login(EMAIL_USER, EMAIL_PASS)
            server.sendmail(EMAIL_USER, [to_email], msg.as_string())
        return True, "تم الإرسال"
    except Exception as e:
        print("EMAIL_SEND_ERROR:", e)
        return False, str(e)


def create_email_verify_code(user_id, email):
    code = make_code()
    exp = (datetime.now() + timedelta(minutes=10)).strftime('%Y-%m-%d %H:%M:%S')
    db().execute("UPDATE email_verify_codes SET used=1 WHERE user_id=? AND used=0", (user_id,))
    db().execute("INSERT INTO email_verify_codes(user_id,email,code,expires_at,created_at) VALUES(?,?,?,?,?)", (user_id, email, code, exp, now()))
    db().commit()
    body = f"""مرحباً بك في واصل شات

رمز التحقق من البريد هو: {code}

الرمز صالح لمدة 10 دقائق.
إذا لم تطلب إنشاء حساب في واصل شات فتجاهل هذه الرسالة.
"""
    ok, info = send_mail(email, "رمز تحقق واصل شات", body)
    return code, ok, info


def verify_pending_user_id():
    return session.get('pending_verify_user_id')

def process_due_reminders(user_id):
    try:
        rows = db().execute("""SELECT id,body,file_name FROM messages
                             WHERE (sender_id=? OR receiver_id=?)
                               AND reminder_at IS NOT NULL AND reminder_at!=''
                               AND COALESCE(reminder_done,0)=0
                               AND reminder_at<=?
                             ORDER BY reminder_at LIMIT 20""", (user_id, user_id, now())).fetchall()
        for r in rows:
            text = '⏰ تذكير برسالة: ' + ((r['body'] or 'ملف مرفق')[:70])
            notify(user_id, user_id, text, '/message/' + str(r['id']) + '/info', 'reminder', 'high')
            db().execute('UPDATE messages SET reminder_done=1 WHERE id=?', (r['id'],))
        if rows:
            db().commit()
    except Exception:
        pass

def unread_notifications_count(user_id):
    try:
        process_due_reminders(user_id)
        return db().execute('SELECT COUNT(*) c FROM notifications WHERE user_id=? AND is_read=0', (user_id,)).fetchone()['c']
    except Exception:
        return 0

def allowed(filename):
    if not filename or "." not in filename or len(filename) > 180:
        return False
    ext = filename.rsplit(".", 1)[1].lower()
    return ext in ALLOWED_EXT


def current_user():
    uid = session.get("user_id")
    if not uid:
        return None
    return db().execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone()


def get_contact(user_id, peer_id):
    row = db().execute("SELECT * FROM contacts WHERE user_id=? AND contact_id=?", (user_id, peer_id)).fetchone()
    if not row:
        db().execute("INSERT OR IGNORE INTO contacts(user_id,contact_id,created_at) VALUES(?,?,?)", (user_id, peer_id, now()))
        db().commit()
        row = db().execute("SELECT * FROM contacts WHERE user_id=? AND contact_id=?", (user_id, peer_id)).fetchone()
    return row


def is_blocked_between(user_id, peer_id):
    a = db().execute("SELECT blocked FROM contacts WHERE user_id=? AND contact_id=?", (user_id, peer_id)).fetchone()
    b = db().execute("SELECT blocked FROM contacts WHERE user_id=? AND contact_id=?", (peer_id, user_id)).fetchone()
    return bool((a and a['blocked']) or (b and b['blocked']))


def login_required(fn):
    @wraps(fn)
    def wrap(*args, **kwargs):
        if not session.get("user_id"):
            return redirect(url_for("login"))
        return fn(*args, **kwargs)
    return wrap


CSS = r"""
:root{--bg:#07111f;--panel:#0d1b2d;--panel2:#101f33;--card:#13243a;--line:#203149;--text:#eaf2ff;--muted:#8fa2bb;--blue:#2563eb;--green:#20c784;--danger:#ef4444;--bubble:#173d72;--other:#152333}
*{box-sizing:border-box}body{margin:0;background:radial-gradient(circle at top,#0d2035,#050b14 70%);font-family:Tahoma,Arial,sans-serif;color:var(--text);direction:rtl}a{text-decoration:none;color:inherit}.phone{max-width:480px;margin:0 auto;min-height:100vh;background:var(--bg);border-left:1px solid #112338;border-right:1px solid #112338}.top{height:72px;display:flex;align-items:center;gap:12px;padding:12px 16px;border-bottom:1px solid var(--line);background:rgba(8,18,32,.92);position:sticky;top:0;z-index:5;backdrop-filter:blur(10px)}.brand{font-weight:800;font-size:23px;color:#35d28f;margin-inline:auto}.avatar{width:46px;height:46px;border-radius:50%;object-fit:cover;background:#233;position:relative}.dot{width:12px;height:12px;border-radius:50%;background:var(--green);border:2px solid var(--bg);display:inline-block}.icon{width:42px;height:42px;border-radius:16px;background:var(--panel2);display:grid;place-items:center;color:#c8d5e6;border:1px solid #182b44}.icon.green{background:linear-gradient(135deg,#15b979,#31d695);color:white}.search{margin:14px 16px}.search input,.input input,.input textarea{width:100%;border:1px solid #1b2e49;background:#0b1728;color:var(--text);border-radius:18px;padding:14px;outline:none}.tabs{position:fixed;bottom:0;left:50%;transform:translateX(-50%);width:min(480px,100%);height:70px;background:#091421;border-top:1px solid var(--line);display:flex;justify-content:space-around;align-items:center;z-index:9}.tabs a{font-size:12px;color:#9fb0c6;text-align:center}.tabs a.active{color:#23c786}.list{padding:0 14px 90px}.chatitem{display:flex;align-items:center;gap:12px;padding:12px;border-bottom:1px solid rgba(255,255,255,.05);border-radius:18px}.chatitem:hover{background:#0d1a2b}.chatitem .grow{flex:1}.name{font-weight:800}.last{font-size:13px;color:var(--muted);margin-top:5px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.time{font-size:11px;color:#8aa}.badge{background:#23c784;color:#062014;border-radius:999px;padding:3px 8px;font-weight:700;font-size:11px}.header-name{line-height:1.25}.status{font-size:12px;color:#29d08b}.messages{padding:18px 14px 92px;min-height:calc(100vh - 72px);background-image:linear-gradient(rgba(255,255,255,.015) 1px,transparent 1px);background-size:22px 22px}.day,.secure{margin:10px auto;text-align:center;color:#a6b4c8;background:#101d30;border-radius:14px;padding:8px 12px;font-size:12px;max-width:360px}.msg{max-width:78%;margin:10px 0;padding:10px 12px;border-radius:18px;position:relative;box-shadow:0 8px 20px rgba(0,0,0,.15);touch-action:pan-y;user-select:none;transition:transform .12s ease,outline .12s ease}.msg.swiping{outline:1px solid #38bdf8;transform:translateX(18px)}.me{margin-right:auto;background:linear-gradient(135deg,#123d73,#0d55a5);border-bottom-left-radius:5px}.other{margin-left:auto;background:var(--other);border-bottom-right-radius:5px}.msg small{color:#9fb6d0;font-size:10px;margin-inline-start:8px}.msg img,.msg video{max-width:100%;border-radius:14px;margin-top:8px}.compose{position:fixed;bottom:10px;left:50%;transform:translateX(-50%);width:min(480px,100%);padding:0 12px;display:flex;gap:8px;z-index:10}.compose form{display:flex;gap:8px;width:100%}.compose input[type=text]{flex:1;border:1px solid #1b2e49;background:#0e1b2d;color:white;border-radius:24px;padding:14px}.btn{border:0;border-radius:18px;background:var(--blue);color:white;padding:12px 16px;font-weight:800}.btn.gray{background:#15243a}.auth{padding:28px 18px}.card{background:rgba(13,27,45,.82);border:1px solid #1e314b;border-radius:24px;padding:18px;margin:14px;box-shadow:0 20px 50px rgba(0,0,0,.24)}.title{font-size:26px;font-weight:900;margin:10px 0;color:#fff}.input{margin:10px 0}.grid{display:grid;grid-template-columns:1fr 1fr;gap:10px}.menu{display:none;position:fixed;inset:0;background:rgba(0,0,0,.35);z-index:50;align-items:flex-end}.sheet{background:#081421;border:1px solid #1d314c;border-radius:26px 26px 0 0;width:min(480px,100%);margin:auto auto 0;padding:14px}.actions{display:grid;grid-template-columns:1fr;gap:8px}.actions button,.actions a{background:#102038;color:#e9f2ff;border:1px solid #203653;border-radius:14px;padding:12px;text-align:right;display:block;font:inherit}.reactions{display:flex;gap:8px;margin-bottom:10px}.reactions button{font-size:22px;background:#11233a;border:1px solid #203653;border-radius:15px;padding:8px}.status-row{display:flex;gap:14px;overflow-x:auto;padding:12px 16px}.story{text-align:center;font-size:12px;min-width:70px}.story img{width:60px;height:60px;border-radius:50%;border:2px solid #26c884;object-fit:cover}.callBtns{display:grid;grid-template-columns:1fr 1fr 1fr;gap:10px}.profileRow{display:flex;align-items:center;gap:12px}
.profileStats{display:grid;grid-template-columns:repeat(4,1fr);gap:8px;margin:12px 0}.profileStats div{background:#0b1728;border:1px solid #1b2e49;border-radius:16px;padding:10px 4px;text-align:center}.profileStats b{display:block;font-size:18px;color:#fff}.profileStats span{font-size:11px;color:var(--muted)}
.muted{color:var(--muted);font-size:13px}.danger{color:var(--danger)!important}.ltr{direction:ltr;text-align:left}.filechip{display:inline-block;margin-top:7px;background:#0b1728;border:1px solid #24405f;border-radius:12px;padding:8px;color:#bfe0ff}.quote{background:rgba(255,255,255,.08);border-right:3px solid #38bdf8;padding:7px;border-radius:10px;margin-bottom:7px;color:#cfe6ff;font-size:12px}.replybar{position:fixed;bottom:68px;left:50%;transform:translateX(-50%);width:min(480px,100%);padding:0 12px;z-index:11}.replybox{display:none;background:#102038;border:1px solid #25466d;border-radius:16px;padding:8px;color:#dcecff}.pinmark{font-size:12px;color:#fde68a;margin-bottom:4px}.searchmini{display:flex;gap:8px;margin:10px 14px}.searchmini input{flex:1;border:1px solid #1b2e49;background:#0b1728;color:white;border-radius:14px;padding:10px}

.authErrorBox{display:none;background:rgba(239,68,68,.12);border:1px solid rgba(239,68,68,.45);color:#fecaca;border-radius:16px;padding:11px 13px;margin:10px 0;font-size:14px;line-height:1.7}
.authErrorBox.show{display:block}
.fieldHint{display:none;color:#fca5a5;font-size:12px;margin:6px 6px 0}.input.hasError input,.input.hasError select,.input.hasError textarea,.countryPick.hasError{border-color:#ef4444!important;box-shadow:0 0 0 2px rgba(239,68,68,.16)}.shake{animation:shake .28s ease}@keyframes shake{0%,100%{transform:translateX(0)}25%{transform:translateX(-4px)}50%{transform:translateX(4px)}75%{transform:translateX(-3px)}}
.authSaving{opacity:.75;pointer-events:none}
"""


CSS += r"""
.profileCover{height:170px;background:linear-gradient(135deg,#10243d,#0b5aa7);border-radius:0 0 28px 28px;position:relative;overflow:hidden;border-bottom:1px solid #214366}
.profileCover img{width:100%;height:100%;object-fit:cover;display:block;opacity:.92}
.profileHero{margin:-52px 14px 14px;background:rgba(13,27,45,.9);border:1px solid #24405f;border-radius:26px;padding:16px;text-align:center;position:relative;box-shadow:0 20px 45px rgba(0,0,0,.28)}
.profileHero .avatar{width:112px;height:112px;border:4px solid #07111f;margin-top:-72px;background:#12243a}
.profileStats{display:grid;grid-template-columns:1fr 1fr 1fr;gap:8px;margin-top:14px}.profileStats div{background:#0b1728;border:1px solid #1b2e49;border-radius:16px;padding:10px}.profileStats b{display:block;font-size:18px;color:#eaf2ff}.profileStats span{font-size:11px;color:#8fa2bb}
.attachPanel{display:none;position:fixed;bottom:78px;left:50%;transform:translateX(-50%);width:min(480px,100%);padding:0 12px;z-index:20}.attachGrid{background:#0b1728;border:1px solid #24405f;border-radius:22px;padding:12px;display:grid;grid-template-columns:1fr 1fr;gap:10px}.attachBtn{background:#102038;border:1px solid #203653;border-radius:18px;color:#eaf2ff;padding:14px;text-align:center;font-size:15px;display:flex;align-items:center;justify-content:center;gap:8px;min-height:60px}.attachBtn .big{font-size:24px}.recBtn{border:0;border-radius:18px;background:#ef4444;color:white;padding:12px 14px;font-weight:800}.recBtn.recording{animation:pulse 1s infinite;background:#b91c1c}@keyframes pulse{50%{opacity:.65;transform:scale(.96)}}
.filePreview{font-size:12px;color:#dcecff;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;align-self:center}.attachNotice{display:none;position:fixed;bottom:74px;left:50%;transform:translateX(-50%);width:min(480px,100%);padding:0 12px;z-index:21}.attachNoticeBox{background:#102038;border:1px solid #2b4a70;border-radius:22px;padding:10px 12px;color:#dcecff;font-size:12px;display:flex;align-items:center;gap:10px}.attachNoticeBox b{color:#fff}.attachThumb{width:58px;height:58px;border-radius:14px;object-fit:cover;background:#07111f;border:1px solid #24405f;display:none;flex:0 0 58px}.attachInfo{min-width:0;flex:1}.attachRemove{border:0;background:#1f2937;color:#fff;border-radius:14px;width:38px;height:38px;font-size:18px}.profileFormGrid{display:grid;grid-template-columns:1fr 1fr;gap:10px}
.chatTop{height:68px;padding:8px 10px;gap:8px;overflow:hidden}.chatTop .backBtn{flex:0 0 42px}.chatTop .avatar{flex:0 0 44px}.chatTop .header-name{flex:1;min-width:0}.chatTop .header-name b{display:block;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.chatTools{display:flex;gap:6px;flex:0 0 auto}.chatTools .icon{width:38px;height:38px;border-radius:14px;font-size:15px}.chatTools .txtIcon{font-size:13px;font-weight:800}.searchmini{align-items:center}.searchmini input{min-width:0}.messages{padding-bottom:118px}.compose{bottom:8px;padding:0 8px}.compose form{align-items:center;gap:6px;background:#07111f}.compose .icon{flex:0 0 46px;width:46px;height:46px;border-radius:50%;font-size:24px}.compose input[type=text]{min-width:0;height:56px;padding:0 16px}.sendBtn{flex:0 0 58px;height:52px;border-radius:18px;padding:0;font-size:14px}.recBtn{flex:0 0 54px;height:52px;border-radius:18px;padding:0;font-size:20px;overflow:hidden}.recBtn .recText{display:none}.filePreview{display:inline-block;max-width:110px}.attachPanel{bottom:74px}.attachGrid{grid-template-columns:1fr 1fr}.msg{cursor:pointer}.menu{background:rgba(0,0,0,.55);backdrop-filter:blur(4px);align-items:flex-end}.sheet{max-height:82vh;overflow:auto;padding:12px 14px 22px}.reactions{justify-content:space-between;gap:6px;position:sticky;top:0;background:#081421;padding-bottom:8px;z-index:2}.reactions button{flex:1;min-height:54px;font-size:23px}.actions{gap:10px}.actions button,.actions a{min-height:58px;border-radius:18px;padding:0 16px;font-size:18px;display:flex;align-items:center;justify-content:flex-start;gap:10px}.actionClose{justify-content:center!important;background:#16243a!important}.menuHint{text-align:center;color:#8fa2bb;font-size:12px;margin:4px 0 10px}

.attachGrid{padding:16px;border-radius:28px;gap:14px;background:linear-gradient(180deg,#0d1d33,#081421);box-shadow:0 -18px 55px rgba(0,0,0,.35)}
.attachBtn{min-height:82px;border-radius:24px;flex-direction:column;gap:8px;background:linear-gradient(180deg,#122642,#0d1b31);box-shadow:inset 0 0 0 1px rgba(255,255,255,.035),0 10px 24px rgba(0,0,0,.18);transition:transform .12s ease,background .12s ease}
.attachBtn:active{transform:scale(.96);background:#173255}.attachBtn .big{width:44px;height:44px;border-radius:18px;display:grid;place-items:center;font-size:24px;background:#0b1728;border:1px solid #2b4a70}.attachBtn span:last-child{font-weight:800;color:#eaf2ff}.attachBtn.image .big{background:linear-gradient(135deg,#0ea5e9,#2563eb)}.attachBtn.video .big{background:linear-gradient(135deg,#8b5cf6,#2563eb)}.attachBtn.audio .big{background:linear-gradient(135deg,#10b981,#0ea5e9)}.attachBtn.file .big{background:linear-gradient(135deg,#f59e0b,#ef4444)}.attachBtn.closeAttach{grid-column:1/3;min-height:58px;flex-direction:row}.attachBtn.closeAttach .big{background:#172036}
.voiceModal{display:none;position:fixed;inset:0;background:rgba(0,0,0,.55);z-index:70;align-items:flex-end;backdrop-filter:blur(5px)}.voiceSheet{width:min(480px,100%);margin:0 auto;background:#081421;border:1px solid #24405f;border-radius:28px 28px 0 0;padding:20px;box-shadow:0 -20px 60px rgba(0,0,0,.4);text-align:center}.voiceMic{width:86px;height:86px;border-radius:50%;display:grid;place-items:center;margin:8px auto 12px;font-size:40px;background:linear-gradient(135deg,#ef4444,#b91c1c);box-shadow:0 0 0 8px rgba(239,68,68,.10)}.voiceMic.recording{animation:pulse 1s infinite}.voiceTime{font-size:28px;font-weight:900;margin:8px 0}.voiceStatus{color:#9fb0c6;font-size:13px;line-height:1.7;margin:8px 0 14px}.voiceActions{display:grid;grid-template-columns:1fr 1fr;gap:10px}.voiceActions .btn{min-height:48px}.voiceActions .full{grid-column:1/3}.recBtn{background:linear-gradient(135deg,#ef4444,#dc2626);box-shadow:0 10px 25px rgba(239,68,68,.18)}

.countrySelect{width:100%;border:1px solid #1b2e49;background:#0b1728;color:#eaf2ff;border-radius:18px;padding:14px;display:flex;align-items:center;justify-content:space-between;font:inherit;text-align:right}.countrySelect b{transform:rotate(180deg);color:#8fa2bb}.countryModal{display:none;position:fixed;inset:0;background:rgba(0,0,0,.55);z-index:80;align-items:flex-end;backdrop-filter:blur(5px)}.countrySheet{width:min(480px,100%);max-height:88vh;margin:0 auto;background:#081421;border:1px solid #24405f;border-radius:26px 26px 0 0;overflow:hidden;box-shadow:0 -20px 50px rgba(0,0,0,.35)}.countryHead{height:64px;display:flex;align-items:center;gap:12px;padding:10px 14px;border-bottom:1px solid #1b2e49}.countryHead b{font-size:20px;margin-inline:auto}.countrySearch{padding:12px 14px;border-bottom:1px solid #10233a}.countrySearch input{width:100%;border:1px solid #24405f;background:#0b1728;color:#eaf2ff;border-radius:18px;padding:13px 16px;outline:none}.countryList{max-height:calc(88vh - 130px);overflow:auto;padding:6px 8px 18px}.countryRow{width:100%;border:0;background:transparent;color:#eaf2ff;display:flex;align-items:center;gap:12px;padding:13px 10px;border-bottom:1px solid rgba(255,255,255,.05);font:inherit;text-align:right;border-radius:16px}.countryRow:hover{background:#102038}.countryFlag{font-size:26px;flex:0 0 36px}.countryName{flex:1;font-weight:800}.countryName small{display:block;color:#8fa2bb;font-size:11px;margin-top:3px}.countryRow b{direction:ltr;color:#bfe0ff;background:#102038;border:1px solid #203653;border-radius:999px;padding:5px 9px;font-size:13px}.countryEmpty{padding:20px;text-align:center;color:#8fa2bb}
@media(max-width:380px){.chatTools .icon{width:34px;height:34px}.chatTop{gap:6px;padding-inline:8px}.compose .icon{flex-basis:42px;width:42px}.sendBtn{flex-basis:52px}.recBtn{flex-basis:48px}.compose input[type=text]{height:52px}.searchmini{margin:8px}.searchmini .btn{padding:10px 12px}}

"""


CSS += r"""
/* STAGE26: تصغير قائمة المرفقات ومعاينة واتساب */
.attachPanel{bottom:72px;padding:0 14px}.attachGrid{width:70%;margin-inline-start:auto;padding:10px;border-radius:18px;grid-template-columns:1fr 1fr;gap:8px}.attachBtn{min-height:44px;border-radius:15px;gap:6px;font-size:12px;padding:8px}.attachBtn .big{width:30px;height:30px;border-radius:12px;font-size:17px}.attachBtn.closeAttach{min-height:42px}.attachNotice{bottom:70px;padding:0 12px}.attachNoticeBox{max-width:78%;margin-inline-start:auto;border-radius:18px;padding:7px 8px;gap:8px;background:linear-gradient(180deg,#11243d,#0d1b31)}.attachThumb{width:74px!important;height:74px!important;border-radius:14px;object-fit:cover;display:block}.attachThumb.videoThumb,.attachThumb.fileThumb,.attachThumb.audioThumb{display:grid!important;place-items:center;font-size:28px;background:#0b1728}.attachInfo b{font-size:12px}.filePreview{font-size:12px;white-space:normal;display:block;max-width:180px}.attachRemove{width:32px;height:32px;border-radius:12px}.voiceSheet{max-width:82%;border-radius:24px 24px 0 0;padding:14px}.voiceMic{width:58px;height:58px;font-size:28px;margin:4px auto 8px}.voiceTime{font-size:22px;margin:4px 0}.voiceStatus{font-size:12px;margin:6px 0 10px}.voiceActions .btn{min-height:40px;border-radius:14px;padding:9px 10px}.voiceActions{gap:8px}.compose{bottom:8px}.messages{padding-bottom:106px}
"""

CSS += r"""
/* STAGE27: تصميم واصل الخاص للمرفقات - ليس نسخ واتساب */
.attachPanel{bottom:70px;padding:0 10px;pointer-events:none}.attachGrid{pointer-events:auto;width:52%;min-width:210px;max-width:245px;margin-inline-start:auto;grid-template-columns:repeat(2,1fr);gap:7px;padding:8px;border-radius:22px;background:linear-gradient(145deg,rgba(9,23,40,.96),rgba(14,35,61,.93));border:1px solid rgba(59,130,246,.22);box-shadow:0 18px 46px rgba(0,0,0,.45),inset 0 1px 0 rgba(255,255,255,.06)}
.attachBtn{min-height:38px;border-radius:16px;padding:7px 6px;font-size:11px;gap:4px;background:linear-gradient(180deg,rgba(18,39,67,.96),rgba(9,21,37,.96));border:1px solid rgba(148,163,184,.13);box-shadow:0 8px 18px rgba(0,0,0,.20);position:relative;overflow:hidden}
.attachBtn:after{content:'';position:absolute;inset:auto 8px 5px 8px;height:2px;border-radius:999px;background:linear-gradient(90deg,transparent,rgba(59,130,246,.45),transparent);opacity:.6}.attachBtn .big{width:24px;height:24px;border-radius:10px;font-size:14px;border:0;box-shadow:0 6px 14px rgba(0,0,0,.18)}.attachBtn span:last-child{font-size:11px;line-height:1.1}.attachBtn.closeAttach{grid-column:1/3;min-height:34px;flex-direction:row;border-radius:15px}.attachBtn.closeAttach .big{width:22px;height:22px}.attachBtn.image .big{background:linear-gradient(135deg,#38bdf8,#2563eb)}.attachBtn.video .big{background:linear-gradient(135deg,#a78bfa,#4f46e5)}.attachBtn.audio .big{background:linear-gradient(135deg,#2dd4bf,#0891b2)}.attachBtn.file .big{background:linear-gradient(135deg,#fb923c,#ef4444)}
.attachNotice{bottom:70px;padding:0 8px}.attachNoticeBox{max-width:72%;margin-inline-start:auto;border-radius:20px;padding:6px;background:linear-gradient(145deg,#10243d,#091827);border:1px solid rgba(59,130,246,.26);box-shadow:0 14px 36px rgba(0,0,0,.34)}.attachThumb{width:82px!important;height:82px!important;border-radius:16px;border:0;box-shadow:0 6px 18px rgba(0,0,0,.28)}.attachInfo b{font-size:11px;color:#dbeafe}.filePreview{font-size:11px;max-width:150px;color:#b9c7d9}.attachRemove{width:30px;height:30px;border-radius:11px;background:rgba(15,23,42,.92)}
.voiceModal{background:rgba(0,0,0,.42)}.voiceSheet{max-width:72%;border-radius:22px;padding:12px;background:linear-gradient(145deg,#0b182a,#10243d)}.voiceMic{width:54px;height:54px;font-size:27px}.voiceTime{font-size:21px}.voiceStatus{font-size:11px}.voiceActions .btn{min-height:38px;font-size:12px}
"""

CSS += r"""
/* STAGE28: قائمة المرفقات في سطر واحد بدل المربعات */
.attachPanel{bottom:70px!important;padding:0 8px!important;pointer-events:none!important}
.attachGrid{pointer-events:auto!important;width:auto!important;max-width:calc(100% - 16px)!important;min-width:0!important;margin:0 auto!important;display:flex!important;grid-template-columns:none!important;align-items:center!important;justify-content:space-between!important;gap:6px!important;padding:7px 8px!important;border-radius:18px!important;background:linear-gradient(145deg,rgba(9,23,40,.96),rgba(14,35,61,.93))!important;border:1px solid rgba(59,130,246,.22)!important;box-shadow:0 12px 34px rgba(0,0,0,.38),inset 0 1px 0 rgba(255,255,255,.05)!important;overflow-x:auto!important;scrollbar-width:none!important}
.attachGrid::-webkit-scrollbar{display:none}
.attachBtn{flex:1 1 0!important;min-width:54px!important;min-height:42px!important;border-radius:14px!important;padding:5px 4px!important;font-size:10px!important;gap:3px!important;display:flex!important;flex-direction:column!important;align-items:center!important;justify-content:center!important;background:linear-gradient(180deg,rgba(18,39,67,.94),rgba(9,21,37,.94))!important;border:1px solid rgba(148,163,184,.13)!important;box-shadow:0 6px 14px rgba(0,0,0,.18)!important}
.attachBtn:after{display:none!important}.attachBtn .big{width:24px!important;height:24px!important;border-radius:10px!important;font-size:14px!important}.attachBtn span:last-child{font-size:10px!important;line-height:1!important;font-weight:800!important}.attachBtn.closeAttach{grid-column:auto!important;flex:0 0 42px!important;min-width:42px!important;min-height:42px!important;border-radius:14px!important;flex-direction:column!important}.attachBtn.closeAttach span:last-child{display:none!important}.attachBtn.closeAttach .big{width:26px!important;height:26px!important;border-radius:50%!important;font-size:15px!important}
.attachNotice{bottom:70px!important}.attachNoticeBox{max-width:82%!important;border-radius:17px!important;padding:6px!important}.attachThumb{width:64px!important;height:64px!important;border-radius:13px!important}.filePreview{font-size:10px!important;max-width:160px!important}.attachInfo b{font-size:10px!important}.attachRemove{width:28px!important;height:28px!important;border-radius:10px!important}
"""



CSS += r"""
/* STAGE29: تطوير كامل للحالات والمشاهدات 24 ساعة */
.statusHero{padding:12px 14px 92px}.statusComposer{display:none}.statusComposer:target{display:block}.storyRail{display:flex;gap:12px;overflow-x:auto;padding:12px 14px 8px;scrollbar-width:none}.storyRail::-webkit-scrollbar{display:none}.storyBubble{min-width:76px;text-align:center;color:#dbeafe}.storyRing{width:64px;height:64px;margin:0 auto 6px;border-radius:50%;padding:3px;background:conic-gradient(#38bdf8 var(--p,100%),#203653 0);display:grid;place-items:center}.storyRing img,.storyRing .initial{width:56px;height:56px;border-radius:50%;object-fit:cover;background:#102038;display:grid;place-items:center;font-weight:900}.storyBubble small{display:block;color:#8fa2bb;font-size:10px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.statusCardNew{background:linear-gradient(145deg,#0d1d33,#091827);border:1px solid #1f3653;border-radius:24px;padding:14px;margin:10px 14px;box-shadow:0 14px 38px rgba(0,0,0,.22)}.statusCard{background:linear-gradient(145deg,#10233c,#081524);border:1px solid #203653;border-radius:24px;margin:12px 14px;padding:12px;overflow:hidden}.statusMeta{display:flex;align-items:center;gap:10px}.statusMeta .grow{flex:1}.statusTime{font-size:11px;color:#93a8c2;margin-top:4px}.statusProgress{height:4px;border-radius:999px;background:#1b2e49;overflow:hidden;margin:10px 0}.statusProgress i{display:block;height:100%;width:var(--w,100%);background:linear-gradient(90deg,#38bdf8,#2563eb);border-radius:999px}.statusPreviewText{font-size:15px;line-height:1.8;margin:8px 2px;color:#eef6ff}.statusActions{display:flex;gap:8px;flex-wrap:wrap;margin-top:10px}.statusActions a,.statusActions span{display:inline-flex;align-items:center;gap:4px;border-radius:999px;padding:6px 10px;background:#102038;border:1px solid #24405f;color:#dbeafe;font-size:12px}.statusFull{min-height:calc(100vh - 72px);padding:10px 12px 90px;background:radial-gradient(circle at top,#10294a,#050b14 70%);display:flex;flex-direction:column}.statusTopBar{height:5px;border-radius:999px;background:#203653;overflow:hidden;margin:8px 2px 12px}.statusTopBar i{display:block;height:100%;width:var(--w,100%);background:linear-gradient(90deg,#22c55e,#38bdf8,#2563eb)}.statusViewerBox{flex:1;display:flex;align-items:center;justify-content:center;min-height:55vh;background:rgba(8,20,35,.55);border:1px solid #1d314c;border-radius:26px;padding:12px;overflow:hidden}.statusViewerBox img,.statusViewerBox video{max-width:100%;max-height:68vh;border-radius:22px;object-fit:contain;background:#020814}.statusTextOnly{font-size:28px;font-weight:900;line-height:1.7;text-align:center;padding:30px;color:#fff}.statusReplyBar{position:fixed;bottom:8px;left:50%;transform:translateX(-50%);width:min(480px,100%);padding:0 12px;display:flex;gap:8px;z-index:20}.statusReplyBar input{flex:1;border:1px solid #25466d;background:#0b1728;color:white;border-radius:24px;padding:14px;outline:none}.statusOwnerStats{display:flex;gap:8px;flex-wrap:wrap;justify-content:center;margin:12px 0}.statusOwnerStats a{border-radius:999px;background:#102038;border:1px solid #24405f;color:#dbeafe;padding:8px 12px}.statusExpired{opacity:.55;filter:grayscale(.2)}
"""



CSS += r"""
/* STAGE30: قائمة الضغط المطول الاحترافية الخاصة بواصل */
.menu{background:rgba(2,8,18,.56)!important;backdrop-filter:blur(6px)!important;align-items:flex-end!important;padding:0 10px 82px!important}
.sheet{width:min(360px,calc(100% - 28px))!important;margin:0 auto!important;background:linear-gradient(180deg,rgba(19,31,48,.98),rgba(9,17,29,.98))!important;border:1px solid rgba(148,163,184,.22)!important;border-radius:24px!important;box-shadow:0 20px 60px rgba(0,0,0,.55),inset 0 1px 0 rgba(255,255,255,.06)!important;padding:10px!important;max-height:72vh!important;overflow:auto!important;animation:waselSheet .16s ease-out!important}
@keyframes waselSheet{from{opacity:.2;transform:translateY(18px) scale(.98)}to{opacity:1;transform:translateY(0) scale(1)}}
.reactions{position:relative!important;top:auto!important;margin:-58px auto 12px!important;width:calc(100% - 8px)!important;max-width:100%!important;min-width:0!important;background:linear-gradient(180deg,#111c2c,#0a1322)!important;border:1px solid rgba(148,163,184,.25)!important;border-radius:999px!important;padding:6px 8px!important;gap:4px!important;box-shadow:0 12px 34px rgba(0,0,0,.45)!important;justify-content:flex-start!important;overflow-x:auto!important;overflow-y:hidden!important;white-space:nowrap!important;scrollbar-width:none!important;-webkit-overflow-scrolling:touch!important;animation:waselReact .16s ease-out!important}.reactions::-webkit-scrollbar{display:none!important}
@keyframes waselReact{from{opacity:.25;transform:translateY(10px) scale(.96)}to{opacity:1;transform:translateY(0) scale(1)}}
.reactions:after{content:'';position:absolute;bottom:-7px;left:50%;transform:translateX(-50%) rotate(45deg);width:14px;height:14px;background:#0a1322;border-right:1px solid rgba(148,163,184,.25);border-bottom:1px solid rgba(148,163,184,.25)}
.reactions button{width:32px!important;height:32px!important;min-height:32px!important;flex:0 0 32px!important;border-radius:50%!important;background:rgba(30,41,59,.86)!important;border:1px solid rgba(148,163,184,.16)!important;padding:0!important;font-size:18px!important;display:grid!important;place-items:center!important;transition:transform .12s ease,background .12s ease,box-shadow .12s ease!important;position:relative;z-index:1}.reactions button:active{transform:scale(.88)!important;background:#1d4ed8!important;box-shadow:0 0 0 3px rgba(59,130,246,.18)!important}
.menuHint{display:none!important}.actions{display:block!important;gap:0!important}.actionGroup{border-bottom:1px solid rgba(148,163,184,.18);padding:4px 0}.actionGroup:last-child{border-bottom:0}.actions button,.actions a{width:100%!important;min-height:46px!important;border:0!important;border-radius:14px!important;background:transparent!important;color:#eef6ff!important;padding:0 10px!important;font-size:16px!important;display:flex!important;align-items:center!important;justify-content:flex-start!important;gap:12px!important;box-shadow:none!important;transition:background .12s ease,transform .12s ease!important}.actions button:active,.actions a:active{background:rgba(59,130,246,.18)!important;transform:scale(.99)}.actions .ico{width:30px;height:30px;border-radius:11px;display:grid;place-items:center;background:rgba(30,41,59,.92);font-size:18px;flex:0 0 30px}.actions .purple .ico{color:#c084fc}.actions .blue .ico{color:#60a5fa}.actions .yellow .ico{color:#facc15}.actions .green .ico{color:#4ade80}.actions .orange .ico{color:#fb923c}.actions .red,.actions .red span{color:#fecaca!important}.actions .red .ico{color:#ef4444;background:rgba(127,29,29,.26)}.actionClose{margin-top:6px!important;justify-content:center!important;background:rgba(15,23,42,.9)!important;border:1px solid rgba(148,163,184,.16)!important;color:#cbd5e1!important}.actionClose .ico{display:none}.messageQuickInfo{background:rgba(15,23,42,.72);border:1px solid rgba(148,163,184,.14);border-radius:16px;padding:8px 10px;margin-bottom:8px;color:#93a8c2;font-size:12px;display:flex;align-items:center;justify-content:space-between}.messageQuickInfo b{color:#eaf2ff;font-size:13px}.msg.longpress-active{outline:1px solid rgba(168,85,247,.65);box-shadow:0 0 0 4px rgba(168,85,247,.10),0 8px 20px rgba(0,0,0,.18)!important}
@media(max-width:380px){.sheet{width:calc(100% - 18px)!important}.reactions button{width:30px!important;height:30px!important;flex-basis:30px!important;font-size:17px!important}.actions button,.actions a{font-size:15px!important;min-height:43px!important}}
"""


CSS += r"""
/* STAGE31 FIX: شريط التفاعلات يظهر كاملًا مع تمرير أفقي احترافي */
.sheet{width:min(390px,calc(100% - 18px))!important;overflow:visible!important;max-height:74vh!important;padding-top:12px!important}
.reactions{box-sizing:border-box!important;width:100%!important;max-width:100%!important;margin:-54px auto 12px!important;padding:6px 7px!important;display:flex!important;flex-wrap:nowrap!important;justify-content:flex-start!important;gap:5px!important;overflow-x:auto!important;overflow-y:hidden!important;scroll-snap-type:x proximity!important;overscroll-behavior-x:contain!important;white-space:nowrap!important;border-radius:999px!important;min-height:40px!important}
.reactions button{width:29px!important;height:29px!important;min-width:29px!important;min-height:29px!important;flex:0 0 29px!important;font-size:16px!important;line-height:1!important;scroll-snap-align:center!important}
.reactions button.selected{background:#1d4ed8!important;border-color:#93c5fd!important;box-shadow:0 0 0 3px rgba(59,130,246,.28),0 0 18px rgba(59,130,246,.45)!important;transform:translateY(-1px)!important}
.reactions button:hover{background:#1e3a8a!important}
.actionGroup{overflow:hidden!important}.actions{max-height:calc(74vh - 56px)!important;overflow:auto!important;padding-bottom:2px!important}.actions button,.actions a{min-height:44px!important;font-size:15px!important}.messageQuickInfo{margin-top:2px!important}
@media(max-width:380px){.sheet{width:calc(100% - 12px)!important}.reactions{gap:4px!important;padding:6px!important}.reactions button{width:28px!important;height:28px!important;min-width:28px!important;flex-basis:28px!important;font-size:15px!important}.actions button,.actions a{min-height:42px!important;font-size:14px!important}}
"""


CSS += r"""

/* STAGE33 FIX: إظهار دائرة تفاعلات الحالة كاملة + ردود خاصة داخل الحالة */
.statusCard{overflow:visible!important}.statusPublicActions{position:relative;overflow:visible!important}.statusReactWrap{position:relative;overflow:visible!important;z-index:80}.statusReactionCircle{right:50%!important;left:auto!important;transform:translateX(50%)!important;bottom:58px!important;width:172px!important;height:172px!important;overflow:visible!important}.statusReactionCircle.show{display:block!important;animation:reactPopFixed .14s ease-out}@keyframes reactPopFixed{from{opacity:.2;transform:translateX(50%) scale(.78)}to{opacity:1;transform:translateX(50%) scale(1)}}.statusReactionCircle button{width:44px!important;height:44px!important}.statusReactionCircle button:nth-child(1){top:6px!important;left:64px!important}.statusReactionCircle button:nth-child(2){top:32px!important;right:10px!important}.statusReactionCircle button:nth-child(3){bottom:32px!important;right:10px!important}.statusReactionCircle button:nth-child(4){bottom:6px!important;left:64px!important}.statusReactionCircle button:nth-child(5){bottom:32px!important;left:10px!important}.statusReactionCircle button:nth-child(6){top:32px!important;left:10px!important}.statusReplyList{margin:12px 0 96px;display:grid;gap:8px}.statusReplyItem{background:#102038;border:1px solid #24405f;border-radius:18px;padding:10px}.statusReplyMine{background:#0d3a6d}.statusReplyOwner{background:#14304f}.inlineReplyForm{display:flex;gap:8px;margin-top:8px}.inlineReplyForm input{flex:1;border:1px solid #25466d;background:#0b1728;color:#fff;border-radius:18px;padding:11px}.statusFileCaption{position:absolute;left:10px;right:10px;bottom:10px;background:rgba(2,8,18,.58);border:1px solid rgba(148,163,184,.20);border-radius:16px;padding:10px;color:#fff;font-weight:800;text-align:center;backdrop-filter:blur(4px)}.statusPreviewPane{position:relative}.statusPreviewPane img,.statusPreviewPane video{display:block}.statusFileName{font-size:12px;color:#93a8c2;text-align:center;margin:6px 0;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}

/* STAGE32: حالات ذكية + تفاعلات دائرية + معاينة رفع */
.statusCreateBox{background:linear-gradient(145deg,#0d1d33,#081524);border:1px solid #24405f;border-radius:26px;margin:12px 14px;padding:14px;box-shadow:0 16px 40px rgba(0,0,0,.24)}
.statusTypeTabs{display:flex;gap:8px;margin:10px 0}.statusTypeTabs button{flex:1;border:1px solid #24405f;background:#102038;color:#dbeafe;border-radius:16px;padding:11px;font-weight:800}.statusTypeTabs button.active{background:#2563eb;color:white}.statusComposer textarea{min-height:86px;resize:vertical;text-align:center;font-size:20px;font-weight:800;line-height:1.6}.statusPreviewPane{display:none;margin-top:10px;border:1px solid #24405f;border-radius:22px;overflow:hidden;background:#07111f;min-height:210px;align-items:center;justify-content:center;text-align:center}.statusPreviewPane.show{display:flex}.statusPreviewPane img,.statusPreviewPane video{max-width:100%;max-height:320px;object-fit:contain}.statusBg_blue{background:linear-gradient(135deg,#0f3b75,#2563eb)!important}.statusBg_green{background:linear-gradient(135deg,#064e3b,#10b981)!important}.statusBg_purple{background:linear-gradient(135deg,#3b0764,#8b5cf6)!important}.statusBg_dark{background:linear-gradient(135deg,#020617,#111827)!important}.statusPreviewTextBig{font-size:28px;font-weight:900;line-height:1.8;color:white;padding:24px;word-break:break-word}.statusCard{position:relative}.statusPublicActions{display:flex;gap:8px;align-items:center;margin-top:10px}.statusRoundBtn{width:46px;height:46px;border-radius:50%;border:1px solid #24405f;background:linear-gradient(145deg,#13243a,#091827);display:grid;place-items:center;color:white;font-size:22px;box-shadow:0 10px 24px rgba(0,0,0,.25)}.statusReactWrap{position:relative;display:inline-block}.statusReactionCircle{display:none;position:absolute;bottom:54px;right:-46px;width:142px;height:142px;border-radius:50%;background:rgba(8,20,35,.88);border:1px solid rgba(148,163,184,.25);box-shadow:0 18px 46px rgba(0,0,0,.45);backdrop-filter:blur(8px);z-index:30}.statusReactionCircle.show{display:block;animation:reactPop .14s ease-out}@keyframes reactPop{from{opacity:.2;transform:scale(.78)}to{opacity:1;transform:scale(1)}}.statusReactionCircle button{position:absolute;width:42px;height:42px;border-radius:50%;border:1px solid rgba(148,163,184,.18);background:#102038;color:white;font-size:22px;display:grid;place-items:center;box-shadow:0 8px 18px rgba(0,0,0,.25)}.statusReactionCircle button:nth-child(1){top:4px;left:50px}.statusReactionCircle button:nth-child(2){top:25px;right:8px}.statusReactionCircle button:nth-child(3){bottom:25px;right:8px}.statusReactionCircle button:nth-child(4){bottom:4px;left:50px}.statusReactionCircle button:nth-child(5){bottom:25px;left:8px}.statusReactionCircle button:nth-child(6){top:25px;left:8px}.statusOwnerStats .statusChip{border-radius:999px;background:#102038;border:1px solid #24405f;color:#dbeafe;padding:8px 12px;display:inline-flex;gap:5px}.statusViewerBox.statusTextView{border:0}.statusReplyThread{margin:10px 14px 90px}.threadBubble{background:#102038;border:1px solid #24405f;border-radius:18px;padding:10px;margin:8px 0}.threadBubble .last{white-space:normal}.statusSubList{display:grid;gap:8px;padding:0 14px 90px}.statusSubList .chatitem{background:#0b1728;border:1px solid #1d314c}.ownerOnlyNote{text-align:center;color:#8fa2bb;font-size:12px;margin:8px}.statusTime strong{color:#dbeafe}.statusActions.ownerOnly{border-top:1px solid rgba(255,255,255,.06);padding-top:10px}
"""


CSS += r"""
/* STAGE34: إصلاح تفاعل الحالة + ردود الحالة الخاصة مثل المحادثة */
.statusCard,.statusFull,.statusViewerBox,.statusPublicActions,.statusReactWrap{overflow:visible!important}
.statusPublicActions{position:relative;z-index:30}.statusReactWrap{display:inline-flex!important;align-items:center;justify-content:center;z-index:90!important}
.statusRoundBtn{position:relative;z-index:92!important;pointer-events:auto!important}
.statusReactionCircle{position:absolute!important;left:50%!important;right:auto!important;bottom:58px!important;transform:translateX(-50%) scale(.88)!important;width:166px!important;height:166px!important;border-radius:50%!important;display:none!important;overflow:visible!important;z-index:500!important;pointer-events:auto!important;background:rgba(10,25,43,.95)!important;box-shadow:0 18px 45px rgba(0,0,0,.50)!important}
.statusReactionCircle.show{display:block!important;transform:translateX(-50%) scale(1)!important}
.statusReactionCircle button{position:absolute!important;width:42px!important;height:42px!important;min-width:42px!important;min-height:42px!important;border-radius:50%!important;padding:0!important;pointer-events:auto!important;z-index:510!important}
.statusReactionCircle button:nth-child(1){top:6px!important;left:62px!important}.statusReactionCircle button:nth-child(2){top:30px!important;right:10px!important}.statusReactionCircle button:nth-child(3){bottom:30px!important;right:10px!important}.statusReactionCircle button:nth-child(4){bottom:6px!important;left:62px!important}.statusReactionCircle button:nth-child(5){bottom:30px!important;left:10px!important}.statusReactionCircle button:nth-child(6){top:30px!important;left:10px!important}
.statusClearFile{position:absolute;top:10px;left:10px;width:38px;height:38px;border-radius:50%;border:1px solid rgba(255,255,255,.22);background:rgba(2,8,18,.72);color:#fff;font-size:22px;z-index:4}
.statusReplyItem{position:relative;touch-action:pan-y;user-select:none}.statusReplyItem.swiping{outline:1px solid #38bdf8;transform:translateX(14px)}.statusReplyItem .replyReaction{float:left;background:#0b1728;border:1px solid #24405f;border-radius:999px;padding:2px 8px;font-size:16px}.replyQuote{background:rgba(255,255,255,.08);border-right:3px solid #60a5fa;border-radius:12px;padding:6px 8px;margin:6px 0;color:#cfe6ff;font-size:12px}
.statusReplyMenu{display:none;position:fixed;inset:0;background:rgba(0,0,0,.42);z-index:700;align-items:flex-end;backdrop-filter:blur(4px)}.statusReplySheet{width:min(390px,calc(100% - 18px));margin:0 auto 12px;background:linear-gradient(180deg,#101f33,#081421);border:1px solid #24405f;border-radius:22px;padding:10px;box-shadow:0 20px 55px rgba(0,0,0,.50)}.statusReplyReacts{display:flex;gap:6px;justify-content:space-between;margin-bottom:8px}.statusReplyReacts button{width:42px;height:42px;border-radius:50%;border:1px solid #24405f;background:#102038;color:white;font-size:20px}.statusReplyActions{display:grid;gap:7px}.statusReplyActions button{border:0;border-radius:15px;background:#102038;color:#eaf2ff;padding:12px;text-align:right;font:inherit}.statusReplyActions .danger{background:rgba(127,29,29,.35)!important;color:#fecaca!important}.statusReplyActions .close{background:#17243a!important;text-align:center}.statusReplyHint{display:none;margin:0 12px 8px;background:#102038;border:1px solid #24405f;border-radius:16px;padding:8px;color:#dbeafe;font-size:12px}.statusReplyBar{align-items:center}.statusReplyBar input[name=body]{min-width:0}.backHistory{cursor:pointer}
"""

CSS += r"""
/* STAGE37: إطار واضح لنص الردود داخل الحالة */
.statusReplyBody{display:block;background:rgba(15,32,55,.95);border:1px solid rgba(96,165,250,.32);border-radius:16px;padding:10px 12px;margin-top:7px;line-height:1.8;color:#eef6ff;white-space:pre-wrap;word-break:break-word;box-shadow:inset 0 1px 0 rgba(255,255,255,.04)}
.statusReplyItem{padding:12px!important;border-radius:20px!important;background:rgba(8,20,35,.35)!important;border:1px solid rgba(96,165,250,.12)!important;margin:10px 0!important}
.statusReplyItem small{display:block;margin-top:6px}
"""



CSS += r"""
/* STAGE38: إطار واضح لنص ردود الحالة */
.statusReplyBody{
  margin-top:10px!important;
  margin-bottom:8px!important;
  padding:12px 14px!important;
  border-radius:18px!important;
  border:1px solid rgba(96,165,250,.35)!important;
  background:linear-gradient(145deg,rgba(17,38,68,.96),rgba(9,24,43,.96))!important;
  color:#f2f7ff!important;
  font-size:16px!important;
  line-height:1.8!important;
  font-weight:700!important;
  white-space:pre-wrap!important;
  word-break:break-word!important;
  box-shadow:inset 0 1px 0 rgba(255,255,255,.04),0 8px 22px rgba(0,0,0,.18)!important;
}
.statusReplyOwner .statusReplyBody{border-color:rgba(34,197,94,.35)!important;background:linear-gradient(145deg,rgba(16,74,55,.92),rgba(8,31,38,.95))!important}
.statusReplyMine .statusReplyBody{border-color:rgba(59,130,246,.42)!important;background:linear-gradient(145deg,rgba(20,70,124,.92),rgba(8,30,56,.96))!important}
.statusReplyListPage{padding:0 14px 90px!important}.statusReplyCard{display:flex;gap:12px;align-items:flex-start;padding:14px 0;border-bottom:1px solid rgba(148,163,184,.09)}.statusReplyCard .avatar{flex:0 0 48px}.statusReplyContent{flex:1;min-width:0}.statusReplyHeader{display:flex;align-items:center;justify-content:space-between;gap:8px;margin-bottom:6px}.statusReplyHeader .name{font-size:16px}.statusReplyTime{font-size:12px;color:#93a8c2;white-space:nowrap}.statusReplyMessageFrame{padding:12px 14px;border-radius:18px;border:1px solid rgba(96,165,250,.34);background:linear-gradient(145deg,#102542,#0a192d);color:#f4f8ff;font-size:16px;line-height:1.8;font-weight:700;white-space:pre-wrap;word-break:break-word;box-shadow:0 8px 24px rgba(0,0,0,.18)}.statusReplyParentFrame{margin:7px 0 8px;padding:8px 10px;border-radius:14px;border-right:3px solid #60a5fa;background:rgba(255,255,255,.06);color:#cfe6ff;font-size:13px;line-height:1.6}.inlineReplyForm{margin-top:9px!important;display:flex;gap:8px}.inlineReplyForm input{flex:1;min-width:0;border:1px solid #25466d;background:#0b1728;color:white;border-radius:16px;padding:11px 12px;outline:none}.inlineReplyForm .btn{border-radius:16px;padding:10px 14px}.statusReplyEmpty{margin:14px;border:1px dashed rgba(148,163,184,.25);background:rgba(15,32,55,.45);border-radius:22px;padding:18px;text-align:center;color:#93a8c2}
"""



CSS += r"""
/* STAGE39: تصميم صفحة المحادثات الجديد - بدون كاميرا، بدون شريط بحث طويل ظاهر، بدون المثبتة */
.chatHome{min-height:100vh;padding:0 14px 92px;background:radial-gradient(circle at top,#0b2136,#07111f 68%)}
.chatHomeTop{height:92px;display:grid;grid-template-columns:56px 1fr 56px;align-items:center;gap:8px;position:sticky;top:0;z-index:6;background:linear-gradient(180deg,rgba(7,17,31,.98),rgba(7,17,31,.78));backdrop-filter:blur(10px)}
.chatLogo{font-size:31px;font-weight:900;color:#29d08b;text-align:center;text-shadow:0 8px 24px rgba(35,199,132,.16)}
.chatTopIcon{width:48px;height:48px;border:0;background:transparent;color:#f2f7ff;display:grid;place-items:center;font-size:34px;border-radius:18px}.searchOnlyBtn{font-size:44px;line-height:1;cursor:pointer}.chatTopIcon:active{background:#102038;transform:scale(.96)}
.chatSearchCollapsed{display:none;margin:0 0 12px}.chatSearchCollapsed.show{display:flex}.chatSearchCollapsed input{width:100%;height:52px;border:1px solid #213b59;background:#0c1a2c;color:#eaf2ff;border-radius:22px;padding:0 18px;font-size:15px;outline:none}
.chatFilterBar{height:62px;border:1px solid rgba(61,91,126,.55);background:linear-gradient(180deg,rgba(13,31,51,.9),rgba(8,20,34,.9));border-radius:24px;display:grid;grid-template-columns:1fr 1fr;align-items:center;margin:0 0 16px;overflow:hidden;box-shadow:0 12px 30px rgba(0,0,0,.18)}
.chatFilterBar a{height:100%;display:grid;place-items:center;color:#e7eefb;font-size:19px;font-weight:800;position:relative}.chatFilterBar a.active{color:#27d690;background:linear-gradient(180deg,rgba(38,199,132,.08),rgba(38,199,132,.02))}.chatFilterBar a.active:after{content:'';position:absolute;bottom:0;width:96px;height:4px;border-radius:999px;background:#27d690;box-shadow:0 0 18px rgba(39,214,144,.45)}
.chatRowsBox{border:1px solid rgba(28,52,80,.86);border-radius:26px;overflow:hidden;background:linear-gradient(180deg,rgba(10,28,47,.72),rgba(7,18,31,.62));box-shadow:0 18px 45px rgba(0,0,0,.20)}
.chatRowNew{min-height:94px;display:grid;grid-template-columns:76px 1fr 70px;gap:12px;align-items:center;padding:12px 14px;border-bottom:1px solid rgba(110,140,170,.12);position:relative}.chatRowNew:last-child{border-bottom:0}.chatRowNew:active{background:rgba(37,99,235,.10)}
.chatAvatarWrap{position:relative;width:64px;height:64px}.chatAvatar{width:64px;height:64px;border-radius:50%;object-fit:cover;background:#12243a;box-shadow:0 0 0 1px rgba(255,255,255,.05)}.onlineDot{position:absolute;right:1px;bottom:2px;width:15px;height:15px;border-radius:50%;background:#23c784;border:3px solid #07111f}
.chatMainNew{min-width:0;text-align:right}.chatNameLine b{font-size:21px;color:#fff;font-weight:900;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;display:block}.chatLastLine{font-size:15px;color:#92a4bb;margin-top:7px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;line-height:1.4}.chatSideNew{text-align:left;display:flex;flex-direction:column;align-items:flex-start;gap:8px;min-height:64px}.chatTimeNew{font-size:14px;color:#9aa9bb;direction:ltr}.chatUnread{width:30px;height:30px;border-radius:50%;display:grid;place-items:center;background:linear-gradient(135deg,#22c55e,#2dd4bf);color:#042014;font-weight:900;box-shadow:0 8px 18px rgba(34,197,94,.28)}.chatMute{font-size:14px;color:#8fa2bb}.chatFab{position:fixed;bottom:86px;right:calc(50% - 220px);width:74px;height:74px;border-radius:28px;background:linear-gradient(135deg,#23c784,#2dd4bf);color:white;display:grid;place-items:center;font-size:42px;font-weight:300;z-index:12;box-shadow:0 18px 42px rgba(35,199,132,.28)}.chatFab small{position:absolute;bottom:-28px;right:0;width:100px;color:#36e69f;font-size:12px;font-weight:800;text-align:center}.chatHome .card{margin:18px 0}.chatHome + .tabs,.tabs{height:76px;border-top:1px solid rgba(61,91,126,.5);background:rgba(7,18,31,.96);border-radius:26px 26px 0 0;box-shadow:0 -16px 38px rgba(0,0,0,.25)}
@media(max-width:480px){.chatFab{right:22px}.chatRowNew{grid-template-columns:72px 1fr 62px;padding:12px}.chatNameLine b{font-size:19px}.chatLastLine{font-size:14px}.chatHomeTop{height:86px}.chatLogo{font-size:29px}}
"""

def page(body, title=APP_NAME):
    body = inject_csrf(body)
    token = session.get('_csrf_token', '')
    return f"""<!doctype html><html lang='ar' dir='rtl'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'><meta name='csrf-token' content='{token}'><title>{h(title)}</title><style>{CSS}</style></head><body><div class='phone'>{body}</div><script>
function csrf(){{return document.querySelector('meta[name="csrf-token"]')?.content||''}}

function toggleStatusCircle(id,e){{if(e){{e.preventDefault();e.stopPropagation();}}document.querySelectorAll('.statusReactionCircle').forEach(x=>{{if(x.id!=='statusReact_'+id)x.classList.remove('show')}});let el=document.getElementById('statusReact_'+id); if(el) el.classList.toggle('show')}}
function sendStatusReaction(id,emoji,e){{
  if(e){{e.preventDefault();e.stopPropagation();}}
  fetch('/status/'+id+'/react',{{method:'POST',credentials:'same-origin',headers:{{'Content-Type':'application/x-www-form-urlencoded','X-CSRFToken':csrf(),'Accept':'application/json'}},body:'emoji='+encodeURIComponent(emoji)}})
  .then(r=>r.text()).then(t=>{{try{{return JSON.parse(t)}}catch(e){{return {{ok:false,error:'bad_json',raw:t.slice(0,80)}}}}}})
  .then(j=>{{
    if(j.ok){{
      let b=document.getElementById('statusRound_'+id)||document.querySelector('#statusReact_'+id)?.previousElementSibling;
      if(b)b.textContent=j.emoji||emoji;
      document.getElementById('statusReact_'+id)?.classList.remove('show');
      document.querySelectorAll('#statusReact_'+id+' button').forEach(x=>x.classList.toggle('selected',x.textContent.trim()===(j.emoji||emoji)));
    }}else{{ alert('لم يتم حفظ التفاعل: '+(j.error||'خطأ غير معروف')+(j.detail?' - '+j.detail:'')); }}
  }})
  .catch(()=>alert('لم يتم حفظ التفاعل'))
}}
document.addEventListener('click',function(e){{if(!e.target.closest('.statusReactWrap')) document.querySelectorAll('.statusReactionCircle').forEach(x=>x.classList.remove('show'))}});
function goBackOne(){{ if(history.length>1) history.back(); else location.href='/statuses'; return false; }}
function openStatusReplyMenu(id){{let m=document.getElementById('statusReplyMenu_'+id); if(m)m.style.display='flex'}}
function closeStatusReplyMenu(id){{let m=document.getElementById('statusReplyMenu_'+id); if(m)m.style.display='none'}}
function setStatusReply(parentId,text){{let p=document.getElementById('status_parent_id');let box=document.getElementById('statusReplyHint');let inp=document.querySelector('.statusReplyBar input[name=body]'); if(p)p.value=parentId||''; if(box){{box.style.display='block';box.innerHTML='↩️ رد على الرد: '+(text||'رد')+' <b style="float:left" onclick="clearStatusReply()">×</b>';}} if(inp){{inp.placeholder='رد على الرد...';inp.focus();}} }}
function clearStatusReply(){{let p=document.getElementById('status_parent_id');let box=document.getElementById('statusReplyHint');let inp=document.querySelector('.statusReplyBar input[name=body]'); if(p)p.value=''; if(box)box.style.display='none'; if(inp)inp.placeholder='رد على الحالة...';}}
function reactStatusReply(sid,rid,emoji){{fetch('/status/'+sid+'/reply_msg/'+rid+'/react',{{method:'POST',headers:{{'Content-Type':'application/x-www-form-urlencoded','X-CSRFToken':csrf()}},body:'emoji='+encodeURIComponent(emoji)}}).then(()=>location.reload())}}
function deleteStatusReply(sid,rid){{if(!confirm('حذف الرد للجميع؟'))return; fetch('/status/'+sid+'/reply_msg/'+rid+'/delete',{{method:'POST',headers:{{'X-CSRFToken':csrf()}}}}).then(()=>location.reload())}}
function editStatusReply(sid,rid,oldText){{let v=prompt('تعديل الرد:',oldText||''); if(v===null)return; fetch('/status/'+sid+'/reply_msg/'+rid+'/edit',{{method:'POST',headers:{{'Content-Type':'application/x-www-form-urlencoded','X-CSRFToken':csrf()}},body:'body='+encodeURIComponent(v)}}).then(()=>location.reload())}}
function initStatusReplyTouch(){{document.querySelectorAll('.statusReplyItem[data-rid]').forEach(el=>{{let sx=0,sy=0,timer=null,moved=false;el.addEventListener('touchstart',e=>{{let t=e.touches[0];sx=t.clientX;sy=t.clientY;moved=false;timer=setTimeout(()=>{{if(!moved)openStatusReplyMenu(el.dataset.rid)}},650)}},{{passive:true}});el.addEventListener('touchmove',e=>{{let t=e.touches[0],dx=t.clientX-sx,dy=t.clientY-sy;if(Math.abs(dx)>8||Math.abs(dy)>8)moved=true;if(Math.abs(dx)>55&&Math.abs(dy)<35)el.classList.add('swiping')}},{{passive:true}});el.addEventListener('touchend',e=>{{clearTimeout(timer);if(el.classList.contains('swiping'))setStatusReply(el.dataset.rid,el.dataset.text||'رد');el.classList.remove('swiping')}},{{passive:true}});}})}}
document.addEventListener('DOMContentLoaded',initStatusReplyTouch);
function openMenu(id){{document.getElementById('menu_'+id)?.style.setProperty('display','flex')}}
function closeMenu(id){{document.getElementById('menu_'+id)?.style.setProperty('display','none')}}
function react(id,emoji){{fetch('/message/'+id+'/react',{{method:'POST',headers:{{'Content-Type':'application/x-www-form-urlencoded','X-CSRFToken':csrf()}},body:'emoji='+encodeURIComponent(emoji)}}).then(()=>location.reload())}}
function copyText(t){{navigator.clipboard?.writeText(t||''); alert('تم النسخ')}}
function setReply(id,text){{let r=document.getElementById('reply_to'); if(!r) return; r.value=id; let b=document.getElementById('replybox'); b.style.display='block'; b.innerHTML='↩️ رد على: '+(text||'رسالة')+' <b style="float:left">×</b>'; document.querySelector('.compose input[name=body]')?.focus()}}
function clearReply(){{let r=document.getElementById('reply_to'); if(r) r.value=''; let b=document.getElementById('replybox'); if(b) b.style.display='none'}}
function initMsgTouch(){{
  document.querySelectorAll('.msg[data-id]').forEach(el=>{{let sx=0,sy=0,timer=null,moved=false;
    el.addEventListener('touchstart',e=>{{let t=e.touches[0]; sx=t.clientX; sy=t.clientY; moved=false; timer=setTimeout(()=>{{if(!moved) openMenu(el.dataset.id)}},650)}},{{passive:true}});
    el.addEventListener('touchmove',e=>{{let t=e.touches[0], dx=t.clientX-sx, dy=t.clientY-sy; if(Math.abs(dx)>8||Math.abs(dy)>8)moved=true; if(dx>55 && Math.abs(dy)<35) el.classList.add('swiping')}},{{passive:true}});
    el.addEventListener('touchend',e=>{{clearTimeout(timer); if(el.classList.contains('swiping')){{setReply(el.dataset.id,el.dataset.text||'رسالة')}} el.classList.remove('swiping')}},{{passive:true}});
  }});
}}

let waselRecorder=null, waselChunks=[], waselPeer=null;
function toggleAttachPanel(force){{let p=document.getElementById('attachPanel'); if(p) p.style.display=(force===false?'none':(p.style.display==='block'?'none':'block'))}}
function setFileKind(kind){{
  let f=document.getElementById('file'); if(!f)return;
  f.dataset.kind=kind;
  if(kind==='image')f.accept='image/*'; else if(kind==='video')f.accept='video/*'; else if(kind==='audio')f.accept='audio/*'; else f.accept='';
  f.click();
}}
function clearAttachment(){{
  let f=document.getElementById('file'); if(f) f.value='';
  let n=document.getElementById('attachNotice'); if(n) n.style.display='none';
  let th=document.getElementById('attachThumb'); if(th){{th.removeAttribute('src'); th.style.display='none';}}
  let body=document.querySelector('.compose input[name=body]'); if(body) body.placeholder='اكتب رسالة...';
}}
function showFileName(input){{
  let x=document.getElementById('filePreview'), n=document.getElementById('attachNotice'), th=document.getElementById('attachThumb');
  if(input.files&&input.files[0]){{
    const file=input.files[0];
    const kind=input.dataset.kind||'';
    let label=kind==='image'?'صورة جاهزة للإرسال':kind==='video'?'فيديو جاهز للإرسال':kind==='audio'?'صوت جاهز للإرسال':'ملف جاهز للإرسال';
    let icon=kind==='image'?'🖼️':kind==='video'?'🎬':kind==='audio'?'🎵':'📄';
    if(x) x.textContent=icon+' '+label;
    if(th){{
      th.style.display='grid'; th.classList.remove('videoThumb','fileThumb','audioThumb'); th.removeAttribute('src'); th.textContent='';
      if(file.type.startsWith('image/')){{ th.src=URL.createObjectURL(file); th.style.display='block'; }}
      else if(file.type.startsWith('video/')){{ th.classList.add('videoThumb'); th.textContent='🎬'; }}
      else if(file.type.startsWith('audio/')){{ th.classList.add('audioThumb'); th.textContent='🎵'; }}
      else {{ th.classList.add('fileThumb'); th.textContent='📄'; }}
    }}
    if(n) n.style.display='block';
    let body=document.querySelector('.compose input[name=body]');
    if(body){{body.placeholder='اكتب نصًا مع المرفق...'; body.focus();}}
    toggleAttachPanel(false);
  }}
}}

function pickVoiceFile(peer){{
  waselPeer=peer;
  let f=document.getElementById('voiceFallback');
  if(f) f.click();
}}
async function sendVoiceFile(input){{
  if(!input.files||!input.files[0]||!waselPeer)return;
  const fd=new FormData();
  fd.append('audio',input.files[0],input.files[0].name||('voice_'+Date.now()+'.webm'));
  let caption=document.querySelector('.compose input[name=body]')?.value||'';
  fd.append('body',caption);
  await fetch('/chat_audio/'+waselPeer,{{method:'POST',headers:{{'X-CSRFToken':csrf()}},body:fd}});
  location.reload();
}}
let voiceStream=null, voiceTimer=null, voiceSeconds=0, voiceBlob=null;
function openVoiceRecorder(peer){{
  waselPeer=peer; voiceBlob=null; voiceSeconds=0;
  const m=document.getElementById('voiceModal'); if(m)m.style.display='flex';
  setVoiceTime(0); setVoiceStatus('اضغط بدء التسجيل ثم اضغط إيقاف وإرسال.');
  const send=document.getElementById('voiceSendBtn'); if(send)send.disabled=true;
  const start=document.getElementById('voiceStartBtn'); if(start)start.style.display='inline-block';
  const stop=document.getElementById('voiceStopBtn'); if(stop)stop.style.display='none';
}}
function closeVoiceRecorder(){{
  if(waselRecorder && waselRecorder.state==='recording') cancelVoiceRecording();
  const m=document.getElementById('voiceModal'); if(m)m.style.display='none';
}}
function setVoiceStatus(t){{let e=document.getElementById('voiceStatus'); if(e)e.textContent=t;}}
function setVoiceTime(n){{let e=document.getElementById('voiceTime'); if(e){{let m=String(Math.floor(n/60)).padStart(2,'0'), s=String(n%60).padStart(2,'0'); e.textContent=m+':'+s;}}}}
function voiceTick(){{voiceSeconds++; setVoiceTime(voiceSeconds);}}
async function startVoiceRecording(){{
  const mic=document.getElementById('voiceMic'), start=document.getElementById('voiceStartBtn'), stop=document.getElementById('voiceStopBtn'), send=document.getElementById('voiceSendBtn');
  try{{
    if(!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) throw new Error('NO_MEDIA');
    voiceStream = await navigator.mediaDevices.getUserMedia({{audio:true}});
    waselChunks=[];
    let mime=MediaRecorder.isTypeSupported('audio/webm;codecs=opus')?'audio/webm;codecs=opus':(MediaRecorder.isTypeSupported('audio/ogg;codecs=opus')?'audio/ogg;codecs=opus':'');
    waselRecorder=mime?new MediaRecorder(voiceStream,{{mimeType:mime}}):new MediaRecorder(voiceStream);
    waselRecorder.ondataavailable=e=>{{if(e.data.size>0)waselChunks.push(e.data)}};
    waselRecorder.onstop=()=>{{
      voiceStream?.getTracks().forEach(t=>t.stop()); voiceStream=null; clearInterval(voiceTimer);
      const type=waselRecorder.mimeType||'audio/webm'; voiceBlob=new Blob(waselChunks,{{type:type}});
      if(mic)mic.classList.remove('recording'); if(start)start.style.display='inline-block'; if(stop)stop.style.display='none'; if(send)send.disabled=false;
      setVoiceStatus('تم التسجيل. يمكنك الإرسال أو الإلغاء.');
    }};
    voiceSeconds=0; setVoiceTime(0); voiceTimer=setInterval(voiceTick,1000);
    waselRecorder.start(); if(mic)mic.classList.add('recording'); if(start)start.style.display='none'; if(stop)stop.style.display='inline-block'; if(send)send.disabled=true;
    setVoiceStatus('جاري التسجيل...');
  }}catch(e){{
    setVoiceStatus('تعذر التسجيل المباشر من هذا الرابط. سيتم فتح مسجل الهاتف كحل مضمون.');
    setTimeout(()=>pickVoiceFile(waselPeer), 350);
  }}
}}
function stopVoiceRecording(){{ if(waselRecorder && waselRecorder.state==='recording') waselRecorder.stop(); }}
function cancelVoiceRecording(){{
  try{{ if(waselRecorder && waselRecorder.state==='recording') waselRecorder.stop(); }}catch(e){{}}
  voiceStream?.getTracks().forEach(t=>t.stop()); voiceStream=null; clearInterval(voiceTimer); voiceBlob=null; setVoiceTime(0);
  const mic=document.getElementById('voiceMic'); if(mic)mic.classList.remove('recording'); setVoiceStatus('تم إلغاء التسجيل.');
}}
async function sendVoiceRecording(){{
  if(!voiceBlob||!waselPeer){{setVoiceStatus('لا يوجد تسجيل لإرساله.'); return;}}
  const type=voiceBlob.type||'audio/webm'; const ext=type.includes('ogg')?'ogg':'webm';
  const fd=new FormData(); fd.append('audio',voiceBlob,'voice_'+Date.now()+'.'+ext);
  let caption=document.querySelector('.compose input[name=body]')?.value||''; fd.append('body',caption);
  await fetch('/chat_audio/'+waselPeer,{{method:'POST',headers:{{'X-CSRFToken':csrf()}},body:fd}});
  location.reload();
}}
async function toggleRecording(peer){{
  waselPeer=peer;
  const host=location.hostname;
  const secure=(location.protocol==='https:'||host==='localhost'||host==='127.0.0.1');
  if(!secure){{
    // على روابط الشبكة المحلية 192.168 المتصفح غالبًا يمنع MediaRecorder، لذلك نفتح مسجل الهاتف مباشرة بدون رسالة خطأ.
    pickVoiceFile(peer);
    return;
  }}
  openVoiceRecorder(peer);
}}


function openCountryPicker(id,target){{
  const m=document.getElementById(id); if(!m)return;
  m.dataset.target=target||'country_picker';
  m.style.display='flex';
  const inp=m.querySelector('.countrySearch input');
  if(inp){{inp.value=''; filterCountries(id,''); setTimeout(()=>inp.focus(),120);}}
}}
function closeCountryPicker(id){{const m=document.getElementById(id); if(m)m.style.display='none'}}
function filterCountries(id,q){{
  const m=document.getElementById(id); if(!m)return;
  const v=(q||'').trim().toLowerCase().replace(/\+/g,''); let shown=0;
  m.querySelectorAll('.countryRow').forEach(r=>{{
    const s=(r.dataset.search||'').replace(/\+/g,'');
    const ok=!v || s.includes(v);
    r.style.display=ok?'flex':'none'; if(ok)shown++;
  }});
  let e=m.querySelector('.countryEmpty');
  if(!shown){{if(!e){{e=document.createElement('div');e.className='countryEmpty';e.textContent='لا توجد دولة بهذا البحث';m.querySelector('.countryList')?.appendChild(e)}}}}
  else if(e)e.remove();
}}
function selectCountry(btn){{
  const label=btn.dataset.label||'';
  const target=btn.dataset.target || btn.closest('.countryModal')?.dataset.target || 'country_picker';
  const hidden=document.getElementById(target); if(hidden)hidden.value=label;
  const lab=document.getElementById(target+'_label'); if(lab)lab.textContent=label;
  const modal=btn.closest('.countryModal'); if(modal)modal.style.display='none';
  const phone=document.querySelector('input[name=phone], input[name=identifier]'); if(phone)phone.focus();
}}


function clearAuthErrors(form){{
  form.querySelectorAll('.hasError').forEach(x=>x.classList.remove('hasError','shake'));
  form.querySelectorAll('.fieldHint').forEach(x=>{{x.textContent='';x.style.display='none'}});
  const box=form.querySelector('.authErrorBox'); if(box){{box.textContent='';box.classList.remove('show')}}
}}
function showAuthError(form,msg,field){{
  const box=form.querySelector('.authErrorBox');
  if(box){{box.textContent=msg||'حدث خطأ';box.classList.add('show')}}
  let el=null;
  if(field) el=form.querySelector(`[name="${{field}}"]`);
  if(!el && field==='country_picker') el=form.querySelector('#country_picker_label');
  if(el){{
    const wrap=el.closest('.input')||el.closest('.countryPick')||el.parentElement;
    if(wrap){{wrap.classList.add('hasError','shake'); setTimeout(()=>wrap.classList.remove('shake'),350)}}
    let hint=wrap?wrap.querySelector('.fieldHint'):null;
    if(!hint && wrap){{hint=document.createElement('div'); hint.className='fieldHint'; wrap.appendChild(hint)}}
    if(hint){{hint.textContent=msg||'تحقق من هذا الحقل';hint.style.display='block'}}
    if(el.focus) setTimeout(()=>el.focus(),80);
  }}
}}
function initAuthAjax(){{
  document.querySelectorAll('form.authAjax').forEach(form=>{{
    form.addEventListener('submit',async e=>{{
      e.preventDefault(); clearAuthErrors(form);
      const btn=form.querySelector('button[type=submit],button:not([type])');
      const old=btn?btn.textContent:'';
      if(btn){{btn.textContent='جاري التحقق...';btn.disabled=true}}
      form.classList.add('authSaving');
      try{{
        const fd=new FormData(form);
        const res=await fetch(form.action||location.href,{{method:'POST',headers:{{'X-Requested-With':'XMLHttpRequest','X-CSRFToken':csrf()}},body:fd,credentials:'same-origin'}});
        let data={{}}; try{{data=await res.json()}}catch(_){{data={{ok:false,message:'تعذر قراءة رد الخادم'}}}}
        if(data.ok){{ location.href=data.redirect||'/chats'; return; }}
        showAuthError(form,data.message||'توجد مشكلة في البيانات',data.field||'');
      }}catch(err){{ showAuthError(form,'تعذر الاتصال بالخادم. حاول مرة أخرى.',''); }}
      finally{{ if(btn){{btn.textContent=old;btn.disabled=false}} form.classList.remove('authSaving'); }}
    }});
  }});
}}

document.addEventListener('DOMContentLoaded',()=>{{initMsgTouch(); initAuthAjax(); document.querySelectorAll('.countryModal').forEach(m=>m.addEventListener('click',e=>{{if(e.target===m)m.style.display='none'}}));}});
</script></body></html>"""


def nav(active):
    uid = session.get('user_id')
    n_count = unread_notifications_count(uid) if uid else 0
    badge = f"<span class='badge' style='position:absolute;margin-top:-8px;margin-right:-10px'>{n_count}</span>" if n_count else ''
    items = [("chats","💬","المحادثات",''),("statuses","◎","الحالات",''),("calls","📞","المكالمات",''),("notifications","🔔","الإشعارات",badge),("me","👤","حسابي",'')]
    return "<div class='tabs'>" + "".join([f"<a class='{ 'active' if active==k else ''}' href='/{k}' style='position:relative'><div>{i}{b}</div><div>{t}</div></a>" for k,i,t,b in items]) + "</div>"


@app.route('/')
def home():
    return redirect('/chats' if session.get('user_id') else '/login')



def wants_json():
    return request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.accept_mimetypes.best == 'application/json'


def auth_fail(kind, message, field='', status=400):
    if wants_json():
        return jsonify({'ok': False, 'message': message, 'field': field}), status
    return page(auth_html(kind, message))


def auth_success(url):
    if wants_json():
        return jsonify({'ok': True, 'redirect': url})
    return redirect(url)


@app.route('/register', methods=['GET','POST'])
def register():
    if request.method == 'POST':
        name = request.form.get('name','').strip()
        email = (request.form.get('email','').strip() or '').lower()
        country_pick = request.form.get('country_picker','').strip() or request.form.get('country','').strip()
        country_info = parse_country_value(country_pick)
        country = country_info['name']
        phone_country_code = country_info['code']
        phone_raw = request.form.get('phone','').strip()
        phone = None
        phone_full = None
        if phone_raw:
            phone, phone_full, country_info, phone_err = normalize_phone_by_country(phone_raw, phone_country_code)
            country = country_info['name']
            phone_country_code = country_info['code']
            if phone_err:
                return auth_fail('register', phone_err, 'phone')
        gender = request.form.get('gender','').strip() or None
        birth_date = request.form.get('birth_date','').strip() or None
        password = request.form.get('password','')
        password2 = request.form.get('password2','')
        if not email or '@' not in email or '.' not in email:
            return auth_fail('register', 'البريد الإلكتروني الصحيح مطلوب للتحقق من الحساب', 'email')
        if not name or not password:
            return auth_fail('register', 'أدخل الاسم والبريد وكلمة المرور', 'name')
        if len(password) < 8:
            return auth_fail('register', 'كلمة المرور يجب أن تكون 8 أحرف على الأقل', 'password')
        if password != password2:
            return auth_fail('register', 'تأكيد كلمة المرور غير مطابق', 'password2')
        if birth_date:
            age = age_from_birth(birth_date)
            if age is None or age < 18:
                return auth_fail('register', 'العمر يجب أن يكون 18 سنة أو أكثر', 'birth_date')
        username_base = ''.join(ch for ch in name.lower().replace(' ','_') if ch.isalnum() or ch=='_')[:20] or 'wasel'
        username = '@' + username_base
        i = 1
        while db().execute('SELECT id FROM users WHERE username=?', (username,)).fetchone():
            i += 1
            username = '@' + username_base + str(i)
        try:
            cur = db().execute("""INSERT INTO users(name,username,email,phone,phone_country_code,phone_full,password_hash,gender,birth_date,country,is_verified,created_at)
                                VALUES(?,?,?,?,?,?,?,?,?,?,0,?)""", (name, username, email, phone, phone_country_code, phone_full, generate_password_hash(password), gender, birth_date, country, now()))
            db().commit()
            uid = cur.lastrowid
            code, ok, info = create_email_verify_code(uid, email)
            session.clear(); session['_csrf_token'] = secrets.token_urlsafe(32)
            session['pending_verify_user_id'] = uid
            session['pending_verify_email'] = email
            if not ok:
                session['dev_verify_code'] = code
                print('رمز تحقق البريد للتجربة:', code, 'سبب عدم الإرسال:', info)
            return auth_success('/verify_email')
        except sqlite3.IntegrityError:
            return auth_fail('register', 'البريد أو الرقم مستخدم من قبل', 'email')
    return page(auth_html('register'))


@app.route('/login', methods=['GET','POST'])
def login():
    if request.method == 'POST':
        ident = request.form.get('ident','').strip().lower()
        password = request.form.get('password','')
        ip = request.headers.get('X-Forwarded-For', request.remote_addr or 'local').split(',')[0].strip()
        rec = LOGIN_ATTEMPTS.get(ip, {'count': 0, 'until': 0})
        if rec.get('until', 0) > time.time():
            return auth_fail('login', 'محاولات كثيرة. انتظر قليلًا ثم حاول من جديد', 'ident', 429)
        lookup_vals = phone_lookup_values(ident)
        placeholders = ','.join(['?'] * len(lookup_vals)) if lookup_vals else '?'
        params = lookup_vals or [ident]
        u = db().execute(f"SELECT * FROM users WHERE lower(email) IN ({placeholders}) OR phone IN ({placeholders}) OR phone_full IN ({placeholders})", params + params + params).fetchone()
        if u and check_password_hash(u['password_hash'], password):
            if u['email'] and ('is_verified' in u.keys()) and not u['is_verified']:
                code, ok, info = create_email_verify_code(u['id'], u['email'])
                session.clear(); session['_csrf_token'] = secrets.token_urlsafe(32)
                session['pending_verify_user_id'] = u['id']
                session['pending_verify_email'] = u['email']
                if not ok:
                    session['dev_verify_code'] = code
                    print('رمز تحقق البريد للتجربة:', code, 'سبب عدم الإرسال:', info)
                return auth_success('/verify_email')
            LOGIN_ATTEMPTS.pop(ip, None)
            session.clear(); session['_csrf_token'] = secrets.token_urlsafe(32)
            session['user_id'] = u['id']; db().execute("UPDATE users SET online=1, last_login_at=? WHERE id=?", (now(), u['id'])); db().commit()
            return auth_success('/chats')
        rec['count'] = rec.get('count', 0) + 1
        if rec['count'] >= 7:
            rec['until'] = time.time() + 600
        LOGIN_ATTEMPTS[ip] = rec
        return auth_fail('login', 'بيانات الدخول غير صحيحة', 'password')
    return page(auth_html('login'))


@app.route('/verify_email', methods=['GET','POST'])
def verify_email():
    uid = verify_pending_user_id()
    if not uid:
        return redirect('/login')
    u = db().execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone()
    if not u:
        session.clear(); return redirect('/register')
    msg = ''
    if request.method == 'POST':
        code = request.form.get('code','').strip()
        r = db().execute("""SELECT * FROM email_verify_codes
                           WHERE user_id=? AND code=? AND used=0
                           ORDER BY id DESC LIMIT 1""", (uid, code)).fetchone()
        if not r or r['expires_at'] < now():
            msg = 'الرمز غير صحيح أو منتهي. أعد الإرسال وجرب مرة ثانية.'
        else:
            db().execute("UPDATE email_verify_codes SET used=1 WHERE id=?", (r['id'],))
            db().execute("UPDATE users SET is_verified=1, email_verified_at=? WHERE id=?", (now(), uid))
            db().execute("UPDATE users SET online=1, last_login_at=? WHERE id=?", (now(), uid))
            db().commit()
            session.clear(); session['_csrf_token'] = secrets.token_urlsafe(32)
            session['user_id'] = uid
            return redirect('/chats')
    dev = session.get('dev_verify_code')
    dev_box = f"<div class='card'><b>رمز التجربة:</b> <span class='badge'>{h(dev)}</span><br><span class='muted'>ظهر لأن SMTP غير مضبوط أو فشل الإرسال. عند ضبط EMAIL_USER و EMAIL_PASS سيصل الرمز للبريد.</span></div>" if dev else ''
    email = h(u['email'])
    return page(f"""
    <div class='top'><a class='icon' href='/login'>‹</a><b>تحقق البريد</b></div>
    <form class='card' method='post'>
      <p class='muted'>أرسلنا رمز تحقق إلى: <b>{email}</b></p>
      <p class='danger'>{h(msg)}</p>
      <div class='input'><input name='code' inputmode='numeric' maxlength='6' placeholder='رمز التحقق من 6 أرقام'></div>
      <button class='btn' style='width:100%'>تأكيد وتسجيل الدخول</button>
    </form>
    <div class='card'><a class='btn gray' href='/resend_verify_email'>إعادة إرسال الرمز</a></div>
    {dev_box}
    """)


@app.route('/resend_verify_email')
def resend_verify_email():
    uid = verify_pending_user_id()
    if not uid:
        return redirect('/login')
    u = db().execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone()
    if not u or not u['email']:
        return redirect('/login')
    code, ok, info = create_email_verify_code(uid, u['email'])
    if not ok:
        session['dev_verify_code'] = code
        print('رمز تحقق البريد للتجربة:', code, 'سبب عدم الإرسال:', info)
    else:
        session.pop('dev_verify_code', None)
    return redirect('/verify_email')


def auth_html(kind, err=''):
    isreg = kind == 'register'
    country_default = country_display(COUNTRY_BY_CODE['+967'])
    fields = "" if not isreg else f"""
    <div class='input'><input name='name' placeholder='الاسم الكامل'></div>
    <div class='grid'><div class='input'><input name='email' placeholder='البريد'></div><div class='input'><input name='phone' inputmode='numeric' pattern='[0-9]*' placeholder='اكتب الرقم بدون رمز الدولة'></div></div>
    <div class='grid'>
        <div class='input'><label class='muted' style='display:block;margin-bottom:6px'>🌍 الدولة</label>{country_picker_html('country_picker', country_default, 'countryPickerRegister')}</div>
        <div class='input'><label class='muted' style='display:block;margin-bottom:6px'>📅 تاريخ الميلاد</label><input name='birth_date' type='date'></div>
    </div>
    <div class='input'><select name='gender' style='width:100%;border:1px solid #1b2e49;background:#0b1728;color:#eaf2ff;border-radius:18px;padding:14px'><option value=''>الجنس</option><option>ذكر</option><option>أنثى</option></select></div>
    """
    ident = "" if isreg else "<div class='input'><input name='ident' placeholder='البريد أو رقم الهاتف'></div>"
    confirm = "<div class='input'><input type='password' name='password2' placeholder='تأكيد كلمة المرور'></div>" if isreg else ""
    forgot = "" if isreg else "<p class='muted'><a href='/forgot'>نسيت كلمة المرور؟</a></p>"
    return f"<div class='auth'><div class='title'>واصل شات</div><div class='muted'>المرحلة 24: تحقق ذكي بدون تحديث الصفحة</div><form class='card authAjax' method='post' novalidate><div class='authErrorBox {'show' if err else ''}'>{h(err) if err else ''}</div>{fields}{ident}<div class='input'><input type='password' name='password' placeholder='كلمة المرور'></div>{confirm}<button class='btn' style='width:100%'>{'إنشاء حساب' if isreg else 'دخول'}</button>{forgot}<p class='muted'>{'لديك حساب؟ <a href=/login>دخول</a>' if isreg else 'ليس لديك حساب؟ <a href=/register>إنشاء حساب</a>'}</p></form></div>"


@app.route('/forgot', methods=['GET','POST'])
def forgot():
    msg = ''
    code_show = ''
    if request.method == 'POST':
        ident = request.form.get('ident','').strip()
        lookup_vals = phone_lookup_values(ident)
        placeholders = ','.join(['?'] * len(lookup_vals)) if lookup_vals else '?'
        params = lookup_vals or [ident]
        u = db().execute(f"SELECT * FROM users WHERE lower(email)=? OR phone IN ({placeholders}) OR phone_full IN ({placeholders})", [ident.lower()] + params + params).fetchone()
        if u:
            code = make_code()
            exp = (datetime.now() + timedelta(minutes=10)).strftime('%Y-%m-%d %H:%M:%S')
            db().execute("INSERT INTO reset_codes(ident,code,expires_at,created_at) VALUES(?,?,?,?)", (ident, code, exp, now()))
            db().commit()
            if u['email']:
                ok, info = send_mail(u['email'], 'رمز استعادة كلمة مرور واصل شات', f'رمز استعادة كلمة المرور هو: {code}\nالرمز صالح لمدة 10 دقائق.')
                if ok:
                    msg = 'تم إرسال رمز استعادة كلمة المرور إلى البريد'
                else:
                    code_show = f"<div class='card'><b>رمز التجربة:</b> <span class='badge'>{code}</span><br><span class='muted'>SMTP غير مضبوط أو فشل الإرسال.</span></div>"
                    msg = 'تم إنشاء الرمز، لكن البريد لم يُرسل'
            else:
                code_show = f"<div class='card'><b>رمز التجربة:</b> <span class='badge'>{code}</span></div>"
                msg = 'تم إنشاء رمز استعادة كلمة المرور'
        else:
            msg = 'لا يوجد حساب بهذا البريد أو الرقم'
    return page(f"<div class='top'><a class='icon' href='/login'>‹</a><b>استعادة كلمة المرور</b></div><form class='card' method='post'><p class='muted'>{msg}</p><div class='input'><input name='ident' placeholder='البريد أو رقم الهاتف'></div><button class='btn'>إرسال الرمز</button></form>{code_show}<div class='card'><a class='btn' href='/reset'>إدخال الرمز وتغيير كلمة المرور</a></div>")

@app.route('/reset', methods=['GET','POST'])
def reset_password():
    msg=''
    if request.method=='POST':
        ident=request.form.get('ident','').strip(); code=request.form.get('code','').strip(); password=request.form.get('password',''); password2=request.form.get('password2','')
        if password != password2:
            msg='كلمة المرور غير متطابقة'
        else:
            r=db().execute("SELECT * FROM reset_codes WHERE ident=? AND code=? AND used=0 ORDER BY id DESC LIMIT 1", (ident, code)).fetchone()
            if not r or r['expires_at'] < now():
                msg='الرمز غير صحيح أو منتهي'
            else:
                vals = phone_lookup_values(ident)
                placeholders = ','.join(['?'] * len(vals)) if vals else '?'
                params = vals or [ident]
                db().execute(f"UPDATE users SET password_hash=? WHERE lower(email)=? OR phone IN ({placeholders}) OR phone_full IN ({placeholders})", [generate_password_hash(password), ident.lower()] + params + params)
                db().execute("UPDATE reset_codes SET used=1 WHERE id=?", (r['id'],))
                db().commit(); msg='تم تغيير كلمة المرور. يمكنك تسجيل الدخول الآن.'
    return page(f"<div class='top'><a class='icon' href='/login'>‹</a><b>تعيين كلمة مرور جديدة</b></div><form class='card' method='post'><p class='muted'>{msg}</p><div class='input'><input name='ident' placeholder='البريد أو رقم الهاتف'></div><div class='input'><input name='code' placeholder='رمز التحقق'></div><div class='input'><input type='password' name='password' placeholder='كلمة المرور الجديدة'></div><div class='input'><input type='password' name='password2' placeholder='تأكيد كلمة المرور'></div><button class='btn'>حفظ</button></form>")

@app.route('/logout', methods=['GET','POST'])
@login_required
def logout():
    u = current_user()
    if request.method == 'POST':
        uid = session.get('user_id')
        if uid:
            db().execute("UPDATE users SET online=0, last_logout_at=? WHERE id=?", (now(), uid))
            db().commit()
        session.clear()
        return redirect('/login')
    avatar = avatar_url(u)
    return page(f"""
    <div class='top'><a class='icon' href='/me'>‹</a><b>تسجيل الخروج</b></div>
    <div class='card' style='text-align:center'>
      <img class='avatar' style='width:86px;height:86px' src='{avatar}'>
      <h2>{h(u['name'])}</h2>
      <p class='muted'>هل تريد الخروج من هذا الحساب؟ سيتم إيقاف حالة الاتصال ومسح الجلسة من هذا الجهاز فقط.</p>
      <form method='post'>
        <button class='btn' style='background:#ef4444;width:100%;margin-bottom:10px'>نعم، تسجيل الخروج</button>
      </form>
      <a class='btn gray' style='display:block' href='/me'>إلغاء والرجوع</a>
    </div>
    <div class='card'><b>معلومة</b><p class='muted'>الخروج لا يحذف الحساب ولا المحادثات ولا الملفات. فقط يغلق الجلسة الحالية.</p></div>
    """)


@app.route('/chats')
@login_required
def chats():
    u = current_user()
    if 'service_chat_enabled' in u.keys() and not u['service_chat_enabled']:
        return page("<div class='top'><a class='icon' href='/services'>‹</a><b>المحادثات متوقفة</b></div><div class='card'>خدمة المحادثات متوقفة من الإعدادات. <a class='btn' href='/services'>تشغيلها الآن</a></div>")
    q = request.args.get('q','').strip()
    view = request.args.get('view','all').strip()

    # تظهر فقط جهات الاتصال التي أضافها المستخدم، بدون عرض كل المستخدمين عشوائياً.
    sql = """SELECT users.*, contacts.pinned, contacts.archived, contacts.muted, contacts.blocked, contacts.note, contacts.nickname
             FROM contacts
             JOIN users ON users.id=contacts.contact_id
             WHERE contacts.user_id=?"""
    params = [u['id']]
    if q:
        sql += " AND (users.name LIKE ? OR users.username LIKE ? OR users.email LIKE ? OR users.phone LIKE ?)"
        like = '%' + q + '%'
        params += [like, like, like, like]
    sql += " ORDER BY COALESCE(contacts.pinned,0) DESC, contacts.id DESC"
    users = db().execute(sql, params).fetchall()

    rows = []
    for x in users:
        if x['archived']:
            continue
        last = db().execute("SELECT * FROM messages WHERE ((sender_id=? AND receiver_id=?) OR (sender_id=? AND receiver_id=?)) AND deleted_for_all=0 ORDER BY id DESC LIMIT 1", (u['id'], x['id'], x['id'], u['id'])).fetchone()
        unread = db().execute("SELECT COUNT(*) c FROM messages WHERE sender_id=? AND receiver_id=? AND is_read=0 AND deleted_for_receiver=0 AND deleted_for_all=0", (x['id'], u['id'])).fetchone()['c']
        if view == 'unread' and not unread:
            continue
        name = h(x['nickname'] or x['name'])
        mute_icon = "<span class='chatMute'>🔕</span>" if x['muted'] else ''
        blocked_icon = "<span class='chatMute'>🛑</span>" if x['blocked'] else ''
        badge = f"<span class='chatUnread'>{unread}</span>" if unread else ''
        if last:
            raw_last = last['body'] if last['body'] else '📎 ملف مرفق'
            last_text = h(raw_last)
            last_time = last['created_at'][11:16] if last['created_at'] else ''
        else:
            last_text = h(x['note'] or 'اضغط لبدء المحادثة')
            last_time = ''
        online = "<span class='onlineDot'></span>" if x['online'] else ''
        rows.append(f"""
        <a class='chatRowNew' href='/chat/{x['id']}'>
            <div class='chatAvatarWrap'><img class='chatAvatar' src='{avatar_url(x)}'>{online}</div>
            <div class='chatMainNew'>
                <div class='chatNameLine'><b>{blocked_icon}{name}</b></div>
                <div class='chatLastLine'>{last_text}</div>
            </div>
            <div class='chatSideNew'><span class='chatTimeNew'>{last_time}</span>{badge}{mute_icon}</div>
        </a>
        """)
    empty = "<div class='card'>لا توجد محادثات. اضغط زر + لإضافة صديق جديد.</div>"
    all_active = 'active' if view != 'unread' else ''
    unread_active = 'active' if view == 'unread' else ''
    body = f"""
    <div class='chatHome'>
        <div class='chatHomeTop'>
            <a class='chatTopIcon' href='/me'>☰</a>
            <div class='chatLogo'>واصل</div>
            <button class='chatTopIcon searchOnlyBtn' type='button' onclick="toggleChatSearch()">⌕</button>
        </div>
        <form id='chatSearchBox' class='chatSearchCollapsed' method='get'>
            <input name='q' value='{h(q)}' placeholder='اكتب للبحث داخل المحادثات'>
            <input type='hidden' name='view' value='{h(view)}'>
        </form>
        <div class='chatFilterBar'>
            <a class='{all_active}' href='/chats'>الكل</a>
            <a class='{unread_active}' href='/chats?view=unread'>غير مقروءة</a>
        </div>
        <div class='chatRowsBox'>{''.join(rows) or empty}</div>
        <a class='chatFab' href='/new_contact'>＋<small>محادثة جديدة</small></a>
    </div>
    <script>
    function toggleChatSearch(){{
        const box=document.getElementById('chatSearchBox');
        if(!box)return;
        box.classList.toggle('show');
        const inp=box.querySelector('input[name=q]');
        if(box.classList.contains('show') && inp) setTimeout(()=>inp.focus(),80);
    }}
    </script>
    {nav('chats')}
    """
    return page(body)

@app.route('/archived')
@login_required
def archived():
    u = current_user()
    users = db().execute("""SELECT users.*, contacts.nickname, contacts.pinned, contacts.muted, contacts.blocked
                            FROM contacts JOIN users ON users.id=contacts.contact_id
                            WHERE contacts.user_id=? AND contacts.archived=1
                            ORDER BY contacts.id DESC""", (u['id'],)).fetchall()
    rows = ''.join([f"<a class='chatitem' href='/chat/{x['id']}'><img class='avatar' src='{avatar_url(x)}'><div class='grow'><div class='name'>{x['nickname'] or x['name']}</div><div class='last'>محادثة مؤرشفة</div></div></a>" for x in users])
    return page(f"<div class='top'><a class='icon' href='/chats'>‹</a><b>الأرشيف</b></div><div class='list'>{rows or '<div class=card>لا توجد محادثات مؤرشفة</div>'}</div>")


def avatar_url(u):
    return f"/uploads/{u['avatar']}" if u['avatar'] else "https://ui-avatars.com/api/?background=123&color=fff&name=" + str(u['name']).replace(' ','+')


def is_my_contact(user_id, other_id):
    return db().execute("SELECT id FROM contacts WHERE user_id=? AND contact_id=?", (user_id, other_id)).fetchone() is not None


def can_view_status(st, viewer_id):
    if st['user_id'] == viewer_id:
        return True
    privacy = st['privacy'] if 'privacy' in st.keys() and st['privacy'] else 'public'
    if privacy == 'private':
        return False
    if privacy == 'contacts':
        return is_my_contact(st['user_id'], viewer_id) or is_my_contact(viewer_id, st['user_id'])
    return True


def status_media_html(st, preview=False):
    if not st['file_name']:
        return ''
    url = '/uploads/' + st['file_name']
    ext = st['file_name'].rsplit('.',1)[-1].lower()
    maxh = '420px' if preview else '70vh'
    if ext in ['png','jpg','jpeg','gif','webp']:
        fit = 'cover' if preview else 'contain'
        return f"<img src='{url}' style='width:100%;max-height:{maxh};object-fit:{fit};border-radius:18px;margin-top:10px;background:#020814'>"
    if ext in ['mp4','webm']:
        auto = '' if preview else 'autoplay'
        return f"<video controls {auto} src='{url}' style='width:100%;max-height:{maxh};border-radius:18px;margin-top:10px;background:#020814'></video>"
    if ext in ['mp3','wav','ogg']:
        auto = '' if preview else 'autoplay'
        return f"<audio controls {auto} src='{url}' style='width:100%;margin-top:10px'></audio>"
    return f"<a class='filechip' href='{url}'>📎 فتح الملف</a>"



def normalize_identifier(value, country_value=None):
    raw = (value or '').strip().lower()
    if not raw:
        return '', 'unknown'
    if '@' in raw and '.' in raw:
        return raw, 'email'
    if country_value:
        local, full, c, err = normalize_phone_by_country(raw, country_value)
        if local and full:
            return full, 'phone'
    digits = clean_digits(raw)
    if digits:
        # إذا كتب المستخدم رقماً كاملاً برمز دولة، نحفظه بصيغة +codeLocal
        for c in COUNTRIES:
            code = clean_digits(c['code'])
            if digits.startswith(code) and len(digits) > len(code):
                return c['code'] + digits[len(code):], 'phone'
        return digits, 'phone'
    return raw, 'username'


def find_platform_user_by_identifier(identifier, identifier_type=None):
    if not identifier:
        return None
    vals = phone_lookup_values(identifier)
    if identifier_type == 'email':
        return db().execute("SELECT * FROM users WHERE lower(email)=?", (identifier.lower(),)).fetchone()
    if identifier_type == 'phone':
        placeholders = ','.join(['?'] * len(vals)) if vals else '?'
        params = vals or [identifier]
        return db().execute(f"SELECT * FROM users WHERE phone IN ({placeholders}) OR phone_full IN ({placeholders})", params + params).fetchone()
    placeholders = ','.join(['?'] * len(vals)) if vals else '?'
    params = vals or [identifier]
    return db().execute(f"SELECT * FROM users WHERE lower(email)=? OR lower(username)=? OR phone IN ({placeholders}) OR phone_full IN ({placeholders})", [identifier.lower(), identifier.lower()] + params + params).fetchone()


def link_address_book_row(row_id, linked_user_id):
    db().execute("UPDATE address_book SET linked_user_id=?, updated_at=? WHERE id=?", (linked_user_id, now(), row_id))

@app.route('/new_contact', methods=['GET','POST'])
@login_required
def new_contact():
    """إنشاء جديد مثل واتساب:
    - يعرض الأشخاص المحفوظين عندي إذا كانوا داخل المنصة.
    - البحث بالاسم يظهر المحفوظين فقط.
    - البحث بالرقم/البريد يبحث في المحفوظين وفي حساب مطابق داخل المنصة.
    - إضافة جديد باسم + بريد_رقم + دولة في إطار واحد.
    """
    u = current_user()
    q = (request.args.get('q') or '').strip()
    q_norm, q_type = normalize_identifier(q)
    msg = ''
    cards = []

    # الأشخاص المحفوظين عندي والمرتبطين بحساب داخل المنصة
    if q:
        if q_type in ('email', 'phone'):
            saved_rows = db().execute("""
                SELECT ab.*, users.name real_name, users.username, users.avatar, users.country user_country, users.id platform_id
                FROM address_book ab
                LEFT JOIN users ON users.id=ab.linked_user_id
                WHERE ab.user_id=? AND (ab.saved_name LIKE ? OR ab.identifier LIKE ?)
                ORDER BY ab.updated_at DESC, ab.id DESC
            """, (u['id'], '%' + q + '%', '%' + q_norm + '%')).fetchall()
        else:
            saved_rows = db().execute("""
                SELECT ab.*, users.name real_name, users.username, users.avatar, users.country user_country, users.id platform_id
                FROM address_book ab
                LEFT JOIN users ON users.id=ab.linked_user_id
                WHERE ab.user_id=? AND ab.saved_name LIKE ?
                ORDER BY ab.updated_at DESC, ab.id DESC
            """, (u['id'], '%' + q + '%')).fetchall()
    else:
        saved_rows = db().execute("""
            SELECT ab.*, users.name real_name, users.username, users.avatar, users.country user_country, users.id platform_id
            FROM address_book ab
            JOIN users ON users.id=ab.linked_user_id
            WHERE ab.user_id=?
            ORDER BY ab.updated_at DESC, ab.id DESC
        """, (u['id'],)).fetchall()

    seen_ids = set()
    for r in saved_rows:
        linked_id = r['linked_user_id']
        # حاول ربط المحفوظ إذا لم يكن مربوطاً
        if not linked_id:
            found = find_platform_user_by_identifier(r['identifier'], r['identifier_type'])
            if found and found['id'] != u['id']:
                linked_id = found['id']
                link_address_book_row(r['id'], linked_id)
                db().commit()
                r = db().execute("""
                    SELECT ab.*, users.name real_name, users.username, users.avatar, users.country user_country, users.id platform_id
                    FROM address_book ab LEFT JOIN users ON users.id=ab.linked_user_id WHERE ab.id=?
                """, (r['id'],)).fetchone()
        if linked_id and linked_id != u['id']:
            seen_ids.add(linked_id)
            saved_name = h(r['saved_name'])
            real_name = h(r['real_name'] or 'حساب واصل')
            country = h(r['country'] or r['user_country'] or 'غير محددة')
            username = h(r['username'] or '')
            avatar = f"/uploads/{r['avatar']}" if r['avatar'] else "https://ui-avatars.com/api/?background=123&color=fff&name=" + str(r['real_name'] or r['saved_name']).replace(' ','+')
            already = db().execute("SELECT id FROM contacts WHERE user_id=? AND contact_id=?", (u['id'], linked_id)).fetchone()
            label = 'مراسلة' if already else 'إضافة ومراسلة'
            cards.append(f"""
            <a class='chatitem' href='/address_book/{r['id']}/chat'>
                <img class='avatar' src='{avatar}'>
                <div class='grow'>
                    <div class='name'>{saved_name}</div>
                    <div class='last'>{real_name} · {username} · {country}</div>
                </div>
                <span class='badge'>{label}</span>
            </a>
            """)

    # إذا البحث ببريد/رقم ولم يكن محفوظاً، أظهر الحساب المطابق فقط مع زر حفظ ومراسلة
    external_card = ''
    if q and q_type in ('email', 'phone'):
        found = find_platform_user_by_identifier(q_norm, q_type)
        if found and found['id'] != u['id'] and found['id'] not in seen_ids:
            country = h(found['country'] or 'غير محددة')
            external_card = f"""
            <div class='card'>
                <div class='profileRow'>
                    <img class='avatar' src='{avatar_url(found)}'>
                    <div class='grow'>
                        <div class='name'>{h(found['name'])}</div>
                        <div class='last'>{h(found['username'] or '')} · الدولة: {country}</div>
                        <div class='muted'>هذا الحساب مطابق للرقم/البريد الذي بحثت عنه. لن يظهر رقمه أو بريده.</div>
                    </div>
                </div>
                <form method='post' action='/address_book/add' style='margin-top:12px'>
                    <input type='hidden' name='saved_name' value='{h(found['name'])}'>
                    <input type='hidden' name='identifier' value='{h(q_norm)}'>
                    <input type='hidden' name='country' value='{country}'>
                    <button class='btn' style='width:100%'>➕ حفظ ومراسلة</button>
                </form>
            </div>
            """
        elif q and not cards:
            msg = 'لا يوجد شخص محفوظ أو حساب مطابق بهذا البحث.'
    elif q and not cards:
        msg = 'البحث بالاسم يظهر الأشخاص المحفوظين عندك فقط. للبحث عن حساب غير محفوظ أدخل رقم الهاتف أو البريد كاملًا.'

    rows_html = ''.join(cards) or ''
    if not rows_html and not q:
        rows_html = "<div class='card'>لا توجد جهات محفوظة مرتبطة بالمنصة. اضغط إضافة جديد واحفظ رقم أو بريد الشخص.</div>"

    body = f"""
    <div class='top'><a href='/chats' class='icon'>‹</a><b>إنشاء جديد</b></div>
    <form class='search' method='get'>
        <input name='q' value='{h(q)}' placeholder='بحث باسم محفوظ، أو رقم/بريد'>
    </form>
    {'<div class=card><p class=danger>'+h(msg)+'</p></div>' if msg else ''}
    <div class='card'>
        <a class='btn' style='width:100%;display:block;text-align:center' href='/address_book/add'>➕ إضافة جديد</a>
        <p class='muted'>مثل واتساب: تظهر هنا فقط الأسماء التي حفظتها أنت ولديها حساب في واصل. البحث بالاسم داخل محفوظاتك فقط، والبحث برقم/بريد يظهر الحساب المطابق حتى لو لم تحفظه بعد.</p>
    </div>
    {external_card}
    <div class='list'>{rows_html}</div>
    """
    return page(body)


@app.route('/address_book/add', methods=['GET','POST'])
@login_required
def address_book_add():
    u = current_user()
    msg = ''
    if request.method == 'POST':
        saved_name = (request.form.get('saved_name') or '').strip()
        identifier_raw = (request.form.get('identifier') or '').strip()
        country_pick = (request.form.get('country_picker') or request.form.get('country') or '').strip()
        country_info = parse_country_value(country_pick)
        country = country_info['name']
        country_code = country_info['code']
        if '@' in identifier_raw and '.' in identifier_raw:
            identifier, identifier_type = normalize_identifier(identifier_raw)
            phone_full = None
        else:
            local, full, c, phone_err = normalize_phone_by_country(identifier_raw, country_code)
            if phone_err:
                identifier, identifier_type, phone_full = '', 'phone', None
                msg = phone_err
            else:
                identifier, identifier_type, phone_full = full, 'phone', full
                country, country_code = c['name'], c['code']
        if not msg:
            if not saved_name or not identifier:
                msg = 'أدخل الاسم ورقم الهاتف أو البريد.'
            else:
                linked = find_platform_user_by_identifier(identifier, identifier_type)
                linked_id = linked['id'] if linked and linked['id'] != u['id'] else None
                try:
                    db().execute("""
                        INSERT INTO address_book(user_id,saved_name,identifier,identifier_type,country,country_code,phone_full,linked_user_id,created_at,updated_at)
                        VALUES(?,?,?,?,?,?,?,?,?,?)
                    """, (u['id'], saved_name, identifier, identifier_type, country, country_code, phone_full, linked_id, now(), now()))
                except sqlite3.IntegrityError:
                    db().execute("""
                        UPDATE address_book SET saved_name=?, identifier_type=?, country=?, country_code=?, phone_full=?, linked_user_id=?, updated_at=?
                        WHERE user_id=? AND identifier=?
                    """, (saved_name, identifier_type, country, country_code, phone_full, linked_id, now(), u['id'], identifier))
                if linked_id:
                    db().execute("INSERT OR IGNORE INTO contacts(user_id,contact_id,nickname,note,created_at) VALUES(?,?,?,?,?)", (u['id'], linked_id, saved_name, country, now()))
                    db().commit()
                    return redirect('/chat/' + str(linked_id))
                db().commit()
                msg = 'تم الحفظ، لكن هذا الرقم/البريد غير مسجل في المنصة حتى الآن.'
    country_default = request.form.get('country_picker') or country_display(COUNTRY_BY_CODE['+967'])
    return page(f"""
    <div class='top'><a class='icon' href='/new_contact'>‹</a><b>إضافة جديد</b></div>
    <form class='card' method='post'>
        {'<p class=danger>'+h(msg)+'</p>' if msg else ''}
        <div class='input'><input name='saved_name' value='{h(request.form.get('saved_name',''))}' placeholder='اسم الشخص عندك'></div>
        <div class='input'><input name='identifier' value='{h(request.form.get('identifier',''))}' placeholder='بريد_رقم'></div>
        <div class='input'><label class='muted' style='display:block;margin-bottom:6px'>🌍 الدولة</label>{country_picker_html('country_picker', country_default, 'countryPickerContact')}</div>
        <button class='btn' style='width:100%'>حفظ</button>
        <p class='muted'>إذا كان البريد أو الرقم مسجلًا في واصل سيتم فتح المحادثة مباشرة. لا يتم عرض البريد أو الرقم للطرف الآخر.</p>
    </form>
    """)


@app.route('/address_book/<int:book_id>/chat')
@login_required
def address_book_chat(book_id):
    u = current_user()
    r = db().execute("SELECT * FROM address_book WHERE id=? AND user_id=?", (book_id, u['id'])).fetchone()
    if not r:
        return redirect('/new_contact')
    linked_id = r['linked_user_id']
    if not linked_id:
        found = find_platform_user_by_identifier(r['identifier'], r['identifier_type'])
        if found and found['id'] != u['id']:
            linked_id = found['id']
            link_address_book_row(book_id, linked_id)
    if not linked_id:
        return page(f"<div class='top'><a class='icon' href='/new_contact'>‹</a><b>غير متاح</b></div><div class='card'>هذا الشخص محفوظ عندك لكنه لم يدخل المنصة بعد.</div>")
    db().execute("INSERT OR IGNORE INTO contacts(user_id,contact_id,nickname,note,created_at) VALUES(?,?,?,?,?)", (u['id'], linked_id, r['saved_name'], r['country'], now()))
    db().commit()
    return redirect('/chat/' + str(linked_id))


@app.route('/add_contact/<int:uid>')
@login_required
def add_contact(uid):
    if uid == session.get('user_id'):
        return redirect('/new_contact')
    x = db().execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone()
    if not x:
        return redirect('/new_contact')
    db().execute("INSERT OR IGNORE INTO contacts(user_id,contact_id,created_at) VALUES(?,?,?)", (session['user_id'], uid, now()))
    db().commit()
    return redirect('/chat/' + str(uid))

@app.route('/chat/<int:peer_id>', methods=['GET','POST'])
@login_required
def chat(peer_id):
    u=current_user(); p=db().execute("SELECT * FROM users WHERE id=?", (peer_id,)).fetchone()
    if not p: return redirect('/chats')
    contact = get_contact(u['id'], peer_id)
    db().execute("UPDATE contacts SET last_opened_at=? WHERE user_id=? AND contact_id=?", (now(), u['id'], peer_id)); db().commit()
    blocked = is_blocked_between(u['id'], peer_id)
    if request.method=='POST':
        body=request.form.get('body','').strip(); reply_to=request.form.get('reply_to') or None; file=request.files.get('file'); fname=None; ftype=None
        if file and file.filename and allowed(file.filename):
            safe=str(int(datetime.now().timestamp()))+'_'+secure_filename(file.filename); file.save(os.path.join(UPLOAD_DIR,safe)); fname=safe; ftype=file.mimetype
        if blocked:
            return redirect('/chat/'+str(peer_id))
        if body or fname:
            db().execute("INSERT INTO messages(sender_id,receiver_id,body,file_name,file_type,reply_to,created_at) VALUES(?,?,?,?,?,?,?)", (u['id'],peer_id,body,fname,ftype,reply_to,now())); db().commit(); notify(peer_id, u['id'], 'رسالة جديدة من ' + u['name'], '/chat/'+str(u['id']), 'message', 'normal')
        return redirect('/chat/'+str(peer_id))
    db().execute("UPDATE messages SET is_read=1, read_at=COALESCE(read_at, ?) WHERE sender_id=? AND receiver_id=? AND is_read=0", (now(), peer_id, u['id']))
    db().commit()
    msgs=db().execute("""SELECT * FROM messages
                         WHERE ((sender_id=? AND receiver_id=? AND deleted_for_sender=0)
                            OR (sender_id=? AND receiver_id=? AND deleted_for_receiver=0))
                           AND deleted_for_all=0
                         ORDER BY pinned DESC, id""", (u['id'],peer_id,peer_id,u['id'])).fetchall()
    q = request.args.get('q','').strip()
    if q:
        msgs = [m for m in msgs if q in (m['body'] or '')]
    html=[]
    for m in msgs:
        cls='me' if m['sender_id']==u['id'] else 'other'
        filehtml=''
        if m['file_name']:
            url='/uploads/'+m['file_name']
            if (m['file_type'] or '').startswith('image'): filehtml=f"<img src='{url}'>"
            elif (m['file_type'] or '').startswith('video'): filehtml=f"<video controls src='{url}'></video>"
            elif (m['file_type'] or '').startswith('audio'): filehtml=f"<audio controls src='{url}'></audio>"
            else: filehtml=f"<a class='filechip' href='{url}'>📎 تحميل الملف</a>"
        ticks = ('✓✓' if m['is_read'] else '✓') if cls=='me' else ''
        edited = ' · معدلة' if m['edited_at'] else ''
        star = '⭐ ' if m['starred'] else ''
        pin = '<div class=pinmark>📌 مثبتة</div>' if 'pinned' in m.keys() and m['pinned'] else ''
        qhtml = ''
        if m['reply_to']:
            old = db().execute('SELECT body,file_name FROM messages WHERE id=?', (m['reply_to'],)).fetchone()
            if old:
                qhtml = f"<div class='quote'>↩️ {old['body'] or 'ملف مرفق'}</div>"
        safe_body=(m['body'] or '').replace('\n',' ').replace("'", '').replace('\"', '')
        msg_text = h(m['body'] or '')
        attr_text = h(safe_body[:80])
        html.append(f"<div class='msg {cls}' data-id='{m['id']}' data-text='{attr_text}' oncontextmenu='openMenu({m['id']});return false' ondblclick=\"setReply({m['id']},'{attr_text}')\">{pin}{qhtml}{star}{msg_text}{filehtml}<small>{m['created_at'][11:16]} {ticks} {m['reaction'] or ''}{edited}</small></div>{message_menu(m['id'], safe_body, m['reaction'] or '')}")
    blocked_note = '<div class=secure>🛑 لا يمكن إرسال رسائل لأن الحظر مفعل.</div>' if blocked else ''
    composer = f"""<div class="replybar"><div id="replybox" class="replybox" onclick="clearReply()"></div></div><div id="attachPanel" class="attachPanel"><div class="attachGrid"><button type="button" class="attachBtn image" onclick="setFileKind('image')"><span class="big">▣</span><span>صورة</span></button><button type="button" class="attachBtn video" onclick="setFileKind('video')"><span class="big">▶</span><span>فيديو</span></button><button type="button" class="attachBtn audio" onclick="setFileKind('audio')"><span class="big">♪</span><span>صوت</span></button><button type="button" class="attachBtn file" onclick="setFileKind('file')"><span class="big">⌁</span><span>ملف</span></button><button type="button" class="attachBtn closeAttach" onclick="toggleAttachPanel(false)"><span class="big">×</span><span>إغلاق</span></button></div></div><div id="attachNotice" class="attachNotice"><div class="attachNoticeBox"><img id="attachThumb" class="attachThumb"><div class="attachInfo"><span id="filePreview">📎 مرفق محدد</span><br><b>اكتب نصًا ثم اضغط إرسال</b></div><button type="button" class="attachRemove" onclick="clearAttachment()">×</button></div></div><div class="compose"><form method="post" enctype="multipart/form-data"><input type="hidden" name="reply_to" id="reply_to"><input type="file" name="file" id="file" hidden onchange="showFileName(this)"><input type="file" name="voiceFallback" id="voiceFallback" accept="audio/*,.m4a,.aac,.amr,.3gp,.ogg,.webm" capture="microphone" hidden onchange="sendVoiceFile(this)"><button type="button" class="icon" onclick="toggleAttachPanel()">＋</button><input type="text" name="body" placeholder="اكتب رسالة..."><button type="button" id="recordBtn" class="recBtn" onclick="toggleRecording({peer_id})">🎙️<span class="recText"> تسجيل</span></button><div id="voiceModal" class="voiceModal"><div class="voiceSheet"><div id="voiceMic" class="voiceMic">🎙️</div><div id="voiceTime" class="voiceTime">00:00</div><div id="voiceStatus" class="voiceStatus">جاهز للتسجيل.</div><div class="voiceActions"><button type="button" id="voiceStartBtn" class="btn" onclick="startVoiceRecording()">بدء</button><button type="button" id="voiceStopBtn" class="btn gray" style="display:none" onclick="stopVoiceRecording()">إيقاف</button><button type="button" id="voiceSendBtn" class="btn full" onclick="sendVoiceRecording()" disabled>إرسال</button><button type="button" class="btn gray" onclick="cancelVoiceRecording()">إلغاء</button><button type="button" class="btn gray" onclick="closeVoiceRecorder()">إغلاق</button></div></div></div><button class="btn sendBtn">إرسال</button></form></div>""" if not blocked else '' 
    display_name = contact['nickname'] or p['name']
    body=f"<div class='top chatTop'><a class='icon backBtn' href='/chats'>‹</a><a href='/profile/{p['id']}'><img class='avatar' src='{avatar_url(p)}'></a><div class='header-name'><b>{display_name}</b><div class='status'>{'متصل الآن' if p['online'] else 'غير متصل'}</div></div><div class='chatTools'><a class='icon' href='/call/{p['id']}/video'>📹</a><a class='icon' href='/call/{p['id']}/audio'>📞</a><a class='icon txtIcon' href='/export_chat/{p['id']}'>TXT</a><a class='icon' href='/chat_options/{p['id']}'>⋮</a></div></div><form class='searchmini' method='get'><input name='q' value='{request.args.get('q','')}' placeholder='بحث داخل الدردشة'><button class='btn gray'>بحث</button></form><div class='messages'><div class='day'>اليوم</div><div class='secure'>🔒 الرسائل والمكالمات مشفرة بين الطرفين.</div>{blocked_note}{''.join(html)}</div>{composer}"
    return page(body)


def message_menu(mid, txt='', current_reaction=''):
    raw_txt = (txt or '').replace('\n',' ')[:120]
    safe_txt = h(raw_txt)
    reaction_items = ['❤️','👍','😂','😮','😢','🔥','😍','👏','😡']
    reactions = ''.join([f"<button class='{('selected' if current_reaction == e else '')}' title='{e}' onclick=\"react({mid},'{e}')\">{e}</button>" for e in reaction_items])
    return f"""
<div class='menu' id='menu_{mid}' onclick='closeMenu({mid})'>
  <div class='sheet' onclick='event.stopPropagation()'>
    <div class='reactions'>{reactions}</div>
    <div class='messageQuickInfo'><b>رسالة محددة</b><span>واصل</span></div>
    <div class='actions'>
      <div class='actionGroup'>
        <button class='purple' data-txt='{safe_txt}' onclick="setReply({mid}, this.getAttribute('data-txt'));closeMenu({mid})"><span class='ico'>↩️</span><span>رد</span></button>
        <button class='purple' data-txt='{safe_txt}' onclick="copyText(this.getAttribute('data-txt'))"><span class='ico'>📋</span><span>نسخ</span></button>
        <button class='purple' onclick="location.href='/message/{mid}/info'"><span class='ico'>ℹ️</span><span>معلومات الرسالة</span></button>
      </div>
      <div class='actionGroup'>
        <button class='blue' onclick="location.href='/message/{mid}/pin'"><span class='ico'>📌</span><span>تثبيت / إلغاء التثبيت</span></button>
        <button class='yellow' onclick="location.href='/message/{mid}/star'"><span class='ico'>⭐</span><span>حفظ / إلغاء الحفظ</span></button>
        <button class='green' onclick="location.href='/message/{mid}/forward'"><span class='ico'>🔄</span><span>تحويل</span></button>
        <button class='blue' onclick="location.href='/message/{mid}/save_file'"><span class='ico'>⬇️</span><span>حفظ الملف</span></button>
        <button class='orange' onclick="location.href='/message/{mid}/reminder'"><span class='ico'>⏰</span><span>تذكير</span></button>
      </div>
      <div class='actionGroup'>
        <button class='orange' onclick="location.href='/message/{mid}/edit'"><span class='ico'>✏️</span><span>تعديل</span></button>
        <button class='red' onclick="location.href='/message/{mid}/delete_me'"><span class='ico'>🗑️</span><span>حذف لدي</span></button>
        <button class='red' onclick="location.href='/message/{mid}/delete_all'"><span class='ico'>🚫</span><span>حذف للجميع</span></button>
      </div>
      <button class='actionClose' onclick="closeMenu({mid})">إغلاق</button>
    </div>
  </div>
</div>"""



@app.route('/message/<int:mid>/react', methods=['POST'])
@login_required
def react(mid):
    m = db().execute("SELECT * FROM messages WHERE id=?", (mid,)).fetchone()
    if not m or (m['sender_id'] != session['user_id'] and m['receiver_id'] != session['user_id']):
        return jsonify({'ok': False}), 403
    db().execute("UPDATE messages SET reaction=? WHERE id=?", (request.form.get('emoji',''), mid)); db().commit(); return 'ok'


@app.route('/message/<int:mid>/star')
@login_required
def star_message(mid):
    m = db().execute("SELECT * FROM messages WHERE id=?", (mid,)).fetchone()
    if m and (m['sender_id'] == session['user_id'] or m['receiver_id'] == session['user_id']):
        db().execute("UPDATE messages SET starred=CASE WHEN starred=1 THEN 0 ELSE 1 END WHERE id=?", (mid,))
        db().commit()
    return redirect(request.referrer or '/chats')


@app.route('/message/<int:mid>/delete_me')
@login_required
def delete_me(mid):
    m = db().execute("SELECT * FROM messages WHERE id=?", (mid,)).fetchone()
    if m:
        if m['sender_id'] == session['user_id']:
            db().execute("UPDATE messages SET deleted_for_sender=1 WHERE id=?", (mid,))
        elif m['receiver_id'] == session['user_id']:
            db().execute("UPDATE messages SET deleted_for_receiver=1 WHERE id=?", (mid,))
        db().commit()
    return redirect(request.referrer or '/chats')



@app.route('/message/<int:mid>/save_file')
@login_required
def save_message_file(mid):
    m = db().execute("SELECT * FROM messages WHERE id=?", (mid,)).fetchone()
    if not m or (m['sender_id'] != session['user_id'] and m['receiver_id'] != session['user_id']):
        return redirect('/chats')
    if not m['file_name']:
        return redirect(request.referrer or '/chats')
    return send_from_directory(UPLOAD_DIR, m['file_name'], as_attachment=True)

@app.route('/message/<int:mid>/reminder', methods=['GET','POST'])
@login_required
def message_reminder(mid):
    m = db().execute("SELECT * FROM messages WHERE id=?", (mid,)).fetchone()
    if not m or (m['sender_id'] != session['user_id'] and m['receiver_id'] != session['user_id']):
        return redirect('/chats')
    peer = m['receiver_id'] if m['sender_id'] == session['user_id'] else m['sender_id']
    msg = ''
    if request.method == 'POST':
        reminder_at = request.form.get('reminder_at','').strip()
        if reminder_at:
            reminder_at = reminder_at.replace('T', ' ')
            if len(reminder_at) == 16:
                reminder_at += ':00'
        db().execute("UPDATE messages SET reminder_at=?, reminder_done=0 WHERE id=?", (reminder_at or None, mid))
        db().commit()
        msg = 'تم حفظ التذكير'
    val = h((m['reminder_at'] or '').replace(' ', 'T')[:16])
    return page(f"<div class='top'><a class='icon' href='/chat/{peer}'>‹</a><b>تذكير الرسالة</b></div><form class='card' method='post'><p class='muted'>{msg or 'حدد وقت التذكير لهذه الرسالة.'}</p><div class='input'><input type='datetime-local' name='reminder_at' value='{val}'></div><button class='btn'>حفظ التذكير</button></form><div class='card'><b>نص الرسالة:</b><p>{h(m['body'] or 'ملف مرفق')}</p></div>")

@app.route('/message/<int:mid>/forward', methods=['GET','POST'])
@login_required
def forward_message(mid):
    u = current_user()
    m = db().execute("SELECT * FROM messages WHERE id=?", (mid,)).fetchone()
    if not m or (m['sender_id'] != u['id'] and m['receiver_id'] != u['id']):
        return redirect('/chats')
    old_peer = m['receiver_id'] if m['sender_id'] == u['id'] else m['sender_id']
    if request.method == 'POST':
        to_id = int(request.form.get('to_id','0') or 0)
        target = db().execute("SELECT id FROM contacts WHERE user_id=? AND contact_id=?", (u['id'], to_id)).fetchone()
        if target:
            body = ('محولة: ' + (m['body'] or '')).strip() or 'رسالة محولة'
            db().execute("INSERT INTO messages(sender_id,receiver_id,body,file_name,file_type,created_at) VALUES(?,?,?,?,?,?)", (u['id'], to_id, body, m['file_name'], m['file_type'], now()))
            db().commit(); notify(to_id, u['id'], 'رسالة محولة من ' + u['name'], '/chat/'+str(u['id']), 'message', 'normal')
            return redirect('/chat/' + str(to_id))
    contacts = db().execute("""SELECT users.*, contacts.nickname FROM contacts JOIN users ON users.id=contacts.contact_id WHERE contacts.user_id=? AND contacts.blocked=0 ORDER BY contacts.id DESC""", (u['id'],)).fetchall()
    rows = ''
    for c in contacts:
        rows += f"<label class='chatitem'><img class='avatar' src='{avatar_url(c)}'><div class='grow'><div class='name'>{h(c['nickname'] or c['name'])}</div><div class='last'>{h(c['username'] or '')}</div></div><input type='radio' name='to_id' value='{c['id']}' required></label>"
    return page(f"<div class='top'><a class='icon' href='/chat/{old_peer}'>‹</a><b>تحويل الرسالة</b></div><form class='card' method='post'><p class='muted'>اختر جهة اتصال لتحويل الرسالة إليها.</p>{rows or '<div class=muted>لا توجد جهات اتصال متاحة.</div>'}<br><button class='btn'>تحويل</button></form>")

@app.route('/message/<int:mid>/edit', methods=['GET','POST'])
@login_required
def edit_message(mid):
    m = db().execute("SELECT * FROM messages WHERE id=?", (mid,)).fetchone()
    if not m or m['sender_id'] != session['user_id']:
        return redirect('/chats')
    if request.method == 'POST':
        body = request.form.get('body','').strip()
        db().execute("UPDATE messages SET body=?, edited_at=? WHERE id=?", (body, now(), mid))
        db().commit()
        return redirect('/chat/' + str(m['receiver_id']))
    body = f"<div class='top'><a class='icon' href='/chat/{m['receiver_id']}'>‹</a><b>تعديل الرسالة</b></div><form class='card' method='post'><div class='input'><textarea name='body' rows='5'>{m['body'] or ''}</textarea></div><button class='btn'>حفظ التعديل</button></form>"
    return page(body)


@app.route('/message/<int:mid>/info')
@login_required
def message_info(mid):
    m = db().execute("SELECT * FROM messages WHERE id=?", (mid,)).fetchone()
    if not m or (m['sender_id'] != session['user_id'] and m['receiver_id'] != session['user_id']):
        return redirect('/chats')
    peer = m['receiver_id'] if m['sender_id'] == session['user_id'] else m['sender_id']
    body = f"<div class='top'><a class='icon' href='/chat/{peer}'>‹</a><b>معلومات الرسالة</b></div><div class='card'><p>الوقت: {m['created_at']}</p><p>محفوظة: {'نعم' if m['starred'] else 'لا'}</p><p>التفاعل: {m['reaction'] or 'لا يوجد'}</p><p>تمت القراءة: {'نعم' if m['is_read'] else 'لا'}</p><p>وقت القراءة: {m['read_at'] or 'لم تقرأ بعد'}</p><p>آخر تعديل: {m['edited_at'] or 'لا يوجد'}</p><p>يوجد ملف: {'نعم' if m['file_name'] else 'لا'}</p></div>"
    return page(body)


@app.route('/message/<int:mid>/delete_all')
@login_required
def delete_all(mid):
    m=db().execute("SELECT * FROM messages WHERE id=?", (mid,)).fetchone()
    if m and m['sender_id']==session['user_id']:
        db().execute("UPDATE messages SET deleted_for_all=1 WHERE id=?", (mid,)); db().commit()
    return redirect(request.referrer or '/chats')



@app.route('/message/<int:mid>/pin')
@login_required
def pin_message(mid):
    m = db().execute("SELECT * FROM messages WHERE id=?", (mid,)).fetchone()
    if m and (m['sender_id'] == session['user_id'] or m['receiver_id'] == session['user_id']):
        db().execute("UPDATE messages SET pinned=CASE WHEN pinned=1 THEN 0 ELSE 1 END WHERE id=?", (mid,))
        db().commit()
    return redirect(request.referrer or '/chats')


@app.route('/chat_audio/<int:peer_id>', methods=['POST'])
@login_required
def chat_audio(peer_id):
    u = current_user()
    p = db().execute("SELECT * FROM users WHERE id=?", (peer_id,)).fetchone()
    if not p:
        return jsonify({'ok': False, 'error': 'not_found'}), 404
    if is_blocked_between(u['id'], peer_id):
        return jsonify({'ok': False, 'error': 'blocked'}), 403
    file = request.files.get('audio')
    if not file or not file.filename:
        return jsonify({'ok': False, 'error': 'no_audio'}), 400
    # تسجيل صوتي من المتصفح WebM/OGG/WAV فقط
    ext = file.filename.rsplit('.', 1)[-1].lower() if '.' in file.filename else 'webm'
    if ext not in {'webm', 'ogg', 'wav', 'mp3', 'm4a', 'aac', 'amr', '3gp'}:
        ext = 'webm'
    safe = str(int(datetime.now().timestamp())) + '_voice.' + ext
    file.save(os.path.join(UPLOAD_DIR, safe))
    caption = request.form.get('body','').strip()[:500]
    voice_body = caption or '🎙️ تسجيل صوتي'
    db().execute("INSERT INTO messages(sender_id,receiver_id,body,file_name,file_type,created_at) VALUES(?,?,?,?,?,?)", (u['id'], peer_id, voice_body, safe, file.mimetype or ('audio/' + ext), now()))
    db().commit()
    notify(peer_id, u['id'], 'تسجيل صوتي جديد من ' + u['name'], '/chat/' + str(u['id']), 'message', 'normal')
    return jsonify({'ok': True})

@app.route('/export_chat/<int:peer_id>')
@login_required
def export_chat(peer_id):
    u = current_user()
    p = db().execute("SELECT * FROM users WHERE id=?", (peer_id,)).fetchone()
    if not p:
        return redirect('/chats')
    rows = db().execute("""SELECT m.*, us.name sender_name FROM messages m
                         JOIN users us ON us.id=m.sender_id
                         WHERE ((m.sender_id=? AND m.receiver_id=?) OR (m.sender_id=? AND m.receiver_id=?))
                           AND m.deleted_for_all=0
                         ORDER BY m.id""", (u['id'], peer_id, peer_id, u['id'])).fetchall()
    lines = [f"محادثة واصل شات بين {u['name']} و {p['name']}", "="*40]
    for m in rows:
        content = m['body'] or ('ملف: ' + (m['file_name'] or ''))
        lines.append(f"[{m['created_at']}] {m['sender_name']}: {content}")
    from flask import Response
    return Response("\n".join(lines), mimetype='text/plain; charset=utf-8', headers={'Content-Disposition':'attachment; filename=wasel_chat_export.txt'})

@app.route('/starred')
@login_required
def starred_messages():
    u = current_user()
    rows = db().execute("""SELECT m.*, us.name sender_name, ur.name receiver_name FROM messages m
                           JOIN users us ON us.id=m.sender_id
                           JOIN users ur ON ur.id=m.receiver_id
                           WHERE (m.sender_id=? OR m.receiver_id=?) AND m.starred=1 AND m.deleted_for_all=0
                           ORDER BY m.id DESC""", (u['id'], u['id'])).fetchall()
    cards = ''
    for m in rows:
        peer = m['receiver_id'] if m['sender_id'] == u['id'] else m['sender_id']
        who = 'أنت' if m['sender_id'] == u['id'] else m['sender_name']
        cards += f"<a class='chatitem' href='/chat/{peer}'><div class='grow'><div class='name'>⭐ {who}</div><div class='last'>{m['body'] or 'ملف مرفق'} · {m['created_at']}</div></div></a>"
    return page(f"<div class='top'><a class='icon' href='/me'>‹</a><b>الرسائل المميزة</b></div><div class='list'>{cards or '<div class=card>لا توجد رسائل مميزة</div>'}</div>")



@app.route('/profile/<int:uid>')
@login_required
def profile(uid):
    u = db().execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone()
    if not u:
        return redirect('/chats')
    me_id = session.get('user_id')
    msg_count = db().execute("SELECT COUNT(*) c FROM messages WHERE sender_id=?", (uid,)).fetchone()['c']
    status_count = db().execute("SELECT COUNT(*) c FROM statuses WHERE user_id=?", (uid,)).fetchone()['c']
    contact_count = db().execute("SELECT COUNT(*) c FROM contacts WHERE user_id=?", (uid,)).fetchone()['c']
    cover = f"<img src='/uploads/{u['cover_photo']}'>" if u['cover_photo'] else ""
    back = '/me' if uid == me_id else f'/chat/{uid}'
    actions = ""
    if uid == me_id:
        actions = "<a class='btn' href='/me'>تعديل ملفي</a> <a class='btn gray' href='/settings'>الإعدادات</a>"
    else:
        actions = f"<a class='btn' href='/chat/{uid}'>مراسلة</a> <a class='btn gray' href='/call/{uid}/audio'>اتصال</a>"
    details = []
    if u['country']: details.append('🌍 ' + h(u['country']))
    if u['location']: details.append('📍 ' + h(u['location']))
    if u['website']: details.append('🔗 ' + h(u['website']))
    body = f"""
    <div class='top'><a class='icon' href='{back}'>‹</a><b>الملف الشخصي</b></div>
    <div class='profileCover'>{cover}</div>
    <div class='profileHero'>
      <img class='avatar' src='{avatar_url(u)}'>
      <h2>{h(u['name'])}</h2>
      <p class='muted'>{h(u['username'] or '')}</p>
      <p>{h(u['about'] or '')}</p>
      <div class='muted'>{' · '.join(details) if details else 'لا توجد تفاصيل إضافية'}</div>
      <div style='margin-top:14px'>{actions}</div>
      <div class='profileStats'><div><b>{msg_count}</b><span>رسائل</span></div><div><b>{status_count}</b><span>حالات</span></div><div><b>{contact_count}</b><span>جهات</span></div></div>
    </div>
    """
    return page(body)

@app.route('/chat_options/<int:peer>', methods=['GET','POST'])
@login_required
def chat_options(peer):
    u = current_user()
    p = db().execute("SELECT * FROM users WHERE id=?", (peer,)).fetchone()
    if not p:
        return redirect('/chats')
    c = get_contact(u['id'], peer)
    if request.method == 'POST':
        nickname = request.form.get('nickname','').strip() or None
        note = request.form.get('note','').strip() or None
        db().execute("UPDATE contacts SET nickname=?, note=? WHERE user_id=? AND contact_id=?", (nickname, note, u['id'], peer))
        db().commit()
        return redirect('/chat_options/' + str(peer))
    return page(f"<div class='top'><a class='icon' href='/chat/{peer}'>‹</a><b>إعدادات المحادثة</b></div><div class='card'><div class='profileRow'><img class='avatar' src='{avatar_url(p)}'><div><b>{p['name']}</b><div class='muted'>{p['about']}</div></div></div></div><form class='card' method='post'><div class='input'><input name='nickname' value='{c['nickname'] or ''}' placeholder='اسم مخصص لهذه الجهة'></div><div class='input'><textarea name='note' rows='3' placeholder='ملاحظة خاصة لا يراها إلا أنت'>{c['note'] or ''}</textarea></div><button class='btn'>حفظ الاسم والملاحظة</button></form><div class='card'><a class='chatitem' href='/contact/{peer}/pin'>{'إلغاء التثبيت' if c['pinned'] else '📌 تثبيت المحادثة'}</a><a class='chatitem' href='/contact/{peer}/mute'>{'إلغاء الكتم' if c['muted'] else '🔕 كتم الإشعارات'}</a><a class='chatitem' href='/contact/{peer}/archive'>{'إلغاء الأرشفة' if c['archived'] else '🗄️ أرشفة المحادثة'}</a><a class='chatitem danger' href='/contact/{peer}/block'>{'إلغاء الحظر' if c['blocked'] else '🛑 حظر المستخدم'}</a></div>")


@app.route('/contact/<int:peer>/<action>')
@login_required
def contact_action(peer, action):
    get_contact(session['user_id'], peer)
    allowed_actions = {'pin':'pinned', 'mute':'muted', 'archive':'archived', 'block':'blocked'}
    col = allowed_actions.get(action)
    if col:
        db().execute(f"UPDATE contacts SET {col}=CASE WHEN {col}=1 THEN 0 ELSE 1 END WHERE user_id=? AND contact_id=?", (session['user_id'], peer))
        db().commit()
    return redirect(request.referrer or '/chat_options/' + str(peer))



def parse_dt_safe(value):
    try:
        return datetime.strptime(value, "%Y-%m-%d %H:%M:%S")
    except Exception:
        return None


def ensure_status_expiry_and_cleanup():
    """يضبط وقت انتهاء 24 ساعة للحالات القديمة وينظف المنتهي ومشاهده وردوده."""
    con = db()
    rows = con.execute("SELECT id,created_at,expires_at FROM statuses").fetchall()
    changed = False
    now_s = now()
    for r in rows:
        if not r['expires_at']:
            base = parse_dt_safe(r['created_at']) or datetime.now()
            exp = (base + timedelta(hours=24)).strftime('%Y-%m-%d %H:%M:%S')
            con.execute("UPDATE statuses SET expires_at=? WHERE id=?", (exp, r['id']))
            changed = True
    expired = con.execute("SELECT id FROM statuses WHERE expires_at IS NOT NULL AND expires_at < ?", (now_s,)).fetchall()
    for e in expired:
        con.execute("DELETE FROM status_views WHERE status_id=?", (e['id'],))
        con.execute("DELETE FROM status_replies WHERE status_id=?", (e['id'],))
        con.execute("DELETE FROM status_reactions WHERE status_id=?", (e['id'],))
        con.execute("DELETE FROM statuses WHERE id=?", (e['id'],))
        changed = True
    con.execute("DELETE FROM status_views WHERE status_id NOT IN (SELECT id FROM statuses)")
    con.execute("DELETE FROM status_replies WHERE status_id NOT IN (SELECT id FROM statuses)")
    con.execute("DELETE FROM status_reactions WHERE status_id NOT IN (SELECT id FROM statuses)")
    if changed:
        con.commit()


def status_progress(st):
    exp = parse_dt_safe(st['expires_at'] if 'expires_at' in st.keys() else None)
    created = parse_dt_safe(st['created_at'] if 'created_at' in st.keys() else None) or datetime.now()
    if not exp:
        exp = created + timedelta(hours=24)
    total = max(1, int((exp - created).total_seconds()))
    left = max(0, int((exp - datetime.now()).total_seconds()))
    pct = max(0, min(100, int(left * 100 / total)))
    return pct


def status_elapsed(st):
    created = parse_dt_safe(st['created_at'] if 'created_at' in st.keys() else None) or datetime.now()
    diff = max(0, int((datetime.now() - created).total_seconds()))
    if diff < 60:
        return 'منذ لحظات'
    if diff < 3600:
        m = diff // 60
        return f'منذ {m} دقيقة'
    if diff < 86400:
        h_ = diff // 3600
        return f'منذ {h_} ساعة'
    d = diff // 86400
    return f'منذ {d} يوم'



def status_reply_time_label(value):
    dt = parse_dt_safe(value)
    if not dt:
        return ''
    hour = dt.hour
    ampm = 'ص' if hour < 12 else 'م'
    hour12 = hour % 12 or 12
    return f'منذ: {hour12}:{dt.minute:02d} {ampm}'

def status_remaining(st):
    # إبقاء الاسم القديم حتى لا ينكسر أي مكان آخر، لكن النص صار "منذ" وليس "باقي".
    return status_elapsed(st), status_progress(st)


def register_status_view(status_id, owner_id, viewer_id):
    if owner_id == viewer_id:
        return
    con = db()
    con.execute("INSERT OR IGNORE INTO status_views(status_id,viewer_id,viewed_at) VALUES(?,?,?)", (status_id, viewer_id, now()))
    con.execute("UPDATE statuses SET last_viewed_at=?, views_count_cache=(SELECT COUNT(*) FROM status_views WHERE status_id=?) WHERE id=?", (now(), status_id, status_id))
    con.commit()




def status_reactions_summary(status_id):
    rows = db().execute("SELECT emoji, COUNT(*) c FROM status_reactions WHERE status_id=? GROUP BY emoji ORDER BY c DESC", (status_id,)).fetchall()
    return ' '.join([f"{h(r['emoji'])} {r['c']}" for r in rows])


def status_react_button(status_id, current_emoji=''):
    emojis = ['❤️','👍','😂','😮','😢','🔥']
    # نمرر event حتى لا يفتح الرابط/النموذج فوق الضغط، ونغلق الدائرة بعد الاختيار.
    btns = ''.join([f"<button type='button' onclick=\"sendStatusReaction({status_id},'{e}',event)\">{e}</button>" for e in emojis])
    face = current_emoji or '❤️'
    return f"""
    <div class='statusReactWrap'>
      <button type='button' class='statusRoundBtn' id='statusRound_{status_id}' onclick='toggleStatusCircle({status_id},event)'>{face}</button>
      <div class='statusReactionCircle' id='statusReact_{status_id}'>{btns}</div>
    </div>
    """


def ensure_status_reactions_table():
    """إصلاح نهائي لجدول تفاعلات الحالات.
    بعض النسخ القديمة أنشأت جدول status_reactions بأعمدة/قيود مختلفة، وهذا كان يسبب db_error.
    هنا نعيد بناء الجدول بشكل مضمون بدون حذف الحالات أو الردود.
    """
    con = db()
    desired = {'id','status_id','user_id','owner_id','emoji','reacted_at'}
    con.execute("""CREATE TABLE IF NOT EXISTS status_reactions(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        status_id INTEGER,
        user_id INTEGER,
        owner_id INTEGER,
        emoji TEXT,
        reacted_at TEXT
    )""")
    info = con.execute("PRAGMA table_info(status_reactions)").fetchall()
    cols = [r[1] for r in info]
    # إذا وجدنا أعمدة قديمة إجبارية أو ناقصة، نبني جدولاً نظيفاً ثم ننقل البيانات الممكنة.
    must_rebuild = False
    for r in info:
        name = r[1]
        notnull = int(r[3] or 0)
        default = r[4]
        if name not in desired and notnull and default is None:
            must_rebuild = True
    if not desired.issubset(set(cols)):
        must_rebuild = True
    if must_rebuild:
        con.execute("DROP TABLE IF EXISTS status_reactions_fixed")
        con.execute("""CREATE TABLE status_reactions_fixed(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            status_id INTEGER,
            user_id INTEGER,
            owner_id INTEGER,
            emoji TEXT,
            reacted_at TEXT
        )""")
        old = set(cols)
        sid_col = 'status_id' if 'status_id' in old else None
        uid_col = 'user_id' if 'user_id' in old else ('viewer_id' if 'viewer_id' in old else None)
        emoji_col = 'emoji' if 'emoji' in old else ('reaction' if 'reaction' in old else None)
        time_col = 'reacted_at' if 'reacted_at' in old else ('created_at' if 'created_at' in old else None)
        owner_col = 'owner_id' if 'owner_id' in old else None
        if sid_col and uid_col:
            sel_emoji = emoji_col if emoji_col else "'❤️'"
            sel_time = time_col if time_col else "''"
            sel_owner = owner_col if owner_col else "NULL"
            try:
                con.execute(f"""INSERT INTO status_reactions_fixed(status_id,user_id,owner_id,emoji,reacted_at)
                                SELECT {sid_col},{uid_col},{sel_owner},COALESCE(NULLIF({sel_emoji},''),'❤️'),COALESCE(NULLIF({sel_time},''),?)
                                FROM status_reactions
                                WHERE {sid_col} IS NOT NULL AND {uid_col} IS NOT NULL""", (now(),))
            except Exception as e:
                print('STATUS_REACTION_MIGRATE_SKIP:', repr(e))
        con.execute("DROP TABLE status_reactions")
        con.execute("ALTER TABLE status_reactions_fixed RENAME TO status_reactions")
    else:
        for col, definition in [('owner_id','INTEGER'),('emoji','TEXT'),('reacted_at','TEXT'),('user_id','INTEGER'),('status_id','INTEGER')]:
            if col not in cols:
                con.execute(f"ALTER TABLE status_reactions ADD COLUMN {col} {definition}")
    con.execute("UPDATE status_reactions SET emoji=COALESCE(NULLIF(emoji,''),'❤️') WHERE emoji IS NULL OR emoji=''")
    con.execute("UPDATE status_reactions SET reacted_at=COALESCE(NULLIF(reacted_at,''),?) WHERE reacted_at IS NULL OR reacted_at=''", (now(),))
    con.execute("DELETE FROM status_reactions WHERE status_id IS NULL OR user_id IS NULL")
    con.execute("""DELETE FROM status_reactions
                   WHERE id NOT IN (SELECT MAX(id) FROM status_reactions GROUP BY status_id,user_id)""")
    con.execute("DROP INDEX IF EXISTS idx_status_reactions_unique")
    con.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_status_reactions_unique ON status_reactions(status_id,user_id)")
    con.commit()


def save_status_reaction(status_id, user_id, owner_id, emoji):
    con = db()
    ensure_status_reactions_table()
    t = now()
    cur = con.execute("UPDATE status_reactions SET emoji=?, reacted_at=?, owner_id=? WHERE status_id=? AND user_id=?",
                      (emoji, t, owner_id, status_id, user_id))
    if cur.rowcount == 0:
        con.execute("INSERT INTO status_reactions(status_id,user_id,owner_id,emoji,reacted_at) VALUES(?,?,?,?,?)",
                    (status_id, user_id, owner_id, emoji, t))
    con.commit()


@app.route('/status/<int:sid>/react', methods=['POST'])
@login_required
def react_status(sid):
    u = current_user()
    ensure_status_reactions_table()
    st = db().execute("SELECT * FROM statuses WHERE id=?", (sid,)).fetchone()
    if not st or not can_view_status(st, u['id']):
        return jsonify({'ok': False, 'error': 'status_not_found'}), 404
    emoji = request.form.get('emoji','').strip()
    allowed_emojis = ['❤️','👍','😂','😮','😢','🔥']
    if emoji not in allowed_emojis:
        return jsonify({'ok': False, 'error': 'bad_emoji'}), 400
    try:
        # محاولة أولى، وإن كانت قاعدة البيانات القديمة مكسورة نعيد بناء الجدول ونكرر مرة واحدة.
        try:
            save_status_reaction(sid, u['id'], st['user_id'], emoji)
        except Exception as e1:
            print('STATUS_REACTION_FIRST_TRY_ERROR:', repr(e1))
            try:
                db().rollback()
            except Exception:
                pass
            # إعادة بناء قسرية للجدول ثم إعادة الحفظ.
            con2 = db()
            con2.execute("DROP INDEX IF EXISTS idx_status_reactions_unique")
            con2.commit()
            ensure_status_reactions_table()
            save_status_reaction(sid, u['id'], st['user_id'], emoji)
        if st['user_id'] != u['id']:
            notify(st['user_id'], u['id'], f'{u["name"]} تفاعل مع حالتك {emoji}', '/status/' + str(sid) + '/reactions', 'status', 'normal')
        return jsonify({'ok': True, 'emoji': emoji})
    except Exception as e:
        try:
            db().rollback()
        except Exception:
            pass
        print('STATUS_REACTION_SAVE_ERROR_FINAL:', repr(e))
        return jsonify({'ok': False, 'error': 'db_error', 'detail': str(e)[:120]}), 200


@app.route('/status/<int:sid>/reactions')
@login_required
def status_reactions(sid):
    ensure_status_reactions_table()
    st = db().execute("SELECT * FROM statuses WHERE id=?", (sid,)).fetchone()
    if not st or st['user_id'] != session['user_id']:
        return redirect('/statuses')
    rows_db = db().execute("""
        SELECT sr.*,u.name,u.avatar FROM status_reactions sr
        JOIN users u ON u.id=sr.user_id
        WHERE sr.status_id=? ORDER BY sr.id DESC
    """, (sid,)).fetchall()
    rows = ''
    for r in rows_db:
        av = ('/uploads/' + r['avatar']) if r['avatar'] else 'https://ui-avatars.com/api/?background=123&color=fff&name=' + str(r['name']).replace(' ','+')
        rows += f"<a class='chatitem' href='/chat/{r['user_id']}'><img class='avatar' src='{av}'><div class='grow'><div class='name'>{h(r['name'])} <span class='badge'>{h(r['emoji'])}</span></div><div class='last'>تفاعل مع الحالة · {h(status_reply_time_label(r['reacted_at']))}</div></div></a>"
    return page(f"<div class='top'><a class='icon backHistory' href='/statuses' onclick='return goBackOne()'>‹</a><b>تفاعلات الحالة</b></div><div class='card'><b>عدد التفاعلات: {len(rows_db)}</b></div><div class='statusSubList'>{rows or '<div class=card>لا توجد تفاعلات حتى الآن</div>'}</div>")

@app.route('/statuses', methods=['GET','POST'])
@login_required
def statuses():
    u = current_user()
    if 'service_status_enabled' in u.keys() and not u['service_status_enabled']:
        return page("<div class='top'><a class='icon' href='/services'>‹</a><b>الحالات متوقفة</b></div><div class='card'>خدمة الحالات متوقفة من الإعدادات. <a class='btn' href='/services'>تشغيلها الآن</a></div>")

    if request.method == 'POST':
        text = request.form.get('text','').strip()
        privacy = request.form.get('privacy','public')
        if privacy not in ('public','contacts','private'):
            privacy = 'public'
        bg = request.form.get('bg','blue')
        if bg not in ('blue','green','purple','dark'):
            bg = 'blue'
        file = request.files.get('file')
        fname = None
        if file and file.filename and allowed(file.filename):
            fname = str(int(datetime.now().timestamp())) + '_' + secure_filename(file.filename)
            file.save(os.path.join(UPLOAD_DIR, fname))
        if text or fname:
            exp = (datetime.now() + timedelta(hours=24)).strftime('%Y-%m-%d %H:%M:%S')
            db().execute("INSERT INTO statuses(user_id,text,file_name,privacy,bg,expires_at,views_count_cache,created_at) VALUES(?,?,?,?,?,?,0,?)", (u['id'], text, fname, privacy, bg, exp, now()))
            db().commit()
        return redirect('/statuses')

    ensure_status_expiry_and_cleanup()
    sts = db().execute("""
        SELECT s.*, u.name, u.avatar,
        (SELECT COUNT(*) FROM status_views v WHERE v.status_id=s.id) AS views_count,
        (SELECT COUNT(*) FROM status_replies r WHERE r.status_id=s.id) AS replies_count,
        (SELECT COUNT(*) FROM status_reactions rr WHERE rr.status_id=s.id) AS reactions_count,
        (SELECT emoji FROM status_reactions mine WHERE mine.status_id=s.id AND mine.user_id=? LIMIT 1) AS my_reaction
        FROM statuses s JOIN users u ON u.id=s.user_id
        WHERE s.expires_at IS NULL OR s.expires_at >= ?
        ORDER BY CASE WHEN s.user_id=? THEN 0 ELSE 1 END, s.id DESC
    """, (u['id'], now(), u['id'])).fetchall()

    visible = [st for st in sts if can_view_status(st, u['id'])]
    privacy_label = {'public':'الكل', 'contacts':'جهاتي فقط', 'private':'أنا فقط'}

    rail = ""
    for st in visible[:20]:
        av = ('/uploads/' + st['avatar']) if st['avatar'] else 'https://ui-avatars.com/api/?background=123&color=fff&name=' + str(st['name']).replace(' ','+')
        elapsed, pct = status_remaining(st)
        name = 'حالتي' if st['user_id'] == u['id'] else st['name']
        rail += f"<a class='storyBubble' href='/status/{st['id']}/view' style='--p:{pct}%'><div class='storyRing'><img src='{av}'></div><b>{h(name)}</b><small>{h(elapsed)}</small></a>"

    cards = ''
    for st in visible:
        av = ('/uploads/' + st['avatar']) if st['avatar'] else 'https://ui-avatars.com/api/?background=123&color=fff&name=' + str(st['name']).replace(' ','+')
        media = status_media_html(st, preview=True)
        text = h(st['text'] or '')
        elapsed, pct = status_remaining(st)
        summary = status_reactions_summary(st['id'])
        public_actions = f"<div class='statusPublicActions'>{status_react_button(st['id'], st['my_reaction'] if 'my_reaction' in st.keys() else '')}<a class='btn gray' href='/status/{st['id']}/view'>عرض / رد</a>{('<span class=muted>'+summary+'</span>') if summary and st['user_id']==u['id'] else ''}</div>"
        if st['user_id'] == u['id']:
            owner_tools = f"<div class='statusActions ownerOnly'><a href='/status/{st['id']}/viewers'>👁️ {st['views_count']} مشاهدة</a><a href='/status/{st['id']}/reactions'>❤️ {st['reactions_count']} تفاعل</a><a href='/status/{st['id']}/replies'>↩️ {st['replies_count']} رد</a><a class='danger' href='/status/{st['id']}/delete' onclick=\"return confirm('حذف الحالة؟')\">حذف</a></div><div class='ownerOnlyNote'>هذه التفاصيل تظهر لصاحب الحالة فقط.</div>"
        else:
            owner_tools = ""
        cards += f"""
        <div class='statusCard statusBg_{h(st['bg'] or 'blue') if not media else ''}'>
          <a href='/status/{st['id']}/view' class='statusMeta'>
            <img class='avatar' src='{av}'>
            <div class='grow'><b>{h('حالتي' if st['user_id']==u['id'] else st['name'])}</b><div class='statusTime'><strong>{h(elapsed)}</strong> · الخصوصية: {privacy_label.get(st['privacy'] or 'public','الكل')}</div></div>
          </a>
          <div class='statusProgress' style='--w:{pct}%'><i></i></div>
          {('<div class="statusPreviewText">'+text+'</div>') if text else ''}
          {media}
          {public_actions}
          {owner_tools}
        </div>"""

    body = f"""
    <div class='top'><a class='icon' href='/chats'>‹</a><b style='margin:auto'>الحالات</b><a class='icon green' href='#newStatus'>＋</a></div>
    <div class='storyRail'>{rail or '<div class=card>لا توجد حالات فعالة</div>'}</div>
    <form id='newStatus' class='statusComposer statusCreateBox' method='post' enctype='multipart/form-data'>
      <b>إضافة حالة جديدة</b>
      <div class='muted'>ارفع صورة/فيديو أو اكتب نص. الوقت سيظهر للناس بصيغة: منذ كم.</div>
      <div class='statusTypeTabs'><button type='button' class='active' onclick="statusMode('text')">نص</button><button type='button' onclick="statusMode('file')">صورة / فيديو</button></div>
      <div class='input'><textarea id='statusTextInput' name='text' placeholder='اكتب نص الحالة هنا...' oninput='updateStatusPreview()'></textarea></div>
      <div class='grid'>
        <div class='input'><select name='privacy' style='width:100%;border:1px solid #1b2e49;background:#0b1728;color:#eaf2ff;border-radius:18px;padding:14px'><option value='public'>الكل</option><option value='contacts'>جهاتي فقط</option><option value='private'>أنا فقط</option></select></div>
        <div class='input'><select id='statusBgSelect' name='bg' onchange='updateStatusPreview()' style='width:100%;border:1px solid #1b2e49;background:#0b1728;color:#eaf2ff;border-radius:18px;padding:14px'><option value='blue'>أزرق هادئ</option><option value='green'>أخضر</option><option value='purple'>بنفسجي</option><option value='dark'>داكن</option></select></div>
      </div>
      <input id='statusFileInput' type='file' name='file' accept='image/*,video/*,audio/*' onchange='previewStatusFile(this)'>
      <div id='statusPreviewPane' class='statusPreviewPane statusBg_blue'><div class='statusPreviewTextBig'>معاينة الحالة</div></div>
      <button class='btn' style='width:100%;margin-top:10px'>نشر الحالة</button>
    </form>
    <div class='statusHero'>{cards or '<div class=card>لا توجد حالات ظاهرة لك</div>'}</div>{nav('statuses')}
    <script>
    function statusMode(m){{document.getElementById('statusFileInput').style.display=m==='file'?'block':'none';document.querySelectorAll('.statusTypeTabs button').forEach((b,i)=>b.classList.toggle('active',(m==='text'&&i===0)||(m==='file'&&i===1)));}}
    let statusSelectedFileUrl='', statusSelectedFileType='', statusSelectedFileName='';
    function safeStatusText(v){{return (v||'').replace(/</g,'&lt;').replace(/>/g,'&gt;')}}
    function updateStatusPreview(){{
      let pane=document.getElementById('statusPreviewPane'), txt=document.getElementById('statusTextInput').value, bg=document.getElementById('statusBgSelect').value; if(!pane)return;
      if(statusSelectedFileUrl){{
        pane.className='statusPreviewPane show';
        let cap=txt?'<div class="statusFileCaption">'+safeStatusText(txt)+'</div>':'';
        let name=statusSelectedFileName?'<div class="statusFileName">'+safeStatusText(statusSelectedFileName)+'</div>':'';
        if(statusSelectedFileType.startsWith('image/')) pane.innerHTML='<button type="button" class="statusClearFile" onclick="clearStatusFile()">×</button><img src="'+statusSelectedFileUrl+'">'+cap;
        else if(statusSelectedFileType.startsWith('video/')) pane.innerHTML='<button type="button" class="statusClearFile" onclick="clearStatusFile()">×</button><video controls src="'+statusSelectedFileUrl+'"></video>'+cap;
        else pane.innerHTML='<div class="statusPreviewTextBig">🎵 ملف صوتي جاهز للنشر</div>'+cap+name;
        return;
      }}
      pane.className='statusPreviewPane show statusBg_'+bg; pane.innerHTML='<div class="statusPreviewTextBig">'+(txt?safeStatusText(txt):'معاينة الحالة')+'</div>';
    }}
    function previewStatusFile(inp){{let pane=document.getElementById('statusPreviewPane'); if(!pane||!inp.files||!inp.files[0])return; let f=inp.files[0]; statusSelectedFileUrl=URL.createObjectURL(f); statusSelectedFileType=f.type||''; statusSelectedFileName=f.name||''; updateStatusPreview();}}
    function clearStatusFile(){{let inp=document.getElementById('statusFileInput'); if(inp)inp.value=''; statusSelectedFileUrl=''; statusSelectedFileType=''; statusSelectedFileName=''; updateStatusPreview();}}
    statusMode('text'); updateStatusPreview();
    </script>
    """
    return page(body)


@app.route('/status/<int:sid>/view', methods=['GET','POST'])
@login_required
def view_status(sid):
    u = current_user()
    ensure_status_expiry_and_cleanup()
    st = db().execute("SELECT s.*,u.name,u.avatar,(SELECT emoji FROM status_reactions WHERE status_id=s.id AND user_id=? LIMIT 1) AS my_reaction FROM statuses s JOIN users u ON u.id=s.user_id WHERE s.id=?", (u['id'], sid)).fetchone()
    if not st or not can_view_status(st, u['id']):
        return redirect('/statuses')
    if st['expires_at'] and st['expires_at'] < now():
        return redirect('/statuses')

    if request.method == 'POST' and st['user_id'] != u['id']:
        body = request.form.get('body','').strip()
        parent_id = request.form.get('parent_id') or None
        try:
            parent_id = int(parent_id) if parent_id else None
        except Exception:
            parent_id = None
        if body:
            db().execute("INSERT INTO status_replies(status_id,sender_id,owner_id,body,parent_id,to_user_id,is_owner_reply,created_at) VALUES(?,?,?,?,?,?,0,?)", (sid, u['id'], st['user_id'], body, parent_id, st['user_id'], now()))
            notify(st['user_id'], u['id'], 'رد جديد على حالتك من ' + u['name'], '/status/' + str(sid) + '/replies', 'status', 'normal')
            db().commit()
        return redirect('/status/' + str(sid) + '/view')

    register_status_view(sid, st['user_id'], u['id'])
    media = status_media_html(st, preview=False)
    av = ('/uploads/' + st['avatar']) if st['avatar'] else 'https://ui-avatars.com/api/?background=123&color=fff&name=' + str(st['name']).replace(' ','+')
    elapsed, pct = status_remaining(st)
    views_count = db().execute("SELECT COUNT(*) c FROM status_views WHERE status_id=?", (sid,)).fetchone()['c']
    replies_count = db().execute("SELECT COUNT(*) c FROM status_replies WHERE status_id=?", (sid,)).fetchone()['c']
    reactions_count = db().execute("SELECT COUNT(*) c FROM status_reactions WHERE status_id=?", (sid,)).fetchone()['c']
    text = h(st['text'] or '')
    bgclass = 'statusBg_' + h(st['bg'] or 'blue')
    text_block = f"<div class='statusTextOnly'>{text}</div>" if text and not media else (f"<h3 style='text-align:center'>{text}</h3>" if text else '')
    owner_links = f"<div class='statusOwnerStats'><a class='statusChip' href='/status/{sid}/viewers'>👁️ {views_count} مشاهدة</a><a class='statusChip' href='/status/{sid}/reactions'>❤️ {reactions_count} تفاعل</a><a class='statusChip' href='/status/{sid}/replies'>↩️ {replies_count} رد</a><a class='statusChip danger' href='/status/{sid}/delete' onclick=\"return confirm('حذف الحالة؟')\">حذف</a></div><div class='ownerOnlyNote'>المشاهدات والتفاعلات والردود تظهر لصاحب الحالة فقط.</div>" if st['user_id'] == u['id'] else ''
    public_react = status_react_button(sid, st['my_reaction'] if 'my_reaction' in st.keys() else '')
    reply_form = '' if st['user_id'] == u['id'] else f"<div id='statusReplyHint' class='statusReplyHint'></div><form class='statusReplyBar' method='post'><input type='hidden' id='status_parent_id' name='parent_id'><input type='text' name='body' placeholder='رد على الحالة...'><button class='btn'>إرسال</button></form>"
    # الردود داخل الحالة: صاحب الحالة يرى كل الردود، والصديق يرى فقط نقاشه مع صاحب الحالة
    if st['user_id'] == u['id']:
        thread_rows = db().execute("""
            SELECT r.*, us.name AS sender_name, ut.name AS target_name, pr.body AS parent_body FROM status_replies r
            JOIN users us ON us.id=r.sender_id
            LEFT JOIN users ut ON ut.id=r.to_user_id
            LEFT JOIN status_replies pr ON pr.id=r.parent_id
            WHERE r.status_id=? ORDER BY r.id ASC
        """, (sid,)).fetchall()
    else:
        thread_rows = db().execute("""
            SELECT r.*, us.name AS sender_name, ut.name AS target_name, pr.body AS parent_body FROM status_replies r
            JOIN users us ON us.id=r.sender_id
            LEFT JOIN users ut ON ut.id=r.to_user_id
            LEFT JOIN status_replies pr ON pr.id=r.parent_id
            WHERE r.status_id=? AND (r.sender_id=? OR r.to_user_id=?) ORDER BY r.id ASC
        """, (sid, u['id'], u['id'])).fetchall()
    thread_html = ''
    for rr in thread_rows:
        cls = 'statusReplyOwner' if rr['sender_id'] == st['user_id'] else 'statusReplyMine'
        target = f"<div class='muted'>رد خاص إلى: {h(rr['target_name'] or '')}</div>" if st['user_id'] == u['id'] and rr['to_user_id'] and rr['to_user_id'] != st['user_id'] else ''
        reply_box = ''
        if st['user_id'] == u['id'] and rr['sender_id'] != u['id']:
            reply_box = f"<form class='inlineReplyForm' method='post' action='/status/{sid}/reply/{rr['id']}'><input name='body' placeholder='رد على {h(rr['sender_name'])}...'><button class='btn'>رد</button></form>"
        tm = status_reply_time_label(rr['created_at'])
        react_badge = f"<span class='replyReaction'>{h(rr['reaction'])}</span>" if ('reaction' in rr.keys() and rr['reaction']) else ''
        quote = f"<div class='replyQuote'>↩️ {h(rr['parent_body'])}</div>" if ('parent_body' in rr.keys() and rr['parent_body']) else ''
        safe_body = h(rr['body'])
        can_edit = rr['sender_id'] == u['id']
        can_delete = (rr['sender_id'] == u['id']) or (st['user_id'] == u['id'])
        menu = f"<div class='statusReplyMenu' id='statusReplyMenu_{rr['id']}' onclick='closeStatusReplyMenu({rr['id']})'><div class='statusReplySheet' onclick='event.stopPropagation()'><div class='statusReplyReacts'><button onclick=\"reactStatusReply({sid},{rr['id']},'❤️')\">❤️</button><button onclick=\"reactStatusReply({sid},{rr['id']},'👍')\">👍</button><button onclick=\"reactStatusReply({sid},{rr['id']},'😂')\">😂</button><button onclick=\"reactStatusReply({sid},{rr['id']},'😮')\">😮</button><button onclick=\"reactStatusReply({sid},{rr['id']},'😢')\">😢</button><button onclick=\"reactStatusReply({sid},{rr['id']},'🔥')\">🔥</button></div><div class='statusReplyActions'><button onclick=\"setStatusReply({rr['id']},'{safe_body}');closeStatusReplyMenu({rr['id']})\">↩️ رد</button>{('<button onclick=\"editStatusReply('+str(sid)+','+str(rr['id'])+',`'+safe_body+'`)\">✏️ تعديل</button>' if can_edit else '')}{('<button class=\"danger\" onclick=\"deleteStatusReply('+str(sid)+','+str(rr['id'])+')\">🗑️ حذف للجميع</button>' if can_delete else '')}<button class='close' onclick=\"closeStatusReplyMenu({rr['id']})\">إغلاق</button></div></div></div>"
        thread_html += f"<div class='statusReplyItem {cls}' data-rid='{rr['id']}' data-text='{safe_body}'><b>{h(rr['sender_name'])}</b>{react_badge}{target}{quote}<div class='statusReplyBody'>{safe_body}</div><small class='muted'>{h(tm)}</small>{reply_box}{menu}</div>"
    if thread_html:
        thread_html = "<div class='statusReplyList'>" + thread_html + "</div>"
    return page(f"""
    <div class='top'><a class='icon backHistory' href='/statuses' onclick='return goBackOne()'>‹</a><img class='avatar' src='{av}'><div><b>{h(st['name'])}</b><div class='muted'>{h(elapsed)}</div></div></div>
    <div class='statusFull'>
      <div class='statusTopBar' style='--w:{pct}%'><i></i></div>
      <div class='statusViewerBox {'statusTextView '+bgclass if text and not media else ''}'>{media or text_block}</div>
      {text_block if media else ''}
      <div class='statusPublicActions' style='justify-content:center'>{public_react}{('<span class=muted>'+status_reactions_summary(sid)+'</span>') if st['user_id']==u['id'] else ''}</div>
      {owner_links}
      {thread_html}
    </div>{reply_form}
    """)


@app.route('/status/<int:sid>/viewers')
@login_required
def status_viewers(sid):
    st = db().execute("SELECT * FROM statuses WHERE id=?", (sid,)).fetchone()
    if not st or st['user_id'] != session['user_id']:
        return redirect('/statuses')
    viewers = db().execute("""
        SELECT u.id,u.name,u.avatar,v.viewed_at FROM status_views v
        JOIN users u ON u.id=v.viewer_id
        WHERE v.status_id=? ORDER BY v.id DESC
    """, (sid,)).fetchall()
    rows = ''
    for v in viewers:
        av = ('/uploads/' + v['avatar']) if v['avatar'] else 'https://ui-avatars.com/api/?background=123&color=fff&name=' + str(v['name']).replace(' ','+')
        rows += f"<a class='chatitem' href='/chat/{v['id']}'><img class='avatar' src='{av}'><div class='grow'><div class='name'>{h(v['name'])}</div><div class='last'>شاهد الحالة · {h(status_reply_time_label(v['viewed_at']))}</div></div></a>"
    return page(f"<div class='top'><a class='icon backHistory' href='/statuses' onclick='return goBackOne()'>‹</a><b>مشاهدات الحالة</b></div><div class='card'><b>عدد المشاهدات: {len(viewers)}</b></div><div class='list'>{rows or '<div class=card>لا توجد مشاهدات حتى الآن</div>'}</div>")


@app.route('/status/<int:sid>/replies')
@login_required
def status_replies(sid):
    st = db().execute("SELECT * FROM statuses WHERE id=?", (sid,)).fetchone()
    if not st or st['user_id'] != session['user_id']:
        return redirect('/statuses')
    replies = db().execute("""
        SELECT r.*,u.name,u.avatar,pr.body AS parent_body,tu.name AS target_name FROM status_replies r
        JOIN users u ON u.id=r.sender_id
        LEFT JOIN status_replies pr ON pr.id=r.parent_id
        LEFT JOIN users tu ON tu.id=r.to_user_id
        WHERE r.status_id=? ORDER BY r.id DESC
    """, (sid,)).fetchall()
    rows = ''
    for r in replies:
        av = ('/uploads/' + r['avatar']) if r['avatar'] else 'https://ui-avatars.com/api/?background=123&color=fff&name=' + str(r['name']).replace(' ','+')
        body = h(r['body'])
        parent = f"<div class='statusReplyParentFrame'>↩️ رد على: {h(r['parent_body'])}</div>" if ('parent_body' in r.keys() and r['parent_body']) else ''
        target = f"<div class='muted'>رد خاص إلى: {h(r['target_name'])}</div>" if ('target_name' in r.keys() and r['target_name'] and r['to_user_id'] != st['user_id']) else ''
        rows += f"<div class='statusReplyCard'><a href='/chat/{r['sender_id']}'><img class='avatar' src='{av}'></a><div class='statusReplyContent'><div class='statusReplyHeader'><a class='name' href='/chat/{r['sender_id']}'>{h(r['name'])}</a><span class='statusReplyTime'>{h(status_reply_time_label(r['created_at']))}</span></div>{target}{parent}<div class='statusReplyMessageFrame'>{body}</div><form class='inlineReplyForm' method='post' action='/status/{sid}/reply/{r['id']}'><input name='body' placeholder='رد خاص عليه داخل الحالة...'><button class='btn'>رد</button></form></div></div>"
    empty = '<div class="statusReplyEmpty">لا توجد ردود حتى الآن</div>'
    return page(f"<div class='top'><a class='icon backHistory' href='/statuses' onclick='return goBackOne()'>‹</a><b>ردود الحالة</b></div><div class='card'><b>عدد الردود: {len(replies)}</b><div class='muted'>الردود هنا خاصة داخل الحالة، وليست رسائل محادثة.</div></div><div class='statusReplyListPage'>{rows or empty}</div>")



@app.route('/status/<int:sid>/reply/<int:rid>', methods=['POST'])
@login_required
def owner_reply_status(sid, rid):
    u = current_user()
    st = db().execute("SELECT * FROM statuses WHERE id=?", (sid,)).fetchone()
    if not st or st['user_id'] != u['id']:
        return redirect('/statuses')
    parent = db().execute("SELECT * FROM status_replies WHERE id=? AND status_id=?", (rid, sid)).fetchone()
    if not parent:
        return redirect('/status/' + str(sid) + '/replies')
    body = request.form.get('body','').strip()
    if body:
        target_id = parent['sender_id'] if parent['sender_id'] != u['id'] else (parent['to_user_id'] or parent['sender_id'])
        db().execute("INSERT INTO status_replies(status_id,sender_id,owner_id,body,parent_id,to_user_id,is_owner_reply,created_at) VALUES(?,?,?,?,?,?,1,?)", (sid, u['id'], u['id'], body, rid, target_id, now()))
        notify(target_id, u['id'], 'صاحب الحالة رد على ردك', '/status/' + str(sid) + '/view', 'status', 'normal')
        db().commit()
    return redirect('/status/' + str(sid) + '/view')


@app.route('/status/<int:sid>/reply_msg/<int:rid>/react', methods=['POST'])
@login_required
def react_status_reply_msg(sid, rid):
    u = current_user()
    st = db().execute("SELECT * FROM statuses WHERE id=?", (sid,)).fetchone()
    rr = db().execute("SELECT * FROM status_replies WHERE id=? AND status_id=?", (rid, sid)).fetchone()
    if not st or not rr or not can_view_status(st, u['id']):
        return jsonify({'ok': False}), 404
    if st['user_id'] != u['id'] and rr['sender_id'] != u['id'] and rr['to_user_id'] != u['id']:
        return jsonify({'ok': False}), 403
    emoji = request.form.get('emoji','').strip()
    if emoji not in ['❤️','👍','😂','😮','😢','🔥']:
        return jsonify({'ok': False}), 400
    db().execute("UPDATE status_replies SET reaction=? WHERE id=?", (emoji, rid))
    db().commit()
    return jsonify({'ok': True})

@app.route('/status/<int:sid>/reply_msg/<int:rid>/delete', methods=['POST'])
@login_required
def delete_status_reply_msg(sid, rid):
    u = current_user()
    st = db().execute("SELECT * FROM statuses WHERE id=?", (sid,)).fetchone()
    rr = db().execute("SELECT * FROM status_replies WHERE id=? AND status_id=?", (rid, sid)).fetchone()
    if st and rr and (rr['sender_id'] == u['id'] or st['user_id'] == u['id']):
        db().execute("DELETE FROM status_replies WHERE id=? OR parent_id=?", (rid, rid))
        db().commit()
    return jsonify({'ok': True})

@app.route('/status/<int:sid>/reply_msg/<int:rid>/edit', methods=['POST'])
@login_required
def edit_status_reply_msg(sid, rid):
    u = current_user()
    rr = db().execute("SELECT * FROM status_replies WHERE id=? AND status_id=?", (rid, sid)).fetchone()
    body = request.form.get('body','').strip()
    if rr and rr['sender_id'] == u['id'] and body:
        db().execute("UPDATE status_replies SET body=?, edited_at=? WHERE id=?", (body, now(), rid))
        db().commit()
    return jsonify({'ok': True})

@app.route('/status/<int:sid>/delete')
@login_required
def delete_status(sid):
    st = db().execute("SELECT * FROM statuses WHERE id=?", (sid,)).fetchone()
    if st and st['user_id'] == session['user_id']:
        db().execute("DELETE FROM status_views WHERE status_id=?", (sid,))
        db().execute("DELETE FROM status_replies WHERE status_id=?", (sid,))
        db().execute("DELETE FROM status_reactions WHERE status_id=?", (sid,))
        db().execute("DELETE FROM statuses WHERE id=?", (sid,))
        db().commit()
    return redirect('/statuses')


@app.route('/calls')
@login_required
def calls():
    u = current_user()
    if 'service_calls_enabled' in u.keys() and not u['service_calls_enabled']:
        return page("<div class='top'><a class='icon' href='/services'>‹</a><b>المكالمات متوقفة</b></div><div class='card'>خدمة المكالمات متوقفة من الإعدادات. <a class='btn' href='/services'>تشغيلها الآن</a></div>")
    rows_db = db().execute("""
        SELECT c.*, usr.name, usr.avatar
        FROM calls c
        JOIN users usr ON usr.id = CASE WHEN c.caller_id=? THEN c.receiver_id ELSE c.caller_id END
        WHERE c.caller_id=? OR c.receiver_id=?
        ORDER BY c.id DESC
    """, (u['id'], u['id'], u['id'])).fetchall()
    rows = ''
    for c in rows_db:
        peer_id = c['receiver_id'] if c['caller_id'] == u['id'] else c['caller_id']
        incoming = c['receiver_id'] == u['id']
        icon = '📹' if c['call_type'] == 'video' else '📞'
        typ_label = 'مكالمة فيديو' if c['call_type'] == 'video' else 'مكالمة صوتية'
        status = c['status'] or 'منتهية'
        if status == 'رنين' and incoming:
            detail = 'مكالمة واردة تنتظر الرد'
            actions = f"<div style='display:flex;gap:8px;margin-top:8px'><a class='btn' href='/call_accept/{c['id']}'>قبول</a><a class='btn' style='background:#ef4444' href='/call_decline/{c['id']}'>رفض</a></div>"
            href = f"/incoming_call/{c['id']}"
        elif status == 'رنين':
            detail = 'جاري الرنين عند الطرف الآخر'
            actions = f"<div style='margin-top:8px'><a class='btn' style='background:#ef4444' href='/call_end/{c['id']}?back=calls'>إلغاء</a></div>"
            href = f"/call_room/{c['id']}"
        else:
            dur = ''
            if c['duration_seconds']:
                m, sec = divmod(int(c['duration_seconds']), 60)
                dur = f" · المدة {m}:{sec:02d}"
            detail = f"{status}{dur}"
            actions = ''
            href = f"/call_room/{c['id']}"
        av = ('/uploads/' + c['avatar']) if c['avatar'] else 'https://ui-avatars.com/api/?background=123&color=fff&name=' + str(c['name']).replace(' ','+')
        rows += f"<div class='chatitem'><a href='{href}' style='display:flex;align-items:center;gap:12px;flex:1'><img class='avatar' src='{av}'><div class='grow'><div class='name'>{icon} {c['name']}</div><div class='last'>{typ_label} · {c['created_at'][11:16]} · {detail}</div></div></a>{actions}</div>"
    return page(f"<div class='top'><a class='icon' href='/chats'>‹</a><b style='margin:auto'>المكالمات</b></div><div class='list'>{rows or '<div class=card>لا توجد مكالمات</div>'}</div>{nav('calls')}")


@app.route('/call/<int:peer>/<typ>')
@login_required
def call(peer, typ):
    u = current_user()
    p = db().execute("SELECT * FROM users WHERE id=?", (peer,)).fetchone()
    if not p or peer == u['id']:
        return redirect('/chats')
    if is_blocked_between(u['id'], peer):
        return page(f"<div class='top'><a class='icon' href='/chat/{peer}'>‹</a><b>المكالمة ممنوعة</b></div><div class='card'>لا يمكن بدء المكالمة لأن الحظر مفعل بينكما.</div>")
    typ = 'video' if typ == 'video' else 'audio'
    cur = db().execute("INSERT INTO calls(caller_id,receiver_id,call_type,status,created_at) VALUES(?,?,?,?,?)", (u['id'], peer, typ, 'رنين', now()))
    db().commit()
    notify(peer, u['id'], ('مكالمة فيديو واردة' if typ == 'video' else 'مكالمة صوتية واردة') + ' من ' + u['name'], '/incoming_call/' + str(cur.lastrowid), 'call', 'high')
    return redirect('/call_room/' + str(cur.lastrowid))


@app.route('/incoming_call/<int:call_id>')
@login_required
def incoming_call(call_id):
    u = current_user()
    c = db().execute("SELECT * FROM calls WHERE id=? AND receiver_id=?", (call_id, u['id'])).fetchone()
    if not c:
        return redirect('/calls')
    p = db().execute("SELECT * FROM users WHERE id=?", (c['caller_id'],)).fetchone()
    if not p:
        return redirect('/calls')
    if c['status'] != 'رنين':
        return redirect('/call_room/' + str(call_id))
    icon = '📹' if c['call_type'] == 'video' else '📞'
    return page(f"<div class='top'><a class='icon' href='/calls'>‹</a><b>مكالمة واردة</b></div><div class='card' style='text-align:center;margin-top:60px'><img class='avatar' style='width:130px;height:130px' src='{avatar_url(p)}'><h2>{p['name']}</h2><p class='status'>{icon} {'مكالمة فيديو واردة' if c['call_type']=='video' else 'مكالمة صوتية واردة'}</p><div class='callBtns'><a class='btn' href='/call_accept/{call_id}'>قبول</a><a class='btn' style='background:#ef4444' href='/call_decline/{call_id}'>رفض</a><a class='btn gray' href='/calls'>رجوع</a></div></div>")


@app.route('/call_accept/<int:call_id>')
@login_required
def call_accept(call_id):
    c = db().execute("SELECT * FROM calls WHERE id=? AND receiver_id=?", (call_id, session['user_id'])).fetchone()
    if not c:
        return redirect('/calls')
    if c['status'] == 'رنين':
        db().execute("UPDATE calls SET status='جارية', accepted_at=COALESCE(accepted_at, ?) WHERE id=?", (now(), call_id))
        db().commit()
        notify(c['caller_id'], session['user_id'], 'تم قبول المكالمة', '/call_room/' + str(call_id), 'call', 'high')
    return redirect('/call_room/' + str(call_id))


@app.route('/call_decline/<int:call_id>')
@login_required
def call_decline(call_id):
    c = db().execute("SELECT * FROM calls WHERE id=? AND receiver_id=?", (call_id, session['user_id'])).fetchone()
    if c and c['status'] == 'رنين':
        db().execute("UPDATE calls SET status='مرفوضة', declined_by=?, ended_at=? WHERE id=?", (session['user_id'], now(), call_id))
        db().commit()
        notify(c['caller_id'], session['user_id'], 'تم رفض المكالمة', '/calls', 'call', 'high')
    return redirect('/calls')


@app.route('/call_room/<int:call_id>')
@login_required
def call_room(call_id):
    u = current_user()
    c = db().execute("SELECT * FROM calls WHERE id=? AND (caller_id=? OR receiver_id=?)", (call_id, u['id'], u['id'])).fetchone()
    if not c:
        return redirect('/calls')
    if c['receiver_id'] == u['id'] and c['status'] == 'رنين':
        return redirect('/incoming_call/' + str(call_id))
    peer_id = c['receiver_id'] if c['caller_id'] == u['id'] else c['caller_id']
    p = db().execute("SELECT * FROM users WHERE id=?", (peer_id,)).fetchone()
    if not p:
        return redirect('/calls')
    if c['status'] in ('مرفوضة', 'منتهية', 'فائتة'):
        return page(f"<div class='top'><a class='icon' href='/calls'>‹</a><b>تفاصيل المكالمة</b></div><div class='card'><h3>{p['name']}</h3><p>الحالة: {c['status']}</p><p>النوع: {'فيديو' if c['call_type']=='video' else 'صوت'}</p><p>الوقت: {c['created_at']}</p><a class='btn' href='/call/{peer_id}/{c['call_type']}'>إعادة الاتصال</a></div>")
    is_caller = 'true' if c['caller_id'] == u['id'] else 'false'
    video_html = "<video id='remoteVideo' autoplay playsinline style='width:100%;height:300px;background:#020814;border-radius:22px;object-fit:cover'></video><video id='localVideo' autoplay muted playsinline style='width:120px;height:160px;background:#111;border-radius:18px;object-fit:cover;position:absolute;top:95px;left:22px;border:2px solid #24405f'></video>" if c['call_type'] == 'video' else "<div class='card' style='text-align:center;margin-top:40px'><img class='avatar' style='width:130px;height:130px' src='" + avatar_url(p) + "'><h2>" + p['name'] + "</h2><p class='status'>مكالمة صوتية WebRTC</p><audio id='remoteAudio' autoplay></audio></div>"
    script = f"""
<script>
const CALL_ID={call_id}, IS_CALLER={is_caller}, CALL_TYPE='{c['call_type']}';
let pc, localStream, lastSignal=0, micOn=true, camOn=true;
const cfg={{iceServers:[{{urls:'stun:stun.l.google.com:19302'}}]}};
async function postSignal(obj){{await fetch('/call_signal/'+CALL_ID,{{method:'POST',headers:{{'Content-Type':'application/json'}},body:JSON.stringify(obj)}})}}
async function refreshStatus(){{
  const r=await fetch('/call_status/'+CALL_ID); const s=await r.json();
  if(s.status==='مرفوضة'||s.status==='منتهية'||s.status==='فائتة'){{ location.href='/calls'; return false; }}
  if(s.status==='رنين' && IS_CALLER){{ document.getElementById('callStatus').innerText='يرن الآن...'; return false; }}
  return true;
}}
async function startCall(){{
  try{{
    const ok = await refreshStatus();
    if(IS_CALLER && !ok){{ setInterval(async()=>{{ const ready=await refreshStatus(); if(ready && !pc) startCall(); }},1500); return; }}
    localStream = await navigator.mediaDevices.getUserMedia({{audio:true, video: CALL_TYPE==='video'}});
    if(CALL_TYPE==='video') document.getElementById('localVideo').srcObject=localStream;
    pc = new RTCPeerConnection(cfg);
    localStream.getTracks().forEach(t=>pc.addTrack(t, localStream));
    pc.ontrack = e=>{{ if(CALL_TYPE==='video') document.getElementById('remoteVideo').srcObject=e.streams[0]; else document.getElementById('remoteAudio').srcObject=e.streams[0]; }};
    pc.onicecandidate = e=>{{if(e.candidate) postSignal({{type:'candidate',candidate:e.candidate}})}};
    if(IS_CALLER){{ const offer=await pc.createOffer(); await pc.setLocalDescription(offer); await postSignal({{type:'offer',sdp:offer}}); document.getElementById('callStatus').innerText='جاري الاتصال...'; }}
    else {{ document.getElementById('callStatus').innerText='تم قبول المكالمة، جاري الاتصال...'; }}
    pollSignals(); setInterval(pollSignals,1000); setInterval(refreshStatus,2500);
  }}catch(err){{document.getElementById('callStatus').innerText='اسمح للكاميرا/الميكروفون أو افتح من localhost/https'; console.log(err)}}
}}
async function pollSignals(){{
  const r=await fetch('/call_signals/'+CALL_ID+'?after='+lastSignal); const arr=await r.json();
  for(const item of arr){{ lastSignal=Math.max(lastSignal,item.id); const msg=JSON.parse(item.data);
    if(!pc) continue;
    if(msg.type==='offer' && !IS_CALLER){{ await pc.setRemoteDescription(new RTCSessionDescription(msg.sdp)); const ans=await pc.createAnswer(); await pc.setLocalDescription(ans); await postSignal({{type:'answer',sdp:ans}}); document.getElementById('callStatus').innerText='تم الاتصال'; }}
    if(msg.type==='answer' && IS_CALLER){{ await pc.setRemoteDescription(new RTCSessionDescription(msg.sdp)); document.getElementById('callStatus').innerText='تم الاتصال'; }}
    if(msg.type==='candidate'){{ try{{ await pc.addIceCandidate(new RTCIceCandidate(msg.candidate)); }}catch(e){{}} }}
    if(msg.type==='hangup'){{ location.href='/calls'; }}
  }}
}}
function toggleMic(){{micOn=!micOn; localStream?.getAudioTracks().forEach(t=>t.enabled=micOn); document.getElementById('micBtn').innerText=micOn?'🎙️ كتم':'🔇 تشغيل'}}
function toggleCam(){{camOn=!camOn; localStream?.getVideoTracks().forEach(t=>t.enabled=camOn); document.getElementById('camBtn').innerText=camOn?'📹 إيقاف':'📷 تشغيل'}}
async function endCall(){{await postSignal({{type:'hangup'}}); await fetch('/call_end/'+CALL_ID); location.href='/chat/{peer_id}';}}
startCall();
</script>"""
    body = f"<div class='top'><a class='icon' href='/chat/{peer_id}'>‹</a><img class='avatar' src='{avatar_url(p)}'><div class='header-name'><b>{p['name']}</b><div class='status' id='callStatus'>{'يرن الآن...' if c['status']=='رنين' else 'بدء المكالمة...'}</div></div></div><div style='position:relative;padding:16px'>{video_html}<div class='card'><div class='callBtns'><button class='btn gray' id='micBtn' onclick='toggleMic()'>🎙️ كتم</button><button class='btn gray' id='camBtn' onclick='toggleCam()'>📹 إيقاف</button><button class='btn' style='background:#ef4444' onclick='endCall()'>إنهاء</button></div><p class='muted'>المرحلة 6: الاتصال صار فيه قبول/رفض وحالة رنين ومدة للمكالمة.</p></div></div>{script}"
    return page(body)


@app.route('/call_status/<int:call_id>')
@login_required
def call_status(call_id):
    c = db().execute("SELECT status FROM calls WHERE id=? AND (caller_id=? OR receiver_id=?)", (call_id, session['user_id'], session['user_id'])).fetchone()
    return jsonify({'status': c['status'] if c else 'غير موجود'})


@app.route('/call_signal/<int:call_id>', methods=['POST'])
@login_required
def call_signal(call_id):
    c = db().execute("SELECT id FROM calls WHERE id=? AND (caller_id=? OR receiver_id=?)", (call_id, session['user_id'], session['user_id'])).fetchone()
    if not c:
        return jsonify({'ok': False}), 403
    import json
    db().execute("INSERT INTO call_signals(call_id,user_id,data,created_at) VALUES(?,?,?,?)", (call_id, session['user_id'], json.dumps(request.get_json(force=True), ensure_ascii=False), now()))
    db().commit()
    return jsonify({'ok': True})


@app.route('/call_signals/<int:call_id>')
@login_required
def call_signals(call_id):
    after = int(request.args.get('after', '0') or 0)
    c = db().execute("SELECT id FROM calls WHERE id=? AND (caller_id=? OR receiver_id=?)", (call_id, session['user_id'], session['user_id'])).fetchone()
    if not c:
        return jsonify([])
    rows = db().execute("SELECT id,data FROM call_signals WHERE call_id=? AND id>? AND user_id!=? ORDER BY id", (call_id, after, session['user_id'])).fetchall()
    return jsonify([dict(r) for r in rows])


@app.route('/call_end/<int:call_id>')
@login_required
def call_end(call_id):
    c = db().execute("SELECT * FROM calls WHERE id=? AND (caller_id=? OR receiver_id=?)", (call_id, session['user_id'], session['user_id'])).fetchone()
    if c:
        status = 'منتهية' if c['accepted_at'] else 'فائتة'
        duration = 0
        if c['accepted_at']:
            try:
                start = datetime.strptime(c['accepted_at'], '%Y-%m-%d %H:%M:%S')
                duration = max(0, int((datetime.now() - start).total_seconds()))
            except Exception:
                duration = 0
        db().execute("UPDATE calls SET status=?, ended_at=?, duration_seconds=? WHERE id=?", (status, now(), duration, call_id))
        db().commit()
    if request.args.get('back') == 'calls':
        return redirect('/calls')
    return 'ok'

@app.route('/notifications')
@login_required
def notifications():
    u = current_user()
    process_due_reminders(u['id'])
    rows = db().execute("SELECT n.*,u.name,u.avatar FROM notifications n LEFT JOIN users u ON u.id=n.actor_id WHERE n.user_id=? ORDER BY n.id DESC LIMIT 100", (u['id'],)).fetchall()
    html = ''
    icons = {'message':'💬', 'status':'◎', 'call':'📞', 'reminder':'⏰', 'general':'🔔'}
    for n in rows:
        icon = icons.get(n['type'] or 'general', '🔔') if 'type' in n.keys() else '🔔'
        priority = n['priority'] if 'priority' in n.keys() else 'normal'
        av = ('/uploads/' + n['avatar']) if n['avatar'] else 'https://ui-avatars.com/api/?background=123&color=fff&name=' + str(n['name'] or 'واصل').replace(' ','+')
        new_badge = '' if n['is_read'] else '<span class=badge>جديد</span>'
        pr = ' · مهم' if priority == 'high' else ''
        html += f"<a class='chatitem' href='{n['link'] or '#'}'><img class='avatar' src='{av}'><div class='grow'><div class='name'>{icon} {h(n['text'])}</div><div class='last'>{n['created_at']}{pr}</div></div>{new_badge}</a>"
    db().execute("UPDATE notifications SET is_read=1 WHERE user_id=?", (u['id'],)); db().commit()
    tools = "<div class='card' style='display:flex;gap:8px;flex-wrap:wrap'><a class='btn gray' href='/notifications/settings'>إعدادات التنبيهات</a><a class='btn gray' href='/notifications/mark_read'>تعليم الكل كمقروء</a><a class='btn' style='background:#ef4444' href='/notifications/clear'>حذف الكل</a></div>"
    return page(f"<div class='top'><a class='icon' href='/chats'>‹</a><b style='margin:auto'>الإشعارات</b></div>{tools}<div class='list'>{html or '<div class=card>لا توجد إشعارات</div>'}</div>{nav('notifications')}")

@app.route('/notifications/mark_read')
@login_required
def notifications_mark_read():
    db().execute('UPDATE notifications SET is_read=1 WHERE user_id=?', (session['user_id'],))
    db().commit()
    return redirect('/notifications')

@app.route('/notifications/clear')
@login_required
def notifications_clear():
    db().execute('DELETE FROM notifications WHERE user_id=?', (session['user_id'],))
    db().commit()
    return redirect('/notifications')



def onoff(v):
    return 'مفعلة' if int(v or 0) else 'متوقفة'


def service_card(icon, title, desc, status, link):
    st = '✅ ' + status if 'مفعلة' in status or 'جاهزة' in status else '⚠️ ' + status
    return f"<a class='chatitem' href='{link}'><div class='icon'>{icon}</div><div class='grow'><div class='name'>{title}</div><div class='last'>{desc}</div></div><span class='badge'>{st}</span></a>"


@app.route('/settings')
@login_required
def settings_home():
    u=current_user()
    body=f"""<div class='top'><a class='icon' href='/me'>‹</a><b>الإعدادات</b></div>
    <div class='card'><div class='profileRow'><img class='avatar' src='{avatar_url(u)}'><div><b>{h(u['name'])}</b><div class='muted'>{h(u['username'] or '')}</div></div></div></div>
    <div class='card'>
      <a class='chatitem' href='/account_settings'><div class='icon'>👤</div><div class='grow'><div class='name'>الحساب</div><div class='last'>الاسم، النبذة، الصورة، كلمة المرور</div></div></a>
      <a class='chatitem' href='/privacy'><div class='icon'>🔒</div><div class='grow'><div class='name'>الخصوصية</div><div class='last'>آخر ظهور، الصورة، مؤشرات القراءة</div></div></a>
      <a class='chatitem' href='/notifications/settings'><div class='icon'>🔔</div><div class='grow'><div class='name'>الإشعارات</div><div class='last'>تنبيهات الرسائل والحالات والمكالمات</div></div></a>
      <a class='chatitem' href='/appearance'><div class='icon'>🎨</div><div class='grow'><div class='name'>المظهر</div><div class='last'>الوضع الداكن، حجم الخط، لون التطبيق</div></div></a>
      <a class='chatitem' href='/storage'><div class='icon'>💾</div><div class='grow'><div class='name'>التخزين والملفات</div><div class='last'>التحميل التلقائي وحفظ الوسائط</div></div></a>
      <a class='chatitem' href='/services'><div class='icon'>🧩</div><div class='grow'><div class='name'>الخدمات الموجودة</div><div class='last'>تشغيل المحادثات، الحالات، المكالمات، الإشعارات</div></div></a>
      <a class='chatitem' href='/security_check'><div class='icon'>🛡️</div><div class='grow'><div class='name'>فحص الأمان والاستقرار</div><div class='last'>فحص سريع للجداول والخدمات</div></div></a>
    </div>{nav('me')}"""
    return page(body)


@app.route('/account_settings', methods=['GET','POST'])
@login_required
def account_settings():
    u=current_user(); msg=''
    if request.method=='POST':
        name=request.form.get('name',u['name']).strip()[:80]
        about=request.form.get('about',u['about'] or '').strip()[:160]
        country=request.form.get('country',u['country'] or '').strip()[:50]
        file=request.files.get('avatar'); avatar=u['avatar']
        if file and file.filename and allowed(file.filename):
            avatar=str(int(datetime.now().timestamp()))+'_'+secure_filename(file.filename); file.save(os.path.join(UPLOAD_DIR,avatar))
        db().execute('UPDATE users SET name=?, about=?, country=?, avatar=? WHERE id=?',(name,about,country,avatar,u['id']))
        db().commit(); msg='تم حفظ بيانات الحساب'; u=current_user()
    body=f"""<div class='top'><a class='icon' href='/settings'>‹</a><b>إعدادات الحساب</b></div>
    <form class='card' method='post' enctype='multipart/form-data'><p class='muted'>{msg or 'عدّل بيانات حسابك.'}</p>
    <div class='profileRow'><img class='avatar' style='width:72px;height:72px' src='{avatar_url(u)}'><div><b>{h(u['name'])}</b><div class='muted'>{h(u['email'] or u['phone'] or '')}</div></div></div>
    <div class='input'><input name='name' value='{h(u['name'])}' placeholder='الاسم'></div>
    <div class='input'><input name='about' value='{h(u['about'])}' placeholder='النبذة'></div>
    <div class='input'><input name='country' value='{h(u['country'])}' placeholder='الدولة'></div>
    <input type='file' name='avatar'><br><br><button class='btn'>حفظ</button></form>
    <div class='card'><a class='chatitem' href='/change_password'>🔑 تغيير كلمة المرور</a></div>"""
    return page(body)


@app.route('/appearance', methods=['GET','POST'])
@login_required
def appearance():
    u=current_user(); msg=''
    if request.method=='POST':
        theme=request.form.get('theme_mode','dark')
        font=request.form.get('font_size','normal')
        accent=request.form.get('accent_color','blue')
        if theme not in ['dark','darker']: theme='dark'
        if font not in ['small','normal','large']: font='normal'
        if accent not in ['blue','green','purple']: accent='blue'
        db().execute('UPDATE users SET theme_mode=?, font_size=?, accent_color=? WHERE id=?',(theme,font,accent,u['id']))
        db().commit(); msg='تم حفظ إعدادات المظهر'; u=current_user()
    def sel(cur,val): return 'selected' if cur==val else ''
    body=f"""<div class='top'><a class='icon' href='/settings'>‹</a><b>المظهر</b></div>
    <form class='card' method='post'><p class='muted'>{msg or 'إعدادات شكل التطبيق.'}</p>
    <label>الوضع</label><div class='input'><select name='theme_mode' style='width:100%;background:#0b1728;color:white;border:1px solid #1b2e49;border-radius:18px;padding:14px'><option value='dark' {sel(u['theme_mode'],'dark')}>داكن مريح</option><option value='darker' {sel(u['theme_mode'],'darker')}>داكن أكثر</option></select></div>
    <label>حجم الخط</label><div class='input'><select name='font_size' style='width:100%;background:#0b1728;color:white;border:1px solid #1b2e49;border-radius:18px;padding:14px'><option value='small' {sel(u['font_size'],'small')}>صغير</option><option value='normal' {sel(u['font_size'],'normal')}>عادي</option><option value='large' {sel(u['font_size'],'large')}>كبير</option></select></div>
    <label>لون التطبيق</label><div class='input'><select name='accent_color' style='width:100%;background:#0b1728;color:white;border:1px solid #1b2e49;border-radius:18px;padding:14px'><option value='blue' {sel(u['accent_color'],'blue')}>أزرق</option><option value='green' {sel(u['accent_color'],'green')}>أخضر هادئ</option><option value='purple' {sel(u['accent_color'],'purple')}>بنفسجي</option></select></div>
    <button class='btn'>حفظ</button></form>"""
    return page(body)


@app.route('/storage', methods=['GET','POST'])
@login_required
def storage_settings():
    u=current_user(); msg=''
    total_files=0; total_size=0
    try:
        for name in os.listdir(UPLOAD_DIR):
            fp=os.path.join(UPLOAD_DIR,name)
            if os.path.isfile(fp):
                total_files+=1; total_size+=os.path.getsize(fp)
    except Exception: pass
    if request.method=='POST':
        auto=1 if request.form.get('media_autodownload') else 0
        gallery=1 if request.form.get('save_media_gallery') else 0
        db().execute('UPDATE users SET media_autodownload=?, save_media_gallery=? WHERE id=?',(auto,gallery,u['id']))
        db().commit(); msg='تم حفظ إعدادات التخزين'; u=current_user()
    def chk(v): return 'checked' if v else ''
    mb=round(total_size/1024/1024,2)
    body=f"""<div class='top'><a class='icon' href='/settings'>‹</a><b>التخزين والملفات</b></div>
    <div class='card'><b>استخدام الملفات</b><p class='muted'>عدد الملفات: {total_files} · الحجم التقريبي: {mb} MB</p></div>
    <form class='card' method='post'><p class='muted'>{msg or 'تحكم بالوسائط والتحميل.'}</p>
    <label class='chatitem'><input type='checkbox' name='media_autodownload' {chk(u['media_autodownload'])}> 📥 تحميل الوسائط تلقائيًا</label>
    <label class='chatitem'><input type='checkbox' name='save_media_gallery' {chk(u['save_media_gallery'])}> 🖼️ حفظ الوسائط في المعرض</label>
    <button class='btn'>حفظ</button></form>"""
    return page(body)


@app.route('/services', methods=['GET','POST'])
@login_required
def services_settings():
    u=current_user(); msg=''
    if request.method=='POST':
        chat=1 if request.form.get('service_chat_enabled') else 0
        status=1 if request.form.get('service_status_enabled') else 0
        calls=1 if request.form.get('service_calls_enabled') else 0
        db().execute('UPDATE users SET service_chat_enabled=?, service_status_enabled=?, service_calls_enabled=? WHERE id=?',(chat,status,calls,u['id']))
        db().commit(); msg='تم حفظ تشغيل الخدمات'; u=current_user()
    counts={}
    counts['contacts']=db().execute('SELECT COUNT(*) c FROM contacts WHERE user_id=?',(u['id'],)).fetchone()['c']
    counts['messages']=db().execute('SELECT COUNT(*) c FROM messages WHERE sender_id=? OR receiver_id=?',(u['id'],u['id'])).fetchone()['c']
    counts['statuses']=db().execute('SELECT COUNT(*) c FROM statuses WHERE user_id=?',(u['id'],)).fetchone()['c']
    counts['calls']=db().execute('SELECT COUNT(*) c FROM calls WHERE caller_id=? OR receiver_id=?',(u['id'],u['id'])).fetchone()['c']
    def chk(v): return 'checked' if v else ''
    body=f"""<div class='top'><a class='icon' href='/settings'>‹</a><b>الخدمات الموجودة</b></div>
    <div class='card'><p class='muted'>{msg or 'تشغيل وتعطيل الخدمات على حسابك بدون حذف البيانات.'}</p>
    {service_card('💬','المحادثات','الرسائل وجهات الاتصال · '+str(counts['messages'])+' رسالة',onoff(u['service_chat_enabled']),'/chats')}
    {service_card('◎','الحالات','حالاتي المنشورة · '+str(counts['statuses'])+' حالة',onoff(u['service_status_enabled']),'/statuses')}
    {service_card('📞','المكالمات','سجل المكالمات · '+str(counts['calls'])+' مكالمة',onoff(u['service_calls_enabled']),'/calls')}
    {service_card('🔔','الإشعارات','عداد وتنبيهات ذكية', 'جاهزة', '/notifications')}
    </div>
    <form class='card' method='post'>
    <label class='chatitem'><input type='checkbox' name='service_chat_enabled' {chk(u['service_chat_enabled'])}> 💬 تشغيل المحادثات</label>
    <label class='chatitem'><input type='checkbox' name='service_status_enabled' {chk(u['service_status_enabled'])}> ◎ تشغيل الحالات</label>
    <label class='chatitem'><input type='checkbox' name='service_calls_enabled' {chk(u['service_calls_enabled'])}> 📞 تشغيل المكالمات</label>
    <button class='btn'>حفظ</button></form>"""
    return page(body)


@app.route('/security_check')
@login_required
def security_check():
    checks=[]
    required={
      'users':['name','password_hash','theme_mode','service_chat_enabled'],
      'messages':['sender_id','receiver_id','reminder_at','pinned'],
      'statuses':['user_id','privacy','expires_at'],
      'calls':['caller_id','receiver_id','status','duration_seconds'],
      'notifications':['user_id','type','priority']
    }
    for table, cols in required.items():
        try:
            have=[r[1] for r in db().execute(f'PRAGMA table_info({table})').fetchall()]
            missing=[c for c in cols if c not in have]
            checks.append((table, not missing, ', '.join(missing)))
        except Exception as e:
            checks.append((table, False, str(e)))
    rows=''.join([f"<div class='chatitem'><div class='icon'>{'✅' if ok else '⚠️'}</div><div class='grow'><div class='name'>{table}</div><div class='last'>{'جاهز' if ok else 'ناقص: '+miss}</div></div></div>" for table,ok,miss in checks])
    return page(f"<div class='top'><a class='icon' href='/settings'>‹</a><b>فحص الأمان والاستقرار</b></div><div class='card'>{rows}</div>")

@app.route('/notifications/settings', methods=['GET','POST'])
@login_required
def notification_settings():
    u = current_user(); msg = ''
    if request.method == 'POST':
        nm = 1 if request.form.get('notify_messages') else 0
        ns = 1 if request.form.get('notify_statuses') else 0
        nc = 1 if request.form.get('notify_calls') else 0
        db().execute('UPDATE users SET notify_messages=?, notify_statuses=?, notify_calls=? WHERE id=?', (nm, ns, nc, u['id']))
        db().commit(); msg = 'تم حفظ إعدادات التنبيهات'; u = current_user()
    def chk(v): return 'checked' if v else ''
    body = f"<div class='top'><a class='icon' href='/notifications'>‹</a><b>إعدادات التنبيهات</b></div><form class='card' method='post'><p class='muted'>{msg or 'اختر التنبيهات التي تريد استقبالها.'}</p><label class='chatitem'><input type='checkbox' name='notify_messages' {chk(u['notify_messages'])}> 💬 تنبيهات الرسائل</label><label class='chatitem'><input type='checkbox' name='notify_statuses' {chk(u['notify_statuses'])}> ◎ تنبيهات الحالات والردود</label><label class='chatitem'><input type='checkbox' name='notify_calls' {chk(u['notify_calls'])}> 📞 تنبيهات المكالمات</label><button class='btn'>حفظ</button></form>"
    return page(body)

@app.route('/change_password', methods=['GET','POST'])
@login_required
def change_password():
    u=current_user(); msg=''
    if request.method=='POST':
        old=request.form.get('old',''); new=request.form.get('new',''); new2=request.form.get('new2','')
        if not check_password_hash(u['password_hash'], old): msg='كلمة المرور الحالية غير صحيحة'
        elif new != new2: msg='تأكيد كلمة المرور غير مطابق'
        elif len(new) < 6: msg='كلمة المرور قصيرة'
        else:
            db().execute("UPDATE users SET password_hash=? WHERE id=?", (generate_password_hash(new), u['id'])); db().commit(); msg='تم تغيير كلمة المرور'
    return page(f"<div class='top'><a class='icon' href='/me'>‹</a><b>تغيير كلمة المرور</b></div><form class='card' method='post'><p class='muted'>{msg}</p><div class='input'><input type='password' name='old' placeholder='كلمة المرور الحالية'></div><div class='input'><input type='password' name='new' placeholder='كلمة المرور الجديدة'></div><div class='input'><input type='password' name='new2' placeholder='تأكيد كلمة المرور'></div><button class='btn'>حفظ</button></form>")

@app.route('/privacy', methods=['GET','POST'])
@login_required
def privacy():
    u=current_user(); msg=''
    if request.method=='POST':
        last=request.form.get('last','everyone'); avatar=request.form.get('avatar','everyone'); receipts=1 if request.form.get('read_receipts') else 0
        db().execute("UPDATE users SET privacy_last_seen=?, privacy_avatar=?, read_receipts=? WHERE id=?", (last, avatar, receipts, u['id'])); db().commit(); msg='تم حفظ الخصوصية'; u=current_user()
    def opts(val):
        return ''.join([f"<option value='{x}' {'selected' if val==x else ''}>{label}</option>" for x,label in [('everyone','الجميع'),('contacts','جهاتي فقط'),('none','لا أحد')]])
    rr = 'checked' if u['read_receipts'] else ''
    return page(f"<div class='top'><a class='icon' href='/settings'>‹</a><b>الخصوصية</b></div><form class='card' method='post'><p class='muted'>{msg}</p><label>آخر ظهور</label><div class='input'><select name='last' style='width:100%;background:#0b1728;color:white;border:1px solid #1b2e49;border-radius:18px;padding:14px'>{opts(u['privacy_last_seen'] or 'everyone')}</select></div><label>صورة الحساب</label><div class='input'><select name='avatar' style='width:100%;background:#0b1728;color:white;border:1px solid #1b2e49;border-radius:18px;padding:14px'>{opts(u['privacy_avatar'] or 'everyone')}</select></div><label class='chatitem'><input type='checkbox' name='read_receipts' {rr}> ✓✓ مؤشرات قراءة الرسائل</label><button class='btn'>حفظ</button></form>")


def profile_stats(uid):
    try:
        return {
            'contacts': db().execute('SELECT COUNT(*) c FROM contacts WHERE user_id=?', (uid,)).fetchone()['c'],
            'messages': db().execute('SELECT COUNT(*) c FROM messages WHERE (sender_id=? OR receiver_id=?) AND deleted_for_all=0', (uid, uid)).fetchone()['c'],
            'statuses': db().execute('SELECT COUNT(*) c FROM statuses WHERE user_id=?', (uid,)).fetchone()['c'],
            'calls': db().execute('SELECT COUNT(*) c FROM calls WHERE caller_id=? OR receiver_id=?', (uid, uid)).fetchone()['c'],
        }
    except Exception:
        return {'contacts':0,'messages':0,'statuses':0,'calls':0}


def account_health(u):
    checks=[]
    checks.append(('البريد مؤكد', bool((not u['email']) or u['is_verified'])))
    checks.append(('كلمة المرور محفوظة بتشفير', bool(u['password_hash'])))
    checks.append(('الخصوصية مضبوطة', bool(u['privacy_last_seen'] and u['privacy_avatar'])))
    checks.append(('الإشعارات قابلة للتحكم', True))
    ok=sum(1 for _,v in checks if v)
    rows=''.join([f"<div class='chatitem'><div class='icon'>{'✅' if v else '⚠️'}</div><div class='grow'><div class='name'>{h(k)}</div><div class='last'>{'مكتمل' if v else 'يحتاج ضبط'}</div></div></div>" for k,v in checks])
    return ok, len(checks), rows

@app.route('/me', methods=['GET','POST'])
@login_required
def me():
    u=current_user()
    if request.method=='POST':
        name=request.form.get('name',u['name']).strip()[:80]
        about=request.form.get('about',u['about'] or '').strip()[:160]
        location=request.form.get('location',u['location'] or '').strip()[:80]
        website=request.form.get('website',u['website'] or '').strip()[:120]
        visibility=request.form.get('profile_visibility',u['profile_visibility'] or 'everyone')
        if visibility not in ['everyone','contacts','none']:
            visibility='everyone'
        avatar=u['avatar']; cover=u['cover_photo']
        file=request.files.get('avatar')
        cover_file=request.files.get('cover_photo')
        if file and file.filename and allowed(file.filename):
            avatar=str(int(datetime.now().timestamp()))+'_avatar_'+secure_filename(file.filename); file.save(os.path.join(UPLOAD_DIR,avatar))
        if cover_file and cover_file.filename and allowed(cover_file.filename):
            cover=str(int(datetime.now().timestamp()))+'_cover_'+secure_filename(cover_file.filename); cover_file.save(os.path.join(UPLOAD_DIR,cover))
        db().execute("UPDATE users SET name=?,about=?,avatar=?,cover_photo=?,location=?,website=?,profile_visibility=? WHERE id=?", (name,about,avatar,cover,location,website,visibility,u['id']))
        db().commit(); return redirect('/me')
    cover = f"<img src='/uploads/{u['cover_photo']}'>" if u['cover_photo'] else ""
    opts = ''.join([f"<option value='{v}' {'selected' if (u['profile_visibility'] or 'everyone')==v else ''}>{lab}</option>" for v,lab in [('everyone','الجميع'),('contacts','جهاتي فقط'),('none','لا أحد')]])
    # الملف الشخصي صار نظيف بدون إحصائيات وبدون فحص الحساب حسب طلبك.
    body=f"""
    <div class='top'><b style='margin:auto'>حسابي</b><a class='icon' href='/profile/{u['id']}'>عرض</a></div>
    <div class='profileCover'>{cover}</div>
    <form class='profileHero' method='post' enctype='multipart/form-data'>
      <img class='avatar' src='{avatar_url(u)}'>
      <h2>{h(u['name'])}</h2><p class='muted'>{h(u['username'] or '')}</p>
      <div class='profileFormGrid'>
        <div class='input'><input name='name' value='{h(u['name'])}' placeholder='الاسم'></div>
        <div class='input'><input name='location' value='{h(u['location'] or '')}' placeholder='المدينة / الموقع'></div>
      </div>
      <div class='input'><input name='about' value='{h(u['about'])}' placeholder='نبذة قصيرة'></div>
      <div class='input'><input name='website' value='{h(u['website'] or '')}' placeholder='رابط أو معرف إضافي'></div>
      <div class='input'><select name='profile_visibility' style='width:100%;background:#0b1728;color:white;border:1px solid #1b2e49;border-radius:18px;padding:14px'>{opts}</select></div>
      <div class='card' style='margin:10px 0;text-align:right'>
        <label>صورة الحساب</label><br><input type='file' name='avatar' accept='image/*'><br><br>
        <label>غلاف الحساب</label><br><input type='file' name='cover_photo' accept='image/*'>
      </div>
      <button class='btn' style='width:100%'>حفظ الملف الشخصي</button>
    </form>
    <div class='card'><a class='chatitem' href='/appearance'><div class='icon'>🎨</div><div class='grow'><div class='name'>المظهر</div><div class='last'>تغيير اللون وحجم الخط وشكل التطبيق</div></div></a></div>
    <div class='card'><a class='chatitem danger' href='/logout'><div class='icon'>🚪</div><div class='grow'><div class='name'>تسجيل الخروج</div><div class='last'>إغلاق الجلسة من هذا الجهاز</div></div></a></div>
    <div class='card'><a class='chatitem' href='/settings'>⚙️ الإعدادات الكاملة</a><a class='chatitem' href='/services'>🧩 الخدمات الموجودة</a><a class='chatitem' href='/privacy'>🔒 الخصوصية</a><a class='chatitem' href='/notifications'>🔔 الإشعارات</a><a class='chatitem' href='/notifications/settings'>⚙️ إعدادات التنبيهات</a><a class='chatitem' href='/starred'>⭐ الرسائل المميزة</a><a class='chatitem' href='/archived'>🗄️ الأرشيف</a><a class='chatitem' href='/appearance'>🎨 المظهر</a></div>{nav('me')}
    """
    return page(body)

@app.route('/uploads/<path:filename>')
def uploads(filename):
    return send_from_directory(UPLOAD_DIR, filename)


if __name__ == '__main__':
    init_db()
    print('✅ واصل شات المرحلة 26 - معاينة المرفقات وتصغير التصميم وإصلاح الصوت تعمل على: http://127.0.0.1:5000')
    app.run(host='0.0.0.0', port=5000, debug=False)
