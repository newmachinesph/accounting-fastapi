import asyncio
import time
from datetime import datetime
from typing import Dict, Any
from fastapi import APIRouter, Depends
from supabase import Client
from api.models.responses import HealthResponse
import os
import psutil

router = APIRouter(prefix="/health", tags=["health"])

async def check_database_health() -> Dict[str, Any]:
    """Check database connectivity and performance"""
    try:
        from supabase import create_client
        supabase: Client = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_KEY"))
        
        start_time = time.time()
        # Simple connectivity test
        response = supabase.table("companies").select("id").limit(1).execute()
        query_time = (time.time() - start_time) * 1000
        
        return {
            "status": "healthy",
            "response_time_ms": round(query_time, 2),
            "connection": "active"
        }
    except Exception as e:
        return {
            "status": "unhealthy",
            "error": str(e),
            "connection": "failed"
        }

async def check_openai_health() -> Dict[str, Any]:
    """Check OpenAI API connectivity"""
    try:
        from openai import OpenAI
        client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        
        start_time = time.time()
        # Test with minimal request
        response = client.models.list()
        response_time = (time.time() - start_time) * 1000
        
        return {
            "status": "healthy",
            "response_time_ms": round(response_time, 2),
            "models_available": len(response.data) if hasattr(response, 'data') else 0
        }
    except Exception as e:
        return {
            "status": "unhealthy",
            "error": str(e)
        }

def get_system_metrics() -> Dict[str, Any]:
    """Get system performance metrics"""
    try:
        return {
            "cpu_percent": psutil.cpu_percent(interval=1),
            "memory_percent": psutil.virtual_memory().percent,
            "disk_percent": psutil.disk_usage('/').percent,
            "load_average": psutil.getloadavg() if hasattr(psutil, 'getloadavg') else None
        }
    except Exception:
        return {"status": "metrics_unavailable"}

@router.get("/", response_model=HealthResponse)
async def health_check():
    """Comprehensive health check endpoint"""
    start_time = time.time()
    
    # Run health checks concurrently
    db_health, openai_health = await asyncio.gather(
        check_database_health(),
        check_openai_health(),
        return_exceptions=True
    )
    
    # Handle exceptions from gather
    if isinstance(db_health, Exception):
        db_health = {"status": "error", "error": str(db_health)}
    if isinstance(openai_health, Exception):
        openai_health = {"status": "error", "error": str(openai_health)}
    
    system_metrics = get_system_metrics()
    total_time = (time.time() - start_time) * 1000
    
    # Determine overall status
    overall_status = "healthy"
    if db_health.get("status") != "healthy":
        overall_status = "degraded"
    if openai_health.get("status") != "healthy" and overall_status == "healthy":
        overall_status = "degraded"
    
    return HealthResponse(
        status=overall_status,
        timestamp=datetime.now(),
        version="1.0.0",
        database=db_health.get("status", "unknown"),
        dependencies={
            "supabase": db_health,
            "openai": openai_health,
            "system": system_metrics,
            "health_check_time_ms": round(total_time, 2)
        }
    )

@router.get("/ready")
async def readiness_check():
    """Kubernetes readiness probe - quick check"""
    try:
        db_health = await check_database_health()
        if db_health.get("status") == "healthy":
            return {"status": "ready"}
        else:
            return {"status": "not_ready", "reason": "database_unavailable"}
    except Exception as e:
        return {"status": "not_ready", "reason": str(e)}

@router.get("/live")
async def liveness_check():
    """Kubernetes liveness probe - minimal check"""
    return {"status": "alive", "timestamp": datetime.now().isoformat()}
