"""
Satel RS-232 — FastAPI Router (updated)
========================================

Endpointy:
  GET  /satel/status          — status serwisu, konfiguracja AFSK
  GET  /satel/ports           — lista portów szeregowych
  POST /satel/loopback        — test encode→decode (AFSK lub transparent)
  POST /satel/send            — wyślij wiadomość przez RS-232
  POST /satel/send_cmd_vel    — wyślij cmd_vel jako JSON-packet przez RS-232
  POST /satel/receive         — odbierz i zdekoduj z RS-232
"""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel, Field

from services.satel_service import get_satel_service

router = APIRouter(prefix="/satel")


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------

class LoopbackRequest(BaseModel):
    message: str  = Field(..., example="Hello Satel!")
    mode:    str  = Field("afsk", description="'afsk' | 'transparent'")


class SendRequest(BaseModel):
    message: str  = Field(..., example="Hello Satel!")
    port:    str  = Field("/dev/ttyUSB0")
    baud:    int  = Field(9600)
    mock:    bool = Field(True)
    mode:    str  = Field("transparent", description="'transparent' | 'afsk'")


class CmdVelRequest(BaseModel):
    linear_x:  float = Field(..., example=0.5)
    angular_z: float = Field(..., example=0.0)
    port:      str   = Field("/dev/ttyUSB0")
    baud:      int   = Field(9600)
    mock:      bool  = Field(True)


class SendTopicRequest(BaseModel):
    topic_type: str  = Field(..., example="rgb",
                             description="cmd_vel | array | arrow | rgb | gps | led | stop")
    payload:    dict = Field(default_factory=dict,
                             example={"r": 255, "g": 0, "b": 0})
    port:       str  = Field("/dev/ttyUSB0")
    baud:       int  = Field(9600)
    mock:       bool = Field(True)


class SendMultiRequest(BaseModel):
    packets: list = Field(...,
                          example=[
                              {"type": "cmd_vel", "lx": 0.5, "az": 0.0},
                              {"type": "rgb",     "r": 0,    "g": 255, "b": 0},
                          ])
    port:    str  = Field("/dev/ttyUSB0")
    baud:    int  = Field(9600)
    mock:    bool = Field(True)



class ReceiveRequest(BaseModel):
    port:    str   = Field("/dev/ttyUSB0")
    baud:    int   = Field(9600)
    timeout: float = Field(5.0)
    mock:    bool  = Field(True)
    mode:    str   = Field("transparent")


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("/status", summary="Status serwisu Satel")
async def satel_status() -> dict:
    svc   = get_satel_service()
    ports = svc.list_ports()
    return {
        "status":  "ok",
        "service": "SatelService",
        "modes":   ["transparent", "afsk"],
        "protocol": {
            "transparent": "JSON-lines over RS-232 (Satel radiomodem passthrough)",
            "afsk":        "AFSK Bell 202 1200 bps audio-over-serial",
        },
        "afsk": {
            "sample_rate_hz": 8000,
            "baud_rate":      1200,
            "freq_mark_hz":   1200,
            "freq_space_hz":  2200,
        },
        "available_ports": ports,
    }


@router.get("/ports", summary="Lista portów szeregowych")
async def satel_ports() -> dict:
    svc = get_satel_service()
    return {"ports": svc.list_ports()}


@router.post("/loopback", summary="Test loopback bez sprzętu")
async def satel_loopback(req: LoopbackRequest) -> dict:
    svc = get_satel_service()
    return svc.loopback(req.message, mode=req.mode)


@router.post("/send", summary="Wyślij wiadomość przez RS-232")
async def satel_send(req: SendRequest) -> dict:
    svc = get_satel_service()
    return svc.send(
        message=req.message,
        port=req.port,
        baud=req.baud,
        mock=req.mock,
        mode=req.mode,
    )


@router.post("/send_cmd_vel", summary="Wyślij cmd_vel przez RS-232 (Satel)")
async def satel_send_cmd_vel(req: CmdVelRequest) -> dict:
    """
    Wysyła polecenie ruchu robota przez port szeregowy podłączony do Satel radiomodemu.
    Pakiet: {\"t\":\"cmd_vel\",\"lx\":<linear_x>,\"az\":<angular_z>}\\n
    """
    svc = get_satel_service()
    return svc.send_cmd_vel(
        linear_x=req.linear_x,
        angular_z=req.angular_z,
        port=req.port,
        baud=req.baud,
        mock=req.mock,
    )


@router.post("/receive", summary="Odbierz z RS-232")
async def satel_receive(req: ReceiveRequest) -> dict:
    svc = get_satel_service()
    return svc.receive(
        port=req.port,
        baud=req.baud,
        timeout=req.timeout,
        mock=req.mock,
        mode=req.mode,
    )


@router.post("/send_topic", summary="Wyślij dowolny topic przez RS-232")
async def satel_send_topic(req: SendTopicRequest) -> dict:
    """
    Wysyła pakiet wybranego topicu przez RS-232.
    topic_type: cmd_vel | array | arrow | rgb | gps | led | stop
    """
    svc = get_satel_service()
    return svc.send_topic(
        topic_type=req.topic_type,
        payload=req.payload,
        port=req.port,
        baud=req.baud,
        mock=req.mock,
    )


@router.post("/send_multi", summary="Wyślij wiele topicków naraz przez RS-232")
async def satel_send_multi(req: SendMultiRequest) -> dict:
    """
    Wysyła listę pakietów w jednym write() do RS-232.
    Każdy element packets: {"type": "cmd_vel"|"array"|"rgb"|..., ...pola...}
    """
    svc = get_satel_service()
    return svc.send_multi(
        packets=req.packets,
        port=req.port,
        baud=req.baud,
        mock=req.mock,
    )
