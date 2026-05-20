"""
Bluetooth device management helper functions.

This module provides functionality for:
- Scanning for nearby Bluetooth devices
- Pairing with Bluetooth devices
- Trusting and connecting to devices
- Managing bluetoothctl subprocess interactions

All functions use the system's bluetoothctl command-line tool
to interact with the Bluetooth stack.
"""
from __future__ import annotations

import logging
import subprocess
import time
from typing import Dict, List

logger = logging.getLogger(__name__)


def scan_devices() -> List[Dict[str, str]]:
    """
    Scan for nearby Bluetooth devices.
    
    Starts a Bluetooth scan, waits for devices to be discovered,
    then returns a list of found devices with their MAC addresses and names.
    
    The scan process:
    1. Starts bluetoothctl scan
    2. Waits 2 seconds for devices to be discovered
    3. Queries the devices list
    4. Stops the scan
    
    Returns:
        List of dictionaries with 'mac' and 'name' keys for each device
        
    Raises:
        Exception: If bluetoothctl fails or timeout occurs
    """
    try:
        # Start bluetoothctl interactive process
        scan_proc = subprocess.Popen(
            ["bluetoothctl"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        assert scan_proc.stdin is not None  # for type checkers
        
        # Start scanning for devices
        scan_proc.stdin.write("scan on\n")
        scan_proc.stdin.flush()
        time.sleep(2)  # Wait for devices to be discovered
        
        # Get list of devices
        scan_proc.stdin.write("devices\n")
        scan_proc.stdin.flush()
        time.sleep(1)
        
        # Stop scanning and quit
        scan_proc.stdin.write("scan off\nquit\n")
        scan_proc.stdin.flush()
        out, _ = scan_proc.communicate(timeout=5)
        
        # Parse device list from output
        devices: List[Dict[str, str]] = []
        for line in out.splitlines():
            if line.strip().startswith("Device"):
                parts = line.strip().split(" ", 2)
                if len(parts) == 3:
                    _, mac, name = parts
                    devices.append({"mac": mac, "name": name})
        return devices
    except Exception as exc:
        logger.error("Bluetooth scan error: %s", exc)
        raise


def pair_device(mac: str) -> Dict[str, str]:
    """
    Pair, trust, and connect to a Bluetooth device.
    
    This function performs a complete Bluetooth device setup:
    1. Pairs with the device (initiates secure connection)
    2. Trusts the device (allows auto-reconnection)
    3. Attempts to connect (up to 3 retries with 2-second delays)
    
    Args:
        mac: MAC address of the Bluetooth device (format: XX:XX:XX:XX:XX:XX)
    
    Returns:
        Dictionary containing:
            - status: "paired_and_connected" or "paired_but_not_connected"
            - mac: The device MAC address
            - pair_result: Output from pair command
            - trust_result: Output from trust command
            - connect_outputs: List of outputs from connection attempts
    
    Raises:
        Exception: If any bluetoothctl command fails
    """
    try:
        # Step 1: Pair with device
        pair_cmd = f"echo 'pair {mac}\\nquit' | bluetoothctl"
        pair_result = subprocess.check_output(pair_cmd, shell=True, text=True)
        logger.info("PAIR OUTPUT:\n%s", pair_result)
        
        # Step 2: Trust device (allows automatic reconnection)
        trust_cmd = f"echo 'trust {mac}\\nquit' | bluetoothctl"
        trust_result = subprocess.check_output(trust_cmd, shell=True, text=True)
        logger.info("TRUST OUTPUT:\n%s", trust_result)
        
        # Step 3: Connect to device (with retries)
        connected = False
        connect_outputs: List[str] = []
        for attempt in range(3):
            connect_cmd = f"echo 'connect {mac}\\nquit' | bluetoothctl"
            connect_result = subprocess.check_output(connect_cmd, shell=True, text=True)
            connect_outputs.append(connect_result)
            logger.info("CONNECT OUTPUT (attempt %d):\n%s", attempt + 1, connect_result)
            
            # Check if connection was successful
            if "Connection successful" in connect_result or "Connection already exists" in connect_result:
                connected = True
                break
            time.sleep(2)  # Wait before retry
        
        # Determine final status
        status = "paired_and_connected" if connected else "paired_but_not_connected"
        return {
            "status": status,
            "mac": mac,
            "pair_result": pair_result,
            "trust_result": trust_result,
            "connect_outputs": connect_outputs,
        }
    except Exception as exc:
        logger.error("Bluetooth pair error: %s", exc)
        raise

