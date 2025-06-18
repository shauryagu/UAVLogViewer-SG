from fastapi import APIRouter, UploadFile, File, HTTPException, status, Query
from typing import List, Optional
import os
import json
import datetime
from libs.log_parser import parse_mavlink_log_bytes
from config.db import SessionLocal
from config.models import LogMetadata, ParsedTelemetry, Base

router = APIRouter()

ALLOWED_EXTENSIONS = {'.bin', '.log'}
MAX_FILE_SIZE_MB = 100  # Adjust as needed

@router.post("/logs/upload")
async def upload_log_file(
    file: UploadFile = File(...),
    session_id: Optional[str] = Query(None, description="Optional chat session ID to link this file to"),
    user_id: Optional[str] = Query(None, description="Optional user ID for session creation"),
    max_messages: int = Query(1000, description="Maximum number of messages to store (for demo purposes)")
):
    """
    Endpoint for uploading UAV log files. Validates file extension and size, parses the log, 
    and stores results in the database. Optionally links to a chat session or creates a new one.
    """
    try:
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

        db = SessionLocal()
        try:
            log_meta = LogMetadata(
                filename=filename,
                upload_time=datetime.datetime.utcnow(),
                notes="Uploaded via API"
            )
            db.add(log_meta)
            db.commit()
            db.refresh(log_meta)
            log_id = log_meta.id
            
            # Store limited number of messages for demo purposes
            messages_to_store = parse_result["messages"][:max_messages]
            for msg in messages_to_store:
                # Ensure all data is JSON serializable
                safe_data = {}
                for key, value in msg["data"].items():
                    try:
                        # Convert numpy arrays and other non-serializable types to lists
                        if hasattr(value, 'tolist'):
                            safe_data[key] = value.tolist()
                        elif isinstance(value, (list, tuple)):
                            safe_data[key] = [x.tolist() if hasattr(x, 'tolist') else x for x in value]
                        else:
                            safe_data[key] = value
                    except (TypeError, AttributeError):
                        # If conversion fails, convert to string as fallback
                        safe_data[key] = str(value)
                
                db.add(ParsedTelemetry(
                    log_id=log_id,
                    message_type=msg["message_type"],
                    timestamp=msg["timestamp"],
                    data=safe_data
                ))
            db.commit()
            
            response_data = {
                "filename": filename,
                "size_mb": f"{size_mb:.2f}",
                "log_id": log_id,
                "total_messages_parsed": parse_result['total_messages'],
                "messages_stored": len(messages_to_store),
                "message": f"Log parsed ({parse_result['total_messages']} messages) and {len(messages_to_store)} messages stored in database."
            }
            
            # Handle chat session linking
            if session_id:
                # Try to link to existing session
                try:
                    import asyncpg
                    import json
                    
                    # Quick connection to update session
                    conn = await asyncpg.connect(os.getenv(
                        "DATABASE_URL", 
                        "postgresql://uavuser:sRinathSai%$8970@localhost:5432/uavlogviewer"
                    ))
                    
                    # Check if session exists
                    session_exists = await conn.fetchval(
                        'SELECT 1 FROM chat_sessions WHERE session_id = $1', session_id
                    )
                    
                    if session_exists:
                        # Update existing session with file_id
                        current_metadata = await conn.fetchval(
                            'SELECT metadata FROM chat_sessions WHERE session_id = $1', session_id
                        )
                        
                        # Merge metadata
                        existing_meta = json.loads(current_metadata) if current_metadata else {}
                        existing_meta.update({
                            "uploaded_file": filename,
                            "upload_time": datetime.datetime.utcnow().isoformat()
                        })
                        
                        await conn.execute('''
                            UPDATE chat_sessions 
                            SET file_id = $1, metadata = $2, last_activity = NOW()
                            WHERE session_id = $3
                        ''', str(log_id), json.dumps(existing_meta), session_id)
                        
                        response_data["session_id"] = session_id
                        response_data["session_status"] = "linked_to_existing"
                        
                        print(f"Successfully linked file {log_id} to existing session {session_id}")
                    else:
                        print(f"Session {session_id} does not exist, will create new one")
                        # Session doesn't exist, we'll create one below
                        session_id = None
                        
                    await conn.close()
                    
                except Exception as e:
                    print(f"Error linking to session: {e}")
                    import traceback
                    traceback.print_exc()
                    # Continue without session linking
                    response_data["session_link_error"] = str(e)
                    session_id = None
            
            # Create new session if no session_id provided or linking failed
            if not session_id:
                try:
                    from libs.session_manager import SessionManager
                    
                    # Create new session linked to this file
                    session_manager = SessionManager()
                    await session_manager.initialize()
                    
                    new_session = await session_manager.create_session(
                        user_id=user_id,
                        file_id=str(log_id),
                        metadata={
                            "uploaded_file": filename,
                            "upload_time": datetime.datetime.utcnow().isoformat(),
                            "auto_created": True
                        }
                    )
                    
                    await session_manager.close()
                    
                    response_data["session_id"] = new_session.session_id
                    response_data["session_status"] = "created_new"
                    
                except Exception as e:
                    print(f"Error creating session: {e}")
                    # Continue without session creation
                    response_data["session_status"] = "no_session_created"
                    response_data["session_creation_error"] = str(e)
            
            return response_data
            
        finally:
            db.close()
            
    except HTTPException:
        raise
    except Exception as e:
        import traceback
        print(f"Upload error: {e}")
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Upload failed: {str(e)}")

@router.post("/logs/upload-simple")
async def upload_log_file_simple(file: UploadFile = File(...)):
    """Simple upload endpoint for debugging."""
    try:
        filename = file.filename
        ext = os.path.splitext(filename)[1].lower()
        if ext not in ALLOWED_EXTENSIONS:
            return {"error": f"Invalid extension {ext}"}
        
        contents = await file.read()
        size_mb = len(contents) / (1024 * 1024)
        
        return {
            "filename": filename,
            "size_mb": f"{size_mb:.2f}",
            "message": "Simple upload successful"
        }
    except Exception as e:
        return {"error": str(e)}

@router.get("/logs")
async def list_logs():
    """List all uploaded log files with their metadata."""
    db = SessionLocal()
    try:
        logs = db.query(LogMetadata).order_by(LogMetadata.upload_time.desc()).all()
        return [
            {
                "id": log.id,
                "filename": log.filename,
                "upload_time": log.upload_time.isoformat(),
                "vehicle_type": log.vehicle_type,
                "notes": log.notes
            }
            for log in logs
        ]
    finally:
        db.close()

@router.get("/logs/{log_id}")
async def get_log_details(log_id: int):
    """Get details for a specific log file."""
    db = SessionLocal()
    try:
        log = db.query(LogMetadata).filter(LogMetadata.id == log_id).first()
        if not log:
            raise HTTPException(status_code=404, detail="Log not found")
        
        # Get message type summary
        message_summary = db.query(ParsedTelemetry.message_type, db.func.count(ParsedTelemetry.id).label('count')).filter(
            ParsedTelemetry.log_id == log_id
        ).group_by(ParsedTelemetry.message_type).order_by(db.text('count DESC')).all()
        
        return {
            "id": log.id,
            "filename": log.filename,
            "upload_time": log.upload_time.isoformat(),
            "vehicle_type": log.vehicle_type,
            "notes": log.notes,
            "message_types": [
                {"type": row.message_type, "count": row.count}
                for row in message_summary
            ],
            "total_messages": sum(row.count for row in message_summary)
        }
    finally:
        db.close()

@router.post("/logs/upload-parse-test")
async def upload_log_file_parse_test(file: UploadFile = File(...)):
    """Upload endpoint with parsing test for debugging."""
    try:
        filename = file.filename
        ext = os.path.splitext(filename)[1].lower()
        if ext not in ALLOWED_EXTENSIONS:
            return {"error": f"Invalid extension {ext}"}
        
        contents = await file.read()
        size_mb = len(contents) / (1024 * 1024)
        
        # Test log parsing
        parse_result = parse_mavlink_log_bytes(contents)
        if parse_result["status"] != "success":
            return {"error": f"Parsing failed: {parse_result.get('error')}"}
        
        return {
            "filename": filename,
            "size_mb": f"{size_mb:.2f}",
            "parse_status": parse_result["status"],
            "message_count": parse_result.get("total_messages", 0),
            "message": "Upload and parsing successful"
        }
    except Exception as e:
        import traceback
        return {"error": str(e), "traceback": traceback.format_exc()}

@router.post("/logs/upload-db-test")
async def upload_log_file_db_test(file: UploadFile = File(...)):
    """Upload endpoint with database test for debugging."""
    try:
        filename = file.filename
        ext = os.path.splitext(filename)[1].lower()
        if ext not in ALLOWED_EXTENSIONS:
            return {"error": f"Invalid extension {ext}"}
        
        contents = await file.read()
        size_mb = len(contents) / (1024 * 1024)
        
        # Test log parsing
        parse_result = parse_mavlink_log_bytes(contents)
        if parse_result["status"] != "success":
            return {"error": f"Parsing failed: {parse_result.get('error')}"}
        
        # Test database operations
        db = SessionLocal()
        try:
            log_meta = LogMetadata(
                filename=filename,
                upload_time=datetime.datetime.utcnow(),
                notes="DB Test upload"
            )
            db.add(log_meta)
            db.commit()
            db.refresh(log_meta)
            log_id = log_meta.id
            
            # Store first 10 messages only for testing
            message_count = 0
            for msg in parse_result["messages"][:10]:
                db.add(ParsedTelemetry(
                    log_id=log_id,
                    message_type=msg["message_type"],
                    timestamp=msg["timestamp"],
                    data=msg["data"]
                ))
                message_count += 1
            db.commit()
            
            return {
                "filename": filename,
                "size_mb": f"{size_mb:.2f}",
                "log_id": log_id,
                "messages_stored": message_count,
                "message": "Upload, parsing, and DB operations successful"
            }
            
        finally:
            db.close()
            
    except Exception as e:
        import traceback
        return {"error": str(e), "traceback": traceback.format_exc()} 