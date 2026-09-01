# 🩺 MedPulse | Medical Knowledge Hub & Clinical Pharmacy Portal

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

## 🏗️ Architecture & Technology Stack
- **Backend**: Python 3 standard library (`http.server`, `sqlite3`, `hashlib`, `secrets`) — zero third-party dependencies required.
- **Security**: PBKDF2-HMAC-SHA256 password hashing with salt + bearer session tokens.
- **Database**: SQLite3 (`medpulse.db`) with pre-seeded clinical articles, pharmacy catalog, comments, and reviews.
- **Frontend**: Single Page Application (SPA) using Tailwind CSS, Lucide Icons, Marked.js for markdown rendering, and responsive vanilla JavaScript.
