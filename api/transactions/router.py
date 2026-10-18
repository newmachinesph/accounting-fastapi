from fastapi import APIRouter, HTTPException, Response, Query
from typing import List, Optional
from supabase import Client
from ..companies.models import Company
from ..categories.models import Category
from ..payees.models import Payee
from .models import Transaction, TransactionCreate, TransactionUpdate, TransactionBulkCreate, TransactionBulkDelete, TransactionSearch
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
    prefix="/companies/{company_id}/transactions",
    tags=["transactions"]
)

# Transaction CRUD endpoints
@router.get("/", response_model=List[Transaction])
async def get_transactions(company_id: str):
    try:
        response = supabase.table("transactions").select("*").eq("company_id", company_id).execute()
        return response.data
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/{transaction_id}", response_model=Transaction)
async def get_transaction(company_id: str, transaction_id: str):
    try:
        response = supabase.table("transactions").select("*").eq("id", transaction_id).eq("company_id", company_id).execute()
        if not response.data:
            raise HTTPException(status_code=404, detail="Transaction not found")
        return response.data[0]
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/", response_model=Transaction)
async def create_transaction(company_id: str, transaction: TransactionCreate):
    try:
        # Verify that the company exists
        company_response = supabase.table("companies").select("*").eq("id", company_id).execute()
        if not company_response.data:
            raise HTTPException(status_code=404, detail="Company not found")
        
        # Verify that the payee exists and belongs to the specified company (if payee_id is provided)
        if transaction.payee_id:
            payee_response = supabase.table("payees").select("*").eq("id", transaction.payee_id).eq("company_id", company_id).execute()
            if not payee_response.data:
                raise HTTPException(status_code=404, detail="Payee not found or does not belong to this company")
        
        # Verify that the category exists and belongs to the specified company
        category_response = supabase.table("account_categories").select("*").eq("id", transaction.category_id).eq("company_id", company_id).execute()
        if not category_response.data:
            raise HTTPException(status_code=404, detail="Category not found or does not belong to this company")
        
        # Ensure the transaction is associated with the specified company
        transaction_data = transaction.dict()
        transaction_data["company_id"] = company_id
        
        response = supabase.table("transactions").insert(transaction_data).execute()
        if not response.data:
            raise HTTPException(status_code=500, detail="Failed to create transaction")
        return response.data[0]
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.put("/{transaction_id}", response_model=Transaction)
async def update_transaction(company_id: str, transaction_id: str, transaction: TransactionUpdate):
    try:
        # Verify that the transaction exists and belongs to the specified company
        existing_transaction = supabase.table("transactions").select("*").eq("id", transaction_id).eq("company_id", company_id).execute()
        if not existing_transaction.data:
            raise HTTPException(status_code=404, detail="Transaction not found")
        
        # Verify that the payee exists and belongs to the specified company (if payee_id is provided)
        if transaction.payee_id:
            payee_response = supabase.table("payees").select("*").eq("id", transaction.payee_id).eq("company_id", company_id).execute()
            if not payee_response.data:
                raise HTTPException(status_code=404, detail="Payee not found or does not belong to this company")
        
        # Verify that the category exists and belongs to the specified company (if category_id is provided)
        if transaction.category_id:
            category_response = supabase.table("account_categories").select("*").eq("id", transaction.category_id).eq("company_id", company_id).execute()
            if not category_response.data:
                raise HTTPException(status_code=404, detail="Category not found or does not belong to this company")
        
        update_data = {}
        if transaction.payee_id is not None:
            update_data["payee_id"] = transaction.payee_id
        if transaction.category_id is not None:
            update_data["category_id"] = transaction.category_id
        if transaction.transaction_date is not None:
            update_data["transaction_date"] = transaction.transaction_date
        if transaction.description is not None:
            update_data["description"] = transaction.description
        if transaction.spent is not None:
            update_data["spent"] = transaction.spent
        if transaction.received is not None:
            update_data["received"] = transaction.received
            
        response = supabase.table("transactions").update(update_data).eq("id", transaction_id).eq("company_id", company_id).execute()
        if not response.data:
            raise HTTPException(status_code=404, detail="Transaction not found")
        return response.data[0]
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/{transaction_id}")
async def delete_transaction(company_id: str, transaction_id: str):
    try:
        # Verify that the transaction exists and belongs to the specified company
        existing_transaction = supabase.table("transactions").select("*").eq("id", transaction_id).eq("company_id", company_id).execute()
        if not existing_transaction.data:
            raise HTTPException(status_code=404, detail="Transaction not found")
        
        response = supabase.table("transactions").delete().eq("id", transaction_id).eq("company_id", company_id).execute()
        if not response.data:
            raise HTTPException(status_code=404, detail="Transaction not found")
        return {"message": "Transaction deleted successfully"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# All specific filtering is now handled by the search endpoints below

@router.post("/search", response_model=List[Transaction])
async def search_transactions(company_id: str, search_params: TransactionSearch):
    """Search transactions with various filters"""
    try:
        query = supabase.table("transactions").select("*").eq("company_id", company_id)
        
        # Apply filters
        if search_params.category_id:
            query = query.eq("category_id", search_params.category_id)
        
        if search_params.payee_id:
            query = query.eq("payee_id", search_params.payee_id)
        
        if search_params.description_contains:
            query = query.ilike("description", f"%{search_params.description_contains}%")
        
        if search_params.date_from:
            query = query.gte("transaction_date", search_params.date_from)
        
        if search_params.date_to:
            query = query.lte("transaction_date", search_params.date_to)
        
        if search_params.min_amount is not None:
            if search_params.transaction_type == "spent":
                query = query.gte("spent", search_params.min_amount)
            elif search_params.transaction_type == "received":
                query = query.gte("received", search_params.min_amount)
            else:
                # For 'all' or None, check either spent or received
                query = query.or_(f"spent.gte.{search_params.min_amount},received.gte.{search_params.min_amount}")
        
        if search_params.max_amount is not None:
            if search_params.transaction_type == "spent":
                query = query.lte("spent", search_params.max_amount)
            elif search_params.transaction_type == "received":
                query = query.lte("received", search_params.max_amount)
            else:
                # For 'all' or None, check either spent or received
                query = query.or_(f"spent.lte.{search_params.max_amount},received.lte.{search_params.max_amount}")
        
        if search_params.transaction_type:
            if search_params.transaction_type == "spent":
                query = query.gt("spent", 0)
            elif search_params.transaction_type == "received":
                query = query.gt("received", 0)
        
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
async def search_transactions_query(
    company_id: str,
    category_id: Optional[str] = Query(None, description="Filter by category ID"),
    payee_id: Optional[str] = Query(None, description="Filter by payee ID"),
    description_contains: Optional[str] = Query(None, description="Description contains this text"),
    date_from: Optional[str] = Query(None, description="Start date (YYYY-MM-DD)"),
    date_to: Optional[str] = Query(None, description="End date (YYYY-MM-DD)"),
    min_amount: Optional[float] = Query(None, description="Minimum amount"),
    max_amount: Optional[float] = Query(None, description="Maximum amount"),
    transaction_type: Optional[str] = Query(None, description="Transaction type: spent, received, or all"),
    limit: Optional[int] = Query(100, description="Maximum number of results"),
    offset: Optional[int] = Query(0, description="Number of results to skip")
):
    """Search transactions using query parameters"""
    try:
        query = supabase.table("transactions").select("*").eq("company_id", company_id)
        
        # Apply filters
        if category_id:
            query = query.eq("category_id", category_id)
        
        if payee_id:
            query = query.eq("payee_id", payee_id)
        
        if description_contains:
            query = query.ilike("description", f"%{description_contains}%")
        
        if date_from:
            query = query.gte("transaction_date", date_from)
        
        if date_to:
            query = query.lte("transaction_date", date_to)
        
        if min_amount is not None:
            if transaction_type == "spent":
                query = query.gte("spent", min_amount)
            elif transaction_type == "received":
                query = query.gte("received", min_amount)
            else:
                query = query.or_(f"spent.gte.{min_amount},received.gte.{min_amount}")
        
        if max_amount is not None:
            if transaction_type == "spent":
                query = query.lte("spent", max_amount)
            elif transaction_type == "received":
                query = query.lte("received", max_amount)
            else:
                query = query.or_(f"spent.lte.{max_amount},received.lte.{max_amount}")
        
        if transaction_type:
            if transaction_type == "spent":
                query = query.gt("spent", 0)
            elif transaction_type == "received":
                query = query.gt("received", 0)
        
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
async def download_transactions(
    company_id: str,
    category_id: Optional[str] = Query(None, description="Filter by category ID"),
    payee_id: Optional[str] = Query(None, description="Filter by payee ID"),
    description_contains: Optional[str] = Query(None, description="Filter by description containing text"),
    date_from: Optional[str] = Query(None, description="Start date (YYYY-MM-DD)"),
    date_to: Optional[str] = Query(None, description="End date (YYYY-MM-DD)"),
    min_amount: Optional[float] = Query(None, description="Minimum amount"),
    max_amount: Optional[float] = Query(None, description="Maximum amount"),
    transaction_type: Optional[str] = Query(None, description="Transaction type: spent, received, or all"),
    format: Optional[str] = Query("json", description="Export format: json or csv")
):
    """Create a temporary download link for transactions with optional filtering"""
    try:
        query = supabase.table("transactions").select("*").eq("company_id", company_id)
        
        # Apply filters
        if category_id:
            query = query.eq("category_id", category_id)
        
        if payee_id:
            query = query.eq("payee_id", payee_id)
        
        if description_contains:
            query = query.ilike("description", f"%{description_contains}%")
        
        if date_from:
            query = query.gte("transaction_date", date_from)
        
        if date_to:
            query = query.lte("transaction_date", date_to)
        
        if min_amount is not None:
            if transaction_type == "spent":
                query = query.gte("spent", min_amount)
            elif transaction_type == "received":
                query = query.gte("received", min_amount)
            else:
                query = query.or_(f"spent.gte.{min_amount},received.gte.{min_amount}")
        
        if max_amount is not None:
            if transaction_type == "spent":
                query = query.lte("spent", max_amount)
            elif transaction_type == "received":
                query = query.lte("received", max_amount)
            else:
                query = query.or_(f"spent.lte.{max_amount},received.lte.{max_amount}")
        
        if transaction_type:
            if transaction_type == "spent":
                query = query.gt("spent", 0)
            elif transaction_type == "received":
                query = query.gt("received", 0)
        
        response = query.execute()
        
        # Generate filename
        filename = f"transactions_{company_id}.{format.lower()}"
        
        if format.lower() == "csv":
            # Create CSV content
            import csv
            import io
            
            output = io.StringIO()
            writer = csv.DictWriter(output, fieldnames=["id", "payee_id", "category_id", "transaction_date", "description", "spent", "received", "company_id", "created_at", "updated_at"])
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

@router.post("/bulk", response_model=List[Transaction])
async def create_transactions_bulk(company_id: str, transactions_data: TransactionBulkCreate):
    """Add multiple new transactions at once"""
    try:
        # Verify that the company exists
        company_response = supabase.table("companies").select("*").eq("id", company_id).execute()
        if not company_response.data:
            raise HTTPException(status_code=404, detail="Company not found")
        
        # Prepare transaction data with company_id and validate each transaction
        transactions_to_insert = []
        for transaction in transactions_data.transactions:
            # Verify that the payee exists and belongs to the specified company (if payee_id is provided)
            if transaction.payee_id:
                payee_response = supabase.table("payees").select("*").eq("id", transaction.payee_id).eq("company_id", company_id).execute()
                if not payee_response.data:
                    raise HTTPException(status_code=404, detail=f"Payee {transaction.payee_id} not found or does not belong to this company")
            
            # Verify that the category exists and belongs to the specified company
            category_response = supabase.table("account_categories").select("*").eq("id", transaction.category_id).eq("company_id", company_id).execute()
            if not category_response.data:
                raise HTTPException(status_code=404, detail=f"Category {transaction.category_id} not found or does not belong to this company")
            
            transaction_data = transaction.dict()
            transaction_data["company_id"] = company_id
            transactions_to_insert.append(transaction_data)
        
        response = supabase.table("transactions").insert(transactions_to_insert).execute()
        if not response.data:
            raise HTTPException(status_code=500, detail="Failed to create transactions")
        return response.data
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/bulk")
async def delete_transactions_bulk(company_id: str, bulk_delete: TransactionBulkDelete):
    """Delete multiple transactions at once"""
    try:
        # Verify that all transactions exist and belong to the specified company
        for transaction_id in bulk_delete.transaction_ids:
            existing_transaction = supabase.table("transactions").select("*").eq("id", transaction_id).eq("company_id", company_id).execute()
            if not existing_transaction.data:
                raise HTTPException(status_code=404, detail=f"Transaction {transaction_id} not found")
        
        # Delete all transactions
        deleted_count = 0
        for transaction_id in bulk_delete.transaction_ids:
            response = supabase.table("transactions").delete().eq("id", transaction_id).eq("company_id", company_id).execute()
            if response.data:
                deleted_count += 1
        
        return {"message": f"Successfully deleted {deleted_count} transactions"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
