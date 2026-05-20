"""
Science Dashboard Layout Persistence Endpoints
================================================

Saves and loads the complete layout configuration for the Science Dashboard
tab (groups of topic watchers, chart types, colours, etc.).

Layout is stored as JSON in ``science_layout.json`` under the backend
directory.

Endpoints:
  GET  /ros2_topics/science-layout       — Load the saved layout
  POST /ros2_topics/science-layout/save  — Save a new layout

Used by: Science tab (Science.jsx)
"""
from __future__ import annotations

import json
import logging
import os
from typing import Any, Dict

from fastapi import APIRouter, Body, HTTPException

router = APIRouter()
logger = logging.getLogger(__name__)

# Persistent storage path builder
def get_layout_file(instance: str) -> str:
    filename = "science_layout.json" if instance == "default" else f"science_layout_{instance}.json"
    return os.path.abspath(
        os.path.join(os.path.dirname(__file__), "..", "data", filename)
    )


# ---------------------------------------------------------------------------
# File helpers
# ---------------------------------------------------------------------------

def _load_layout(instance: str) -> Dict[str, Any]:
    """Read the science layout JSON from disk; return empty dict on error."""
    file_path = get_layout_file(instance)
    try:
        if os.path.exists(file_path):
            with open(file_path, "r") as fh:
                return json.load(fh)
    except Exception as exc:
        logger.warning(f"Failed to load science layout for {instance}: %s", exc)
    return {}


def _save_layout(instance: str, layout: Dict[str, Any]) -> None:
    """Write the science layout JSON to disk."""
    file_path = get_layout_file(instance)
    try:
        with open(file_path, "w") as fh:
            json.dump(layout, fh, indent=2)
    except Exception as exc:
        logger.error(f"Failed to save science layout for {instance}: %s", exc)
        raise


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("/ros/science_layout")
def get_science_layout(instance: str = "default") -> Dict[str, Any]:
    """Get the saved Science Dashboard layout."""
    return _load_layout(instance)


@router.post("/ros/science_layout")
def save_science_layout(body: Dict[str, Any] = Body(...), instance: str = "default") -> Dict[str, str]:
    """
    Save the entire Science Dashboard layout by merging with the existing configuration.
    """
    existing = _load_layout(instance)
    existing.update(body)
    _save_layout(instance, existing)
    return {"status": "saved"}
