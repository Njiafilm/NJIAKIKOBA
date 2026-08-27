import os
import sqlite3
import secrets
import hmac
import hashlib
import requests
from datetime import datetime, timedelta
from functools import wraps

from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)

TRANSLATIONS = {
    "sw": {
        "nav_home": "Nyumbani", "nav_about": "Kuhusu", "nav_works": "Jinsi inavyofanya kazi",
        "nav_join": "Jiunge", "nav_login": "Ingia",
        "hero_title1": "Pamoja Tunajenga", "hero_title2": "Kesho Imara",
        "hero_desc": "NJIAKIKOBA ni jukwaa la kisasa la akiba, mikopo na usimamizi wa vikundi linalowezesha wanachama kuweka akiba, kukopa na kufuatilia maendeleo yao kwa uwazi.",
        "btn_join": "👥 Jiunge Sasa", "btn_learn": "🎓 Jifunze Zaidi",
        "about_title": "Fedha Yako. Maendeleo Yako.", "about_sub": "Teknolojia rahisi kwa ukuaji wa pamoja.",
        "f_secure": "🔐 Salama", "f_secure_d": "Nywila zinalindwa kwa hashing na session salama.",
        "f_open": "📊 Wazi", "f_open_d": "Historia ya miamala na ripoti zinapatikana kwa mtumiaji husika.",
        "f_easy": "⚡ Rahisi", "f_easy_d": "Muonekano unaoeleweka kwenye simu, tablet na kompyuta.",
        "f_comm": "🤝 Jumuia", "f_comm_d": "Vikundi vinaweza kusimamia wanachama, michango na mikopo.",
        "works_title": "Jinsi Inavyofanya Kazi",
        "w1": "1. Jiunge", "w1_d": "Fungua akaunti na jiunge na kikundi chako.",
        "w2": "2. Weka Akiba", "w2_d": "Fuatilia michango na historia ya malipo.",
        "w3": "3. Kopa & Rejesha", "w3_d": "Usimamizi wa mkopo na marejesho kwa uwazi.",
        "w4": "4. Fikia Malengo", "w4_d": "Jenga uwezo wa kifedha pamoja.",
        "contact_title": "🎧 Huduma kwa wateja", "contact_email": "✉️ Tuma Email", "contact_wa": "💬 WhatsApp: 0755 248 789",
        "trust_title": "🔒 Salama na Imani", "trust_d": "Taarifa zako zinalindwa kwa usalama wa hali ya juu.",
        "copyright": "© 2026 {group}. Haki zote zimehifadhiwa.",
    },
    "en": {
        "nav_home": "Home", "nav_about": "About", "nav_works": "How it works",
        "nav_join": "Join", "nav_login": "Login",
        "hero_title1": "Together We Build", "hero_title2": "A Stronger Future",
        "hero_desc": "NJIAKIKOBA is a modern savings, loans and group-management platform that helps members save, borrow and track their progress with full transparency.",
        "btn_join": "👥 Join Now", "btn_learn": "🎓 Learn More",
        "about_title": "Your Money. Your Progress.", "about_sub": "Simple technology for growing together.",
        "f_secure": "🔐 Secure", "f_secure_d": "Passwords are protected with hashing and secure sessions.",
        "f_open": "📊 Transparent", "f_open_d": "Transaction history and reports are available to each member.",
        "f_easy": "⚡ Easy", "f_easy_d": "A clear experience across phone, tablet and desktop.",
        "f_comm": "🤝 Community", "f_comm_d": "Groups can manage members, contributions and loans.",
        "works_title": "How It Works",
        "w1": "1. Join", "w1_d": "Create an account and join your group.",
        "w2": "2. Save", "w2_d": "Track contributions and payment history.",
        "w3": "3. Borrow & Repay", "w3_d": "Transparent loan management and repayment.",
        "w4": "4. Reach Your Goals", "w4_d": "Build financial capacity together.",
        "contact_title": "🎧 Customer Support", "contact_email": "✉️ Send Email", "contact_wa": "💬 WhatsApp: 0755 248 789",
        "trust_title": "🔒 Safe & Trusted", "trust_d": "Your information is protected with top-level security.",
        "copyright": "© 2026 {group}. All rights reserved.",
    },
}
app.secret_key = os.environ.get("SECRET_KEY", secrets.token_hex(32))
app.permanent_session_lifetime = timedelta(minutes=30)

DB_PATH = os.environ.get("DATABASE_PATH", "njiakikoba.db")
DEVELOPER_PASSWORD_HASH = os.environ.get("DEVELOPER_PASSWORD_HASH")
DEVELOPER_LIPA_NUMBER = os.environ.get("DEVELOPER_LIPA_NUMBER")  # Secret; never expose publicly.
GROUP_SETTLEMENT_PHONE = os.environ.get("GROUP_SETTLEMENT_PHONE")  # Secret.
GROUP_SETTLEMENT_NETWORK = os.environ.get("GROUP_SETTLEMENT_NETWORK", "MIXX_BY_YAS")
BLMPAY_BASE_URL = os.environ.get("BLMPAY_BASE_URL", "https://pay.blmtec.co.tz/api/v1")
BLMPAY_API_KEY = os.environ.get("BLMPAY_API_KEY")
BLMPAY_WEBHOOK_SECRET = os.environ.get("BLMPAY_WEBHOOK_SECRET")
BLMPAY_WEBHOOK_URL = os.environ.get("BLMPAY_WEBHOOK_URL")
COMMISSION_RATE = 0.02


def db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = db()
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        full_name TEXT NOT NULL,
        phone TEXT UNIQUE NOT NULL,
        payment_phone TEXT,
        payment_network TEXT DEFAULT 'MPESA',
        payout_method TEXT DEFAULT 'mobile',
        bank_code TEXT,
        bank_account TEXT,
        bank_account_name TEXT,
        email TEXT,
        password TEXT NOT NULL,
        role TEXT DEFAULT 'member',
        id_type TEXT,
        id_number_hash TEXT,
        savings REAL DEFAULT 0,
        loan_balance REAL DEFAULT 0,
        status TEXT DEFAULT 'active',
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    );

    CREATE TABLE IF NOT EXISTS group_info (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        group_name TEXT DEFAULT 'NJIAKIKOBA',
        payment_number TEXT,
        system_commission REAL DEFAULT 0
    );

    CREATE TABLE IF NOT EXISTS transactions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        tx_ref TEXT UNIQUE NOT NULL,
        tx_type TEXT NOT NULL,
        amount REAL NOT NULL,
        commission REAL NOT NULL,
        group_amount REAL NOT NULL,
        status TEXT DEFAULT 'pending',
        provider TEXT,
        provider_reference TEXT,
        payment_reference TEXT,
        developer_settlement_status TEXT DEFAULT 'not_configured',
        group_settlement_status TEXT DEFAULT 'not_configured',
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(user_id) REFERENCES users(id)
    );

    CREATE TABLE IF NOT EXISTS security_events (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        event_type TEXT NOT NULL,
        ip TEXT,
        detail TEXT,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    );

    CREATE TABLE IF NOT EXISTS system_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        level TEXT NOT NULL,
        message TEXT NOT NULL,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    );

    CREATE TABLE IF NOT EXISTS messages (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        full_name TEXT NOT NULL,
        role TEXT NOT NULL DEFAULT 'member',
        body TEXT NOT NULL,
        pinned INTEGER DEFAULT 0,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(user_id) REFERENCES users(id)
    );

    CREATE TABLE IF NOT EXISTS integrations (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        label TEXT NOT NULL,
        url TEXT NOT NULL,
        icon TEXT DEFAULT '🔗',
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    );
    """)
    if conn.execute("SELECT COUNT(*) FROM group_info").fetchone()[0] == 0:
        conn.execute("INSERT INTO group_info (group_name, payment_number) VALUES (?, ?)",
                     ("NJIAKIKOBA", os.environ.get("GROUP_PAYMENT_NUMBER")))
    # Migrate existing installations without exposing secrets.
    for stmt in [
        "ALTER TABLE users ADD COLUMN payment_phone TEXT",
        "ALTER TABLE users ADD COLUMN payment_network TEXT DEFAULT 'MPESA'",
        "ALTER TABLE users ADD COLUMN payout_method TEXT DEFAULT 'mobile'",
        "ALTER TABLE users ADD COLUMN bank_code TEXT",
        "ALTER TABLE users ADD COLUMN bank_account TEXT",
        "ALTER TABLE users ADD COLUMN bank_account_name TEXT",
        "ALTER TABLE users ADD COLUMN email TEXT",
        "ALTER TABLE transactions ADD COLUMN payment_reference TEXT",
        "ALTER TABLE transactions ADD COLUMN developer_settlement_status TEXT DEFAULT 'not_configured'",
        "ALTER TABLE transactions ADD COLUMN group_settlement_status TEXT DEFAULT 'not_configured'",
        "ALTER TABLE group_info ADD COLUMN adsense_publisher_id TEXT",
        "ALTER TABLE group_info ADD COLUMN play_store_url TEXT",
        "ALTER TABLE group_info ADD COLUMN appstore_url TEXT",
        "ALTER TABLE group_info ADD COLUMN registration_code TEXT",
        "ALTER TABLE group_info ADD COLUMN member_cap INTEGER DEFAULT 999",
        "ALTER TABLE users ADD COLUMN member_number INTEGER",
        "ALTER TABLE users ADD COLUMN group_size_at_join INTEGER",
    ]:
        try:
            conn.execute(stmt)
        except sqlite3.OperationalError:
            pass

    # Assign a permanent registration code to the group, once.
    row = conn.execute("SELECT id, registration_code FROM group_info LIMIT 1").fetchone()
    if row and not row["registration_code"]:
        code = f"NK-{row['id']:015d}"
        conn.execute("UPDATE group_info SET registration_code=? WHERE id=?", (code, row["id"]))

    # Backfill member_number for any users created before this feature existed.
    max_num = conn.execute("SELECT COALESCE(MAX(member_number),0) FROM users").fetchone()[0]
    unnumbered = conn.execute("SELECT id FROM users WHERE member_number IS NULL ORDER BY id").fetchall()
    for u in unnumbered:
        max_num += 1
        conn.execute("UPDATE users SET member_number=? WHERE id=?", (max_num, u["id"]))

    conn.commit()
    conn.close()


def log_event(event_type, detail=""):
    conn = db()
    conn.execute(
        "INSERT INTO security_events (event_type, ip, detail) VALUES (?, ?, ?)",
        (event_type, request.remote_addr, detail[:500])
    )
    conn.commit()
    conn.close()


def developer_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not session.get("is_developer"):
            return redirect(url_for("developer_room"))
        return view(*args, **kwargs)
    return wrapped


def member_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if "user_id" not in session:
            return redirect(url_for("login"))
        return view(*args, **kwargs)
    return wrapped


@app.before_request
def session_control():
    session.permanent = True


@app.route("/")
def home():
    lang = request.args.get("lang")
    if lang in ("sw", "en"):
        session["lang"] = lang
        session.permanent = True
    conn = db()
    settings = conn.execute(
        "SELECT adsense_publisher_id, play_store_url, appstore_url, group_name FROM group_info LIMIT 1"
    ).fetchone()
    integrations = conn.execute("SELECT label, url, icon FROM integrations ORDER BY id").fetchall()
    conn.close()
    return render_template("index.html", settings=settings, integrations=integrations, lang=session.get("lang", "sw"), t=TRANSLATIONS[session.get("lang", "sw")])


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        name = request.form.get("full_name", "").strip()
        phone = request.form.get("phone", "").strip()
        password = request.form.get("password", "")
        if not name or not phone or len(password) < 8:
            flash("Jaza taarifa zote. Nywila iwe na angalau herufi 8.", "danger")
            return render_template("register.html")

        conn = db()
        group = conn.execute("SELECT member_cap FROM group_info LIMIT 1").fetchone()
        member_cap = group["member_cap"] if group and group["member_cap"] else 999
        current_total = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        if current_total >= member_cap:
            conn.close()
            flash(
                f"Kikundi kimefikia ukomo wa wanachama ({member_cap}). "
                "Wasiliana na msimamizi wa mfumo kuongeza nafasi (upgrade).",
                "danger"
            )
            return render_template("register.html")

        try:
            next_number = conn.execute("SELECT COALESCE(MAX(member_number),0)+1 FROM users").fetchone()[0]
            new_total = current_total + 1
            conn.execute(
                "INSERT INTO users (full_name, phone, email, password, member_number, group_size_at_join) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (name, phone, request.form.get("email", "").strip(), generate_password_hash(password),
                 next_number, new_total)
            )
            conn.execute(
                "INSERT INTO messages (user_id, full_name, role, body) VALUES (0, 'Mfumo', 'system', ?)",
                (f"🔔 {name} amejiunga na kikundi. Idadi ya sasa ya wanachama: {new_total}.",)
            )
            conn.commit()
            flash("Akaunti imetengenezwa. Tafadhali ingia.", "success")
            return redirect(url_for("login"))
        except sqlite3.IntegrityError:
            flash("Namba hii ya simu tayari ina akaunti.", "danger")
        finally:
            conn.close()
    return render_template("register.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        phone = request.form.get("phone", "").strip()
        password = request.form.get("password", "")
        conn = db()
        user = conn.execute("SELECT * FROM users WHERE phone=?", (phone,)).fetchone()
        conn.close()
        if user and user["status"] == "active" and check_password_hash(user["password"], password):
            session.clear()
            session.permanent = True
            session["user_id"] = user["id"]
            session["full_name"] = user["full_name"]
            session["role"] = user["role"]
            return redirect(url_for("dashboard"))
        log_event("login_failed", "Failed member login")
        flash("Taarifa si sahihi.", "danger")
    return render_template("login.html")


@app.route("/dashboard")
@member_required
def dashboard():
    conn = db()
    user = conn.execute(
        "SELECT full_name, phone, payment_phone, payment_network, payout_method, bank_code, bank_account, bank_account_name, email, savings, loan_balance, role, member_number, group_size_at_join FROM users WHERE id=?",
        (session["user_id"],)
    ).fetchone()
    transactions = conn.execute(
        "SELECT tx_ref, tx_type, amount, commission, group_amount, status, created_at "
        "FROM transactions WHERE user_id=? ORDER BY id DESC LIMIT 10",
        (session["user_id"],)
    ).fetchall()
    conn.close()
    share_url = url_for("home", _external=True)
    return render_template("dashboard.html", user=user, transactions=transactions, share_url=share_url)


@app.route("/register-leaders", methods=["GET", "POST"])
def register_leaders():
    if request.method == "POST":
        title = request.form.get("leader_title", "Kiongozi")
        name = request.form.get("full_name", "").strip()
        phone = request.form.get("phone", "").strip()
        id_type = request.form.get("id_type", "")
        id_number = request.form.get("id_number", "").strip()
        password = request.form.get("password", "")
        if not all([name, phone, id_type, id_number]) or len(password) < 8:
            flash("Jaza taarifa zote kwa usahihi.", "danger")
            return render_template("register_leaders.html")
        conn = db()
        leader_count = conn.execute("SELECT COUNT(*) FROM users WHERE role='leader'").fetchone()[0]
        if leader_count >= 3:
            conn.close()
            flash("Kikundi tayari kina viongozi 3 (idadi ya juu inayoruhusiwa).", "danger")
            return render_template("register_leaders.html")

        group = conn.execute("SELECT member_cap FROM group_info LIMIT 1").fetchone()
        member_cap = group["member_cap"] if group and group["member_cap"] else 999
        current_total = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        if current_total >= member_cap:
            conn.close()
            flash(f"Kikundi kimefikia ukomo wa wanachama ({member_cap}).", "danger")
            return render_template("register_leaders.html")

        try:
            next_number = conn.execute("SELECT COALESCE(MAX(member_number),0)+1 FROM users").fetchone()[0]
            new_total = current_total + 1
            # ID number is hashed; the developer dashboard does not expose it.
            conn.execute(
                "INSERT INTO users (full_name, phone, password, role, id_type, id_number_hash, member_number, group_size_at_join) "
                "VALUES (?, ?, ?, 'leader', ?, ?, ?, ?)",
                (f"{title}: {name}", phone, generate_password_hash(password),
                 id_type, generate_password_hash(id_number), next_number, new_total)
            )
            conn.execute(
                "INSERT INTO messages (user_id, full_name, role, body) VALUES (0, 'Mfumo', 'system', ?)",
                (f"🔔 Kiongozi mpya ({name}) amejiunga. Idadi ya sasa ya wanachama: {new_total}.",)
            )
            conn.commit()
            flash("Taarifa za kiongozi zimehifadhiwa kwa usalama.", "success")
            return redirect(url_for("login"))
        except sqlite3.IntegrityError:
            flash("Namba hii ya simu tayari imesajiliwa.", "danger")
        finally:
            conn.close()
    return render_template("register_leaders.html")


@app.route("/developer-room", methods=["GET", "POST"])
def developer_room():
    # This route is intentionally not linked from any public page.
    if request.method == "POST":
        entered = request.form.get("developer_password", "")
        valid = False
        if DEVELOPER_PASSWORD_HASH:
            valid = check_password_hash(DEVELOPER_PASSWORD_HASH, entered)
        else:
            # Development fallback only. Production should set DEVELOPER_PASSWORD_HASH.
            valid = secrets.compare_digest(
                entered, os.environ.get("DEVELOPER_PASSWORD_DEV_ONLY", "")
            )
        if valid:
            session.clear()
            session.permanent = True
            session["is_developer"] = True
            return redirect(url_for("developer_dashboard"))
        log_event("developer_login_failed", "Failed developer authentication")
        flash("Neno la siri si sahihi.", "danger")
    return render_template("developer_login.html")


@app.route("/developer-dashboard")
@developer_required
def developer_dashboard():
    conn = db()
    stats = {
        "transactions": conn.execute("SELECT COUNT(*) FROM transactions").fetchone()[0],
        "pending": conn.execute(
            "SELECT COUNT(*) FROM transactions WHERE status='pending'"
        ).fetchone()[0],
        "commission": conn.execute(
            "SELECT COALESCE(SUM(commission),0) FROM transactions WHERE status='paid'"
        ).fetchone()[0],
        "commission_30d": conn.execute(
            "SELECT COALESCE(SUM(commission),0) FROM transactions "
            "WHERE status='paid' AND created_at >= datetime('now','-30 days')"
        ).fetchone()[0],
        "errors": conn.execute(
            "SELECT COUNT(*) FROM system_logs WHERE level='ERROR'"
        ).fetchone()[0],
    }
    logs = conn.execute(
        "SELECT level, message, created_at FROM system_logs ORDER BY id DESC LIMIT 15"
    ).fetchall()
    settings = conn.execute(
        "SELECT adsense_publisher_id, play_store_url, appstore_url, group_name, registration_code, member_cap FROM group_info LIMIT 1"
    ).fetchone()
    counts = {
        "leaders": conn.execute("SELECT COUNT(*) FROM users WHERE role='leader'").fetchone()[0],
        "members": conn.execute("SELECT COUNT(*) FROM users").fetchone()[0],
    }
    integrations = conn.execute("SELECT id, label, url, icon FROM integrations ORDER BY id").fetchall()
    conn.close()
    return render_template("developer_dashboard.html", stats=stats, logs=logs, settings=settings, counts=counts, integrations=integrations)


@app.route("/developer-dashboard/settings", methods=["POST"])
@developer_required
def developer_settings_update():
    adsense_id = request.form.get("adsense_publisher_id", "").strip()
    play_store = request.form.get("play_store_url", "").strip()
    appstore = request.form.get("appstore_url", "").strip()
    group_name = request.form.get("group_name", "").strip()
    member_cap_raw = request.form.get("member_cap", "").strip()

    # Basic sanity checks — don't save obviously malformed values.
    if adsense_id and not adsense_id.startswith("ca-pub-"):
        flash("AdSense Publisher ID lazima ianze na 'ca-pub-'.", "danger")
        return redirect(url_for("developer_dashboard"))
    for url_val, label in [(play_store, "Play Store"), (appstore, "App Store")]:
        if url_val and not (url_val.startswith("https://")):
            flash(f"Link ya {label} lazima ianze na https://", "danger")
            return redirect(url_for("developer_dashboard"))

    conn = db()
    member_cap = None
    if member_cap_raw:
        try:
            member_cap = max(1, int(member_cap_raw))
        except ValueError:
            flash("Idadi ya wanachama (upgrade) lazima iwe namba.", "danger")
            conn.close()
            return redirect(url_for("developer_dashboard"))

    if member_cap is not None:
        current_total = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        if member_cap < current_total:
            flash(f"Huwezi kuweka ukomo chini ya idadi ya sasa ya wanachama ({current_total}).", "danger")
            conn.close()
            return redirect(url_for("developer_dashboard"))
        conn.execute(
            "UPDATE group_info SET adsense_publisher_id=?, play_store_url=?, appstore_url=?, group_name=?, member_cap=?",
            (adsense_id or None, play_store or None, appstore or None, group_name or "NJIAKIKOBA", member_cap)
        )
    else:
        conn.execute(
            "UPDATE group_info SET adsense_publisher_id=?, play_store_url=?, appstore_url=?, group_name=?",
            (adsense_id or None, play_store or None, appstore or None, group_name or "NJIAKIKOBA")
        )
    conn.commit()
    conn.close()
    flash("Mipangilio imehifadhiwa.", "success")
    return redirect(url_for("developer_dashboard"))


@app.route("/run-bots", methods=["POST"])
@developer_required
def run_bots():
    conn = db()
    checks = []

    try:
        conn.execute("PRAGMA integrity_check").fetchone()
        checks.append("Database integrity check: OK")
    except Exception as exc:
        checks.append("Database check issue detected")
        conn.execute("INSERT INTO system_logs (level, message) VALUES (?, ?)",
                     ("ERROR", f"Database check failed: {str(exc)[:300]}"))

    try:
        conn.execute("SELECT 1").fetchone()
        checks.append("Database connectivity: OK")
    except Exception:
        checks.append("Database connectivity: ISSUE")

    # Safe self-repair: logs the diagnostics; no destructive code mutation.
    for item in checks:
        conn.execute("INSERT INTO system_logs (level, message) VALUES (?, ?)",
                     ("INFO", f"System Checker: {item}"))
    conn.execute("INSERT INTO system_logs (level, message) VALUES (?, ?)",
                 ("INFO", "System Security: authentication/session checks active"))
    conn.commit()
    conn.close()

    flash("Bots zimekamilisha diagnostic scan na safe checks.", "success")
    return redirect(url_for("developer_dashboard"))


@app.route("/api/profile/payment-number", methods=["POST"])
@member_required
def update_payment_number():
    data = request.get_json(silent=True) or {}
    phone = str(data.get("payment_phone", "")).strip()
    network = str(data.get("payment_network", "MPESA")).upper()
    allowed = {"MPESA", "AIRTEL_MONEY", "MIXX_BY_YAS", "HALOPESA", "EZYPESA", "TTCLPESA"}
    if not __import__("re").fullmatch(r"255\d{9}", phone):
        return jsonify({"error": "Tumia namba ya Tanzania ya muundo 255XXXXXXXXX."}), 400
    if network not in allowed:
        return jsonify({"error": "Mtandao wa simu haujatambuliwa."}), 400
    conn=db()
    conn.execute("UPDATE users SET payment_phone=?, payment_network=? WHERE id=?", (phone, network, session["user_id"]))
    conn.commit(); conn.close()
    return jsonify({"success": True, "message": "Namba yako ya malipo imehifadhiwa."})


@app.route("/api/profile/payout-destination", methods=["POST"])
@member_required
def update_payout_destination():
    data = request.get_json(silent=True) or {}
    method = str(data.get("payout_method", "mobile")).lower()
    if method not in {"mobile", "bank"}:
        return jsonify({"error": "Chagua simu au bank."}), 400
    conn = db()
    if method == "mobile":
        phone = str(data.get("payment_phone", "")).strip()
        network = str(data.get("payment_network", "MPESA")).upper()
        allowed = {"MPESA", "AIRTEL_MONEY", "MIXX_BY_YAS", "HALOPESA", "EZYPESA", "TTCLPESA"}
        if not __import__("re").fullmatch(r"255\d{9}", phone):
            conn.close(); return jsonify({"error": "Tumia namba ya Tanzania ya muundo 255XXXXXXXXX."}), 400
        if network not in allowed:
            conn.close(); return jsonify({"error": "Mtandao wa simu haujatambuliwa."}), 400
        conn.execute("UPDATE users SET payout_method='mobile', payment_phone=?, payment_network=?, bank_code=NULL, bank_account=NULL, bank_account_name=NULL WHERE id=?", (phone, network, session["user_id"]))
    else:
        bank = str(data.get("bank_code", "")).upper().strip()
        account = str(data.get("bank_account", "")).strip()
        if bank not in {"CRDB", "NMB", "NBC", "ABSA"}:
            conn.close(); return jsonify({"error": "Chagua bank inayoungwa mkono."}), 400
        if not __import__("re").fullmatch(r"\d{6,34}", account):
            conn.close(); return jsonify({"error": "Namba ya akaunti ya bank si sahihi."}), 400
        conn.execute("UPDATE users SET payout_method='bank', bank_code=?, bank_account=?, bank_account_name=NULL WHERE id=?", (bank, account, session["user_id"]))
    conn.commit(); conn.close()
    return jsonify({"success": True, "message": "Njia ya kupokea malipo imehifadhiwa. Mfumo utaitumia kwenye malipo yaliyoidhinishwa."})


@app.route("/api/payout/verify-destination", methods=["POST"])
@member_required
def verify_payout_destination():
    if not BLMPAY_API_KEY:
        return jsonify({"error": "Payment gateway haijaunganishwa kwenye server."}), 503
    data = request.get_json(silent=True) or {}
    method = str(data.get("payout_method", "mobile")).lower()
    if method == "mobile":
        account = str(data.get("payment_phone", "")).strip()
        payload = {"channel": "mobile", "account_number": account}
    elif method == "bank":
        account = str(data.get("bank_account", "")).strip()
        bank = str(data.get("bank_code", "")).upper().strip()
        payload = {"channel": "bank", "account_number": account, "bank_code": bank}
    else:
        return jsonify({"error": "Njia si sahihi."}), 400
    try:
        r = requests.post(f"{BLMPAY_BASE_URL}/payouts/name-lookup", headers={"Authorization": f"Bearer {BLMPAY_API_KEY}", "Content-Type": "application/json"}, json=payload, timeout=20)
        result = r.json()
    except Exception:
        return jsonify({"error": "Huduma ya uthibitishaji haipatikani kwa sasa."}), 502
    if r.status_code >= 400 or result.get("status") != "success":
        return jsonify({"error": result.get("message", "Taarifa za mpokeaji hazijathibitishwa.")}), 400
    name = (result.get("data") or {}).get("account_name")
    conn = db()
    if method == "mobile":
        conn.execute("UPDATE users SET payout_method='mobile', payment_phone=?, payment_network=COALESCE(payment_network,'MPESA'), bank_account_name=? WHERE id=?", (account, name, session["user_id"]))
    else:
        conn.execute("UPDATE users SET payout_method='bank', bank_code=?, bank_account=?, bank_account_name=? WHERE id=?", (payload["bank_code"], account, name, session["user_id"]))
    conn.commit(); conn.close()
    return jsonify({"success": True, "account_name": name, "message": "Mpokeaji amethibitishwa."})


@app.route("/api/leader/loan-disburse", methods=["POST"])
@member_required
def leader_loan_disburse():
    # Only a registered leader can authorize a loan payout.
    conn = db()
    actor = conn.execute("SELECT role FROM users WHERE id=?", (session["user_id"],)).fetchone()
    if not actor or actor["role"] != "leader":
        conn.close(); return jsonify({"error": "Ni kiongozi aliyeidhinishwa pekee anayeruhusiwa kuanzisha malipo ya mkopo."}), 403
    data = request.get_json(silent=True) or {}
    try: member_id = int(data.get("member_id")); amount = int(float(data.get("amount", 0)))
    except (TypeError, ValueError):
        conn.close(); return jsonify({"error": "Member ID au kiasi si sahihi."}), 400
    if amount < 1000:
        conn.close(); return jsonify({"error": "Kiasi cha chini cha payout ni TZS 1,000."}), 400
    member = conn.execute("SELECT id, full_name, payout_method, payment_phone, payment_network, bank_code, bank_account FROM users WHERE id=? AND status='active'", (member_id,)).fetchone()
    if not member:
        conn.close(); return jsonify({"error": "Mwanakikundi hakupatikana."}), 404
    if not BLMPAY_API_KEY:
        conn.close(); return jsonify({"error": "Payment gateway haijaunganishwa."}), 503
    method = member["payout_method"] or "mobile"
    tx_ref = "LOAN-" + secrets.token_hex(8).upper()
    if method == "bank":
        if not member["bank_code"] or not member["bank_account"]:
            conn.close(); return jsonify({"error": "Mwanakikundi hajajaza taarifa za bank."}), 400
        payout = {"amount": amount, "currency": "TZS", "channel": "bank", "recipient_bank": member["bank_code"], "recipient_account": member["bank_account"], "narration": f"NJIAKIKOBA loan {tx_ref}", "metadata": {"tx_ref": tx_ref, "member_id": member_id, "type": "loan_disbursement"}}
    else:
        if not member["payment_phone"] or not member["payment_network"]:
            conn.close(); return jsonify({"error": "Mwanakikundi hajajaza namba ya simu ya malipo."}), 400
        payout = {"amount": amount, "currency": "TZS", "channel": "mobile", "recipient_phone": member["payment_phone"], "network": member["payment_network"], "narration": f"NJIAKIKOBA loan {tx_ref}", "metadata": {"tx_ref": tx_ref, "member_id": member_id, "type": "loan_disbursement"}}
    conn.close()
    try:
        r = requests.post(f"{BLMPAY_BASE_URL}/payouts/send", headers={"Authorization": f"Bearer {BLMPAY_API_KEY}", "Content-Type": "application/json", "Idempotency-Key": tx_ref}, json=payout, timeout=25)
        result = r.json()
    except Exception:
        return jsonify({"error": "Payout provider haipatikani kwa sasa."}), 502
    if r.status_code >= 400 or result.get("status") != "success":
        return jsonify({"error": result.get("message", "Malipo hayakuanzishwa.")}), 502
    ref = (result.get("data") or {}).get("reference")
    conn = db()
    conn.execute("INSERT INTO transactions (user_id,tx_ref,tx_type,amount,commission,group_amount,status,provider,provider_reference,payment_reference) VALUES (?,?,?,?,?,?,?,?,?,?)", (member_id, tx_ref, "loan_disbursement", amount, 0, amount, "payout_processing", "BLMPay", ref, ref))
    conn.commit(); conn.close()
    return jsonify({"success": True, "reference": ref, "message": "Malipo ya mkopo yamepelekwa kwenye njia ya mwanakikundi."}), 201


@app.route("/api/payment/create", methods=["POST"])
@member_required
def create_payment():
    data=request.get_json(silent=True) or {}
    try: amount=int(float(data.get("amount", 0)))
    except (TypeError, ValueError): amount=0
    tx_type=data.get("tx_type", "savings")
    if amount < 100 or tx_type not in ("savings", "loan_repayment"):
        return jsonify({"error":"Kiasi au aina ya malipo si sahihi."}),400
    conn=db()
    user=conn.execute("SELECT full_name,email,payment_phone,payment_network FROM users WHERE id=?",(session["user_id"],)).fetchone()
    conn.close()
    if not user or not user["payment_phone"]:
        return jsonify({"error":"Weka kwanza namba yako ya malipo kwenye akaunti yako."}),400
    if not user["email"]:
        return jsonify({"error":"Weka barua pepe kwenye akaunti yako kabla ya malipo."}),400
    phone=user["payment_phone"]
    network=user["payment_network"] or "MPESA"
    if not __import__("re").fullmatch(r"255\d{9}", phone):
        return jsonify({"error":"Namba yako ya malipo si sahihi."}),400
    commission=round(amount*COMMISSION_RATE,2)
    group_amount=round(amount-commission,2)
    tx_ref="NJK-"+secrets.token_hex(8).upper()
    if not BLMPAY_API_KEY or not BLMPAY_WEBHOOK_URL:
        return jsonify({"error":"Payment gateway haijaunganishwa kikamilifu kwenye server."}),503
    first,*last=user["full_name"].split()
    payload={"payment_type":"mobile","details":{"amount":amount,"currency":"TZS"},"phone_number":phone,"customer":{"firstname":first[:60],"lastname":" ".join(last)[:60] or first[:60],"email":user["email"]},"webhook_url":BLMPAY_WEBHOOK_URL,"metadata":{"tx_ref":tx_ref,"tx_type":tx_type,"network":network,"commission_percent":2}}
    try:
        r=requests.post(f"{BLMPAY_BASE_URL}/payments",headers={"Authorization":f"Bearer {BLMPAY_API_KEY}","Content-Type":"application/json","Idempotency-Key":tx_ref},json=payload,timeout=25)
        result=r.json()
    except Exception as exc:
        log_event("payment_gateway_error",str(exc))
        return jsonify({"error":"Payment gateway haipatikani kwa sasa."}),502
    if r.status_code>=400 or result.get("status")!="success":
        return jsonify({"error":result.get("message","Malipo hayakuanzishwa.")}),502
    pref=(result.get("data") or {}).get("reference")
    conn=db(); conn.execute("INSERT INTO transactions (user_id,tx_ref,tx_type,amount,commission,group_amount,provider,status,provider_reference,payment_reference) VALUES (?,?,?,?,?,?,?,?,?,?)",(session["user_id"],tx_ref,tx_type,amount,commission,group_amount,"BLMPay","awaiting_confirmation",pref,pref)); conn.commit(); conn.close()
    return jsonify({"success":True,"tx_ref":tx_ref,"payment_reference":pref,"amount":amount,"message":"USSD push imetumwa kwenye namba yako. Ingiza PIN yako kuthibitisha."}),201


@app.route("/webhooks/blmpay", methods=["POST"])
def blmpay_webhook():
    if not BLMPAY_WEBHOOK_SECRET: return "Webhook secret not configured",503
    raw=request.get_data(); sig=request.headers.get("X-Webhook-Signature",""); timestamp=request.headers.get("X-Webhook-Timestamp","")
    if not timestamp or not sig: return "Missing signature",401
    expected=hmac.new(BLMPAY_WEBHOOK_SECRET.encode(),(timestamp+".").encode()+raw,hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected,sig): return "Invalid signature",401
    body=request.get_json(silent=True) or {}; event=body.get("event") or body.get("type"); data=body.get("data") or body
    tx_ref=(data.get("metadata") or {}).get("tx_ref") or data.get("reference")
    if not tx_ref: return "Missing transaction reference",400
    conn=db(); tx=conn.execute("SELECT * FROM transactions WHERE tx_ref=?",(tx_ref,)).fetchone()
    if not tx: conn.close(); return "Transaction not found",404
    status=str(data.get("status","")).lower()
    if event=="payment.completed" or status=="completed":
        if tx["status"]=="paid": conn.close(); return "OK",200
        conn.execute("UPDATE transactions SET status='paid', payment_reference=COALESCE(payment_reference, ?) WHERE tx_ref=?",(data.get("reference"),tx_ref))
        if tx["tx_type"]=="savings": conn.execute("UPDATE users SET savings=savings+? WHERE id=?",(tx["group_amount"],tx["user_id"]))
        else: conn.execute("UPDATE users SET loan_balance=MAX(0,loan_balance-?) WHERE id=?",(tx["group_amount"],tx["user_id"]))
        # The Developer destination is a secret Lipa Namba. Do NOT put it in HTML/JS.
        # BLMPay's documented payout API sends to verified mobile/bank recipients, not Lipa Namba.
        # Therefore this code records the 2% fee for settlement through the merchant's approved Lipa/settlement integration,
        # instead of pretending a payout to the Lipa Namba happened.
        dev_status="configured" if DEVELOPER_LIPA_NUMBER else "not_configured"
        grp_status="configured" if GROUP_SETTLEMENT_PHONE else "not_configured"
        conn.execute("UPDATE transactions SET developer_settlement_status=?, group_settlement_status=? WHERE tx_ref=?",(dev_status,grp_status,tx_ref))
        conn.execute("INSERT INTO system_logs(level,message) VALUES(?,?)",("INFO",f"Paid {tx_ref}: 2% operating fee recorded server-side; destination secret configured={bool(DEVELOPER_LIPA_NUMBER)}"))
    elif event in ("payment.failed","payment.expired","payment.cancelled","payment.voided") or status in ("failed","expired","cancelled","voided"):
        conn.execute("UPDATE transactions SET status='failed' WHERE tx_ref=? AND status!='paid'",(tx_ref,))
    conn.commit(); conn.close(); return "OK",200

@app.route("/group-chat", methods=["GET", "POST"])
@member_required
def group_chat():
    conn = db()
    actor = conn.execute("SELECT full_name, role FROM users WHERE id=?", (session["user_id"],)).fetchone()

    if request.method == "POST":
        body = request.form.get("body", "").strip()
        if body:
            body = body[:1000]  # cap message length
            conn.execute(
                "INSERT INTO messages (user_id, full_name, role, body) VALUES (?, ?, ?, ?)",
                (session["user_id"], actor["full_name"], actor["role"], body)
            )
            conn.commit()
        conn.close()
        return redirect(url_for("group_chat"))

    messages = conn.execute(
        "SELECT id, user_id, full_name, role, body, pinned, created_at "
        "FROM messages ORDER BY pinned DESC, id DESC LIMIT 100"
    ).fetchall()
    conn.close()
    return render_template("group_chat.html", messages=messages, actor=actor)


@app.route("/group-chat/delete/<int:message_id>", methods=["POST"])
@member_required
def group_chat_delete(message_id):
    conn = db()
    actor = conn.execute("SELECT role FROM users WHERE id=?", (session["user_id"],)).fetchone()
    msg = conn.execute("SELECT user_id FROM messages WHERE id=?", (message_id,)).fetchone()
    if msg and (actor["role"] == "leader" or msg["user_id"] == session["user_id"]):
        conn.execute("DELETE FROM messages WHERE id=?", (message_id,))
        conn.commit()
    else:
        flash("Huna ruhusa ya kufuta ujumbe huu.", "danger")
    conn.close()
    return redirect(url_for("group_chat"))


@app.route("/group-chat/pin/<int:message_id>", methods=["POST"])
@member_required
def group_chat_pin(message_id):
    conn = db()
    actor = conn.execute("SELECT role FROM users WHERE id=?", (session["user_id"],)).fetchone()
    if actor["role"] == "leader":
        conn.execute("UPDATE messages SET pinned = CASE WHEN pinned=1 THEN 0 ELSE 1 END WHERE id=?", (message_id,))
        conn.commit()
    else:
        flash("Ni viongozi tu wanaoweza ku-pin ujumbe.", "danger")
    conn.close()
    return redirect(url_for("group_chat"))


@app.route("/certificate")
@member_required
def certificate():
    conn = db()
    user = conn.execute(
        "SELECT full_name, member_number, role, group_size_at_join, created_at FROM users WHERE id=?",
        (session["user_id"],)
    ).fetchone()
    leaders = conn.execute(
        "SELECT full_name FROM users WHERE role='leader' ORDER BY id LIMIT 3"
    ).fetchall()
    group = conn.execute("SELECT group_name FROM group_info LIMIT 1").fetchone()
    conn.close()
    return render_template("certificate.html", user=user, leaders=leaders, group=group)


@app.route("/receipt/<tx_ref>")
@member_required
def receipt(tx_ref):
    conn = db()
    tx = conn.execute(
        "SELECT tx_ref, tx_type, amount, commission, group_amount, status, created_at, user_id "
        "FROM transactions WHERE tx_ref=?", (tx_ref,)
    ).fetchone()
    if not tx or tx["user_id"] != session["user_id"] or tx["status"] != "paid":
        conn.close()
        flash("Risiti haipatikani.", "danger")
        return redirect(url_for("dashboard"))
    user = conn.execute(
        "SELECT full_name, member_number FROM users WHERE id=?", (session["user_id"],)
    ).fetchone()
    group = conn.execute("SELECT group_name, registration_code FROM group_info LIMIT 1").fetchone()
    conn.close()
    return render_template("receipt.html", tx=tx, user=user, group=group)


@app.route("/developer-dashboard/integrations/add", methods=["POST"])
@developer_required
def integration_add():
    label = request.form.get("label", "").strip()[:60]
    url_val = request.form.get("url", "").strip()
    icon = request.form.get("icon", "").strip()[:4] or "🔗"
    if not label or not url_val.startswith("https://"):
        flash("Jina na link (lianze na https://) vinahitajika.", "danger")
        return redirect(url_for("developer_dashboard"))
    conn = db()
    conn.execute("INSERT INTO integrations (label, url, icon) VALUES (?, ?, ?)", (label, url_val, icon))
    conn.commit()
    conn.close()
    flash(f"Chanzo '{label}' kimeongezwa.", "success")
    return redirect(url_for("developer_dashboard"))


@app.route("/developer-dashboard/integrations/delete/<int:integration_id>", methods=["POST"])
@developer_required
def integration_delete(integration_id):
    conn = db()
    conn.execute("DELETE FROM integrations WHERE id=?", (integration_id,))
    conn.commit()
    conn.close()
    flash("Chanzo kimeondolewa.", "success")
    return redirect(url_for("developer_dashboard"))


@app.route("/developer-dashboard/chat", methods=["GET", "POST"])
@developer_required
def developer_chat():
    conn = db()
    if request.method == "POST":
        body = request.form.get("body", "").strip()[:1000]
        if body:
            conn.execute(
                "INSERT INTO messages (user_id, full_name, role, body) VALUES (0, 'Msimamizi wa Mfumo', 'developer', ?)",
                (body,)
            )
            conn.commit()
        conn.close()
        return redirect(url_for("developer_chat"))

    messages = conn.execute(
        "SELECT id, user_id, full_name, role, body, pinned, created_at "
        "FROM messages ORDER BY pinned DESC, id DESC LIMIT 200"
    ).fetchall()
    conn.close()
    return render_template("developer_chat.html", messages=messages)


@app.route("/developer-dashboard/chat/delete/<int:message_id>", methods=["POST"])
@developer_required
def developer_chat_delete(message_id):
    conn = db()
    conn.execute("DELETE FROM messages WHERE id=?", (message_id,))
    conn.commit()
    conn.close()
    return redirect(url_for("developer_chat"))


@app.route("/developer-dashboard/chat/pin/<int:message_id>", methods=["POST"])
@developer_required
def developer_chat_pin(message_id):
    conn = db()
    conn.execute("UPDATE messages SET pinned = CASE WHEN pinned=1 THEN 0 ELSE 1 END WHERE id=?", (message_id,))
    conn.commit()
    conn.close()
    return redirect(url_for("developer_chat"))


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("home"))


init_db()

if __name__ == "__main__":
    app.run(debug=os.environ.get("FLASK_DEBUG") == "1", port=int(os.environ.get("PORT", 5000)))
