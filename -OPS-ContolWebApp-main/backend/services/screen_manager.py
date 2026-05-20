"""Screen session management helpers extracted from the monolithic server."""
from __future__ import annotations

import logging
import os
import re
import shlex
import shutil
import subprocess
import threading
import time
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class ScreenManager:
    """Manage ROS 2 screen sessions and script definitions."""

    def __init__(self, base_dir: str) -> None:
        self.base_dir = Path(base_dir)
        self.lock = threading.Lock()
        self.xml_path = self.base_dir / "data" / "jetson_scripts.xml"
        self.log_dir = self.base_dir / "logs"
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.screen_binary = shutil.which("screen")
        self.scripts: Dict[str, Dict[str, Any]] = {}
        self.history: Dict[str, Dict[str, Any]] = {}
        self.load_scripts()

    def _default_scripts(self) -> List[Dict[str, Any]]:
        return [
            {
                "name": "bringup_navigation",
                "session": "ros2-nav",
                "command": "ros2 launch nav_bringup bringup_launch.py",
                "working_dir": None,
                "auto_restart": False,
                "description": "Standard navigation launch",
                "tags": ["nav", "launch"],
            },
            {
                "name": "perception_stack",
                "session": "ros2-perception",
                "command": "ros2 launch perception bringup.launch.py",
                "working_dir": None,
                "auto_restart": False,
                "description": "Perception pipeline",
                "tags": ["perception"],
            },
        ]

    def _split_tags(self, value: Optional[str]) -> List[str]:
        if not value:
            return []
        return [tag.strip() for tag in value.split(",") if tag.strip()]

    def _join_tags(self, tags: Optional[List[str]]) -> str:
        if not tags:
            return ""
        return ", ".join(sorted({tag.strip() for tag in tags if tag.strip()}))

    def _sanitize_session(self, value: Optional[str]) -> str:
        if not value:
            value = f"ros2-{int(time.time())}"
        base = re.sub(r"[^a-zA-Z0-9_-]+", "-", value.strip().lower())
        base = base.strip("-") or "ros2"
        return base[:48]

    def _ensure_screen_available(self) -> None:
        if not self.screen_binary:
            self.screen_binary = shutil.which("screen")
        if not self.screen_binary:
            raise RuntimeError("screen command not found on this system")

    def _normalise_script(self, script_data: Dict[str, Any]) -> Dict[str, Any]:
        name = (script_data.get("name") or "").strip()
        if not name:
            raise ValueError("Script name is required")
        command = (script_data.get("command") or "").strip()
        if not command:
            raise ValueError("Script command is required")
        session = self._sanitize_session(script_data.get("session") or name)
        working_dir = (script_data.get("working_dir") or "").strip() or None
        auto_restart = bool(script_data.get("auto_restart", False))
        description = (script_data.get("description") or "").strip() or None
        tags = script_data.get("tags") or []
        if isinstance(tags, str):
            tags = self._split_tags(tags)
        tags = [tag for tag in tags if tag]
        return {
            "name": name,
            "session": session,
            "command": command,
            "working_dir": working_dir,
            "auto_restart": auto_restart,
            "description": description,
            "tags": tags,
        }

    def _save_scripts_locked(self) -> None:
        root = ET.Element("jetsonScripts")
        for script in sorted(self.scripts.values(), key=lambda s: s["name"].lower()):
            script_el = ET.SubElement(root, "script")
            ET.SubElement(script_el, "name").text = script["name"]
            ET.SubElement(script_el, "session").text = script["session"]
            ET.SubElement(script_el, "command").text = script["command"]
            ET.SubElement(script_el, "workingDir").text = script["working_dir"] or ""
            ET.SubElement(script_el, "autoRestart").text = "true" if script["auto_restart"] else "false"
            ET.SubElement(script_el, "description").text = script.get("description") or ""
            ET.SubElement(script_el, "tags").text = self._join_tags(script.get("tags"))
        tree = ET.ElementTree(root)
        tree.write(self.xml_path, encoding="utf-8", xml_declaration=True)

    def load_scripts(self) -> None:
        with self.lock:
            self.scripts.clear()
            if not self.xml_path.exists():
                for script in self._default_scripts():
                    normalised = self._normalise_script(script)
                    self.scripts[normalised["name"]] = normalised
                self._save_scripts_locked()
                return
            try:
                tree = ET.parse(self.xml_path)
                root = tree.getroot()
                for script_el in root.findall("script"):
                    script_dict = {
                        "name": script_el.findtext("name", ""),
                        "session": script_el.findtext("session", ""),
                        "command": script_el.findtext("command", ""),
                        "working_dir": script_el.findtext("workingDir", ""),
                        "auto_restart": script_el.findtext("autoRestart", "false"),
                        "description": script_el.findtext("description", ""),
                        "tags": script_el.findtext("tags", ""),
                    }
                    try:
                        normalised = self._normalise_script(script_dict)
                        self.scripts[normalised["name"]] = normalised
                    except ValueError as parse_error:
                        logger.warning("Skipping script entry due to error: %s", parse_error)
                if not self.scripts:
                    for script in self._default_scripts():
                        normalised = self._normalise_script(script)
                        self.scripts[normalised["name"]] = normalised
                    self._save_scripts_locked()
            except Exception as exc:
                logger.error("Failed to load jetson scripts XML: %s", exc)
                self.scripts.clear()
                for script in self._default_scripts():
                    normalised = self._normalise_script(script)
                    self.scripts[normalised["name"]] = normalised
                self._save_scripts_locked()

    def list_scripts(self) -> List[Dict[str, Any]]:
        with self.lock:
            return [
                {
                    **script,
                    "tags": list(script.get("tags", [])),
                }
                for script in sorted(self.scripts.values(), key=lambda s: s["name"].lower())
            ]

    def get_script(self, name: str) -> Optional[Dict[str, Any]]:
        with self.lock:
            script = self.scripts.get(name)
            if not script:
                return None
            return {
                **script,
                "tags": list(script.get("tags", [])),
            }

    def add_or_update_script(self, script_data: Dict[str, Any]) -> Dict[str, Any]:
        normalised = self._normalise_script(script_data)
        with self.lock:
            self.scripts[normalised["name"]] = normalised
            self._save_scripts_locked()
        return self.get_script(normalised["name"])

    def remove_script(self, name: str) -> bool:
        with self.lock:
            if name not in self.scripts:
                return False
            self.scripts.pop(name)
            self._save_scripts_locked()
        return True

    def find_script_by_session(self, session: str) -> Optional[Dict[str, Any]]:
        with self.lock:
            for script in self.scripts.values():
                if script.get("session") == session:
                    return {
                        **script,
                        "tags": list(script.get("tags", [])),
                    }
        return None

    def is_session_active(self, session: str) -> bool:
        for entry in self.list_active_screens():
            if entry.get("session") == session:
                return True
        return False

    def _register_history(self, session: str, info: Dict[str, Any]) -> None:
        with self.lock:
            self.history[session] = info

    def list_active_screens(self) -> List[Dict[str, Any]]:
        self._ensure_screen_available()
        try:
            output = subprocess.check_output([self.screen_binary, "-ls"], text=True, stderr=subprocess.STDOUT)
        except subprocess.CalledProcessError as exc:
            output = exc.output
        except FileNotFoundError as exc:  # pragma: no cover - defensive logging
            raise RuntimeError("screen command not available") from exc

        sessions: List[Dict[str, Any]] = []
        for raw_line in output.splitlines():
            line = raw_line.strip()
            if not line or "Sockets in" in line or "There is" in line or "There are" in line:
                continue
            if "." not in line or "(" not in line:
                continue
            parts = line.split()
            session_part = parts[0]
            status = parts[-1].strip("()") if parts[-1].startswith("(") else "unknown"
            try:
                pid, session_name = session_part.split(".", 1)
            except ValueError:
                continue
            script = self.find_script_by_session(session_name)
            history_entry = self.history.get(session_name, {})
            sessions.append(
                {
                    "pid": pid,
                    "session": session_name,
                    "status": status,
                    "script": script.get("name") if script else None,
                    "started_at": history_entry.get("started_at"),
                    "auto_restart": history_entry.get("auto_restart"),
                    "log_path": str(self.log_dir / f"{session_name}.log"),
                }
            )
        return sessions

    def _build_shell_command(self, command: str, working_dir: Optional[str], auto_restart: bool) -> str:
        base_command = command.strip()
        if working_dir:
            base_command = f"cd {shlex.quote(working_dir)} && {base_command}"
        if auto_restart:
            base_command = (
                "while true; do "
                f"{base_command}; "
                "echo '--- restarting in 3s ---'; "
                "sleep 3; "
                "done"
            )
        return base_command

    def _run_session(
        self,
        *,
        session: str,
        command: str,
        working_dir: Optional[str],
        auto_restart: bool,
        source_script: Optional[str],
    ) -> Dict[str, Any]:
        self._ensure_screen_available()
        session_name = self._sanitize_session(session)
        if self.is_session_active(session_name):
            raise ValueError(f"Session '{session_name}' is already active")
        if not command.strip():
            raise ValueError("Command cannot be empty")

        log_path = self.log_dir / f"{session_name}.log"
        shell_command = self._build_shell_command(command, working_dir, auto_restart)
        screen_cmd = [
            self.screen_binary,
            "-S",
            session_name,
            "-dm",
            "-L",
            "-Logfile",
            str(log_path),
            "bash",
            "-lc",
            shell_command,
        ]

        try:
            subprocess.check_call(screen_cmd)
        except subprocess.CalledProcessError as exc:
            raise RuntimeError(f"Failed to start screen session: {exc}") from exc

        started_at = datetime.now().isoformat()
        self._register_history(
            session_name,
            {
                "started_at": started_at,
                "source_script": source_script,
                "auto_restart": auto_restart,
                "command": command,
                "working_dir": working_dir,
            },
        )
        return {
            "session": session_name,
            "log_path": str(log_path),
            "started_at": started_at,
            "auto_restart": auto_restart,
            "source_script": source_script,
        }

    def run_script(
        self,
        script_name: str,
        *,
        session_override: Optional[str] = None,
        working_dir_override: Optional[str] = None,
        auto_restart_override: Optional[bool] = None,
        command_override: Optional[str] = None,
    ) -> Dict[str, Any]:
        script = self.get_script(script_name)
        if not script:
            raise ValueError(f"Script '{script_name}' not found")
        session = session_override or script.get("session") or script_name
        command = command_override or script.get("command")
        working_dir = working_dir_override or script.get("working_dir")
        auto_restart = (
            auto_restart_override
            if auto_restart_override is not None
            else bool(script.get("auto_restart", False))
        )
        return self._run_session(
            session=session,
            command=command,
            working_dir=working_dir,
            auto_restart=auto_restart,
            source_script=script_name,
        )

    def run_custom(
        self,
        *,
        command: str,
        session: Optional[str] = None,
        working_dir: Optional[str] = None,
        auto_restart: Optional[bool] = False,
    ) -> Dict[str, Any]:
        if not command or not command.strip():
            raise ValueError("Command is required")
        final_session = session or f"custom-{int(time.time())}"
        return self._run_session(
            session=final_session,
            command=command,
            working_dir=working_dir,
            auto_restart=bool(auto_restart),
            source_script=None,
        )

    def kill_session(self, session: str) -> Dict[str, Any]:
        self._ensure_screen_available()
        session_name = self._sanitize_session(session)
        try:
            subprocess.check_call([self.screen_binary, "-S", session_name, "-X", "quit"])
        except subprocess.CalledProcessError as exc:
            raise RuntimeError(f"Failed to terminate session '{session_name}'") from exc
        with self.lock:
            self.history.pop(session_name, None)
        return {"session": session_name}

    def tail_log(self, session: str, lines: int = 200) -> Dict[str, Any]:
        session_name = self._sanitize_session(session)
        log_path = self.log_dir / f"{session_name}.log"
        if not log_path.exists():
            raise FileNotFoundError(f"Log file for session '{session_name}' not found")
        with log_path.open("r", encoding="utf-8", errors="ignore") as handle:
            content = handle.readlines()
        if lines > 0:
            content = content[-lines:]
        text = "".join(content)
        history_entry = self.history.get(session_name, {})
        return {
            "session": session_name,
            "log": text,
            "lines": len(content),
            "log_path": str(log_path),
            "started_at": history_entry.get("started_at"),
            "auto_restart": history_entry.get("auto_restart"),
        }
