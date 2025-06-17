from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic_settings import BaseSettings
import os

# Pydantic settings for configuration
class Settings(BaseSettings):
    app_name: str = "UAV Log Viewer Backend"
    debug: bool = os.getenv("DEBUG", "False").lower() == "true"
    database_url: str = os.getenv("DATABASE_URL", "postgresql://uavuser:sRinathSai%$8970@localhost:5432/uavlogviewer")

    class Config:
        env_file = ".env"

settings = Settings()

app = FastAPI(title=settings.app_name, debug=settings.debug)

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
    return {"message": "UAV Log Viewer Backend: Use /logs/upload to upload UAV log files and /telemetry to query parsed telemetry data."}

# Include UAV-specific routers
from routers import log_upload
app.include_router(log_upload.router)
from routers import telemetry
app.include_router(telemetry.router)

# from routers import log_upload, telemetry
# app.include_router(log_upload.router)
# app.include_router(telemetry.router) 