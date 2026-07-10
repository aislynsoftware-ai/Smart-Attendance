from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.employee import Employee
from app.models.office import Office
from app.schemas.employee import (
    EmployeeCreate,
    EmployeeUpdate,
    EmployeeOut
)
from app.core.auth import get_current_user


router = APIRouter(
    prefix="/employees",
    tags=["Employees"]
)


# =====================================================
# Role Checker: Admin OR HR
# =====================================================
def require_admin_or_hr(user=Depends(get_current_user)):
    if user.role.lower() not in ["admin", "hr"]:
        raise HTTPException(status_code=403, detail="Access denied")
    return user


# =====================================================
# Create Employee
# =====================================================
@router.post("", response_model=EmployeeOut)
def create_employee(
    data: EmployeeCreate,
    db: Session = Depends(get_db),
    user=Depends(require_admin_or_hr)
):

    existing = db.query(Employee).filter(
        Employee.emp_id == data.emp_id
    ).first()

    if existing:
        raise HTTPException(
            status_code=400,
            detail="Employee ID already exists"
        )

    office = db.query(Office).filter(
        Office.id == data.office_id,
        Office.status == True
    ).first()

    if not office:
        raise HTTPException(
            status_code=400,
            detail="Invalid office"
        )

    emp = Employee(**data.dict())

    db.add(emp)
    db.commit()
    db.refresh(emp)

    return emp


# =====================================================
# Get Single Employee
# =====================================================
@router.get("/{emp_id}", response_model=EmployeeOut)
def get_employee(
    emp_id: str,
    db: Session = Depends(get_db),
    user=Depends(require_admin_or_hr)
):

    emp = db.query(Employee).filter(
        Employee.emp_id == emp_id
    ).first()

    if not emp:
        raise HTTPException(
            status_code=404,
            detail="Employee not found"
        )

    return emp


# =====================================================
# Update Employee
# =====================================================
@router.put("/{emp_id}", response_model=EmployeeOut)
def update_employee(
    emp_id: str,
    data: EmployeeUpdate,
    db: Session = Depends(get_db),
    user=Depends(require_admin_or_hr)
):

    emp = db.query(Employee).filter(
        Employee.emp_id == emp_id
    ).first()

    if not emp:
        raise HTTPException(
            status_code=404,
            detail="Employee not found"
        )

    if data.office_id:
        office = db.query(Office).filter(
            Office.id == data.office_id,
            Office.status == True
        ).first()

        if not office:
            raise HTTPException(
                status_code=400,
                detail="Invalid office"
            )

    for key, value in data.dict(exclude_unset=True).items():
        setattr(emp, key, value)

    db.commit()
    db.refresh(emp)

    return emp


# =====================================================
# Deactivate Employee (Soft Delete)
# =====================================================
@router.delete("/{emp_id}")
def deactivate_employee(
    emp_id: str,
    db: Session = Depends(get_db),
    user=Depends(require_admin_or_hr)
):

    emp = db.query(Employee).filter(
        Employee.emp_id == emp_id
    ).first()

    if not emp:
        raise HTTPException(
            status_code=404,
            detail="Employee not found"
        )

    emp.status = False
    db.commit()

    return {"message": "Employee deactivated successfully"}


# =====================================================
# Update Employee Status
# =====================================================
@router.put("/{emp_id}/status")
def update_employee_status(
    emp_id: str,
    status: bool = Query(...),
    db: Session = Depends(get_db),
    user=Depends(require_admin_or_hr)
):

    emp = db.query(Employee).filter(
        Employee.emp_id == emp_id
    ).first()

    if not emp:
        raise HTTPException(
            status_code=404,
            detail="Employee not found"
        )

    emp.status = status
    db.commit()

    return {"message": "Employee status updated"}


# =====================================================
# List Employees
# =====================================================
@router.get("", response_model=list[EmployeeOut])
def list_employees(
    active_only: bool = Query(True),
    db: Session = Depends(get_db),
    user=Depends(require_admin_or_hr)
):

    query = db.query(Employee)

    if active_only:
        query = query.filter(Employee.status == True)

    return query.all()


# =====================================================
# Get Employees By Office
# =====================================================
@router.get("/office/{office_id}", response_model=list[EmployeeOut])
def get_employees_by_office(
    office_id: int,
    db: Session = Depends(get_db),
    user=Depends(require_admin_or_hr)
):

    employees = db.query(Employee).filter(
        Employee.office_id == office_id,
        Employee.status == True
    ).all()

    return employees


# =====================================================
# Update Biometric Data
# =====================================================
@router.put("/{emp_id}/biometric")
def update_biometric(
    emp_id: str,
    biometric_type: str = Query(...),
    data: str = Query(...),
    db: Session = Depends(get_db),
    user=Depends(require_admin_or_hr)
):

    emp = db.query(Employee).filter(
        Employee.emp_id == emp_id
    ).first()

    if not emp:
        raise HTTPException(
            status_code=404,
            detail="Employee not found"
        )

    if biometric_type == "rfid":
        emp.rfid_uid = data

    else:
        raise HTTPException(
            status_code=400,
            detail="Invalid biometric type. Use /hardware/upload for fingerprint/face."
        )

    db.commit()

    return {"message": "Biometric updated successfully"}