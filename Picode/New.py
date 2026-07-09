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
DB_NAME = "office_system.db"
API_URL = "http://192.168.1.6:8000"

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
    conn = sqlite3.connect(DB_NAME)
    conn.execute("""
    CREATE TABLE IF NOT EXISTS employees (
        emp_id TEXT PRIMARY KEY,
        name TEXT,
        rfid TEXT,
        fingerprint1 TEXT, fingerprint2 TEXT, fingerprint3 TEXT, 
        fingerprint4 TEXT, fingerprint5 TEXT,
        face1 TEXT, face2 TEXT, face3 TEXT, face4 TEXT, face5 TEXT,
        is_synced INTEGER DEFAULT 0
    )
    """)
    conn.commit()
    conn.close()
# -----------------------------
# FETCH EMPLOYEES
# -----------------------------
def fetch_employees_worker():

    global all_employees, status_msg

    print(">>> Fetching employees from server")

    try:

        res = requests.get(
            f"{API_URL}/hardware/employees-pending",
            timeout=5
        )

        print("API STATUS:", res.status_code)

        if res.status_code == 200:

            all_employees = res.json()

            print(">>> Employees:", all_employees)

            status_msg = "Employees Loaded"

        else:
            status_msg = "API Error"

    except Exception as e:

        print("API ERROR:", e)

        status_msg = "Server Offline"

# -----------------------------
# RFID
# -----------------------------
def hw_rfid():

    global rfid_data, status_msg

    try:

        print(">>> Waiting RFID...")

        reader = SimpleMFRC522()

        uid, _ = reader.read()

        rfid_data = str(uid)

        print(">>> RFID Captured:", rfid_data)

        status_msg = "RFID Captured"

    except Exception as e:

        print("RFID ERROR:", e)

        status_msg = "RFID Error"

# -----------------------------
# FINGERPRINT
# -----------------------------
def hw_finger():
    global finger_data, status_msg
    finger_data = []
    try:
        f = PyFingerprint('/dev/serial0', 57600, 0xFFFFFFFF, 0x00000000)
        if not f.verifyPassword(): raise ValueError("Sensor Password Error")

        i = 0
        while i < 5:
            status_msg = f"Enroll Finger {i+1}/5"
            
            # Step 1: First Read
            while not f.readImage(): pass
            f.convertImage(0x01)
            
            status_msg = "Remove & Place Again"
            time.sleep(1.5) # Wait for person to lift finger
            
            # Step 2: Second Read for verification
            while not f.readImage(): pass
            f.convertImage(0x02)

            if f.compareCharacteristics() == 0:
                status_msg = "Mismatch! Try Finger " + str(i+1) + " again"
                time.sleep(1.5)
                continue  # This restarts the loop for the SAME 'i'

            f.createTemplate()
            position = f.storeTemplate()
            finger_data.append(position)
            i += 1  # Move to next finger only if successful
            status_msg = f"Finger {i} Saved"
            time.sleep(1)

        status_msg = "All Fingers Enrolled"
    except Exception as e:
        status_msg = "Finger Error: " + str(e)
# -----------------------------
# FACE
# -----------------------------
def hw_face():

    global face_data, status_msg, picam2

    face_data = []

    try:

        print(">>> Camera start")

        if picam2 is None:
            picam2 = Picamera2()

        config = picam2.create_preview_configuration(
            main={"size":(640,480),"format":"XBGR8888"}
        )

        picam2.configure(config)
        picam2.start()

        win = "Face Capture - Press W"

        while len(face_data) < 5:

            status_msg = f"Face {len(face_data)}/5"

            frame = picam2.capture_array()

            frame = cv2.cvtColor(frame,cv2.COLOR_RGBA2BGR)

            rgb = cv2.cvtColor(frame,cv2.COLOR_BGR2RGB)

            cv2.imshow(win,frame)

            key = cv2.waitKey(1) & 0xFF

            if key == ord('w'):

                print(">>> Detecting face")

                faces = face_recognition.face_locations(rgb)

                if len(faces) == 0:

                    print(">>> No face detected")

                    continue

                encodings = face_recognition.face_encodings(rgb,faces)

                embedding = encodings[0].tolist()

                face_data.append(json.dumps(embedding))

                print(">>> Face embedding stored:",len(face_data))

                time.sleep(1)

            elif key == ord('q'):
                break

        picam2.stop()

        cv2.destroyWindow(win)

        print(">>> Face enrollment done")

        status_msg = "Face Done"

    except Exception as e:

        print("Camera error:",e)

        status_msg = "Camera Error"

# -----------------------------
# SAVE + UPLOAD
# -----------------------------
def save_local():
    global status_msg
    try:
        f_pad = (finger_data + [None]*5)[:5]
        fc_pad = (face_data + [None]*5)[:5]
        
        conn = sqlite3.connect(DB_NAME)
        conn.execute("""UPDATE employees SET rfid=?, 
                        fingerprint1=?, fingerprint2=?, fingerprint3=?, fingerprint4=?, fingerprint5=?,
                        face1=?, face2=?, face3=?, face4=?, face5=?, is_synced=0 
                        WHERE emp_id=?""",
                     (rfid_data, *f_pad, *fc_pad, current_emp["emp_id"]))
        conn.commit()
        conn.close()
        status_msg = "Saved Locally. Syncing..."
        
        # Trigger an immediate sync attempt
        threading.Thread(target=sync_with_server, daemon=True).start()
    except Exception as e:
        status_msg = "Local Save Failed"

def sync_with_server():
    global status_msg
    try:
        conn = sqlite3.connect(DB_NAME)
        # Find all unsynced records
        unsynced = conn.execute("SELECT * FROM employees WHERE is_synced=0").fetchall()
        
        for row in unsynced:
            emp_id = row[0]
            # Map columns back to your API payload format...
            payload = {
                "emp_id": emp_id,
                "rfid": row[2],
                "fingerprints": [row[3], row[4], row[5], row[6], row[7]],
                "faces": [row[8], row[9], row[10], row[11], row[12]]
            }
            
            res = requests.put(f"{API_URL}/hardware/assign-biometric", json=payload, timeout=5)
            if res.status_code == 200:
                conn.execute("UPDATE employees SET is_synced=1 WHERE emp_id=?", (emp_id,))
                conn.commit()
                status_msg = "Cloud Sync Success!"
        
        conn.close()
    except:
        status_msg = "Server Offline - Will retry"

# -----------------------------
# UI START
# -----------------------------
pygame.init()

screen = pygame.display.set_mode((WIDTH,HEIGHT))
pygame.display.set_caption("Employee Enrollment")

font = pygame.font.SysFont("Arial",22,True)

clock = pygame.time.Clock()

init_db()

threading.Thread(target=fetch_employees_worker,daemon=True).start()

running = True



while running:

    screen.fill(CLR_BG)

    mouse = pygame.mouse.get_pos()

    select_rect = pygame.Rect(30,80,420,50)

    rfid_btn = pygame.Rect(30,220,420,55)
    finger_btn = pygame.Rect(30,290,420,55)
    face_btn = pygame.Rect(30,360,420,55)
    save_btn = pygame.Rect(30,430,420,65)

    pygame.draw.rect(screen,CLR_CARD,select_rect,border_radius=8)

    name = current_emp["name"] if current_emp else "SELECT EMPLOYEE"

    screen.blit(font.render(name,True,CLR_ACCENT),(45,92))
    screen.blit(font.render(status_msg,True,CLR_ACCENT),(30,20))

    # -----------------------------
    # DRAW BUTTONS
    # -----------------------------
    if current_emp:

        buttons = [
            (rfid_btn,"SCAN RFID",rfid_data),
            (finger_btn,f"FINGER {len(finger_data)}/5",len(finger_data)>=5),
            (face_btn,f"FACE {len(face_data)}/5",len(face_data)>=5)
        ]

        for btn,label,val in buttons:

            color = CLR_SUCCESS if val else (CLR_HOVER if btn.collidepoint(mouse) else CLR_CARD)

            pygame.draw.rect(screen,color,btn,border_radius=8)

            txt = font.render(label,True,CLR_TEXT)

            screen.blit(txt,(btn.centerx-txt.get_width()//2,btn.centery-txt.get_height()//2))

        pygame.draw.rect(screen,CLR_ACCENT,save_btn,border_radius=8)

        txt = font.render("FINISH & SYNC",True,CLR_BG)

        screen.blit(txt,(save_btn.centerx-txt.get_width()//2,save_btn.centery-txt.get_height()//2))

    # -----------------------------
    # DROPDOWN
    # -----------------------------
    if show_dropdown:

        for i,emp in enumerate(all_employees):

            r = pygame.Rect(30,130+(i*45),420,40)

            pygame.draw.rect(
                screen,
                CLR_HOVER if r.collidepoint(mouse) else CLR_CARD,
                r,
                border_radius=5
            )

            screen.blit(
                font.render(emp["name"],True,CLR_TEXT),
                (45,135+(i*45))
            )

    # -----------------------------
    # EVENTS
    # -----------------------------
    for event in pygame.event.get():

        if event.type == pygame.QUIT:
            running = False

        if event.type == pygame.MOUSEBUTTONDOWN:

            if select_rect.collidepoint(mouse):
                show_dropdown = not show_dropdown

            elif show_dropdown:

                for i,emp in enumerate(all_employees):

                    if pygame.Rect(30,130+(i*45),420,40).collidepoint(mouse):

                        current_emp = emp
                        show_dropdown = False

                        rfid_data = None
                        finger_data = []
                        face_data = []

                        print(">>> Selected Employee:", emp)

            elif current_emp:

                if rfid_btn.collidepoint(mouse):
                    threading.Thread(target=hw_rfid,daemon=True).start()

                if finger_btn.collidepoint(mouse):
                    threading.Thread(target=hw_finger,daemon=True).start()

                if face_btn.collidepoint(mouse):
                    threading.Thread(target=hw_face,daemon=True).start()

                if save_btn.collidepoint(mouse):
                    threading.Thread(target=save_and_upload,daemon=True).start()

    pygame.display.flip()

    clock.tick(FPS)



pygame.quit()
