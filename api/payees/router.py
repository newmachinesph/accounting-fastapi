from fastapi import APIRouter, HTTPException, Response, Query
from typing import List, Optional
from supabase import Client
from ..companies.models import Company
from .models import Payee, PayeeCreate, PayeeUpdate, PayeeBulkCreate, PayeeBulkDelete, PayeeMerge, PayeeSearch
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
    prefix="/companies/{company_id}/payees",
    tags=["payees"]
)

# Payee CRUD endpoints
@router.get("/", response_model=List[Payee])
async def get_payees(company_id: str):
    try:
        response = supabase.table("payees").select("*").eq("company_id", company_id).execute()
        return response.data
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# Enhanced endpoints - must come before /{payee_id} to avoid conflicts

@router.post("/search", response_model=List[Payee])
async def search_payees(company_id: str, search_params: PayeeSearch):
    """Search payees with various filters"""
    try:
        query = supabase.table("payees").select("*").eq("company_id", company_id)
        
        # Apply filters
        if search_params.name:
            query = query.eq("name", search_params.name)
        
        if search_params.name_contains:
            query = query.ilike("name", f"%{search_params.name_contains}%")
        
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
async def search_payees_query(
    company_id: str, 
    name: Optional[str] = Query(None, description="Exact name match"),
    name_contains: Optional[str] = Query(None, description="Name contains this text"),
    limit: Optional[int] = Query(100, description="Maximum number of results"),
    offset: Optional[int] = Query(0, description="Number of results to skip")
):
    """Search payees using query parameters"""
    try:
        query = supabase.table("payees").select("*").eq("company_id", company_id)
        
        # Apply filters
        if name:
            query = query.eq("name", name)
        
        if name_contains:
            query = query.ilike("name", f"%{name_contains}%")
        
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
async def download_payees(
    company_id: str,
    name: Optional[str] = Query(None, description="Filter by exact name match"),
    name_contains: Optional[str] = Query(None, description="Filter by name containing text"),
    format: Optional[str] = Query("json", description="Export format: json or csv")
):
    """Create a temporary download link for payees with optional filtering"""
    try:
        query = supabase.table("payees").select("*").eq("company_id", company_id)
        
        # Apply filters
        if name:
            query = query.eq("name", name)
        
        if name_contains:
            query = query.ilike("name", f"%{name_contains}%")
        
        response = query.execute()
        
        # Generate filename
        filename = f"payees_{company_id}.{format.lower()}"
        
        if format.lower() == "csv":
            # Create CSV content
            import csv
            import io
            
            output = io.StringIO()
            writer = csv.DictWriter(output, fieldnames=["id", "name", "company_id", "created_at", "updated_at"])
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

@router.post("/", response_model=Payee)
async def create_payee(company_id: str, payee: PayeeCreate):
    try:
        # Verify that the company exists
        company_response = supabase.table("companies").select("*").eq("id", company_id).execute()
        if not company_response.data:
            raise HTTPException(status_code=404, detail="Company not found")
        
        # Ensure the payee is associated with the specified company
        payee_data = payee.dict()
        payee_data["company_id"] = company_id
        
        response = supabase.table("payees").insert(payee_data).execute()
        if not response.data:
            raise HTTPException(status_code=500, detail="Failed to create payee")
        return response.data[0]
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/bulk", response_model=List[Payee])
async def create_payees_bulk(company_id: str, payees_data: PayeeBulkCreate):
    """Add multiple new payees at once"""
    try:
        # Verify that the company exists
        company_response = supabase.table("companies").select("*").eq("id", company_id).execute()
        if not company_response.data:
            raise HTTPException(status_code=404, detail="Company not found")
        
        # Prepare payee data with company_id
        payees_to_insert = []
        for payee in payees_data.payees:
            payee_data = payee.dict()
            payee_data["company_id"] = company_id
            payees_to_insert.append(payee_data)
        
        response = supabase.table("payees").insert(payees_to_insert).execute()
        if not response.data:
            raise HTTPException(status_code=500, detail="Failed to create payees")
        return response.data
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# Enhanced endpoints for bulk operations and merging

@router.delete("/bulk")
async def delete_payees_bulk(company_id: str, bulk_delete: PayeeBulkDelete):
    """Delete multiple payees at once"""
    try:
        # Verify that all payees exist and belong to the specified company
        for payee_id in bulk_delete.payee_ids:
            existing_payee = supabase.table("payees").select("*").eq("id", payee_id).eq("company_id", company_id).execute()
            if not existing_payee.data:
                raise HTTPException(status_code=404, detail=f"Payee {payee_id} not found")
        
        # Delete all payees
        deleted_count = 0
        for payee_id in bulk_delete.payee_ids:
            response = supabase.table("payees").delete().eq("id", payee_id).eq("company_id", company_id).execute()
            if response.data:
                deleted_count += 1
        
        return {"message": f"Successfully deleted {deleted_count} payees"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/merge")
async def merge_payees(company_id: str, merge_data: PayeeMerge):
    """Merge one payee with another (move all transactions from source to target, then delete source)"""
    try:
        # Verify that both payees exist and belong to the specified company
        source_payee = supabase.table("payees").select("*").eq("id", merge_data.source_payee_id).eq("company_id", company_id).execute()
        if not source_payee.data:
            raise HTTPException(status_code=404, detail="Source payee not found")
        
        target_payee = supabase.table("payees").select("*").eq("id", merge_data.target_payee_id).eq("company_id", company_id).execute()
        if not target_payee.data:
            raise HTTPException(status_code=404, detail="Target payee not found")
        
        # Update all transactions from source payee to target payee
        transactions_response = supabase.table("transactions").update(
            {"payee_id": merge_data.target_payee_id}
        ).eq("payee_id", merge_data.source_payee_id).eq("company_id", company_id).execute()
        
        # Delete the source payee
        delete_response = supabase.table("payees").delete().eq("id", merge_data.source_payee_id).eq("company_id", company_id).execute()
        if not delete_response.data:
            raise HTTPException(status_code=500, detail="Failed to delete source payee")
        
        return {
            "message": f"Successfully merged payee {source_payee.data[0]['name']} into {target_payee.data[0]['name']}",
            "transactions_updated": len(transactions_response.data) if transactions_response.data else 0
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# CRUD endpoints with path parameters - these must come AFTER specific endpoints

@router.get("/{payee_id}", response_model=Payee)
async def get_payee(company_id: str, payee_id: str):
    try:
        response = supabase.table("payees").select("*").eq("id", payee_id).eq("company_id", company_id).execute()
        if not response.data:
            raise HTTPException(status_code=404, detail="Payee not found")
        return response.data[0]
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.put("/{payee_id}", response_model=Payee)
async def update_payee(company_id: str, payee_id: str, payee: PayeeUpdate):
    try:
        # Verify that the payee exists and belongs to the specified company
        existing_payee = supabase.table("payees").select("*").eq("id", payee_id).eq("company_id", company_id).execute()
        if not existing_payee.data:
            raise HTTPException(status_code=404, detail="Payee not found")
        
        update_data = {}
        if payee.name is not None:
            update_data["name"] = payee.name
            
        response = supabase.table("payees").update(update_data).eq("id", payee_id).eq("company_id", company_id).execute()
        if not response.data:
            raise HTTPException(status_code=404, detail="Payee not found")
        return response.data[0]
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/{payee_id}")
async def delete_payee(company_id: str, payee_id: str):
    try:
        # Verify that the payee exists and belongs to the specified company
        existing_payee = supabase.table("payees").select("*").eq("id", payee_id).eq("company_id", company_id).execute()
        if not existing_payee.data:
            raise HTTPException(status_code=404, detail="Payee not found")
        
        response = supabase.table("payees").delete().eq("id", payee_id).eq("company_id", company_id).execute()
        if not response.data:
            raise HTTPException(status_code=404, detail="Payee not found")
        return {"message": "Payee deleted successfully"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/by-name/{payee_name}", response_model=Payee)
async def get_payee_by_name(company_id: str, payee_name: str):
    """
    Lookup a payee by name for a given company.
    Returns the first match (names are not guaranteed unique).
    """
    try:
        response = supabase.table("payees").select("*").eq("company_id", company_id).eq("name", payee_name).execute()
        if not response.data:
            raise HTTPException(status_code=404, detail="Payee not found")
        return response.data[0]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
