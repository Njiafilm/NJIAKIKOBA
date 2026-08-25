import os
import sqlite3
import secrets
import hmac
import hashlib
import requests
from datetime import timedelta
from functools import wraps
from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__, template_folder='templates', static_folder='static')
app.secret_key = os.environ.get('SECRET_KEY', secrets.token_hex(32))
app.permanent_session_lifetime = timedelta(minutes=30)
DB_PATH = os.environ.get('DATABASE_PATH', 'njiakikoba.db')
DEVELOPER_PASSWORD_HASH = os.environ.get('DEVELOPER_PASSWORD_HASH')
DEVELOPER_PASSWORD_DEV_ONLY = os.environ.get('DEVELOPER_PASSWORD_DEV_ONLY', '')
BLMPAY_BASE_URL = os.environ.get('BLMPAY_BASE_URL', 'https://pay.blmtec.co.tz/api/v1')
BLMPAY_API_KEY = os.environ.get('BLMPAY_API_KEY')
BLMPAY_WEBHOOK_SECRET = os.environ.get('BLMPAY_WEBHOOK_SECRET')
BLMPAY_WEBHOOK_URL = os.environ.get('BLMPAY_WEBHOOK_URL')
COMMISSION_RATE = 0.02


def db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = db()
    conn.executescript('''
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT, full_name TEXT NOT NULL,
        phone TEXT UNIQUE NOT NULL, payment_phone TEXT,
        payment_network TEXT DEFAULT 'MPESA', payout_method TEXT DEFAULT 'mobile',
        bank_code TEXT, bank_account TEXT, bank_account_name TEXT, email TEXT,
        password TEXT NOT NULL, role TEXT DEFAULT 'member', id_type TEXT,
        id_number_hash TEXT, savings REAL DEFAULT 0, loan_balance REAL DEFAULT 0,
        status TEXT DEFAULT 'active', created_at TEXT DEFAULT CURRENT_TIMESTAMP
    );
    CREATE TABLE IF NOT EXISTS group_info (
        id INTEGER PRIMARY KEY AUTOINCREMENT, group_name TEXT DEFAULT 'NJIAKIKOBA',
        payment_number TEXT, system_commission REAL DEFAULT 0
    );
    CREATE TABLE IF NOT EXISTS transactions (
        id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL,
        tx_ref TEXT UNIQUE NOT NULL, tx_type TEXT NOT NULL, amount REAL NOT NULL,
        commission REAL NOT NULL, group_amount REAL NOT NULL, status TEXT DEFAULT 'pending',
        provider TEXT, provider_reference TEXT, payment_reference TEXT,
        developer_settlement_status TEXT DEFAULT 'not_configured',
        group_settlement_status TEXT DEFAULT 'not_configured',
        created_at TEXT DEFAULT CURRENT_TIMESTAMP, FOREIGN KEY(user_id) REFERENCES users(id)
    );
    CREATE TABLE IF NOT EXISTS security_events (
        id INTEGER PRIMARY KEY AUTOINCREMENT, event_type TEXT NOT NULL, ip TEXT,
        detail TEXT, created_at TEXT DEFAULT CURRENT_TIMESTAMP
    );
    CREATE TABLE IF NOT EXISTS system_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT, level TEXT NOT NULL, message TEXT NOT NULL,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    );
    ''')
    if conn.execute('SELECT COUNT(*) FROM group_info').fetchone()[0] == 0:
        conn.execute('INSERT INTO group_info (group_name,payment_number,system_commission) VALUES (?,?,?)',
                     ('NJIAKIKOBA', os.environ.get('GROUP_PAYMENT_NUMBER'), COMMISSION_RATE))
    migrations = [
        'ALTER TABLE users ADD COLUMN payment_phone TEXT',
        'ALTER TABLE users ADD COLUMN payment_network TEXT DEFAULT "MPESA"',
        'ALTER TABLE users ADD COLUMN payout_method TEXT DEFAULT "mobile"',
        'ALTER TABLE users ADD COLUMN bank_code TEXT',
        'ALTER TABLE users ADD COLUMN bank_account TEXT',
        'ALTER TABLE users ADD COLUMN bank_account_name TEXT',
        'ALTER TABLE users ADD COLUMN email TEXT',
        'ALTER TABLE transactions ADD COLUMN payment_reference TEXT',
        'ALTER TABLE transactions ADD COLUMN developer_settlement_status TEXT DEFAULT "not_configured"',
        'ALTER TABLE transactions ADD COLUMN group_settlement_status TEXT DEFAULT "not_configured"'
    ]
    for stmt in migrations:
        try: conn.execute(stmt)
        except sqlite3.OperationalError: pass
    conn.commit(); conn.close()


def log_event(event_type, detail=''):
    conn = db()
    conn.execute('INSERT INTO security_events(event_type,ip,detail) VALUES(?,?,?)',
                 (event_type, request.remote_addr, str(detail)[:500]))
    conn.commit(); conn.close()


def developer_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not session.get('is_developer'):
            return redirect(url_for('developer_room'))
        return view(*args, **kwargs)
    return wrapped


def member_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('login'))
        return view(*args, **kwargs)
    return wrapped


@app.before_request
def session_control():
    session.permanent = True


@app.route('/')
def home():
    return render_template('index.html')


@app.route('/register', methods=['GET','POST'])
def register():
    if request.method == 'POST':
        name=request.form.get('full_name','').strip(); phone=request.form.get('phone','').strip()
        password=request.form.get('password',''); email=request.form.get('email','').strip()
        if not name or not phone or len(password)<8:
            flash('Jaza taarifa zote. Nywila iwe na angalau herufi 8.','danger'); return render_template('register.html')
        conn=db()
        try:
            conn.execute('INSERT INTO users(full_name,phone,email,password) VALUES(?,?,?,?)',
                         (name,phone,email,generate_password_hash(password)))
            conn.commit(); flash('Akaunti imetengenezwa. Tafadhali ingia.','success')
            return redirect(url_for('login'))
        except sqlite3.IntegrityError:
            flash('Namba hii ya simu tayari ina akaunti.','danger')
        finally: conn.close()
    return render_template('register.html')


@app.route('/login', methods=['GET','POST'])
def login():
    if request.method == 'POST':
        phone=request.form.get('phone','').strip(); password=request.form.get('password','')
        conn=db(); user=conn.execute('SELECT * FROM users WHERE phone=?',(phone,)).fetchone(); conn.close()
        if user and user['status']=='active' and check_password_hash(user['password'],password):
            session.clear(); session.permanent=True
            session['user_id']=user['id']; session['full_name']=user['full_name']; session['role']=user['role']
            return redirect(url_for('dashboard'))
        log_event('login_failed','Failed member login'); flash('Taarifa si sahihi.','danger')
    return render_template('login.html')


@app.route('/dashboard')
@member_required
def dashboard():
    conn=db()
    user=conn.execute('SELECT full_name,phone,payment_phone,payment_network,payout_method,bank_code,bank_account,bank_account_name,email,savings,loan_balance FROM users WHERE id=?',(session['user_id'],)).fetchone()
    transactions=conn.execute('SELECT tx_ref,tx_type,amount,commission,group_amount,status,created_at FROM transactions WHERE user_id=? ORDER BY id DESC LIMIT 10',(session['user_id'],)).fetchall()
    conn.close(); return render_template('dashboard.html',user=user,transactions=transactions)


@app.route('/register-leaders', methods=['GET','POST'])
def register_leaders():
    if request.method=='POST':
        title=request.form.get('leader_title','Kiongozi'); name=request.form.get('full_name','').strip()
        phone=request.form.get('phone','').strip(); id_type=request.form.get('id_type',''); id_number=request.form.get('id_number','').strip(); password=request.form.get('password','')
        if not all([name,phone,id_type,id_number]) or len(password)<8:
            flash('Jaza taarifa zote kwa usahihi.','danger'); return render_template('register_leaders.html')
        conn=db()
        try:
            conn.execute('INSERT INTO users(full_name,phone,password,role,id_type,id_number_hash) VALUES(?,?,?,"leader",?,?)',
                         (f'{title}: {name}',phone,generate_password_hash(password),id_type,generate_password_hash(id_number)))
            conn.commit(); flash('Taarifa za kiongozi zimehifadhiwa kwa usalama.','success'); return redirect(url_for('login'))
        except sqlite3.IntegrityError: flash('Namba hii ya simu tayari imesajiliwa.','danger')
        finally: conn.close()
    return render_template('register_leaders.html')


@app.route('/developer-room', methods=['GET','POST'])
@app.route('/developer', methods=['GET','POST'])
def developer_room():
    if request.method=='POST':
        entered=request.form.get('developer_password',''); valid=False
        if DEVELOPER_PASSWORD_HASH:
            try: valid=check_password_hash(DEVELOPER_PASSWORD_HASH,entered)
            except ValueError: valid=False
        elif DEVELOPER_PASSWORD_DEV_ONLY:
            valid=secrets.compare_digest(entered,DEVELOPER_PASSWORD_DEV_ONLY)
        if valid:
            session.clear(); session.permanent=True; session['is_developer']=True
            return redirect(url_for('developer_dashboard'))
        log_event('developer_login_failed','Failed developer authentication'); flash('Neno la siri si sahihi.','danger')
    return render_template('developer_login.html')


@app.route('/developer-dashboard')
@developer_required
def developer_dashboard():
    conn=db()
    stats={
        'transactions':conn.execute('SELECT COUNT(*) FROM transactions').fetchone()[0],
        'pending':conn.execute("SELECT COUNT(*) FROM transactions WHERE status IN ('pending','awaiting_confirmation','payout_processing')").fetchone()[0],
        'commission':conn.execute("SELECT COALESCE(SUM(commission),0) FROM transactions WHERE status='paid'").fetchone()[0],
        'errors':conn.execute("SELECT COUNT(*) FROM system_logs WHERE level='ERROR'").fetchone()[0],
        'members':conn.execute('SELECT COUNT(*) FROM users').fetchone()[0]
    }
    logs=conn.execute('SELECT level,message,created_at FROM system_logs ORDER BY id DESC LIMIT 20').fetchall(); conn.close()
    return render_template('developer_dashboard.html',stats=stats,logs=logs)


@app.route('/run-bots',methods=['POST'])
@developer_required
def run_bots():
    conn=db(); checks=[]
    try:
        result=conn.execute('PRAGMA integrity_check').fetchone(); checks.append('Database integrity: OK' if result and result[0]=='ok' else 'Database integrity: ISSUE')
    except Exception as exc:
        checks.append('Database integrity: ISSUE'); conn.execute('INSERT INTO system_logs(level,message) VALUES(?,?)',('ERROR',f'Database check failed: {str(exc)[:300]}'))
    try: conn.execute('SELECT 1').fetchone(); checks.append('Database connection: OK')
    except Exception: checks.append('Database connection: ISSUE')
    for item in checks: conn.execute('INSERT INTO system_logs(level,message) VALUES(?,?)',('INFO',f'System Checker: {item}'))
    conn.execute('INSERT INTO system_logs(level,message) VALUES(?,?)',('INFO','Security checks active: authentication and sessions.'))
    conn.commit(); conn.close(); flash('System Checker imekamilisha diagnostic scan.','success')
    return redirect(url_for('developer_dashboard'))


@app.route('/api/profile/payment-number',methods=['POST'])
@member_required
def update_payment_number():
    import re
    data=request.get_json(silent=True) or {}; phone=str(data.get('payment_phone','')).strip(); network=str(data.get('payment_network','MPESA')).upper()
    allowed={'MPESA','AIRTEL_MONEY','MIXX_BY_YAS','HALOPESA','EZYPESA','TTCLPESA'}
    if not re.fullmatch(r'255\d{9}',phone): return jsonify(error='Tumia namba ya Tanzania ya muundo 255XXXXXXXXX.'),400
    if network not in allowed: return jsonify(error='Mtandao wa simu haujatambuliwa.'),400
    conn=db(); conn.execute('UPDATE users SET payment_phone=?,payment_network=? WHERE id=?',(phone,network,session['user_id'])); conn.commit(); conn.close()
    return jsonify(success=True,message='Namba ya malipo imehifadhiwa.')


@app.route('/api/payment/create',methods=['POST'])
@member_required
def create_payment():
    data=request.get_json(silent=True) or {}
    try: amount=int(float(data.get('amount',0)))
    except (TypeError,ValueError): amount=0
    tx_type=data.get('tx_type','savings')
    if amount<100 or tx_type not in ('savings','loan_repayment'): return jsonify(error='Kiasi au aina ya malipo si sahihi.'),400
    conn=db(); user=conn.execute('SELECT full_name,email,payment_phone,payment_network FROM users WHERE id=?',(session['user_id'],)).fetchone(); conn.close()
    if not user or not user['payment_phone']: return jsonify(error='Weka kwanza namba yako ya malipo kwenye akaunti.'),400
    if not user['email']: return jsonify(error='Weka barua pepe kwenye akaunti kabla ya malipo.'),400
    import re
    phone=user['payment_phone']; network=user['payment_network'] or 'MPESA'
    if not re.fullmatch(r'255\d{9}',phone): return jsonify(error='Namba ya malipo si sahihi.'),400
    commission=round(amount*COMMISSION_RATE,2); group_amount=round(amount-commission,2); tx_ref='NJK-'+secrets.token_hex(8).upper()
    if not BLMPAY_API_KEY or not BLMPAY_WEBHOOK_URL: return jsonify(error='Payment gateway haijaunganishwa kikamilifu kwenye server.'),503
    parts=user['full_name'].split(); first=parts[0]; last=' '.join(parts[1:]) or first
    payload={'payment_type':'mobile','details':{'amount':amount,'currency':'TZS'},'phone_number':phone,'customer':{'firstname':first[:60],'lastname':last[:60],'email':user['email']},'webhook_url':BLMPAY_WEBHOOK_URL,'metadata':{'tx_ref':tx_ref,'tx_type':tx_type,'network':network,'commission_percent':2}}
    try:
        r=requests.post(f'{BLMPAY_BASE_URL}/payments',headers={'Authorization':f'Bearer {BLMPAY_API_KEY}','Content-Type':'application/json','Idempotency-Key':tx_ref},json=payload,timeout=25); result=r.json()
    except Exception as exc: log_event('payment_gateway_error',str(exc)); return jsonify(error='Payment gateway haipatikani kwa sasa.'),502
    if r.status_code>=400 or result.get('status')!='success': return jsonify(error=result.get('message','Malipo hayakuanzishwa.')),502
    ref=(result.get('data') or {}).get('reference')
    conn=db(); conn.execute('INSERT INTO transactions(user_id,tx_ref,tx_type,amount,commission,group_amount,provider,status,provider_reference,payment_reference) VALUES(?,?,?,?,?,?,?,?,?,?)',(session['user_id'],tx_ref,tx_type,amount,commission,group_amount,'BLMPay','awaiting_confirmation',ref,ref)); conn.commit(); conn.close()
    return jsonify(success=True,tx_ref=tx_ref,payment_reference=ref,amount=amount,message='USSD push imetumwa kwenye namba yako. Ingiza PIN yako.'),201


@app.route('/webhooks/blmpay',methods=['POST'])
def blmpay_webhook():
    if not BLMPAY_WEBHOOK_SECRET: return 'Webhook secret not configured',503
    raw=request.get_data(); sig=request.headers.get('X-Webhook-Signature',''); timestamp=request.headers.get('X-Webhook-Timestamp','')
    if not timestamp or not sig: return 'Missing signature',401
    expected=hmac.new(BLMPAY_WEBHOOK_SECRET.encode(),(timestamp+'.').encode()+raw,hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected,sig): return 'Invalid signature',401
    body=request.get_json(silent=True) or {}; event=body.get('event') or body.get('type'); data=body.get('data') or body; metadata=data.get('metadata') or {}; tx_ref=metadata.get('tx_ref') or data.get('reference')
    if not tx_ref: return 'Missing transaction reference',400
    conn=db(); tx=conn.execute('SELECT * FROM transactions WHERE tx_ref=?',(tx_ref,)).fetchone()
    if not tx: conn.close(); return 'Transaction not found',404
    status=str(data.get('status','')).lower()
    if event=='payment.completed' or status=='completed':
        if tx['status']=='paid': conn.close(); return 'OK',200
        conn.execute('UPDATE transactions SET status="paid",payment_reference=COALESCE(payment_reference,?) WHERE tx_ref=?',(data.get('reference'),tx_ref))
        if tx['tx_type']=='savings': conn.execute('UPDATE users SET savings=savings+? WHERE id=?',(tx['group_amount'],tx['user_id']))
        else: conn.execute('UPDATE users SET loan_balance=MAX(0,loan_balance-?) WHERE id=?',(tx['group_amount'],tx['user_id']))
        conn.execute('INSERT INTO system_logs(level,message) VALUES(?,?)',('INFO',f'Paid {tx_ref}: 2% operating fee recorded server-side.'))
    elif event in ('payment.failed','payment.expired','payment.cancelled','payment.voided') or status in ('failed','expired','cancelled','voided'):
        conn.execute('UPDATE transactions SET status="failed" WHERE tx_ref=? AND status!="paid"',(tx_ref,))
    conn.commit(); conn.close(); return 'OK',200


@app.route('/logout')
def logout():
    session.clear(); return redirect(url_for('home'))


@app.errorhandler(404)
def not_found(_error):
    return redirect(url_for('home'))


init_db()

if __name__ == '__main__':
    app.run(host='0.0.0.0',port=int(os.environ.get('PORT',5000)),debug=os.environ.get('FLASK_DEBUG')=='1')
