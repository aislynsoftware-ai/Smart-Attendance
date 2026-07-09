import os

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError

from app.database import engine

# Models
from app.models import attendance, device, employee, leave, office, user

# Routes
from app.routes import biometrics, devices, employees, leaves, offices, reports, users, hardware
from app.routes import attendance as attendance_router


app = FastAPI(
    title="Smart Attendance System",
    version="1.0.0",
    redirect_slashes=False
)

# Add your IP directly to the list
raw_origins = os.getenv(
    "CORS_ORIGINS",
    "http://localhost:5173,http://127.0.0.1:5173,http://192.168.1.6:5173,http://192.168.0.109:5173,http://127.0.0.1:5500",
)
allowed_origins = [origin.strip() for origin in raw_origins.split(",") if origin.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins, 
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)



@app.exception_handler(Exception)
def unhandled_exception_handler(_: Request, exc: Exception):
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error", "error": exc.__class__.__name__},
    )


# Create tables (with retry support)
try:
    user.Base.metadata.create_all(bind=engine)
    employee.Base.metadata.create_all(bind=engine)
    device.Base.metadata.create_all(bind=engine)
    office.Base.metadata.create_all(bind=engine)
    attendance.Base.metadata.create_all(bind=engine)
    leave.Base.metadata.create_all(bind=engine)
except Exception as e:
    print(f"⚠️  Could not create tables: {e}")
    print("   The API will still start, but DB operations may fail.")



# Register routes
app.include_router(users.router)
app.include_router(employees.router)
app.include_router(biometrics.router)
app.include_router(devices.router)
app.include_router(offices.router)
app.include_router(attendance_router.router)
app.include_router(reports.router)
app.include_router(leaves.router)
app.include_router(hardware.router)

@app.get("/")
def root():
    return {"message": "Smart Attendance Backend is Running 🚀"}
