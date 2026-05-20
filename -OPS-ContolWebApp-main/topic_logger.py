#!/usr/bin/env python3
"""
ROS2 Universal Topic Logger — standalone script
Run: python3 topic_logger.py [--output-dir ./logs] [--hz 5] [--max-mb 10]

Requirements: ROS2 sourced (rclpy available)
"""

import argparse
import csv
import importlib
import os
import sys
import threading
from collections import defaultdict
from datetime import datetime

import rclpy
from rclpy.node import Node

# ══════════════════════════════════════════════════════════════════════════════
#  CONFIGURATION — edit these values to change behaviour
# ══════════════════════════════════════════════════════════════════════════════

OUTPUT_DIR          = "./logs"      # folder where CSV files are saved
WRITE_HZ            = 2.0          # how often to write each topic [Hz]
MAX_FILE_MB         = 10.0         # rotate to a new file after this size [MB]
DISCOVERY_INTERVAL  = 3.0          # how often to scan for new topics [s]

TOPIC_BLACKLIST = {                 # topics that will never be logged
    "/rosout",
    "/parameter_events",
    "/rosout_agg",
}


# ── constants ─────────────────────────────────────────────────────────────────
DISCOVERY_INTERVAL_S = 3.0
TOPIC_BLACKLIST      = {"/rosout", "/parameter_events", "/rosout_agg"}


# ── helpers ───────────────────────────────────────────────────────────────────

def import_msg_type(type_str: str):
    """Dynamically load a ROS2 message class from its type string."""
    parts = type_str.split("/")
    package, msg_name = (parts[0], parts[2]) if len(parts) == 3 else (parts[0], parts[1])
    try:
        return getattr(importlib.import_module(f"{package}.msg"), msg_name)
    except Exception:
        return None


def flatten_msg(msg, prefix="") -> dict:
    """Recursively flatten a ROS2 message into {dotted.key: value} pairs."""
    result = {}
    if hasattr(msg, "get_fields_and_field_types"):
        for field in msg.get_fields_and_field_types():
            result.update(flatten_msg(getattr(msg, field), f"{prefix}{field}."))
    elif isinstance(msg, (list, tuple)):
        for i, item in enumerate(msg):
            result.update(flatten_msg(item, f"{prefix}{i}."))
    else:
        result[prefix.rstrip(".")] = msg
    return result


def safe_topic_name(topic: str) -> str:
    """Convert /some/topic/name → some__topic__name  (safe filename)."""
    return topic.lstrip("/").replace("/", "__")


# ── main node ─────────────────────────────────────────────────────────────────

class TopicLogger(Node):
    def __init__(self, output_dir: str, write_hz: float, max_mb: float):
        super().__init__("topic_logger")

        self._output_dir = output_dir
        self._write_hz   = write_hz
        self._max_bytes  = int(max_mb * 1024 * 1024)

        os.makedirs(self._output_dir, exist_ok=True)

        self._subs:          dict = {}
        self._latest:        dict = {}   # topic → (msg, ros_time) | None
        self._file_handles:  dict = {}
        self._writers:       dict = {}
        self._file_paths:    dict = {}
        self._header_done:   set  = set()
        self._lock           = defaultdict(threading.Lock)

        self.create_timer(DISCOVERY_INTERVAL_S, self._discover)
        self.create_timer(1.0 / self._write_hz, self._flush)

        self.get_logger().info(
            f"TopicLogger ready  |  dir={self._output_dir}  "
            f"rate={self._write_hz} Hz  max={max_mb} MB"
        )

    # ── discovery ─────────────────────────────────────────────────────────────

    def _discover(self):
        for name, types in self.get_topic_names_and_types():
            if name in TOPIC_BLACKLIST or name in self._subs or not types:
                continue
            msg_cls = import_msg_type(types[0])
            if msg_cls is None:
                self.get_logger().warn(f"[skip] {name}  (cannot import {types[0]})")
                continue
            self._latest[name] = None
            self._subs[name]   = self.create_subscription(
                msg_cls, name,
                lambda msg, n=name: self._cb(msg, n),
                10,
            )
            self.get_logger().info(f"[+] {name}  [{types[0]}]")

    # ── subscriber callback ───────────────────────────────────────────────────

    def _cb(self, msg, topic: str):
        self._latest[topic] = (msg, self.get_clock().now())

    # ── 5 Hz flush ────────────────────────────────────────────────────────────

    def _flush(self):
        for topic, payload in list(self._latest.items()):
            if payload is None:
                continue
            msg, ros_time = payload
            with self._lock[topic]:
                self._write(topic, msg, ros_time)

    def _write(self, topic: str, msg, ros_time):
        writer = self._get_writer(topic)
        if writer is None:
            return

        wall = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")
        ros_s = f"{ros_time.nanoseconds / 1e9:.9f}"

        try:
            flat = flatten_msg(msg)
        except Exception:
            flat = {"raw": str(msg)}

        # header (once per file)
        fpath = self._file_paths[topic]
        if fpath not in self._header_done:
            writer.writerow(["wall_timestamp", "ros_timestamp_s"] + list(flat.keys()))
            self._header_done.add(fpath)

        writer.writerow([wall, ros_s] + list(flat.values()))
        self._file_handles[topic].flush()

    # ── file management ───────────────────────────────────────────────────────

    def _get_writer(self, topic: str):
        # rotate if file hit size limit
        if topic in self._file_paths:
            try:
                if os.path.getsize(self._file_paths[topic]) >= self._max_bytes:
                    self._close(topic)
                    self.get_logger().info(f"[rotate] {topic}")
            except OSError:
                pass

        if topic not in self._file_handles:
            self._open(topic)

        return self._writers.get(topic)

    def _open(self, topic: str):
        ts       = datetime.now().strftime("%d_%m_%Y_%H_%M_%S")
        filename = f"{safe_topic_name(topic)}_{ts}.csv"
        fpath    = os.path.join(self._output_dir, filename)
        fh       = open(fpath, "w", newline="", encoding="utf-8")
        self._file_handles[topic] = fh
        self._writers[topic]      = csv.writer(fh)
        self._file_paths[topic]   = fpath
        self.get_logger().info(f"[file] {fpath}")

    def _close(self, topic: str):
        try:
            self._file_handles.pop(topic).close()
        except Exception:
            pass
        self._writers.pop(topic, None)

    def destroy_node(self):
        for topic in list(self._file_handles):
            self._close(topic)
        self.get_logger().info("[shutdown] all files closed.")
        super().destroy_node()


# ── CLI entry point ───────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Log every ROS2 topic to CSV at a fixed rate."
    )
    parser.add_argument("--output-dir", default="./topic_logs",
                        help="Folder where CSV files are saved  (default: ./topic_logs)")
    parser.add_argument("--hz",         type=float, default=5.0,
                        help="Write rate in Hz                  (default: 5.0)")
    parser.add_argument("--max-mb",     type=float, default=10.0,
                        help="Max CSV file size in MB           (default: 10.0)")
    # allow ROS2 args to be passed after --ros-args without confusing argparse
    args, _ = parser.parse_known_args()

    rclpy.init()
    node = TopicLogger(
        output_dir=args.output_dir,
        write_hz=args.hz,
        max_mb=args.max_mb,
    )
    print(f"\n  Ctrl+C to stop.  Logs → {os.path.abspath(args.output_dir)}\n")
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
