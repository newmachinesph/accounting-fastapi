import os
import uuid
from datetime import datetime, timezone
from supabase import create_client, Client

# Environment setup
SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_KEY = os.environ["SUPABASE_KEY"]

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# 21 default categories
default_categories = [
    ("Current Assets", "Asset", None),
    ("Fixed Assets", "Asset", None),
    ("Equipment", "Asset", "Fixed Assets"),
    ("Merchandise", "COGS", None),
    ("Owner's Equity", "Equity", None),
    ("Owner's Distribution", "Equity", "Owner's Equity"),
    ("Owner's Investment", "Equity", "Owner's Equity"),
    ("Meals & Entertainment", "Expense", None),
    ("Operating Expenses", "Expense", None),
    ("Bank Charges", "Expense", "Operating Expenses"),
    ("Software", "Expense", "Operating Expenses"),
    ("Supplies", "Expense", "Operating Expenses"),
    ("Payroll Expenses", "Expense", None),
    ("Payroll Taxes", "Expense", "Payroll Expenses"),
    ("Payroll Wages", "Expense", "Payroll Expenses"),
    ("Travel", "Expense", None),
    ("Airfare", "Expense", "Travel"),
    ("Lodging", "Expense", "Travel"),
    ("Current Liabilities", "Liability", None),
    ("Sales", "Revenue", None),
    ("Discounts", "Revenue", "Sales")
]

# 18 default payees
default_payees = [
    "Adobe",
    "ADP",
    "Amazon",
    "Apple",
    "Costco",
    "Delta Airlines",
    "Gusto",
    "Home Depot",
    "Lowe's",
    "Microsoft",
    "PayPal",
    "Square",
    "Starbucks",
    "Stripe",
    "Switch",
    "Tesla",
    "Uber",
    "Zoom"
]

def create_company_with_categories(description: str = None):
    # Generate a default company name with timestamp
    company_name = f"Company_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    # 1. Create company
    company_id = str(uuid.uuid4())
    company_resp = supabase.table("companies").insert({
        "id": company_id,
        "name": company_name,
        "description": description,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat()
    }).execute()

    if hasattr(company_resp, 'error') and company_resp.error:
        raise Exception(f"Error creating company: {company_resp.error}")
    elif not hasattr(company_resp, 'error'):
        # New API response format - check if data was inserted
        if not company_resp.data:
            raise Exception("Error creating company: No data returned")

    # 2. Create category ID map to resolve parent-child relationships
    name_to_id = {}
    rows_to_insert = []
    for name, type_, parent_name in default_categories:
        cat_id = str(uuid.uuid4())
        name_to_id[name] = cat_id
        parent_id = name_to_id.get(parent_name)
        rows_to_insert.append({
            "id": cat_id,
            "company_id": company_id,
            "name": name,
            "type": type_,
            "parent_id": parent_id,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat()
        })

    # 3. Bulk insert categories
    for chunk_start in range(0, len(rows_to_insert), 10):  # handle chunking if needed
        chunk = rows_to_insert[chunk_start:chunk_start+10]
        category_resp = supabase.table("account_categories").insert(chunk).execute()
        if hasattr(category_resp, 'error') and category_resp.error:
            raise Exception(f"Error inserting categories: {category_resp.error}")
        elif not hasattr(category_resp, 'error'):
            # New API response format - check if data was inserted
            if not category_resp.data:
                raise Exception("Error inserting categories: No data returned")

    print(f"Company '{company_name}' and 21 default categories created successfully.")
    
    # 4. Create default payees
    create_default_payees(company_id)
    
    # 5. Create initial transactions for July 2025
    create_initial_transactions(company_id)
    
    return company_id

def create_default_payees(company_id: str):
    """Create default payees for a company"""
    rows_to_insert = []
    for name in default_payees:
        rows_to_insert.append({
            "id": str(uuid.uuid4()),
            "company_id": company_id,
            "name": name,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat()
        })

    # 5. Bulk insert payees
    for chunk_start in range(0, len(rows_to_insert), 10):  # handle chunking if needed
        chunk = rows_to_insert[chunk_start:chunk_start+10]
        payee_resp = supabase.table("payees").insert(chunk).execute()
        if hasattr(payee_resp, 'error') and payee_resp.error:
            raise Exception(f"Error inserting payees: {payee_resp.error}")
        elif not hasattr(payee_resp, 'error'):
            # New API response format - check if data was inserted
            if not payee_resp.data:
                raise Exception("Error inserting payees: No data returned")
    
    print(f"18 default payees created successfully.")

def create_initial_transactions(company_id: str):
    """Create initial transactions for July 2025"""
    # Fetch payees and categories from the database
    payees_resp = supabase.table("payees").select("id").eq("company_id", company_id).execute()
    categories_resp = supabase.table("account_categories").select("id").eq("company_id", company_id).execute()
    
    if not payees_resp.data or not categories_resp.data:
        raise Exception("Error fetching payees or categories for transactions")
    
    payee_ids = [payee["id"] for payee in payees_resp.data]
    category_ids = [category["id"] for category in categories_resp.data]
    
    # Generate 100+ transactions for July 2025
    rows_to_insert = []
    for i in range(105):  # Create 105 transactions to ensure we have at least 100
        # Randomly select a payee and category
        payee_id = payee_ids[i % len(payee_ids)]
        category_id = category_ids[i % len(category_ids)]
        
        # Generate a random date in July 2025
        day = (i % 31) + 1
        transaction_date = f"2025-07-{day:02d}"
        
        # Generate random spent/received amounts
        # For simplicity, we'll make about 70% expenses (spent) and 30% income (received)
        if i % 3 == 0:  # 30% chance of income
            spent = 0.00
            received = round(100 + (i * 10.5), 2)  # Random received amount
            description = f"Income transaction {i+1}"
        else:  # 70% chance of expense
            spent = round(10 + (i * 2.75), 2)  # Random spent amount
            received = 0.00
            description = f"Expense transaction {i+1}"
        
        rows_to_insert.append({
            "id": str(uuid.uuid4()),
            "company_id": company_id,
            "payee_id": payee_id,
            "category_id": category_id,
            "transaction_date": transaction_date,
            "description": description,
            "spent": spent,
            "received": received,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat()
        })

    # Bulk insert transactions
    for chunk_start in range(0, len(rows_to_insert), 10):  # handle chunking if needed
        chunk = rows_to_insert[chunk_start:chunk_start+10]
        transaction_resp = supabase.table("transactions").insert(chunk).execute()
        if hasattr(transaction_resp, 'error') and transaction_resp.error:
            raise Exception(f"Error inserting transactions: {transaction_resp.error}")
        elif not hasattr(transaction_resp, 'error'):
            # New API response format - check if data was inserted
            if not transaction_resp.data:
                raise Exception("Error inserting transactions: No data returned")
    
    print(f"105 initial transactions for July 2025 created successfully.")

# Example usage:
# create_company_with_categories("My New Company", "Company with default categories")

if __name__ == "__main__":
    create_company_with_categories("Auto-generated company with default categories")
