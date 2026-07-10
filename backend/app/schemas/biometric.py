from pydantic import BaseModel
from typing import Optional


class RFIDEnroll(BaseModel):
    emp_id: str
    rfid_uid: str


class FingerEnroll(BaseModel):
    emp_id: str
    index: int
    data: str


class FaceEnroll(BaseModel):
    emp_id: str
    index: int
    embedding: str
    image: Optional[str] = None