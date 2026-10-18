from fastapi import APIRouter, HTTPException
from typing import List
from supabase import Client
from .models import Company, CompanyCreate, CompanyUpdate
import os
from dotenv import load_dotenv
from supabase import create_client

# Load environment variables
load_dotenv()

# Initialize Supabase client
supabase: Client = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_KEY"))

# Create router
router = APIRouter(
    prefix="/companies",
    tags=["companies"]
)

# Company CRUD endpoints
@router.get("/", response_model=List[Company])
async def get_companies():
    try:
        response = supabase.table("companies").select("*").execute()
        return response.data
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/{company_id}", response_model=Company)
async def get_company(company_id: str):
    try:
        response = supabase.table("companies").select("*").eq("id", company_id).execute()
        if not response.data:
            raise HTTPException(status_code=404, detail="Company not found")
        return response.data[0]
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/", response_model=Company)
async def create_company(company: CompanyCreate):
    try:
        response = supabase.table("companies").insert({
            "name": company.name,
            "description": company.description
        }).execute()
        if not response.data:
            raise HTTPException(status_code=500, detail="Failed to create company")
        return response.data[0]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.put("/{company_id}", response_model=Company)
async def update_company(company_id: str, company: CompanyUpdate):
    try:
        update_data = {}
        if company.name is not None:
            update_data["name"] = company.name
        if company.description is not None:
            update_data["description"] = company.description
            
        response = supabase.table("companies").update(update_data).eq("id", company_id).execute()
        if not response.data:
            raise HTTPException(status_code=404, detail="Company not found")
        return response.data[0]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/{company_id}")
async def delete_company(company_id: str):
    try:
        response = supabase.table("companies").delete().eq("id", company_id).execute()
        if not response.data:
            raise HTTPException(status_code=404, detail="Company not found")
        return {"message": "Company deleted successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/{company_id}/financial-summary")
async def get_financial_summary(company_id: str, date_from: str = None, date_to: str = None):
    """Get financial summary with revenue, expenses, and net income"""
    try:
        # First verify company exists
        company_response = supabase.table("companies").select("*").eq("id", company_id).execute()
        if not company_response.data:
            raise HTTPException(status_code=404, detail="Company not found")

        # Build query for transactions
        query = supabase.table("transactions").select("spent, received, category_id").eq("company_id", company_id)
        
        # Add date filters if provided
        if date_from:
            query = query.gte("transaction_date", date_from)
        if date_to:
            query = query.lte("transaction_date", date_to)
            
        transactions_response = query.execute()
        transactions = transactions_response.data

        # Get categories to determine revenue vs expense
        categories_response = supabase.table("account_categories").select("id, type").eq("company_id", company_id).execute()
        categories = {cat['id']: cat['type'] for cat in categories_response.data}

        # Calculate totals
        total_revenue = 0
        total_expenses = 0

        for transaction in transactions:
            category_type = categories.get(transaction['category_id'], 'Expense')
            spent = float(transaction.get('spent', 0) or 0)
            received = float(transaction.get('received', 0) or 0)

            if category_type.lower() in ['revenue', 'income']:
                total_revenue += received
                total_expenses += spent
            else:
                total_expenses += spent
                total_revenue += received

        net_income = total_revenue - total_expenses

        return {
            "revenue": total_revenue,
            "expenses": total_expenses,
            "net_income": net_income,
            "transactions_count": len(transactions)
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
