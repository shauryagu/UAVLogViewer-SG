import uuid
import json
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Any
from dataclasses import dataclass, asdict
from enum import Enum
import asyncpg
import os

class SessionStatus(Enum):
    ACTIVE = "active"
    INACTIVE = "inactive"
    EXPIRED = "expired"

@dataclass
class ChatMessage:
    role: str  # 'user', 'assistant', 'system'
    content: str
    timestamp: datetime
    metadata: Optional[Dict[str, Any]] = None

@dataclass
class ChatSession:
    session_id: str
    user_id: Optional[str]
    status: SessionStatus
    created_at: datetime
    last_activity: datetime
    expires_at: Optional[datetime]
    file_id: Optional[str]  # Associated uploaded file
    metadata: Dict[str, Any]
    message_count: int = 0

class SessionManager:
    def __init__(self, database_url: str = None):
        self.database_url = database_url or os.getenv(
            "DATABASE_URL", 
            "postgresql://uavuser:sRinathSai%$8970@localhost:5432/uavlogviewer"
        )
        self.session_timeout = timedelta(hours=24)  # Sessions expire after 24 hours
        self._connection_pool = None

    async def initialize(self):
        """Initialize the database connection and create tables if needed."""
        self._connection_pool = await asyncpg.create_pool(self.database_url)
        await self._create_tables()

    async def _create_tables(self):
        """Create necessary tables for session management."""
        async with self._connection_pool.acquire() as conn:
            # Chat sessions table
            await conn.execute('''
                CREATE TABLE IF NOT EXISTS chat_sessions (
                    session_id VARCHAR(36) PRIMARY KEY,
                    user_id VARCHAR(255),
                    status VARCHAR(20) NOT NULL DEFAULT 'active',
                    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
                    last_activity TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
                    expires_at TIMESTAMP WITH TIME ZONE,
                    file_id VARCHAR(255),
                    metadata JSONB DEFAULT '{}',
                    message_count INTEGER DEFAULT 0
                );
            ''')
            
            # Chat messages table
            await conn.execute('''
                CREATE TABLE IF NOT EXISTS chat_messages (
                    id SERIAL PRIMARY KEY,
                    session_id VARCHAR(36) NOT NULL REFERENCES chat_sessions(session_id) ON DELETE CASCADE,
                    role VARCHAR(20) NOT NULL,
                    content TEXT NOT NULL,
                    timestamp TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
                    metadata JSONB DEFAULT '{}',
                    message_order INTEGER NOT NULL
                );
            ''')
            
            # Create indexes for performance
            await conn.execute('''
                CREATE INDEX IF NOT EXISTS idx_chat_sessions_user_id ON chat_sessions(user_id);
                CREATE INDEX IF NOT EXISTS idx_chat_sessions_status ON chat_sessions(status);
                CREATE INDEX IF NOT EXISTS idx_chat_sessions_last_activity ON chat_sessions(last_activity);
                CREATE INDEX IF NOT EXISTS idx_chat_messages_session_id ON chat_messages(session_id);
                CREATE INDEX IF NOT EXISTS idx_chat_messages_timestamp ON chat_messages(timestamp);
            ''')

    async def create_session(
        self, 
        user_id: Optional[str] = None, 
        file_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> ChatSession:
        """Create a new chat session."""
        session_id = str(uuid.uuid4())
        now = datetime.utcnow()
        expires_at = now + self.session_timeout
        
        session = ChatSession(
            session_id=session_id,
            user_id=user_id,
            status=SessionStatus.ACTIVE,
            created_at=now,
            last_activity=now,
            expires_at=expires_at,
            file_id=file_id,
            metadata=metadata or {},
            message_count=0
        )
        
        async with self._connection_pool.acquire() as conn:
            await conn.execute('''
                INSERT INTO chat_sessions 
                (session_id, user_id, status, created_at, last_activity, expires_at, file_id, metadata)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
            ''', session_id, user_id, session.status.value, now, now, expires_at, file_id, json.dumps(metadata or {}))
        
        return session

    async def get_session(self, session_id: str) -> Optional[ChatSession]:
        """Retrieve a session by ID."""
        async with self._connection_pool.acquire() as conn:
            row = await conn.fetchrow('''
                SELECT session_id, user_id, status, created_at, last_activity, 
                       expires_at, file_id, metadata, message_count
                FROM chat_sessions WHERE session_id = $1
            ''', session_id)
            
            if not row:
                return None
            
            return ChatSession(
                session_id=row['session_id'],
                user_id=row['user_id'],
                status=SessionStatus(row['status']),
                created_at=row['created_at'],
                last_activity=row['last_activity'],
                expires_at=row['expires_at'],
                file_id=row['file_id'],
                metadata=row['metadata'] or {},
                message_count=row['message_count']
            )

    async def update_session_activity(self, session_id: str) -> bool:
        """Update the last activity timestamp for a session."""
        now = datetime.utcnow()
        async with self._connection_pool.acquire() as conn:
            result = await conn.execute('''
                UPDATE chat_sessions 
                SET last_activity = $1 
                WHERE session_id = $2 AND status = 'active'
            ''', now, session_id)
            return result != "UPDATE 0"

    async def add_message(
        self, 
        session_id: str, 
        role: str, 
        content: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> bool:
        """Add a message to a chat session."""
        now = datetime.utcnow()
        
        async with self._connection_pool.acquire() as conn:
            async with conn.transaction():
                # Get current message count and increment
                current_count = await conn.fetchval('''
                    SELECT message_count FROM chat_sessions WHERE session_id = $1
                ''', session_id)
                
                if current_count is None:
                    return False  # Session doesn't exist
                
                new_count = current_count + 1
                
                # Insert the message
                await conn.execute('''
                    INSERT INTO chat_messages 
                    (session_id, role, content, timestamp, metadata, message_order)
                    VALUES ($1, $2, $3, $4, $5, $6)
                ''', session_id, role, content, now, json.dumps(metadata or {}), new_count)
                
                # Update session message count and last activity
                await conn.execute('''
                    UPDATE chat_sessions 
                    SET message_count = $1, last_activity = $2 
                    WHERE session_id = $3
                ''', new_count, now, session_id)
        
        return True

    async def get_chat_history(
        self, 
        session_id: str, 
        limit: Optional[int] = None,
        include_system: bool = True
    ) -> List[ChatMessage]:
        """Retrieve chat history for a session."""
        query = '''
            SELECT role, content, timestamp, metadata 
            FROM chat_messages 
            WHERE session_id = $1
        '''
        
        if not include_system:
            query += " AND role != 'system'"
        
        query += " ORDER BY message_order ASC"
        
        if limit:
            query += f" LIMIT {limit}"
        
        async with self._connection_pool.acquire() as conn:
            rows = await conn.fetch(query, session_id)
            
            return [
                ChatMessage(
                    role=row['role'],
                    content=row['content'],
                    timestamp=row['timestamp'],
                    metadata=row['metadata'] or {}
                )
                for row in rows
            ]

    async def get_user_sessions(
        self, 
        user_id: str, 
        status: Optional[SessionStatus] = None,
        limit: int = 50
    ) -> List[ChatSession]:
        """Get all sessions for a user."""
        query = '''
            SELECT session_id, user_id, status, created_at, last_activity, 
                   expires_at, file_id, metadata, message_count
            FROM chat_sessions 
            WHERE user_id = $1
        '''
        params = [user_id]
        
        if status:
            query += " AND status = $2"
            params.append(status.value)
        
        query += " ORDER BY last_activity DESC LIMIT ${}".format(len(params) + 1)
        params.append(limit)
        
        async with self._connection_pool.acquire() as conn:
            rows = await conn.fetch(query, *params)
            
            return [
                ChatSession(
                    session_id=row['session_id'],
                    user_id=row['user_id'],
                    status=SessionStatus(row['status']),
                    created_at=row['created_at'],
                    last_activity=row['last_activity'],
                    expires_at=row['expires_at'],
                    file_id=row['file_id'],
                    metadata=row['metadata'] or {},
                    message_count=row['message_count']
                )
                for row in rows
            ]

    async def expire_session(self, session_id: str) -> bool:
        """Mark a session as expired."""
        async with self._connection_pool.acquire() as conn:
            result = await conn.execute('''
                UPDATE chat_sessions 
                SET status = 'expired' 
                WHERE session_id = $1
            ''', session_id)
            return result != "UPDATE 0"

    async def cleanup_expired_sessions(self) -> int:
        """Clean up expired sessions based on timeout."""
        now = datetime.utcnow()
        async with self._connection_pool.acquire() as conn:
            result = await conn.execute('''
                UPDATE chat_sessions 
                SET status = 'expired' 
                WHERE status = 'active' AND expires_at < $1
            ''', now)
            # Extract number from "UPDATE n" string
            return int(result.split()[-1]) if result != "UPDATE 0" else 0

    async def delete_session(self, session_id: str) -> bool:
        """Permanently delete a session and all its messages."""
        async with self._connection_pool.acquire() as conn:
            result = await conn.execute('''
                DELETE FROM chat_sessions WHERE session_id = $1
            ''', session_id)
            return result != "DELETE 0"

    async def close(self):
        """Close the database connection pool."""
        if self._connection_pool:
            await self._connection_pool.close()

# Global session manager instance
session_manager = SessionManager() 