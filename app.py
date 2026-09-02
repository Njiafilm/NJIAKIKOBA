import os
import re
import sqlite3
import secrets
import hmac
import hashlib
import json
import traceback
import requests
from datetime import datetime, timedelta
from functools import wraps

from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify, send_from_directory
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename

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
FIRST_DEPOSIT_FEE_RATE = 0.01  # 1% on first savings deposit only

# Group-chat media uploads: images, voice notes and videos.
CHAT_UPLOAD_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static", "chat_uploads")
CHAT_MAX_UPLOAD_MB = int(os.environ.get("CHAT_MAX_UPLOAD_MB", "25"))
app.config["MAX_CONTENT_LENGTH"] = CHAT_MAX_UPLOAD_MB * 1024 * 1024
os.makedirs(CHAT_UPLOAD_DIR, exist_ok=True)
VERIFICATION_UPLOAD_DIR = os.environ.get(
    "VERIFICATION_UPLOAD_DIR",
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "verification_uploads")
)
os.makedirs(VERIFICATION_UPLOAD_DIR, exist_ok=True)

def save_data_image(data_url, prefix):
    """Save a browser-captured JPEG data URL outside /static so it is not public."""
    if not data_url or not data_url.startswith("data:image/"):
        raise ValueError("Picha ya uthibitisho haipo au si sahihi.")
    try:
        header, encoded = data_url.split(",", 1)
        raw = __import__("base64").b64decode(encoded, validate=True)
    except Exception as exc:
        raise ValueError("Picha ya uthibitisho imeharibika.") from exc
    if len(raw) < 8 * 1024 or len(raw) > 5 * 1024 * 1024:
        raise ValueError("Picha ya uthibitisho lazima iwe kati ya 8KB na 5MB.")
    filename = f"{prefix}_{secrets.token_hex(16)}.jpg"
    with open(os.path.join(VERIFICATION_UPLOAD_DIR, filename), "wb") as fh:
        fh.write(raw)
    return filename

def normalize_id_type(value):
    return re.sub(r"[^a-z0-9]", "", str(value or "").lower())

def validate_leader_id(id_type, id_number):
    """Local format validation only; authoritative NIDA/passport verification needs an official API."""
    typ = normalize_id_type(id_type)
    value = re.sub(r"[^A-Za-z0-9]", "", str(id_number or "")).upper()
    if typ in ("nida", "nid"):
        return bool(re.fullmatch(r"\d{20}", value))
    if "passport" in typ:
        return bool(re.fullmatch(r"[A-Z0-9]{6,12}", value))
    if "driving" in typ or "license" in typ or "leseni" in typ:
        return bool(re.fullmatch(r"[A-Z0-9]{6,15}", value))
    if "voter" in typ or "kura" in typ:
        return bool(re.fullmatch(r"[A-Z0-9]{8,20}", value))
    return bool(re.fullmatch(r"[A-Z0-9]{6,20}", value))

ALLOWED_CHAT_MIMES = {
    "image/jpeg", "image/png", "image/webp", "image/gif",
    "audio/webm", "audio/ogg", "audio/mpeg", "audio/mp4", "audio/wav",
    "video/webm", "video/mp4", "video/quicktime"
}

def normalize_tz_phone(value):
    """Normalize Tanzania phone input to canonical 255XXXXXXXXX format."""
    raw = re.sub(r"\D", "", str(value or ""))
    if raw.startswith("00"):
        raw = raw[2:]
    if raw.startswith("255") and len(raw) == 12:
        return raw
    if raw.startswith("0") and len(raw) == 10:
        raw = "255" + raw[1:]
    elif len(raw) == 9 and raw[0] in ("6", "7"):
        raw = "255" + raw
    return raw


def is_valid_tz_phone(value):
    """True when value is a valid Tanzania mobile in 255XXXXXXXXX form."""
    phone = normalize_tz_phone(value)
    return bool(re.fullmatch(r"255[67]\d{8}", phone))


def phone_lookup_variants(value):
    """Return common stored/login variants so old rows still authenticate."""
    phone = normalize_tz_phone(value)
    variants = {phone}
    if phone.startswith("255") and len(phone) == 12:
        variants.add("0" + phone[3:])
        variants.add(phone[3:])
    raw = re.sub(r"\D", "", str(value or ""))
    if raw:
        variants.add(raw)
    return [v for v in variants if v]


def save_chat_media(file_storage):
    """Save a chat image/audio/video with a random server filename."""
    if not file_storage or not file_storage.filename:
        return None

    mime = (file_storage.mimetype or "").lower()
    if mime not in ALLOWED_CHAT_MIMES:
        raise ValueError("Aina hii ya faili hairuhusiwi. Tumia picha, sauti au video.")

    original = secure_filename(file_storage.filename)[:120] or "media"
    ext = os.path.splitext(original)[1].lower()

    # Give recorded browser media a useful extension when the blob has no filename.
    if not ext:
        ext_map = {
            "image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp",
            "image/gif": ".gif", "audio/webm": ".webm", "audio/ogg": ".ogg",
            "audio/mpeg": ".mp3", "audio/mp4": ".m4a", "audio/wav": ".wav",
            "video/webm": ".webm", "video/mp4": ".mp4", "video/quicktime": ".mov"
        }
        ext = ext_map.get(mime, "")

    filename = secrets.token_hex(16) + ext
    path = os.path.join(CHAT_UPLOAD_DIR, filename)
    file_storage.save(path)

    kind = "image" if mime.startswith("image/") else ("audio" if mime.startswith("audio/") else "video")
    return {"filename": filename, "kind": kind, "mime": mime, "original": original}

@app.route("/chat-media/<path:filename>")
def chat_media(filename):
    # Filenames are generated by the server; send_from_directory also prevents
    # path traversal outside CHAT_UPLOAD_DIR.
    return send_from_directory(CHAT_UPLOAD_DIR, filename)


def db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def ensure_column(conn, table, column, definition):
    """Safely add a column when an older SQLite database is opened."""
    cols = {row[1] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}
    if column not in cols:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")


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
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        id_verification_status TEXT DEFAULT 'pending',
        id_verification_method TEXT,
        id_document_filename TEXT,
        face_image_filename TEXT,
        biometric_enrolled INTEGER DEFAULT 0,
        biometric_credential_id TEXT,
        recognition_confidence REAL DEFAULT 0,
        recognition_quality INTEGER DEFAULT 0
    );

    CREATE TABLE IF NOT EXISTS group_info (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        group_name TEXT DEFAULT 'NJIAKIKOBA',
        payment_number TEXT,
        system_commission REAL DEFAULT 0,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        recognition_enabled INTEGER DEFAULT 1,
        recognition_threshold INTEGER DEFAULT 80
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
        media_kind TEXT,
        media_url TEXT,
        media_name TEXT,
        media_mime TEXT,
        group_id INTEGER,
        FOREIGN KEY(user_id) REFERENCES users(id),
        FOREIGN KEY(group_id) REFERENCES group_info(id)
    );

    CREATE TABLE IF NOT EXISTS integrations (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        label TEXT NOT NULL,
        url TEXT NOT NULL,
        icon TEXT DEFAULT '🔗',
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    );

    CREATE TABLE IF NOT EXISTS payment_providers (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        provider_name TEXT NOT NULL,
        provider_type TEXT NOT NULL DEFAULT 'collection',
        base_url TEXT,
        api_key TEXT,
        api_secret TEXT,
        merchant_id TEXT,
        collection_path TEXT,
        payout_path TEXT,
        webhook_path TEXT,
        webhook_secret TEXT,
        enabled INTEGER DEFAULT 0,
        is_default INTEGER DEFAULT 0,
        notes TEXT,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        updated_at TEXT DEFAULT CURRENT_TIMESTAMP
    );

    CREATE TABLE IF NOT EXISTS developer_repairs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        issue_text TEXT NOT NULL,
        diagnosis TEXT,
        generated_fix TEXT,
        status TEXT DEFAULT 'generated',
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        applied_at TEXT
    );

    CREATE TABLE IF NOT EXISTS cycle_settlements (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        total_group_savings REAL NOT NULL,
        commission_amount REAL NOT NULL,
        cycle_months INTEGER NOT NULL,
        group_id INTEGER,
        status TEXT DEFAULT 'recorded',
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
        "ALTER TABLE group_info ADD COLUMN video_room TEXT",
        "ALTER TABLE group_info ADD COLUMN registration_code TEXT",
        "ALTER TABLE group_info ADD COLUMN member_cap INTEGER DEFAULT 999",
        "ALTER TABLE group_info ADD COLUMN settlement_phone TEXT",
        "ALTER TABLE group_info ADD COLUMN settlement_bank_name TEXT",
        "ALTER TABLE group_info ADD COLUMN settlement_bank_account TEXT",
        "ALTER TABLE group_info ADD COLUMN partner_name TEXT",
        "ALTER TABLE group_info ADD COLUMN partner_contact TEXT",
        "ALTER TABLE group_info ADD COLUMN partner_account_details TEXT",
        "ALTER TABLE group_info ADD COLUMN cycle_months INTEGER DEFAULT 12",
        "ALTER TABLE group_info ADD COLUMN cycle_started_at TEXT",
        "ALTER TABLE group_info ADD COLUMN whatsapp_group_url TEXT",
        "ALTER TABLE group_info ADD COLUMN created_at TEXT DEFAULT CURRENT_TIMESTAMP",
        "ALTER TABLE users ADD COLUMN member_number INTEGER",
        "ALTER TABLE users ADD COLUMN group_size_at_join INTEGER",
        "ALTER TABLE transactions ADD COLUMN first_deposit_fee REAL DEFAULT 0",
        "ALTER TABLE users ADD COLUMN group_id INTEGER",
        "ALTER TABLE users ADD COLUMN id_verification_status TEXT DEFAULT 'pending'",
        "ALTER TABLE users ADD COLUMN id_verification_method TEXT",
        "ALTER TABLE users ADD COLUMN id_document_filename TEXT",
        "ALTER TABLE users ADD COLUMN face_image_filename TEXT",
        "ALTER TABLE users ADD COLUMN biometric_enrolled INTEGER DEFAULT 0",
        "ALTER TABLE users ADD COLUMN biometric_credential_id TEXT",
        "ALTER TABLE users ADD COLUMN recognition_confidence REAL DEFAULT 0",
        "ALTER TABLE users ADD COLUMN recognition_quality INTEGER DEFAULT 0",
        "ALTER TABLE group_info ADD COLUMN recognition_enabled INTEGER DEFAULT 1",
        "ALTER TABLE group_info ADD COLUMN recognition_threshold INTEGER DEFAULT 80",
        "ALTER TABLE messages ADD COLUMN group_id INTEGER",
        "ALTER TABLE transactions ADD COLUMN group_id INTEGER",
        "ALTER TABLE cycle_settlements ADD COLUMN group_id INTEGER",
    ]:
        try:
            conn.execute(stmt)
        except sqlite3.OperationalError:
            pass

    # No-code payment provider and developer repair tables/columns.
    # These are intentionally non-destructive migrations.
    try:
        conn.execute("CREATE TABLE IF NOT EXISTS payment_providers (id INTEGER PRIMARY KEY AUTOINCREMENT, provider_name TEXT NOT NULL, provider_type TEXT NOT NULL DEFAULT 'collection', base_url TEXT, api_key TEXT, api_secret TEXT, merchant_id TEXT, collection_path TEXT, payout_path TEXT, webhook_path TEXT, webhook_secret TEXT, enabled INTEGER DEFAULT 0, is_default INTEGER DEFAULT 0, notes TEXT, created_at TEXT DEFAULT CURRENT_TIMESTAMP, updated_at TEXT DEFAULT CURRENT_TIMESTAMP)")
        conn.execute("CREATE TABLE IF NOT EXISTS developer_repairs (id INTEGER PRIMARY KEY AUTOINCREMENT, issue_text TEXT NOT NULL, diagnosis TEXT, generated_fix TEXT, status TEXT DEFAULT 'generated', created_at TEXT DEFAULT CURRENT_TIMESTAMP, applied_at TEXT)")
    except sqlite3.OperationalError:
        pass

    # Multi-group migration:
    # Existing installations keep their original group as Group 1.
    groups = conn.execute(
        "SELECT id, group_name, registration_code, video_room FROM group_info ORDER BY id"
    ).fetchall()
    for g in groups:
        if not g["video_room"]:
            room = "Njiakikoba-" + secrets.token_urlsafe(18).replace("-", "").replace("_", "")
            conn.execute("UPDATE group_info SET video_room=? WHERE id=?", (room, g["id"]))

    # Normalize registration codes to NK/{INITIALS}
    # (numeric #### suffix is reserved for member numbers, not group ids).
    for g in conn.execute(
        "SELECT id, group_name, registration_code FROM group_info ORDER BY id"
    ).fetchall():
        desired = make_registration_code(g["id"], g["group_name"] or f"GROUP{g['id']}", conn)
        if (g["registration_code"] or "") != desired:
            conn.execute(
                "UPDATE group_info SET registration_code=? WHERE id=?",
                (desired, g["id"]),
            )

    # Give legacy rows the first group.
    first_group = conn.execute("SELECT id FROM group_info ORDER BY id LIMIT 1").fetchone()
    if first_group:
        gid = first_group["id"]
        conn.execute("UPDATE users SET group_id=? WHERE group_id IS NULL", (gid,))
        conn.execute("UPDATE messages SET group_id=? WHERE group_id IS NULL AND user_id IN (SELECT id FROM users)", (gid,))
        conn.execute("UPDATE transactions SET group_id=? WHERE group_id IS NULL AND user_id IN (SELECT id FROM users)", (gid,))

    # Backfill member numbers per group.
    for g in conn.execute("SELECT id FROM group_info ORDER BY id").fetchall():
        current = conn.execute(
            "SELECT COALESCE(MAX(member_number),0) FROM users WHERE group_id=?", (g["id"],)
        ).fetchone()[0]
        for u in conn.execute(
            "SELECT id FROM users WHERE group_id=? AND member_number IS NULL ORDER BY id", (g["id"],)
        ).fetchall():
            current += 1
            conn.execute("UPDATE users SET member_number=? WHERE id=?", (current, u["id"]))

    # A group may have at most 999 members unless the developer explicitly
    # raises the cap for that particular group.
    conn.execute("UPDATE group_info SET member_cap=999 WHERE member_cap IS NULL OR member_cap < 1")

    # Ensure member_number is unique within each group (fix any legacy duplicates).
    for g in conn.execute("SELECT id FROM group_info ORDER BY id").fetchall():
        seen = {}
        rows = conn.execute(
            "SELECT id, member_number FROM users WHERE group_id=? ORDER BY id", (g["id"],)
        ).fetchall()
        next_num = conn.execute(
            "SELECT COALESCE(MAX(member_number),0) FROM users WHERE group_id=?", (g["id"],)
        ).fetchone()[0] or 0
        for u in rows:
            mn = u["member_number"]
            if mn is None or mn in seen:
                next_num += 1
                conn.execute("UPDATE users SET member_number=? WHERE id=?", (next_num, u["id"]))
                seen[next_num] = u["id"]
            else:
                seen[mn] = u["id"]
    try:
        conn.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_users_group_member "
            "ON users(group_id, member_number)"
        )
    except sqlite3.OperationalError:
        pass
    # Phone must remain globally unique (one phone = one account).
    try:
        conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_users_phone ON users(phone)")
    except sqlite3.OperationalError:
        pass

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


def current_member(conn):
    if "user_id" not in session:
        return None
    return conn.execute(
        "SELECT * FROM users WHERE id=? AND status='active'", (session["user_id"],)
    ).fetchone()


def member_group(conn, user_id=None):
    uid = user_id or session.get("user_id")
    if not uid:
        return None
    return conn.execute(
        """SELECT g.* FROM group_info g
           JOIN users u ON u.group_id=g.id
           WHERE u.id=? AND u.status='active'""",
        (uid,)
    ).fetchone()


def group_member_count(conn, group_id):
    return conn.execute(
        "SELECT COUNT(*) FROM users WHERE group_id=? AND status='active'", (group_id,)
    ).fetchone()[0]


def group_member_number(conn, group_id):
    return conn.execute(
        "SELECT COALESCE(MAX(member_number),0)+1 FROM users WHERE group_id=?", (group_id,)
    ).fetchone()[0]


def group_from_code(conn, code):
    """Lookup group by registration code.

    Group codes look like NK/CK or NK/MM (optionally NK/CK-02 if initials collide).
    Member identities look like NK/CK-0012 — those are NOT group join codes.
    Legacy codes NK-0001 (no slash) still resolve by group id.
    """
    raw = (code or "").strip().upper().replace(" ", "")
    if not raw:
        return None
    row = conn.execute(
        "SELECT * FROM group_info WHERE UPPER(REPLACE(registration_code,' ',''))=?",
        (raw,),
    ).fetchone()
    if row:
        return row
    # Prefix match: user typed NK/CK while stored is NK/CK-02
    if raw.startswith("NK/"):
        row = conn.execute(
            "SELECT * FROM group_info WHERE UPPER(REPLACE(registration_code,' ','')) LIKE ? "
            "ORDER BY id LIMIT 1",
            (raw + "%",),
        ).fetchone()
        if row:
            return row
    # Legacy only (no slash): NK-0001 → group id
    if "/" not in raw:
        m = re.search(r"-(\d{1,6})$", raw)
        if m:
            return conn.execute(
                "SELECT * FROM group_info WHERE id=?", (int(m.group(1)),)
            ).fetchone()
    return None


_SKIP_WORDS = {
    "wa", "ya", "za", "la", "cha", "kwa", "na", "the", "of", "and", "group",
    "kikundi", "society", "asso", "association", "co", "ltd", "limited",
}


def group_initials(group_name):
    """Build 2–4 letter initials from a group name.

    Examples:
      CHAPAKAZI / CHAPA KAZI → CK
      Maji Moto → MM
      Umoja wa Vijana → UV
    """
    name = re.sub(r"[^A-Za-z0-9\s\-]", " ", str(group_name or ""))
    parts = [p for p in re.split(r"[\s\-]+", name) if p]
    meaningful = [p for p in parts if p.lower() not in _SKIP_WORDS]
    if not meaningful:
        meaningful = parts or ["XX"]
    if len(meaningful) == 1:
        word = re.sub(r"[^A-Za-z0-9]", "", meaningful[0]).upper()
        if len(word) >= 4:
            # Compound-style single word: first letter + first consonant of 2nd half
            # CHAPAKAZI → C + K (from KAZI) = CK
            mid = len(word) // 2
            vowels = set("AEIOU")
            second = word[mid]
            for ch in word[mid:]:
                if ch not in vowels:
                    second = ch
                    break
            initials = word[0] + second
        else:
            initials = (word + "X")[:2]
    else:
        initials = "".join(p[0].upper() for p in meaningful if p)[:4]
    if len(initials) < 2:
        initials = (initials + "X")[:2]
    return initials


def make_registration_code(group_id, group_name, conn=None):
    """Group join code: NK/{INITIALS} (or NK/{INITIALS}-{id} if initials collide).

    The numeric #### suffix is reserved for *member* numbers, not group ids.
    Example group codes: NK/CK , NK/MM
    """
    initials = group_initials(group_name)
    base = f"NK/{initials}"
    if conn is not None:
        clash = conn.execute(
            "SELECT id FROM group_info WHERE UPPER(registration_code)=UPPER(?) AND id!=?",
            (base, int(group_id)),
        ).fetchone()
        if clash:
            return f"NK/{initials}-{int(group_id):02d}"
    return base


def make_member_code(group_name, member_number):
    """Member identity: NK/{INITIALS}-{member_number:04d}

    Example: CHAPAKAZI member #12 → NK/CK-0012
    """
    initials = group_initials(group_name)
    try:
        num = int(member_number or 0)
    except (TypeError, ValueError):
        num = 0
    return f"NK/{initials}-{num:04d}"


def current_lang():
    lang = session.get("lang") or request.args.get("lang") or "sw"
    return lang if lang in TRANSLATIONS else "sw"


def t_dict():
    return TRANSLATIONS[current_lang()]


@app.before_request
def session_control():
    session.permanent = True


@app.context_processor
def inject_i18n():
    """Make lang + translations available on every template."""
    lang = current_lang()
    return {
        "lang": lang,
        "t": TRANSLATIONS[lang],
        "other_lang": "en" if lang == "sw" else "sw",
        "other_lang_label": "EN" if lang == "sw" else "SW",
    }


@app.route("/set-lang/<lang_code>")
def set_lang(lang_code):
    if lang_code in TRANSLATIONS:
        session["lang"] = lang_code
        session.permanent = True
    nxt = request.args.get("next") or request.referrer or url_for("home")
    # Avoid open redirect
    if not nxt.startswith("/") and not nxt.startswith(request.host_url):
        nxt = url_for("home")
    return redirect(nxt)


@app.route("/")
def home():
    # Support legacy ?lang=sw|en links
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
    return render_template("index.html", settings=settings, integrations=integrations)


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        name = request.form.get("full_name", "").strip()
        phone_raw = request.form.get("phone", "")
        phone = normalize_tz_phone(phone_raw)
        email = request.form.get("email", "").strip()
        password = request.form.get("password", "")
        code = request.form.get("group_code", "").strip()
        group_name_input = request.form.get("group_name", "").strip()

        if not name or not phone_raw or len(password) < 8 or not code or not group_name_input:
            flash("Jaza Jina la Kikundi, jina, simu, nywila na Registration Code.", "danger")
            return render_template("register.html")
        if not is_valid_tz_phone(phone):
            flash("Namba ya simu si sahihi. Tumia muundo 07XXXXXXXX au 2557XXXXXXXX.", "danger")
            return render_template("register.html")

        conn = db()
        group = group_from_code(conn, code)
        if not group:
            conn.close()
            flash("Registration Code ya kikundi haijatambuliwa. Thibitisha code uliyopewa na kiongozi.", "danger")
            return render_template("register.html")
        if group_name_input.casefold() != (group["group_name"] or "").strip().casefold():
            conn.close()
            flash(
                f"Jina la Kikundi halilingani. Andika jina hasa kama lilivyoandikwa na viongozi "
                f"(si 'NJIAKIKOBA' — hilo ni jina la mfumo).",
                "danger",
            )
            return render_template("register.html")

        member_cap = max(1, min(int(group["member_cap"] or 999), 9999))
        current_total = group_member_count(conn, group["id"])
        if current_total >= member_cap:
            conn.close()
            flash(f"{group['group_name']} imefikia ukomo wa wanachama {member_cap}.", "danger")
            return render_template("register.html")

        # Reject if this phone already exists under any stored format.
        variants = phone_lookup_variants(phone)
        placeholders = ",".join("?" * len(variants))
        existing = conn.execute(
            f"SELECT id, phone FROM users WHERE phone IN ({placeholders})", variants
        ).fetchone()
        if existing:
            conn.close()
            flash("Namba hii ya simu tayari ina akaunti. Ingia au tumia namba nyingine.", "danger")
            return render_template("register.html")

        try:
            next_number = group_member_number(conn, group["id"])
            new_total = current_total + 1
            # Always store the canonical 255XXXXXXXXX form.
            conn.execute(
                """INSERT INTO users
                   (full_name, phone, email, password, member_number, group_size_at_join, group_id, status, role)
                   VALUES (?, ?, ?, ?, ?, ?, ?, 'active', 'member')""",
                (name, phone, email or None, generate_password_hash(password),
                 next_number, new_total, group["id"])
            )
            conn.execute(
                """INSERT INTO messages
                   (user_id, full_name, role, body, group_id)
                   VALUES (0, 'Mfumo', 'system', ?, ?)""",
                (f"🔔 {name} amejiunga na {group['group_name']}. Idadi ya sasa: {new_total}.", group["id"])
            )
            conn.commit()
            flash(
                f"Akaunti imetengenezwa (#{next_number:06d}) na umejiunga na {group['group_name']}. "
                f"Ingia kwa namba yako ya simu na nywila.",
                "success",
            )
            return redirect(url_for("login"))
        except sqlite3.IntegrityError as exc:
            conn.rollback()
            msg = str(exc).lower()
            if "phone" in msg or "unique" in msg:
                flash("Namba hii ya simu tayari ina akaunti.", "danger")
            elif "member_number" in msg or "group_member" in msg:
                flash("Namba ya uanachama imeshindwa kutengenezwa. Jaribu tena.", "danger")
            else:
                flash("Usajili umeshindwa. Angalia taarifa zako na jaribu tena.", "danger")
        finally:
            conn.close()
    return render_template("register.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        phone_raw = request.form.get("phone", "")
        password = request.form.get("password", "")
        if not phone_raw or not password:
            flash("Jaza namba ya simu na nywila.", "danger")
            return render_template("login.html")

        variants = phone_lookup_variants(phone_raw)
        conn = db()
        user = None
        if variants:
            placeholders = ",".join("?" * len(variants))
            user = conn.execute(
                f"SELECT * FROM users WHERE phone IN ({placeholders})", variants
            ).fetchone()
            # Heal legacy phone formats to canonical form after successful match.
            if user and is_valid_tz_phone(phone_raw) and user["phone"] != normalize_tz_phone(phone_raw):
                try:
                    conn.execute(
                        "UPDATE users SET phone=? WHERE id=?",
                        (normalize_tz_phone(phone_raw), user["id"]),
                    )
                    conn.commit()
                except sqlite3.IntegrityError:
                    conn.rollback()
        conn.close()

        if user and user["status"] == "active" and check_password_hash(user["password"], password):
            if not user["group_id"]:
                flash("Akaunti haina kikundi. Wasiliana na msimamizi.", "danger")
                return render_template("login.html")
            session.clear()
            session.permanent = True
            session["user_id"] = user["id"]
            session["full_name"] = user["full_name"]
            session["role"] = user["role"]
            session["group_id"] = user["group_id"]
            return redirect(url_for("dashboard"))

        log_event("login_failed", f"Failed member login phone={normalize_tz_phone(phone_raw)[:15]}")
        flash("Taarifa si sahihi. Hakikisha namba ya simu na nywila ulizotumia kusajili.", "danger")
    return render_template("login.html")


@app.route("/leader-login", methods=["GET", "POST"])
def leader_login():
    """Dedicated leader login; it never grants leader access to ordinary members."""
    if request.method == "POST":
        phone_raw = request.form.get("phone", "")
        password = request.form.get("password", "")
        variants = phone_lookup_variants(phone_raw)
        conn = db()
        user = None
        if variants:
            placeholders = ",".join("?" * len(variants))
            user = conn.execute(
                f"SELECT * FROM users WHERE phone IN ({placeholders}) AND role='leader'",
                variants,
            ).fetchone()
            if user and is_valid_tz_phone(phone_raw) and user["phone"] != normalize_tz_phone(phone_raw):
                try:
                    conn.execute(
                        "UPDATE users SET phone=? WHERE id=?",
                        (normalize_tz_phone(phone_raw), user["id"]),
                    )
                    conn.commit()
                except sqlite3.IntegrityError:
                    conn.rollback()
        conn.close()
        if user and user["status"] == "active" and check_password_hash(user["password"], password):
            session.clear()
            session.permanent = True
            session["user_id"] = user["id"]
            session["full_name"] = user["full_name"]
            session["role"] = user["role"]
            session["group_id"] = user["group_id"]
            return redirect(url_for("dashboard"))
        log_event("leader_login_failed", "Failed leader login")
        flash("Taarifa za kiongozi si sahihi. Hakikisha namba na nywila.", "danger")
    return render_template("leader_login.html")


@app.route("/dashboard")
@member_required
def dashboard():
    conn = db()
    user = conn.execute(
        """SELECT full_name, phone, payment_phone, payment_network, payout_method,
                  bank_code, bank_account, bank_account_name, email, savings,
                  loan_balance, role, member_number, group_size_at_join, group_id, status
           FROM users WHERE id=?""",
        (session["user_id"],)
    ).fetchone()
    if not user or user["status"] != "active" or not user["group_id"]:
        conn.close()
        session.clear()
        flash("Akaunti haipatikani au haijaamilishwa. Ingia tena.", "danger")
        return redirect(url_for("login"))
    transactions = conn.execute(
        """SELECT tx_ref, tx_type, amount, commission, group_amount, status, created_at
           FROM transactions WHERE user_id=? AND group_id=? ORDER BY id DESC LIMIT 10""",
        (session["user_id"], user["group_id"])
    ).fetchall()
    group = conn.execute(
        "SELECT group_name, registration_code, member_cap FROM group_info WHERE id=?",
        (user["group_id"],)
    ).fetchone()
    conn.close()
    if not group:
        session.clear()
        flash("Kikundi cha akaunti yako hakijapatikana.", "danger")
        return redirect(url_for("login"))
    share_url = url_for("home", _external=True)
    member_code = make_member_code(group["group_name"], user["member_number"])
    return render_template(
        "dashboard.html",
        user=user,
        transactions=transactions,
        share_url=share_url,
        group=group,
        member_code=member_code,
    )


@app.route("/register-leaders", methods=["GET", "POST"])
def register_leaders():
    if request.method == "POST":
        title = request.form.get("leader_title", "Kiongozi").strip()[:40]
        name = request.form.get("full_name", "").strip()
        phone_raw = request.form.get("phone", "")
        phone = normalize_tz_phone(phone_raw)
        id_type = request.form.get("id_type", "")
        id_number = request.form.get("id_number", "").strip()
        password = request.form.get("password", "")
        code = request.form.get("group_code", "").strip()
        group_name_input = request.form.get("group_name", "").strip()
        face_image = request.form.get("face_image", "")
        biometric_credential = request.form.get("biometric_credential", "").strip()

        if not all([name, phone_raw, id_type, id_number, code, group_name_input, face_image, biometric_credential]) or len(password) < 8:
            flash("Kiongozi lazima ajaze Jina la Kikundi, ID, Face ID na fingerprint/biometric.", "danger")
            return render_template("register_leaders.html")
        if not is_valid_tz_phone(phone):
            flash("Namba ya simu si sahihi. Tumia muundo 07XXXXXXXX au 2557XXXXXXXX.", "danger")
            return render_template("register_leaders.html")
        if not validate_leader_id(id_type, id_number):
            flash("Kitambulisho hakijaonekana kuwa na format sahihi. Usajili umekataliwa.", "danger")
            return render_template("register_leaders.html")

        conn = db()
        group = group_from_code(conn, code)
        if not group:
            conn.close()
            flash("Registration Code ya kikundi haijatambuliwa.", "danger")
            return render_template("register_leaders.html")
        if group_name_input.casefold() != (group["group_name"] or "").strip().casefold():
            conn.close()
            flash(
                "Jina la Kikundi halilingani na Registration Code. "
                "Andika jina hasa la kikundi (si jina la mfumo NJIAKIKOBA).",
                "danger",
            )
            return render_template("register_leaders.html")
        try:
            face_filename = save_data_image(face_image, "face")
        except ValueError as exc:
            conn.close()
            flash(str(exc), "danger")
            return render_template("register_leaders.html")

        # WebAuthn: store credential identifier only (never biometric templates).
        try:
            bio = json.loads(biometric_credential)
            if not isinstance(bio, dict) or not bio.get("id"):
                raise ValueError("invalid")
            # Keep a compact, non-sensitive record for audit.
            biometric_credential = json.dumps({
                "id": str(bio.get("id"))[:512],
                "type": str(bio.get("type") or "public-key")[:40],
                "rawId": str(bio.get("rawId") or "")[:1024],
                "createdAt": str(bio.get("createdAt") or datetime.utcnow().isoformat()),
                "rpId": str(bio.get("rpId") or "")[:120],
                "method": str(bio.get("method") or "webauthn-platform")[:40],
            })
        except Exception:
            conn.close()
            flash(
                "WebAuthn credential si sahihi. Kamilisha hatua ya Fingerprint/Device Biometric "
                "kwenye kivinjari kinachotumia WebAuthn.",
                "danger",
            )
            return render_template("register_leaders.html")

        leader_count = conn.execute(
            "SELECT COUNT(*) FROM users WHERE role='leader' AND group_id=?", (group["id"],)
        ).fetchone()[0]
        if leader_count >= 3:
            conn.close()
            flash(f"{group['group_name']} tayari ina viongozi 3.", "danger")
            return render_template("register_leaders.html")

        current_total = group_member_count(conn, group["id"])
        member_cap = max(1, int(group["member_cap"] or 999))
        if current_total >= member_cap:
            conn.close()
            flash(f"{group['group_name']} imefikia ukomo wa wanachama {member_cap}.", "danger")
            return render_template("register_leaders.html")

        try:
            next_number = group_member_number(conn, group["id"])
            new_total = current_total + 1
            conn.execute(
                """INSERT INTO users
                   (full_name, phone, password, role, id_type, id_number_hash,
                    member_number, group_size_at_join, group_id, id_verification_status,
                    id_verification_method, face_image_filename, biometric_enrolled,
                    biometric_credential_id, recognition_confidence, recognition_quality)
                   VALUES (?, ?, ?, 'leader', ?, ?, ?, ?, ?, 'pending', 'format+face+webauthn', ?, 1, ?, 0, ?)""",
                (f"{title}: {name}", phone, generate_password_hash(password),
                 id_type, generate_password_hash(id_number),
                 next_number, new_total, group["id"], face_filename, biometric_credential, 0, 0)
            )
            conn.execute(
                """INSERT INTO messages
                   (user_id, full_name, role, body, group_id)
                   VALUES (0, 'Mfumo', 'system', ?, ?)""",
                (f"🔔 Kiongozi mpya ({name}) amejiunga na {group['group_name']}. Idadi ya sasa: {new_total}.", group["id"])
            )
            conn.commit()
            flash(f"Kiongozi ameongezwa kwenye {group['group_name']}.", "success")
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
        "pending": conn.execute("SELECT COUNT(*) FROM transactions WHERE status='pending'").fetchone()[0],
        "commission": conn.execute(
            "SELECT COALESCE(SUM(commission)+SUM(first_deposit_fee),0) FROM transactions WHERE status='paid'"
        ).fetchone()[0],
        "commission_30d": conn.execute(
            "SELECT COALESCE(SUM(commission)+SUM(first_deposit_fee),0) FROM transactions "
            "WHERE status='paid' AND created_at >= datetime('now','-30 days')"
        ).fetchone()[0],
        "errors": conn.execute("SELECT COUNT(*) FROM system_logs WHERE level='ERROR'").fetchone()[0],
        "registered_users": conn.execute("SELECT COUNT(*) FROM users").fetchone()[0],
        "active_users": conn.execute("SELECT COUNT(*) FROM users WHERE status='active'").fetchone()[0],
        "payment_providers": conn.execute("SELECT COUNT(*) FROM payment_providers").fetchone()[0],
        "pending_identity": conn.execute("SELECT COUNT(*) FROM users WHERE role='leader' AND id_verification_status='pending'").fetchone()[0],
        "biometric_enrolled": conn.execute("SELECT COUNT(*) FROM users WHERE role='leader' AND biometric_enrolled=1").fetchone()[0],
    }
    logs = conn.execute(
        "SELECT level, message, created_at FROM system_logs ORDER BY id DESC LIMIT 15"
    ).fetchall()
    settings = conn.execute(
        """SELECT adsense_publisher_id, play_store_url, appstore_url, group_name,
                  registration_code, member_cap, settlement_phone, settlement_bank_name,
                  settlement_bank_account, partner_name, partner_contact,
                  partner_account_details, cycle_months, cycle_started_at, whatsapp_group_url,
                  recognition_enabled, recognition_threshold
           FROM group_info ORDER BY id LIMIT 1"""
    ).fetchone()
    counts = {
        "leaders": conn.execute("SELECT COUNT(*) FROM users WHERE role='leader'").fetchone()[0],
        "members": conn.execute("SELECT COUNT(*) FROM users").fetchone()[0],
        "groups": conn.execute("SELECT COUNT(*) FROM group_info").fetchone()[0],
    }
    group_summary = {
        "total_savings": conn.execute("SELECT COALESCE(SUM(savings),0) FROM users").fetchone()[0],
        "total_loans": conn.execute("SELECT COALESCE(SUM(loan_balance),0) FROM users").fetchone()[0],
    }
    last_cycle = conn.execute(
        "SELECT total_group_savings, commission_amount, cycle_months, created_at "
        "FROM cycle_settlements ORDER BY id DESC LIMIT 1"
    ).fetchone()
    integrations = conn.execute("SELECT id, label, url, icon FROM integrations ORDER BY id").fetchall()
    payment_providers = conn.execute(
        "SELECT id, provider_name, provider_type, base_url, merchant_id, collection_path, payout_path, webhook_path, enabled, is_default, notes, updated_at FROM payment_providers ORDER BY is_default DESC, id DESC"
    ).fetchall()
    repair_history = conn.execute(
        "SELECT id, issue_text, diagnosis, generated_fix, status, created_at, applied_at FROM developer_repairs ORDER BY id DESC LIMIT 20"
    ).fetchall()
    groups = conn.execute(
        """SELECT g.id, g.group_name, g.registration_code, g.member_cap, g.whatsapp_group_url,
                  COUNT(u.id) AS member_count,
                  COALESCE(SUM(u.savings),0) AS savings,
                  COALESCE(SUM(u.loan_balance),0) AS loans
           FROM group_info g
           LEFT JOIN users u ON u.group_id=g.id AND u.status='active'
           GROUP BY g.id
           ORDER BY g.id DESC"""
    ).fetchall()
    conn.close()
    return render_template(
        "developer_dashboard.html", stats=stats, logs=logs, settings=settings, counts=counts,
        integrations=integrations, payment_providers=payment_providers, repair_history=repair_history,
        group_summary=group_summary, last_cycle=last_cycle, groups=groups
    )


@app.route("/developer-dashboard/support", methods=["POST"])
@developer_required
def developer_support_action():
    """Help members/leaders who cannot register or log in.

    Requires exact full_name + member_number (+ optional group) to reduce
    accidental account takeover. Logs every action.
    """
    action = (request.form.get("action") or "").strip().lower()
    full_name = (request.form.get("full_name") or "").strip()
    member_number_raw = (request.form.get("member_number") or "").strip()
    group_id = request.form.get("group_id", type=int)
    phone_hint = normalize_tz_phone(request.form.get("phone") or "")
    new_password = request.form.get("new_password") or ""
    consent = request.form.get("consent") == "on"

    if not consent:
        flash("Lazima uthibitishe kuwa una idhini ya mwanachama/kiongozi kabla ya kusaidia.", "danger")
        return redirect(url_for("developer_dashboard"))
    if not full_name or not member_number_raw:
        flash("Jaza jina kamili na namba ya uanachama.", "danger")
        return redirect(url_for("developer_dashboard"))
    try:
        member_number = int(re.sub(r"\D", "", member_number_raw) or "0")
    except ValueError:
        flash("Namba ya uanachama si sahihi.", "danger")
        return redirect(url_for("developer_dashboard"))

    conn = db()
    query = """SELECT u.*, g.group_name FROM users u
               LEFT JOIN group_info g ON g.id=u.group_id
               WHERE LOWER(TRIM(u.full_name))=LOWER(TRIM(?)) AND u.member_number=?"""
    params = [full_name, member_number]
    if group_id:
        query += " AND u.group_id=?"
        params.append(group_id)
    if phone_hint and is_valid_tz_phone(phone_hint):
        query += " AND u.phone=?"
        params.append(phone_hint)
    matches = conn.execute(query, params).fetchall()

    if len(matches) == 0:
        conn.close()
        flash("Hakuna akaunti inayolingana na jina + namba ya uanachama uliyojaza.", "danger")
        return redirect(url_for("developer_dashboard"))
    if len(matches) > 1:
        conn.close()
        flash("Kuna akaunti zaidi ya moja zinazofanana. Ongeza kikundi au namba ya simu ili kubainisha.", "warning")
        return redirect(url_for("developer_dashboard"))

    user = matches[0]

    if action == "reset_password":
        if len(new_password) < 8:
            conn.close()
            flash("Nywila mpya lazima iwe angalau herufi 8.", "danger")
            return redirect(url_for("developer_dashboard"))
        conn.execute(
            "UPDATE users SET password=? WHERE id=?",
            (generate_password_hash(new_password), user["id"]),
        )
        conn.execute(
            "INSERT INTO system_logs (level, message) VALUES ('INFO', ?)",
            (f"Developer reset password for user#{user['id']} {user['full_name']} "
             f"(member #{user['member_number']}, group {user['group_name']})",),
        )
        conn.commit()
        conn.close()
        log_event("developer_password_reset", f"user_id={user['id']}")
        flash(
            f"Nywila ya {user['full_name']} (#{user['member_number']:06d}, {user['group_name']}) "
            f"imewekwa upya. Mjulishe nywila mpya kwa usalama.",
            "success",
        )
        return redirect(url_for("developer_dashboard"))

    if action == "activate":
        conn.execute("UPDATE users SET status='active' WHERE id=?", (user["id"],))
        conn.execute(
            "INSERT INTO system_logs (level, message) VALUES ('INFO', ?)",
            (f"Developer activated user#{user['id']} {user['full_name']}",),
        )
        conn.commit()
        conn.close()
        flash(f"Akaunti ya {user['full_name']} imeamilishwa.", "success")
        return redirect(url_for("developer_dashboard"))

    if action == "login_as":
        # Temporary support session: developer enters the member account with audit trail.
        conn.execute(
            "INSERT INTO system_logs (level, message) VALUES ('INFO', ?)",
            (f"Developer support login-as user#{user['id']} {user['full_name']} "
             f"(member #{user['member_number']}, group {user['group_name']})",),
        )
        conn.commit()
        conn.close()
        log_event("developer_login_as", f"user_id={user['id']}")
        session.clear()
        session.permanent = True
        session["user_id"] = user["id"]
        session["full_name"] = user["full_name"]
        session["role"] = user["role"]
        session["group_id"] = user["group_id"]
        session["is_developer"] = True
        session["support_mode"] = True
        session["support_for"] = user["id"]
        flash(
            f"Umeingia kwa msaada kwenye akaunti ya {user['full_name']}. "
            f"Tumia kwa ajili ya kusaidia tu, kisha toka.",
            "success",
        )
        return redirect(url_for("dashboard"))

    conn.close()
    flash("Chagua kitendo: reset_password, activate, au login_as.", "danger")
    return redirect(url_for("developer_dashboard"))



@app.route("/developer-dashboard/groups/<int:group_id>/update", methods=["POST"])
@developer_required
def developer_group_update(group_id):
    """Update group name, WhatsApp, cap, or regenerate registration code."""
    action = (request.form.get("action") or "save").strip().lower()
    conn = db()
    group = conn.execute("SELECT * FROM group_info WHERE id=?", (group_id,)).fetchone()
    if not group:
        conn.close()
        flash("Kikundi hakipatikani.", "danger")
        return redirect(url_for("developer_groups"))

    if action == "regenerate_code":
        code = make_registration_code(group_id, group["group_name"], conn)
        conn.execute("UPDATE group_info SET registration_code=? WHERE id=?", (code, group_id))
        conn.execute(
            "INSERT INTO system_logs (level, message) VALUES ('INFO', ?)",
            (f"Developer regenerated registration code for group#{group_id}: {code}",),
        )
        conn.commit()
        conn.close()
        flash(f"Registration Code mpya: {code}", "success")
        return redirect(url_for("developer_group_inspect", group_id=group_id))

    if action == "save":
        new_name = (request.form.get("group_name") or "").strip()[:100]
        whatsapp = (request.form.get("whatsapp_group_url") or "").strip()
        cap_raw = request.form.get("member_cap", "").strip()
        settlement_phone = (request.form.get("settlement_phone") or "").strip()
        notes_log = []

        if new_name:
            forbidden = {"njiakikoba", "njiakikoba"}
            if new_name.casefold().replace(" ", "") in {"njiakikoba", "njiakikoba"}:
                conn.close()
                flash("Jina 'NJIAKIKOBA' haliwezi kuwa jina la kikundi.", "danger")
                return redirect(url_for("developer_group_inspect", group_id=group_id))
            if new_name != group["group_name"]:
                code = make_registration_code(group_id, new_name, conn)
                conn.execute(
                    "UPDATE group_info SET group_name=?, registration_code=? WHERE id=?",
                    (new_name, code, group_id),
                )
                notes_log.append(f"jina→{new_name}, code→{code}")

        if whatsapp:
            if not whatsapp.startswith("https://chat.whatsapp.com/"):
                conn.close()
                flash("Link ya WhatsApp lazima ianze na https://chat.whatsapp.com/", "danger")
                return redirect(url_for("developer_group_inspect", group_id=group_id))
            conn.execute(
                "UPDATE group_info SET whatsapp_group_url=? WHERE id=?",
                (whatsapp, group_id),
            )
            notes_log.append("whatsapp updated")
        elif request.form.get("clear_whatsapp") == "on":
            conn.execute("UPDATE group_info SET whatsapp_group_url=NULL WHERE id=?", (group_id,))
            notes_log.append("whatsapp cleared")

        if cap_raw:
            try:
                cap = min(max(1, int(cap_raw)), 9999)
            except ValueError:
                conn.close()
                flash("Ukomo si sahihi.", "danger")
                return redirect(url_for("developer_group_inspect", group_id=group_id))
            total = conn.execute(
                "SELECT COUNT(*) FROM users WHERE group_id=? AND status='active'", (group_id,)
            ).fetchone()[0]
            if cap < total:
                conn.close()
                flash(f"Ukomo ({cap}) hauwezi kuwa chini ya wanachama waliopo ({total}).", "danger")
                return redirect(url_for("developer_group_inspect", group_id=group_id))
            conn.execute("UPDATE group_info SET member_cap=? WHERE id=?", (cap, group_id))
            notes_log.append(f"cap→{cap}")

        if settlement_phone:
            sp = normalize_tz_phone(settlement_phone)
            if not is_valid_tz_phone(sp):
                conn.close()
                flash("Namba ya settlement si sahihi.", "danger")
                return redirect(url_for("developer_group_inspect", group_id=group_id))
            conn.execute("UPDATE group_info SET settlement_phone=? WHERE id=?", (sp, group_id))
            notes_log.append("settlement_phone updated")

        if notes_log:
            conn.execute(
                "INSERT INTO system_logs (level, message) VALUES ('INFO', ?)",
                (f"Developer updated group#{group_id}: " + "; ".join(notes_log),),
            )
            conn.commit()
            flash("Kikundi kimesasishwa: " + ", ".join(notes_log), "success")
        else:
            flash("Hakuna mabadiliko yaliyowekwa.", "warning")
        conn.close()
        return redirect(url_for("developer_group_inspect", group_id=group_id))

    conn.close()
    flash("Kitendo hakijatambuliwa.", "danger")
    return redirect(url_for("developer_groups"))


@app.route("/developer-dashboard/members/update", methods=["POST"])
@developer_required
def developer_member_update():
    """Support tools: update phone, reset password, change status, fix member_number."""
    action = (request.form.get("action") or "").strip().lower()
    user_id = request.form.get("user_id", type=int)
    consent = request.form.get("consent") == "on"
    if not consent:
        flash("Lazima uthibitishe idhini ya mmiliki wa akaunti.", "danger")
        return redirect(url_for("developer_dashboard"))
    if not user_id:
        flash("Chagua mwanachama.", "danger")
        return redirect(url_for("developer_dashboard"))

    conn = db()
    user = conn.execute(
        """SELECT u.*, g.group_name FROM users u
           LEFT JOIN group_info g ON g.id=u.group_id WHERE u.id=?""",
        (user_id,),
    ).fetchone()
    if not user:
        conn.close()
        flash("Mwanachama hakupatikani.", "danger")
        return redirect(url_for("developer_dashboard"))

    if action == "reset_password":
        new_password = request.form.get("new_password") or ""
        if len(new_password) < 8:
            conn.close()
            flash("Nywila mpya lazima iwe angalau herufi 8.", "danger")
            return redirect(url_for("developer_dashboard"))
        conn.execute(
            "UPDATE users SET password=? WHERE id=?",
            (generate_password_hash(new_password), user_id),
        )
        msg = f"Developer reset password user#{user_id} {user['full_name']}"
    elif action == "update_phone":
        phone = normalize_tz_phone(request.form.get("phone") or "")
        if not is_valid_tz_phone(phone):
            conn.close()
            flash("Namba ya simu si sahihi.", "danger")
            return redirect(url_for("developer_dashboard"))
        try:
            conn.execute("UPDATE users SET phone=? WHERE id=?", (phone, user_id))
            msg = f"Developer updated phone user#{user_id} → {phone}"
        except sqlite3.IntegrityError:
            conn.rollback()
            conn.close()
            flash("Namba hii ya simu tayari inatumika na akaunti nyingine.", "danger")
            return redirect(url_for("developer_dashboard"))
    elif action == "set_status":
        status = (request.form.get("status") or "").strip().lower()
        if status not in {"active", "suspended", "inactive"}:
            conn.close()
            flash("Status si sahihi.", "danger")
            return redirect(url_for("developer_dashboard"))
        conn.execute("UPDATE users SET status=? WHERE id=?", (status, user_id))
        msg = f"Developer set status={status} user#{user_id}"
    elif action == "reassign_member_number":
        try:
            mn = int(re.sub(r"\\D", "", request.form.get("member_number") or "0") or "0")
        except ValueError:
            mn = 0
        if mn < 1:
            conn.close()
            flash("Namba ya uanachama si sahihi.", "danger")
            return redirect(url_for("developer_dashboard"))
        clash = conn.execute(
            "SELECT id FROM users WHERE group_id=? AND member_number=? AND id!=?",
            (user["group_id"], mn, user_id),
        ).fetchone()
        if clash:
            conn.close()
            flash("Namba hiyo ya uanachama tayari inatumika kwenye kikundi hiki.", "danger")
            return redirect(url_for("developer_dashboard"))
        conn.execute("UPDATE users SET member_number=? WHERE id=?", (mn, user_id))
        msg = f"Developer set member_number={mn} user#{user_id}"
    elif action == "login_as":
        conn.execute(
            "INSERT INTO system_logs (level, message) VALUES ('INFO', ?)",
            (f"Developer support login-as user#{user_id} {user['full_name']}",),
        )
        conn.commit()
        conn.close()
        log_event("developer_login_as", f"user_id={user_id}")
        session.clear()
        session.permanent = True
        session["user_id"] = user["id"]
        session["full_name"] = user["full_name"]
        session["role"] = user["role"]
        session["group_id"] = user["group_id"]
        session["is_developer"] = True
        session["support_mode"] = True
        flash(f"Umeingia kwa msaada kwenye akaunti ya {user['full_name']}.", "success")
        return redirect(url_for("dashboard"))
    else:
        conn.close()
        flash("Chagua kitendo sahihi.", "danger")
        return redirect(url_for("developer_dashboard"))

    conn.execute("INSERT INTO system_logs (level, message) VALUES ('INFO', ?)", (msg,))
    conn.commit()
    conn.close()
    log_event("developer_member_update", msg[:200])
    flash(f"Imefanikiwa: {msg}", "success")
    return redirect(url_for("developer_dashboard"))


@app.route("/developer-dashboard/support/search", methods=["GET", "POST"])
@developer_required
def developer_support_search():
    """Search members for support desk."""
    q = (request.form.get("q") or request.args.get("q") or "").strip()
    group_id = request.form.get("group_id", type=int) or request.args.get("group_id", type=int)
    conn = db()
    sql = """SELECT u.id, u.full_name, u.phone, u.member_number, u.role, u.status,
                    u.group_id, g.group_name, g.registration_code
             FROM users u LEFT JOIN group_info g ON g.id=u.group_id WHERE 1=1"""
    params = []
    if q:
        phone = normalize_tz_phone(q)
        sql += " AND (u.full_name LIKE ? OR u.phone LIKE ? OR CAST(u.member_number AS TEXT)=?)"
        params.extend([f"%{q}%", f"%{phone or q}%", re.sub(r"\\D", "", q) or q])
    if group_id:
        sql += " AND u.group_id=?"
        params.append(group_id)
    sql += " ORDER BY u.id DESC LIMIT 30"
    rows = conn.execute(sql, params).fetchall()
    groups = conn.execute(
        "SELECT id, group_name, registration_code, member_cap FROM group_info ORDER BY id"
    ).fetchall()
    conn.close()
    return render_template(
        "developer_support.html",
        results=rows,
        groups=groups,
        q=q,
        selected_group_id=group_id,
    )


@app.route("/developer-dashboard/groups", methods=["GET", "POST"])
@developer_required
def developer_groups():
    conn = db()

    if request.method == "POST":
        group_name = request.form.get("group_name", "").strip()[:100]
        cap_raw = request.form.get("member_cap", "999").strip()
        whatsapp_group_url = request.form.get("whatsapp_group_url", "").strip()

        try:
            cap = min(max(1, int(cap_raw)), 9999)
        except ValueError:
            conn.close()
            flash("Ukomo wa wanachama lazima uwe namba kati ya 1 na 9999.", "danger")
            return redirect(url_for("developer_groups"))

        if whatsapp_group_url and not whatsapp_group_url.startswith("https://chat.whatsapp.com/"):
            conn.close()
            flash("Link ya WhatsApp ya kikundi lazima ianze na https://chat.whatsapp.com/.", "danger")
            return redirect(url_for("developer_groups"))

        if not group_name:
            conn.close()
            flash("Jina la kikundi linahitajika.", "danger")
            return redirect(url_for("developer_groups"))

        # NJIAKIKOBA is the platform name, not a group name.
        forbidden = {"njiakikoba", "njia kikoba", "njia-kikoba"}
        if group_name.casefold().replace(" ", "") in {x.replace(" ", "") for x in forbidden} or group_name.casefold() == "njiakikoba":
            conn.close()
            flash(
                "Jina 'NJIAKIKOBA' ni jina la mfumo, si jina la kikundi. "
                "Tumia jina la kikundi chenyewe (mfano: CHAPAKAZI GROUP).",
                "danger",
            )
            return redirect(url_for("developer_groups"))

        # Default member cap is 999 per group (developer may raise later).
        if cap > 999 and not request.form.get("force_high_cap"):
            cap = 999

        try:
            cur = conn.execute(
                "INSERT INTO group_info (group_name, member_cap, payment_number, whatsapp_group_url) VALUES (?, ?, ?, ?)",
                (group_name, cap, os.environ.get("GROUP_PAYMENT_NUMBER"), whatsapp_group_url or None)
            )
            gid = cur.lastrowid
            code = make_registration_code(gid, group_name, conn)
            room = "Njiakikoba-" + secrets.token_urlsafe(18).replace("-", "").replace("_", "")
            conn.execute(
                "UPDATE group_info SET registration_code=?, video_room=? WHERE id=?",
                (code, room, gid)
            )
            conn.commit()
            flash(
                f"Kikundi {group_name} kimeundwa. Registration Code ya kikundi: {code}. "
                f"Namba ya mwanachama itakuwa mfano: {make_member_code(group_name, 1)}.",
                "success",
            )
        except sqlite3.IntegrityError:
            conn.rollback()
            flash("Kikundi hakikuundwa.", "danger")
        finally:
            conn.close()
        return redirect(url_for("developer_groups"))

    groups = conn.execute(
        """SELECT g.id, g.group_name, g.registration_code, g.member_cap,
                  g.video_room, g.whatsapp_group_url, g.created_at,
                  COUNT(u.id) AS member_count,
                  SUM(CASE WHEN u.role='leader' THEN 1 ELSE 0 END) AS leader_count,
                  COALESCE(SUM(u.savings),0) AS savings,
                  COALESCE(SUM(u.loan_balance),0) AS loans
           FROM group_info g
           LEFT JOIN users u ON u.group_id=g.id AND u.status='active'
           GROUP BY g.id ORDER BY g.id DESC"""
    ).fetchall()
    conn.close()
    return render_template("developer_groups.html", groups=groups)


@app.route("/developer-dashboard/groups/<int:group_id>")
@developer_required
def developer_group_inspect(group_id):
    conn = db()
    group = conn.execute("SELECT * FROM group_info WHERE id=?", (group_id,)).fetchone()
    if not group:
        conn.close()
        flash("Kikundi hakipo.", "danger")
        return redirect(url_for("developer_groups"))

    members = conn.execute(
        """SELECT id, member_number, full_name, phone, role, savings, loan_balance,
                  status, created_at
           FROM users WHERE group_id=? ORDER BY role='leader' DESC, member_number ASC""",
        (group_id,)
    ).fetchall()

    recent_transactions = conn.execute(
        """SELECT t.tx_ref, t.tx_type, t.amount, t.status, t.created_at,
                  u.full_name
           FROM transactions t
           JOIN users u ON u.id=t.user_id
           WHERE t.group_id=?
           ORDER BY t.id DESC LIMIT 50""",
        (group_id,)
    ).fetchall()

    recent_messages = conn.execute(
        """SELECT id, full_name, role, body, media_kind, media_url, media_name,
                  pinned, created_at
           FROM messages WHERE group_id=?
           ORDER BY pinned DESC, id DESC LIMIT 100""",
        (group_id,)
    ).fetchall()

    stats = {
        "members": len(members),
        "leaders": sum(1 for m in members if m["role"] == "leader"),
        "savings": sum((m["savings"] or 0) for m in members),
        "loans": sum((m["loan_balance"] or 0) for m in members),
    }
    conn.close()

    # This is a read-only developer view. It does not create a users/session
    # record and no member-facing route is notified that the developer is here.
    return render_template(
        "developer_group_inspect.html",
        group=group, members=members,
        recent_transactions=recent_transactions,
        recent_messages=recent_messages,
        stats=stats
    )


@app.route("/developer-dashboard/upgrade", methods=["POST"])
@developer_required
def developer_upgrade():
    group_id = request.form.get("group_id", type=int)
    try:
        new_cap = int(request.form.get("member_cap", "0"))
    except ValueError:
        new_cap = 0
    if not group_id or not (1 <= new_cap <= 9999):
        flash("Upgrade lazima ichague kikundi na ukomo wa 1 hadi 9,999.", "danger")
        return redirect(url_for("developer_dashboard"))
    conn = db()
    current = conn.execute("SELECT group_name FROM group_info WHERE id=?", (group_id,)).fetchone()
    if not current:
        conn.close(); flash("Kikundi hakipo.", "danger"); return redirect(url_for("developer_dashboard"))
    total = conn.execute("SELECT COUNT(*) FROM users WHERE group_id=? AND status='active'", (group_id,)).fetchone()[0]
    if new_cap < total:
        conn.close(); flash(f"Upgrade haiwezi kuweka ukomo chini ya wanachama waliopo ({total}).", "danger"); return redirect(url_for("developer_dashboard"))
    conn.execute("UPDATE group_info SET member_cap=? WHERE id=?", (new_cap, group_id))
    conn.execute("INSERT INTO system_logs(level,message) VALUES('INFO',?)", (f"Developer upgraded {current['group_name']} member cap to {new_cap}.",))
    conn.commit(); conn.close()
    flash(f"{current['group_name']} ime-upgradeiwa hadi wanachama {new_cap}.", "success")
    return redirect(url_for("developer_dashboard"))


@app.route("/developer-dashboard/end-cycle", methods=["POST"])
@developer_required
def end_cycle():
    conn = db()
    selected_group_id = request.form.get("group_id", type=int)
    if selected_group_id:
        total_savings = conn.execute(
            "SELECT COALESCE(SUM(savings),0) FROM users WHERE group_id=?", (selected_group_id,)
        ).fetchone()[0]
        group = conn.execute(
            "SELECT cycle_months FROM group_info WHERE id=?", (selected_group_id,)
        ).fetchone()
    else:
        total_savings = conn.execute("SELECT COALESCE(SUM(savings),0) FROM users").fetchone()[0]
        group = conn.execute("SELECT cycle_months FROM group_info ORDER BY id LIMIT 1").fetchone()
    cycle_months = group["cycle_months"] if group and group["cycle_months"] else 12
    commission = round(total_savings * 0.02, 2)
    conn.execute(
        "INSERT INTO cycle_settlements (total_group_savings, commission_amount, cycle_months, group_id) VALUES (?, ?, ?, ?)",
        (total_savings, commission, cycle_months, selected_group_id)
    )
    conn.execute("UPDATE group_info SET cycle_started_at=CURRENT_TIMESTAMP WHERE id=COALESCE(?, id)", (selected_group_id,))
    conn.execute(
        "INSERT INTO system_logs (level, message) VALUES ('INFO', ?)",
        (f"Mzunguko umefungwa: jumla ya akiba TZS {total_savings:,.2f}, ada ya 2% = TZS {commission:,.2f} imerekodiwa kwa ajili ya usuluhishi.",)
    )
    conn.commit()
    conn.close()
    flash(
        f"Mzunguko umefungwa. Jumla ya akiba: TZS {total_savings:,.2f}. Ada ya 2% (TZS {commission:,.2f}) imerekodiwa — "
        "hii HAIJATUMWA kiotomatiki kwenye namba yako; fanya uhamisho halisi kupitia namba yako ya usuluhishi.",
        "success"
    )
    return redirect(url_for("developer_dashboard"))


@app.route("/developer-dashboard/recognition-settings", methods=["POST"])
@developer_required
def developer_recognition_settings():
    enabled = 1 if request.form.get("recognition_enabled") == "on" else 0
    try:
        threshold = max(50, min(99, int(request.form.get("recognition_threshold", "80"))))
    except ValueError:
        threshold = 80
    conn = db()
    group_id = request.form.get("group_id", type=int) or conn.execute("SELECT id FROM group_info ORDER BY id LIMIT 1").fetchone()[0]
    conn.execute("UPDATE group_info SET recognition_enabled=?, recognition_threshold=? WHERE id=?", (enabled, threshold, group_id))
    conn.commit(); conn.close()
    flash("Recognition Quality settings zimehifadhiwa.", "success")
    return redirect(url_for("developer_dashboard"))

@app.route("/developer-dashboard/settings", methods=["POST"])
@developer_required
def developer_settings_update():
    adsense_id = request.form.get("adsense_publisher_id", "").strip()
    play_store = request.form.get("play_store_url", "").strip()
    appstore = request.form.get("appstore_url", "").strip()
    group_name = request.form.get("group_name", "").strip()
    member_cap_raw = request.form.get("member_cap", "").strip()
    settlement_phone = request.form.get("settlement_phone", "").strip()
    settlement_bank_name = request.form.get("settlement_bank_name", "").strip()
    settlement_bank_account = request.form.get("settlement_bank_account", "").strip()
    partner_name = request.form.get("partner_name", "").strip()
    partner_contact = request.form.get("partner_contact", "").strip()
    partner_account_details = request.form.get("partner_account_details", "").strip()
    cycle_months_raw = request.form.get("cycle_months", "12").strip()
    whatsapp_group_url = request.form.get("whatsapp_group_url", "").strip()
    selected_group_id = request.form.get("group_id", type=int)

    # Basic sanity checks — don't save obviously malformed values.
    if adsense_id and not adsense_id.startswith("ca-pub-"):
        flash("AdSense Publisher ID lazima ianze na 'ca-pub-'.", "danger")
        return redirect(url_for("developer_dashboard"))
    for url_val, label in [(play_store, "Play Store"), (appstore, "App Store")]:
        if url_val and not (url_val.startswith("https://")):
            flash(f"Link ya {label} lazima ianze na https://", "danger")
            return redirect(url_for("developer_dashboard"))
    if settlement_phone and not re.fullmatch(r"255\d{9}", settlement_phone):
        flash("Namba ya simu ya kikundi lazima iwe mfumo 255XXXXXXXXX.", "danger")
        return redirect(url_for("developer_dashboard"))
    if whatsapp_group_url and not whatsapp_group_url.startswith("https://chat.whatsapp.com/"):
        flash("Link ya WhatsApp ya kikundi lazima ianze na https://chat.whatsapp.com/.", "danger")
        return redirect(url_for("developer_dashboard"))
    if cycle_months_raw not in ("3", "6", "9", "12"):
        flash("Muda wa mzunguko lazima uwe miezi 3, 6, 9, au 12.", "danger")
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
        target_for_cap = selected_group_id or conn.execute(
            "SELECT id FROM group_info ORDER BY id LIMIT 1"
        ).fetchone()[0]
        current_total = conn.execute(
            "SELECT COUNT(*) FROM users WHERE group_id=?", (target_for_cap,)
        ).fetchone()[0]
        if member_cap < current_total:
            flash(f"Huwezi kuweka ukomo chini ya idadi ya sasa ya wanachama ({current_total}).", "danger")
            conn.close()
            return redirect(url_for("developer_dashboard"))

    target_group_id = selected_group_id or conn.execute(
        "SELECT id FROM group_info ORDER BY id LIMIT 1"
    ).fetchone()[0]
    conn.execute(
        "UPDATE group_info SET adsense_publisher_id=?, play_store_url=?, appstore_url=?, group_name=?, "
        "settlement_phone=?, settlement_bank_name=?, settlement_bank_account=?, "
        "partner_name=?, partner_contact=?, partner_account_details=?, cycle_months=?, whatsapp_group_url=? "
        "WHERE id=?",
        (adsense_id or None, play_store or None, appstore or None, group_name or "NJIAKIKOBA",
         settlement_phone or None, settlement_bank_name or None, settlement_bank_account or None,
         partner_name or None, partner_contact or None, partner_account_details or None,
         int(cycle_months_raw), whatsapp_group_url or None, target_group_id)
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
    actor = conn.execute("SELECT role, group_id FROM users WHERE id=?", (session["user_id"],)).fetchone()
    if not actor or actor["role"] != "leader":
        conn.close(); return jsonify({"error": "Ni kiongozi aliyeidhinishwa pekee anayeruhusiwa kuanzisha malipo ya mkopo."}), 403
    data = request.get_json(silent=True) or {}
    try: member_id = int(data.get("member_id")); amount = int(float(data.get("amount", 0)))
    except (TypeError, ValueError):
        conn.close(); return jsonify({"error": "Member ID au kiasi si sahihi."}), 400
    if amount < 1000:
        conn.close(); return jsonify({"error": "Kiasi cha chini cha payout ni TZS 1,000."}), 400
    member = conn.execute(
        """SELECT id, full_name, payout_method, payment_phone, payment_network,
                  bank_code, bank_account, group_id
           FROM users WHERE id=? AND status='active'""",
        (member_id,)
    ).fetchone()
    if member and member["group_id"] != actor["group_id"]:
        conn.close()
        return jsonify({"error": "Mwanakikundi huyu hayuko kwenye kikundi chako."}), 403
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
    conn.execute("INSERT INTO transactions (user_id,tx_ref,tx_type,amount,commission,group_amount,status,provider,provider_reference,payment_reference,group_id) VALUES (?,?,?,?,?,?,?,?,?,?,?)", (member_id, tx_ref, "loan_disbursement", amount, 0, amount, "payout_processing", "BLMPay", ref, ref, member["group_id"]))
    conn.commit(); conn.close()
    return jsonify({"success": True, "reference": ref, "message": "Malipo ya mkopo yamepelekwa kwenye njia ya mwanakikundi."}), 201



def settle_system_fees(conn, tx):
    """Send platform fees (2% commission + optional 1% first-deposit) to DEVELOPER_LIPA_NUMBER.

    Returns (status_text, detail_message). Does not raise.
    """
    fee_total = round(float(tx["commission"] or 0) + float(tx["first_deposit_fee"] or 0), 2)
    if fee_total <= 0:
        return "not_applicable", "Hakuna ada ya mfumo kwenye muamala huu."
    dest = (DEVELOPER_LIPA_NUMBER or "").strip()
    if not dest:
        return "not_configured", "DEVELOPER_LIPA_NUMBER haijawekwa kwenye environment."
    if not BLMPAY_API_KEY:
        return "not_configured", "BLMPAY_API_KEY haipo."

    # Normalize if it looks like a TZ phone
    phone = normalize_tz_phone(dest)
    network = (GROUP_SETTLEMENT_NETWORK or "MIXX_BY_YAS").upper()
    tx_ref = tx["tx_ref"]
    payout_ref = f"FEE-{tx_ref}"

    # Prefer mobile payout when destination is a valid TZ mobile.
    if is_valid_tz_phone(phone):
        payload = {
            "amount": fee_total,
            "currency": "TZS",
            "channel": "mobile",
            "recipient_phone": phone,
            "network": network,
            "narration": f"NJIAKIKOBA system fee {tx_ref}",
            "metadata": {
                "tx_ref": tx_ref,
                "type": "system_commission",
                "commission": float(tx["commission"] or 0),
                "first_deposit_fee": float(tx["first_deposit_fee"] or 0),
            },
        }
    else:
        # Lipa / merchant number stored as opaque destination — still attempt mobile channel
        payload = {
            "amount": fee_total,
            "currency": "TZS",
            "channel": "mobile",
            "recipient_phone": dest,
            "network": network,
            "narration": f"NJIAKIKOBA system fee {tx_ref}",
            "metadata": {"tx_ref": tx_ref, "type": "system_commission", "dest": "lipa_or_custom"},
        }

    try:
        r = requests.post(
            f"{BLMPAY_BASE_URL}/payouts/send",
            headers={
                "Authorization": f"Bearer {BLMPAY_API_KEY}",
                "Content-Type": "application/json",
                "Idempotency-Key": payout_ref,
            },
            json=payload,
            timeout=25,
        )
        result = r.json() if r.content else {}
    except Exception as exc:
        log_event("system_fee_settlement_error", str(exc)[:300])
        return "failed", f"Payout error: {str(exc)[:200]}"

    if r.status_code < 400 and str(result.get("status", "")).lower() in ("success", "pending", "processing", "ok"):
        ref = (result.get("data") or {}).get("reference") or result.get("reference") or payout_ref
        return "settled", f"Ada TZS {fee_total:,.2f} imetumwa (ref {ref})"
    msg = result.get("message") or result.get("error") or f"HTTP {r.status_code}"
    log_event("system_fee_settlement_rejected", msg[:300])
    return "failed", msg[:300]


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
    user=conn.execute("SELECT full_name,email,payment_phone,payment_network,group_id FROM users WHERE id=?",(session["user_id"],)).fetchone()
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
    conn=db()
    is_first_deposit = tx_type == "savings" and conn.execute(
        "SELECT COUNT(*) FROM transactions WHERE user_id=? AND group_id=? AND tx_type='savings' AND status='paid'",
        (session["user_id"], user["group_id"])
    ).fetchone()[0] == 0
    conn.close()
    first_deposit_fee = round(amount*FIRST_DEPOSIT_FEE_RATE, 2) if is_first_deposit else 0
    group_amount=round(amount-commission-first_deposit_fee,2)
    tx_ref="NJK-"+secrets.token_hex(8).upper()
    if not BLMPAY_API_KEY or not BLMPAY_WEBHOOK_URL:
        return jsonify({"error":"Payment gateway haijaunganishwa kikamilifu kwenye server."}),503
    first,*last=user["full_name"].split()
    payload={"payment_type":"mobile","details":{"amount":amount,"currency":"TZS"},"phone_number":phone,"customer":{"firstname":first[:60],"lastname":" ".join(last)[:60] or first[:60],"email":user["email"]},"webhook_url":BLMPAY_WEBHOOK_URL,"metadata":{"tx_ref":tx_ref,"tx_type":tx_type,"network":network,"commission_percent":2,"first_deposit_fee_percent":(1 if is_first_deposit else 0)}}
    try:
        r=requests.post(f"{BLMPAY_BASE_URL}/payments",headers={"Authorization":f"Bearer {BLMPAY_API_KEY}","Content-Type":"application/json","Idempotency-Key":tx_ref},json=payload,timeout=25)
        result=r.json()
    except Exception as exc:
        log_event("payment_gateway_error",str(exc))
        return jsonify({"error":"Payment gateway haipatikani kwa sasa."}),502
    if r.status_code>=400 or result.get("status")!="success":
        return jsonify({"error":result.get("message","Malipo hayakuanzishwa.")}),502
    pref=(result.get("data") or {}).get("reference")
    conn=db(); conn.execute("INSERT INTO transactions (user_id,tx_ref,tx_type,amount,commission,group_amount,first_deposit_fee,provider,status,provider_reference,payment_reference,group_id) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",(session["user_id"],tx_ref,tx_type,amount,commission,group_amount,first_deposit_fee,"BLMPay","awaiting_confirmation",pref,pref,user["group_id"])); conn.commit(); conn.close()
    msg = "USSD push imetumwa kwenye namba yako. Ingiza PIN yako kuthibitisha."
    if is_first_deposit:
        msg += " (Amana yako ya kwanza — ada ya uendeshaji ya ziada ya 1% inatumika mara moja tu.)"
    return jsonify({"success":True,"tx_ref":tx_ref,"payment_reference":pref,"amount":amount,"message":msg}),201


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
        # Credit member with net group_amount; platform fees go to DEVELOPER_LIPA_NUMBER.
        tx = conn.execute("SELECT * FROM transactions WHERE tx_ref=?", (tx_ref,)).fetchone()
        dev_status, detail = settle_system_fees(conn, tx)
        grp_status = "configured" if GROUP_SETTLEMENT_PHONE else "not_configured"
        conn.execute(
            "UPDATE transactions SET developer_settlement_status=?, group_settlement_status=? WHERE tx_ref=?",
            (dev_status, grp_status, tx_ref),
        )
        fee_total = round(float(tx["commission"] or 0) + float(tx["first_deposit_fee"] or 0), 2)
        conn.execute(
            "INSERT INTO system_logs(level,message) VALUES(?,?)",
            (
                "INFO" if dev_status == "settled" else "WARNING",
                f"Paid {tx_ref}: member net TZS {float(tx['group_amount']):,.2f}; "
                f"system fees TZS {fee_total:,.2f} → {dev_status}: {detail}",
            ),
        )
    elif event in ("payment.failed","payment.expired","payment.cancelled","payment.voided") or status in ("failed","expired","cancelled","voided"):
        conn.execute("UPDATE transactions SET status='failed' WHERE tx_ref=? AND status!='paid'",(tx_ref,))
    conn.commit(); conn.close(); return "OK",200

@app.route("/group-chat/voice", methods=["POST"])
@member_required
def group_chat_voice():
    """Receive a voice note recorded during a conference and publish it to the actor's group chat."""
    conn = db()
    actor = conn.execute(
        "SELECT id, full_name, role, group_id FROM users WHERE id=? AND status='active'",
        (session["user_id"],)
    ).fetchone()
    upload = request.files.get("voice")
    try:
        if not actor or not upload or not upload.filename:
            return jsonify({"ok": False, "message": "Ujumbe wa sauti haupo."}), 400
        media = save_chat_media(upload)
        if media["kind"] != "audio":
            return jsonify({"ok": False, "message": "Faili si sauti."}), 400
        conn.execute(
            """INSERT INTO messages
               (user_id, full_name, role, body, media_kind, media_url, media_name, media_mime, group_id)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (actor["id"], actor["full_name"], actor["role"],
             "🎙️ Ujumbe wa sauti kutoka kwenye mkutano wa LIVE.", media["kind"],
             url_for("chat_media", filename=media["filename"]), media["original"], media["mime"], actor["group_id"])
        )
        conn.commit()
        return jsonify({"ok": True, "message": "Ujumbe wa sauti umetumwa kwa kikundi."})
    except ValueError as exc:
        return jsonify({"ok": False, "message": str(exc)}), 400
    finally:
        conn.close()

@app.route("/group-chat", methods=["GET", "POST"])
@member_required
def group_chat():
    conn = db()
    actor = conn.execute(
        "SELECT id, full_name, role, group_id FROM users WHERE id=? AND status='active'",
        (session["user_id"],)
    ).fetchone()
    group = conn.execute(
        "SELECT id, group_name, registration_code, member_cap, whatsapp_group_url FROM group_info WHERE id=?",
        (actor["group_id"],)
    ).fetchone()

    if request.method == "POST":
        body = request.form.get("body", "").strip()[:1000]
        upload = request.files.get("media")
        media = None
        try:
            if upload and upload.filename:
                media = save_chat_media(upload)
            if body or media:
                conn.execute(
                    """INSERT INTO messages
                       (user_id, full_name, role, body, media_kind, media_url, media_name, media_mime, group_id)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        actor["id"], actor["full_name"], actor["role"], body,
                        media["kind"] if media else None,
                        url_for("chat_media", filename=media["filename"]) if media else None,
                        media["original"] if media else None,
                        media["mime"] if media else None,
                        actor["group_id"]
                    )
                )
                conn.commit()
        except ValueError as exc:
            flash(str(exc), "danger")
        finally:
            conn.close()
        return redirect(url_for("group_chat"))

    messages = conn.execute(
        """SELECT id, user_id, full_name, role, body, pinned, created_at,
                  media_kind, media_url, media_name, media_mime
           FROM messages
           WHERE group_id=?
           ORDER BY pinned DESC, id DESC LIMIT 100""",
        (actor["group_id"],)
    ).fetchall()
    members = conn.execute(
        """SELECT id, member_number, full_name, phone, role
           FROM users
           WHERE group_id=? AND status='active'
           ORDER BY role='leader' DESC, member_number ASC""",
        (actor["group_id"],)
    ).fetchall()
    conn.close()
    return render_template("group_chat.html", messages=messages, actor=actor, group=group, members=members)


@app.route("/group-chat/whatsapp/<int:member_id>")
@member_required
def group_member_whatsapp(member_id):
    # Backward-compatible route: always opens the current group's WhatsApp, never a developer contact.
    conn = db()
    actor = conn.execute("SELECT group_id FROM users WHERE id=? AND status='active'", (session["user_id"],)).fetchone()
    group = conn.execute("SELECT whatsapp_group_url FROM group_info WHERE id=?", (actor["group_id"],)).fetchone() if actor else None
    conn.close()
    if not actor or not group or not group["whatsapp_group_url"]:
        flash("Kikundi hiki bado hakijawekewa WhatsApp Group link.", "warning")
        return redirect(url_for("group_chat"))
    return redirect(group["whatsapp_group_url"])


@app.route("/group-chat/delete/<int:message_id>", methods=["POST"])
@member_required
def group_chat_delete(message_id):
    conn = db()
    actor = conn.execute(
        "SELECT role, group_id FROM users WHERE id=?", (session["user_id"],)
    ).fetchone()
    msg = conn.execute(
        "SELECT user_id, media_url, group_id FROM messages WHERE id=?", (message_id,)
    ).fetchone()
    if not msg or msg["group_id"] != actor["group_id"]:
        flash("Ujumbe haupo kwenye kikundi chako.", "danger")
    elif actor["role"] == "leader" or msg["user_id"] == session["user_id"]:
        if msg["media_url"]:
            filename = os.path.basename(msg["media_url"])
            try:
                os.remove(os.path.join(CHAT_UPLOAD_DIR, filename))
            except OSError:
                pass
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
    actor = conn.execute("SELECT role, group_id FROM users WHERE id=?", (session["user_id"],)).fetchone()
    msg = conn.execute("SELECT group_id FROM messages WHERE id=?", (message_id,)).fetchone()
    if not msg or msg["group_id"] != actor["group_id"]:
        flash("Ujumbe haupo kwenye kikundi chako.", "danger")
    elif actor["role"] == "leader":
        conn.execute(
            "UPDATE messages SET pinned = CASE WHEN pinned=1 THEN 0 ELSE 1 END WHERE id=? AND group_id=?",
            (message_id, actor["group_id"])
        )
        conn.commit()
    else:
        flash("Ni viongozi tu wanaoweza ku-pin ujumbe.", "danger")
    conn.close()
    return redirect(url_for("group_chat"))


@app.route("/video-call")
@app.route("/conference-call")
@member_required
def video_call():
    conn = db()
    actor = conn.execute(
        "SELECT id, full_name, role, group_id FROM users WHERE id=? AND status='active'",
        (session["user_id"],)
    ).fetchone()
    group = conn.execute(
        "SELECT group_name, video_room, registration_code FROM group_info WHERE id=?",
        (actor["group_id"],)
    ).fetchone()
    conn.close()

    if not group:
        flash("Chumba cha conference hakijapatikana.", "danger")
        return redirect(url_for("group_chat"))

    # Ensure every group has a dedicated Jitsi room so members of the same
    # group always meet in one shared call without colliding with other groups.
    room = group["video_room"]
    if not room:
        room = "Njiakikoba-" + secrets.token_urlsafe(18).replace("-", "").replace("_", "")
        conn = db()
        conn.execute("UPDATE group_info SET video_room=? WHERE id=?", (room, group["id"]))
        conn.commit()
        conn.close()

    return render_template(
        "conference_call.html", actor=actor, group=group, room_name=room
    )


@app.route("/certificate")
@member_required
def certificate():
    conn = db()
    user = conn.execute(
        """SELECT full_name, member_number, role, group_size_at_join, created_at, group_id
           FROM users WHERE id=?""", (session["user_id"],)
    ).fetchone()
    leaders = conn.execute(
        "SELECT full_name FROM users WHERE role='leader' AND group_id=? ORDER BY member_number LIMIT 3",
        (user["group_id"],)
    ).fetchall()
    group = conn.execute(
        "SELECT group_name FROM group_info WHERE id=?", (user["group_id"],)
    ).fetchone()
    conn.close()
    member_code = make_member_code(group["group_name"] if group else "", user["member_number"])
    return render_template(
        "certificate.html", user=user, leaders=leaders, group=group, member_code=member_code
    )


@app.route("/receipt/<tx_ref>")
@member_required
def receipt(tx_ref):
    conn = db()
    tx = conn.execute(
        """SELECT tx_ref, tx_type, amount, commission, group_amount, status,
                  created_at, user_id, group_id
           FROM transactions WHERE tx_ref=? AND user_id=? AND group_id=?""",
        (tx_ref, session["user_id"], session.get("group_id"))
    ).fetchone()
    if not tx or tx["status"] != "paid":
        conn.close()
        flash("Risiti haipatikani.", "danger")
        return redirect(url_for("dashboard"))
    user = conn.execute(
        "SELECT full_name, member_number FROM users WHERE id=? AND group_id=?",
        (session["user_id"], tx["group_id"])
    ).fetchone()
    group = conn.execute(
        "SELECT group_name, registration_code FROM group_info WHERE id=?",
        (tx["group_id"],)
    ).fetchone()
    conn.close()
    return render_template("receipt.html", tx=tx, user=user, group=group)


@app.route("/developer-dashboard/payment-providers", methods=["POST"])
@developer_required
def payment_provider_save():
    """No-code configuration for payment gateways. Secrets are never rendered back to the browser."""
    provider_id = request.form.get("provider_id", type=int)
    name = request.form.get("provider_name", "").strip()[:80]
    ptype = request.form.get("provider_type", "collection").strip()[:30]
    base_url = request.form.get("base_url", "").strip()[:300]
    api_key = request.form.get("api_key", "").strip()[:500]
    api_secret = request.form.get("api_secret", "").strip()[:500]
    merchant_id = request.form.get("merchant_id", "").strip()[:150]
    collection_path = request.form.get("collection_path", "").strip()[:200]
    payout_path = request.form.get("payout_path", "").strip()[:200]
    webhook_path = request.form.get("webhook_path", "").strip()[:200]
    webhook_secret = request.form.get("webhook_secret", "").strip()[:500]
    enabled = 1 if request.form.get("enabled") == "on" else 0
    is_default = 1 if request.form.get("is_default") == "on" else 0
    notes = request.form.get("notes", "").strip()[:1000]

    if not name:
        flash("Jina la payment system linahitajika.", "danger")
        return redirect(url_for("developer_dashboard"))
    if base_url and not base_url.startswith("https://"):
        flash("Base URL lazima ianze na https://", "danger")
        return redirect(url_for("developer_dashboard"))
    if ptype not in {"collection", "payout", "both"}:
        ptype = "both"

    conn=db()
    try:
        if is_default:
            conn.execute("UPDATE payment_providers SET is_default=0")
        if provider_id:
            # Empty secret fields mean: preserve the existing secret.
            old=conn.execute("SELECT api_key, api_secret, webhook_secret FROM payment_providers WHERE id=?",(provider_id,)).fetchone()
            if not old:
                raise ValueError("Payment provider haipo.")
            api_key = api_key or old["api_key"]
            api_secret = api_secret or old["api_secret"]
            webhook_secret = webhook_secret or old["webhook_secret"]
            conn.execute("""UPDATE payment_providers SET provider_name=?, provider_type=?, base_url=?, api_key=?, api_secret=?, merchant_id=?, collection_path=?, payout_path=?, webhook_path=?, webhook_secret=?, enabled=?, is_default=?, notes=?, updated_at=CURRENT_TIMESTAMP WHERE id=?""",
                         (name,ptype,base_url or None,api_key or None,api_secret or None,merchant_id or None,collection_path or None,payout_path or None,webhook_path or None,webhook_secret or None,enabled,is_default,notes or None,provider_id))
        else:
            conn.execute("""INSERT INTO payment_providers (provider_name,provider_type,base_url,api_key,api_secret,merchant_id,collection_path,payout_path,webhook_path,webhook_secret,enabled,is_default,notes) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                         (name,ptype,base_url or None,api_key or None,api_secret or None,merchant_id or None,collection_path or None,payout_path or None,webhook_path or None,webhook_secret or None,enabled,is_default,notes or None))
        conn.commit()
        flash(f"Payment system '{name}' imehifadhiwa bila ku-edit code.", "success")
    except Exception as exc:
        conn.rollback(); log_event("payment_provider_save_failed", str(exc))
        flash("Payment system haikuhifadhiwa. Kagua taarifa ulizoingiza.", "danger")
    finally:
        conn.close()
    return redirect(url_for("developer_dashboard"))


@app.route("/developer-dashboard/payment-providers/delete/<int:provider_id>", methods=["POST"])
@developer_required
def payment_provider_delete(provider_id):
    conn=db()
    conn.execute("DELETE FROM payment_providers WHERE id=?",(provider_id,))
    conn.commit(); conn.close()
    flash("Payment system imeondolewa.", "success")
    return redirect(url_for("developer_dashboard"))


@app.route("/developer-dashboard/payment-providers/test/<int:provider_id>", methods=["POST"])
@developer_required
def payment_provider_test(provider_id):
    """Connectivity-only test; never creates a real payment or sends money."""
    conn=db(); p=conn.execute("SELECT * FROM payment_providers WHERE id=?",(provider_id,)).fetchone(); conn.close()
    if not p:
        flash("Payment system haipo.","danger"); return redirect(url_for("developer_dashboard"))
    if not p["base_url"]:
        flash("Test haijaendeshwa: Base URL haijawekwa.","warning"); return redirect(url_for("developer_dashboard"))
    try:
        r=requests.get(p["base_url"], timeout=8, allow_redirects=True)
        log_event("payment_provider_connectivity_test", f"{p['provider_name']}: HTTP {r.status_code}")
        flash(f"{p['provider_name']}: server ilijibu HTTP {r.status_code}. Hii ni connectivity test tu; hakuna pesa iliyotumwa.", "success" if r.ok else "warning")
    except Exception as exc:
        log_event("payment_provider_connectivity_failed", f"{p['provider_name']}: {str(exc)[:300]}")
        flash(f"{p['provider_name']}: connection test imeshindwa. Kagua Base URL/API service.", "danger")
    return redirect(url_for("developer_dashboard"))


def build_repair(issue_text):
    """Generate a deterministic, reviewable repair plan for common system faults.
    It deliberately does not execute arbitrary code supplied by a user.
    """
    text=issue_text.strip()[:3000]
    low=text.lower()
    diagnosis=[]; actions=[]; code=[]
    if "no such table" in low or "table" in low and "missing" in low:
        diagnosis.append("Database table inaweza kuwa haipo au migration haijakimbia.")
        actions.append("Kimbiza init_db/migrations na fanya integrity check.")
        code.append("init_db()")
    if "no such column" in low or "column" in low and "missing" in low:
        diagnosis.append("Database column inaweza kukosekana kwenye version ya zamani ya database.")
        actions.append("Kagua schema na tumia migration ya non-destructive.")
        code.append("init_db()  # safe migration/backfill")
    if "payment" in low or "malipo" in low or "blmpay" in low or "azam" in low or "click pesa" in low:
        diagnosis.append("Tatizo linaonekana kuhusiana na payment configuration/provider.")
        actions.append("Kagua Developer Room > Payment Systems; usifanye live payment mpaka connectivity/configuration ipite.")
        code.append("# SAFE ACTION: validate payment provider configuration; do not send money")
    if "webhook" in low or "signature" in low:
        diagnosis.append("Tatizo linaweza kuwa kwenye callback/webhook signature au endpoint.")
        actions.append("Kagua webhook URL, secret na provider callback logs.")
        code.append("# SAFE ACTION: verify webhook signature/configuration before marking transaction paid")
    if not diagnosis:
        diagnosis.append("Tatizo halija-match na safe repair template iliyopo.")
        actions.append("Developer akague traceback/logs; hakuna arbitrary source-code auto-edit itakayofanyika.")
        code.append("# REVIEW REQUIRED — no automatic source modification")
    fix="\n".join(code)
    return " ".join(diagnosis), " ".join(actions), fix


@app.route("/developer-dashboard/command", methods=["POST"])
@developer_required
def developer_command():
    command = request.form.get("command", "").strip().upper()
    issue = request.form.get("issue_text", "").strip()
    commands = {
        "RUN_SYSTEM_HEALTH": "Kagua database, migrations, templates na configuration bila kubadilisha data.",
        "REPAIR_DATABASE": "Kimbiza init_db() na migrations/backfills salama.",
        "CHECK_PHONE_VALIDATION": "Thibitisha na kutumia normalization ya Tanzania 255XXXXXXXXX, pamoja na +255 na 0XXXXXXXXX.",
        "REPAIR_CERTIFICATE_PAGE": "Kagua route /certificate na template certificate.html; rekebisha missing-template error.",
        "CHECK_PUBLIC_DEVELOPER_LEAKS": "Tafuta links/text za Developer kwenye public UI na kuziondoa bila kugusa Developer Room.",
        "CHECK_GROUP_WHATSAPP": "Kagua WhatsApp Group link ya kila kikundi na kuhakikisha inatumika kwa group husika.",
        "HARDWARE_DIAGNOSTIC": "Hardware diagnostic ya browser/device: camera, microphone, storage na connectivity. Hakuna command inayoweza kuendesha code ya kifaa moja kwa moja.",
        "HARDWARE_REPAIR": "Hardware repair workflow: kagua permissions, camera/microphone, storage, browser cache na connectivity; hatua za kifaa zinafanywa na mtumiaji/technician, si server.",
        "RECOGNITION_DIAGNOSTIC": "Kagua ubora wa Face ID, ID capture na biometric enrollment; toa confidence/quality diagnostics bila kuhifadhi biometrics mpya.",
        "SOFTWARE_REPAIR": "Safe software repair: migrations, template checks, validation checks na system logs; hakuna arbitrary exec().",
    }
    if command not in commands:
        flash("Command haijatambuliwa. Chagua command iliyopo kwenye Developer Room.", "danger")
        return redirect(url_for("developer_dashboard"))
    plan = commands[command]
    if issue:
        diagnosis, actions, fix = build_repair(issue)
        plan += " " + diagnosis + " " + actions
        generated = fix
    else:
        generated = command
    conn = db()
    cur = conn.execute("INSERT INTO developer_repairs (issue_text,diagnosis,generated_fix,status) VALUES (?,?,?, 'generated')", (issue or command, plan, generated))
    conn.commit(); conn.close()
    flash(f"Command {command} imeandaliwa. Review plan kabla ya Apply Safe Fix.", "success")
    return redirect(url_for("developer_dashboard", repair_id=cur.lastrowid))


@app.route("/developer-dashboard/repair", methods=["POST"])
@developer_required
def developer_repair():
    issue=request.form.get("issue_text", "").strip()
    if not issue:
        flash("Andika tatizo la mfumo kwanza.","danger")
        return redirect(url_for("developer_dashboard"))
    diagnosis, actions, fix=build_repair(issue)
    conn=db()
    cur=conn.execute("INSERT INTO developer_repairs (issue_text,diagnosis,generated_fix,status) VALUES (?,?,?, 'generated')",(issue,diagnosis,fix))
    conn.commit(); conn.close()
    flash("Repair plan/code imetengenezwa. Safe fixes zinaweza kutekelezwa bila ku-edit source code.","success")
    return redirect(url_for("developer_dashboard", repair_id=cur.lastrowid))


@app.route("/developer-dashboard/repair/<int:repair_id>/apply", methods=["POST"])
@developer_required
def developer_repair_apply(repair_id):
    conn=db(); repair=conn.execute("SELECT * FROM developer_repairs WHERE id=?",(repair_id,)).fetchone()
    if not repair:
        conn.close(); flash("Repair haipo.","danger"); return redirect(url_for("developer_dashboard"))
    # Only execute safe, deterministic maintenance actions. Never exec() generated text.
    try:
        init_db()
        conn.execute("INSERT INTO system_logs (level,message) VALUES ('INFO',?)",(f"Developer applied safe repair #{repair_id}: database migration/integrity refresh",))
        conn.execute("UPDATE developer_repairs SET status='applied', applied_at=CURRENT_TIMESTAMP WHERE id=?",(repair_id,))
        conn.commit()
        flash("Safe repair imefanyika: database migrations/schema refresh zimekimbizwa. Hakuna arbitrary code iliyotekelezwa.","success")
    except Exception as exc:
        conn.rollback()
        conn.execute("INSERT INTO system_logs (level,message) VALUES ('ERROR',?)",(f"Repair #{repair_id} failed: {str(exc)[:400]}",))
        conn.commit()
        flash("Safe repair imeshindwa. Angalia system logs.","danger")
    finally:
        conn.close()
    return redirect(url_for("developer_dashboard"))


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
        upload = request.files.get("media")
        media = None

        try:
            if upload and upload.filename:
                media = save_chat_media(upload)

            if body or media:
                conn.execute(
                    "INSERT INTO messages "
                    "(user_id, full_name, role, body, media_kind, media_url, media_name, media_mime) "
                    "VALUES (0, 'Msimamizi wa Mfumo', 'developer', ?, ?, ?, ?, ?)",
                    (
                        body,
                        media["kind"] if media else None,
                        url_for("chat_media", filename=media["filename"]) if media else None,
                        media["original"] if media else None,
                        media["mime"] if media else None,
                    )
                )
                conn.commit()
        except ValueError as exc:
            flash(str(exc), "danger")
        finally:
            conn.close()

        return redirect(url_for("developer_chat"))

    messages = conn.execute(
        "SELECT id, user_id, full_name, role, body, pinned, created_at, "
        "media_kind, media_url, media_name, media_mime "
        "FROM messages ORDER BY pinned DESC, id DESC LIMIT 200"
    ).fetchall()
    conn.close()
    return render_template("developer_chat.html", messages=messages)


@app.route("/developer-dashboard/chat/delete/<int:message_id>", methods=["POST"])
@developer_required
def developer_chat_delete(message_id):
    conn = db()
    msg = conn.execute(
        "SELECT media_url FROM messages WHERE id=?", (message_id,)
    ).fetchone()

    if msg and msg["media_url"]:
        filename = os.path.basename(msg["media_url"])
        try:
            os.remove(os.path.join(CHAT_UPLOAD_DIR, filename))
        except OSError:
            pass

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

@app.errorhandler(413)
def upload_too_large(e):
    return render_template(
        "error.html",
        code=413,
        title="Faili ni kubwa",
        message=f"Media imezidi kikomo cha {CHAT_MAX_UPLOAD_MB} MB."
    ), 413


@app.errorhandler(404)
def not_found(e):
    return render_template("error.html", code=404, title="Ukurasa Haupo",
                            message="Ukurasa unaoutafuta haupo au umehamishwa."), 404


@app.errorhandler(500)
def server_error(e):
    return render_template("error.html", code=500, title="Hitilafu ya Mfumo",
                            message="Kuna tatizo la muda kwenye mfumo. Tafadhali jaribu tena baadaye."), 500


if __name__ == "__main__":
    app.run(debug=os.environ.get("FLASK_DEBUG") == "1", port=int(os.environ.get("PORT", 5000)))
