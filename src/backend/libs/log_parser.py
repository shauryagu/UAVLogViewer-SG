from pymavlink import mavutil
from pymavlink.DFReader import DFReader_binary
import io
import tempfile
import os


def parse_mavlink_log_bytes(file_bytes):
    """
    Parse a UAV log file (Dataflash .bin or .log) from bytes using pymavlink.
    Returns a summary: message types and their counts.
    """
    temp_file = None
    try:
        # Write bytes to a temporary file
        temp_file = tempfile.NamedTemporaryFile(delete=False, suffix='.bin')
        temp_file.write(file_bytes)
        temp_file.close()
        df = DFReader_binary(temp_file.name)
        msg_counts = {}
        while True:
            msg = df.recv_msg()
            if msg is None:
                break
            msg_type = msg.get_type()
            msg_counts[msg_type] = msg_counts.get(msg_type, 0) + 1
        return {
            "status": "success",
            "message_counts": msg_counts,
            "total_messages": sum(msg_counts.values())
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