from pymavlink import mavutil
from pymavlink.DFReader import DFReader_binary
import io
import tempfile
import os


def parse_mavlink_log_bytes(file_bytes):
    """
    Parse a UAV log file (Dataflash .bin or .log) from bytes using pymavlink.
    Returns a list of messages: each with message_type, timestamp, and data.
    """
    temp_file = None
    try:
        # Write bytes to a temporary file
        temp_file = tempfile.NamedTemporaryFile(delete=False, suffix='.bin')
        temp_file.write(file_bytes)
        temp_file.close()
        df = DFReader_binary(temp_file.name)
        messages = []
        while True:
            msg = df.recv_msg()
            if msg is None:
                break
            msg_type = msg.get_type()
            # Try to extract a timestamp field if present
            ts = 0.0
            if hasattr(msg, 'time_boot_ms') and msg.time_boot_ms is not None:
                ts = float(msg.time_boot_ms) / 1000.0  # Convert ms to seconds
            elif hasattr(msg, 'time_usec') and msg.time_usec is not None:
                ts = float(msg.time_usec) / 1e6  # Convert usec to seconds
            # Convert message to dict, remove CRC and internal fields
            data = {k: v for k, v in msg.to_dict().items() if not k.startswith('_')}
            messages.append({
                "message_type": msg_type,
                "timestamp": ts,
                "data": data
            })
        return {
            "status": "success",
            "messages": messages,
            "total_messages": len(messages)
        }
    except Exception as e:
        return {
            "status": "error",
            "error": str(e)
        }
    finally:
        if temp_file is not None:
            try:
                os.unlink(temp_file.name)
            except Exception:
                pass 