import os
import re
import sys
import logging
import subprocess
from datetime import datetime
from fastmcp import FastMCP

from SBC_Tools import enable_debug as cube_enable_debug
from SBC_Tools import disable_and_pull_logs as cube_disable_and_pull_logs

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
LOG_DIR = os.path.join(BASE_DIR, "test_logs")
SCENARIO_FILE = os.path.join(BASE_DIR, "basic_call.xml")

SIPP_PATH = "/usr/bin/sipp"  # SIPp Path
SIPP_LOCAL_IP = "X.X.X.X"  # Your SIPp machine IP

os.makedirs(LOG_DIR, exist_ok=True)


# ******* FastMCP instance *******
mcp = FastMCP("sipp_mcp_server_v1")


# ******* Helper Functions *******
def _extract_call_id(msg_log_path: str) -> str:
    """Extract Call-ID value from SIPp message log."""
    if not os.path.exists(msg_log_path):
        return ""
    with open(msg_log_path, "r") as f:
        content = f.read()
    match = re.search(r"Call-ID:\s*(\S+)", content, re.IGNORECASE)
    return match.group(1).strip() if match else ""


def _get_outcome(msg_log_path: str) -> str:
    """Determine call outcome from SIPp message log response codes."""
    if not os.path.exists(msg_log_path):
        return "UNKNOWN"
    with open(msg_log_path, "r") as f:
        content = f.read()
    responses = re.findall(r"SIP/2\.0 (\d{3})", content)
    if "200" in responses:
        return "ANSWERED"
    if "486" in responses:
        return "BUSY"
    if "404" in responses:
        return "NOT FOUND (404)"
    if "403" in responses:
        return "REJECTED (403)"
    if "407" in responses:
        return "AUTH REQUIRED (407)"
    if "180" in responses:
        return "RANG - NO ANSWER"
    if "100" in responses:
        return "TRYING - NO RESPONSE"
    if "500" in responses:
        return "SERVER ERROR"
    return "UNKNOWN"


def _filter_log_by_call_id(raw_log: str, call_id: str, context: int = 5) -> str:
    """Filter raw CUBE log to lines matching call_id with surrounding context."""
    if not call_id:
        return raw_log
    lines = raw_log.splitlines()
    matched_indices = set()
    for i, line in enumerate(lines):
        if call_id in line:
            start = max(0, i - context)
            end = min(len(lines), i + context + 1)
            matched_indices.update(range(start, end))
    if not matched_indices:
        return raw_log
    return "\n".join(lines[i] for i in sorted(matched_indices))


# ******* TOOLS *******
@mcp.tool()
def enable_debug(cube_ip: str) -> str:
    """
    SSH into the CUBE router and enable 'debug ccsip messages'.
    Always call this FIRST before running a SIPp test so that
    the SIP signalling for the test call is captured in the CUBE log.

    Args:
        cube_ip: IP address of the CUBE router to SSH into.
    """
    logger.info(f"enable_debug called for CUBE: {cube_ip}")

    cube_cfg = {
        "device_type": "cisco_ios",
        "host": cube_ip,
        "username": os.getenv("sbc_ID"),
        "password": os.getenv("sbc_PASS"),
        "timeout": 30,
    }

    success = cube_enable_debug(cube_config=cube_cfg)

    if success:
        return (
            f"debug ccsip messages enabled on CUBE {cube_ip}. "
            f"Ready to run SIPp test."
        )
    return (
        f"Failed to enable debug on CUBE {cube_ip}. Check connectivity and credentials."
    )


@mcp.tool()
def run_sipp_test(extension: str, target_ip: str) -> str:
    """
    Run a single SIPp test call to a phone number or extension.
    Returns the call outcome and Call-ID needed for log filtering.
    Always call this AFTER enable_debug and BEFORE disable_and_pull_logs.
    If extension doesn't have 91 in the beginning then add 91 at the beginning & use the final number as extension.

    Args:
        extension: The phone number or extension to test.
        target_ip: IP address of the SBC or SIP server to send the call to.
    """
    logger.info(f"run_sipp_test called: extension={extension}, target={target_ip}")

    safe_ext = extension.replace("/", "_")
    stats_file = os.path.join(LOG_DIR, f"{safe_ext}_stats.csv")
    msg_log = os.path.join(LOG_DIR, f"{safe_ext}_messages.log")
    err_log = os.path.join(LOG_DIR, f"{safe_ext}_errors.log")

    cmd = [
        SIPP_PATH,
        target_ip,
        "-sf",
        SCENARIO_FILE,
        "-s",
        extension,
        "-i",
        SIPP_LOCAL_IP,
        "-m",
        "1",
        "-d",
        "15000",
        "-timeout",
        "30",
        "-trace_msg",
        "-message_file",
        msg_log,
        "-trace_err",
        "-error_file",
        err_log,
        "-trace_stat",
        "-stf",
        stats_file,
        "-nostdin",
    ]

    try:
        proc = subprocess.run(
            cmd, capture_output=True, text=True, timeout=45, cwd=LOG_DIR
        )
    except subprocess.TimeoutExpired:
        return f"SIPp process timed out for extension {extension}."

    call_id = _extract_call_id(msg_log)
    outcome = _get_outcome(msg_log)

    return (
        f"SIPp test complete.\n"
        f"Extension  : {extension}\n"
        f"Outcome    : {outcome}\n"
        f"Call-ID    : {call_id}\n"
        f"Return code: {proc.returncode}\n\n"
        f"Pass the Call-ID '{call_id}' to disable_and_pull_logs."
    )


@mcp.tool()
def disable_and_pull_logs(cube_ip: str, call_id: str, extension: str) -> str:
    """
    SSH into the CUBE router, disable debug ccsip messages, pull the full
    log buffer, filter it to lines relevant to the SIPp test call using
    the Call-ID & save both raw and filtered logs to disk.
    Always call this AFTER run_sipp_test.

    Args:
        cube_ip:   IP address of the CUBE router.
        call_id:   The Call-ID from the SIPp test call returned by run_sipp_test.
        extension: The extension that was tested, used to name the log file.
    """
    logger.info(f"disable_and_pull_logs: cube={cube_ip}, call_id={call_id}")

    cube_cfg = {
        "device_type": "cisco_ios",
        "host": cube_ip,
        "username": os.getenv("sbc_ID"),
        "password": os.getenv("sbc_PASS"),
        "timeout": 30,
    }

    raw_log = cube_disable_and_pull_logs(cube_config=cube_cfg)

    if not raw_log:
        return "No log output retrieved from CUBE. Cannot proceed with analysis."

    # Save full raw log with timestamp
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    raw_path = os.path.join(LOG_DIR, f"cube_raw_{extension}_{timestamp}.log")
    with open(raw_path, "w") as f:
        f.write(raw_log)

    # Filter by Call-ID and save
    filtered = _filter_log_by_call_id(raw_log, call_id)
    safe_ext = extension.replace("/", "_")
    filtered_path = os.path.join(LOG_DIR, f"cube_filtered_{safe_ext}.log")
    with open(filtered_path, "w") as f:
        f.write(filtered)

    total_lines = len(raw_log.splitlines())
    filtered_lines = len(filtered.splitlines())

    return (
        f"Debug disabled on CUBE {cube_ip}.\n"
        f"Raw log  : {total_lines} lines saved to {raw_path}\n"
        f"Filtered : {filtered_lines} lines matched Call-ID '{call_id}'\n"
        f"Saved to : {filtered_path}\n\n"
        f"Call read_filtered_log with extension '{extension}' to retrieve "
        f"the SIP dialogue for analysis."
    )


@mcp.tool()
def read_filtered_log(extension: str) -> str:
    """
    Reads the filtered CUBE debug log for a previously tested extension
    and returns its full contents. Call this LAST - after disable_and_pull_logs.
    The log contains only the SIP dialogue relevant to the test call.
    Use the contents to diagnose what happened and produce a plain English report.

    Important context for analysis:
    - A CANCEL message appearing after a 183 Session Progress or 200 OK is expected and intentional.
      The SIPp scenario sends a CANCEL after a 10 second pause to terminate
      the call cleanly. This is NOT a failure or warning - treat it as a
      normal call teardown equivalent to a BYE.
    - Only flag CANCEL as a problem if it appears BEFORE a 200 OK except when it's coming after 183 Session Progress,
      which would indicate the call was cancelled before being answered.

    Args:
        extension: The extension that was tested.
    """
    safe_ext = extension.replace("/", "_")
    filtered_path = os.path.join(LOG_DIR, f"cube_filtered_{safe_ext}.log")

    if not os.path.exists(filtered_path):
        return (
            f"Filtered log not found for extension {extension}.\n"
            f"Expected: {filtered_path}\n"
            f"Make sure disable_and_pull_logs was called first."
        )

    with open(filtered_path, "r") as f:
        content = f.read()

    if not content.strip():
        return (
            f"Filtered log is empty for extension {extension}. "
            f"The Call-ID may not have matched any lines in the CUBE debug output."
        )

    return content


# ******* Entry point MCP Server*******
if __name__ == "__main__":
    mcp.run()
