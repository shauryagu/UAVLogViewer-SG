-- UAV Log Viewer PostgreSQL Schema

-- 1. User Sessions
CREATE TABLE user_sessions (
    id SERIAL PRIMARY KEY,
    user_id VARCHAR(64), -- nullable, for future auth
    session_start TIMESTAMP NOT NULL DEFAULT NOW(),
    session_end TIMESTAMP,
    description TEXT
);

-- 2. Log Metadata
CREATE TABLE log_metadata (
    id SERIAL PRIMARY KEY,
    session_id INTEGER REFERENCES user_sessions(id) ON DELETE CASCADE,
    filename VARCHAR(255) NOT NULL,
    upload_time TIMESTAMP NOT NULL DEFAULT NOW(),
    log_start_time TIMESTAMP,
    log_end_time TIMESTAMP,
    vehicle_type VARCHAR(64),
    parser_version VARCHAR(32),
    notes TEXT
);

CREATE INDEX idx_log_metadata_session_id ON log_metadata(session_id);
CREATE INDEX idx_log_metadata_upload_time ON log_metadata(upload_time);

-- 3. Parsed Telemetry
CREATE TABLE parsed_telemetry (
    id BIGSERIAL PRIMARY KEY,
    log_id INTEGER REFERENCES log_metadata(id) ON DELETE CASCADE,
    message_type VARCHAR(64) NOT NULL,
    timestamp DOUBLE PRECISION NOT NULL, -- Use float for ms precision, or TIMESTAMP if always UTC
    data JSONB NOT NULL
);

CREATE INDEX idx_parsed_telemetry_log_type_time
    ON parsed_telemetry (log_id, message_type, timestamp);

CREATE INDEX idx_parsed_telemetry_data_gin
    ON parsed_telemetry USING GIN (data);

-- 4. Chat History
CREATE TABLE chat_history (
    id SERIAL PRIMARY KEY,
    session_id INTEGER REFERENCES user_sessions(id) ON DELETE CASCADE,
    timestamp TIMESTAMP NOT NULL DEFAULT NOW(),
    sender VARCHAR(16) NOT NULL, -- 'user' or 'system'
    message TEXT NOT NULL
);

CREATE INDEX idx_chat_history_session_time
    ON chat_history (session_id, timestamp);

-- 5. (Optional) Message Type Reference
CREATE TABLE message_type_reference (
    id SERIAL PRIMARY KEY,
    name VARCHAR(64) UNIQUE NOT NULL,
    description TEXT,
    fields JSONB -- Array of field definitions
);

CREATE INDEX idx_message_type_reference_name ON message_type_reference(name); 