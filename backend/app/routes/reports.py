from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import extract
from datetime import date

from app.database import get_db
from app.models.employee import Employee
from app.models.attendance import Attendance
from app.core.auth import get_current_user
import csv
from io import StringIO
from reportlab.pdfgen import canvas
from fastapi.responses import StreamingResponse
from io import BytesIO

router = APIRouter(
    prefix="/reports",
    tags=["Reports"]
)


@router.get("/daily-summary")
def daily_summary(
    report_date: date,
    db: Session = Depends(get_db),
    user=Depends(get_current_user)
):
    try:
        total = db.query(Employee).filter(
            Employee.status == True
        ).count()

        present = db.query(Attendance.employee_id).filter(
            Attendance.date == report_date,
            Attendance.check_in != None
        ).distinct().count()

        absent = total - present

        return {
            "date": report_date,
            "total_employees": total,
            "present": present,
            "absent": absent
        }

    except Exception as e:
        print("DAILY SUMMARY ERROR:", e)
        raise HTTPException(status_code=500, detail="Failed to generate summary")


@router.get("/absent-list")
def absent_list(
    report_date: date,
    db: Session = Depends(get_db),
    user=Depends(get_current_user)
):
    try:
        present_ids = db.query(
            Attendance.employee_id
        ).filter(
            Attendance.date == report_date,
            Attendance.check_in != None
        ).subquery()

        absent = db.query(Employee).filter(
            Employee.status == True,
            ~Employee.id.in_(present_ids)
        ).all()

        return absent

    except Exception as e:
        print("ABSENT ERROR:", e)
        raise HTTPException(status_code=500, detail="Failed to get absent list")


@router.get("/monthly")
def monthly_report(year: int, month: int, db: Session = Depends(get_db), user=Depends(get_current_user)):
    try:
        results = db.query(Attendance, Employee).join(
            Employee, Attendance.employee_id == Employee.id
        ).filter(
            extract("year", Attendance.date) == year,
            extract("month", Attendance.date) == month
        ).all()

        return [
            {
                "id": att.id,
                "emp_id": emp.emp_id,
                "emp_name": emp.name,
                "date": att.date,
                "type": "Regular",
                "in_time": att.check_in,
                "out_time": att.check_out
            } for att, emp in results
        ]
    except Exception as e:
        raise HTTPException(status_code=500, detail="Failed to get monthly report")


@router.get("/export-csv")
def export_csv(report_date: date, db: Session = Depends(get_db)):

    records = db.query(Attendance, Employee).join(
        Employee, Attendance.employee_id == Employee.id
    ).filter(
        Attendance.date == report_date
    ).all()

    output = StringIO()
    writer = csv.writer(output)

    writer.writerow([
        "Employee ID",
        "Name",
        "Date",
        "Check In",
        "Check Out",
        "Source",
        "Status"
    ])

    for att, emp in records:
        writer.writerow([
            emp.emp_id,
            emp.name,
            att.date,
            att.check_in,
            att.check_out,
            att.source,
            att.status
        ])

    output.seek(0)

    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={
            "Content-Disposition": f"attachment; filename=attendance_{report_date}.csv"
        },
    )


@router.get("/export-pdf")
def export_pdf(report_date: date, db: Session = Depends(get_db)):

    records = db.query(Attendance, Employee).join(
        Employee, Attendance.employee_id == Employee.id
    ).filter(
        Attendance.date == report_date
    ).all()

    buffer = BytesIO()

    p = canvas.Canvas(buffer)

    y = 800

    p.drawString(50, y, f"Attendance Report - {report_date}")
    y -= 40

    for att, emp in records:

        line = f"{emp.emp_id} | {emp.name} | {att.check_in} | {att.check_out} | {att.status}"

        p.drawString(50, y, line)

        y -= 20

        if y < 100:
            p.showPage()
            y = 800

    p.save()

    buffer.seek(0)

    return StreamingResponse(
        buffer,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f"attachment; filename=attendance_{report_date}.pdf"
        },
    )


@router.get("/export-monthly-csv")
def export_monthly_csv(year: int, month: int, db: Session = Depends(get_db)):

    results = db.query(Attendance, Employee).join(
        Employee, Attendance.employee_id == Employee.id
    ).filter(
        extract("year", Attendance.date) == year,
        extract("month", Attendance.date) == month
    ).all()

    output = StringIO()
    writer = csv.writer(output)

    writer.writerow([
        "Employee ID",
        "Name",
        "Date",
        "Check In",
        "Check Out"
    ])

    for att, emp in results:
        writer.writerow([
            emp.emp_id,
            emp.name,
            att.date,
            att.check_in,
            att.check_out
        ])

    output.seek(0)

    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={
            "Content-Disposition": f"attachment; filename=monthly_{year}_{month}.csv"
        }
    )


@router.get("/export-monthly-pdf")
def export_monthly_pdf(year: int, month: int, db: Session = Depends(get_db)):

    results = db.query(Attendance, Employee).join(
        Employee, Attendance.employee_id == Employee.id
    ).filter(
        extract("year", Attendance.date) == year,
        extract("month", Attendance.date) == month
    ).all()

    buffer = BytesIO()
    pdf = canvas.Canvas(buffer)

    y = 800
    pdf.drawString(50, y, f"Monthly Report {month}/{year}")
    y -= 40

    for att, emp in results:

        line = f"{emp.emp_id} | {emp.name} | {att.date} | {att.check_in} | {att.check_out}"

        pdf.drawString(50, y, line)
        y -= 20

        if y < 100:
            pdf.showPage()
            y = 800

    pdf.save()
    buffer.seek(0)

    return StreamingResponse(
        buffer,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f"attachment; filename=monthly_{year}_{month}.pdf"
        }
    )
