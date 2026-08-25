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

# Project folders on GitHub:
#   template/  -> HTML templates
#   Static/    -> static files
app = Flask(__name__, template_folder="template", static_folder="Static")

app.secret_key = os.environ.get("SECRET_KEY", secrets.token_hex(32))
app.permanent_session_lifetime = timedelta(minutes=30)

DB_PATH = os.environ.get("DATABASE_PATH", "njiakikoba.db")
DEVELOPER_PASSWORD_HASH = os.environ.get("DEVELOPER_PASSWORD_HASH")
DEVELOPER_LIPA_NUMBER = os.environ.get("DEVELOPER_LIPA_NUMBER")
GROUP_SETTLEMENT_PHONE = os.environ.get("GROUP_SETTLEMENT_PHONE")
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
    """)

    if conn.execute("SELECT COUNT(*) FROM group_info").fetchone()[0] == 0:
        conn.execute(
            "INSERT INTO group_info (group_name, payment_number) VALUES (?, ?)",
            ("NJIAKIKOBA", os.environ.get("GROUP_PAYMENT_NUMBER"))
        )

    # Safe migration for existing databases.
    migrations = [
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
    ]

    for stmt in migrations:
        try:
            conn.execute(stmt)
        except sqlite3.OperationalError:
            pass

    conn.commit()
    conn.close()


def log_event(event_type, detail=""):
    conn = db()
    conn.execute(
        "INSERT INTO security_events (event_type, ip, detail) VALUES (?, ?, ?)",
        (event_type, request.remote_addr, str(detail)[:500])
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
    return render_template("index.html")


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
        try:
            conn.execute(
                "INSERT INTO users (full_name, phone, email, password) VALUES (?, ?, ?, ?)",
                (
                    name,
                    phone,
                    request.form.get("email", "").strip(),
                    generate_password_hash(password),
                ),
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
        user = conn.execute(
            "SELECT * FROM users WHERE phone=?", (phone,)
        ).fetchone()
        conn.close()

        if (
            user
            and user["status"] == "active"
            and check_password_hash(user["password"], password)
        ):
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
        """
        SELECT full_name, phone, payment_phone, payment_network,
               payout_method, bank_code, bank_account, bank_account_name,
               email, savings, loan_balance
        FROM users WHERE id=?
        """,
        (session["user_id"],),
    ).fetchone()

    transactions = conn.execute(
        """
        SELECT tx_ref, tx_type, amount, commission, group_amount,
               status, created_at
        FROM transactions
        WHERE user_id=?
        ORDER BY id DESC
        LIMIT 10
        """,
        (session["user_id"],),
    ).fetchall()

    conn.close()
    return render_template(
        "dashboard.html",
        user=user,
        transactions=transactions,
    )


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
        try:
            conn.execute(
                """
                INSERT INTO users
                (full_name, phone, password, role, id_type, id_number_hash)
                VALUES (?, ?, ?, 'leader', ?, ?)
                """,
                (
                    f"{title}: {name}",
                    phone,
                    generate_password_hash(password),
                    id_type,
                    generate_password_hash(id_number),
                ),
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
    if request.method == "POST":
        entered = request.form.get("developer_password", "")
        valid = False

        if DEVELOPER_PASSWORD_HASH:
            valid = check_password_hash(DEVELOPER_PASSWORD_HASH, entered)
        else:
            valid = secrets.compare_digest(
                entered,
                os.environ.get("DEVELOPER_PASSWORD_DEV_ONLY", ""),
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
        "transactions": conn.execute(
            "SELECT COUNT(*) FROM transactions"
        ).fetchone()[0],
        "pending": conn.execute(
            "SELECT COUNT(*) FROM transactions WHERE status='pending'"
        ).fetchone()[0],
        "commission": conn.execute(
            "SELECT COALESCE(SUM(commission),0) FROM transactions WHERE status='paid'"
        ).fetchone()[0],
        "errors": conn.execute(
            "SELECT COUNT(*) FROM system_logs WHERE level='ERROR'"
        ).fetchone()[0],
    }

    logs = conn.execute(
        """
        SELECT level, message, created_at
        FROM system_logs
        ORDER BY id DESC
        LIMIT 15
        """
    ).fetchall()

    conn.close()
    return render_template(
        "developer_dashboard.html",
        stats=stats,
        logs=logs,
    )


@app.route("/run-bots", methods=["POST"])
@developer_required
def run_bots():
    conn = db()
    checks = []

    try:
        result = conn.execute("PRAGMA integrity_check").fetchone()
        if result and result[0] == "ok":
            checks.append("Database integrity check: OK")
        else:
            checks.append("Database integrity check: ISSUE")
    except Exception as exc:
        checks.append("Database check issue detected")
        conn.execute(
            "INSERT INTO system_logs (level, message) VALUES (?, ?)",
            ("ERROR", f"Database check failed: {str(exc)[:300]}"),
        )

    try:
        conn.execute("SELECT 1").fetchone()
        checks.append("Database connectivity: OK")
    except Exception:
        checks.append("Database connectivity: ISSUE")

    for item in checks:
        conn.execute(
            "INSERT INTO system_logs (level, message) VALUES (?, ?)",
            ("INFO", f"System Checker: {item}"),
        )

    conn.execute(
        "INSERT INTO system_logs (level, message) VALUES (?, ?)",
        ("INFO", "System Security: authentication/session checks active"),
    )

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

    allowed = {
        "MPESA",
        "AIRTEL_MONEY",
        "MIXX_BY_YAS",
        "HALOPESA",
        "EZYPESA",
        "TTCLPESA",
    }

    import re

    if not re.fullmatch(r"255\d{9}", phone):
        return jsonify(
            {"error": "Tumia namba ya Tanzania ya muundo 255XXXXXXXXX."}
        ), 400

    if network not in allowed:
        return jsonify({"error": "Mtandao wa simu haujatambuliwa."}), 400

    conn = db()
    conn.execute(
        """
        UPDATE users
        SET payment_phone=?, payment_network=?
        WHERE id=?
        """,
        (phone, network, session["user_id"]),
    )
    conn.commit()
    conn.close()

    return jsonify({
        "success": True,
        "message": "Namba yako ya malipo imehifadhiwa.",
    })


@app.route("/api/profile/payout-destination", methods=["POST"])
@member_required
def update_payout_destination():
    data = request.get_json(silent=True) or {}
    method = str(data.get("payout_method", "mobile")).lower()

    if method not in {"mobile", "bank"}:
        return jsonify({"error": "Chagua simu au bank."}), 400

    conn = db()
    import re

    if method == "mobile":
        phone = str(data.get("payment_phone", "")).strip()
        network = str(data.get("payment_network", "MPESA")).upper()

        allowed = {
            "MPESA",
            "AIRTEL_MONEY",
            "MIXX_BY_YAS",
            "HALOPESA",
            "EZYPESA",
            "TTCLPESA",
        }

        if not re.fullmatch(r"255\d{9}", phone):
            conn.close()
            return jsonify({
                "error": "Tumia namba ya Tanzania ya muundo 255XXXXXXXXX."
            }), 400

        if network not in allowed:
            conn.close()
            return jsonify({
                "error": "Mtandao wa simu haujatambuliwa."
            }), 400

        conn.execute(
            """
            UPDATE users
            SET payout_method='mobile',
                payment_phone=?,
                payment_network=?,
                bank_code=NULL,
                bank_account=NULL,
                bank_account_name=NULL
            WHERE id=?
            """,
            (phone, network, session["user_id"]),
        )

    else:
        bank = str(data.get("bank_code", "")).upper().strip()
        account = str(data.get("bank_account", "")).strip()

        if bank not in {"CRDB", "NMB", "NBC", "ABSA"}:
            conn.close()
            return jsonify({
                "error": "Chagua bank inayoungwa mkono."
            }), 400

        if not re.fullmatch(r"\d{6,34}", account):
            conn.close()
            return jsonify({
                "error": "Namba ya akaunti ya bank si sahihi."
            }), 400

        conn.execute(
            """
            UPDATE users
            SET payout_method='bank',
                bank_code=?,
                bank_account=?,
                bank_account_name=NULL
            WHERE id=?
            """,
            (bank, account, session["user_id"]),
        )

    conn.commit()
    conn.close()

    return jsonify({
        "success": True,
        "message": "Njia ya kupokea malipo imehifadhiwa.",
    })


@app.route("/api/payout/verify-destination", methods=["POST"])
@member_required
def verify_payout_destination():
    if not BLMPAY_API_KEY:
        return jsonify({
            "error": "Payment gateway haijaunganishwa kwenye server."
        }), 503

    data = request.get_json(silent=True) or {}
    method = str(data.get("payout_method", "mobile")).lower()

    if method == "mobile":
        account = str(data.get("payment_phone", "")).strip()
        payload = {
            "channel": "mobile",
            "account_number": account,
        }
    elif method == "bank":
        account = str(data.get("bank_account", "")).strip()
        bank = str(data.get("bank_code", "")).upper().strip()
        payload = {
            "channel": "bank",
            "account_number": account,
            "bank_code": bank,
        }
    else:
        return jsonify({"error": "Njia si sahihi."}), 400

    try:
        response = requests.post(
            f"{BLMPAY_BASE_URL}/payouts/name-lookup",
            headers={
                "Authorization": f"Bearer {BLMPAY_API_KEY}",
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=20,
        )
        result = response.json()
    except Exception:
        return jsonify({
            "error": "Huduma ya uthibitishaji haipatikani kwa sasa."
        }), 502

    if response.status_code >= 400 or result.get("status") != "success":
        return jsonify({
            "error": result.get(
                "message",
                "Taarifa za mpokeaji hazijathibitishwa.",
            )
        }), 400

    name = (result.get("data") or {}).get("account_name")

    conn = db()
    if method == "mobile":
        conn.execute(
            """
            UPDATE users
            SET payout_method='mobile',
                payment_phone=?,
                payment_network=COALESCE(payment_network,'MPESA'),
                bank_account_name=?
            WHERE id=?
            """,
            (account, name, session["user_id"]),
        )
    else:
        conn.execute(
            """
            UPDATE users
            SET payout_method='bank',
                bank_code=?,
                bank_account=?,
                bank_account_name=?
            WHERE id=?
            """,
            (payload["bank_code"], account, name, session["user_id"]),
        )

    conn.commit()
    conn.close()

    return jsonify({
        "success": True,
        "account_name": name,
        "message": "Mpokeaji amethibitishwa.",
    })


@app.route("/api/leader/loan-disburse", methods=["POST"])
@member_required
def leader_loan_disburse():
    conn = db()

    actor = conn.execute(
        "SELECT role FROM users WHERE id=?",
        (session["user_id"],),
    ).fetchone()

    if not actor or actor["role"] != "leader":
        conn.close()
        return jsonify({
            "error": "Ni kiongozi aliyeidhinishwa pekee anayeruhusiwa kuanzisha malipo ya mkopo."
        }), 403

    data = request.get_json(silent=True) or {}

    try:
        member_id = int(data.get("member_id"))
        amount = int(float(data.get("amount", 0)))
    except (TypeError, ValueError):
        conn.close()
        return jsonify({
            "error": "Member ID au kiasi si sahihi."
        }), 400

    if amount < 1000:
        conn.close()
        return jsonify({
            "error": "Kiasi cha chini cha payout ni TZS 1,000."
        }), 400

    member = conn.execute(
        """
        SELECT id, full_name, payout_method, payment_phone,
               payment_network, bank_code, bank_account
        FROM users
        WHERE id=? AND status='active'
        """,
        (member_id,),
    ).fetchone()

    if not member:
        conn.close()
        return jsonify({"error": "Mwanakikundi hakupatikana."}), 404

    if not BLMPAY_API_KEY:
        conn.close()
        return jsonify({
            "error": "Payment gateway haijaunganishwa."
        }), 503

    method = member["payout_method"] or "mobile"
    tx_ref = "LOAN-" + secrets.token_hex(8).upper()

    if method == "bank":
        if not member["bank_code"] or not member["bank_account"]:
            conn.close()
            return jsonify({
                "error": "Mwanakikundi hajajaza taarifa za bank."
            }), 400

        payout = {
            "amount": amount,
            "currency": "TZS",
            "channel": "bank",
            "recipient_bank": member["bank_code"],
            "recipient_account": member["bank_account"],
            "narration": f"NJIAKIKOBA loan {tx_ref}",
            "metadata": {
                "tx_ref": tx_ref,
                "member_id": member_id,
                "type": "loan_disbursement",
            },
        }
    else:
        if not member["payment_phone"] or not member["payment_network"]:
            conn.close()
            return jsonify({
                "error": "Mwanakikundi hajajaza namba ya simu ya malipo."
            }), 400

        payout = {
            "amount": amount,
            "currency": "TZS",
            "channel": "mobile",
            "recipient_phone": member["payment_phone"],
            "network": member["payment_network"],
            "narration": f"NJIAKIKOBA loan {tx_ref}",
            "metadata": {
                "tx_ref": tx_ref,
                "member_id": member_id,
                "type": "loan_disbursement",
            },
        }

    conn.close()

    try:
        response = requests.post(
            f"{BLMPAY_BASE_URL}/payouts/send",
            headers={
                "Authorization": f"Bearer {BLMPAY_API_KEY}",
                "Content-Type": "application/json",
                "Idempotency-Key": tx_ref,
            },
            json=payout,
            timeout=25,
        )
        result = response.json()
    except Exception:
        return jsonify({
            "error": "Payout provider haipatikani kwa sasa."
        }), 502

    if response.status_code >= 400 or result.get("status") != "success":
        return jsonify({
            "error": result.get(
                "message",
                "Malipo hayakuanzishwa.",
            )
        }), 502

    ref = (result.get("data") or {}).get("reference")

    conn = db()
    conn.execute(
        """
        INSERT INTO transactions
        (user_id, tx_ref, tx_type, amount, commission, group_amount,
         status, provider, provider_reference, payment_reference)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            member_id,
            tx_ref,
            "loan_disbursement",
            amount,
            0,
            amount,
            "payout_processing",
            "BLMPay",
            ref,
            ref,
        ),
    )
    conn.commit()
    conn.close()

    return jsonify({
        "success": True,
        "reference": ref,
        "message": "Malipo ya mkopo yamepelekwa kwenye njia ya mwanakikundi.",
    }), 201


@app.route("/api/payment/create", methods=["POST"])
@member_required
def create_payment():
    data = request.get_json(silent=True) or {}

    try:
        amount = int(float(data.get("amount", 0)))
    except (TypeError, ValueError):
        amount = 0

    tx_type = data.get("tx_type", "savings")

    if amount < 100 or tx_type not in ("savings", "loan_repayment"):
        return jsonify({
            "error": "Kiasi au aina ya malipo si sahihi."
        }), 400

    conn = db()
    user = conn.execute(
        """
        SELECT full_name, email, payment_phone, payment_network
        FROM users WHERE id=?
        """,
        (session["user_id"],),
    ).fetchone()
    conn.close()

    if not user or not user["payment_phone"]:
        return jsonify({
            "error": "Weka kwanza namba yako ya malipo kwenye akaunti yako."
        }), 400

    if not user["email"]:
        return jsonify({
            "error": "Weka barua pepe kwenye akaunti yako kabla ya malipo."
        }), 400

    import re

    phone = user["payment_phone"]
    network = user["payment_network"] or "MPESA"

    if not re.fullmatch(r"255\d{9}", phone):
        return jsonify({
            "error": "Namba yako ya malipo si sahihi."
        }), 400

    commission = round(amount * COMMISSION_RATE, 2)
    group_amount = round(amount - commission, 2)
    tx_ref = "NJK-" + secrets.token_hex(8).upper()

    if not BLMPAY_API_KEY or not BLMPAY_WEBHOOK_URL:
        return jsonify({
            "error": "Payment gateway haijaunganishwa kikamilifu kwenye server."
        }), 503

    first, *last = user["full_name"].split()

    payload = {
        "payment_type": "mobile",
        "details": {
            "amount": amount,
            "currency": "TZS",
        },
        "phone_number": phone,
        "customer": {
            "firstname": first[:60],
            "lastname": " ".join(last)[:60] or first[:60],
            "email": user["email"],
        },
        "webhook_url": BLMPAY_WEBHOOK_URL,
        "metadata": {
            "tx_ref": tx_ref,
            "tx_type": tx_type,
            "network": network,
            "commission_percent": 2,
        },
    }

    try:
        response = requests.post(
            f"{BLMPAY_BASE_URL}/payments",
            headers={
                "Authorization": f"Bearer {BLMPAY_API_KEY}",
                "Content-Type": "application/json",
                "Idempotency-Key": tx_ref,
            },
            json=payload,
            timeout=25,
        )
        result = response.json()
    except Exception as exc:
        log_event("payment_gateway_error", str(exc))
        return jsonify({
            "error": "Payment gateway haipatikani kwa sasa."
        }), 502

    if response.status_code >= 400 or result.get("status") != "success":
        return jsonify({
            "error": result.get(
                "message",
                "Malipo hayakuanzishwa.",
            )
        }), 502

    pref = (result.get("data") or {}).get("reference")

    conn = db()
    conn.execute(
        """
        INSERT INTO transactions
        (user_id, tx_ref, tx_type, amount, commission, group_amount,
         provider, status, provider_reference, payment_reference)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            session["user_id"],
            tx_ref,
            tx_type,
            amount,
            commission,
            group_amount,
            "BLMPay",
            "awaiting_confirmation",
            pref,
            pref,
        ),
    )
    conn.commit()
    conn.close()

    return jsonify({
        "success": True,
        "tx_ref": tx_ref,
        "payment_reference": pref,
        "amount": amount,
        "message": "USSD push imetumwa kwenye namba yako. Ingiza PIN yako kuthibitisha.",
    }), 201


@app.route("/webhooks/blmpay", methods=["POST"])
def blmpay_webhook():
    if not BLMPAY_WEBHOOK_SECRET:
        return "Webhook secret not configured", 503

    raw = request.get_data()
    sig = request.headers.get("X-Webhook-Signature", "")
    timestamp = request.headers.get("X-Webhook-Timestamp", "")

    if not timestamp or not sig:
        return "Missing signature", 401

    expected = hmac.new(
        BLMPAY_WEBHOOK_SECRET.encode(),
        (timestamp + ".").encode() + raw,
        hashlib.sha256,
    ).hexdigest()

    if not hmac.compare_digest(expected, sig):
        return "Invalid signature", 401

    body = request.get_json(silent=True) or {}
    event = body.get("event") or body.get("type")
    data = body.get("data") or body

    tx_ref = (
        (data.get("metadata") or {}).get("tx_ref")
        or data.get("reference")
    )

    if not tx_ref:
        return "Missing transaction reference", 400

    conn = db()
    tx = conn.execute(
        "SELECT * FROM transactions WHERE tx_ref=?",
        (tx_ref,),
    ).fetchone()

    if not tx:
        conn.close()
        return "Transaction not found", 404

    status = str(data.get("status", "")).lower()

    if event == "payment.completed" or status == "completed":
        if tx["status"] == "paid":
            conn.close()
            return "OK", 200

        conn.execute(
            """
            UPDATE transactions
            SET status='paid',
                payment_reference=COALESCE(payment_reference, ?)
            WHERE tx_ref=?
            """,
            (data.get("reference"), tx_ref),
        )

        if tx["tx_type"] == "savings":
            conn.execute(
                "UPDATE users SET savings=savings+? WHERE id=?",
                (tx["group_amount"], tx["user_id"]),
            )
        elif tx["tx_type"] == "loan_repayment":
            conn.execute(
                """
                UPDATE users
                SET loan_balance=MAX(0, loan_balance-?)
                WHERE id=?
                """,
                (tx["group_amount"], tx["user_id"]),
            )

        dev_status = (
            "configured"
            if DEVELOPER_LIPA_NUMBER
            else "not_configured"
        )
        grp_status = (
            "configured"
            if GROUP_SETTLEMENT_PHONE
            else "not_configured"
        )

        conn.execute(
            """
            UPDATE transactions
            SET developer_settlement_status=?,
                group_settlement_status=?
            WHERE tx_ref=?
            """,
            (dev_status, grp_status, tx_ref),
        )

        conn.execute(
            "INSERT INTO system_logs(level,message) VALUES(?,?)",
            (
                "INFO",
                f"Paid {tx_ref}: 2% operating fee recorded server-side; "
                f"destination secret configured={bool(DEVELOPER_LIPA_NUMBER)}",
            ),
        )

    elif (
        event in (
            "payment.failed",
            "payment.expired",
            "payment.cancelled",
            "payment.voided",
        )
        or status in ("failed", "expired", "cancelled", "voided")
    ):
        conn.execute(
            """
            UPDATE transactions
            SET status='failed'
            WHERE tx_ref=? AND status!='paid'
            """,
            (tx_ref,),
        )

    conn.commit()
    conn.close()
    return "OK", 200


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("home"))


# Initialize database when the application starts.
init_db()


if __name__ == "__main__":
    app.run(
        debug=os.environ.get("FLASK_DEBUG") == "1",
        host="0.0.0.0",
        port=int(os.environ.get("PORT", 5000)),
    )
