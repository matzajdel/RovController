#!/usr/bin/env python3
"""
rover_satel_bridge.py — Satel RS-232 Radio Bridge (strona łazika)
==================================================================

Uruchom na komputerze ŁAZIKA (z source'd ROS2):

    python3 rover_satel_bridge.py [--port /dev/ttyUSB0] [--baud 9600] [--watchdog 2.0]

Działanie:
  • Otwiera port RS-232 podłączony do Satel radiomodemu
  • Czyta JSON-linie przesłane ze stacji bazowej
  • Publikuje je na odpowiednie topicki ROS2

Obsługiwane pakiety (JSON-linie):
  {"t":"cmd_vel","lx":0.5,"az":-0.25}        → /cmd_vel          (Twist)
  {"t":"array","data":[0,100,0,0,0,0]}        → /array_topic      (Float64MultiArray)
  {"t":"arrow","data":[1,90]}                  → /arrow_keys       (Int32MultiArray)
  {"t":"rgb","r":255,"g":0,"b":0}             → /rgb              (Float32MultiArray)
  {"t":"gps","lon":21.01,"lat":52.23}         → /gps_waypoint     (Float64MultiArray)
  {"t":"led","state":[1,0,0]}                 → /ESP32_GIZ/led_state_topic (Int32MultiArray)
  {"t":"stop"}                                 → /cmd_vel zero Twist

Watchdog:
  Jeśli brak pakietu przez <watchdog> sekund → auto STOP na /cmd_vel.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import threading
import time

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [SATEL] %(levelname)s %(message)s",
)
logger = logging.getLogger("satel_bridge")


# ---------------------------------------------------------------------------
# ROS 2 guard — import only if available
# ---------------------------------------------------------------------------
try:
    import rclpy
    from rclpy.node import Node
    from geometry_msgs.msg import Twist, Vector3
    from std_msgs.msg import Float64MultiArray, Float32MultiArray, Int32MultiArray, UInt8MultiArray
    import std_msgs.msg as std_msgs
    ROS_AVAILABLE = True
except ImportError:
    ROS_AVAILABLE = False
    logger.warning("rclpy not found — running in DRY-RUN mode (packets parsed but not published)")


# ---------------------------------------------------------------------------
# Bridge Node
# ---------------------------------------------------------------------------

class SatelBridgeNode:
    """
    Wraps a ROS2 node (or a dry-run stub) and publishes incoming
    serial packets to the appropriate ROS2 topics.
    """

    def __init__(self, watchdog_sec: float = 2.0):
        self.watchdog_sec    = watchdog_sec
        self._last_packet_ts = time.time()
        self._stop_sent      = False
        self._running        = True

        if ROS_AVAILABLE:
            rclpy.init()
            self._node = _ROS2PublisherNode()
            self._spin_thread = threading.Thread(
                target=rclpy.spin, args=(self._node,), daemon=True
            )
            self._spin_thread.start()
        else:
            self._node = _DryRunNode()

        # Start watchdog thread
        self._watchdog_thread = threading.Thread(target=self._watchdog_loop, daemon=True)
        self._watchdog_thread.start()

        logger.info(
            "SatelBridgeNode ready (watchdog=%.1fs, ros=%s)", watchdog_sec, ROS_AVAILABLE
        )

    # ---- Dispatch ---------------------------------------------------------

    def handle_packet(self, raw: bytes) -> None:
        """Parse one JSON-line and publish to ROS2."""
        try:
            pkt = json.loads(raw.decode("utf-8").strip())
        except Exception:
            logger.warning("Bad packet (not JSON): %r", raw[:80])
            return

        t = pkt.get("t")
        self._last_packet_ts = time.time()
        self._stop_sent = False

        if t == "cmd_vel":
            lx = float(pkt.get("lx", 0.0))
            ly = float(pkt.get("ly", 0.0))
            lz = float(pkt.get("lz", 0.0))
            az = float(pkt.get("az", 0.0))
            self._node.pub_cmd_vel(lx, ly, lz, az)
            logger.debug("cmd_vel lx=%.3f ly=%.3f lz=%.3f az=%.3f", lx, ly, lz, az)

        elif t == "stop":
            self._node.pub_cmd_vel(0.0, 0.0, 0.0, 0.0)
            logger.info("STOP received")

        elif t == "array":
            data = pkt.get("data", [])
            self._node.pub_array(data)
            logger.debug("array %s", data)

        elif t == "arrow":
            data = pkt.get("data", [0, 0])
            self._node.pub_arrow(data)
            logger.debug("arrow %s", data)

        elif t == "rgb":
            r = float(pkt.get("r", 0))
            g = float(pkt.get("g", 0))
            b = float(pkt.get("b", 0))
            self._node.pub_rgb(r, g, b)
            logger.debug("rgb r=%d g=%d b=%d", r, g, b)

        elif t == "gps":
            lon = float(pkt.get("lon", 0.0))
            lat = float(pkt.get("lat", 0.0))
            self._node.pub_gps(lon, lat)
            logger.debug("gps lon=%.6f lat=%.6f", lon, lat)

        elif t == "led":
            state = pkt.get("state", [0, 0, 0])
            self._node.pub_led(state)
            logger.debug("led %s", state)
            
        elif t == "array_idx":
            idx = int(pkt.get("idx", 1))
            val = float(pkt.get("val", 0.0))
            self._node.pub_array_idx(idx, val)
            logger.debug("array_idx %d=%f", idx, val)
            
        elif t == "custom":
            topic = pkt.get("topic")
            msg_type = pkt.get("msg")
            data = pkt.get("data", [])
            self._node.pub_custom(topic, msg_type, data)
            logger.debug("custom %s %s %s", topic, msg_type, data)

        else:
            logger.warning("Unknown packet type: %r", t)

    # ---- Watchdog ---------------------------------------------------------

    def _watchdog_loop(self) -> None:
        """Auto-stop if no packet received for watchdog_sec seconds."""
        while self._running:
            time.sleep(0.5)
            age = time.time() - self._last_packet_ts
            if age > self.watchdog_sec and not self._stop_sent:
                logger.warning(
                    "Watchdog: no packet for %.1fs — sending STOP", age
                )
                self._node.pub_cmd_vel(0.0, 0.0, 0.0, 0.0)
                self._stop_sent = True

    def shutdown(self) -> None:
        self._running = False
        self._node.pub_cmd_vel(0.0, 0.0, 0.0, 0.0)
        if ROS_AVAILABLE:
            self._node.destroy_node()
            rclpy.shutdown()
        logger.info("SatelBridgeNode shut down")


# ---------------------------------------------------------------------------
# ROS2 publisher node
# ---------------------------------------------------------------------------

class _ROS2PublisherNode(Node):  # type: ignore[misc]
    def __init__(self) -> None:
        super().__init__("satel_bridge")
        self._cmd_vel  = self.create_publisher(Twist,              "/cmd_vel",                       10)
        self._array    = self.create_publisher(Float64MultiArray,   "/array_topic",                  10)
        self._arrow    = self.create_publisher(Int32MultiArray,     "/arrow_keys",                   10)
        self._rgb      = self.create_publisher(Float32MultiArray,   "/rgb",                          10)
        self._gps      = self.create_publisher(Float64MultiArray,   "/gps_waypoint",                 10)
        self._led      = self.create_publisher(Int32MultiArray,     "/ESP32_GIZ/led_state_topic",    10)
        self._custom_pubs = {}
        
        # State for array manipulator caching
        self._array_state = [0.0, 0.0, 0.0, 0.0, 0.0, 0.0]
        
        logger.info("ROS2 publishers created on all topics")

    def pub_cmd_vel(self, lx: float, ly: float, lz: float, az: float) -> None:
        msg = Twist()
        msg.linear  = Vector3(x=lx,  y=ly,  z=lz)
        msg.angular = Vector3(x=0.0, y=0.0, z=az)
        self._cmd_vel.publish(msg)

    def pub_array(self, data: list) -> None:
        msg = Float64MultiArray()
        msg.data = [float(v) for v in data]
        for i, v in enumerate(msg.data):
            if i < len(self._array_state):
                self._array_state[i] = v
        self._array.publish(msg)

    def pub_array_idx(self, idx: int, val: float) -> None:
        if 1 <= idx <= 6:
            self._array_state[idx - 1] = float(val)
            msg = Float64MultiArray()
            msg.data = list(self._array_state)
            self._array.publish(msg)

    def pub_arrow(self, data: list) -> None:
        msg = Int32MultiArray()
        msg.data = [int(v) for v in data]
        self._arrow.publish(msg)

    def pub_rgb(self, r: float, g: float, b: float) -> None:
        msg = Float32MultiArray()
        msg.data = [r, g, b]
        self._rgb.publish(msg)

    def pub_gps(self, lon: float, lat: float) -> None:
        msg = Float64MultiArray()
        msg.data = [lon, lat]
        self._gps.publish(msg)

    def pub_led(self, state: list) -> None:
        msg = Int32MultiArray()
        msg.data = [int(v) for v in state]
        self._led.publish(msg)

    def pub_custom(self, topic: str, msg_type_str: str, data: list) -> None:
        if topic not in self._custom_pubs:
            msg_class = getattr(std_msgs, msg_type_str, None)
            if not msg_class:
                logger.warning("Unknown message type: %s", msg_type_str)
                return
            self._custom_pubs[topic] = self.create_publisher(msg_class, topic, 10)
            
        pub = self._custom_pubs[topic]
        msg = pub.msg_type()
        
        if "Int32MultiArray" in msg_type_str:
            msg.data = [int(v) for v in data]
        elif "UInt8MultiArray" in msg_type_str:
            msg.data = [int(v) for v in data]
        elif "Float" in msg_type_str:
            msg.data = [float(v) for v in data]
            
        pub.publish(msg)

class _DryRunNode:
    def pub_cmd_vel(self, lx, ly, lz, az): logger.info("[DRY] cmd_vel lx=%.3f ly=%.3f lz=%.3f az=%.3f", lx, ly, lz, az)
    def pub_array(self, data):         logger.info("[DRY] array %s", data)
    def pub_array_idx(self, idx, val): logger.info("[DRY] array_idx %d=%f", idx, val)
    def pub_arrow(self, data):         logger.info("[DRY] arrow %s", data)
    def pub_rgb(self, r, g, b):       logger.info("[DRY] rgb %d %d %d", r, g, b)
    def pub_gps(self, lon, lat):      logger.info("[DRY] gps %.6f %.6f", lon, lat)
    def pub_led(self, state):         logger.info("[DRY] led %s", state)
    def pub_custom(self, topic, mtype, data): logger.info("[DRY] custom %s %s %s", topic, mtype, data)
    def destroy_node(self): pass


# ---------------------------------------------------------------------------
# Serial reader
# ---------------------------------------------------------------------------

def read_serial_loop(port: str, baud: int, bridge: SatelBridgeNode) -> None:
    """Open RS-232 port and feed lines to bridge. Auto-reconnects on error."""
    try:
        import serial  # type: ignore
    except ImportError:
        logger.error("pyserial not installed. Run: pip install pyserial")
        sys.exit(1)

    buffer = b""
    ser = None

    while True:
        try:
            if ser is None or not ser.is_open:
                logger.info("Opening serial port %s @ %d baud…", port, baud)
                ser = serial.Serial(port, baudrate=baud, timeout=1.0)
                logger.info("Serial port open")

            chunk = ser.read(256)
            if not chunk:
                continue

            buffer += chunk
            while b"\n" in buffer:
                line, buffer = buffer.split(b"\n", 1)
                line = line.strip()
                if line:
                    bridge.handle_packet(line)

        except Exception as exc:
            logger.error("Serial error: %s — retrying in 3s…", exc)
            if ser:
                try:
                    ser.close()
                except Exception:
                    pass
                ser = None
            time.sleep(3.0)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="Satel RS-232 → ROS2 bridge (rover side)")
    parser.add_argument("--port",     default="/dev/ttyUSB0", help="Serial port device")
    parser.add_argument("--baud",     default=9600,  type=int,   help="Baud rate")
    parser.add_argument("--watchdog", default=2.0,   type=float, help="Watchdog timeout (s)")
    parser.add_argument("--dry-run",  action="store_true",        help="Parse only, do not publish to ROS")
    args = parser.parse_args()

    if args.dry_run:
        global ROS_AVAILABLE
        ROS_AVAILABLE = False  # noqa: F841

    logger.info("Satel Bridge starting — port=%s baud=%d watchdog=%.1fs",
                args.port, args.baud, args.watchdog)

    bridge = SatelBridgeNode(watchdog_sec=args.watchdog)

    try:
        read_serial_loop(args.port, args.baud, bridge)
    except KeyboardInterrupt:
        logger.info("Interrupted by user")
    finally:
        bridge.shutdown()


if __name__ == "__main__":
    main()
