from pydantic import BaseModel
from typing import Optional

class CompanyCreate(BaseModel):
    name: str
    description: Optional[str] = None

class CompanyUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None

class Company(CompanyCreate):
    id: str
    created_at: str
    updated_at: str
