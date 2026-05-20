"""
sequence.py — REST API for Science Automation Sequences
=========================================================
Endpoints:
  GET  /science/sequences              — list saved sequences
  POST /science/sequences              — save/update a sequence
  DELETE /science/sequences/{seq_id}   — delete a sequence
  POST /science/sequence/run           — start running a sequence
  GET  /science/sequence/status/{id}   — poll run status
  POST /science/sequence/stop/{id}     — stop a running sequence
"""

from __future__ import annotations

import json
import logging
import os
import uuid
from typing import Any, Dict, List

from fastapi import APIRouter, Body, HTTPException

from services.ros_node import get_ros_node
from services import sequence_runner

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/science")

DATA_FILE = os.path.join(os.path.dirname(__file__), "..", "data", "science_sequences.json")

# ---------------------------------------------------------------------------
# Helpers — persistence
# ---------------------------------------------------------------------------

def _load_sequences() -> List[Dict]:
    try:
        if os.path.exists(DATA_FILE):
            with open(DATA_FILE, "r") as f:
                return json.load(f)
    except Exception as exc:
        logger.warning("Could not load sequences: %s", exc)
    return []


def _save_sequences(sequences: List[Dict]) -> None:
    try:
        os.makedirs(os.path.dirname(DATA_FILE), exist_ok=True)
        with open(DATA_FILE, "w") as f:
            json.dump(sequences, f, indent=2)
    except Exception as exc:
        logger.error("Could not save sequences: %s", exc)

# ---------------------------------------------------------------------------
# Saved sequence CRUD
# ---------------------------------------------------------------------------

@router.get("/sequences")
async def list_sequences() -> Dict:
    return {"sequences": _load_sequences()}


@router.post("/sequences")
async def save_sequence(body: Dict[str, Any] = Body(...)) -> Dict:
    sequences = _load_sequences()
    seq_id = body.get("id") or str(uuid.uuid4())
    body["id"] = seq_id

    # Upsert
    updated = False
    for i, s in enumerate(sequences):
        if s.get("id") == seq_id:
            sequences[i] = body
            updated = True
            break
    if not updated:
        sequences.append(body)

    _save_sequences(sequences)
    return {"status": "ok", "id": seq_id}


@router.delete("/sequences/{seq_id}")
async def delete_sequence(seq_id: str) -> Dict:
    sequences = [s for s in _load_sequences() if s.get("id") != seq_id]
    _save_sequences(sequences)
    return {"status": "ok"}

# ---------------------------------------------------------------------------
# Run management
# ---------------------------------------------------------------------------

@router.post("/sequence/run")
async def run_sequence(body: Dict[str, Any] = Body(...)) -> Dict:
    ros_node = get_ros_node()
    if not ros_node:
        raise HTTPException(status_code=503, detail="ROS node not initialized")

    steps = body.get("steps")
    if not steps or not isinstance(steps, list):
        raise HTTPException(status_code=400, detail="'steps' list is required")

    run_id = sequence_runner.start_sequence(steps, ros_node)
    return {"run_id": run_id}


@router.get("/sequence/status/{run_id}")
async def get_sequence_status(run_id: str) -> Dict:
    status = sequence_runner.get_run_status(run_id)
    if not status:
        raise HTTPException(status_code=404, detail="Run not found")
    return status


@router.post("/sequence/stop/{run_id}")
async def stop_sequence(run_id: str) -> Dict:
    stopped = sequence_runner.stop_run(run_id)
    return {"status": "stop_requested" if stopped else "not_running"}
