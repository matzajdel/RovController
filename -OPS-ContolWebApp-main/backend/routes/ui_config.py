"""
UI Configuration Persistence Endpoints
=======================================

Saves and loads per-topic button/widget configuration for the frontend
array-topic panels (e.g. custom labels and default values per button index).

Configuration is stored as JSON in ``saved_ui_config.json`` under the
backend directory.

Endpoints:
  GET  /ros2_topics/ui-config        — Load UI config (optionally filter by topic)
  POST /ros2_topics/ui-config/save   — Save UI config for a specific topic

Used by: Sterowanie tab → ArrayTopicButtons component
"""
from __future__ import annotations

import json
import logging
import os
from typing import Any, Dict

from fastapi import APIRouter, Body, HTTPException

router = APIRouter()
logger = logging.getLogger(__name__)

# Persistent storage path
SAVED_UI_CONFIG_FILE = os.path.join(
    os.path.dirname(__file__), "..", "data", "saved_ui_config.json"
)


# ---------------------------------------------------------------------------
# File helpers
# ---------------------------------------------------------------------------

def _load_ui_config() -> Dict[str, Any]:
    """Read the UI config JSON from disk; return empty dict on error."""
    try:
        if os.path.exists(SAVED_UI_CONFIG_FILE):
            with open(SAVED_UI_CONFIG_FILE, "r") as fh:
                return json.load(fh)
    except Exception as exc:
        logger.warning("Failed to load UI config: %s", exc)
    return {}


def _save_ui_config(config: Dict[str, Any]) -> None:
    """Write the UI config JSON to disk."""
    try:
        with open(SAVED_UI_CONFIG_FILE, "w") as fh:
            json.dump(config, fh, indent=2)
    except Exception as exc:
        logger.error("Failed to save UI config: %s", exc)
        raise


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("/ros/ui_config")
def get_ui_config(topic: str = None) -> Dict[str, Any]:
    """
    Get saved UI button configuration.

    If *topic* is provided, return config for that topic only;
    otherwise return the entire config dictionary.
    """
    config = _load_ui_config()
    if topic:
        return config.get(topic, {})
    return config


@router.post("/ros/ui_config")
def save_ui_config(body: Dict[str, Any] = Body(...)) -> Dict[str, str]:
    """
    Save UI configuration for a specific topic.

    Body:
        topic  (str)  — ROS topic name, e.g. "/array_topic"
        config (dict) — Per-index settings, e.g. {"0": {"label": "X", "value": 10}}
    """
    topic = body.get("topic")
    per_topic = body.get("config")

    if not topic or per_topic is None:
        raise HTTPException(status_code=400, detail="Missing 'topic' or 'config'")

    config = _load_ui_config()
    config[topic] = per_topic
    _save_ui_config(config)
    return {"status": "saved"}
