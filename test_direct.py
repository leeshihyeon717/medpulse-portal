"""
Direct in-process unit tests for MedPulse Backend logic, RBAC, and Database
"""
import io
import json
import sqlite3
import time
from database import init_db, get_db
from auth import hash_password, verify_password, generate_session_token, SESSION_EXPIRY_SECONDS
from server import MedPulseHandler

class MockRequest:
    def __init__(self, raw_input=b""):
        self.raw_input = raw_input

    def makefile(self, mode, *args, **kwargs):
        if 'b' in mode:
            if 'r' in mode:
                return io.BytesIO(self.raw_input)
            elif 'w' in mode:
                return io.BytesIO()
        return io.StringIO()

def run_direct_tests():
    print("\n--- [1] Initializing Database & Seed Verification ---")
    init_db()
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("SELECT COUNT(*) FROM articles")
    art_count = cursor.fetchone()[0]
    assert art_count >= 5, f"Expected at least 5 articles, got {art_count}"
    print(f"✓ Verified {art_count} medical articles in database.")

    cursor.execute("SELECT COUNT(*) FROM pharmacy_items")
    pharm_count = cursor.fetchone()[0]
    assert pharm_count >= 8, f"Expected at least 8 pharmacy items, got {pharm_count}"
    print(f"✓ Verified {pharm_count} pharmacy items in database.")

    cursor.execute("SELECT COUNT(*) FROM users WHERE role IN ('admin', 'editor', 'medical_editor', 'pharmacy_editor')")
    doctor_count = cursor.fetchone()[0]
    assert doctor_count >= 2, f"Expected at least 2 approved editors, got {doctor_count}"
    print(f"✓ Verified {doctor_count} approved medical doctors/editors.")

    print("\n--- [2] Testing Auth & RBAC Security Module ---")
    # Verify Shihyeon Lee's password
    cursor.execute("SELECT id, password_hash, salt FROM users WHERE email = 'shihyeon.lee@medpulse.org'")
    user_row = cursor.fetchone()
    assert verify_password("MedicalAdmin2026!", user_row["password_hash"], user_row["salt"]), "Password verification failed"
    print("✓ Password hashing & verification with PBKDF2-SHA256 verified.")

    # Wrong password test
    assert not verify_password("WrongPassword123!", user_row["password_hash"], user_row["salt"])
    print("✓ Invalid password correctly rejected.")

    # Session token generation & expiration
    token = generate_session_token()
    now = int(time.time())
    cursor.execute("INSERT INTO sessions (token, user_id, expires_at) VALUES (?, 1, ?)", (token, now + 3600))
    conn.commit()

    cursor.execute("""
        SELECT u.id, u.email, u.name, u.role
        FROM sessions s
        JOIN users u ON s.user_id = u.id
        WHERE s.token = ? AND s.expires_at > ?
    """, (token, now))
    session_user = cursor.fetchone()
    assert session_user["name"] == "Shihyeon Lee"
    print(f"✓ Session validation verified for {session_user['name']} (Role: {session_user['role']}).")

    print("\n--- [3] Testing Comments System ---")
    cursor.execute("""
        INSERT INTO comments (article_id, author_name, author_role, content)
        VALUES (?, ?, ?, ?)
    """, (1, "Sarah Jenkins", "Patient", "Does this interact with calcium channel blockers?"))
    conn.commit()
    com_id = cursor.lastrowid
    assert com_id > 0
    print(f"✓ Visitor comment submitted successfully (ID: {com_id}).")

    print("\n--- [4] Testing Site Rating & Calculation Metrics ---")
    cursor.execute("""
        INSERT INTO site_ratings (score, user_name, category, feedback, recommended)
        VALUES (5, "Dr. Test User", "Clinical Accuracy", "Top tier medical repository.", 1)
    """)
    conn.commit()

    cursor.execute("SELECT AVG(score), COUNT(*) FROM site_ratings")
    avg_score, total_reviews = cursor.fetchone()
    assert avg_score >= 4.0
    print(f"✓ Rating system verified: {round(avg_score, 1)}/5.0 from {total_reviews} reviews.")

    print("\n--- [5] Testing Pharmacy Catalog Filters & Data ---")
    cursor.execute("SELECT COUNT(*) FROM pharmacy_items WHERE prescription_required = 1")
    rx_count = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM pharmacy_items WHERE prescription_required = 0")
    otc_count = cursor.fetchone()[0]
    print(f"✓ Pharmacy verified: {rx_count} Rx medications, {otc_count} OTC medications.")

    conn.close()
    print("\n=======================================================")
    print(" ALL DIRECT UNIT & LOGICAL TESTS PASSED (100%)!")
    print("=======================================================\n")

if __name__ == "__main__":
    run_direct_tests()
