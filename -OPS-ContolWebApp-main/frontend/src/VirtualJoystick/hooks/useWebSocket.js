import { useEffect, useRef, useState, useCallback } from "react";
import { BACKEND_CONFIG, CONNECTION_STATUS, CONTROL_MODES } from "../Constants.js";

export const useWebSocket = (controlMode) => {
  const [connectionStatus, setConnectionStatus] = useState(CONNECTION_STATUS.DISCONNECTED);
  const [robotStatus, setRobotStatus] = useState(null);
  const websocketRef = useRef(null);
  const reconnectTimeoutRef = useRef(null);
  const isConnectingRef = useRef(false);
  const controlModeRef = useRef(controlMode);
  const lastJoystickPayloadRef = useRef(null);
  const lastJoystickReleaseSentRef = useRef(false);

  // Keep controlMode ref in sync
  useEffect(() => {
    controlModeRef.current = controlMode;
    if (controlMode === CONTROL_MODES.OFF) {
      lastJoystickPayloadRef.current = null;
      lastJoystickReleaseSentRef.current = false;
    }
  }, [controlMode]);

  // Single effect to manage WebSocket lifecycle — depends ONLY on controlMode
  useEffect(() => {
    if (controlMode === CONTROL_MODES.OFF) {
      // ── Close everything ──
      if (reconnectTimeoutRef.current) {
        clearTimeout(reconnectTimeoutRef.current);
        reconnectTimeoutRef.current = null;
      }
      if (websocketRef.current) {
        websocketRef.current.close(1000, "Manual close");
        websocketRef.current = null;
      }
      setConnectionStatus(CONNECTION_STATUS.DISCONNECTED);
      setRobotStatus(null);
      isConnectingRef.current = false;
      return;
    }

    // ── Open WebSocket ──
    const connect = () => {
      if (isConnectingRef.current) return;
      if (websocketRef.current && websocketRef.current.readyState === WebSocket.OPEN) return;

      isConnectingRef.current = true;
      setConnectionStatus(CONNECTION_STATUS.CONNECTING);

      try {
        const ws = new WebSocket(BACKEND_CONFIG.WS_URL);
        websocketRef.current = ws;

        ws.onopen = () => {
          console.log("WebSocket connected");
          setConnectionStatus(CONNECTION_STATUS.CONNECTED);
          isConnectingRef.current = false;
        };

        ws.onclose = (event) => {
          console.log("WebSocket closed:", event.code, event.reason);
          setConnectionStatus(CONNECTION_STATUS.DISCONNECTED);
          setRobotStatus(null);
          isConnectingRef.current = false;
          websocketRef.current = null;

          // Auto-reconnect only if still active (not OFF) and not a clean close
          if (controlModeRef.current !== CONTROL_MODES.OFF && !event.wasClean) {
            console.log("Attempting to reconnect in 3 seconds...");
            reconnectTimeoutRef.current = setTimeout(() => {
              connect();
            }, 3000);
          }
        };

        ws.onerror = (error) => {
          console.error("WebSocket error:", error);
          setConnectionStatus(CONNECTION_STATUS.ERROR);
          isConnectingRef.current = false;
        };

        ws.onmessage = (event) => {
          try {
            const message = JSON.parse(event.data);
            switch (message.type) {
              case "status":
                setRobotStatus(message.data);
                break;
              case "pong":
                break;
              default:
                console.log("Unknown message type:", message.type);
            }
          } catch (error) {
            console.error("Error parsing WebSocket message:", error);
          }
        };
      } catch (error) {
        console.error("Failed to create WebSocket:", error);
        setConnectionStatus(CONNECTION_STATUS.ERROR);
        isConnectingRef.current = false;
      }
    };

    connect();

    // Cleanup on controlMode change or unmount
    return () => {
      if (reconnectTimeoutRef.current) {
        clearTimeout(reconnectTimeoutRef.current);
        reconnectTimeoutRef.current = null;
      }
      if (websocketRef.current) {
        websocketRef.current.close(1000, "Mode change");
        websocketRef.current = null;
      }
      isConnectingRef.current = false;
    };
  }, [controlMode]);

  // Memoized send message function
  const sendMessage = useCallback((command) => {
    if (websocketRef.current?.readyState === WebSocket.OPEN) {
      try {
        websocketRef.current.send(JSON.stringify({
          ...command,
          timestamp: new Date().toISOString(),
        }));
        return true;
      } catch (error) {
        console.error("Failed to send message:", error);
        return false;
      }
    }
    console.warn("WebSocket not connected, cannot send message:", command);
    return false;
  }, []);

  // Memoized joystick functions
  const sendJoystickCommand = useCallback((x, y, speed) => {
    const round3 = (v) => Math.round(v * 1000) / 1000;
    const command = {
      type: "joystick",
      x: round3((-y * speed * 4) / 3),
      y: round3((-x * speed * 4) / 3),
    };

    const last = lastJoystickPayloadRef.current;
    if (last && last.x === command.x && last.y === command.y) {
      return true;
    }

    const sent = sendMessage(command);
    if (sent) {
      lastJoystickPayloadRef.current = { x: command.x, y: command.y };
      lastJoystickReleaseSentRef.current = false;
    }
    return sent;
  }, [sendMessage]);

  const sendJoystickRelease = useCallback(() => {
    if (lastJoystickReleaseSentRef.current) {
      return true;
    }

    const command = {
      type: "joystick_release",
    };

    const sent = sendMessage(command);
    if (sent) {
      lastJoystickPayloadRef.current = { x: 0, y: 0 };
      lastJoystickReleaseSentRef.current = true;
    }
    return sent;
  }, [sendMessage]);

  const activateJoystick = useCallback(async () => {
    try {
      // Send WebSocket command
      if (websocketRef.current?.readyState === WebSocket.OPEN) {
        sendMessage({ type: "joystick_activate" });
      }

      // Also call REST API as backup
      const response = await fetch(`${BACKEND_CONFIG.BACKEND_URL}/joystick/activate`, {
        method: "POST",
        headers: { 'Content-Type': 'application/json' },
      });

      if (response.ok) {
        lastJoystickPayloadRef.current = null;
        lastJoystickReleaseSentRef.current = false;
        console.log("Joystick activated successfully");
        return true;
      } else {
        console.error("Failed to activate joystick:", response.statusText);
        return false;
      }
    } catch (error) {
      console.error("Error activating joystick:", error);
      return false;
    }
  }, [sendMessage]);

  const deactivateJoystick = useCallback(async () => {
    try {
      // Send WebSocket command
      if (websocketRef.current?.readyState === WebSocket.OPEN) {
        sendMessage({ type: "joystick_deactivate" });
      }

      // Also call REST API as backup
      const response = await fetch(`${BACKEND_CONFIG.BACKEND_URL}/joystick/deactivate`, {
        method: "POST",
        headers: { 'Content-Type': 'application/json' },
      });

      if (response.ok) {
        lastJoystickPayloadRef.current = null;
        lastJoystickReleaseSentRef.current = false;
        console.log("Joystick deactivated successfully");
        return true;
      } else {
        console.error("Failed to deactivate joystick:", response.statusText);
        return false;
      }
    } catch (error) {
      console.error("Error deactivating joystick:", error);
      return false;
    }
  }, [sendMessage]);

  return {
    connectionStatus,
    robotStatus,
    sendJoystickCommand,
    sendJoystickRelease,
    activateJoystick,
    deactivateJoystick,
  };
};