# SIPp Agentic - LLM powered Automated VoIP Call Testing with Python, MCP and Claude

An agentic extension to the [SIPp Python testing framework](https://learnuccollab.com) that combines SIP call testing with real-time CUBE debug capture and Claude-powered log analysis. Instead of manually SSHing into your SBC, running debug commands, and reading through verbose logs, you issue a natural language prompt in Claude Desktop and the agent handles the entire workflow end to end.

This repository accompanies the multi-part blog series on [learnuccollab.com](https://learnuccollab.com/category/sipp/) and video playlist on my [YouTube](https://www.youtube.com/@learnuccollab).

---

## How It Works

The agent follows a four-step sequence driven by Claude Desktop via the Model Context Protocol:

```
1. enable_debug          -> SSH to CUBE, start debug ccsip messages
2. run_sipp_test         -> Fire SIPp test call, capture outcome + Call-ID
3. disable_and_pull_logs -> Stop debug, filter log by Call-ID, save to disk
4. read_filtered_log     -> Return filtered log. Claude reads and produces diagnosis
```

The Call-ID from the SIPp test call is used to filter the CUBE log buffer down to only the lines relevant to that specific call which is typically 30-50 lines instead of thousands before passing anything to Claude.

---

## Repository Structure

```
SIPp_Agentic/
 -- SBC_Tools.py                 # Netmiko SSH functions for CUBE interaction
 -- SIPp_MCP_Svr_Claude_v1.py    # MCP server - Claude
 -- basic_call.xml               # SIPp scenario file (basic call, no audio)
 -- test_logs/                   # Auto-created - raw and filtered log output
 -- README.md
```

---

## Prerequisites

### System
- Python 3.10+
- SIPp installed — built from source recommended:
  ```bash
  sudo apt-get install autoconf libncurses5-dev libpcap-dev libssl-dev g++
  git clone https://github.com/SIPp/sipp.git
  cd sipp && ./build.sh --with-pcap --with-openssl
  ```
- SSH access to your CUBE router from the machine running the MCP server/Python tools
- Claude Desktop

### Python dependencies
```bash
pip install fastmcp netmiko mcp
```

---

## Configuration

### 1. Update `SBC_Tools.py`

Replace the placeholder credentials with your actual CUBE details. For production use, move these to environment variables:

```python
import os

CUBE_CONFIG = {
    "device_type": "cisco_ios",
    "host":        os.environ.get("CUBE_HOST"),
    "username":    os.environ.get("CUBE_USER"),
    "password":    os.environ.get("CUBE_PASS"),
    "timeout":     30,
}
```

### 2. Update `SIPp_MCP_Svr_Claude_v1.py`

Update these values at the top of the file to match your environment. Run command "which sipp" to find the exact path to sipp:

```python
SIPP_PATH     = "/usr/local/bin/sipp"   
SIPP_LOCAL_IP = "X.X.X.X"          # IP of the machine running SIPp
```

Replace the placeholder username/password with your actual CUBE credentials. For production use, move these to environment variables.

```python
cube_cfg = {
  "device_type": "cisco_ios",
  "host": cube_ip,
  "username": "admin",
  "password": "pass@123",
  "timeout": 30,
}
```
---

## Claude Desktop Setup

Add the following entry to your Claude Desktop config file (`claude_desktop_config.json`):

```json
"mcpServers": {
    "sipp_mcp_server_v1": {
        "command": "python3",
        "args": [
            "/absolute/path/to/SIPp_Agentic/SIPp_MCP_Svr_Claude_v1.py"
        ]
    }
}
```

Restart Claude Desktop. The four tools should appear in the tools panel as shown below.

<img width="803" height="352" alt="Tools" src="https://github.com/user-attachments/assets/87366209-6e33-44b8-a882-6c5b00457327" />


---

## Usage

Once the MCP server is connected, prompt Claude Desktop naturally like:

```
Test number 918765674532 via CUBE 10.10.10.2 and give me a full report
```

**Make sure to add 91 in the beginning.** 

**Replace the CUBE IP with your actual CUBE IP address**


Claude will call the four tools based on their need and produce a plain English diagnosis of what happened on the call.

---

## Tool Reference

### `enable_debug(cube_ip)`
SSHes into the CUBE and runs `debug ccsip messages`. Call this before `run_sipp_test`.

| Parameter | Type | Description |
|---|---|---|
| `cube_ip` | string | IP address of the CUBE router |

---

### `run_sipp_test(extension, target_ip)`
Fires a single SIPp test call. Returns the call outcome and Call-ID.

| Parameter | Type | Description |
|---|---|---|
| `extension` | string | Phone number or extension to test |
| `target_ip` | string | IP address of the SBC or SIP server |

**Returns:** Outcome string (ANSWERED, BUSY, NOT FOUND, REJECTED, AUTH REQUIRED, RANG - NO ANSWER, TRYING - NO RESPONSE) and the Call-ID for use in the next step.

---

### `disable_and_pull_logs(cube_ip, call_id, extension)`
Disables debug on the CUBE, pulls the full log buffer, filters it by Call-ID, and saves both raw and filtered logs to `test_logs/`.

| Parameter | Type | Description |
|---|---|---|
| `cube_ip` | string | IP address of the CUBE router |
| `call_id` | string | Call-ID returned by `run_sipp_test` |
| `extension` | string | Extension tested - used to name the log file |

---

### `read_filtered_log(extension)`
Returns the filtered log content as a string for Claude to read and analyse.

| Parameter | Type | Description |
|---|---|---|
| `extension` | string | Extension that was tested |

---

## Log Files

All logs are written to the `test_logs/` directory:

| File | Description |
|---|---|
| `<extension>_messages.log` | Full SIP message log from SIPp (`-trace_msg`) |
| `<extension>_errors.log` | SIPp error log (`-trace_err`) |
| `<extension>_stats.csv` | SIPp statistics CSV (`-trace_stat`) |
| `cube_raw_<extension>_<timestamp>.log` | Full raw CUBE log buffer |
| `cube_filtered_<extension>.log` | Filtered log — Call-ID matched lines only |

---

## Important Notes

**CANCEL is expected** - The `basic_call.xml` scenario sends a CANCEL after a 10-second pause to terminate the call cleanly. This is not a failure. It only flags CANCEL as a problem if it appears before a 200 OK & for any message except 183 Session in Progress.

**Scope of the test** - A successful result confirms the path between your test machine and the SBC is working and the SBC is accepting the call. It does not verify delivery beyond the SBC to the PSTN destination.

**Concurrent calls** - In a busy production environment, enable debug only for the duration of the test to minimise noise in the log buffer. The Call-ID filtering handles most of this but shorter debug windows mean cleaner logs.

**Phone Number format** - My CUBE/SBC environment is expecting 91 as the prefixes for long distance calls. That's why I prefixed the number with 91. Yours may differ. So, format the number in your prompt according to your own dial-plan. 

---

## Related Blog Posts

- [Part 1 - Stop Testing Phone Numbers Manually: Let SIPp Do It](https://learnuccollab.com/2026/06/21/automated-testing-phone-numbers-with-sipp/)
- [Part 2 - SIPp at Scale: Driving Bulk Automated Call Tests with Python](https://learnuccollab.com/2026/08/09/sipp-at-scale-driving-bulk-automated-call-tests-with-python/)
- [Part 3 - Build a Django GUI for SIP Call Testing](https://learnuccollab.com/2026/09/20/build-a-django-gui-for-sip-phone-call-testing/)
- [Part 4 - Enhance SIP VoIP Call Testing with Agentic AI LLM Integration](https://learnuccollab.com/2026/09/26/enhance-sip-voip-call-testing-with-agentic-ai-llm-integration/)

---

## Related YouTube Explanatory Videos

- [Stop Testing Phone Numbers Manually: Let SIPp Do It](https://youtu.be/inulTQSeWwQ?si=iHankRLgPV70kgoQ)
- [SIPp at Scale: Driving Bulk Automated Call Tests with Python](https://youtu.be/zdwOsXrXJDA?si=beGKkOgXsKoMbR04)
- [CLI to GUI: Automating SIPp VoIP Call Testing with Django & Python](https://youtu.be/-tDElcYFS4A?si=QBQGjG0pyn6k6Vfn)
