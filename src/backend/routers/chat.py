from fastapi import APIRouter, WebSocket, WebSocketDisconnect, HTTPException, status
from libs.llm_client import LLMClient
from libs.session_manager import SessionManager
from libs.telemetry_service import TelemetryService
from pydantic import BaseModel
from typing import Optional, Dict, Any, List
import json
import uuid
from datetime import datetime

router = APIRouter()

# Initialize services
session_manager = SessionManager()
telemetry_service = TelemetryService()

# Pydantic models for REST endpoints
class CreateSessionRequest(BaseModel):
    user_id: Optional[str] = None
    file_id: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None

class SessionResponse(BaseModel):
    session_id: str
    user_id: Optional[str]
    status: str
    created_at: str
    file_id: Optional[str]
    metadata: Dict[str, Any]

class MessageResponse(BaseModel):
    role: str
    content: str
    timestamp: str
    metadata: Optional[Dict[str, Any]] = None

class ChatHistoryResponse(BaseModel):
    session_id: str
    messages: List[MessageResponse]
    total_count: int

# REST API Endpoints

@router.post("/chat/sessions", response_model=SessionResponse)
async def create_chat_session(request: CreateSessionRequest):
    """Create a new chat session."""
    try:
        # Ensure session manager is initialized
        if session_manager._connection_pool is None:
            await session_manager.initialize()
            
        session = await session_manager.create_session(
            user_id=request.user_id,
            file_id=request.file_id,
            metadata=request.metadata or {}
        )
        
        return SessionResponse(
            session_id=session.session_id,
            user_id=session.user_id,
            status=session.status.value,
            created_at=session.created_at.isoformat(),
            file_id=session.file_id,
            metadata=session.metadata
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to create session: {str(e)}")

@router.get("/chat/sessions/{session_id}", response_model=SessionResponse)
async def get_chat_session(session_id: str):
    """Get chat session information."""
    # Ensure session manager is initialized
    if session_manager._connection_pool is None:
        await session_manager.initialize()
        
    session = await session_manager.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    
    return SessionResponse(
        session_id=session.session_id,
        user_id=session.user_id,
        status=session.status.value,
        created_at=session.created_at.isoformat(),
        file_id=session.file_id,
        metadata=session.metadata
    )

@router.get("/chat/sessions/{session_id}/history", response_model=ChatHistoryResponse)
async def get_chat_history(session_id: str, limit: Optional[int] = 50):
    """Get chat history for a session."""
    # Ensure session manager is initialized
    if session_manager._connection_pool is None:
        await session_manager.initialize()
        
    messages = await session_manager.get_chat_history(session_id, limit=limit)
    
    return ChatHistoryResponse(
        session_id=session_id,
        messages=[
            MessageResponse(
                role=msg.role,
                content=msg.content,
                timestamp=msg.timestamp.isoformat(),
                metadata=msg.metadata
            )
            for msg in messages
        ],
        total_count=len(messages)
    )

@router.delete("/chat/sessions/{session_id}")
async def delete_chat_session(session_id: str):
    """Delete a chat session."""
    # Ensure session manager is initialized
    if session_manager._connection_pool is None:
        await session_manager.initialize()
        
    success = await session_manager.delete_session(session_id)
    if not success:
        raise HTTPException(status_code=404, detail="Session not found")
    
    return {"message": "Session deleted successfully"}

@router.get("/chat/sessions/{session_id}/telemetry-summary")
async def get_session_telemetry_summary(session_id: str):
    """Get telemetry summary for a chat session."""
    # Ensure telemetry service is initialized
    if telemetry_service._connection_pool is None:
        await telemetry_service.initialize()
    
    summary = await telemetry_service.get_telemetry_summary(session_id)
    if not summary:
        raise HTTPException(status_code=404, detail="No telemetry data found for this session")
    
    return {"session_id": session_id, "telemetry_summary": summary}

# WebSocket endpoint for real-time chat
@router.websocket("/ws/chat")
async def websocket_chat_endpoint(websocket: WebSocket):
    """WebSocket endpoint for real-time chat with telemetry context."""
    await websocket.accept()
    
    session_id = None
    llm_client = LLMClient()
    
    try:
        print("WebSocket connection established")
        
        async for data in websocket.iter_text():
            try:
                message_data = json.loads(data)
                user_message = message_data.get('message', '').strip()
                provided_session_id = message_data.get('session_id')
                
                if not user_message:
                    await websocket.send_text(json.dumps({
                        "type": "error",
                        "message": "Empty message received"
                    }))
                    continue
                
                # Handle session management
                if provided_session_id:
                    # Ensure session manager is initialized
                    if session_manager._connection_pool is None:
                        await session_manager.initialize()
                        
                    # Validate existing session
                    session = await session_manager.get_session(provided_session_id)
                    if session:
                        session_id = provided_session_id
                        await session_manager.update_session_activity(session_id)
                        print(f"Using existing session: {session_id}")
                    else:
                        # Session doesn't exist, create new one
                        new_session = await session_manager.create_session()
                        session_id = new_session.session_id
                        print(f"Created new session (invalid provided): {session_id}")
                        
                        await websocket.send_text(json.dumps({
                            "type": "control",
                            "action": "session_created",
                            "session_id": session_id,
                            "message": "Invalid session ID provided. Created new session."
                        }))
                else:
                    # Ensure session manager is initialized
                    if session_manager._connection_pool is None:
                        await session_manager.initialize()
                        
                    # No session provided, create new one
                    new_session = await session_manager.create_session()
                    session_id = new_session.session_id
                    print(f"Created new session: {session_id}")
                    
                    await websocket.send_text(json.dumps({
                        "type": "control",
                        "action": "session_created",
                        "session_id": session_id
                    }))
                
                # Store user message
                await session_manager.add_message(session_id, "user", user_message)
                
                # Get telemetry context if available
                if telemetry_service._connection_pool is None:
                    await telemetry_service.initialize()
                
                telemetry_context = await telemetry_service.get_telemetry_summary(session_id)
                
                # Get chat history for context (last 20 messages)
                chat_history = await session_manager.get_chat_history(session_id, limit=20, include_system=False)
                
                # Build conversation context
                conversation_history = []
                for msg in reversed(chat_history[:-1]):  # Exclude the current message
                    conversation_history.append({
                        "role": msg.role,
                        "content": msg.content
                    })
                
                # Prepare system message with context
                system_content = [
                    "You are a UAV flight log analysis assistant for the UAV Log Viewer application.",
                    "You help users understand MAVLink logs, Dataflash logs, and telemetry data from drones and UAVs.",
                    "",
                    "Your capabilities include:",
                    "- Flight log analysis and interpretation",
                    "- MAVLink message explanation",
                    "- Flight telemetry understanding",
                    "- Problem diagnosis from flight data",
                    "- Best practices for UAV operations",
                    ""
                ]
                
                if telemetry_context:
                    system_content.extend([
                        "CURRENT FLIGHT LOG CONTEXT:",
                        telemetry_context,
                        "",
                        "Use this flight data context to provide specific, relevant analysis.",
                        "Reference actual data from the log when answering questions.",
                        ""
                    ])
                else:
                    system_content.append("No flight log data is currently available for this session.")
                
                system_content.append("Provide helpful, accurate, and context-aware responses about UAV flight logs and operations.")
                
                # Prepare messages for LLM
                messages = [
                    {"role": "system", "content": "\n".join(system_content)},
                    *conversation_history,
                    {"role": "user", "content": user_message}
                ]
                
                # Stream response from LLM
                full_response = ""
                async for chunk in llm_client.stream_chat(messages):
                    if chunk:
                        full_response += chunk
                        await websocket.send_text(json.dumps({
                            "type": "message_chunk",
                            "content": chunk
                        }))
                
                # Send completion signal
                await websocket.send_text(json.dumps({
                    "type": "message_complete",
                    "session_id": session_id
                }))
                
                # Store assistant response
                if full_response.strip():
                    await session_manager.add_message(session_id, "assistant", full_response.strip())
                
                print(f"Completed chat exchange for session {session_id}")
                
            except json.JSONDecodeError:
                await websocket.send_text(json.dumps({
                    "type": "error",
                    "message": "Invalid JSON format"
                }))
            except Exception as e:
                print(f"Error in chat processing: {e}")
                await websocket.send_text(json.dumps({
                    "type": "error",
                    "message": f"Processing error: {str(e)}"
                }))
                
    except WebSocketDisconnect:
        print("WebSocket connection closed")
    except Exception as e:
        print(f"WebSocket error: {e}")
    finally:
        try:
            await websocket.close()
        except:
            pass 