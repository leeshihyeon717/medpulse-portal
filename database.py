"""
Database schema, connection helper, and seeding for MedPulse Portal

By default this connects to a local SQLite file (DB_PATH below), which is fine for local
development but does NOT survive a redeploy/restart on hosts like Render with no persistent
disk. Setting TURSO_DATABASE_URL + TURSO_AUTH_TOKEN (e.g. in Render's environment variable
settings) switches every query to a remote Turso database instead, over Turso's plain HTTP
API (https://docs.turso.tech/sdk/http/quickstart) - using only the Python standard library's
urllib, so no extra pip dependency is needed. The Remote* classes below imitate just the
sqlite3.Connection/Cursor/Row surface this codebase actually uses, so database.py and
server.py don't need to know or care which mode they're in.
"""
import sqlite3
import os
import json
import time
import base64
import urllib.request
import urllib.error
from auth import hash_password

DB_PATH = os.path.join(os.path.dirname(__file__), "medpulse.db")

TURSO_DATABASE_URL = os.environ.get("TURSO_DATABASE_URL", "").strip()
TURSO_AUTH_TOKEN = os.environ.get("TURSO_AUTH_TOKEN", "").strip()
USE_REMOTE_DB = bool(TURSO_DATABASE_URL and TURSO_AUTH_TOKEN)


def _turso_http_base_url():
    url = TURSO_DATABASE_URL
    if url.startswith("libsql://"):
        url = "https://" + url[len("libsql://"):]
    elif url.startswith("turso://"):
        url = "https://" + url[len("turso://"):]
    return url.rstrip("/")


def _encode_arg(value):
    """Python value -> Hrana typed argument, per the libSQL HTTP API's Value format."""
    if value is None:
        return {"type": "null"}
    if isinstance(value, bool):
        return {"type": "integer", "value": str(int(value))}
    if isinstance(value, int):
        return {"type": "integer", "value": str(value)}
    if isinstance(value, float):
        return {"type": "float", "value": value}
    if isinstance(value, bytes):
        return {"type": "blob", "base64": base64.b64encode(value).decode("ascii")}
    return {"type": "text", "value": str(value)}


def _decode_value(value):
    """Hrana typed cell value -> native Python value."""
    vtype = value.get("type")
    if vtype == "integer":
        return int(value["value"])
    if vtype == "float":
        return float(value["value"])
    if vtype == "text":
        return value["value"]
    if vtype == "blob":
        return base64.b64decode(value["base64"])
    return None  # "null" (and any unrecognized future type) both default to None


class RemoteIntegrityError(sqlite3.IntegrityError):
    """Subclassing sqlite3.IntegrityError so server.py's existing
    `except sqlite3.IntegrityError` blocks catch this without any changes."""
    pass


class RemoteRow:
    """Mimics sqlite3.Row: supports row['col'], row[0], iteration, and dict(row)."""

    def __init__(self, cols, values):
        self._cols = cols
        self._values = values

    def __getitem__(self, key):
        if isinstance(key, int):
            return self._values[key]
        return self._values[self._cols.index(key)]

    def __iter__(self):
        return iter(self._values)

    def __len__(self):
        return len(self._values)

    def keys(self):
        return list(self._cols)

    def get(self, key, default=None):
        try:
            return self[key]
        except (ValueError, IndexError):
            return default


class RemoteCursor:
    def __init__(self):
        self._rows = []
        self._idx = 0
        self.lastrowid = None

    def execute(self, sql, params=()):
        args = [_encode_arg(p) for p in (params or ())]
        payload = {"requests": [
            {"type": "execute", "stmt": {"sql": sql, "args": args}},
            {"type": "close"},
        ]}
        req = urllib.request.Request(
            f"{_turso_http_base_url()}/v2/pipeline",
            data=json.dumps(payload).encode("utf-8"),
            method="POST",
            headers={
                "Authorization": f"Bearer {TURSO_AUTH_TOKEN}",
                "Content-Type": "application/json",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            raise RuntimeError(f"Turso HTTP API error {e.code}: {e.read().decode('utf-8', 'ignore')}")

        first = data["results"][0]
        if first["type"] == "error":
            message = first["error"].get("message", "Unknown Turso error")
            if "UNIQUE constraint failed" in message:
                raise RemoteIntegrityError(message)
            raise RuntimeError(f"Turso SQL error: {message}")

        result = first["response"]["result"]
        cols = [c.get("name") for c in result.get("cols", [])]
        self._rows = [RemoteRow(cols, [_decode_value(v) for v in row]) for row in result.get("rows", [])]
        self._idx = 0
        last_id = result.get("last_insert_rowid")
        self.lastrowid = int(last_id) if last_id is not None else None
        return self

    def executemany(self, sql, seq_of_params):
        for params in seq_of_params:
            self.execute(sql, params)

    def fetchone(self):
        if self._idx >= len(self._rows):
            return None
        row = self._rows[self._idx]
        self._idx += 1
        return row

    def fetchall(self):
        rows = self._rows[self._idx:]
        self._idx = len(self._rows)
        return rows


class RemoteConnection:
    """Each statement commits itself immediately over HTTP, so commit()/close() are no-ops -
    there's no persistent connection or pending transaction to manage."""

    def cursor(self):
        return RemoteCursor()

    def commit(self):
        pass

    def close(self):
        pass


def get_db():
    if USE_REMOTE_DB:
        return RemoteConnection()
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def _add_column_if_missing(cursor, table, column, coltype):
    """Adds a column to an existing table if it isn't already there.
    Needed because CREATE TABLE IF NOT EXISTS silently no-ops on a table that
    already exists with an older schema. Returns True if the column was added."""
    cursor.execute(f"PRAGMA table_info({table})")
    existing = {row[1] for row in cursor.fetchall()}
    if column not in existing:
        cursor.execute(f"ALTER TABLE {table} ADD COLUMN {column} {coltype}")
        return True
    return False

def init_db():
    conn = get_db()
    cursor = conn.cursor()

    # Users Table (Approved Medical Staff / Editors)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        email TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL,
        salt TEXT NOT NULL,
        name TEXT NOT NULL,
        role TEXT NOT NULL DEFAULT 'editor',
        title TEXT NOT NULL,
        avatar TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)

    # Sessions Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS sessions (
        token TEXT PRIMARY KEY,
        user_id INTEGER NOT NULL,
        expires_at INTEGER NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
    )
    """)

    # Medical Articles Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS articles (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT NOT NULL,
        slug TEXT UNIQUE,
        category TEXT NOT NULL,
        specialty_badge TEXT,
        summary TEXT NOT NULL,
        content TEXT NOT NULL,
        author_id INTEGER,
        author_name TEXT NOT NULL,
        author_title TEXT NOT NULL,
        cover_image TEXT,
        reading_time TEXT DEFAULT '5 min read',
        tags TEXT DEFAULT '[]',
        views INTEGER DEFAULT 0,
        helpful_count INTEGER DEFAULT 0,
        not_helpful_count INTEGER DEFAULT 0,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (author_id) REFERENCES users(id)
    )
    """)

    # Pharmacy Medications Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS pharmacy_items (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        generic_name TEXT NOT NULL,
        category TEXT NOT NULL,
        prescription_required INTEGER DEFAULT 0,
        dosage_form TEXT NOT NULL,
        indications TEXT NOT NULL,
        usage_instructions TEXT NOT NULL,
        side_effects TEXT NOT NULL,
        contraindications TEXT NOT NULL,
        storage_info TEXT NOT NULL,
        price REAL NOT NULL,
        in_stock INTEGER DEFAULT 1,
        rating REAL DEFAULT 4.9,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)

    # Comments Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS comments (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        article_id INTEGER,
        pharmacy_id INTEGER,
        author_name TEXT NOT NULL,
        author_role TEXT DEFAULT 'Patient / Visitor',
        content TEXT NOT NULL,
        likes INTEGER DEFAULT 0,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (article_id) REFERENCES articles(id) ON DELETE CASCADE,
        FOREIGN KEY (pharmacy_id) REFERENCES pharmacy_items(id) ON DELETE CASCADE
    )
    """)

    # Site Ratings Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS site_ratings (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        client_identifier TEXT,
        user_id INTEGER,
        score INTEGER NOT NULL,
        user_name TEXT NOT NULL,
        category TEXT DEFAULT 'Overall Experience',
        feedback TEXT,
        recommended INTEGER DEFAULT 1,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)

    # Migrate older databases created before client_identifier/user_id/updated_at existed
    # (CREATE TABLE IF NOT EXISTS above is a no-op once the table already exists).
    _add_column_if_missing(cursor, "site_ratings", "client_identifier", "TEXT")
    _add_column_if_missing(cursor, "site_ratings", "user_id", "INTEGER")
    if _add_column_if_missing(cursor, "site_ratings", "updated_at", "TIMESTAMP"):
        cursor.execute("UPDATE site_ratings SET updated_at = created_at WHERE updated_at IS NULL")

    # One review per identity - allows edit-in-place, blocks duplicates. A logged-in account is its
    # own identity (user_id), separate from the anonymous browser id (client_identifier) that tags
    # its row for reference; the client_identifier is only a uniqueness key for GUEST rows (user_id
    # IS NULL), so two different accounts logging in on the same browser never collide.
    cursor.execute("""
    CREATE UNIQUE INDEX IF NOT EXISTS idx_site_ratings_user_unique
    ON site_ratings(user_id) WHERE user_id IS NOT NULL
    """)
    # Drop and recreate: this index previously covered ALL rows regardless of user_id, which meant
    # a second account rating from the same browser as an earlier account would collide on this
    # index and get its INSERT rejected as a duplicate.
    cursor.execute("DROP INDEX IF EXISTS idx_site_ratings_client_unique")
    cursor.execute("""
    CREATE UNIQUE INDEX IF NOT EXISTS idx_site_ratings_client_unique
    ON site_ratings(client_identifier) WHERE client_identifier IS NOT NULL AND client_identifier != '' AND user_id IS NULL
    """)

    # Comment Likes Table - tracks which identity (user or anonymous client) already liked a comment
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS comment_likes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        comment_id INTEGER NOT NULL,
        liker_key TEXT NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(comment_id, liker_key),
        FOREIGN KEY (comment_id) REFERENCES comments(id) ON DELETE CASCADE
    )
    """)

    # Article Helpful/Not-Helpful Votes Table - one vote per identity per article
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS article_votes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        article_id INTEGER NOT NULL,
        liker_key TEXT NOT NULL,
        vote_type TEXT NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(article_id, liker_key),
        FOREIGN KEY (article_id) REFERENCES articles(id) ON DELETE CASCADE
    )
    """)

    conn.commit()
    seed_initial_data(conn)
    conn.close()

def seed_initial_data(conn):
    cursor = conn.cursor()

    # Check if users already exist
    cursor.execute("SELECT COUNT(*) FROM users")
    if cursor.fetchone()[0] == 0:
        med_pwd, med_salt = hash_password("MedicalAdmin2026!")
        pharm_pwd, pharm_salt = hash_password("DoctorSarah2026!")

        accounts = [
            # 1. Medical Article Access Only (Shihyeon Lee + 4 Medical Admins)
            (
                "shihyeon.lee@medpulse.org", med_pwd, med_salt,
                "Shihyeon Lee", "medical_editor", "Lead Medical Content Editor",
                "https://images.unsplash.com/photo-1534528741775-53994a69daeb?auto=format&fit=crop&q=80&w=300"
            ),
            (
                "admin1.medical@medpulse.org", med_pwd, med_salt,
                "Admin 1 Medical", "medical_editor", "Medical Article Specialist 1",
                "https://images.unsplash.com/photo-1559839734-2b71ea197ec2?auto=format&fit=crop&q=80&w=300"
            ),
            (
                "admin2.medical@medpulse.org", med_pwd, med_salt,
                "Admin 2 Medical", "medical_editor", "Medical Article Specialist 2",
                "https://images.unsplash.com/photo-1622253692010-333f2da6031d?auto=format&fit=crop&q=80&w=300"
            ),
            (
                "admin3.medical@medpulse.org", med_pwd, med_salt,
                "Admin 3 Medical", "medical_editor", "Medical Article Specialist 3",
                "https://images.unsplash.com/photo-1594824813589-a2a4b862bbd7?auto=format&fit=crop&q=80&w=300"
            ),
            (
                "admin4.medical@medpulse.org", med_pwd, med_salt,
                "Admin 4 Medical", "medical_editor", "Medical Article Specialist 4",
                "https://images.unsplash.com/photo-1612349317150-e413f6a5b16d?auto=format&fit=crop&q=80&w=300"
            ),

            # 2. Medication / Pharmacy Access Only (Jay Cho + 4 Medicine Admins)
            (
                "jay.cho@medpulse.org", pharm_pwd, pharm_salt,
                "Jay Cho", "pharmacy_editor", "Director of Clinical Pharmacology",
                "https://images.unsplash.com/photo-1537368910025-700350fe46c7?auto=format&fit=crop&q=80&w=300"
            ),
            (
                "admin1.medicine@medpulse.org", pharm_pwd, pharm_salt,
                "Admin 1 Medicine", "pharmacy_editor", "Clinical Pharmacy Specialist 1",
                "https://images.unsplash.com/photo-1594824813626-d667c4270df8?auto=format&fit=crop&q=80&w=300"
            ),
            (
                "admin2.medicine@medpulse.org", pharm_pwd, pharm_salt,
                "Admin 2 Medicine", "pharmacy_editor", "Clinical Pharmacy Specialist 2",
                "https://images.unsplash.com/photo-1582750433449-648ed127bb54?auto=format&fit=crop&q=80&w=300"
            ),
            (
                "admin3.medicine@medpulse.org", pharm_pwd, pharm_salt,
                "Admin 3 Medicine", "pharmacy_editor", "Clinical Pharmacy Specialist 3",
                "https://images.unsplash.com/photo-1551836022-d5d88e9218df?auto=format&fit=crop&q=80&w=300"
            ),
            (
                "admin4.medicine@medpulse.org", pharm_pwd, pharm_salt,
                "Admin 4 Medicine", "pharmacy_editor", "Clinical Pharmacy Specialist 4",
                "https://images.unsplash.com/photo-1579684385127-1ef15d508118?auto=format&fit=crop&q=80&w=300"
            ),

            # 3. Full Platform Access (Admin Full 1 & Admin Full 2)
            (
                "admin.full1@medpulse.org", med_pwd, med_salt,
                "Admin Full 1", "admin", "Chief Executive Medical Administrator",
                "https://images.unsplash.com/photo-1559839734-2b71ea197ec2?auto=format&fit=crop&q=80&w=300"
            ),
            (
                "admin.full2@medpulse.org", med_pwd, med_salt,
                "Admin Full 2", "admin", "Senior Platform & Operations Administrator",
                "https://images.unsplash.com/photo-1507003211169-0a1dd7228f2d?auto=format&fit=crop&q=80&w=300"
            )
        ]

        cursor.executemany("""
        INSERT INTO users (email, password_hash, salt, name, role, title, avatar)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """, accounts)

    conn.commit()

def clear_all_content():
    """Purge all articles, medications, comments, and ratings from the database."""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM articles")
    cursor.execute("DELETE FROM pharmacy_items")
    cursor.execute("DELETE FROM comments")
    cursor.execute("DELETE FROM site_ratings")
    cursor.execute("DELETE FROM sqlite_sequence WHERE name IN ('articles', 'pharmacy_items', 'comments', 'site_ratings')")
    conn.commit()
    conn.close()
    print("✓ All articles, medications, comments, and reviews have been deleted.")

def reseed_users():
    """Reset and re-seed the 12 specific accounts."""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM sessions")
    cursor.execute("DELETE FROM users")
    cursor.execute("DELETE FROM sqlite_sequence WHERE name IN ('users', 'sessions')")
    conn.commit()
    seed_initial_data(conn)
    conn.close()
    print("✓ 12 Clinician and Admin accounts re-seeded successfully.")

if __name__ == "__main__":
    init_db()
    reseed_users()
    clear_all_content()
    print("Database ready with 12 configured accounts and clean content tables.")

