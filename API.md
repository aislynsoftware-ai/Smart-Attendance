# Smart Attendance System - API Reference

**Base URL:** `https://aislyntech-attendance.hf.space`

---

## Authentication
### POST /users/register
Register a new user.

### POST /users/login
Login and receive a JWT access token.

### GET /users/me
Get current user profile (requires auth).

### GET /users/admin-only
Admin-only endpoint (requires admin role).

---

## Employees
### POST /employees/
Create a new employee.

### GET /employees/
List all employees.

### GET /employees/{emp_id}
Get employee by ID.

### PUT /employees/{emp_id}
Update employee details.

### DELETE /employees/{emp_id}
Deactivate an employee.

### PUT /employees/{emp_id}/status
Update employee status.

### GET /employees/office/{office_id}
List employees by office.

### PUT /employees/{emp_id}/biometric
Update employee biometric data.

---

## Attendance
### POST /attendance/mark
Mark attendance (via RFID, face, or manual).

### GET /attendance/by-date/{day}
Get attendance records by date (format: YYYY-MM-DD).

### GET /attendance/by-employee/{emp_id}
Get attendance records by employee.

### GET /attendance/summary/{day}
Get attendance summary for a date.

---

## Devices
### POST /devices/
Register a new device.

### GET /devices/
List all devices.

### GET /devices/{device_id}
Get device details.

### PUT /devices/{device_id}
Update device.

### PUT /devices/{device_id}/status
Update device status.

### DELETE /devices/{device_id}
Delete a device.

### PUT /devices/{device_id}/regenerate-key
Regenerate device API key.

### POST /devices/verify
Verify a device.

### GET /devices/sync-data
Get data to sync to devices.

---

## Biometrics
### POST /biometrics/rfid
Enroll RFID tag for an employee.

### POST /biometrics/fingerprint
Enroll fingerprint for an employee.

### POST /biometrics/face
Enroll face image/embedding for an employee.

---

## Offices
### POST /offices/
Create a new office.

### GET /offices/
List all offices.

### PUT /offices/{office_id}
Update office details.

### DELETE /offices/{office_id}
Delete an office.

---

## Leaves
### POST /leaves/apply
Apply for leave.

### GET /leaves/
List all leaves.

### GET /leaves/employee/{employee_id}
Get leaves by employee.

### PUT /leaves/approve/{leave_id}
Approve a leave request.

### PUT /leaves/reject/{leave_id}
Reject a leave request.

---

## Reports
### GET /reports/daily-summary
Get daily attendance summary.

### GET /reports/absent-list
Get list of absent employees.

### GET /reports/monthly
Get monthly attendance report.

### GET /reports/export-csv
Export attendance as CSV.

### GET /reports/export-pdf
Export attendance as PDF.

### GET /reports/export-monthly-csv
Export monthly report as CSV.

### GET /reports/export-monthly-pdf
Export monthly report as PDF.

---

## Hardware
### POST /hardware/command
Send command to hardware device.

### GET /hardware/command
Get pending command for hardware.

### POST /hardware/reset
Reset hardware command queue.

### POST /hardware/upload
Upload biometric data from hardware.

### GET /hardware/face-preview/{index}
Get face preview image.

### GET /hardware/download/employees-csv
Download employees list as CSV for device sync.