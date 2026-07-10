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

API_URL = "https://aislyntech-attendance.hf.space"
DEVICE_ID = "AT002"
DEVICE_API_KEY = "203e500e05fa0b2b610a5c446f239e2033ec2c3e1ccc5050f320600ad9c60b7e"
DB_NAME = "smart_attendance.db"

finger_lock = threading.Lock()


def device_headers():
    return {"X-Device-ID": DEVICE_ID, "X-API-Key": DEVICE_API_KEY}


def open_door():
    try:
        print(">>> Door Open")
        GPIO.output(RELAY_PIN, GPIO.HIGH)
        time.sleep(5)
        GPIO.output(RELAY_PIN, GPIO.LOW)
        print(">>> Door Close")
    except Exception as e:
        print("Relay Error:", e)


def init_db():
    conn = sqlite3.connect(DB_NAME)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS employees (
            emp_id TEXT PRIMARY KEY,
            name TEXT,
            rfid TEXT,
            fingerprint1 TEXT, fingerprint2 TEXT, fingerprint3 TEXT, fingerprint4 TEXT, fingerprint5 TEXT,
            face1 TEXT, face2 TEXT, face3 TEXT, face4 TEXT, face5 TEXT
        )
    """)
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


def save_attendance_local(emp_id, bio_type):
    conn = sqlite3.connect(DB_NAME)
    conn.execute("INSERT INTO attendance_logs (emp_id, date, time, type, synced) VALUES (?,?,?,?,0)",
                 (emp_id, time.strftime('%Y-%m-%d'), time.strftime('%H:%M:%S'), bio_type))
    conn.commit()
    conn.close()


def mark_attendance(emp_id, name, bio_type):
    save_attendance_local(emp_id, bio_type)
    print(f">>> ATTENDANCE: {name} ({emp_id}) - {bio_type}")
    open_door()
    payload = {"identifier": emp_id, "type": bio_type.lower(), "device_id": DEVICE_ID}
    try:
        res = requests.post(f"{API_URL}/hardware/verify-and-record", json=payload, headers=device_headers(), timeout=5)
        if res.status_code == 200:
            conn = sqlite3.connect(DB_NAME)
            conn.execute("UPDATE attendance_logs SET synced = 1 WHERE emp_id = ? AND time = ?",
                         (emp_id, time.strftime('%H:%M:%S')))
            conn.commit()
            conn.close()
    except Exception:
        pass


def sync_worker():
    while True:
        try:
            conn = sqlite3.connect(DB_NAME)
            conn.row_factory = sqlite3.Row
            unsynced = conn.execute("SELECT * FROM attendance_logs WHERE synced = 0").fetchall()
            if unsynced:
                records = []
                for r in unsynced:
                    records.append({"emp_id": r["emp_id"], "date": r["date"], "check_in": r["time"], "source": r["type"]})
                res = requests.post(f"{API_URL}/hardware/sync-attendance",
                                    json={"device_id": DEVICE_ID, "records": records},
                                    headers=device_headers(), timeout=10)
                if res.status_code == 200:
                    conn.execute("UPDATE attendance_logs SET synced = 1 WHERE synced = 0")
                    conn.commit()
                    print(f">>> [SYNC] Uploaded {len(records)} offline records")
            conn.close()
        except Exception:
            pass
        time.sleep(30)


def download_employees():
    try:
        res = requests.get(f"{API_URL}/hardware/download/employees-csv",
                           params={"device_id": DEVICE_ID, "api_key": DEVICE_API_KEY}, timeout=10)
        if res.status_code == 200:
            lines = res.text.strip().split("\n")
            if len(lines) < 2:
                return
            conn = sqlite3.connect(DB_NAME)
            conn.execute("DELETE FROM employees")
            for line in lines[1:]:
                vals = line.split(",")
                if len(vals) >= 3:
                    conn.execute("""INSERT OR REPLACE INTO employees
                        (emp_id, name, rfid, fingerprint1, fingerprint2, fingerprint3, fingerprint4, fingerprint5,
                         face1, face2, face3, face4, face5)
                        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                                 (vals[1] if len(vals) > 1 else "",
                                  vals[2] if len(vals) > 2 else "",
                                  vals[14] if len(vals) > 14 else "",
                                  vals[15] if len(vals) > 15 else "",
                                  vals[16] if len(vals) > 16 else "",
                                  vals[17] if len(vals) > 17 else "",
                                  vals[18] if len(vals) > 18 else "",
                                  "",
                                  vals[19] if len(vals) > 19 else "",
                                  vals[20] if len(vals) > 20 else "",
                                  vals[21] if len(vals) > 21 else "",
                                  vals[22] if len(vals) > 22 else "",
                                  vals[23] if len(vals) > 23 else ""))
            conn.commit()
            conn.close()
            print(f">>> Downloaded {len(lines)-1} employees")
    except Exception as e:
        print(f">>> Download error: {e}")


# ─────────────────────────────────────────────
# ENROLLMENT (Dashboard Command)
# ─────────────────────────────────────────────
def enroll_rfid(emp_id):
    print(f"[ENROLL RFID] {emp_id} - Tap card...")
    reader = SimpleMFRC522()
    uid, _ = reader.read()
    uid_str = str(uid)
    requests.post(f"{API_URL}/hardware/upload",
                  json={"emp_id": emp_id, "type": "rfid", "data": uid_str},
                  headers=device_headers(), timeout=10)
    print(f">>> RFID Enrolled: {uid_str}")


def enroll_finger(emp_id, index):
    with finger_lock:
        print(f"\n[ENROLL FINGER {index}/4] {emp_id}")
        try:
            f = PyFingerprint('/dev/serial0', 57600, 0xFFFFFFFF, 0x00000000)
            if not f.verifyPassword():
                print(">>> Sensor password error")
                return

            print(f">>> Place Finger {index} - Scan 1...")
            while not f.readImage():
                time.sleep(0.1)
            f.convertImage(0x01)
            print(f">>> Finger {index} - Scan 1 Done")

            print(f">>> Remove Finger {index}...")
            time.sleep(1.5)

            print(f">>> Place Same Finger {index} Again - Scan 2...")
            while not f.readImage():
                time.sleep(0.1)
            f.convertImage(0x02)
            print(f">>> Finger {index} - Scan 2 Done")

            if f.compareCharacteristics() == 0:
                print(f">>> Finger {index} - Mismatch! Try again from dashboard")
                return

            f.createTemplate()
            position = f.storeTemplate()
            print(f">>> Finger {index}/4 - Saved (slot {position})")

            requests.post(f"{API_URL}/hardware/upload",
                          json={"emp_id": emp_id, "type": "finger", "index": index, "data": str(position)},
                          headers=device_headers(), timeout=10)
            print(f">>> Finger {index}/4 - Uploaded to Server ✅")
        except Exception as e:
            print(f">>> Finger enrollment error: {e}")


def enroll_face(emp_id, index):
    print(f"[ENROLL FACE {index}/5] {emp_id} - Look at camera...")
    try:
        picam2 = Picamera2()
        config = picam2.create_preview_configuration(main={"size": (640, 480), "format": "XBGR8888"})
        picam2.configure(config)
        picam2.start()
        time.sleep(1)
        frame = picam2.capture_array()
        frame_bgr = cv2.cvtColor(frame, cv2.COLOR_RGBA2BGR)
        rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
        faces = face_recognition.face_locations(rgb)
        if len(faces) == 0:
            print(">>> No face detected")
            picam2.stop()
            picam2.close()
            return
        enc = face_recognition.face_encodings(rgb, faces)[0].tolist()
        _, buffer = cv2.imencode(".jpg", frame_bgr)
        img_b64 = base64.b64encode(buffer).decode()
        picam2.stop()
        picam2.close()
        requests.post(f"{API_URL}/hardware/upload",
                      json={"emp_id": emp_id, "type": "face", "index": index,
                            "data": json.dumps(enc), "image": img_b64},
                      headers=device_headers(), timeout=10)
        print(f">>> Face {index} Enrolled")
    except Exception as e:
        print(f">>> Face enrollment error: {e}")


# ─────────────────────────────────────────────
# ATTENDANCE MODE FUNCTIONS
# ─────────────────────────────────────────────
def attendance_rfid_blocking():
    try:
        reader = SimpleMFRC522()
        uid, _ = reader.read()
        uid_str = str(uid)
        conn = sqlite3.connect(DB_NAME)
        emp = conn.execute("SELECT emp_id, name FROM employees WHERE rfid = ?", (uid_str,)).fetchone()
        conn.close()
        if emp:
            mark_attendance(emp[0], emp[1], "RFID")
        else:
            res = requests.post(f"{API_URL}/hardware/verify-and-record",
                                json={"identifier": uid_str, "type": "rfid", "device_id": DEVICE_ID},
                                headers=device_headers(), timeout=10)
            if res.status_code == 200:
                open_door()
    except Exception as e:
        print(f"RFID Error: {e}")


def attendance_finger_blocking():
    with finger_lock:
        try:
            f = PyFingerprint('/dev/serial0', 57600, 0xFFFFFFFF, 0x00000000)
            if not f.verifyPassword():
                return

            while not f.readImage():
                time.sleep(0.1)

            f.convertImage(0x01)
            result = f.searchTemplate()
            position = result[0]

            if position == -1:
                print(">>> Finger not recognized")
                return

            print(f">>> Finger matched slot: {position}")

            conn = sqlite3.connect(DB_NAME)
            emp = conn.execute("""SELECT emp_id, name FROM employees
                                  WHERE fingerprint1=? OR fingerprint2=? OR fingerprint3=?
                                  OR fingerprint4=? OR fingerprint5=?""",
                               (position, position, position, position, position)).fetchone()
            conn.close()

            if emp:
                mark_attendance(emp[0], emp[1], "FINGERPRINT")
            else:
                res = requests.post(f"{API_URL}/hardware/verify-and-record",
                                    json={"identifier": str(position), "type": "fingerprint", "device_id": DEVICE_ID},
                                    headers=device_headers(), timeout=10)
                if res.status_code == 200:
                    open_door()
        except Exception as e:
            print(f"Finger Error: {e}")


def load_face_db():
    encodings, names, ids = [], [], []
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    rows = conn.execute("SELECT emp_id, name, face1, face2, face3, face4, face5 FROM employees").fetchall()
    conn.close()
    for row in rows:
        for i in range(1, 6):
            if row[f"face{i}"]:
                encodings.append(np.array(json.loads(row[f"face{i}"])))
                names.append(row["name"])
                ids.append(row["emp_id"])
    return encodings, names, ids


# ─────────────────────────────────────────────
# BACKGROUND THREADS
# ─────────────────────────────────────────────
def rfid_thread():
    while True:
        try:
            attendance_rfid_blocking()
        except Exception:
            pass
        time.sleep(0.5)


def finger_thread():
    while True:
        attendance_finger_blocking()
        time.sleep(0.5)


def command_poll_thread():
    global known_encodings, known_names, known_ids, picam2_active
    while True:
        try:
            res = requests.get(f"{API_URL}/hardware/pending-command", headers=device_headers(), timeout=5)
            if res.status_code == 200:
                cmd = res.json()
                if cmd.get("command") and cmd["command"] != 0:
                    emp_id = cmd["emp_id"]

                    if picam2_active:
                        picam2.stop()
                        picam2.close()
                        picam2_active = False

                    if cmd["command"] == 1:
                        enroll_rfid(emp_id)
                    elif cmd["command"] == 2 and cmd.get("index"):
                        enroll_finger(emp_id, cmd["index"])
                    elif cmd["command"] == 3 and cmd.get("index"):
                        enroll_face(emp_id, cmd["index"])

                    requests.post(f"{API_URL}/hardware/reset", headers=device_headers(), timeout=5)
                    download_employees()
                    known_encodings, known_names, known_ids = load_face_db()

                    picam2.start()
                    picam2_active = True
                    time.sleep(1)
        except Exception:
            pass
        time.sleep(2)


# ─────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────
known_encodings = []
known_names = []
known_ids = []
picam2 = None
picam2_active = False


def main():
    global known_encodings, known_names, known_ids, picam2, picam2_active

    print(">>> Smart Attendance Terminal Starting...")
    init_db()
    download_employees()

    picam2 = Picamera2()
    config = picam2.create_preview_configuration(main={"size": (640, 480), "format": "XBGR8888"})
    picam2.configure(config)
    picam2.start()
    picam2_active = True

    known_encodings, known_names, known_ids = load_face_db()
    print(f">>> Loaded {len(known_encodings)} face encodings")

    threading.Thread(target=sync_worker, daemon=True).start()
    threading.Thread(target=rfid_thread, daemon=True).start()
    threading.Thread(target=finger_thread, daemon=True).start()
    threading.Thread(target=command_poll_thread, daemon=True).start()

    face_seen_time = None

    try:
        while True:
            frame = picam2.capture_array()
            frame_bgr = cv2.cvtColor(frame, cv2.COLOR_RGBA2BGR)
            small = cv2.resize(frame_bgr, (0, 0), fx=0.5, fy=0.5)
            rgb_small = cv2.cvtColor(small, cv2.COLOR_BGR2RGB)
            face_locs = face_recognition.face_locations(rgb_small)
            face_encs = face_recognition.face_encodings(rgb_small, face_locs)

            if len(face_encs) > 0 and len(known_encodings) > 0:
                if face_seen_time is None:
                    face_seen_time = time.time()
                if time.time() - face_seen_time >= 2:
                    matches = face_recognition.compare_faces(known_encodings, face_encs[0], tolerance=0.45)
                    if True in matches:
                        idx = matches.index(True)
                        mark_attendance(known_ids[idx], known_names[idx], "FACE")
                        face_seen_time = None
                        time.sleep(3)
                    else:
                        print(">>> Face not recognized")
                        face_seen_time = None
            else:
                face_seen_time = None

            if cv2.waitKey(1) & 0xFF == ord("q"):
                break

    except KeyboardInterrupt:
        print("\n>>> Shutting down...")
    finally:
        if picam2:
            picam2.stop()
            picam2.close()
        cv2.destroyAllWindows()
        GPIO.cleanup()


if __name__ == "__main__":
    try:
        main()
    finally:
        GPIO.cleanup()
