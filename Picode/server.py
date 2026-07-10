import requests
import time
import cv2
import base64
import sqlite3
import threading
import json
import numpy as np
from picamera2 import Picamera2
from mfrc522 import SimpleMFRC522
from pyfingerprint.pyfingerprint import PyFingerprint
import face_recognition
import RPi.GPIO as GPIO

RELAY_PIN = 17

GPIO.setmode(GPIO.BCM)
GPIO.setup(RELAY_PIN, GPIO.OUT)
GPIO.output(RELAY_PIN, GPIO.LOW)


# -----------------------------
# CONFIG
# -----------------------------
API_URL = "https://aislyntech-attendance.hf.space"
VERIFY_ENDPOINT = f"{API_URL}/hardware/verify-and-record"
SYNC_ENDPOINT = f"{API_URL}/hardware/sync-attendance"
DEVICE_ID = "Aislyn001"
DEVICE_API_KEY = ""
DB_NAME = "smart_attendance.db"


def device_headers():
    return {"X-Device-ID": DEVICE_ID, "X-API-Key": DEVICE_API_KEY}



def open_door():
    try:
        print(">>> Door Relay ON")
        GPIO.output(RELAY_PIN, GPIO.HIGH)
        time.sleep(5)  # Door open time
        GPIO.output(RELAY_PIN, GPIO.LOW)
        print(">>> Door Relay OFF")
    except Exception as e:
        print("Relay Error:", e)
        
        
# -----------------------------
# DATABASE & SYNC LOGIC
# -----------------------------
def init_local_storage():
    """Ensures we have a table for offline logs"""
    conn = sqlite3.connect(DB_NAME)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS attendance_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            emp_id TEXT,
            date TEXT,
            time TEXT,
            type TEXT,
            synced INTEGER DEFAULT 0
        )
    """)
    conn.commit()
    conn.close()


def sync_worker():
    """Background thread: Pushes offline records to server when online"""
    while True:
        try:
            conn = sqlite3.connect(DB_NAME)
            conn.row_factory = sqlite3.Row
            unsynced = conn.execute("SELECT * FROM attendance_logs WHERE synced = 0").fetchall()
            
            if unsynced:
                records = []
                for r in unsynced:
                    records.append({
                        "emp_id": r["emp_id"],
                        "date": r["date"],
                        "check_in": r["time"],
                        "source": r["type"]
                    })
                
                payload = {"device_id": DEVICE_ID, "records": records}
                response = requests.post(SYNC_ENDPOINT, json=payload, headers=device_headers(), timeout=10)
                
                if response.status_code == 200:
                    conn.execute("UPDATE attendance_logs SET synced = 1 WHERE synced = 0")
                    conn.commit()
                    print(f">>> [SYNC] Successfully uploaded {len(records)} offline records.")
            conn.close()
        except Exception:
            pass 
        time.sleep(30)


# -----------------------------
# ATTENDANCE RECORDING (Local + Online)
# -----------------------------
def record_attendance(emp_id, emp_name, bio_type, identifier=None):
    """Saves to local DB first, then attempts real-time server call"""
    curr_date = time.strftime('%Y-%m-%d')
    curr_time = time.strftime('%H:%M:%S')

    # 1. Immediate Local Save
    try:
        conn = sqlite3.connect(DB_NAME)
        conn.execute("INSERT INTO attendance_logs (emp_id, date, time, type, synced) VALUES (?,?,?,?,0)",
                     (emp_id, curr_date, curr_time, bio_type))
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"Local DB Error: {e}")

    print("\n" + "="*30)
    print(f"USER    : {emp_name}")
    print(f"TIME    : {curr_time}")
    print(f"TYPE    : {bio_type}")
   # print(">>> [SIGNAL] DOOR OPENED SUCCESSFULLY!")
    print("="*30)
    open_door()

    # 2. Immediate Server Attempt (Real-time)
    payload = {
        "identifier": identifier if identifier else emp_id,
        "type": bio_type.lower(),
        "device_id": DEVICE_ID
    }
    
    try:
        res = requests.post(VERIFY_ENDPOINT, json=payload, headers=device_headers(), timeout=5)
        if res.status_code == 200:
            conn = sqlite3.connect(DB_NAME)
            conn.execute("UPDATE attendance_logs SET synced = 1 WHERE emp_id = ? AND time = ?", (emp_id, curr_time))
            conn.commit()
            conn.close()
            print(">>> [ONLINE] Server updated in real-time.")
    except:
        print(">>> [OFFLINE] Server unreachable. Log saved locally.")
        

# -----------------------------
# RFID MODE
# -----------------------------
def run_rfid():
    reader = SimpleMFRC522()
    print("\n[RFID] Tap your card now...")
    try:
        uid, _ = reader.read()
        uid_str = str(uid)
        print(f"UID Detected: {uid_str}")

        conn = sqlite3.connect(DB_NAME)
        user = conn.execute("SELECT emp_id, name FROM employees WHERE rfid = ?", (uid_str,)).fetchone()
        conn.close()

        if user:
            record_attendance(user[0], user[1], "RFID", identifier=uid_str)
        else:
            print(">>> User Not Found Locally. Attempting Server Check...")
            # Fallback to direct server call if local DB doesn't have it
            call_server_fallback(uid_str, "rfid")
            
    except Exception as e:
        print(f"RFID Sensor Error: {e}")


# -----------------------------
# FINGERPRINT MODE
# -----------------------------
def run_fingerprint():
    print("\n[FINGER] Place finger on sensor...")
    try:
        f = PyFingerprint('/dev/serial0', 57600, 0xFFFFFFFF, 0x00000000)
        if not f.verifyPassword():
            print("Sensor password error")
            return

        while not f.readImage():
            time.sleep(0.1)

        f.convertImage(0x01)
        result = f.searchTemplate()
        position = result[0]

        if position == -1:
            print(">>> Finger not recognized")
            return

        print(">>> Matched slot:", position)

        conn = sqlite3.connect(DB_NAME)
        # Check all finger columns stored by your app.py
        user = conn.execute("""SELECT emp_id, name FROM employees 
                               WHERE fingerprint1=? OR fingerprint2=? OR fingerprint3=? 
                               OR fingerprint4=? OR fingerprint5=?""", 
                            (position, position, position, position, position)).fetchone()
        conn.close()

        if user:
            record_attendance(user[0], user[1], "FINGERPRINT", identifier=str(position))
            
        else:
            print(">>> Finger recognized but not found in Local DB. Checking Server...")
            call_server_fallback(int(position), "fingerprint")

    except Exception as e:
        print("Fingerprint Error:", e)


# Face mode 

def run_face():

    print("\n[FACE] Camera starting... Please look at the camera.")

    picam2 = Picamera2()
    config = picam2.create_preview_configuration(
        main={"size": (640, 480), "format": "XBGR8888"}
    )

    picam2.configure(config)
    picam2.start()

    # -----------------------------
    # LOAD FACE DATABASE
    # -----------------------------
    known_encodings = []
    known_names = []
    known_ids = []

    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row

    rows = conn.execute("""
        SELECT emp_id,name,face1,face2,face3,face4,face5
        FROM employees
    """).fetchall()

    conn.close()

    for row in rows:
        for i in range(1,6):
            if row[f"face{i}"]:
                known_encodings.append(
                    np.array(json.loads(row[f"face{i}"]))
                )
                known_names.append(row["name"])
                known_ids.append(row["emp_id"])

    print("Loaded faces:", len(known_encodings))

    face_detect_time = None
    hold_time = 2 

    try:

        while True:

            frame = picam2.capture_array()
            frame_bgr = cv2.cvtColor(frame, cv2.COLOR_RGBA2BGR)

            small = cv2.resize(frame_bgr, (0,0), fx=0.5, fy=0.5)
            rgb_small = cv2.cvtColor(small, cv2.COLOR_BGR2RGB)

            face_locations = face_recognition.face_locations(rgb_small)
            face_encodings = face_recognition.face_encodings(rgb_small, face_locations)

            if len(face_encodings) > 0:

                if face_detect_time is None:
                    face_detect_time = time.time()

                elapsed = time.time() - face_detect_time

                cv2.putText(frame_bgr,
                            f"Hold Still {int(hold_time - elapsed) if elapsed < hold_time else 0}",
                            (20,40),
                            cv2.FONT_HERSHEY_SIMPLEX,
                            1,
                            (0,255,0),
                            2)

                if elapsed >= hold_time:

                    face_encoding = face_encodings[0]

                    matches = face_recognition.compare_faces(
                        known_encodings,
                        face_encoding,
                        tolerance=0.45
                    )

                    if True in matches:

                        index = matches.index(True)

                        emp_id = known_ids[index]
                        name = known_names[index]

                        _, buffer = cv2.imencode(".jpg", frame_bgr)
                        img_base64 = base64.b64encode(buffer).decode()
                        record_attendance(emp_id, name, "FACE", identifier=img_base64)

                        picam2.stop()
                        picam2.close()
                        cv2.destroyAllWindows()

                        return

                    else:
                        print(">>> Face not recognized")

            else:
                face_detect_time = None

            cv2.imshow("Face Recognition", frame_bgr)

            if cv2.waitKey(1) & 0xFF == ord("q"):
                break

    except Exception as e:
        print("Camera Error:", e)

    finally:
        picam2.stop()
        picam2.close()
        cv2.destroyAllWindows()
        

# -----------------------------
# SERVER FALLBACK (For Unknown IDs/Face)
# -----------------------------
def call_server_fallback(identifier, bio_type):
    """Old server logic maintained for face recognition or unknown IDs"""
    payload = {"identifier": identifier, "type": bio_type, "device_id": DEVICE_ID}
    try:
        response = requests.post(VERIFY_ENDPOINT, json=payload, headers=device_headers(), timeout=10)
        if response.status_code == 200:
            data = response.json()
            print(data)
            print(f">>> Server Confirmed: {data.get('name')}")
            return True
        else:
            print(f">>> Server could not verify: {response.status_code}")
    except:
        print(">>> Server Offline and User not in Local Cache.")
    return False

# -----------------------------
# MAIN LOOP
# -----------------------------
def main():
    init_local_storage()
    # Start the sync worker in the background
    threading.Thread(target=sync_worker, daemon=True).start()

    while True:
       
       
       
        print("1. RFID Tap")
        print("2. Fingerprint Scan")
        print("3. Face Recognition")
        print("4. Exit")

        choice = input("\nSelect Option: ")

        if choice == '1': run_rfid()
        elif choice == '2': run_fingerprint()
        elif choice == '3': run_face()
        elif choice == '4':
            print("Shutting down terminal...")
            break
        
        else:
            print("Invalid Option.")
        
        time.sleep(1)

if __name__ == "__main__":
    try:
        main()
    finally:
        GPIO.cleanup()
