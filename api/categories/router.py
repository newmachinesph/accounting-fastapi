from fastapi import APIRouter, HTTPException, Response, Query
from typing import List, Optional
from supabase import Client
from ..companies.models import Company
from .models import Category, CategoryCreate, CategoryUpdate, CategoryBulkCreate, CategoryBulkDelete, CategoryParentUpdate, CategoryTypeUpdate, CategorySearch
import os
import json
from dotenv import load_dotenv
from supabase import create_client
from temp_downloads import temp_download_manager

# Load environment variables
load_dotenv()

# Initialize Supabase client
supabase: Client = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_KEY"))

# Create router
router = APIRouter(
    prefix="/companies/{company_id}/categories",
    tags=["categories"]
)

# Account Category CRUD endpoints
@router.get("/", response_model=List[Category])
async def get_categories(company_id: str):
    try:
        response = supabase.table("account_categories").select("*").eq("company_id", company_id).execute()
        return response.data
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# Enhanced endpoints - must come before /{category_id} to avoid conflicts

# All specific filtering is now handled by the search endpoints below

@router.post("/search", response_model=List[Category])
async def search_categories(company_id: str, search_params: CategorySearch):
    """Search categories with various filters"""
    try:
        query = supabase.table("account_categories").select("*").eq("company_id", company_id)
        
        # Apply filters
        if search_params.name:
            query = query.eq("name", search_params.name)
        
        if search_params.name_contains:
            query = query.ilike("name", f"%{search_params.name_contains}%")
        
        if search_params.type:
            query = query.eq("type", search_params.type)
        
        if search_params.types:
            query = query.in_("type", search_params.types)
        
        if search_params.parent_id:
            query = query.eq("parent_id", search_params.parent_id)
        
        if search_params.has_parent is not None:
            if search_params.has_parent:
                query = query.not_.is_("parent_id", "null")
            else:
                query = query.is_("parent_id", "null")
        
        # Apply pagination
        if search_params.offset:
            query = query.range(search_params.offset, search_params.offset + search_params.limit - 1)
        else:
            query = query.limit(search_params.limit)
        
        response = query.execute()
        return response.data
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/search")
async def search_categories_query(
    company_id: str,
    name: Optional[str] = Query(None, description="Exact name match"),
    name_contains: Optional[str] = Query(None, description="Name contains this text"),
    type: Optional[str] = Query(None, description="Category type"),
    types: Optional[str] = Query(None, description="Comma-separated list of types"),
    parent_id: Optional[str] = Query(None, description="Parent category ID"),
    has_parent: Optional[bool] = Query(None, description="True for subcategories, False for root categories"),
    limit: Optional[int] = Query(100, description="Maximum number of results"),
    offset: Optional[int] = Query(0, description="Number of results to skip")
):
    """Search categories using query parameters"""
    try:
        query = supabase.table("account_categories").select("*").eq("company_id", company_id)
        
        # Apply filters
        if name:
            query = query.eq("name", name)
        
        if name_contains:
            query = query.ilike("name", f"%{name_contains}%")
        
        if type:
            query = query.eq("type", type)
        
        if types:
            type_list = [t.strip() for t in types.split(',')]
            query = query.in_("type", type_list)
        
        if parent_id:
            query = query.eq("parent_id", parent_id)
        
        if has_parent is not None:
            if has_parent:
                query = query.not_.is_("parent_id", "null")
            else:
                query = query.is_("parent_id", "null")
        
        # Apply pagination
        if offset:
            query = query.range(offset, offset + limit - 1)
        else:
            query = query.limit(limit)
        
        response = query.execute()
        return response.data
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/download")
async def download_categories(
    company_id: str,
    name: Optional[str] = Query(None, description="Filter by exact name match"),
    name_contains: Optional[str] = Query(None, description="Filter by name containing text"),
    type: Optional[str] = Query(None, description="Filter by category type"),
    types: Optional[str] = Query(None, description="Filter by multiple types (comma-separated)"),
    parent_id: Optional[str] = Query(None, description="Filter by parent category ID"),
    has_parent: Optional[bool] = Query(None, description="True for subcategories, False for root categories"),
    format: Optional[str] = Query("json", description="Export format: json or csv")
):
    """Create a temporary download link for categories with optional filtering"""
    try:
        query = supabase.table("account_categories").select("*").eq("company_id", company_id)
        
        # Apply filters
        if name:
            query = query.eq("name", name)
        
        if name_contains:
            query = query.ilike("name", f"%{name_contains}%")
        
        if type:
            query = query.eq("type", type)
        
        if types:
            type_list = [t.strip() for t in types.split(',')]
            query = query.in_("type", type_list)
        
        if parent_id:
            query = query.eq("parent_id", parent_id)
        
        if has_parent is not None:
            if has_parent:
                query = query.not_.is_("parent_id", "null")
            else:
                query = query.is_("parent_id", "null")
        
        response = query.execute()
        
        # Generate filename
        filename = f"categories_{company_id}.{format.lower()}"
        
        if format.lower() == "csv":
            # Create CSV content
            import csv
            import io
            
            output = io.StringIO()
            writer = csv.DictWriter(output, fieldnames=["id", "name", "type", "parent_id", "company_id", "created_at", "updated_at"])
            writer.writeheader()
            writer.writerows(response.data)
            content = output.getvalue()
            content_type = "text/csv"
        else:
            # Create JSON content
            content = json.dumps(response.data, indent=2)
            content_type = "application/json"
        
        # Create temporary download
        download_info = temp_download_manager.create_temp_download(
            content=content,
            filename=filename,
            content_type=content_type
        )
        
        return download_info
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/bulk", response_model=List[Category])
async def create_categories_bulk(company_id: str, categories_data: CategoryBulkCreate):
    """Add multiple new categories at once"""
    try:
        # Verify that the company exists
        company_response = supabase.table("companies").select("*").eq("id", company_id).execute()
        if not company_response.data:
            raise HTTPException(status_code=404, detail="Company not found")
        
        # Prepare category data with company_id
        categories_to_insert = []
        for category in categories_data.categories:
            category_data = category.dict()
            category_data["company_id"] = company_id
            categories_to_insert.append(category_data)
        
        response = supabase.table("account_categories").insert(categories_to_insert).execute()
        if not response.data:
            raise HTTPException(status_code=500, detail="Failed to create categories")
        return response.data
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/bulk")
async def delete_categories_bulk(company_id: str, bulk_delete: CategoryBulkDelete):
    """Delete multiple categories at once"""
    try:
        # Verify that all categories exist and belong to the specified company
        for category_id in bulk_delete.category_ids:
            existing_category = supabase.table("account_categories").select("*").eq("id", category_id).eq("company_id", company_id).execute()
            if not existing_category.data:
                raise HTTPException(status_code=404, detail=f"Category {category_id} not found")
        
        # Delete all categories
        deleted_count = 0
        for category_id in bulk_delete.category_ids:
            response = supabase.table("account_categories").delete().eq("id", category_id).eq("company_id", company_id).execute()
            if response.data:
                deleted_count += 1
        
        return {"message": f"Successfully deleted {deleted_count} categories"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/{category_id}", response_model=Category)
async def get_category(company_id: str, category_id: str):
    try:
        response = supabase.table("account_categories").select("*").eq("id", category_id).eq("company_id", company_id).execute()
        if not response.data:
            raise HTTPException(status_code=404, detail="Category not found")
        return response.data[0]
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/", response_model=Category)
async def create_category(company_id: str, category: CategoryCreate):
    try:
        # Verify that the company exists
        company_response = supabase.table("companies").select("*").eq("id", company_id).execute()
        if not company_response.data:
            raise HTTPException(status_code=404, detail="Company not found")
        
        # Ensure the category is associated with the specified company
        category_data = category.dict()
        category_data["company_id"] = company_id
        
        response = supabase.table("account_categories").insert(category_data).execute()
        if not response.data:
            raise HTTPException(status_code=500, detail="Failed to create category")
        return response.data[0]
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.put("/{category_id}", response_model=Category)
async def update_category(company_id: str, category_id: str, category: CategoryUpdate):
    try:
        # Verify that the category exists and belongs to the specified company
        existing_category = supabase.table("account_categories").select("*").eq("id", category_id).eq("company_id", company_id).execute()
        if not existing_category.data:
            raise HTTPException(status_code=404, detail="Category not found")
        
        update_data = {}
        if category.name is not None:
            update_data["name"] = category.name
        if category.type is not None:
            update_data["type"] = category.type
        if category.parent_id is not None:
            update_data["parent_id"] = category.parent_id
            
        response = supabase.table("account_categories").update(update_data).eq("id", category_id).eq("company_id", company_id).execute()
        if not response.data:
            raise HTTPException(status_code=404, detail="Category not found")
        return response.data[0]
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/{category_id}")
async def delete_category(company_id: str, category_id: str):
    try:
        # Verify that the category exists and belongs to the specified company
        existing_category = supabase.table("account_categories").select("*").eq("id", category_id).eq("company_id", company_id).execute()
        if not existing_category.data:
            raise HTTPException(status_code=404, detail="Category not found")
        
        response = supabase.table("account_categories").delete().eq("id", category_id).eq("company_id", company_id).execute()
        if not response.data:
            raise HTTPException(status_code=404, detail="Category not found")
        return {"message": "Category deleted successfully"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.patch("/{category_id}/parent", response_model=Category)
async def update_category_parent(company_id: str, category_id: str, parent_update: CategoryParentUpdate):
    """Change the parent category of a specific category"""
    try:
        # Verify that the category exists and belongs to the specified company
        existing_category = supabase.table("account_categories").select("*").eq("id", category_id).eq("company_id", company_id).execute()
        if not existing_category.data:
            raise HTTPException(status_code=404, detail="Category not found")
        
        # If parent_id is provided, verify it exists and belongs to the same company
        if parent_update.parent_id:
            parent_response = supabase.table("account_categories").select("*").eq("id", parent_update.parent_id).eq("company_id", company_id).execute()
            if not parent_response.data:
                raise HTTPException(status_code=404, detail="Parent category not found")
            # Check that type matches
            child_type = existing_category.data[0].get("type")
            parent_type = parent_response.data[0].get("type")
            if child_type != parent_type:
                raise HTTPException(
                    status_code=400,
                    detail="Parent category must be of the same type as the child category"
                )
        
        response = supabase.table("account_categories").update({"parent_id": parent_update.parent_id}).eq("id", category_id).eq("company_id", company_id).execute()
        if not response.data:
            raise HTTPException(status_code=404, detail="Category not found")
        return response.data[0]
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.patch("/{category_id}/type", response_model=Category)
async def update_category_type(company_id: str, category_id: str, type_update: CategoryTypeUpdate):
    """Change the type of a category (e.g., to COGS from what it is now)"""
    try:
        # Verify that the category exists and belongs to the specified company
        existing_category = supabase.table("account_categories").select("*").eq("id", category_id).eq("company_id", company_id).execute()
        if not existing_category.data:
            raise HTTPException(status_code=404, detail="Category not found")
        
        response = supabase.table("account_categories").update({"type": type_update.type}).eq("id", category_id).eq("company_id", company_id).execute()
        if not response.data:
            raise HTTPException(status_code=404, detail="Category not found")
        return response.data[0]
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/by-name/{category_name}", response_model=Category)
async def get_category_by_name(company_id: str, category_name: str):
    """
    Lookup a category by name for a given company.
    Returns the first match (names are not guaranteed unique).
    """
    try:
        response = supabase.table("account_categories").select("*").eq("company_id", company_id).eq("name", category_name).execute()
        if not response.data:
            raise HTTPException(status_code=404, detail="Category not found")
        return response.data[0]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
