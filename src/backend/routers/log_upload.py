from fastapi import APIRouter, UploadFile, File, HTTPException, status
from typing import List
import os
from libs.log_parser import parse_mavlink_log_bytes
from config.db import SessionLocal
from config.models import LogMetadata, ParsedTelemetry, Base
import datetime
import json

router = APIRouter()

ALLOWED_EXTENSIONS = {'.bin', '.log'}
MAX_FILE_SIZE_MB = 100  # Adjust as needed

@router.post("/logs/upload")
async def upload_log_file(file: UploadFile = File(...)):
    """
    Endpoint for uploading UAV log files. Validates file extension and size, parses the log, and stores results in the database.
    """
    filename = file.filename
    ext = os.path.splitext(filename)[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid file extension: {ext}. Only .bin and .log files are allowed."
        )
    contents = await file.read()
    size_mb = len(contents) / (1024 * 1024)
    if size_mb > MAX_FILE_SIZE_MB:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File too large: {size_mb:.2f} MB. Max allowed is {MAX_FILE_SIZE_MB} MB."
        )
    # Parse the log file using pymavlink
    parse_result = parse_mavlink_log_bytes(contents)
    if parse_result["status"] != "success":
        raise HTTPException(status_code=400, detail=f"Log parsing failed: {parse_result.get('error')}")

    # Store log metadata and parsed telemetry in the database
    db = SessionLocal()
    try:
        log_meta = LogMetadata(
            filename=filename,
            upload_time=datetime.datetime.now(datetime.UTC),
            notes="Uploaded via API"
        )
        db.add(log_meta)
        db.commit()
        db.refresh(log_meta)
        log_id = log_meta.id
        # Store each message type count as a dummy telemetry row (for demo)
        # In a real implementation, you would store each message instance with its timestamp and data
        for msg_type, count in parse_result["message_counts"].items():
            db.add(ParsedTelemetry(
                log_id=log_id,
                message_type=msg_type,
                timestamp=0.0,  # Placeholder, real parser should extract timestamp
                data={"count": count}
            ))
        db.commit()
        return {
            "filename": filename,
            "size_mb": f"{size_mb:.2f}",
            "log_id": log_id,
            "message": f"Log and {len(parse_result['message_counts'])} message types stored in database."
        }
    finally:
        db.close() 