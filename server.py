"""
MedPulse Medical & Pharmacy Portal - REST API & Web Server
"""
import http.server
import json
import mimetypes
import os
import re
import sqlite3
import sys
import time
import urllib.parse
from database import get_db, init_db
from auth import verify_password, generate_session_token, hash_password, SESSION_EXPIRY_SECONDS

PORT = int(os.environ.get("PORT", 8000))
PUBLIC_DIR = os.path.join(os.path.dirname(__file__), "public")

def dict_from_row(row):
    return dict(row) if row else None

class MedPulseHandler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=PUBLIC_DIR, **kwargs)

    def _send_json(self, data, status=200):
        body = json.dumps(data, default=str).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, PUT, DELETE, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
        self.end_headers()
        self.wfile.write(body)

    def _send_error_json(self, message, status=400, details=None):
        payload = {"error": message, "status": status}
        if details:
            payload["details"] = details
        self._send_json(payload, status=status)

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, PUT, DELETE, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
        self.end_headers()

    def _read_json_body(self):
        try:
            content_length = int(self.headers.get("Content-Length", 0))
            if content_length == 0:
                return {}
            raw = self.rfile.read(content_length).decode("utf-8")
            return json.loads(raw)
        except Exception as e:
            return None

    def _get_auth_user(self):
        auth_header = self.headers.get("Authorization", "")
        token = ""
        if auth_header.startswith("Bearer "):
            token = auth_header[7:].strip()
        
        if not token:
            cookie_header = self.headers.get("Cookie", "")
            for cookie in cookie_header.split(";"):
                parts = cookie.strip().split("=")
                if len(parts) == 2 and parts[0] == "medpulse_session":
                    token = parts[1]
                    break

        if not token:
            return None

        conn = get_db()
        cursor = conn.cursor()
        now = int(time.time())
        cursor.execute("""
            SELECT u.id, u.email, u.name, u.role, u.title, u.avatar, s.expires_at
            FROM sessions s
            JOIN users u ON s.user_id = u.id
            WHERE s.token = ? AND s.expires_at > ?
        """, (token, now))
        row = cursor.fetchone()
        conn.close()
        return dict_from_row(row)

    def _get_liker_key(self, user, client_identifier):
        """Stable identity key used to dedupe likes/votes/reviews: the account id if
        logged in, otherwise the anonymous per-browser client_identifier."""
        if user:
            return f"user:{user['id']}"
        if client_identifier:
            return f"client:{client_identifier}"
        return None

    def _require_article_editor(self):
        user = self._get_auth_user()
        if not user:
            self._send_error_json("Unauthorized. You must be logged in to publish or edit medical articles.", 401)
            return None
        if user.get("role") not in ("admin", "medical_editor", "editor"):
            self._send_error_json("Forbidden. Your account only has permission for specific modules and cannot edit medical articles.", 403)
            return None
        return user

    def _require_pharmacy_editor(self):
        user = self._get_auth_user()
        if not user:
            self._send_error_json("Unauthorized. You must be logged in to manage pharmacy medications.", 401)
            return None
        if user.get("role") not in ("admin", "pharmacy_editor", "editor"):
            self._send_error_json("Forbidden. Your account only has permission for specific modules and cannot edit pharmacy medications.", 403)
            return None
        return user

    def _require_admin(self):
        user = self._get_auth_user()
        if not user:
            self._send_error_json("Unauthorized. You must be logged in as an administrator.", 401)
            return None
        if user.get("role") != "admin":
            self._send_error_json("Forbidden. Only Full Administrators can assign or manage site editors and permissions.", 403)
            return None
        return user

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        query = urllib.parse.parse_qs(parsed.query)

        # API Endpoints
        if path.startswith("/api/"):
            return self._handle_api_get(path, query)

        # Static Files fallback
        if path == "/" or not os.path.exists(os.path.join(PUBLIC_DIR, path.lstrip("/"))):
            self.path = "/index.html"
        return super().do_GET()

    def _handle_api_get(self, path, query):
        conn = get_db()
        cursor = conn.cursor()

        try:
            # 1. Auth check: /api/auth/me
            if path == "/api/auth/me":
                user = self._get_auth_user()
                if user:
                    return self._send_json({"authenticated": True, "user": user})
                return self._send_json({"authenticated": False, "user": None})

            # 2. Stats: /api/stats
            if path == "/api/stats":
                cursor.execute("SELECT COUNT(*) FROM articles")
                total_articles = cursor.fetchone()[0]

                cursor.execute("SELECT COUNT(*) FROM pharmacy_items")
                total_meds = cursor.fetchone()[0]

                cursor.execute("SELECT COUNT(*) FROM comments")
                total_comments = cursor.fetchone()[0]

                cursor.execute("SELECT AVG(score), COUNT(*) FROM site_ratings")
                rating_row = cursor.fetchone()
                total_ratings = rating_row[1] if rating_row else 0
                avg_rating = round(rating_row[0], 1) if (rating_row and rating_row[0] is not None and total_ratings > 0) else 0.0

                cursor.execute("SELECT COUNT(*) FROM users WHERE role IN ('admin', 'editor', 'medical_editor', 'pharmacy_editor')")
                total_doctors = cursor.fetchone()[0]

                return self._send_json({
                    "total_articles": total_articles,
                    "total_medications": total_meds,
                    "total_comments": total_comments,
                    "avg_rating": avg_rating,
                    "total_ratings": total_ratings,
                    "total_doctors": total_doctors
                })

            # 3. Articles: /api/articles or /api/articles/<id>
            match_art = re.match(r"^/api/articles/(\d+)$", path)
            if match_art:
                art_id = int(match_art.group(1))
                # Increment views
                cursor.execute("UPDATE articles SET views = views + 1 WHERE id = ?", (art_id,))
                conn.commit()

                cursor.execute("SELECT * FROM articles WHERE id = ?", (art_id,))
                row = cursor.fetchone()
                if not row:
                    return self._send_error_json("Article not found", 404)
                
                art = dict_from_row(row)
                try:
                    art["tags"] = json.loads(art.get("tags") or "[]")
                except:
                    art["tags"] = []

                liker_key = self._get_liker_key(self._get_auth_user(), query.get("client_identifier", [""])[0].strip())
                art["my_vote"] = None
                if liker_key:
                    cursor.execute("SELECT vote_type FROM article_votes WHERE article_id = ? AND liker_key = ?", (art_id, liker_key))
                    vote_row = cursor.fetchone()
                    if vote_row:
                        art["my_vote"] = vote_row["vote_type"]

                return self._send_json(art)

            if path == "/api/articles":
                search_q = query.get("search", [""])[0].strip()
                category = query.get("category", [""])[0].strip()
                tag = query.get("tag", [""])[0].strip()

                sql = "SELECT * FROM articles WHERE 1=1"
                params = []

                if search_q:
                    sql += " AND (title LIKE ? OR summary LIKE ? OR content LIKE ?)"
                    params.extend([f"%{search_q}%", f"%{search_q}%", f"%{search_q}%"])
                if category and category.lower() != "all":
                    sql += " AND (category = ? OR specialty_badge = ?)"
                    params.extend([category, category])
                if tag:
                    sql += " AND tags LIKE ?"
                    params.append(f"%{tag}%")

                sql += " ORDER BY created_at DESC"
                cursor.execute(sql, params)
                rows = cursor.fetchall()
                articles = []
                for r in rows:
                    item = dict_from_row(r)
                    try:
                        item["tags"] = json.loads(item.get("tags") or "[]")
                    except:
                        item["tags"] = []
                    articles.append(item)
                return self._send_json({"articles": articles, "count": len(articles)})

            # 4. Pharmacy: /api/pharmacy or /api/pharmacy/<id>
            match_pharm = re.match(r"^/api/pharmacy/(\d+)$", path)
            if match_pharm:
                pharm_id = int(match_pharm.group(1))
                cursor.execute("SELECT * FROM pharmacy_items WHERE id = ?", (pharm_id,))
                row = cursor.fetchone()
                if not row:
                    return self._send_error_json("Pharmacy item not found", 404)
                return self._send_json(dict_from_row(row))

            if path == "/api/pharmacy":
                search_q = query.get("search", [""])[0].strip()
                category = query.get("category", [""])[0].strip()
                ptype = query.get("type", [""])[0].strip().lower()

                sql = "SELECT * FROM pharmacy_items WHERE 1=1"
                params = []

                if search_q:
                    sql += " AND (name LIKE ? OR generic_name LIKE ? OR indications LIKE ?)"
                    params.extend([f"%{search_q}%", f"%{search_q}%", f"%{search_q}%"])
                if category and category.lower() != "all":
                    sql += " AND category = ?"
                    params.append(category)
                if ptype == "rx":
                    sql += " AND prescription_required = 1"
                elif ptype == "otc":
                    sql += " AND prescription_required = 0"

                sql += " ORDER BY name ASC"
                cursor.execute(sql, params)
                items = [dict_from_row(r) for r in cursor.fetchall()]
                return self._send_json({"medications": items, "count": len(items)})

            # 5. Comments: /api/comments
            if path == "/api/comments":
                article_id = query.get("article_id", [""])[0]
                pharmacy_id = query.get("pharmacy_id", [""])[0]

                sql = "SELECT * FROM comments WHERE 1=1"
                params = []
                if article_id:
                    sql += " AND article_id = ?"
                    params.append(int(article_id))
                elif pharmacy_id:
                    sql += " AND pharmacy_id = ?"
                    params.append(int(pharmacy_id))

                sql += " ORDER BY created_at DESC"
                cursor.execute(sql, params)
                comments = [dict_from_row(r) for r in cursor.fetchall()]

                liker_key = self._get_liker_key(self._get_auth_user(), query.get("client_identifier", [""])[0].strip())
                liked_ids = set()
                if liker_key and comments:
                    placeholders = ",".join("?" * len(comments))
                    cursor.execute(
                        f"SELECT comment_id FROM comment_likes WHERE liker_key = ? AND comment_id IN ({placeholders})",
                        (liker_key, *[c["id"] for c in comments])
                    )
                    liked_ids = {r["comment_id"] for r in cursor.fetchall()}
                for c in comments:
                    c["liked_by_me"] = c["id"] in liked_ids

                return self._send_json({"comments": comments, "count": len(comments)})

            # 6. Site Ratings: /api/ratings
            if path == "/api/ratings":
                cursor.execute("SELECT * FROM site_ratings ORDER BY created_at DESC")
                ratings = [dict_from_row(r) for r in cursor.fetchall()]

                # Calculate metrics
                total = len(ratings)
                avg = round(sum(r["score"] for r in ratings) / total, 1) if total > 0 else 0.0
                stars_count = {1: 0, 2: 0, 3: 0, 4: 0, 5: 0}
                recommended_count = 0
                for r in ratings:
                    stars_count[r["score"]] = stars_count.get(r["score"], 0) + 1
                    if r.get("recommended"):
                        recommended_count += 1

                recommend_pct = round((recommended_count / total) * 100) if total > 0 else 0

                return self._send_json({
                    "ratings": ratings,
                    "summary": {
                        "average": avg,
                        "total": total,
                        "recommend_percentage": recommend_pct,
                        "distribution": stars_count
                    }
                })

            # 6.1 My Rating / Existing Review: /api/ratings/my
            if path == "/api/ratings/my":
                client_id = query.get("client_identifier", [""])[0].strip()
                user = self._get_auth_user()
                user_id = user["id"] if user else None

                # A logged-in identity is matched by account only - never fall back to the shared
                # browser client_identifier, or switching accounts on the same browser would surface
                # (and later overwrite) whichever other account last rated from that browser.
                row = None
                if user_id:
                    cursor.execute("SELECT * FROM site_ratings WHERE user_id = ? ORDER BY id DESC LIMIT 1", (user_id,))
                    row = cursor.fetchone()
                elif client_id:
                    cursor.execute("SELECT * FROM site_ratings WHERE client_identifier = ? AND user_id IS NULL ORDER BY id DESC LIMIT 1", (client_id,))
                    row = cursor.fetchone()

                return self._send_json({"review": dict_from_row(row) if row else None})

            # 7. Medical Staff / Editors List: /api/users
            if path == "/api/users":
                cursor.execute("""
                SELECT id, email, name, role, title, avatar, created_at
                FROM users
                ORDER BY CASE WHEN role = 'admin' THEN 0 WHEN role = 'medical_editor' THEN 1 ELSE 2 END, name ASC
                """)
                rows = cursor.fetchall()
                users = [dict_from_row(r) for r in rows]
                return self._send_json({"users": users})

            return self._send_error_json(f"Endpoint GET {path} not found", 404)

        finally:
            conn.close()

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        data = self._read_json_body()
        if data is None:
            return self._send_error_json("Invalid JSON request body", 400)

        conn = get_db()
        cursor = conn.cursor()

        try:
            # 1. Auth Login: /api/auth/login
            if path == "/api/auth/login":
                email = data.get("email", "").strip()
                password = data.get("password", "")

                if not email or not password:
                    return self._send_error_json("Email and password are required", 400)

                cursor.execute("SELECT * FROM users WHERE email = ?", (email,))
                user = cursor.fetchone()
                if not user or not verify_password(password, user["password_hash"], user["salt"]):
                    return self._send_error_json("Invalid medical credentials or not an approved editor", 401)

                token = generate_session_token()
                expires_at = int(time.time()) + SESSION_EXPIRY_SECONDS
                cursor.execute("INSERT INTO sessions (token, user_id, expires_at) VALUES (?, ?, ?)",
                               (token, user["id"], expires_at))
                conn.commit()

                user_dict = {
                    "id": user["id"],
                    "email": user["email"],
                    "name": user["name"],
                    "role": user["role"],
                    "title": user["title"],
                    "avatar": user["avatar"]
                }
                return self._send_json({
                    "success": True,
                    "token": token,
                    "user": user_dict,
                    "message": f"Welcome back, {user['name']} (Approved {user['role'].title()})"
                })

            # 2. Auth Logout: /api/auth/logout
            if path == "/api/auth/logout":
                token = data.get("token", "")
                if token:
                    cursor.execute("DELETE FROM sessions WHERE token = ?", (token,))
                    conn.commit()
                return self._send_json({"success": True, "message": "Logged out successfully"})

            # 3. Create Article: POST /api/articles (PROTECTED - Medical Article Editors Only)
            if path == "/api/articles":
                user = self._require_article_editor()
                if not user:
                    return

                title = data.get("title", "").strip()
                category = data.get("category", "General Health").strip()
                summary = data.get("summary", "").strip()
                content = data.get("content", "").strip()
                specialty = data.get("specialty_badge", category).strip()
                cover_image = data.get("cover_image", "").strip() or "https://images.unsplash.com/photo-1576091160399-112ba8d25d1d?auto=format&fit=crop&q=80&w=1000"
                reading_time = data.get("reading_time", "5 min read").strip()
                tags = data.get("tags", [])
                if isinstance(tags, str):
                    tags = [t.strip() for t in tags.split(",") if t.strip()]

                if not title or not content:
                    return self._send_error_json("Title and content are required", 400)

                slug = re.sub(r'[^a-zA-Z0-9]+', '-', title.lower()).strip('-') + f"-{int(time.time())}"

                cursor.execute("""
                INSERT INTO articles (title, slug, category, specialty_badge, summary, content, author_id, author_name, author_title, cover_image, reading_time, tags)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    title, slug, category, specialty, summary, content,
                    user["id"], user["name"], user["title"], cover_image,
                    reading_time, json.dumps(tags)
                ))
                conn.commit()
                article_id = cursor.lastrowid

                return self._send_json({
                    "success": True,
                    "message": "Medical article published successfully.",
                    "article_id": article_id
                }, 201)

            # 4. Article Helpful/Vote: POST /api/articles/<id>/vote (Public, one vote per visitor)
            match_vote = re.match(r"^/api/articles/(\d+)/vote$", path)
            if match_vote:
                art_id = int(match_vote.group(1))
                vote_type = data.get("type", "helpful")
                client_identifier = data.get("client_identifier", "").strip()
                liker_key = self._get_liker_key(self._get_auth_user(), client_identifier)

                if not liker_key:
                    return self._send_error_json("Unable to identify visitor. Please refresh the page and try again.", 400)

                try:
                    cursor.execute(
                        "INSERT INTO article_votes (article_id, liker_key, vote_type) VALUES (?, ?, ?)",
                        (art_id, liker_key, vote_type)
                    )
                except sqlite3.IntegrityError:
                    return self._send_error_json("You have already submitted feedback for this article.", 409)

                if vote_type == "helpful":
                    cursor.execute("UPDATE articles SET helpful_count = helpful_count + 1 WHERE id = ?", (art_id,))
                else:
                    cursor.execute("UPDATE articles SET not_helpful_count = not_helpful_count + 1 WHERE id = ?", (art_id,))
                conn.commit()
                return self._send_json({"success": True, "message": "Thank you for your feedback!"})

            # 5. Create Pharmacy Item: POST /api/pharmacy (PROTECTED - Pharmacy Editors Only)
            if path == "/api/pharmacy":
                user = self._require_pharmacy_editor()
                if not user:
                    return

                name = data.get("name", "").strip()
                generic_name = data.get("generic_name", "").strip()
                category = data.get("category", "General").strip()
                rx_req = 1 if data.get("prescription_required") in (True, 1, "1", "true") else 0
                dosage_form = data.get("dosage_form", "").strip()
                indications = data.get("indications", "").strip()
                usage_instructions = data.get("usage_instructions", "").strip()
                side_effects = data.get("side_effects", "").strip()
                contraindications = data.get("contraindications", "").strip()
                storage_info = data.get("storage_info", "Store at room temperature.").strip()
                price = float(data.get("price", 10.0))

                if not name or not indications:
                    return self._send_error_json("Medication name and indications are required", 400)

                cursor.execute("""
                INSERT INTO pharmacy_items (name, generic_name, category, prescription_required, dosage_form, indications, usage_instructions, side_effects, contraindications, storage_info, price)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    name, generic_name, category, rx_req, dosage_form,
                    indications, usage_instructions, side_effects, contraindications,
                    storage_info, price
                ))
                conn.commit()
                pharm_id = cursor.lastrowid

                return self._send_json({
                    "success": True,
                    "message": "Medication added to pharmacy catalog.",
                    "item_id": pharm_id
                }, 201)

            # 6. Post Comment: POST /api/comments (Public / Visitors)
            if path == "/api/comments":
                author_name = data.get("author_name", "").strip() or "Visitor"
                author_role = data.get("author_role", "Patient / Visitor").strip()
                content = data.get("content", "").strip()
                article_id = data.get("article_id")
                pharmacy_id = data.get("pharmacy_id")

                # If the author is logged in as an editor, elevate their badge!
                user = self._get_auth_user()
                if user:
                    author_name = user["name"]
                    author_role = f"Verified {user['role'].title()} ({user['title']})"

                if not content:
                    return self._send_error_json("Comment content cannot be empty", 400)

                cursor.execute("""
                INSERT INTO comments (article_id, pharmacy_id, author_name, author_role, content)
                VALUES (?, ?, ?, ?, ?)
                """, (article_id, pharmacy_id, author_name, author_role, content))
                conn.commit()
                comment_id = cursor.lastrowid

                return self._send_json({
                    "success": True,
                    "message": "Comment posted successfully.",
                    "comment_id": comment_id
                }, 201)

            # 7. Like Comment: POST /api/comments/<id>/like (Public, one like per visitor)
            match_like = re.match(r"^/api/comments/(\d+)/like$", path)
            if match_like:
                com_id = int(match_like.group(1))
                client_identifier = data.get("client_identifier", "").strip()
                liker_key = self._get_liker_key(self._get_auth_user(), client_identifier)

                if not liker_key:
                    return self._send_error_json("Unable to identify visitor. Please refresh the page and try again.", 400)

                try:
                    cursor.execute(
                        "INSERT INTO comment_likes (comment_id, liker_key) VALUES (?, ?)",
                        (com_id, liker_key)
                    )
                except sqlite3.IntegrityError:
                    return self._send_error_json("You have already marked this comment as helpful.", 409)

                cursor.execute("UPDATE comments SET likes = likes + 1 WHERE id = ?", (com_id,))
                conn.commit()
                return self._send_json({"success": True})

            # 8. Post Site Rating: POST /api/ratings (Public / Visitors - one review per visitor, editable)
            if path == "/api/ratings":
                raw_score = data.get("score")
                if raw_score is None:
                    return self._send_error_json("Please select a star rating before submitting.", 400)
                try:
                    score = int(raw_score)
                except (TypeError, ValueError):
                    return self._send_error_json("Please select a star rating before submitting.", 400)
                if score < 1 or score > 5:
                    return self._send_error_json("Score must be between 1 and 5", 400)

                user_name = data.get("user_name", "").strip() or "Anonymous Patient"
                category = data.get("category", "Overall Experience").strip()
                feedback = data.get("feedback", "").strip()
                recommended = 1 if data.get("recommended", True) else 0
                client_identifier = data.get("client_identifier", "").strip()

                user = self._get_auth_user()
                user_id = user["id"] if user else None

                if not user_id and not client_identifier:
                    return self._send_error_json("Unable to identify visitor. Please refresh the page and try again.", 400)

                # A logged-in identity is matched (and later updated) by account only. Falling back to
                # the shared browser client_identifier here would let a second account logged in on the
                # same browser silently overwrite the first account's review instead of adding its own.
                existing = None
                if user_id:
                    cursor.execute("SELECT id FROM site_ratings WHERE user_id = ?", (user_id,))
                    existing = cursor.fetchone()
                elif client_identifier:
                    cursor.execute("SELECT id FROM site_ratings WHERE client_identifier = ? AND user_id IS NULL", (client_identifier,))
                    existing = cursor.fetchone()

                if existing:
                    cursor.execute("""
                    UPDATE site_ratings
                    SET score = ?, user_name = ?, category = ?, feedback = ?, recommended = ?,
                        user_id = ?, client_identifier = ?, updated_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                    """, (score, user_name, category, feedback, recommended, user_id, client_identifier, existing["id"]))
                    conn.commit()
                    return self._send_json({
                        "success": True,
                        "message": "Your review has been updated. Thank you for keeping your feedback current!",
                        "rating_id": existing["id"]
                    })

                cursor.execute("""
                INSERT INTO site_ratings (score, user_name, category, feedback, recommended, user_id, client_identifier)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (score, user_name, category, feedback, recommended, user_id, client_identifier))
                conn.commit()
                rating_id = cursor.lastrowid

                return self._send_json({
                    "success": True,
                    "message": "Thank you for rating MedPulse! Your feedback helps us improve clinical content.",
                    "rating_id": rating_id
                }, 201)

            # 9. Create / Assign New Editor or Admin: POST /api/users (PROTECTED - Admin Only)
            if path == "/api/users":
                admin = self._require_admin()
                if not admin:
                    return

                email = data.get("email", "").strip().lower()
                name = data.get("name", "").strip()
                password = data.get("password", "").strip()
                role = data.get("role", "editor").strip().lower()
                title = data.get("title", "Clinical Contributor").strip()
                avatar = data.get("avatar", "").strip() or "https://images.unsplash.com/photo-1622253692010-333f2da6031d?auto=format&fit=crop&q=80&w=300"

                if not email or not name or not password:
                    return self._send_error_json("Email, full name, and password are required", 400)

                if role not in ("admin", "editor", "medical_editor", "pharmacy_editor"):
                    role = "editor"

                cursor.execute("SELECT id FROM users WHERE email = ?", (email,))
                if cursor.fetchone():
                    return self._send_error_json("A user with this email address already exists", 400)

                pwd_hash, salt = hash_password(password)
                cursor.execute("""
                INSERT INTO users (email, password_hash, salt, name, role, title, avatar)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (email, pwd_hash, salt, name, role, title, avatar))
                conn.commit()
                user_id = cursor.lastrowid

                return self._send_json({
                    "success": True,
                    "message": f"Successfully assigned {name} as an approved {role.upper()}.",
                    "user": {
                        "id": user_id,
                        "email": email,
                        "name": name,
                        "role": role,
                        "title": title,
                        "avatar": avatar
                    }
                }, 201)

            return self._send_error_json(f"Endpoint POST {path} not found", 404)

        finally:
            conn.close()

    def do_PUT(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        data = self._read_json_body()
        if data is None:
            return self._send_error_json("Invalid JSON request body", 400)

        conn = get_db()
        cursor = conn.cursor()

        try:
            # 1. Update Article: PUT /api/articles/<id> (PROTECTED - Medical Article Editors Only)
            match_art = re.match(r"^/api/articles/(\d+)$", path)
            if match_art:
                user = self._require_article_editor()
                if not user:
                    return

                art_id = int(match_art.group(1))
                cursor.execute("SELECT * FROM articles WHERE id = ?", (art_id,))
                if not cursor.fetchone():
                    return self._send_error_json("Article not found", 404)

                title = data.get("title", "").strip()
                category = data.get("category", "General Health").strip()
                summary = data.get("summary", "").strip()
                content = data.get("content", "").strip()
                specialty = data.get("specialty_badge", category).strip()
                cover_image = data.get("cover_image", "").strip()
                reading_time = data.get("reading_time", "5 min read").strip()
                tags = data.get("tags", [])
                if isinstance(tags, str):
                    tags = [t.strip() for t in tags.split(",") if t.strip()]

                if not title or not content:
                    return self._send_error_json("Title and content are required", 400)

                cursor.execute("""
                UPDATE articles
                SET title = ?, category = ?, specialty_badge = ?, summary = ?, content = ?,
                    cover_image = ?, reading_time = ?, tags = ?, updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """, (
                    title, category, specialty, summary, content,
                    cover_image, reading_time, json.dumps(tags), art_id
                ))
                conn.commit()
                return self._send_json({"success": True, "message": "Article updated successfully."})

            # 2. Update Pharmacy Item: PUT /api/pharmacy/<id> (PROTECTED - Pharmacy Editors Only)
            match_pharm = re.match(r"^/api/pharmacy/(\d+)$", path)
            if match_pharm:
                user = self._require_pharmacy_editor()
                if not user:
                    return

                pharm_id = int(match_pharm.group(1))
                cursor.execute("SELECT * FROM pharmacy_items WHERE id = ?", (pharm_id,))
                if not cursor.fetchone():
                    return self._send_error_json("Pharmacy item not found", 404)

                name = data.get("name", "").strip()
                generic_name = data.get("generic_name", "").strip()
                category = data.get("category", "General").strip()
                rx_req = 1 if data.get("prescription_required") in (True, 1, "1", "true") else 0
                dosage_form = data.get("dosage_form", "").strip()
                indications = data.get("indications", "").strip()
                usage_instructions = data.get("usage_instructions", "").strip()
                side_effects = data.get("side_effects", "").strip()
                contraindications = data.get("contraindications", "").strip()
                storage_info = data.get("storage_info", "Store at room temperature.").strip()
                price = float(data.get("price", 10.0))
                in_stock = 1 if data.get("in_stock", True) else 0

                cursor.execute("""
                UPDATE pharmacy_items
                SET name = ?, generic_name = ?, category = ?, prescription_required = ?,
                    dosage_form = ?, indications = ?, usage_instructions = ?, side_effects = ?,
                    contraindications = ?, storage_info = ?, price = ?, in_stock = ?, updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """, (
                    name, generic_name, category, rx_req, dosage_form,
                    indications, usage_instructions, side_effects, contraindications,
                    storage_info, price, in_stock, pharm_id
                ))
                conn.commit()
                return self._send_json({"success": True, "message": "Pharmacy item updated successfully."})

            # 3. Update User / Editor: PUT /api/users/<id> (PROTECTED - Admin Only)
            match_user = re.match(r"^/api/users/(\d+)$", path)
            if match_user:
                admin = self._require_admin()
                if not admin:
                    return

                target_id = int(match_user.group(1))
                cursor.execute("SELECT * FROM users WHERE id = ?", (target_id,))
                existing = cursor.fetchone()
                if not existing:
                    return self._send_error_json("User not found", 404)

                name = data.get("name", "").strip() or existing["name"]
                email = data.get("email", "").strip().lower() or existing["email"]
                title = data.get("title", "").strip() or existing["title"]
                role = data.get("role", "").strip().lower() or existing["role"]
                avatar = data.get("avatar", "").strip() or existing["avatar"]
                password = data.get("password", "").strip()

                if role not in ("admin", "editor", "medical_editor", "pharmacy_editor"):
                    role = existing["role"]

                if email != existing["email"]:
                    cursor.execute("SELECT id FROM users WHERE email = ? AND id != ?", (email, target_id))
                    if cursor.fetchone():
                        return self._send_error_json("Email is already registered to another user", 400)

                if password:
                    pwd_hash, salt = hash_password(password)
                    cursor.execute("""
                    UPDATE users
                    SET name = ?, email = ?, title = ?, role = ?, avatar = ?, password_hash = ?, salt = ?
                    WHERE id = ?
                    """, (name, email, title, role, avatar, pwd_hash, salt, target_id))
                else:
                    cursor.execute("""
                    UPDATE users
                    SET name = ?, email = ?, title = ?, role = ?, avatar = ?
                    WHERE id = ?
                    """, (name, email, title, role, avatar, target_id))
                conn.commit()

                return self._send_json({
                    "success": True,
                    "message": f"Updated profile and permissions for {name}."
                })

            return self._send_error_json(f"Endpoint PUT {path} not found", 404)

        finally:
            conn.close()

    def do_DELETE(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path

        conn = get_db()
        cursor = conn.cursor()

        try:
            # 1. Delete Article: DELETE /api/articles/<id> (PROTECTED - Medical Article Editors Only)
            match_art = re.match(r"^/api/articles/(\d+)$", path)
            if match_art:
                user = self._require_article_editor()
                if not user:
                    return

                art_id = int(match_art.group(1))
                cursor.execute("DELETE FROM articles WHERE id = ?", (art_id,))
                conn.commit()
                return self._send_json({"success": True, "message": "Article deleted successfully."})

            # 2. Delete Pharmacy Item: DELETE /api/pharmacy/<id> (PROTECTED - Pharmacy Editors Only)
            match_pharm = re.match(r"^/api/pharmacy/(\d+)$", path)
            if match_pharm:
                user = self._require_pharmacy_editor()
                if not user:
                    return

                pharm_id = int(match_pharm.group(1))
                cursor.execute("DELETE FROM pharmacy_items WHERE id = ?", (pharm_id,))
                conn.commit()
                return self._send_json({"success": True, "message": "Pharmacy medication deleted successfully."})

            # 3. Delete Site Rating/Review: DELETE /api/ratings/<id> (PROTECTED - Full Admins Only)
            match_rating = re.match(r"^/api/ratings/(\d+)$", path)
            if match_rating:
                admin = self._require_admin()
                if not admin:
                    return

                rating_id = int(match_rating.group(1))
                cursor.execute("SELECT id FROM site_ratings WHERE id = ?", (rating_id,))
                if not cursor.fetchone():
                    return self._send_error_json("Rating not found", 404)

                cursor.execute("DELETE FROM site_ratings WHERE id = ?", (rating_id,))
                conn.commit()
                return self._send_json({"success": True, "message": "Rating deleted successfully."})

            # 4. Delete User / Revoke Editor Access: DELETE /api/users/<id> (PROTECTED - Admin Only)
            match_user = re.match(r"^/api/users/(\d+)$", path)
            if match_user:
                admin = self._require_admin()
                if not admin:
                    return

                target_id = int(match_user.group(1))
                if target_id == admin["id"]:
                    return self._send_error_json("You cannot delete your own administrative account.", 400)

                cursor.execute("SELECT id, name FROM users WHERE id = ?", (target_id,))
                user_row = cursor.fetchone()
                if not user_row:
                    return self._send_error_json("User not found", 404)

                cursor.execute("DELETE FROM sessions WHERE user_id = ?", (target_id,))
                cursor.execute("DELETE FROM users WHERE id = ?", (target_id,))
                conn.commit()

                return self._send_json({
                    "success": True,
                    "message": f"Successfully revoked editorial access for {user_row['name']}."
                })

            return self._send_error_json(f"Endpoint DELETE {path} not found", 404)

        finally:
            conn.close()

def run(port=PORT):
    init_db()
    server_address = ("", port)
    httpd = http.server.ThreadingHTTPServer(server_address, MedPulseHandler)
    print(f"MedPulse Health & Pharmacy Portal running on http://localhost:{port}")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down server.")
        httpd.server_close()

if __name__ == "__main__":
    run()
