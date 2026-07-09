from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.leave import Leave
from app.models.employee import Employee
from app.schemas.leave import LeaveCreate, LeaveOut, LeaveUpdateStatus
from app.core.auth import get_current_user


router = APIRouter(
    prefix="/leaves",
    tags=["Leaves"]
)


# =====================================================
# Apply Leave
# =====================================================
@router.post("/apply", response_model=LeaveOut)
def apply_leave(
    data: LeaveCreate,
    db: Session = Depends(get_db),
    user=Depends(get_current_user)
):

    employee = db.query(Employee).filter(
        Employee.id == data.employee_id,
        Employee.status == True
    ).first()

    if not employee:
        raise HTTPException(404, "Employee not found")

    leave = Leave(
        employee_id=data.employee_id,
        start_date=data.start_date,
        end_date=data.end_date,
        reason=data.reason,
        leave_type=data.leave_type
    )

    db.add(leave)
    db.commit()
    db.refresh(leave)

    return leave


# =====================================================
# Approve Leave (HR / Admin)
# =====================================================
@router.put("/{leave_id}/approve")
def approve_leave(
    leave_id: int,
    db: Session = Depends(get_db),
    user=Depends(get_current_user)
):

    leave = db.query(Leave).filter(
        Leave.id == leave_id
    ).first()

    if not leave:
        raise HTTPException(404, "Leave request not found")

    leave.status = "APPROVED"

    db.commit()

    return {"message": "Leave approved"}


# =====================================================
# Reject Leave (HR / Admin)
# =====================================================
@router.put("/{leave_id}/reject")
def reject_leave(
    leave_id: int,
    db: Session = Depends(get_db),
    user=Depends(get_current_user)
):

    leave = db.query(Leave).filter(
        Leave.id == leave_id
    ).first()

    if not leave:
        raise HTTPException(404, "Leave request not found")

    leave.status = "REJECTED"

    db.commit()

    return {"message": "Leave rejected"}


# =====================================================
# List All Leaves
# =====================================================
@router.get("", response_model=list[LeaveOut])
def list_leaves(
    db: Session = Depends(get_db),
    user=Depends(get_current_user)
):

    return db.query(Leave).all()


# =====================================================
# Get Leaves By Employee
# =====================================================
@router.get("/employee/{employee_id}", response_model=list[LeaveOut])
def get_employee_leaves(
    employee_id: int,
    db: Session = Depends(get_db),
    user=Depends(get_current_user)
):

    return db.query(Leave).filter(
        Leave.employee_id == employee_id
    ).all()