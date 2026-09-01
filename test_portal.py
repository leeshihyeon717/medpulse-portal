"""
Automated Test Suite for MedPulse Medical & Pharmacy Portal
"""
import urllib.request
import urllib.parse
import json
import threading
import time
import sys
from server import MedPulseHandler, init_db, PORT
import http.server

BASE_URL = f"http://127.0.0.1:8008"

def make_req(path, method="GET", data=None, token=None):
    url = f"{BASE_URL}{path}"
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    
    encoded_data = json.dumps(data).encode("utf-8") if data is not None else None
    req = urllib.request.Request(url, data=encoded_data, headers=headers, method=method)
    
    try:
        with urllib.request.urlopen(req) as resp:
            body = resp.read().decode("utf-8")
            return resp.status, json.loads(body) if body else {}
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8")
        try:
            return e.code, json.loads(body)
        except:
            return e.code, {"error": body}

def run_tests():
    print("\n--- [1] Testing Public API Endpoints ---")
    status, stats = make_req("/api/stats")
    assert status == 200, f"Stats failed: {status}"
    print(f"✓ GET /api/stats returned: {stats}")

    status, articles = make_req("/api/articles")
    assert status == 200 and len(articles["articles"]) > 0, "Articles fetch failed"
    print(f"✓ GET /api/articles returned {articles['count']} articles.")

    status, pharmacy = make_req("/api/pharmacy")
    assert status == 200 and len(pharmacy["medications"]) > 0, "Pharmacy fetch failed"
    print(f"✓ GET /api/pharmacy returned {pharmacy['count']} medications.")

    status, ratings = make_req("/api/ratings")
    assert status == 200 and len(ratings["ratings"]) > 0, "Ratings fetch failed"
    print(f"✓ GET /api/ratings returned avg score {ratings['summary']['average']}/5.0.")

    print("\n--- [2] Testing RBAC Security: Guest Access Rejection on Protected Actions ---")
    # Unauthenticated attempt to create an article
    status, res = make_req("/api/articles", method="POST", data={
        "title": "Hacker Post", "content": "Unauthorized medical post"
    })
    assert status in (401, 403), f"Expected 401/403 for guest article creation, got {status}"
    print(f"✓ Guest POST /api/articles correctly rejected: {status} ({res.get('error')})")

    # Unauthenticated attempt to edit an article
    status, res = make_req("/api/articles/1", method="PUT", data={"title": "Hacked Title", "content": "Fake content"})
    assert status in (401, 403), f"Expected 401/403 for guest article update, got {status}"
    print(f"✓ Guest PUT /api/articles/1 correctly rejected: {status} ({res.get('error')})")

    # Unauthenticated attempt to delete an article
    status, res = make_req("/api/articles/1", method="DELETE")
    assert status in (401, 403), f"Expected 401/403 for guest article deletion, got {status}"
    print(f"✓ Guest DELETE /api/articles/1 correctly rejected: {status} ({res.get('error')})")

    # Unauthenticated attempt to create pharmacy item
    status, res = make_req("/api/pharmacy", method="POST", data={"name": "Fake Drug", "indications": "None"})
    assert status in (401, 403), f"Expected 401/403 for guest pharmacy creation, got {status}"
    print(f"✓ Guest POST /api/pharmacy correctly rejected: {status} ({res.get('error')})")

    print("\n--- [3] Testing Visitor Features (Commenting & Rating) ---")
    # Visitor comment on article
    status, com_res = make_req("/api/comments", method="POST", data={
        "article_id": 1,
        "author_name": "Test Visitor Jane",
        "author_role": "Patient",
        "content": "Is this treatment suitable for patients with mild asthma?"
    })
    assert status == 201 and "comment_id" in com_res, f"Comment failed: {com_res}"
    print(f"✓ Visitor POST /api/comments succeeded: ID {com_res['comment_id']}")

    # Liking the same comment twice from the same visitor must be blocked the second time
    comment_id = com_res["comment_id"]
    status, like_res = make_req(f"/api/comments/{comment_id}/like", method="POST", data={"client_identifier": "test-client-liker"})
    assert status == 200 and like_res.get("success"), f"First like failed: {like_res}"
    status, like_res2 = make_req(f"/api/comments/{comment_id}/like", method="POST", data={"client_identifier": "test-client-liker"})
    assert status == 409, f"Expected 409 for duplicate like, got {status}: {like_res2}"
    print("✓ A visitor cannot like the same comment more than once.")

    # Voting helpful on an article twice from the same visitor must be blocked the second time
    status, vote_res = make_req("/api/articles/1/vote", method="POST", data={"type": "helpful", "client_identifier": "test-client-voter"})
    assert status == 200 and vote_res.get("success"), f"First vote failed: {vote_res}"
    status, vote_res2 = make_req("/api/articles/1/vote", method="POST", data={"type": "helpful", "client_identifier": "test-client-voter"})
    assert status == 409, f"Expected 409 for duplicate article vote, got {status}: {vote_res2}"
    print("✓ A visitor cannot vote helpful on the same article more than once.")

    # Visitor site rating (client_identifier stands in for the browser-local id the frontend generates)
    status, rate_res = make_req("/api/ratings", method="POST", data={
        "score": 5,
        "user_name": "Automated Tester",
        "category": "Clinical Accuracy",
        "feedback": "Outstanding evidence-based medical articles!",
        "recommended": True,
        "client_identifier": "test-client-001"
    })
    assert status == 201 and "rating_id" in rate_res, f"Rating failed: {rate_res}"
    print(f"✓ Visitor POST /api/ratings succeeded: ID {rate_res['rating_id']}")

    # Submitting again with the same client_identifier must update the existing review, not duplicate it
    status, rate_res2 = make_req("/api/ratings", method="POST", data={
        "score": 4,
        "user_name": "Automated Tester",
        "category": "Clinical Accuracy",
        "feedback": "Updating my review after further use.",
        "recommended": True,
        "client_identifier": "test-client-001"
    })
    assert status == 200 and rate_res2.get("rating_id") == rate_res["rating_id"], f"Duplicate review was not blocked/merged: {rate_res2}"
    print("✓ Resubmitting a review from the same visitor updated it in place instead of duplicating it.")

    # Missing score must be rejected instead of silently defaulting
    status, no_score_res = make_req("/api/ratings", method="POST", data={
        "user_name": "No Score Tester",
        "client_identifier": "test-client-002"
    })
    assert status == 400, f"Expected 400 when score is missing, got {status}: {no_score_res}"
    print("✓ Submitting a review with no score selected is correctly rejected (no silent 5-star default).")

    print("\n--- [4] Testing Approved Medical Editor Login & Privileged Actions ---")
    # Login as a Full Administrator, since this test exercises both the article and
    # pharmacy modules (scoped medical_editor/pharmacy_editor accounts can only do one).
    status, login_res = make_req("/api/auth/login", method="POST", data={
        "email": "admin.full1@medpulse.org",
        "password": "MedicalAdmin2026!"
    })
    assert status == 200 and login_res.get("token"), f"Login failed: {login_res}"
    token = login_res["token"]
    user_name = login_res["user"]["name"]
    print(f"✓ Login successful for {user_name}. Token acquired.")

    # Check /api/auth/me
    status, me_res = make_req("/api/auth/me", token=token)
    assert status == 200 and me_res["authenticated"] is True, f"Auth verification failed: {me_res}"
    print(f"✓ GET /api/auth/me verified: {me_res['user']['name']} ({me_res['user']['role']})")

    # Approved Editor: Create New Medical Article
    new_art_payload = {
        "title": "Clinical Neurological Protocol for Acute Migraine",
        "category": "Neurology",
        "specialty_badge": "Neurology",
        "summary": "Evidence-based triage for migraine with aura, acute triptan therapy, and CGRP antagonists.",
        "content": "### Migraine Pathophysiology & Triptan Protocols\n\nMigraine is a neurovascular disorder characterized by trigeminovascular activation...",
        "reading_time": "7 min read",
        "tags": ["Neurology", "Migraine", "Triptans", "CGRP"]
    }
    status, art_create_res = make_req("/api/articles", method="POST", data=new_art_payload, token=token)
    assert status == 201 and "article_id" in art_create_res, f"Article creation failed: {art_create_res}"
    new_art_id = art_create_res["article_id"]
    print(f"✓ Approved Editor POST /api/articles succeeded: Created Article ID {new_art_id}")

    # Approved Editor: Update the Article
    status, art_upd_res = make_req(f"/api/articles/{new_art_id}", method="PUT", data={
        "title": "Clinical Neurological Protocol for Acute Migraine (Updated 2026)",
        "category": "Neurology",
        "specialty_badge": "Neurology",
        "summary": "Updated 2026 clinical guidelines for acute migraine therapy.",
        "content": "### Updated 2026 Protocols\n\nIncluding newly approved CGRP receptor antagonists..."
    }, token=token)
    assert status == 200, f"Article update failed: {art_upd_res}"
    print(f"✓ Approved Editor PUT /api/articles/{new_art_id} succeeded.")

    # Approved Editor: Create Pharmacy Medication
    new_med_payload = {
        "name": "Sumatriptan Succinate",
        "generic_name": "Sumatriptan",
        "category": "Pain & Inflammation",
        "prescription_required": 1,
        "dosage_form": "50mg Oral Tablet",
        "indications": "Acute treatment of migraine attacks with or without aura in adults.",
        "usage_instructions": "Take 1 tablet (50mg) at the onset of migraine. A second dose may be administered after 2 hours if migraine persists (Max 200mg/24hr).",
        "side_effects": "Chest tightness or pressure, tingling sensations, flushing, dizziness.",
        "contraindications": "Ischemic heart disease, coronary artery vasospasm, uncontrolled hypertension.",
        "storage_info": "Store at 20°C to 25°C.",
        "price": 32.50
    }
    status, med_create_res = make_req("/api/pharmacy", method="POST", data=new_med_payload, token=token)
    assert status == 201 and "item_id" in med_create_res, f"Pharmacy creation failed: {med_create_res}"
    new_med_id = med_create_res["item_id"]
    print(f"✓ Approved Editor POST /api/pharmacy succeeded: Created Drug ID {new_med_id}")

    # Approved Editor: Delete the created test items
    status, art_del_res = make_req(f"/api/articles/{new_art_id}", method="DELETE", token=token)
    assert status == 200, f"Article deletion failed: {art_del_res}"
    print(f"✓ Approved Editor DELETE /api/articles/{new_art_id} succeeded.")

    status, med_del_res = make_req(f"/api/pharmacy/{new_med_id}", method="DELETE", token=token)
    assert status == 200, f"Pharmacy deletion failed: {med_del_res}"
    print(f"✓ Approved Editor DELETE /api/pharmacy/{new_med_id} succeeded.")

    print("\n--- [5] Testing Scoped Editor Roles Stay in Their Own Module ---")
    # Shihyeon Lee (medical_editor) may publish articles, but must be rejected from pharmacy
    status, res = make_req("/api/auth/login", method="POST", data={
        "email": "shihyeon.lee@medpulse.org", "password": "MedicalAdmin2026!"
    })
    assert status == 200, f"Medical editor login failed: {res}"
    medical_token = res["token"]

    status, res = make_req("/api/articles", method="POST", data={
        "title": "Scoped Role Test Article", "content": "Content", "summary": "Summary"
    }, token=medical_token)
    assert status == 201, f"Medical editor should be able to create articles, got {status}: {res}"
    scoped_art_id = res["article_id"]
    print("✓ Medical Article Editor can publish articles.")

    status, res = make_req("/api/pharmacy", method="POST", data={
        "name": "Unauthorized Drug", "indications": "None"
    }, token=medical_token)
    assert status == 403, f"Medical editor should be blocked from pharmacy, got {status}: {res}"
    print("✓ Medical Article Editor is correctly blocked from managing pharmacy medications (403).")
    make_req(f"/api/articles/{scoped_art_id}", method="DELETE", token=medical_token)

    # Jay Cho (pharmacy_editor) may manage pharmacy, but must be rejected from articles
    status, res = make_req("/api/auth/login", method="POST", data={
        "email": "jay.cho@medpulse.org", "password": "DoctorSarah2026!"
    })
    assert status == 200, f"Pharmacy editor login failed: {res}"
    pharmacy_token = res["token"]

    status, res = make_req("/api/pharmacy", method="POST", data={
        "name": "Scoped Role Test Drug", "indications": "Testing"
    }, token=pharmacy_token)
    assert status == 201, f"Pharmacy editor should be able to add medications, got {status}: {res}"
    scoped_med_id = res["item_id"]
    print("✓ Medication Editor can manage the pharmacy catalog.")

    status, res = make_req("/api/articles", method="POST", data={
        "title": "Unauthorized Article", "content": "Content", "summary": "Summary"
    }, token=pharmacy_token)
    assert status == 403, f"Pharmacy editor should be blocked from articles, got {status}: {res}"
    print("✓ Medication Editor is correctly blocked from publishing medical articles (403).")
    make_req(f"/api/pharmacy/{scoped_med_id}", method="DELETE", token=pharmacy_token)

    print("\n=======================================================")
    print(" ALL BACKEND, RBAC SECURITY & API TESTS PASSED (100%)!")
    print("=======================================================\n")

if __name__ == "__main__":
    init_db()
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 8008), MedPulseHandler)
    server_thread = threading.Thread(target=server.serve_forever, daemon=True)
    server_thread.start()
    time.sleep(0.5)

    try:
        run_tests()
    finally:
        server.shutdown()
        server.server_close()
