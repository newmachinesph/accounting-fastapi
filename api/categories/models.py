from pydantic import BaseModel
from typing import Optional, List

class CategoryCreate(BaseModel):
    name: str
    type: str
    parent_id: Optional[str] = None

class CategoryUpdate(BaseModel):
    company_id: Optional[str] = None
    name: Optional[str] = None
    type: Optional[str] = None
    parent_id: Optional[str] = None

class CategoryBulkCreate(BaseModel):
    categories: List[CategoryCreate]

class CategoryBulkDelete(BaseModel):
    category_ids: List[str]

class CategoryParentUpdate(BaseModel):
    parent_id: Optional[str] = None

class CategoryTypeUpdate(BaseModel):
    type: str

class CategorySearch(BaseModel):
    name: Optional[str] = None
    name_contains: Optional[str] = None
    type: Optional[str] = None
    types: Optional[List[str]] = None
    parent_id: Optional[str] = None
    has_parent: Optional[bool] = None  # True for categories with parent, False for root categories
    limit: Optional[int] = 100
    offset: Optional[int] = 0

class Category(CategoryCreate):
    id: str
    company_id: str
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
