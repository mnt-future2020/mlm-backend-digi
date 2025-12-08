"""
MLM VSV Unite Application
Main entry point
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.core.config import settings

# Create FastAPI app
app = FastAPI(
    title="MLM VSV Unite API",
    description="Multi-Level Marketing Platform API",
    version="1.0.0"
)

# CORS Configuration
cors_origins = settings.CORS_ORIGINS
if cors_origins == "*":
    allowed_origins = ["*"]
else:
    allowed_origins = cors_origins.split(",")

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Import all routes from old server.py temporarily
# This allows gradual migration
import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

# Import the old server module and copy its routes
from server import app as old_app

# Copy all routes from old app to new app
app.router.routes = old_app.router.routes

# Health check endpoint
@app.get("/api/health")
async def health_check():
    """Check API health"""
    from app.core.database import users_collection
    from datetime import datetime
    try:
        users_collection.find_one()
        return {
            "status": "healthy",
            "database": "connected",
            "timestamp": datetime.utcnow().isoformat()
        }
    except Exception as e:
        return {
            "status": "unhealthy",
            "database": "disconnected",
            "error": str(e),
            "timestamp": datetime.utcnow().isoformat()
        }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8001, reload=True)
