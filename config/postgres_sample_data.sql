-- Sample data for UAV Log Viewer PostgreSQL Schema

-- 1. Insert a user session
INSERT INTO user_sessions (user_id, session_start, description)
VALUES ('testuser', NOW(), 'Sample session for testing');

-- 2. Insert log metadata (linked to the above session)
INSERT INTO log_metadata (session_id, filename, upload_time, log_start_time, log_end_time, vehicle_type, parser_version, notes)
VALUES (1, '1980-01-08 09-44-08.bin', NOW(), NOW(), NOW() + interval '1 hour', 'quadcopter', 'v1.0', 'Test log file');

-- 3. Insert parsed telemetry (linked to the above log)
INSERT INTO parsed_telemetry (log_id, message_type, timestamp, data)
VALUES
  (1, 'GLOBAL_POSITION_INT', 1000.0, '{"lat": 374221234, "lon": -1220845678, "alt": 120, "relative_alt": 10, "vx": 0, "vy": 0, "vz": 0, "hdg": 90}'),
  (1, 'HEARTBEAT', 1000.0, '{"type": 2, "autopilot": 3, "base_mode": 81, "custom_mode": 0, "system_status": 4, "mavlink_version": 3, "asText": "Stabilize", "craft": "quadcopter"}');

-- 4. Insert chat history (linked to the above session)
INSERT INTO chat_history (session_id, timestamp, sender, message)
VALUES
  (1, NOW(), 'user', 'How do I view the log?'),
  (1, NOW(), 'system', 'You can view the log by selecting it from the dashboard.');

-- 5. Insert a message type reference
INSERT INTO message_type_reference (name, description, fields)
VALUES
  ('GLOBAL_POSITION_INT', 'GPS position and velocity data', '[{"name": "lat", "type": "int32"}, {"name": "lon", "type": "int32"}, {"name": "alt", "type": "int32"}, {"name": "relative_alt", "type": "int32"}, {"name": "vx", "type": "int16"}, {"name": "vy", "type": "int16"}, {"name": "vz", "type": "int16"}, {"name": "hdg", "type": "uint16"}]'); 