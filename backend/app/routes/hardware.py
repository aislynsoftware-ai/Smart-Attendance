

from fastapi import Response, Header
import csv
from io import StringIO
from datetime import datetime, date, time
from fastapi import APIRouter, HTTPException, Depends, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.employee import Employee
from app.models.attendance import Attendance
from app.models.device import Device
from app.core.auth import get_current_user

from pydantic import BaseModel
from typing import Optional, List


class SyncRecord(BaseModel):
    emp_id: str
    date: str
    check_in: str
    source: str


class SyncAttendancePayload(BaseModel):
    device_id: str
    records: List[SyncRecord]


class VerifyRecordPayload(BaseModel):
    identifier: str
    type: str
    device_id: str


class AssignBiometricPayload(BaseModel):
    emp_id: str
    rfid: Optional[str] = None
    fingerprints: Optional[List[int]] = None
    faces: Optional[List[str]] = None

router = APIRouter(prefix="/hardware", tags=["Hardware"])


def verify_device(
    x_device_id: str = Header(..., alias="X-Device-ID"),
    x_api_key: str = Header(..., alias="X-API-Key"),
    db: Session = Depends(get_db)
):
    device = db.query(Device).filter(
        Device.device_id == x_device_id,
        Device.api_key == x_api_key,
        Device.status == True
    ).first()

    if not device:
        raise HTTPException(status_code=401, detail="Invalid device credentials")

    return device


# ----------------------------
# COMMAND STATE (RAM)
# ----------------------------

hardware_state = {
    "emp_id": None,
    "command": 0,
    "index": None
}


# ----------------------------
# SCHEMAS
# ----------------------------

class HardwareCommand(BaseModel):
    emp_id: str
    command: int
    index: Optional[int] = None


class HardwareUpload(BaseModel):
    emp_id: str
    type: str
    index: Optional[int] = None
    data: Optional[str] = None
    image: Optional[str] = None


# ----------------------------
# SEND COMMAND (FROM DASHBOARD - JWT AUTH)
# ----------------------------

@router.post("/command")
def send_command(
    data: HardwareCommand,
    user=Depends(get_current_user)
):
    hardware_state["emp_id"] = data.emp_id
    hardware_state["command"] = data.command
    hardware_state["index"] = data.index

    print("Hardware command:", hardware_state)

    return {
        "message": "Command stored",
        "state": hardware_state
    }


# ----------------------------
# READ COMMAND STATUS (JWT AUTH - for dashboard polling)
# ----------------------------

@router.get("/command")
def get_command(user=Depends(get_current_user)):
    return hardware_state


# ----------------------------
# READ PENDING COMMAND (DEVICE AUTH - for Pi polling)
# ----------------------------

@router.get("/pending-command")
def get_pending_command(device: Device = Depends(verify_device)):
    return hardware_state


# ----------------------------
# RESET COMMAND (FROM DASHBOARD - JWT AUTH)
# ----------------------------

@router.post("/reset")
def reset_command(user=Depends(get_current_user)):
    hardware_state["emp_id"] = None
    hardware_state["command"] = 0
    hardware_state["index"] = None
    return {"message": "Command reset"}


# ----------------------------
# UPLOAD BIOMETRIC FROM DEVICE (DEVICE AUTH)
# ----------------------------

@router.post("/upload")
def upload_biometric(
    data: HardwareUpload,
    db: Session = Depends(get_db),
    device: Device = Depends(verify_device)
):
    emp = db.query(Employee).filter(Employee.emp_id == data.emp_id).first()

    if not emp:
        raise HTTPException(status_code=404, detail="Employee not found")

    # RFID
    if data.type == "rfid":
        emp.rfid_uid = data.data

    # Fingerprint
    elif data.type == "finger":
        if data.index == 1:
            emp.fingerprint_1 = data.data
        elif data.index == 2:
            emp.fingerprint_2 = data.data
        elif data.index == 3:
            emp.fingerprint_3 = data.data
        elif data.index == 4:
            emp.fingerprint_4 = data.data

    # Face Recognition
    elif data.type == "face":
        if data.index == 1:
            emp.face_embedding_1 = data.data
            emp.face_image_1 = data.image
        elif data.index == 2:
            emp.face_embedding_2 = data.data
            emp.face_image_2 = data.image
        elif data.index == 3:
            emp.face_embedding_3 = data.data
            emp.face_image_3 = data.image
        elif data.index == 4:
            emp.face_embedding_4 = data.data
            emp.face_image_4 = data.image
        elif data.index == 5:
            emp.face_embedding_5 = data.data
            emp.face_image_5 = data.image

    else:
        raise HTTPException(status_code=400, detail="Invalid biometric type")

    db.commit()
    
    # IMPORTANT: Reset the hardware state after successful upload
    hardware_state["emp_id"] = None
    hardware_state["command"] = 0
    hardware_state["index"] = None

    print(f"Biometric stored for: {data.emp_id}, command reset to 0")

    return {"message": "Biometric saved successfully"}

# ----------------------------
# VERIFY IDENTITY & MARK ATTENDANCE (DEVICE AUTH - called by Pi server.py)
# ----------------------------

@router.post("/verify-and-record")
def verify_and_record(
    data: VerifyRecordPayload,
    db: Session = Depends(get_db),
    device: Device = Depends(verify_device)
):
    emp = db.query(Employee).filter(
        Employee.emp_id == data.identifier
    ).first()

    if not emp:
        raise HTTPException(status_code=404, detail="Employee not found")

    today_date = date.today()
    now_time = datetime.now().time()

    records = db.query(Attendance).filter(
        Attendance.employee_id == emp.id,
        Attendance.date == today_date
    ).all()

    count = len(records)

    if count >= 7:
        return {"message": "Daily access limit reached", "name": emp.name}

    if count == 0:
        record = Attendance(
            employee_id=emp.id,
            device_id=device.id,
            office_id=emp.office_id,
            date=today_date,
            check_in=now_time,
            source=data.type.upper(),
            status="CHECK_IN"
        )
        db.add(record)
        db.commit()
        return {"name": emp.name, "status": "CHECK_IN", "time": now_time.strftime("%H:%M:%S")}

    if count == 5:
        record = Attendance(
            employee_id=emp.id,
            device_id=device.id,
            office_id=emp.office_id,
            date=today_date,
            check_out=now_time,
            source=data.type.upper(),
            status="CHECK_OUT"
        )
        db.add(record)
        db.commit()
        return {"name": emp.name, "status": "CHECK_OUT", "time": now_time.strftime("%H:%M:%S")}

    record = Attendance(
        employee_id=emp.id,
        device_id=device.id,
        office_id=emp.office_id,
        date=today_date,
        check_in=now_time,
        source=data.type.upper(),
        status="ACCESS"
    )
    db.add(record)
    db.commit()

    return {"name": emp.name, "status": "ACCESS", "time": now_time.strftime("%H:%M:%S")}


# ----------------------------
# SYNC OFFLINE ATTENDANCE (DEVICE AUTH - called by Pi server.py)
# ----------------------------

@router.post("/sync-attendance")
def sync_attendance(
    data: SyncAttendancePayload,
    db: Session = Depends(get_db),
    device: Device = Depends(verify_device)
):
    synced = 0
    for record in data.records:
        emp = db.query(Employee).filter(Employee.emp_id == record.emp_id).first()
        if not emp:
            continue

        try:
            record_date = datetime.strptime(record.date, "%Y-%m-%d").date()
            record_time = datetime.strptime(record.check_in, "%H:%M:%S").time()
        except (ValueError, TypeError):
            continue

        att = Attendance(
            employee_id=emp.id,
            device_id=device.id,
            office_id=emp.office_id,
            date=record_date,
            check_in=record_time,
            source=record.source,
            status="CHECK_IN"
        )
        db.add(att)
        synced += 1

    db.commit()

    return {"message": f"Synced {synced} records"}


# ----------------------------
# ASSIGN BIOMETRIC (DEVICE AUTH - called by Pi register.py)
# ----------------------------

@router.put("/assign-biometric")
def assign_biometric(
    data: AssignBiometricPayload,
    db: Session = Depends(get_db),
    device: Device = Depends(verify_device)
):
    emp = db.query(Employee).filter(Employee.emp_id == data.emp_id).first()
    if not emp:
        raise HTTPException(status_code=404, detail="Employee not found")

    if data.rfid:
        emp.rfid_uid = data.rfid

    if data.fingerprints:
        for i, fp in enumerate(data.fingerprints[:4]):
            setattr(emp, f"fingerprint_{i+1}", str(fp))

    if data.faces:
        for i, face_enc in enumerate(data.faces[:5]):
            setattr(emp, f"face_embedding_{i+1}", face_enc)

    db.commit()

    return {"message": f"Biometric data assigned for {data.emp_id}"}


# ----------------------------
# GET EMPLOYEES PENDING ENROLLMENT (DEVICE AUTH - called by Pi register.py)
# ----------------------------

@router.get("/employees-pending")
def employees_pending(
    db: Session = Depends(get_db),
    device: Device = Depends(verify_device)
):
    employees = db.query(Employee).filter(
        Employee.status == True,
        Employee.office_id == device.office_id
    ).all()

    return [
        {
            "emp_id": e.emp_id,
            "name": e.name
        }
        for e in employees
    ]


# ----------------------------
# GET FACE PREVIEW
# ----------------------------

@router.get("/face-preview/{index}")
def get_face_preview(
    index: int,
    emp_id: str,
    db: Session = Depends(get_db),
    user=Depends(get_current_user)
):
    """
    Get face preview image for an employee
    Usage: /hardware/face-preview/1?emp_id=AT0001
    """
    print(f"Fetching face preview for emp_id: {emp_id}, index: {index}")
    
    emp = db.query(Employee).filter(Employee.emp_id == emp_id).first()
    
    if not emp:
        raise HTTPException(status_code=404, detail="Employee not found")
    
    # Get the appropriate face image based on index
    image = None
    if index == 1:
        image = emp.face_image_1
    elif index == 2:
        image = emp.face_image_2
    elif index == 3:
        image = emp.face_image_3
    elif index == 4:
        image = emp.face_image_4
    elif index == 5:
        image = emp.face_image_5
    
    if not image:
        return {"image": None, "message": f"No face image found for index {index}"}
    
    return {"image": image}



@router.get("/download/employees-csv")
def download_employees_csv(
    device_id: str,
    api_key: str,
    db: Session = Depends(get_db)
):

    # ------------------------------------------------
    # 1. VERIFY DEVICE
    # ------------------------------------------------
    device = db.query(Device).filter(
        Device.device_id == device_id,
        Device.api_key == api_key,
        Device.status == True
    ).first()

    if not device:
        raise HTTPException(status_code=401, detail="Invalid device")

    # ------------------------------------------------
    # 2. GET ONLY DEVICE OFFICE EMPLOYEES
    # ------------------------------------------------
    employees = db.query(Employee).filter(
        Employee.status == True,
        Employee.office_id == device.office_id
    ).all()

    print(f"Preparing CSV for {len(employees)} employees (office {device.office_id})")

    # ------------------------------------------------
    # 3. CREATE CSV
    # ------------------------------------------------
    output = StringIO()
    writer = csv.writer(output)

    writer.writerow([
        'id', 'emp_id', 'name', 'email', 'phone', 'address', 'photo',
        'gender', 'blood_group', 'date_of_birth', 'position', 'joined_date',
        'office_id', 'status', 'rfid_uid',
        'fingerprint_1', 'fingerprint_2', 'fingerprint_3', 'fingerprint_4',
        'face_image_1', 'face_image_2', 'face_image_3', 'face_image_4', 'face_image_5',
        'face_embedding_1', 'face_embedding_2', 'face_embedding_3', 'face_embedding_4', 'face_embedding_5',
        'created_at', 'updated_at'
    ])

    for emp in employees:

        joined_date = emp.joined_date.strftime('%Y-%m-%d') if emp.joined_date else ''
        date_of_birth = emp.date_of_birth.strftime('%Y-%m-%d') if emp.date_of_birth else ''
        created_at = emp.created_at.strftime('%Y-%m-%d %H:%M:%S') if emp.created_at else ''
        updated_at = emp.updated_at.strftime('%Y-%m-%d %H:%M:%S') if emp.updated_at else ''

        writer.writerow([
            emp.id, emp.emp_id, emp.name, emp.email or '', emp.phone or '', emp.address or '',
            emp.photo or '', emp.gender or '', emp.blood_group or '', date_of_birth, emp.position, joined_date,
            emp.office_id, emp.status, emp.rfid_uid or '',
            emp.fingerprint_1 or '', emp.fingerprint_2 or '', emp.fingerprint_3 or '', emp.fingerprint_4 or '',
            emp.face_image_1 or '', emp.face_image_2 or '', emp.face_image_3 or '', emp.face_image_4 or '', emp.face_image_5 or '',
            emp.face_embedding_1 or '', emp.face_embedding_2 or '', emp.face_embedding_3 or '', emp.face_embedding_4 or '', emp.face_embedding_5 or '',
            created_at, updated_at
        ])

    print("CSV generation completed")

    filename = f"employees_{datetime.now().strftime('%I-%M-%p-%d-%m-%Y')}.csv"

    return Response(
        content=output.getvalue(),
        media_type="text/csv",
        headers={
            "Content-Disposition": f"attachment; filename={filename}"
        }
    )