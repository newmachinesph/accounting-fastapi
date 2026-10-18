from pydantic import BaseModel
from typing import Optional, List
from datetime import date

class TransactionCreate(BaseModel):
    payee_id: Optional[str] = None
    category_id: str
    transaction_date: str
    description: Optional[str] = None
    spent: Optional[float] = 0.00
    received: Optional[float] = 0.00

class TransactionUpdate(BaseModel):
    company_id: Optional[str] = None
    payee_id: Optional[str] = None
    category_id: Optional[str] = None
    transaction_date: Optional[str] = None
    description: Optional[str] = None
    spent: Optional[float] = None
    received: Optional[float] = None

class TransactionBulkCreate(BaseModel):
    transactions: List[TransactionCreate]

class TransactionBulkDelete(BaseModel):
    transaction_ids: List[str]

class TransactionSearch(BaseModel):
    category_id: Optional[str] = None
    payee_id: Optional[str] = None
    description_contains: Optional[str] = None
    date_from: Optional[str] = None
    date_to: Optional[str] = None
    min_amount: Optional[float] = None
    max_amount: Optional[float] = None
    transaction_type: Optional[str] = None  # "spent", "received", "all"
    limit: Optional[int] = 100
    offset: Optional[int] = 0

class Transaction(TransactionCreate):
    id: str
    company_id: str
    created_at: str
    updated_at: str
