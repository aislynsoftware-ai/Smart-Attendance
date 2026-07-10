# Smart Attendance System — Complete Workflow

## Architecture Overview

```
Frontend (React + Vite)         Pi Device (Raspberry Pi)
       │                                │
       │ JWT Token Auth                 │ Device Auth (X-Device-ID + X-API-Key)
       │                                │
       ▼                                ▼
┌──────────────────────────────────────────────┐
│           Backend (FastAPI + MySQL)            │
│  - JWT Auth for dashboard endpoints           │
│  - Device Auth for Pi endpoints               │
│  - In-memory command queue for enrollment     │
└──────────────────────────────────────────────┘
```

---

## Step-by-Step Workflow

### Step 1: Setup & Configuration

**Backend:**
1. Set up MySQL database with credentials in `backend/.env`
2. Start backend: `uvicorn app.main:app --host 0.0.0.0 --port 8000`
3. Tables auto-create on first run (employees, users, devices, offices, attendance, leaves)

**Frontend:**
1. Set `VITE_API_BASE_URL` in `frontend/.env` to your backend URL
2. Run: `npm run dev` (starts on port 5173)

**Pi Device (Raspberry Pi):**
1. In `Picode/server.py`: Set `API_URL`, `DEVICE_ID`, `DEVICE_API_KEY`
2. In `Picode/register.py`: Set `API_URL`, `DEVICE_ID`, `DEVICE_API_KEY`
3. Run attendance terminal: `python server.py`
4. Run enrollment terminal: `python register.py`

---

### Step 2: Register a Device

1. **Admin logs in** to the dashboard (`/login`) using admin credentials
2. **Creates an Office** via `/app/offices`
3. **Registers the Pi device** via `/app/devices` — backend generates a unique `api_key`
4. Copy the `device_id` and `api_key` into `Picode/server.py` and `Picode/register.py`

---

### Step 3: Create Employees & Enroll Biometrics

There are two ways to enroll employees:

#### Method A: Via Dashboard (Admin Panel)

1. Admin goes to `/app/employees` in the frontend
2. Fills employee details (name, ID, position, office, etc.) and clicks **Save Employee**
3. After saving, biometric section appears showing:
   - **RFID** — click "Tap RFID Card"
   - **Fingerprint 1-4** — click each finger button
   - **Face 1-5** — click each face capture button
4. When a button is clicked, the frontend sends a command via:
   ```
   POST /hardware/command  (JWT Auth) → stores command in memory {emp_id, command, index}
   ```
5. The Pi enrollment terminal (`register.py`) polls:
   ```
   GET /hardware/pending-command  (Device Auth) → reads pending command
   ```
6. Pi detects the command, runs the appropriate sensor (RFID/Fingerprint/Camera)
7. Pi uploads captured data via:
   ```
   POST /hardware/upload  (Device Auth) → saves to MySQL, resets command to 0
   ```
8. Frontend polls `GET /hardware/command` (JWT Auth) and sees `command=0` → shows success

#### Method B: Directly via Pi Enrollment Terminal

1. Run `python Picode/register.py` on the Pi
2. The Pygame UI shows a list of employees fetched from:
   ```
   GET /hardware/employees-pending  (Device Auth)
   ```
3. Select an employee → scan RFID → scan 5 fingerprints → capture 5 face images
4. Click **FINISH & SYNC** → saves locally to SQLite and uploads to server:
   ```
   PUT /hardware/assign-biometric  (Device Auth)
   ```
5. Background thread syncs any offline enrollments every 30 seconds

---

### Step 4: Daily Attendance (Pi Terminal)

1. Run `python Picode/server.py` on the Pi at the office entrance
2. Terminal shows menu:
   ```
   1. RFID Tap
   2. Fingerprint Scan
   3. Face Recognition
   4. Exit
   ```
3. **RFID**: User taps card → Pi reads UID → checks local SQLite cache → if found, marks attendance locally and opens door relay (GPIO 17 for 5s) → sends to server:
   ```
   POST /hardware/verify-and-record  (Device Auth)
   ```
4. **Fingerprint**: User places finger → sensor matches against enrolled templates → same flow as RFID
5. **Face**: User looks at camera → Pi captures frame → compares against known face encodings → same flow

**Attendance Logic (in `POST /hardware/verify-and-record`):**
| Count today | Action |
|-------------|--------|
| 0 | CHECK_IN — first arrival |
| 1-4 | ACCESS — door opens |
| 5 | CHECK_OUT — departure |
| 6 | ACCESS — re-entry |
| 7+ | Denied — daily limit reached |

---

### Step 5: Offline Mode

If the Pi loses internet:
1. Attendance is saved immediately to **local SQLite** (`office_system.db`)
2. Door still opens (GPIO relay runs regardless)
3. Background sync worker retries every 30 seconds:
   ```
   POST /hardware/sync-attendance  (Device Auth)
   ```
4. Once online, all queued records sync automatically

---

### Step 6: Reports & Management (Dashboard)

| Feature | Endpoint | Auth |
|---------|----------|------|
| Attendance by date | `GET /attendance/by-date/{date}` | JWT |
| Attendance by employee | `GET /attendance/by-employee/{emp_id}` | JWT |
| Daily summary | `GET /reports/daily-summary` | JWT |
| Monthly report | `GET /reports/monthly` | JWT |
| Export CSV | `GET /reports/export-csv` | JWT |
| Export PDF | `GET /reports/export-pdf` | JWT |
| Employee management | `GET/POST/PUT /employees` | JWT (Admin/HR) |
| Leave management | `POST /leaves/apply`, `PUT /leaves/{id}/approve` | JWT |

---

## Auth Summary

| Who | Auth Method | How |
|-----|-------------|-----|
| **Frontend user** | JWT Bearer token | Login → get token → stored in localStorage → sent via axios interceptor |
| **Pi Device** | Device API Key | `X-Device-ID` + `X-API-Key` headers in every request |

**Which endpoints use which auth:**

| Endpoints | Auth |
|-----------|------|
| `/users/*`, `/employees/*`, `/attendance/*`, `/offices/*`, `/devices/*`, `/leaves/*`, `/reports/*`, `/biometrics/*` | JWT |
| `POST /hardware/command`, `GET /hardware/command`, `POST /hardware/reset`, `GET /hardware/face-preview/*` | JWT |
| `GET /hardware/pending-command`, `POST /hardware/upload`, `POST /hardware/verify-and-record`, `POST /hardware/sync-attendance`, `PUT /hardware/assign-biometric`, `GET /hardware/employees-pending` | Device Auth |
| `GET /hardware/download/employees-csv` | Query params (`device_id` + `api_key`) |

---

## File Structure

```
backend/app/
├── main.py                 # FastAPI entry, CORS, error handler
├── config.py               # Env vars (DB, JWT)
├── database.py             # SQLAlchemy engine + session
├── core/
│   ├── auth.py             # JWT create/verify, get_current_user, require_role
│   └── security.py         # Password hashing
├── models/                 # SQLAlchemy models
├── schemas/                # Pydantic schemas
├── routes/                 # API route handlers
└── services/               # Business logic

frontend/src/
├── api/client.js           # Axios with JWT interceptor
├── auth/AuthContext.jsx    # Login/logout/token context
├── features/               # Page components
└── routes/                 # Protected route wrappers

Picode/
├── server.py               # Attendance terminal (RFID/Finger/Face + door relay)
├── register.py             # Enrollment terminal (Pygame UI)
├── New.py                  # Dev variant of register.py
└── office_system.db        # Local SQLite cache
```

---

## Quick Start

```bash
# 1. Start Backend
cd backend
pip install -r requirements.txt
uvicorn app.main:app --reload

# 2. Start Frontend
cd frontend
npm install
npm run dev

# 3. On Pi - Attendance Terminal
python Picode/server.py

# 4. On Pi - Enrollment Terminal
python Picode/register.py
```
