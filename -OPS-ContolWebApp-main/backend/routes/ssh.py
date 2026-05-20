"""SSH command execution for remote robot control."""
from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import subprocess
import threading
from collections import deque
from datetime import datetime
from typing import Dict, Optional

from fastapi import APIRouter, HTTPException
from models import SSHCommandRequest, MicroRosDeviceRequest

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/ssh")

ROBOT_SSH_HOST = "192.168.2.50"
ROBOT_SSH_USER = "lrt_geeokom"
ROBOT_SSH_PASS = "qwerty"

STM32_ALIAS_FILE = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "config", "stm32_aliases.json")
)

# Store SSH session logs in memory (last 1000 lines per session)
ssh_logs: Dict[str, deque] = {}
ssh_processes: Dict[str, subprocess.Popen] = {}
ssh_lock = threading.Lock()


def _load_stm32_aliases() -> dict:
    """Load user-defined STM32 aliases from JSON config."""
    try:
        if os.path.exists(STM32_ALIAS_FILE):
            with open(STM32_ALIAS_FILE, "r", encoding="utf-8") as fh:
                data = json.load(fh)
                aliases = data.get("device_aliases", {})
                if isinstance(aliases, dict):
                    return {str(k): str(v) for k, v in aliases.items()}
    except Exception as exc:
        logger.warning("Failed to load STM32 aliases: %s", exc)
    return {}


def _save_stm32_aliases(aliases: dict) -> None:
    """Persist user-defined STM32 aliases to JSON config."""
    os.makedirs(os.path.dirname(STM32_ALIAS_FILE), exist_ok=True)
    with open(STM32_ALIAS_FILE, "w", encoding="utf-8") as fh:
        json.dump({"device_aliases": aliases}, fh, indent=2)


def _is_stm32_device_id(device_id: str) -> bool:
    token = device_id.lower()
    return ("stm32" in token) or ("stmicro" in token) or ("stlink" in token)


def _device_id_to_session(device_id: str) -> str:
    """Generate a stable screen session name from a USB device ID."""
    sanitized = re.sub(r"[^a-zA-Z0-9]+", "_", device_id).strip("_").lower()
    if len(sanitized) > 48:
        sanitized = sanitized[-48:]
    return f"microros_agent_{sanitized}"


def _extract_session_name(screen_entry: str) -> str:
    """Extract screen session from lines like '1234.session_name'."""
    token = screen_entry.strip().split()[0]
    if "." in token:
        return token.split(".", 1)[1]
    return token


def _probe_microros_devices() -> list[dict]:
    """Discover STM32 serial devices on robot and correlate with running sessions."""
    aliases = _load_stm32_aliases()
    probe_cmd = (
        "for link in /dev/serial/by-id/*; do "
        "[ -L \"$link\" ] || continue; "
        "target=$(readlink -f \"$link\" 2>/dev/null || true); "
        "[ -n \"$target\" ] || continue; "
        "case \"$target\" in /dev/ttyACM*|/dev/ttyUSB*) ;; *) continue;; esac; "
        "echo \"DEV|$(basename \"$link\")|$target\"; "
        "done; "
        "screen -ls 2>/dev/null | awk '/microros_agent_/ {print \"SCR|\" $1}'"
    )
    ssh_cmd = [
        "sshpass", "-p", ROBOT_SSH_PASS,
        "ssh", "-o", "StrictHostKeyChecking=no", "-o", "ConnectTimeout=3",
        f"{ROBOT_SSH_USER}@{ROBOT_SSH_HOST}",
        probe_cmd,
    ]

    running_sessions: set[str] = set()
    raw_devices: list[tuple[str, str]] = []

    try:
        result = subprocess.run(
            ssh_cmd,
            timeout=6,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
        )
        for line in (result.stdout or "").splitlines():
            if line.startswith("SCR|"):
                running_sessions.add(_extract_session_name(line.split("|", 1)[1]))
            elif line.startswith("DEV|"):
                parts = line.split("|", 2)
                if len(parts) == 3:
                    raw_devices.append((parts[1], parts[2]))
    except Exception as exc:
        logger.error("Failed to probe STM32 devices: %s", exc)

    devices = []
    for device_id, tty_device in raw_devices:
        if not _is_stm32_device_id(device_id):
            continue
        session = _device_id_to_session(device_id)
        alias = aliases.get(device_id, "")
        devices.append(
            {
                "device_id": device_id,
                "tty_device": tty_device,
                "session": session,
                "alias": alias,
                "display_name": alias or device_id,
                "running": session in running_sessions,
            }
        )

    def _sort_key(item: dict):
        tty = item.get("tty_device", "")
        match = re.search(r"(\d+)$", tty)
        return (int(match.group(1)) if match else 9999, tty)

    devices.sort(key=_sort_key)
    return devices


def _log_reader(process: subprocess.Popen, session_name: str):
    """Background thread to read SSH output and store in logs."""
    global ssh_logs
    if session_name not in ssh_logs:
        ssh_logs[session_name] = deque(maxlen=1000)
    
    try:
        for line in iter(process.stdout.readline, b''):
            if line:
                decoded = line.decode('utf-8', errors='replace').rstrip()
                with ssh_lock:
                    ssh_logs[session_name].append(f"[{datetime.now().strftime('%H:%M:%S')}] {decoded}")
        
        # Process ended
        exit_code = process.wait()
        with ssh_lock:
            ssh_logs[session_name].append(f"[{datetime.now().strftime('%H:%M:%S')}] === Process exited with code {exit_code} ===")
            if session_name in ssh_processes:
                del ssh_processes[session_name]
    except Exception as e:
        with ssh_lock:
            ssh_logs[session_name].append(f"[ERROR] Log reader failed: {e}")


@router.post("/run")
def run_ssh_command(req: SSHCommandRequest) -> dict:
    """Execute a command on remote robot via SSH within a detached screen session."""
    session_name = req.session_name or f"ssh_{datetime.now().strftime('%H%M%S')}"
    
    # Kill existing process if running
    password = req.password or "qwerty"
    logfile = f"/tmp/{session_name}.log"
    pidfile = f"/tmp/{session_name}.pid"
    
    # Kill existing process using process group
    kill_cmd = f"screen -S {session_name} -X quit 2>/dev/null || true"
    kill_ssh_cmd = [
        "sshpass", "-p", password,
        "ssh", "-o", "StrictHostKeyChecking=no", "-o", "ConnectTimeout=5",
        f"{req.user}@{req.host}",
        kill_cmd
    ]
    
    try:
        subprocess.run(kill_ssh_cmd, timeout=3, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except:
        pass
    
    # Build screen command with logging enabled
    # -dm starts detached, -S sets name, -L -Logfile logs to file
    screen_cmd = f"screen -dm -S {session_name} -L -Logfile {logfile} bash -c '{req.command}'"
    
    ssh_cmd = [
        "sshpass", "-p", password,
        "ssh", "-o", "StrictHostKeyChecking=no", "-o", "ConnectTimeout=5",
        f"{req.user}@{req.host}",
        screen_cmd
    ]
    
    try:
        # Start nohup process on remote
        result = subprocess.run(
            ssh_cmd,
            timeout=10,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True
        )
        
        with ssh_lock:
            ssh_logs[session_name] = deque(maxlen=1000)
            ssh_logs[session_name].append(f"[{datetime.now().strftime('%H:%M:%S')}] === Started screen session: {session_name} ===")
            ssh_logs[session_name].append(f"[{datetime.now().strftime('%H:%M:%S')}] === Host: {req.user}@{req.host} ===")
            ssh_logs[session_name].append(f"[{datetime.now().strftime('%H:%M:%S')}] === Command: {req.command} ===")
            ssh_logs[session_name].append(f"[{datetime.now().strftime('%H:%M:%S')}] === Logfile: {logfile} ===")
            if result.returncode == 0:
                ssh_logs[session_name].append(f"[{datetime.now().strftime('%H:%M:%S')}] Process started successfully")
                # Mark as running in our tracking
                ssh_processes[session_name] = {
                    "pidfile": pidfile,
                    "logfile": logfile,
                    "host": req.host,
                    "user": req.user
                }
            else:
                ssh_logs[session_name].append(f"[{datetime.now().strftime('%H:%M:%S')}] ERROR: {result.stdout}")
        
        return {
            "status": "ok",
            "session": session_name,
            "command": req.command,
            "message": f"Screen session '{session_name}' started on {req.host}"
        }
    except FileNotFoundError:
        raise HTTPException(status_code=500, detail="sshpass not installed. Run: sudo apt install sshpass")
    except subprocess.TimeoutExpired:
        raise HTTPException(status_code=500, detail="SSH connection timeout")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to start SSH: {str(e)}")



@router.get("/sessions")
def list_ssh_sessions() -> dict:
    """List active SSH sessions, including a probe for MicroROS agents."""
    active_sessions = []
    
    # 1. Probe remote for running MicroROS agents (screens)
    try:
        # Check for all known MicroROS sessions (legacy and ID-based)
        check_cmd = "screen -ls | grep microros_agent_ || true"
        password = ROBOT_SSH_PASS
        host = ROBOT_SSH_HOST
        user = ROBOT_SSH_USER
        
        ssh_cmd = [
            "sshpass", "-p", password,
            "ssh", "-o", "StrictHostKeyChecking=no", "-o", "ConnectTimeout=2",
            f"{user}@{host}",
            check_cmd
        ]
        
        result = subprocess.run(ssh_cmd, timeout=3, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
        
        if result.returncode == 0 and result.stdout.strip():
            lines = result.stdout.strip().split('\n')
            for line in lines:
                if not line.strip() or "microros_agent_" not in line:
                    continue
                # Output format: \t1234.microros_agent_xxx\t(Detached)
                parts = line.strip().split()
                if not parts:
                    continue
                full_name = parts[0] # e.g., 1234.microros_agent_acm0
                if '.' in full_name:
                    session_name = full_name.split('.', 1)[1]
                else:
                    session_name = full_name
                
                # Update our local knowledge
                with ssh_lock:
                    if session_name not in ssh_processes:
                         ssh_processes[session_name] = {
                            "logfile": f"/tmp/{session_name}.log",
                            "host": host,
                            "user": user
                        }
    except Exception as e:
        logger.error(f"Failed to probe remote sessions: {e}")

    # 2. Build response from local knowledge (now updated)
    with ssh_lock:
        for name, info in ssh_processes.items():
            # If it's a Popen object (local process), check poll()
            is_running = False
            if isinstance(info, subprocess.Popen):
                 is_running = info.poll() is None
            elif isinstance(info, dict):
                # We assume it's running if it's in the dict (verified by probe above or just started)
                # But for safety, we can trust the probe we just did for MicroROS agents.
                # For others, we assume true until next probe or action.
                is_running = True
                
            active_sessions.append({
                "session": name,
                "running": is_running
            })
            
    return {"sessions": active_sessions}


@router.get("/microros/config")
def get_microros_config() -> dict:
    """Return current STM32 alias configuration used by Status Jetson."""
    return {
        "device_aliases": _load_stm32_aliases(),
        "config_file": STM32_ALIAS_FILE,
    }


@router.post("/microros/config")
def save_microros_config(body: dict) -> dict:
    """Save STM32 alias mapping. Body: { device_aliases: {<device_id>: <name>} }."""
    aliases = body.get("device_aliases", {})
    if not isinstance(aliases, dict):
        raise HTTPException(status_code=400, detail="'device_aliases' must be a dictionary")
    normalized = {str(k): str(v) for k, v in aliases.items()}
    _save_stm32_aliases(normalized)
    return {"status": "saved", "device_aliases": normalized, "config_file": STM32_ALIAS_FILE}


@router.get("/microros/devices")
def list_microros_devices() -> dict:
    """List detected STM32 devices with stable IDs, aliases and running state."""
    devices = _probe_microros_devices()
    return {"devices": devices, "count": len(devices)}


@router.post("/microros/start")
def start_microros_agent(req: MicroRosDeviceRequest) -> dict:
    """Start MicroROS agent using a stable STM32 USB ID instead of tty index."""
    devices = _probe_microros_devices()
    target = next((d for d in devices if d["device_id"] == req.device_id), None)
    if not target:
        raise HTTPException(status_code=404, detail=f"STM32 device '{req.device_id}' not found")

    command = (
        "cd ~ && cd microros/ && source install/setup.bash && "
        f"ros2 run micro_ros_agent micro_ros_agent serial --dev {target['tty_device']} -b {int(req.baud_rate)}"
    )

    result = run_ssh_command(
        SSHCommandRequest(
            host=ROBOT_SSH_HOST,
            user=ROBOT_SSH_USER,
            password=ROBOT_SSH_PASS,
            command=command,
            session_name=target["session"],
        )
    )

    result["device_id"] = target["device_id"]
    result["tty_device"] = target["tty_device"]
    result["display_name"] = target["display_name"]
    return result


@router.post("/microros/stop")
def stop_microros_agent(req: MicroRosDeviceRequest) -> dict:
    """Stop MicroROS agent using stable STM32 USB ID session naming."""
    session = _device_id_to_session(req.device_id)
    result = kill_ssh_session(session)
    result["device_id"] = req.device_id
    return result


@router.get("/logs/{session}")
def get_ssh_logs(session: str) -> dict:
    """Get logs for a specific SSH nohup process from remote robot."""
    with ssh_lock:
        if session not in ssh_logs:
            ssh_logs[session] = deque(maxlen=1000)
            ssh_logs[session].append(f"[{datetime.now().strftime('%H:%M:%S')}] Initializing log retrieval...")
        
        # Get session info
        if session in ssh_processes and isinstance(ssh_processes[session], dict):
            info = ssh_processes[session]
            logfile = info.get("logfile", f"/tmp/{session}.log")
            pidfile = info.get("pidfile", f"/tmp/{session}.pid")
            host = info.get("host", "192.168.2.50")
            user = info.get("user", "lrt_geeokom")
        else:
            logfile = f"/tmp/{session}.log"
            pidfile = f"/tmp/{session}.pid"
            host = "192.168.2.50"
            user = "lrt_geeokom"
        
        password = "qwerty"
        # Read logfile content (last 100 lines)
        log_cmd = f"tail -n 100 {logfile} 2>/dev/null || echo 'No logs available or file not found'"
        
        ssh_cmd = [
            "sshpass", "-p", password,
            "ssh", "-o", "StrictHostKeyChecking=no", "-o", "ConnectTimeout=3",
            f"{user}@{host}",
            log_cmd
        ]
        
        is_running = False
        try:
            result = subprocess.run(
                ssh_cmd,
                timeout=5,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True
            )
            
            if result.returncode == 0 and result.stdout.strip():
                # Replace old logs with new ones from file
                ssh_logs[session] = deque(maxlen=1000)
                new_logs = result.stdout.strip().split('\n')
                for log_line in new_logs:
                    if log_line.strip():
                        ssh_logs[session].append(log_line)
            
            # Check if process is still running
            check_cmd = f"screen -ls | grep -q '\\.{session}\\b' && echo 'RUNNING' || echo 'STOPPED'"
            check_ssh = [
                "sshpass", "-p", password,
                "ssh", "-o", "StrictHostKeyChecking=no", "-o", "ConnectTimeout=3",
                f"{user}@{host}",
                check_cmd
            ]
            check_result = subprocess.run(check_ssh, timeout=3, stdout=subprocess.PIPE, text=True)
            is_running = "RUNNING" in check_result.stdout
            
        except Exception as e:
            ssh_logs[session].append(f"[{datetime.now().strftime('%H:%M:%S')}] Error fetching logs: {str(e)}")
            is_running = False
        
        logs = list(ssh_logs[session])
        
        return {
            "session": session,
            "logs": logs,
            "log_text": "\n".join(logs),
            "line_count": len(logs),
            "running": is_running
        }


@router.post("/kill/{session}")
def kill_ssh_session(session: str) -> dict:
    """Kill a running SSH screen process on remote robot."""
    # Get session info
    with ssh_lock:
        if session in ssh_processes and isinstance(ssh_processes[session], dict):
            info = ssh_processes[session]
            host = info.get("host", "192.168.2.50")
            user = info.get("user", "lrt_geeokom")
        else:
            host = "192.168.2.50"
            user = "lrt_geeokom"
            
        # Remove from local tracking immediately
        if session in ssh_processes:
            del ssh_processes[session]
    
    password = "qwerty"
    kill_cmd = f"screen -S {session} -X quit 2>/dev/null || true"
    
    ssh_cmd = [ 
        "sshpass", "-p", password,
        "ssh", "-o", "StrictHostKeyChecking=no", "-o", "ConnectTimeout=3",
        f"{user}@{host}",
        kill_cmd
    ]
    
    try:
        result = subprocess.run(ssh_cmd, timeout=5, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        
        with ssh_lock:
            if session in ssh_logs:
                ssh_logs[session].append(f"[{datetime.now().strftime('%H:%M:%S')}] === Process killed by user ===")
        
        return {"status": "ok", "session": session, "message": f"Process '{session}' terminated"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to kill process: {str(e)}")
