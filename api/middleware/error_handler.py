import traceback
import uuid
from datetime import datetime
from fastapi import Request, HTTPException
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response
import logging

logger = logging.getLogger(__name__)

class ErrorHandlerMiddleware(BaseHTTPMiddleware):
    """Global error handler middleware for consistent error responses"""
    
    async def dispatch(self, request: Request, call_next) -> Response:
        request_id = str(uuid.uuid4())
        request.state.request_id = request_id
        
        try:
            response = await call_next(request)
            return response
        except HTTPException as e:
            return JSONResponse(
                status_code=e.status_code,
                content={
                    "success": False,
                    "error": "HTTP_ERROR",
                    "message": e.detail,
                    "status_code": e.status_code,
                    "timestamp": datetime.now().isoformat(),
                    "request_id": request_id,
                    "path": str(request.url.path)
                }
            )
        except ValueError as e:
            logger.error(f"Validation error in request {request_id}: {str(e)}")
            return JSONResponse(
                status_code=422,
                content={
                    "success": False,
                    "error": "VALIDATION_ERROR",
                    "message": "Invalid input data",
                    "details": str(e),
                    "timestamp": datetime.now().isoformat(),
                    "request_id": request_id,
                    "path": str(request.url.path)
                }
            )
        except Exception as e:
            logger.error(f"Unexpected error in request {request_id}: {str(e)}\n{traceback.format_exc()}")
            return JSONResponse(
                status_code=500,
                content={
                    "success": False,
                    "error": "INTERNAL_SERVER_ERROR",
                    "message": "An unexpected error occurred",
                    "timestamp": datetime.now().isoformat(),
                    "request_id": request_id,
                    "path": str(request.url.path)
                }
            )

class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """Middleware for request/response logging and metrics"""
    
    async def dispatch(self, request: Request, call_next) -> Response:
        start_time = datetime.now()
        
        # Log request
        logger.info(f"Request: {request.method} {request.url.path} - ID: {getattr(request.state, 'request_id', 'unknown')}")
        
        response = await call_next(request)
        
        # Calculate duration
        duration = (datetime.now() - start_time).total_seconds() * 1000
        
        # Log response
        logger.info(f"Response: {response.status_code} - Duration: {duration:.2f}ms - ID: {getattr(request.state, 'request_id', 'unknown')}")
        
        # Add request ID to response headers
        response.headers["X-Request-ID"] = getattr(request.state, 'request_id', 'unknown')
        response.headers["X-Response-Time"] = f"{duration:.2f}ms"
        
        return response
