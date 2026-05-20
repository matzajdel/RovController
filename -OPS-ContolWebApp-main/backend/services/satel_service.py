"""
Satel RS-232 Service
=====================

Dwa tryby pracy:

1. AFSK encode/decode  — czysto softwarowy modem AFSK (Bell 202, 1200 bps).
   Dane → sygnał audio PCM → port RS-232.
   Używany gdy radio jest podłączone przez linię dźwiękową.

2. Transparent serial   — Satel działa jako przezroczysty radiomodem.
   Dane → port RS-232 → Satel → radio → drugi Satel → port RS-232 → ROS.
   W tym trybie wysyłamy po prostu JSON-linie (np. cmd_vel, topic data).

Protokół JSON-over-serial (tryb transparent):
  Każda linia to jeden pakiet JSON zakończony '\\n':
    {"t":"cmd_vel","lx":0.5,"az":0.0}
    {"t":"topic","name":"/Serwa","data":[1,90]}
    {"t":"stop"}

Enkoder/dekoder AFSK:
  Używa korelacji DFT (iloczyn skalarny z sinusoidami referencyjnymi)
  dla niezawodnej detekcji tonów mark (1200 Hz) i space (2200 Hz).
"""

from __future__ import annotations

import io
import logging
import math
import struct
import threading
import json
from dataclasses import dataclass, field
from typing import List, Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# AFSK constants (Bell 202 / 1200-baud packet radio)
# ---------------------------------------------------------------------------
SAMPLE_RATE     = 8000      # Hz
BAUD_RATE       = 1200      # bps
SAMPLES_PER_BIT = SAMPLE_RATE / BAUD_RATE   # ≈ 6.6667

FREQ_MARK  = 1200.0   # Hz  → bit 1
FREQ_SPACE = 2200.0   # Hz  → bit 0

# Radio preamble / postamble: 0x7E flags (HDLC-style)
PREAMBLE_LEN  = 12   # 0x7E bytes before data
POSTAMBLE_LEN = 6    # 0x7E bytes after data


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _bytes_to_bits(data: bytes) -> List[int]:
    """Convert bytes to LSB-first list of bits."""
    bits: List[int] = []
    for byte in data:
        for i in range(8):
            bits.append((byte >> i) & 1)
    return bits


def _bits_to_bytes(bits: List[int]) -> bytes:
    """Convert LSB-first list of bits back to bytes."""
    out = bytearray()
    for i in range(0, len(bits), 8):
        chunk = bits[i:i + 8]
        if len(chunk) < 8:
            chunk += [0] * (8 - len(chunk))
        byte = 0
        for j, b in enumerate(chunk):
            byte |= (b & 1) << j
        out.append(byte)
    return bytes(out)


def _tone_energy(samples: list, freq: float) -> float:
    """
    Energy at *freq* — DFT correlation (Goertzel-style inner product).
    More accurate than zero-crossing; works even with as few as 4 samples.
    """
    sin_sum = 0.0
    cos_sum = 0.0
    N = len(samples)
    for i, s in enumerate(samples):
        angle = 2.0 * math.pi * freq * i / SAMPLE_RATE
        sin_sum += s * math.sin(angle)
        cos_sum += s * math.cos(angle)
    return sin_sum * sin_sum + cos_sum * cos_sum


# ---------------------------------------------------------------------------
# Encoding
# ---------------------------------------------------------------------------

def encode_afsk(data: bytes) -> bytes:
    """
    Encode *data* as AFSK audio (raw 16-bit signed PCM, 8000 Hz, little-endian).
    Uses continuous-phase FSK to avoid click artefacts between bits.
    """
    preamble  = bytes([0x7E] * PREAMBLE_LEN)
    postamble = bytes([0x7E] * POSTAMBLE_LEN)
    payload   = preamble + data + postamble
    bits      = _bytes_to_bits(payload)

    amplitude = 32767
    samples: List[int] = []
    phase = 0.0   # accumulated phase in radians

    for i, bit in enumerate(bits):
        # Exact integer sample boundaries avoids timing drift
        start = round(i       * SAMPLES_PER_BIT)
        end   = round((i + 1) * SAMPLES_PER_BIT)
        freq  = FREQ_MARK if bit == 1 else FREQ_SPACE
        for _ in range(end - start):
            samples.append(int(math.sin(phase) * amplitude))
            phase += 2.0 * math.pi * freq / SAMPLE_RATE

    pcm = struct.pack(f"<{len(samples)}h", *samples)
    logger.debug("AFSK encode: %d bytes → %d PCM samples (%d B)",
                 len(data), len(samples), len(pcm))
    return pcm


# ---------------------------------------------------------------------------
# Decoding
# ---------------------------------------------------------------------------

def decode_afsk(signal: bytes) -> bytes:
    """
    Decode raw 16-bit signed PCM → original bytes.

    Uses DFT correlation to compare energy at FREQ_MARK vs FREQ_SPACE
    for each bit window. Preamble/postamble 0x7E bytes are stripped.
    """
    if len(signal) < 2:
        return b""

    n_samples = len(signal) // 2
    samples   = list(struct.unpack(f"<{n_samples}h", signal[:n_samples * 2]))

    bits: List[int] = []
    n_bits = int(n_samples / SAMPLES_PER_BIT)

    for i in range(n_bits):
        start  = round(i       * SAMPLES_PER_BIT)
        end    = round((i + 1) * SAMPLES_PER_BIT)
        window = samples[start:end]
        if len(window) < 2:
            continue
        e_mark  = _tone_energy(window, FREQ_MARK)
        e_space = _tone_energy(window, FREQ_SPACE)
        bits.append(1 if e_mark >= e_space else 0)

    if not bits:
        return b""

    raw = _bits_to_bytes(bits)

    # Strip leading 0x7E preamble bytes
    start_idx = 0
    while start_idx < len(raw) and raw[start_idx] == 0x7E:
        start_idx += 1
    # Strip trailing 0x7E postamble bytes
    end_idx = len(raw)
    while end_idx > start_idx and raw[end_idx - 1] == 0x7E:
        end_idx -= 1

    result = raw[start_idx:end_idx]
    logger.debug("AFSK decode: %d PCM samples → %d bytes", n_samples, len(result))
    return result


# ---------------------------------------------------------------------------
# Serial Packet Protocol (Binary Frames)
# Format: $ [HEADER_2_BYTES] [DATA_N_BYTES] [CHECKSUM_1_BYTE] #
# ---------------------------------------------------------------------------

CMD_VEL_TYPE  = "cmd_vel"
TOPIC_TYPE    = "topic"
STOP_TYPE     = "stop"

def float_to_byte(val: float) -> int:
    """Map float [-1, 1] to byte [0, 254]"""
    clamped = max(-1.0, min(1.0, val))
    return int((clamped * 127.0) + 128.0)

def float_to_byte_100(val: float) -> int:
    """Map float [-100, 100] to byte [0, 254]"""
    clamped = max(-100.0, min(100.0, val))
    return int((clamped + 100.0) / 200.0 * 254.0)

def _build_frame(header: bytes, data: list[int]) -> bytes:
    """Build a complete binary frame with start $, checksum, and end #."""
    checksum = sum(data) % 256
    return b"$" + header + bytes(data) + bytes([checksum]) + b"#"

def build_cmd_vel_packet(linear_x: float, angular_z: float) -> bytes:
    """Header: DV. Data: x_byte, z_byte"""
    x_b = float_to_byte(linear_x)
    z_b = float_to_byte(angular_z)
    return _build_frame(b"DV", [x_b, z_b])

def build_cmd_vel_full_packet(lx: float, ly: float, lz: float, az: float) -> bytes:
    """Header: D4. Data: lx, ly, lz, az"""
    x_b = float_to_byte(lx)
    y_b = float_to_byte(ly)
    z_b = float_to_byte(lz)
    az_b = float_to_byte(az)
    return _build_frame(b"D4", [x_b, y_b, z_b, az_b])

def build_array_packet(data: list) -> bytes:
    """Header: MN. Data: val1..val6 (mapped to 0-254)"""
    vals = [float_to_byte_100(float(v)) for v in (data + [0]*6)[:6]]
    return _build_frame(b"MN", vals)

def build_arrow_packet(data: list) -> bytes:
    """Header: GS. Data: s1..s4 (0-255)"""
    vals = [max(0, min(255, int(v))) for v in (data + [0]*4)[:4]]
    return _build_frame(b"GS", vals)

def build_rgb_packet(r: float, g: float, b: float) -> bytes:
    """Header: RG. Data: r, g, b"""
    return _build_frame(b"RG", [max(0, min(255, int(r))), max(0, min(255, int(g))), max(0, min(255, int(b)))])

def build_science_led_packet(brightness: int) -> bytes:
    """Header: SL. Data: brightness"""
    return _build_frame(b"SL", [max(0, min(255, int(brightness)))])

def build_gps_packet(lon: float, lat: float) -> bytes:
    """GPS is not natively supported by the new receiver script, returning empty"""
    return b""

def build_led_packet(state: list) -> bytes:
    """Header: GL. Data: 1 byte bits (manual, autonomy, kill_switch)
    Incoming state: [mode, r, g, b]
    """
    mode = state[0] if len(state) > 0 else 0
    r = state[1] if len(state) > 1 else 0
    b = state[3] if len(state) > 3 else 0

    manual = 1 if b == 255 else 0
    autonomy = 1 if r == 255 else 0
    kill_switch = 1 if mode == 0 else 0

    byte_val = (manual << 0) | (autonomy << 1) | (kill_switch << 2)
    return _build_frame(b"GL", [byte_val])

def build_koszelnik_packet(drill: int, koszelnik: int, heater: int) -> bytes:
    """Header: GK. Data: 1 byte bits"""
    byte_val = ((drill & 1) << 0) | ((koszelnik & 1) << 1) | ((heater & 1) << 2)
    return _build_frame(b"GK", [byte_val])

def build_science_servo_packet(data: list) -> bytes:
    """Header: SS. Data: s1..s6"""
    vals = [max(0, min(255, int(v))) for v in (data + [0]*6)[:6]]
    return _build_frame(b"SS", vals)

def build_science_pump_packet(p1: int, p2: int) -> bytes:
    """Header: SP. Data: 1 byte bits"""
    byte_val = ((p1 & 1) << 0) | ((p2 & 1) << 1)
    return _build_frame(b"SP", [byte_val])

def build_topic_packet(topic: str, data: list) -> bytes:
    """Generic named-topic packet (Not supported in new binary protocol)."""
    return b""

def build_stop_packet() -> bytes:
    """Generate stop packet for cmd_vel (x=0, z=0)"""
    return build_cmd_vel_packet(0.0, 0.0)

def parse_packet(line: bytes) -> Optional[dict]:
    """Parse is not typically used on base station for outgoing. Stubbed."""
    return None



# ---------------------------------------------------------------------------
# Service class
# ---------------------------------------------------------------------------

@dataclass
class SatelService:
    """
    Manages RS-232 communication.

    Supports two encoding modes:
      - 'afsk'        : encode data as AFSK audio signal
      - 'transparent' : send raw JSON-line packets (Satel radiomodem)

    When *mock=True* no serial port is opened; all operations use
    in-memory BytesIO buffers (loopback).
    """

    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def _write_serial(
        self,
        raw: bytes,
        port: str,
        baud: int,
        mock: bool,
        extra: Optional[dict] = None,
    ) -> dict:
        """Open port, write *raw*, close. Mock mode skips the port."""
        base = {"status": "ok", "mock": mock, "port": port,
                "packet": raw.decode(errors="replace").strip(),
                **(extra or {})}
        if mock:
            logger.info("MOCK SEND %d bytes → %s", len(raw), port)
            return base

        try:
            import serial
        except ImportError:
            return {"status": "error", "detail": "pyserial not installed. Run: pip install pyserial"}

        try:
            with self._lock:
                with serial.Serial(port, baudrate=baud, timeout=2) as ser:
                    ser.write(raw)
            return {**base, "baud": baud, "bytes_written": len(raw)}
        except Exception as exc:
            logger.error("Serial write error: %s", exc)
            return {"status": "error", "detail": str(exc)}


    def loopback_afsk(self, message: str) -> dict:
        """Encode *message* as AFSK signal, immediately decode → return result."""
        raw    = message.encode("utf-8")
        signal = encode_afsk(raw)
        recovered = decode_afsk(signal)
        try:
            text = recovered.decode("utf-8")
        except UnicodeDecodeError:
            text = recovered.hex()
        ok = text == message
        logger.info("AFSK loopback: input=%r decoded=%r match=%s", message, text, ok)
        return {
            "mode":          "afsk",
            "input":         message,
            "encoded_bytes": len(signal),
            "decoded":       text,
            "match":         ok,
        }



    def loopback_transparent(self, message: str) -> dict:
        """Build a JSON packet, parse it back → verify roundtrip."""
        raw = build_cmd_vel_packet(0.5, 0.1)   # example numeric packet
        parsed = parse_packet(raw)
        text_pkt = (json.dumps({"t": "msg", "v": message}, separators=(",", ":")) + "\n").encode()
        parsed_msg = parse_packet(text_pkt)
        ok = parsed_msg is not None and parsed_msg.get("v") == message
        logger.info("Transparent loopback: input=%r match=%s", message, ok)
        return {
            "mode":    "transparent",
            "input":   message,
            "packet":  text_pkt.decode().strip(),
            "decoded": parsed_msg.get("v") if parsed_msg else None,
            "match":   ok,
        }

    # ---- Generic loopback --------------------------------------------------

    def loopback(self, message: str, mode: str = "afsk") -> dict:
        if mode == "transparent":
            return self.loopback_transparent(message)
        return self.loopback_afsk(message)

    # ---- Send --------------------------------------------------------------

    def send(
        self,
        message:  str,
        port:     str  = "/dev/ttyUSB0",
        baud:     int  = 9600,
        mock:     bool = False,
        mode:     str  = "transparent",
    ) -> dict:
        """Encode *message* and write to RS-232 (or mock buffer)."""
        if mode == "afsk":
            raw = encode_afsk(message.encode("utf-8"))
        else:
            raw = (json.dumps({"t": "msg", "v": message}, separators=(",", ":")) + "\n").encode()

        if mock:
            logger.info("MOCK SEND [%s]: %d bytes", mode, len(raw))
            return {"status": "ok", "mock": True, "port": port,
                    "mode": mode, "encoded_bytes": len(raw), "message_bytes": len(message)}

        try:
            import serial  # type: ignore
        except ImportError:
            return {"status": "error", "detail": "pyserial not installed"}

        try:
            with serial.Serial(port, baudrate=baud, timeout=5) as ser:
                ser.write(raw)
            return {"status": "ok", "mock": False, "port": port, "baud": baud,
                    "mode": mode, "encoded_bytes": len(raw), "message_bytes": len(message)}
        except Exception as exc:
            logger.error("Serial send error: %s", exc)
            return {"status": "error", "detail": str(exc)}

    # ---- Send cmd_vel ------------------------------------------------------

    def send_cmd_vel(
        self,
        linear_x: float,
        angular_z: float,
        port: str  = "/dev/ttyUSB0",
        baud: int  = 9600,
        mock: bool = False,
    ) -> dict:
        """Send a cmd_vel JSON-line packet over RS-232."""
        raw = build_cmd_vel_packet(linear_x, angular_z)
        return self._write_serial(raw, port, baud, mock,
                                  extra={"linear_x": linear_x, "angular_z": angular_z})

    # ---- Send single named topic -------------------------------------------

    def send_topic(
        self,
        topic_type: str,        # "array" | "arrow" | "rgb" | "gps" | "led" | "stop"
        payload:    dict,
        port: str  = "/dev/ttyUSB0",
        baud: int  = 9600,
        mock: bool = False,
    ) -> dict:
        """Build and send a single typed topic packet."""
        t = topic_type
        if t == "array":
            raw = build_array_packet(payload.get("data", []))
        elif t == "arrow":
            raw = build_arrow_packet(payload.get("data", [0, 0]))
        elif t == "rgb":
            raw = build_rgb_packet(float(payload.get("r", 0)), float(payload.get("g", 0)), float(payload.get("b", 0)))
        elif t == "gps":
            raw = build_gps_packet(float(payload.get("lon", 0.0)), float(payload.get("lat", 0.0)))
        elif t == "led":
            raw = build_led_packet(payload.get("state", [0, 0, 0, 0]))
        elif t == "koszelnik":
            raw = build_koszelnik_packet(payload.get("drill", 0), payload.get("koszelnik", 0), payload.get("heater", 0))
        elif t == "science_servo":
            raw = build_science_servo_packet(payload.get("data", []))
        elif t == "science_pump":
            raw = build_science_pump_packet(payload.get("p1", 0), payload.get("p2", 0))
        elif t == "science_led":
            raw = build_science_led_packet(payload.get("brightness", 0))
        elif t == "stop":
            raw = build_stop_packet()
        elif t == "cmd_vel":
            raw = build_cmd_vel_full_packet(
                float(payload.get("lx", 0.0)),
                float(payload.get("ly", 0.0)),
                float(payload.get("lz", 0.0)),
                float(payload.get("az", 0.0))
            )
        else:
            return {"status": "error", "detail": f"Unknown topic type: {t!r}"}

        return self._write_serial(raw, port, baud, mock,
                                  extra={"topic_type": t, "payload": payload})

    # ---- Send multiple topics in one call ----------------------------------

    def send_multi(
        self,
        packets:  list,         # [{"type": "cmd_vel", ...}, {"type": "rgb", ...}, ...]
        port: str  = "/dev/ttyUSB0",
        baud: int  = 9600,
        mock: bool = False,
    ) -> dict:
        """
        Send multiple topic packets back-to-back in a single serial write.
        *packets* is a list of dicts with a 'type' key and topic-specific fields.
        """
        raw_parts: list[bytes] = []
        for pkt in packets:
            t = pkt.get("type", "")
            
            if t == "cmd_vel":
                raw_parts.append(build_cmd_vel_full_packet(
                    float(pkt.get("lx", 0)),
                    float(pkt.get("ly", 0)),
                    float(pkt.get("lz", 0)),
                    float(pkt.get("az", 0))
                ))
            elif t == "array":
                raw_parts.append(build_array_packet(pkt.get("data", [])))
            elif t == "arrow":
                raw_parts.append(build_arrow_packet(pkt.get("data", [0, 0])))
            elif t == "rgb":
                raw_parts.append(build_rgb_packet(float(pkt.get("r", 0)), float(pkt.get("g", 0)), float(pkt.get("b", 0))))
            elif t == "gps":
                raw_parts.append(build_gps_packet(float(pkt.get("lon", 0)), float(pkt.get("lat", 0))))
            elif t == "led":
                raw_parts.append(build_led_packet(pkt.get("state", [0, 0, 0, 0])))
            elif t == "koszelnik":
                raw_parts.append(build_koszelnik_packet(pkt.get("drill", 0), pkt.get("koszelnik", 0), pkt.get("heater", 0)))
            elif t == "science_servo":
                raw_parts.append(build_science_servo_packet(pkt.get("data", [])))
            elif t == "science_pump":
                raw_parts.append(build_science_pump_packet(pkt.get("p1", 0), pkt.get("p2", 0)))
            elif t == "science_led":
                raw_parts.append(build_science_led_packet(pkt.get("brightness", 0)))
            elif t == "stop":
                raw_parts.append(build_stop_packet())

        combined = b"".join(raw_parts)
        return self._write_serial(combined, port, baud, mock,
                                  extra={"packet_count": len(raw_parts)})

    # ---- Receive -----------------------------------------------------------

    def receive(
        self,
        port:    str   = "/dev/ttyUSB0",
        baud:    int   = 9600,
        timeout: float = 5.0,
        mock:    bool  = False,
        mode:    str   = "transparent",
        mock_signal: Optional[bytes] = None,
    ) -> dict:
        """Read and decode data from RS-232."""
        if mock:
            signal = mock_signal or b""
            if mode == "afsk" and signal:
                decoded = decode_afsk(signal)
                try:
                    text = decoded.decode("utf-8")
                except UnicodeDecodeError:
                    text = decoded.hex()
                return {"status": "ok", "mock": True, "mode": "afsk", "decoded": text, "signal_bytes": len(signal)}
            return {"status": "ok", "mock": True, "mode": mode, "decoded": "", "signal_bytes": 0}

        try:
            import serial  # type: ignore
        except ImportError:
            return {"status": "error", "detail": "pyserial not installed"}

        try:
            with serial.Serial(port, baudrate=baud, timeout=timeout) as ser:
                if mode == "afsk":
                    signal = ser.read(65536)
                    decoded_raw = decode_afsk(signal)
                    try:
                        text = decoded_raw.decode("utf-8")
                    except UnicodeDecodeError:
                        text = decoded_raw.hex()
                    return {"status": "ok", "mock": False, "port": port, "mode": "afsk",
                            "signal_bytes": len(signal), "decoded": text}
                else:
                    line = ser.readline()
                    parsed = parse_packet(line)
                    return {"status": "ok", "mock": False, "port": port, "mode": "transparent",
                            "decoded": line.decode().strip(), "parsed": parsed}
        except Exception as exc:
            logger.error("Serial receive error: %s", exc)
            return {"status": "error", "detail": str(exc)}

    # ---- List ports --------------------------------------------------------

    @staticmethod
    def list_ports() -> List[str]:
        try:
            from serial.tools import list_ports  # type: ignore
            return [p.device for p in list_ports.comports()]
        except ImportError:
            import os
            candidates = ([f"/dev/ttyUSB{i}" for i in range(4)] +
                          [f"/dev/ttyACM{i}" for i in range(4)] +
                          [f"/dev/ttyS{i}"   for i in range(4)] +
                          ["COM1", "COM2", "COM3", "COM4"])
            return [c for c in candidates if os.path.exists(c)] or candidates[:4]


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------
_satel_service: Optional[SatelService] = None


def get_satel_service() -> SatelService:
    global _satel_service
    if _satel_service is None:
        _satel_service = SatelService()
        logger.info("SatelService initialised")
    return _satel_service
