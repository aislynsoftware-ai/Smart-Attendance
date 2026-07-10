import pygame
import sqlite3
import requests
import threading
import cv2
import base64
import time
import numpy as np
import json
import face_recognition

from picamera2 import Picamera2
from mfrc522 import SimpleMFRC522
from pyfingerprint.pyfingerprint import PyFingerprint

print(">>> Enrollment Terminal Started")

# -----------------------------
# CONFIG
# -----------------------------
DB_NAME = "smart_attendance.db"
API_URL = "https://aislyntech-attendance.hf.space"
DEVICE_ID = "Aislyn001"
DEVICE_API_KEY = ""


def device_headers():
    return {"X-Device-ID": DEVICE_ID, "X-API-Key": DEVICE_API_KEY}

WIDTH, HEIGHT = 480, 800
FPS = 60

CLR_BG = (15,23,42)
CLR_CARD = (30,41,59)
CLR_ACCENT = (56,189,248)
CLR_TEXT = (248,250,252)
CLR_SUCCESS = (34,197,94)
CLR_HOVER = (51,65,85)

# -----------------------------
# GLOBAL STATE
# -----------------------------
all_employees = []
current_emp = None
rfid_data = None
finger_data = []
face_data = []
status_msg = "Ready"
show_dropdown = False
picam2 = None

# -----------------------------
# SQLITE INIT
# -----------------------------
def init_db():
    print(">>> Initializing SQLite")
    conn = sqlite3.connect(DB_NAME)
    # Added 'synced' column to track server status
    conn.execute("""
    CREATE TABLE IF NOT EXISTS employees (
        emp_id TEXT PRIMARY KEY,
        name TEXT,
        rfid TEXT,
        fingerprint1 TEXT, fingerprint2 TEXT, fingerprint3 TEXT, fingerprint4 TEXT, fingerprint5 TEXT,
        face1 TEXT, face2 TEXT, face3 TEXT, face4 TEXT, face5 TEXT,
        synced INTEGER DEFAULT 0
    )
    """)
    conn.commit()
    conn.close()

# -----------------------------
# BACKGROUND SYNC WORKER
# -----------------------------
def sync_pending_records():
    """Background task to push offline enrollments to server"""
    while True:
        try:
            conn = sqlite3.connect(DB_NAME)
            conn.row_factory = sqlite3.Row
            pending = conn.execute("SELECT * FROM employees WHERE synced = 0 AND rfid IS NOT NULL").fetchall()
            
            for row in pending:
                payload = {
                    "emp_id": row["emp_id"],
                    "rfid": row["rfid"],
                    "fingerprints": [row[f"fingerprint{i}"] for i in range(1,6) if row[f"fingerprint{i}"]],
                    "faces": [row[f"face{i}"] for i in range(1,6) if row[f"face{i}"]]
                }
                
                res = requests.put(f"{API_URL}/hardware/assign-biometric", json=payload, headers=device_headers(), timeout=5)
                if res.status_code == 200:
                    conn.execute("UPDATE employees SET synced = 1 WHERE emp_id = ?", (row["emp_id"],))
                    conn.commit()
                    print(f">>> Background Sync Success for {row['emp_id']}")
            
            conn.close()
        except Exception as e:
            pass # Silent fail to keep thread alive
        time.sleep(30) 

# -----------------------------
# FETCH EMPLOYEES
# -----------------------------
def fetch_employees_worker():
    global all_employees, status_msg
    print(">>> Fetching employees from server")
    try:
        res = requests.get(f"{API_URL}/hardware/employees-pending", headers=device_headers(), timeout=5)
        if res.status_code == 200:
            all_employees = res.json()
            # Insert/Update local list so we can work offline next time
            conn = sqlite3.connect(DB_NAME)
            for emp in all_employees:
                conn.execute("INSERT OR IGNORE INTO employees (emp_id, name) VALUES (?,?)", 
                             (emp["emp_id"], emp["name"]))
            conn.commit()
            conn.close()
            status_msg = "Employees Loaded"
        else:
            status_msg = "API Error - Using Local"
    except Exception as e:
        status_msg = "Server Offline - Local Mode"

# -----------------------------
# RFID
# -----------------------------
def hw_rfid():
    global rfid_data, status_msg
    try:
        status_msg = "Waiting for RFID..."
        reader = SimpleMFRC522()
        uid, _ = reader.read()
        rfid_data = str(uid)
        status_msg = "RFID Captured"
    except Exception as e:
        status_msg = "RFID Error"

# -----------------------------
# FINGERPRINT (With Retry Logic)
# -----------------------------
def hw_finger():
    global finger_data, status_msg
    finger_data = []
    stored_slots = []

    try:
        f = PyFingerprint('/dev/serial0', 57600, 0xFFFFFFFF, 0x00000000)

        if not f.verifyPassword():
            raise ValueError("Sensor Password Error")

        i = 0

        while i < 5:
            try:

                status_msg = f"Enroll Finger {i+1}/5"

                # first scan
                while not f.readImage():
                    pass

                f.convertImage(0x01)

                status_msg = "Remove Finger..."
                time.sleep(1.5)

                # second scan
                status_msg = "Place Same Finger Again"

                while not f.readImage():
                    pass

                f.convertImage(0x02)

                if f.compareCharacteristics() == 0:
                    raise Exception("Fingerprint mismatch")

                f.createTemplate()

                position = f.storeTemplate()

                stored_slots.append(position)
                finger_data.append(position)

                print("Stored slot:", position)

                i += 1
                status_msg = f"Finger {i}/5 Saved"

                time.sleep(1)

            except Exception as e:

                print(">>> Enrollment error:", e)
                status_msg = "Restarting Enrollment..."

                # delete stored templates
                for slot in stored_slots:
                    try:
                        f.deleteTemplate(slot)
                        print("Deleted slot:", slot)
                    except:
                        pass

                stored_slots = []
                finger_data = []
                i = 0

                time.sleep(2)

        status_msg = "Finger Enrollment Done"

    except Exception as e:
        print(e)
        status_msg = "Finger Sensor Error"
# -----------------------------
# FACE
# -----------------------------
def hw_face():
    global face_data, status_msg, picam2
    face_data = []
    try:
        if picam2 is None: picam2 = Picamera2()
        config = picam2.create_preview_configuration(main={"size":(640,480),"format":"XBGR8888"})
        picam2.configure(config)
        picam2.start()

        win = "Capture Face - 'W' to save"
        while len(face_data) < 5:
            status_msg = f"Face {len(face_data)}/5"
            frame = picam2.capture_array()
            frame = cv2.cvtColor(frame, cv2.COLOR_RGBA2BGR)
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            cv2.imshow(win, frame)
            
            key = cv2.waitKey(1) & 0xFF
            if key == ord('w'):
                faces = face_recognition.face_locations(rgb)
                if len(faces) > 0:
                    enc = face_recognition.face_encodings(rgb, faces)[0].tolist()
                    face_data.append(json.dumps(enc))
                    time.sleep(0.5)
            elif key == ord('q'): break

        picam2.stop()
        cv2.destroyWindow(win)
        status_msg = "Face Done"
    except Exception as e:
        status_msg = "Camera Error"
        
def load_next_employee():
    global current_emp, rfid_data, finger_data, face_data, status_msg

    if len(all_employees) == 0:
        current_emp = None
        status_msg = "All Employees Registered"
        return

    # remove current employee from list
    all_employees[:] = [e for e in all_employees if e["emp_id"] != current_emp["emp_id"]]

    if len(all_employees) > 0:
        current_emp = all_employees[0]
        rfid_data = None
        finger_data = []
        face_data = []
        status_msg = f"Next Employee: {current_emp['name']}"
    else:
        current_emp = None
        status_msg = "Enrollment Completed"        

# -----------------------------
# SAVE + SYNC (Local First)
# -----------------------------
def save_and_upload():
    global status_msg
    if not current_emp: return

    try:
        status_msg = "Saving Locally..."
        f_pad = (finger_data + [None]*5)[:5]
        fc_pad = (face_data + [None]*5)[:5]

        conn = sqlite3.connect(DB_NAME)
        conn.execute("""UPDATE employees SET rfid=?,
                        fingerprint1=?, fingerprint2=?, fingerprint3=?, fingerprint4=?, fingerprint5=?,
                        face1=?, face2=?, face3=?, face4=?, face5=?, synced=0 
                        WHERE emp_id=?""",
                     (rfid_data, *f_pad, *fc_pad, current_emp["emp_id"]))
        conn.commit()
        conn.close()

        # Immediate Attempt to Upload
        payload = {
            "emp_id": current_emp["emp_id"],
            "rfid": rfid_data,
            "fingerprints": finger_data,
            "faces": face_data
        }

        try:
            res = requests.put(f"{API_URL}/hardware/assign-biometric", json=payload, headers=device_headers(), timeout=5)
            if res.status_code == 200:
                conn = sqlite3.connect(DB_NAME)
                conn.execute("UPDATE employees SET synced=1 WHERE emp_id=?", (current_emp["emp_id"],))
                conn.commit()
                conn.close()
                status_msg = "Cloud Sync Success!"
                load_next_employee()
            else:
                status_msg = "Saved (Server Error)"
        except:
            status_msg = "Saved (Offline)"

    except Exception as e:
        status_msg = "Error Saving!"

# -----------------------------
# MAIN UI LOOP
# -----------------------------
pygame.init()
screen = pygame.display.set_mode((WIDTH, HEIGHT))
pygame.display.set_caption("Biometric Enrollment")
font = pygame.font.SysFont("Arial", 22, True)
clock = pygame.time.Clock()

init_db()
threading.Thread(target=fetch_employees_worker, daemon=True).start()
threading.Thread(target=sync_pending_records, daemon=True).start()

running = True
while running:
    screen.fill(CLR_BG)
    mouse = pygame.mouse.get_pos()
    
    # UI Layout
    select_rect = pygame.Rect(30, 80, 420, 50)
    rfid_btn = pygame.Rect(30, 220, 420, 55)
    finger_btn = pygame.Rect(30, 290, 420, 55)
    face_btn = pygame.Rect(30, 360, 420, 55)
    save_btn = pygame.Rect(30, 430, 420, 65)

    pygame.draw.rect(screen, CLR_CARD, select_rect, border_radius=8)
    name_label = current_emp["name"] if current_emp else "SELECT EMPLOYEE"
    screen.blit(font.render(name_label, True, CLR_ACCENT), (45, 92))
    screen.blit(font.render(status_msg, True, CLR_TEXT), (30, 20))

    if current_emp:
        btns = [(rfid_btn, "SCAN RFID", rfid_data),
                (finger_btn, f"FINGER {len(finger_data)}/5", len(finger_data)>=5),
                (face_btn, f"FACE {len(face_data)}/5", len(face_data)>=5)]
        
        for btn, lbl, val in btns:
            c = CLR_SUCCESS if val else (CLR_HOVER if btn.collidepoint(mouse) else CLR_CARD)
            pygame.draw.rect(screen, c, btn, border_radius=8)
            t = font.render(lbl, True, CLR_TEXT)
            screen.blit(t, (btn.centerx-t.get_width()//2, btn.centery-t.get_height()//2))

        pygame.draw.rect(screen, CLR_ACCENT, save_btn, border_radius=8)
        finish_txt = font.render("FINISH & SYNC", True, CLR_BG)
        screen.blit(finish_txt, (save_btn.centerx-finish_txt.get_width()//2, save_btn.centery-finish_txt.get_height()//2))

    if show_dropdown:
        for i, emp in enumerate(all_employees):
            r = pygame.Rect(30, 130+(i*45), 420, 40)
            pygame.draw.rect(screen, CLR_HOVER if r.collidepoint(mouse) else CLR_CARD, r, border_radius=5)
            screen.blit(font.render(emp["name"], True, CLR_TEXT), (45, 135+(i*45)))

    for event in pygame.event.get():
        if event.type == pygame.QUIT: running = False
        if event.type == pygame.MOUSEBUTTONDOWN:
            if select_rect.collidepoint(mouse): show_dropdown = not show_dropdown
            elif show_dropdown:
                for i, emp in enumerate(all_employees):
                    if pygame.Rect(30, 130+(i*45), 420, 40).collidepoint(mouse):
                        current_emp, show_dropdown = emp, False
                        rfid_data, finger_data, face_data = None, [], []
            elif current_emp:
                if rfid_btn.collidepoint(mouse): threading.Thread(target=hw_rfid, daemon=True).start()
                if finger_btn.collidepoint(mouse): threading.Thread(target=hw_finger, daemon=True).start()
                if face_btn.collidepoint(mouse): threading.Thread(target=hw_face, daemon=True).start()
                if save_btn.collidepoint(mouse): threading.Thread(target=save_and_upload, daemon=True).start()

    pygame.display.flip()
    clock.tick(FPS)

pygame.quit()