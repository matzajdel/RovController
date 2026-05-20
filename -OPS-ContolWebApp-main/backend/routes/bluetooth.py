"""Bluetooth endpoints."""
from __future__ import annotations

from fastapi import APIRouter

from services.bluetooth_manager import pair_device, scan_devices
from models import BluetoothPairRequest

router = APIRouter()


@router.get("/bluetooth/scan")
def bluetooth_scan() -> dict[str, object]:
    try:
        devices = scan_devices()
        return {"devices": devices}
    except Exception as exc:  # pragma: no cover - defensive logging
        return {"error": str(exc)}


@router.post("/bluetooth/pair")
def bluetooth_pair(req: BluetoothPairRequest) -> dict[str, object]:
    try:
        return pair_device(req.mac)
    except Exception as exc:  # pragma: no cover - defensive logging
        return {"error": str(exc)}


@router.get("/bluetooth/mobile")
def bluetooth_mobile_wip() -> dict[str, str]:
    return {"status": "WiP", "message": "Bluetooth mobile endpoint is Work in Progress (WiP)"}


@router.get("/bluetooth/mobile/wip-frontend")
def bluetooth_mobile_wip_frontend() -> dict[str, str]:
    return {"status": "WiP", "message": "Bluetooth mobile frontend is Work in Progress (WiP)"}
