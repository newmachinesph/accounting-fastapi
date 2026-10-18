from pydantic import BaseModel
from typing import Optional, List

class PayeeCreate(BaseModel):
    name: str

class PayeeUpdate(BaseModel):
    company_id: Optional[str] = None
    name: Optional[str] = None

class PayeeBulkCreate(BaseModel):
    payees: List[PayeeCreate]

class PayeeBulkDelete(BaseModel):
    payee_ids: List[str]

class PayeeMerge(BaseModel):
    source_payee_id: str
    target_payee_id: str

class PayeeSearch(BaseModel):
    name: Optional[str] = None
    name_contains: Optional[str] = None
    limit: Optional[int] = 100
    offset: Optional[int] = 0

class Payee(PayeeCreate):
    id: str
    company_id: str
    created_at: str
    updated_at: str
