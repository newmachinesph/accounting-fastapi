from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from openai import OpenAI
from dotenv import load_dotenv
from supabase import create_client, Client
import os
import json
import logging
from contextlib import asynccontextmanager

# Accounting agent removed - using FastMCP server instead
# from api.agent.accounting_agent import AccountingAgent

# Import routers
from api.companies.router import router as companies_router
from api.categories.router import router as categories_router
from api.payees.router import router as payees_router
from api.transactions.router import router as transactions_router
from api.core.health import router as health_router

# Import middleware
from api.middleware.error_handler import ErrorHandlerMiddleware, RequestLoggingMiddleware
from api.middleware.rate_limiting import RateLimitMiddleware

# Import temp download manager
from temp_downloads import temp_download_manager

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler("api.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Initialize OpenAI client
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# Initialize Supabase client
supabase: Client = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_KEY"))

# Accounting agent removed - using FastMCP server instead
# accounting_agent = AccountingAgent(client)

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan management"""
    # Startup
    logger.info("Starting AI Chat Accounting API...")
    logger.info("Initializing database connections...")
    logger.info("Setting up temporary download manager...")
    
    # Accounting agent removed - using FastMCP server instead
    logger.info("FastAPI backend ready - accounting features available via FastMCP server")
    
    yield
    
    # Shutdown
    logger.info("Shutting down AI Chat Accounting API...")
    logger.info("Cleaning up temporary files...")
    temp_download_manager.cleanup_expired()
    
    # No accounting agent cleanup needed - using FastMCP server instead
    logger.info("Shutdown complete")

# Create FastAPI app with modern configuration
app = FastAPI(
    title="AI Chat Accounting API",
    description="Modern accounting API with AI integration and secure file downloads",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    lifespan=lifespan,
    # Security headers
    swagger_ui_oauth2_redirect_url="/docs/oauth2-redirect",
    servers=[
        {"url": "http://localhost:8000", "description": "Development server"},
        {"url": "https://api.yourdomain.com", "description": "Production server"}
    ]
)

# Security Middleware (order matters!)
app.add_middleware(
    TrustedHostMiddleware,
    allowed_hosts=["localhost", "127.0.0.1", "0.0.0.0", "*", "*.yourdomain.com"]
)

# Compression middleware
app.add_middleware(GZipMiddleware, minimum_size=1000)

# Rate limiting middleware
app.add_middleware(RateLimitMiddleware, requests_per_minute=100, burst_limit=20)

# Request logging middleware  
app.add_middleware(RequestLoggingMiddleware)

# Error handling middleware (should be last)
app.add_middleware(ErrorHandlerMiddleware)

# CORS middleware - Allow all origins for development (including file:// for local HTML files)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allow all origins for development
    allow_credentials=False,  # Must be False when allow_origins=["*"]
    allow_methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"],
    allow_headers=["*"],
    expose_headers=["X-Request-ID", "X-Response-Time", "X-RateLimit-Remaining"]
)

# Include routers
app.include_router(health_router)  # Health checks first
app.include_router(companies_router)
# Include sub-routers under companies
app.include_router(categories_router)
app.include_router(payees_router)
app.include_router(transactions_router)

# Root endpoint
@app.get("/")
async def root():
    return {"message": "AI Chat Accounting API", "version": "1.0.0", "docs": "/docs"}

# Temporary download endpoint
@app.get("/download/{token}")
async def download_temp_file(token: str):
    """Download a temporary file using a secure token"""
    try:
        # Clean up expired downloads first
        temp_download_manager.cleanup_expired()
        
        # Get download info
        download_info = temp_download_manager.get_download(token)
        if not download_info:
            raise HTTPException(status_code=404, detail="Download not found or expired")
        
        # Return the file
        return FileResponse(
            path=download_info["file_path"],
            filename=download_info["filename"],
            media_type=download_info["content_type"],
            headers={"Content-Disposition": f"attachment; filename={download_info['filename']}"}
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# Download cleanup endpoint (optional - for manual cleanup)
@app.post("/download/cleanup")
async def cleanup_expired_downloads():
    """Manually clean up expired downloads"""
    try:
        cleaned_count = temp_download_manager.cleanup_expired()
        return {"message": f"Cleaned up {cleaned_count} expired downloads"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# Chat endpoints removed - AI features now available via FastMCP server
# For AI accounting assistance, use the FastMCP server with any MCP-compatible client
# The FastMCP server provides 39 comprehensive tools covering all accounting operations

if __name__ == "__main__":
    import uvicorn
    import sys
    
    # Check for port argument
    port = 8000  # Default to 8001 to avoid conflicts
    if len(sys.argv) > 1 and sys.argv[1].startswith("--port"):
        try:
            port = int(sys.argv[1].split("=")[1] if "=" in sys.argv[1] else sys.argv[2])
        except:
            port = 8000
    
    print(f"Starting server on port {port}")
    uvicorn.run(app, host="0.0.0.0", port=port)
