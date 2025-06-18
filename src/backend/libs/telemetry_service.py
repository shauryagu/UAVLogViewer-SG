# TelemetryService for UAV Log Viewer
# Provides context-aware telemetry data retrieval for chat sessions

import asyncpg
import json
from typing import List, Dict, Optional, Any
from dataclasses import dataclass
from datetime import datetime
import os

@dataclass
class TelemetryMessage:
    """Individual telemetry message."""
    id: int
    message_type: str
    timestamp: float
    data: Dict[str, Any]

class TelemetryService:
    """Service for retrieving and analyzing telemetry data for chat sessions."""
    
    def __init__(self, database_url: str = None):
        self.database_url = database_url or os.getenv(
            "DATABASE_URL", 
            "postgresql://uavuser:sRinathSai%$8970@localhost:5432/uavlogviewer"
        )
        self._connection_pool = None

    async def initialize(self):
        """Initialize the database connection pool."""
        self._connection_pool = await asyncpg.create_pool(self.database_url)

    async def get_telemetry_summary(self, session_id: str) -> Optional[str]:
        """Get telemetry summary for LLM context."""
        if not self._connection_pool:
            return None
            
        async with self._connection_pool.acquire() as conn:
            # Get file_id from session
            session_row = await conn.fetchrow(
                'SELECT file_id FROM chat_sessions WHERE session_id = $1', session_id
            )
            
            if not session_row or not session_row['file_id']:
                return None
            
            file_id = int(session_row['file_id'])
            
            # Get log metadata
            log_row = await conn.fetchrow('''
                SELECT filename, upload_time, vehicle_type 
                FROM log_metadata WHERE id = $1
            ''', file_id)
            
            if not log_row:
                return None
            
            # Get message summary
            message_summary = await conn.fetch('''
                SELECT message_type, COUNT(*) as count
                FROM parsed_telemetry WHERE log_id = $1
                GROUP BY message_type ORDER BY count DESC LIMIT 10
            ''', file_id)
            
            # Build summary for LLM
            summary = [
                f"=== FLIGHT LOG SUMMARY ===",
                f"File: {log_row['filename']}",
                f"Vehicle: {log_row['vehicle_type'] or 'Unknown'}"
            ]
            
            if message_summary:
                total_msgs = sum(row['count'] for row in message_summary)
                summary.append(f"Total Messages: {total_msgs:,}")
                summary.append("Available Message Types:")
                for row in message_summary[:5]:
                    summary.append(f"  - {row['message_type']}: {row['count']} messages")
                if len(message_summary) > 5:
                    summary.append(f"  ... and {len(message_summary) - 5} more types")
            
            return "\n".join(summary)

    async def query_telemetry_data(
        self, 
        session_id: str, 
        message_type: Optional[str] = None,
        limit: int = 20
    ) -> List[TelemetryMessage]:
        """Query telemetry data for a session."""
        if not self._connection_pool:
            return []
            
        async with self._connection_pool.acquire() as conn:
            # Get the log_id for this session
            session_row = await conn.fetchrow(
                'SELECT file_id FROM chat_sessions WHERE session_id = $1', session_id
            )
            
            if not session_row or not session_row['file_id']:
                return []
            
            log_id = int(session_row['file_id'])
            
            # Build query
            if message_type:
                query = '''
                    SELECT id, message_type, timestamp, data
                    FROM parsed_telemetry 
                    WHERE log_id = $1 AND message_type = $2
                    ORDER BY timestamp DESC LIMIT $3
                '''
                params = [log_id, message_type, limit]
            else:
                query = '''
                    SELECT id, message_type, timestamp, data
                    FROM parsed_telemetry 
                    WHERE log_id = $1
                    ORDER BY timestamp DESC LIMIT $2
                '''
                params = [log_id, limit]
            
            rows = await conn.fetch(query, *params)
            
            return [
                TelemetryMessage(
                    id=row['id'],
                    message_type=row['message_type'],
                    timestamp=row['timestamp'],
                    data=row['data']
                )
                for row in rows
            ]

    async def close(self):
        """Close the database connection pool."""
        if self._connection_pool:
            await self._connection_pool.close() 