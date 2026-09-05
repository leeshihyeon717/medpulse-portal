# 🩺 PANHCE | Pennsylvania Non-Physician Health Career Exploration

An evidence-based medical publication and clinical pharmacy web platform designed with strict **Role-Based Access Control (RBAC)** to ensure all medical literature is curated exclusively by approved clinicians, while enabling patients and visitors to read articles, leave comments, and rate the platform.

---

## 🌟 Key Features

### 1. 📖 Medical Article Library
- Rich clinical summaries and patient guides across specialties (**Cardiovascular, Endocrinology, Pediatrics, Immunology, Pharmacology**).
- Full Markdown reading mode with author credentials, specialty badges, reading time estimation, and references.
- Helpfulness rating widget ("Was this clinical guide helpful?").

### 2. 💬 Interactive Community Discussion
- Threaded discussion section beneath every medical article.
- Visitors can ask questions or share health experiences.
- Distinct badges for **Verified Medical Staff** vs **Patients / Visitors**.
- Helpful / Like upvote counter.

### 3. ⭐ Site & Platform Rating System
- Comprehensive 5-star rating widget with category breakdown (*Clinical Accuracy, Usability, Pharmacy Catalog, Overall Experience*).
- Live rating aggregation (average score, star distribution bar charts, recommendation percentage).
- Public community reviews wall.

### 4. 💊 Clinical Pharmacy & Medication Guide
- Searchable drug directory with **Prescription (Rx)** vs **Over-The-Counter (OTC)** distinction.
- Detailed clinical profiles for each drug: *Active Ingredient, Approved Indications, Administration & Dosing, Adverse Effects, Contraindications, Storage, and Pricing*.
- Interactive **Prescription Refill / Consultation Inquiry** simulation.

### 5. 🔐 Strict Role-Based Access Control (RBAC)
- **Visitors / Public Users**: Can freely read articles, browse medications, post comments, like a comment once, and submit one platform review (editable any time by resubmitting). Editing or deleting content is strictly blocked on both UI and REST API.
- **Medical Article Editors**: Can log in to publish, update, and delete medical articles only. The pharmacy catalog is off-limits to this role, both in the UI and on the API.
- **Medication Editors**: Can log in to add, update, and delete pharmacy/medication listings only. The article library is off-limits to this role, both in the UI and on the API.
- **Full Administrators**: Full access to both modules, plus staff management.

### 6. 👥 Assign & Manage Site Editors (Admin Feature)
- **Full Administrators**: Can assign new staff with a specific scoped role (Medical Article Editor, Medication Editor, full Clinical Editor, or Admin) directly from the UI or API (`POST /api/users`), update credentials/role (`PUT /api/users/<id>`), and revoke access (`DELETE /api/users/<id>`).
- **Accredited Editorial Board**: Public directory showcasing verified clinicians curating the portal, with badges reflecting each person's actual access scope.

---

## 👨‍⚕️ Pre-Configured Staff Accounts

12 accounts are seeded on first run, split across three access tiers:

| Name | Role | Email | Password | Access |
| :--- | :--- | :--- | :--- | :--- |
| **Shihyeon Lee** | Medical Article Editor | `shihyeon.lee@medpulse.org` | `MedicalAdmin2026!` | Medical articles only |
| **Admin 1–4 Medical** | Medical Article Editor | `admin1.medical@medpulse.org` … `admin4.medical@medpulse.org` | `MedicalAdmin2026!` | Medical articles only |
| **Jay Cho** | Medication Editor | `jay.cho@medpulse.org` | `DoctorSarah2026!` | Pharmacy/medications only |
| **Admin 1–4 Medicine** | Medication Editor | `admin1.medicine@medpulse.org` … `admin4.medicine@medpulse.org` | `DoctorSarah2026!` | Pharmacy/medications only |
| **Admin Full 1 & 2** | Full Administrator | `admin.full1@medpulse.org`, `admin.full2@medpulse.org` | `MedicalAdmin2026!` | Full access (articles, pharmacy, staff management) |

> *Tip: The login modal contains 1-click buttons to automatically fill in demo credentials for quick testing.*

---

## 🚀 Quick Start Guide

### 1. Start the Server
```bash
cd /Users/shihyeon/.gemini/antigravity/scratch/medpulse-portal
./start.sh
# or run with python directly:
python3 server.py
```

### 2. Open in Your Browser
Open your browser and navigate to:
```
http://localhost:8000
```

---

## ☁️ Deploying So the Site Runs Without Your Mac

Running `server.py` locally only serves the site while your Mac is on. To make it reachable
24/7, deploy it to Render (this repo already includes `render.yaml` and `requirements.txt` for
that - no code changes needed, since `server.py` already binds to all interfaces and reads the
`PORT` environment variable Render provides):

1. Push this repo to GitHub (create an empty repo at github.com/new, then from this folder):
   ```bash
   git remote add origin <your-new-repo-url>
   git push -u origin main
   ```
2. Sign up at [render.com](https://render.com) (free, email only, no card required).
3. **New +** → **Web Service** → connect the GitHub repo you just pushed.
4. Render should auto-detect `render.yaml`. If asked to confirm settings manually: Environment
   = Python, Build Command = `pip install -r requirements.txt`, Start Command =
   `python3 server.py`, Plan = Free.
5. Deploy. Render gives you a permanent `https://<your-service-name>.onrender.com` URL.

**Free-tier tradeoffs to know:**
- Without the Turso setup below, the disk is not persistent - every restart/redeploy re-seeds
  `medpulse.db` back to the 12 default accounts with no articles, medications, comments, or
  reviews.
- The free service spins down after ~15 minutes of no traffic and takes 30-60 seconds to wake
  back up on the next visit (a cold start), rather than responding instantly. This is unrelated
  to the database and happens either way.

### Keeping the Database Across Restarts (Turso)

By default the app stores everything in a local SQLite file, which is wiped on every Render
restart/redeploy as noted above. Setting two environment variables switches it to a free,
permanent, hosted database instead - `database.py` talks to it over Turso's HTTP API using only
the Python standard library, so no dependency install or code change is needed on your end.

1. Sign up at [turso.tech](https://turso.tech) (free, no card required) and create a database
   from their web dashboard.
2. From the database's page, get its **URL** (starts with `libsql://...`) and generate an
   **auth token**.
3. In your Render service → **Environment** tab, add two variables:
   - `TURSO_DATABASE_URL` = the URL from step 2
   - `TURSO_AUTH_TOKEN` = the token from step 2
4. Save - Render redeploys automatically. From then on, every restart/redeploy keeps your data
   (accounts, articles, medications, comments, and reviews) instead of resetting it.

Leaving these two variables unset keeps the app on the local SQLite file exactly as before - so
this is entirely optional and safe to skip or add later.

---

## 🏗️ Architecture & Technology Stack
- **Backend**: Python 3 standard library (`http.server`, `sqlite3`, `hashlib`, `secrets`) — zero third-party dependencies required.
- **Security**: PBKDF2-HMAC-SHA256 password hashing with salt + bearer session tokens.
- **Database**: SQLite3 (`medpulse.db`) with pre-seeded clinical articles, pharmacy catalog, comments, and reviews.
- **Frontend**: Single Page Application (SPA) using Tailwind CSS, Lucide Icons, Marked.js for markdown rendering, and responsive vanilla JavaScript.
