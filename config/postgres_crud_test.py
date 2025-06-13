import psycopg2
import json
import os

# Update these as needed or use environment variables
DB_NAME = os.getenv('PGDATABASE', 'uavlogviewer')
DB_USER = os.getenv('PGUSER', 'uavuser')
DB_PASSWORD = os.getenv('PGPASSWORD', None)  # Set in your environment or here
DB_HOST = os.getenv('PGHOST', 'localhost')
DB_PORT = os.getenv('PGPORT', '5432')

conn = psycopg2.connect(
    dbname=DB_NAME,
    user=DB_USER,
    password=DB_PASSWORD,
    host=DB_HOST,
    port=DB_PORT
)
conn.autocommit = True
cur = conn.cursor()

try:
    print('--- CREATE: Insert new user session')
    cur.execute("""
        INSERT INTO user_sessions (user_id, session_start, description)
        VALUES ('cruduser', NOW(), 'CRUD test session') RETURNING id;
    """)
    session_id = cur.fetchone()[0]
    print(f'Inserted user_session with id: {session_id}')

    print('--- CREATE: Insert log metadata')
    cur.execute("""
        INSERT INTO log_metadata (session_id, filename, upload_time, log_start_time, log_end_time, vehicle_type, parser_version, notes)
        VALUES (%s, %s, NOW(), NOW(), NOW() + interval '1 hour', %s, %s, %s) RETURNING id;
    """, (session_id, 'crud_test_log.bin', 'quadcopter', 'v1.0', 'CRUD log'))
    log_id = cur.fetchone()[0]
    print(f'Inserted log_metadata with id: {log_id}')

    print('--- CREATE: Insert parsed telemetry')
    cur.execute("""
        INSERT INTO parsed_telemetry (log_id, message_type, timestamp, data)
        VALUES (%s, %s, %s, %s::jsonb) RETURNING id;
    """, (log_id, 'HEARTBEAT', 2000.0, json.dumps({
        "type": 2, "autopilot": 3, "base_mode": 81, "custom_mode": 0, "system_status": 4, "mavlink_version": 3, "asText": "Stabilize", "craft": "quadcopter"
    })))
    telemetry_id = cur.fetchone()[0]
    print(f'Inserted parsed_telemetry with id: {telemetry_id}')

    print('--- CREATE: Insert chat history')
    cur.execute("""
        INSERT INTO chat_history (session_id, timestamp, sender, message)
        VALUES (%s, NOW(), %s, %s) RETURNING id;
    """, (session_id, 'user', 'CRUD test message'))
    chat_id = cur.fetchone()[0]
    print(f'Inserted chat_history with id: {chat_id}')

    print('--- CREATE: Insert message type reference')
    cur.execute("""
        INSERT INTO message_type_reference (name, description, fields)
        VALUES (%s, %s, %s::jsonb) RETURNING id;
    """, ('HEARTBEAT', 'Heartbeat message', json.dumps([
        {"name": "type", "type": "uint8"},
        {"name": "autopilot", "type": "uint8"},
        {"name": "base_mode", "type": "uint8"},
        {"name": "custom_mode", "type": "uint32"},
        {"name": "system_status", "type": "uint8"},
        {"name": "mavlink_version", "type": "uint8"}
    ])))
    ref_id = cur.fetchone()[0]
    print(f'Inserted message_type_reference with id: {ref_id}')

    print('\n--- READ: Fetch all user_sessions')
    cur.execute('SELECT * FROM user_sessions;')
    for row in cur.fetchall():
        print(row)

    print('\n--- UPDATE: Update user_sessions description')
    cur.execute('UPDATE user_sessions SET description = %s WHERE id = %s;', ('Updated CRUD test session', session_id))
    print(f'Updated user_sessions id {session_id}')

    print('\n--- DELETE: Delete inserted data (cascade test)')
    cur.execute('DELETE FROM user_sessions WHERE id = %s;', (session_id,))
    print(f'Deleted user_sessions id {session_id} (should cascade to log_metadata, parsed_telemetry, chat_history)')

    print('\n--- VERIFY: Check if related data is deleted')
    cur.execute('SELECT * FROM log_metadata WHERE session_id = %s;', (session_id,))
    print('log_metadata:', cur.fetchall())
    cur.execute('SELECT * FROM parsed_telemetry WHERE log_id = %s;', (log_id,))
    print('parsed_telemetry:', cur.fetchall())
    cur.execute('SELECT * FROM chat_history WHERE session_id = %s;', (session_id,))
    print('chat_history:', cur.fetchall())

    print('\n--- DELETE: Clean up message_type_reference')
    cur.execute('DELETE FROM message_type_reference WHERE id = %s;', (ref_id,))
    print(f'Deleted message_type_reference id {ref_id}')

except Exception as e:
    print('Error:', e)
finally:
    cur.close()
    conn.close()
    print('Connection closed.') 