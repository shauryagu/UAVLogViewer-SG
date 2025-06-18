# Smart Telemetry Storage for UAV Log Viewer
# Implements intelligent storage strategies to maximize chatbot performance

import asyncpg
import json
import numpy as np
from typing import List, Dict, Optional, Any, Tuple
from dataclasses import dataclass
from datetime import datetime
import os
from collections import defaultdict
import statistics

@dataclass
class MessageSummary:
    """Aggregated message statistics."""
    message_type: str
    count: int
    time_range: Tuple[float, float]
    sample_rate: float
    key_fields: Dict[str, Any]
    statistical_summary: Dict[str, float]

@dataclass
class FlightPhase:
    """Identified flight phase with boundaries."""
    phase_name: str
    start_time: float
    end_time: float
    key_events: List[Dict[str, Any]]
    summary_stats: Dict[str, Any]

class SmartTelemetryStorage:
    """
    Intelligent telemetry storage that optimizes for chatbot performance by:
    1. Storing ALL critical events and state changes
    2. Intelligently sampling high-frequency data
    3. Pre-computing flight statistics and summaries
    4. Creating searchable metadata for quick retrieval
    5. Maintaining full resolution data for specific analysis needs
    """
    
    def __init__(self, database_url: str = None):
        self.database_url = database_url or os.getenv(
            "DATABASE_URL", 
            "postgresql://uavuser:sRinathSai%$8970@localhost:5432/uavlogviewer"
        )
        self._connection_pool = None
        
        # Critical message types (store ALL instances)
        self.critical_messages = {
            'MODE', 'HEARTBEAT', 'ARM', 'DISARM', 'TAKEOFF', 'LAND',
            'STATUSTEXT', 'ERROR', 'CRITICAL', 'ALERT', 'EMERGENCY',
            'GPS_FIX_TYPE', 'EKF_STATUS_REPORT', 'VIBRATION', 'POWER_STATUS'
        }
        
        # High-frequency messages (intelligent sampling)
        self.high_frequency_messages = {
            'ATTITUDE': {'sample_rate': 10, 'key_fields': ['roll', 'pitch', 'yaw']},
            'GLOBAL_POSITION_INT': {'sample_rate': 5, 'key_fields': ['lat', 'lon', 'alt', 'relative_alt']},
            'LOCAL_POSITION_NED': {'sample_rate': 10, 'key_fields': ['x', 'y', 'z']},
            'VFR_HUD': {'sample_rate': 5, 'key_fields': ['airspeed', 'groundspeed', 'alt', 'throttle']},
            'RAW_IMU': {'sample_rate': 20, 'key_fields': ['xacc', 'yacc', 'zacc']},
            'SERVO_OUTPUT_RAW': {'sample_rate': 10, 'key_fields': ['servo1_raw', 'servo2_raw', 'servo3_raw', 'servo4_raw']}
        }

    async def initialize(self):
        """Initialize the database connection pool and create optimized tables."""
        self._connection_pool = await asyncpg.create_pool(self.database_url)
        await self._create_smart_tables()

    async def _create_smart_tables(self):
        """Create optimized tables for smart telemetry storage."""
        async with self._connection_pool.acquire() as conn:
            # Enhanced parsed_telemetry with storage strategy
            await conn.execute('''
                CREATE TABLE IF NOT EXISTS smart_telemetry (
                    id BIGSERIAL PRIMARY KEY,
                    log_id INTEGER REFERENCES log_metadata(id) ON DELETE CASCADE,
                    message_type VARCHAR(64) NOT NULL,
                    timestamp DOUBLE PRECISION NOT NULL,
                    data JSONB NOT NULL,
                    storage_strategy VARCHAR(32) NOT NULL, -- 'critical', 'sampled', 'full'
                    sampling_index INTEGER, -- For sampled data, original index
                    phase_tags TEXT[], -- Flight phase tags
                    created_at TIMESTAMP DEFAULT NOW()
                );
            ''')
            
            # Flight statistics table for quick summary retrieval
            await conn.execute('''
                CREATE TABLE IF NOT EXISTS flight_statistics (
                    id SERIAL PRIMARY KEY,
                    log_id INTEGER REFERENCES log_metadata(id) ON DELETE CASCADE,
                    statistic_type VARCHAR(64) NOT NULL, -- 'duration', 'max_altitude', 'distance', etc.
                    value DOUBLE PRECISION,
                    unit VARCHAR(32),
                    metadata JSONB,
                    created_at TIMESTAMP DEFAULT NOW()
                );
            ''')
            
            # Flight phases table for temporal analysis
            await conn.execute('''
                CREATE TABLE IF NOT EXISTS flight_phases (
                    id SERIAL PRIMARY KEY,
                    log_id INTEGER REFERENCES log_metadata(id) ON DELETE CASCADE,
                    phase_name VARCHAR(64) NOT NULL,
                    start_time DOUBLE PRECISION NOT NULL,
                    end_time DOUBLE PRECISION NOT NULL,
                    key_events JSONB,
                    summary_stats JSONB,
                    created_at TIMESTAMP DEFAULT NOW()
                );
            ''')
            
            # Message summaries for quick overview
            await conn.execute('''
                CREATE TABLE IF NOT EXISTS message_summaries (
                    id SERIAL PRIMARY KEY,
                    log_id INTEGER REFERENCES log_metadata(id) ON DELETE CASCADE,
                    message_type VARCHAR(64) NOT NULL,
                    total_count INTEGER NOT NULL,
                    stored_count INTEGER NOT NULL,
                    sample_rate DOUBLE PRECISION,
                    time_range_start DOUBLE PRECISION,
                    time_range_end DOUBLE PRECISION,
                    key_statistics JSONB,
                    created_at TIMESTAMP DEFAULT NOW()
                );
            ''')
            
            # Create indexes for optimal performance
            await conn.execute('''
                CREATE INDEX IF NOT EXISTS idx_smart_telemetry_log_type_time 
                ON smart_telemetry (log_id, message_type, timestamp);
            ''')
            await conn.execute('''
                CREATE INDEX IF NOT EXISTS idx_smart_telemetry_strategy 
                ON smart_telemetry (log_id, storage_strategy);
            ''')
            await conn.execute('''
                CREATE INDEX IF NOT EXISTS idx_smart_telemetry_phases 
                ON smart_telemetry USING GIN (phase_tags);
            ''')

    async def store_telemetry_intelligently(self, log_id: int, messages: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Store telemetry data using intelligent strategies to maximize chatbot performance.
        """
        if not messages:
            return {"status": "error", "message": "No messages to process"}
        
        async with self._connection_pool.acquire() as conn:
            async with conn.transaction():
                # Analyze messages to determine storage strategy
                storage_plan = await self._analyze_messages(messages)
                
                # Store messages according to strategy
                stored_stats = await self._store_with_strategy(conn, log_id, messages, storage_plan)
                
                # Compute and store flight statistics
                flight_stats = await self._compute_flight_statistics(messages)
                await self._store_flight_statistics(conn, log_id, flight_stats)
                
                # Identify and store flight phases
                phases = await self._identify_flight_phases(messages)
                await self._store_flight_phases(conn, log_id, phases)
                
                # Store message summaries
                summaries = await self._create_message_summaries(messages, stored_stats)
                await self._store_message_summaries(conn, log_id, summaries)
                
                return {
                    "status": "success",
                    "total_messages": len(messages),
                    "stored_critical": stored_stats["critical_count"],
                    "stored_sampled": stored_stats["sampled_count"],
                    "stored_full": stored_stats["full_count"],
                    "storage_efficiency": stored_stats["total_stored"] / len(messages),
                    "flight_phases": len(phases),
                    "computed_statistics": len(flight_stats)
                }

    async def _analyze_messages(self, messages: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Analyze message patterns to determine optimal storage strategy."""
        message_types = defaultdict(list)
        
        for i, msg in enumerate(messages):
            msg_type = msg["message_type"]
            message_types[msg_type].append(i)
        
        storage_plan = {}
        for msg_type, indices in message_types.items():
            count = len(indices)
            
            if msg_type in self.critical_messages:
                storage_plan[msg_type] = {"strategy": "critical", "indices": indices}
            elif msg_type in self.high_frequency_messages:
                config = self.high_frequency_messages[msg_type]
                sample_rate = config["sample_rate"]
                step = max(1, count // sample_rate) if count > sample_rate else 1
                sampled_indices = indices[::step]
                storage_plan[msg_type] = {
                    "strategy": "sampled", 
                    "indices": sampled_indices,
                    "original_count": count,
                    "sample_rate": len(sampled_indices)
                }
            elif count < 100:  # Store all instances of rare messages
                storage_plan[msg_type] = {"strategy": "full", "indices": indices}
            else:  # Intelligent sampling for other high-frequency messages
                step = max(1, count // 50)  # Store ~50 representative samples
                sampled_indices = indices[::step]
                storage_plan[msg_type] = {
                    "strategy": "sampled",
                    "indices": sampled_indices,
                    "original_count": count,
                    "sample_rate": len(sampled_indices)
                }
        
        return storage_plan

    async def _store_with_strategy(self, conn, log_id: int, messages: List[Dict[str, Any]], storage_plan: Dict[str, Any]) -> Dict[str, int]:
        """Store messages according to the determined strategy."""
        critical_count = 0
        sampled_count = 0
        full_count = 0
        
        for msg_type, plan in storage_plan.items():
            strategy = plan["strategy"]
            indices = plan["indices"]
            
            for i, msg_idx in enumerate(indices):
                msg = messages[msg_idx]
                
                # Ensure data is JSON serializable
                safe_data = self._make_json_safe(msg["data"])
                
                # Determine phase tags (simplified here, could be enhanced)
                phase_tags = await self._determine_phase_tags(msg, msg_idx, len(messages))
                
                await conn.execute('''
                    INSERT INTO smart_telemetry 
                    (log_id, message_type, timestamp, data, storage_strategy, sampling_index, phase_tags)
                    VALUES ($1, $2, $3, $4, $5, $6, $7)
                ''', log_id, msg_type, msg["timestamp"], safe_data, strategy, msg_idx, phase_tags)
                
                if strategy == "critical":
                    critical_count += 1
                elif strategy == "sampled":
                    sampled_count += 1
                else:
                    full_count += 1
        
        return {
            "critical_count": critical_count,
            "sampled_count": sampled_count,
            "full_count": full_count,
            "total_stored": critical_count + sampled_count + full_count
        }

    async def _determine_phase_tags(self, msg: Dict[str, Any], index: int, total_messages: int) -> List[str]:
        """Determine flight phase tags for a message."""
        tags = []
        
        # Simple phase detection based on position in flight
        progress = index / total_messages
        if progress < 0.1:
            tags.append("startup")
        elif progress < 0.2:
            tags.append("preflight")
        elif progress < 0.8:
            tags.append("flight")
        elif progress < 0.95:
            tags.append("landing")
        else:
            tags.append("shutdown")
        
        # Add message-specific tags
        msg_type = msg["message_type"]
        if msg_type in ["TAKEOFF", "LAND"]:
            tags.append("critical_event")
        elif msg_type == "MODE":
            tags.append("mode_change")
        elif "ERROR" in msg_type or "ALERT" in msg_type:
            tags.append("alert")
        
        return tags

    async def _compute_flight_statistics(self, messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Compute key flight statistics for quick retrieval."""
        stats = []
        
        # Group messages by type for analysis
        by_type = defaultdict(list)
        for msg in messages:
            by_type[msg["message_type"]].append(msg)
        
        # Altitude statistics
        if "GLOBAL_POSITION_INT" in by_type:
            gps_msgs = by_type["GLOBAL_POSITION_INT"]
            altitudes = [msg["data"].get("relative_alt", 0) / 1000.0 for msg in gps_msgs if "relative_alt" in msg["data"]]
            if altitudes:
                stats.extend([
                    {"statistic_type": "max_altitude", "value": max(altitudes), "unit": "meters"},
                    {"statistic_type": "min_altitude", "value": min(altitudes), "unit": "meters"},
                    {"statistic_type": "avg_altitude", "value": statistics.mean(altitudes), "unit": "meters"}
                ])
        
        # Flight duration
        if messages:
            start_time = messages[0]["timestamp"]
            end_time = messages[-1]["timestamp"]
            duration = end_time - start_time
            stats.append({"statistic_type": "flight_duration", "value": duration, "unit": "seconds"})
        
        # Speed statistics from VFR_HUD
        if "VFR_HUD" in by_type:
            vfr_msgs = by_type["VFR_HUD"]
            speeds = [msg["data"].get("groundspeed", 0) for msg in vfr_msgs if "groundspeed" in msg["data"]]
            if speeds:
                stats.extend([
                    {"statistic_type": "max_speed", "value": max(speeds), "unit": "m/s"},
                    {"statistic_type": "avg_speed", "value": statistics.mean(speeds), "unit": "m/s"}
                ])
        
        # Distance traveled (simplified calculation)
        if "GLOBAL_POSITION_INT" in by_type:
            gps_msgs = by_type["GLOBAL_POSITION_INT"]
            if len(gps_msgs) >= 2:
                start_pos = gps_msgs[0]["data"]
                end_pos = gps_msgs[-1]["data"]
                if all(k in start_pos and k in end_pos for k in ["lat", "lon"]):
                    # Simplified distance calculation (could be enhanced with proper geodetic calculation)
                    lat_diff = (end_pos["lat"] - start_pos["lat"]) / 1e7
                    lon_diff = (end_pos["lon"] - start_pos["lon"]) / 1e7
                    approx_distance = ((lat_diff**2 + lon_diff**2)**0.5) * 111000  # Rough conversion to meters
                    stats.append({"statistic_type": "total_distance", "value": approx_distance, "unit": "meters"})
        
        return stats

    async def _identify_flight_phases(self, messages: List[Dict[str, Any]]) -> List[FlightPhase]:
        """Identify distinct flight phases for temporal analysis."""
        phases = []
        
        # Simple phase detection based on mode changes and events
        current_phase = None
        phase_start = 0
        
        for i, msg in enumerate(messages):
            if msg["message_type"] == "MODE":
                mode = msg["data"].get("mode", "unknown")
                
                if current_phase is not None:
                    # End the current phase
                    phases.append(FlightPhase(
                        phase_name=current_phase,
                        start_time=messages[phase_start]["timestamp"],
                        end_time=msg["timestamp"],
                        key_events=[],
                        summary_stats={}
                    ))
                
                current_phase = f"mode_{mode}"
                phase_start = i
        
        # Add final phase
        if current_phase is not None and messages:
            phases.append(FlightPhase(
                phase_name=current_phase,
                start_time=messages[phase_start]["timestamp"],
                end_time=messages[-1]["timestamp"],
                key_events=[],
                summary_stats={}
            ))
        
        return phases

    async def _store_flight_statistics(self, conn, log_id: int, stats: List[Dict[str, Any]]):
        """Store computed flight statistics."""
        for stat in stats:
            await conn.execute('''
                INSERT INTO flight_statistics (log_id, statistic_type, value, unit, metadata)
                VALUES ($1, $2, $3, $4, $5)
            ''', log_id, stat["statistic_type"], stat["value"], stat.get("unit"), stat.get("metadata", {}))

    async def _store_flight_phases(self, conn, log_id: int, phases: List[FlightPhase]):
        """Store identified flight phases."""
        for phase in phases:
            await conn.execute('''
                INSERT INTO flight_phases (log_id, phase_name, start_time, end_time, key_events, summary_stats)
                VALUES ($1, $2, $3, $4, $5, $6)
            ''', log_id, phase.phase_name, phase.start_time, phase.end_time, 
            json.dumps(phase.key_events), json.dumps(phase.summary_stats))

    async def _create_message_summaries(self, messages: List[Dict[str, Any]], stored_stats: Dict[str, int]) -> List[MessageSummary]:
        """Create message summaries for quick overview."""
        summaries = []
        by_type = defaultdict(list)
        
        for msg in messages:
            by_type[msg["message_type"]].append(msg)
        
        for msg_type, msgs in by_type.items():
            timestamps = [msg["timestamp"] for msg in msgs]
            summaries.append(MessageSummary(
                message_type=msg_type,
                count=len(msgs),
                time_range=(min(timestamps), max(timestamps)),
                sample_rate=1.0,  # Will be updated based on storage strategy
                key_fields={},
                statistical_summary={}
            ))
        
        return summaries

    async def _store_message_summaries(self, conn, log_id: int, summaries: List[MessageSummary]):
        """Store message summaries."""
        for summary in summaries:
            await conn.execute('''
                INSERT INTO message_summaries 
                (log_id, message_type, total_count, stored_count, sample_rate, 
                 time_range_start, time_range_end, key_statistics)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
            ''', log_id, summary.message_type, summary.count, summary.count,
            summary.sample_rate, summary.time_range[0], summary.time_range[1],
            json.dumps(summary.statistical_summary))

    def _make_json_safe(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Convert data to JSON-safe format."""
        safe_data = {}
        for key, value in data.items():
            try:
                if hasattr(value, 'tolist'):
                    safe_data[key] = value.tolist()
                elif isinstance(value, (list, tuple)):
                    safe_data[key] = [x.tolist() if hasattr(x, 'tolist') else x for x in value]
                else:
                    safe_data[key] = value
            except (TypeError, AttributeError):
                safe_data[key] = str(value)
        return safe_data

    async def get_intelligent_summary(self, session_id: str) -> Optional[str]:
        """Get an intelligent, comprehensive flight summary for LLM context."""
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
            
            # Get comprehensive flight data
            log_row = await conn.fetchrow('''
                SELECT filename, upload_time, vehicle_type FROM log_metadata WHERE id = $1
            ''', file_id)
            
            # Get flight statistics
            stats_rows = await conn.fetch('''
                SELECT statistic_type, value, unit FROM flight_statistics 
                WHERE log_id = $1 ORDER BY statistic_type
            ''', file_id)
            
            # Get message summaries
            summary_rows = await conn.fetch('''
                SELECT message_type, total_count, stored_count, sample_rate
                FROM message_summaries WHERE log_id = $1 
                ORDER BY total_count DESC LIMIT 15
            ''', file_id)
            
            # Get flight phases
            phase_rows = await conn.fetch('''
                SELECT phase_name, start_time, end_time 
                FROM flight_phases WHERE log_id = $1 
                ORDER BY start_time
            ''', file_id)
            
            # Build comprehensive summary
            summary_parts = [
                "=== COMPREHENSIVE FLIGHT LOG ANALYSIS ===",
                f"File: {log_row['filename']}",
                f"Vehicle: {log_row['vehicle_type'] or 'Unknown'}",
                ""
            ]
            
            # Add key statistics
            if stats_rows:
                summary_parts.append("=== KEY FLIGHT STATISTICS ===")
                for stat in stats_rows:
                    unit_str = f" {stat['unit']}" if stat['unit'] else ""
                    summary_parts.append(f"• {stat['statistic_type'].replace('_', ' ').title()}: {stat['value']:.2f}{unit_str}")
                summary_parts.append("")
            
            # Add message analysis
            if summary_rows:
                total_original = sum(row['total_count'] for row in summary_rows)
                total_stored = sum(row['stored_count'] for row in summary_rows)
                summary_parts.extend([
                    "=== MESSAGE ANALYSIS ===",
                    f"Total Messages: {total_original:,} (Stored: {total_stored:,}, Efficiency: {total_stored/total_original:.1%})",
                    "Top Message Types:"
                ])
                for row in summary_rows[:8]:
                    efficiency = f"({row['stored_count']}/{row['total_count']})" if row['stored_count'] != row['total_count'] else ""
                    summary_parts.append(f"  • {row['message_type']}: {row['total_count']:,} messages {efficiency}")
                summary_parts.append("")
            
            # Add flight phases
            if phase_rows:
                summary_parts.append("=== FLIGHT PHASES ===")
                for phase in phase_rows:
                    duration = phase['end_time'] - phase['start_time']
                    summary_parts.append(f"• {phase['phase_name']}: {duration:.1f}s")
                summary_parts.append("")
            
            summary_parts.extend([
                "=== ANALYSIS CAPABILITIES ===",
                "Available for detailed analysis:",
                "• All critical events and state changes stored",
                "• High-frequency data intelligently sampled", 
                "• Flight statistics pre-computed",
                "• Temporal phase analysis available",
                "• Can retrieve specific data on demand"
            ])
            
            return "\n".join(summary_parts)

    async def query_specific_data(self, session_id: str, query_type: str, **kwargs) -> List[Dict[str, Any]]:
        """Query specific telemetry data based on intelligent storage."""
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
            
            if query_type == "critical_events":
                rows = await conn.fetch('''
                    SELECT message_type, timestamp, data, phase_tags
                    FROM smart_telemetry 
                    WHERE log_id = $1 AND storage_strategy = 'critical'
                    ORDER BY timestamp DESC LIMIT $2
                ''', log_id, kwargs.get('limit', 50))
                
            elif query_type == "message_type":
                msg_type = kwargs.get('message_type')
                rows = await conn.fetch('''
                    SELECT message_type, timestamp, data, sampling_index
                    FROM smart_telemetry 
                    WHERE log_id = $1 AND message_type = $2
                    ORDER BY timestamp DESC LIMIT $3
                ''', log_id, msg_type, kwargs.get('limit', 100))
                
            elif query_type == "phase":
                phase_tag = kwargs.get('phase')
                rows = await conn.fetch('''
                    SELECT message_type, timestamp, data, phase_tags
                    FROM smart_telemetry 
                    WHERE log_id = $1 AND $2 = ANY(phase_tags)
                    ORDER BY timestamp DESC LIMIT $3
                ''', log_id, phase_tag, kwargs.get('limit', 100))
                
            else:
                rows = await conn.fetch('''
                    SELECT message_type, timestamp, data, storage_strategy
                    FROM smart_telemetry 
                    WHERE log_id = $1
                    ORDER BY timestamp DESC LIMIT $2
                ''', log_id, kwargs.get('limit', 20))
            
            return [dict(row) for row in rows]

    async def close(self):
        """Close the database connection pool."""
        if self._connection_pool:
            await self._connection_pool.close() 