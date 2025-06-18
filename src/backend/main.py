from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic_settings import BaseSettings
import os
from routers import log_upload, telemetry, chat
from config.models import Base
from config.db import engine
from libs.session_manager import SessionManager
from libs.telemetry_service import TelemetryService

# Pydantic settings for configuration
class Settings(BaseSettings):
    app_name: str = "UAV Log Viewer Backend"
    debug: bool = os.getenv("DEBUG", "False").lower() == "true"
    database_url: str = os.getenv("DATABASE_URL", "postgresql://uavuser:sRinathSai%$8970@localhost:5432/uavlogviewer")

    class Config:
        env_file = ".env"

settings = Settings()

# Create database tables
Base.metadata.create_all(bind=engine)

app = FastAPI(title=settings.app_name, debug=settings.debug)

# Initialize services
session_manager = SessionManager()
telemetry_service = TelemetryService()

@app.on_event("startup")
async def startup_event():
    """Initialize services on startup."""
    print("Initializing UAV Log Viewer services...")
    await session_manager.initialize()
    await telemetry_service.initialize()
    print("Services initialized successfully")

@app.on_event("shutdown")
async def shutdown_event():
    """Clean up services on shutdown."""
    print("Shutting down UAV Log Viewer services...")
    await session_manager.close()
    await telemetry_service.close()
    print("Services shut down successfully")

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Adjust as needed for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Root endpoint
@app.get("/")
async def root():
    return {"message": "UAV Log Viewer API - Ready for flight log analysis!"}

# Include UAV-specific routers
app.include_router(log_upload.router, prefix="/api", tags=["logs"])
app.include_router(telemetry.router, prefix="/api", tags=["telemetry"])
app.include_router(chat.router, prefix="/api", tags=["chat"])

# from routers import log_upload, telemetry
# app.include_router(log_upload.router)
# app.include_router(telemetry.router) 

# Create tables
Base.metadata.create_all(bind=engine) 