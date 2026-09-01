"""
Automated Test for MedPulse Editor & User Management System
"""
import urllib.request
import urllib.error
import json
import time

BASE_URL = "http://localhost:8000/api"

def api_request(path, method="GET", data=None, token=None):
    url = f"{BASE_URL}{path}"
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    body = json.dumps(data).encode("utf-8") if data else None
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode("utf-8"))

def run_tests():
    print("🧪 Running User Management & Role Assignment Tests...")

    # 1. Login as Admin (Admin Full 1)
    status, res = api_request("/auth/login", "POST", {
        "email": "admin.full1@medpulse.org",
        "password": "MedicalAdmin2026!"
    })
    assert status == 200, f"Admin login failed: {res}"
    admin_token = res["token"]
    admin_id = res["user"]["id"]
    print("✅ 1. Admin login successful")

    # 2. Login as a non-admin scoped editor (Jay Cho)
    status, res = api_request("/auth/login", "POST", {
        "email": "jay.cho@medpulse.org",
        "password": "DoctorSarah2026!"
    })
    assert status == 200, f"Editor login failed: {res}"
    editor_token = res["token"]
    print("✅ 2. Editor login successful")

    # 3. GET /api/users (Public/Staff can see editorial directory)
    status, res = api_request("/users")
    assert status == 200, f"GET /api/users failed: {res}"
    assert len(res["users"]) >= 2, "Expected at least 2 seeded staff members"
    print(f"✅ 3. Fetched {len(res['users'])} existing staff members")

    # 4. Non-admin editor tries to assign a new editor (Should be rejected with 403)
    status, res = api_request("/users", "POST", {
        "name": "Dr. John Watson",
        "email": "watson@medpulse.org",
        "password": "WatsonPassword2026!",
        "role": "editor",
        "title": "Clinical General Practitioner"
    }, token=editor_token)
    assert status == 403, f"Expected 403 Forbidden for editor assigning user, got {status}: {res}"
    print("✅ 4. Non-admin editor successfully blocked from assigning users (403 Forbidden)")

    # 5. Admin assigns a new doctor / clinical editor
    new_email = f"watson_{int(time.time())}@medpulse.org"
    status, res = api_request("/users", "POST", {
        "name": "Dr. John Watson, MD",
        "email": new_email,
        "password": "WatsonPassword2026!",
        "role": "editor",
        "title": "Senior Clinical Diagnostician",
        "avatar": "https://images.unsplash.com/photo-1622253692010-333f2da6031d?auto=format&fit=crop&q=80&w=300"
    }, token=admin_token)
    assert status == 201, f"Admin assign user failed: {res}"
    new_user_id = res["user"]["id"]
    print(f"✅ 5. Admin successfully assigned new editor: {res['user']['name']} (ID: {new_user_id})")

    # 6. Verify newly assigned editor can log in and publish an article
    status, res = api_request("/auth/login", "POST", {
        "email": new_email,
        "password": "WatsonPassword2026!"
    })
    assert status == 200, f"New editor login failed: {res}"
    watson_token = res["token"]

    status, res = api_request("/articles", "POST", {
        "title": f"Diagnostic Methods in Primary Care {int(time.time())}",
        "category": "General Health",
        "summary": "Clinical diagnostic approaches for differential diagnosis.",
        "content": "### Introduction\n\nComprehensive diagnostic assessment...",
        "reading_time": "4 min read",
        "tags": ["Diagnostics", "Primary Care"]
    }, token=watson_token)
    assert status == 201, f"New editor failed to publish article: {res}"
    print("✅ 6. Newly assigned editor logged in and successfully published a medical article")

    # 7. Admin updates newly created user's title and role
    status, res = api_request(f"/users/{new_user_id}", "PUT", {
        "title": "Lead Clinical Diagnostician & Senior Editor",
        "role": "editor"
    }, token=admin_token)
    assert status == 200, f"Admin update user failed: {res}"
    print("✅ 7. Admin successfully updated editor details")

    # 8. Admin attempts self-deletion (Should be blocked with 400)
    status, res = api_request(f"/users/{admin_id}", "DELETE", token=admin_token)
    assert status == 400, f"Self-deletion should be blocked, got {status}: {res}"
    print("✅ 8. Admin self-deletion successfully prevented")

    # 9. Admin revokes/deletes the test editor
    status, res = api_request(f"/users/{new_user_id}", "DELETE", token=admin_token)
    assert status == 200, f"Admin delete user failed: {res}"
    print("✅ 9. Admin successfully revoked editor access")

    # 10. Verify revoked editor cannot log in anymore
    status, res = api_request("/auth/login", "POST", {
        "email": new_email,
        "password": "WatsonPassword2026!"
    })
    assert status == 401, f"Revoked editor login should fail with 401, got {status}"
    print("✅ 10. Revoked editor successfully blocked from logging in")

    print("\n🎉 ALL USER MANAGEMENT API TESTS PASSED SUCCESSFULLY!")

if __name__ == "__main__":
    run_tests()
