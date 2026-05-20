/**
 * useRosBridge — singleton WebSocket connection to rosbridge_websocket
 * =====================================================================
 *
 * Provides a `publish(topic, msgType, msg)` helper that sends
 * geometry_msgs/Twist (or any other message) directly to ROS via
 * the rosbridge protocol — no backend HTTP needed.
 *
 * Features:
 *  • Singleton socket shared across all hook consumers
 *  • Auto-reconnect every 3 s on disconnect / error
 *  • op:advertise wysyłane automatycznie przed pierwszym publish —
 *    dzięki temu topic pojawia się w `ros2 topic list` i `ros2 topic echo`
 *
 * Usage:
 *   const { publish, connected } = useRosBridge();
 *   publish("/cmd_vel", "geometry_msgs/Twist", { linear: {x:1,y:0,z:0}, angular: {x:0,y:0,z:0} });
 */

import { useEffect, useRef, useState, useCallback } from "react";

// ── Singleton state (shared across all consumers) ──────────────────────────

let _ws = null;
let _reconnectTimer = null;
let _rosBridgeUrl = null;
const _listeners = new Set(); // (connected: boolean) => void

// Keeps track of which topics have been advertised on the current connection.
// Cleared on disconnect so that re-advertisement happens after every reconnect.
const _advertisedTopics = new Set();

const RECONNECT_DELAY = 3000;

function notifyListeners(connected) {
    _listeners.forEach((fn) => fn(connected));
}

/**
 * Send op:advertise so the topic appears in `ros2 topic list` and
 * can be echoed with `ros2 topic echo`.
 * Called automatically by publish() the first time a topic is used,
 * and again after every reconnect.
 */
function advertise(topic, msgType) {
    if (!_ws || _ws.readyState !== WebSocket.OPEN) return;
    if (_advertisedTopics.has(topic)) return;
    _advertisedTopics.add(topic);
    try {
        _ws.send(JSON.stringify({
            op: "advertise",
            topic,
            type: msgType,
        }));
        console.log("[RosBridge] Advertised", topic, "as", msgType);
    } catch (err) {
        console.warn("[RosBridge] advertise error:", err);
    }
}

function connect(url) {
    if (_ws && (_ws.readyState === WebSocket.CONNECTING || _ws.readyState === WebSocket.OPEN)) return;

    console.log("[RosBridge] Connecting to", url);
    _ws = new WebSocket(url);

    _ws.onopen = () => {
        console.log("[RosBridge] Connected");
        if (_reconnectTimer) { clearTimeout(_reconnectTimer); _reconnectTimer = null; }
        // Clear so all topics get re-advertised on this fresh connection
        _advertisedTopics.clear();
        notifyListeners(true);
    };

    _ws.onclose = () => {
        console.warn("[RosBridge] Disconnected — reconnecting in", RECONNECT_DELAY, "ms");
        _advertisedTopics.clear();
        notifyListeners(false);
        scheduleReconnect(url);
    };

    _ws.onerror = (e) => {
        console.error("[RosBridge] WebSocket error", e);
        // onclose will be called automatically after onerror
    };
}

function scheduleReconnect(url) {
    if (_reconnectTimer) return;
    _reconnectTimer = setTimeout(() => {
        _reconnectTimer = null;
        connect(url);
    }, RECONNECT_DELAY);
}

// ── Hook ───────────────────────────────────────────────────────────────────

export const useRosBridge = (url) => {
    const [connected, setConnected] = useState(false);
    const urlRef = useRef(url);

    useEffect(() => {
        urlRef.current = url;

        // Register listener
        const handleChange = (state) => setConnected(state);
        _listeners.add(handleChange);

        // Start singleton connection if needed
        if (!_ws || _ws.readyState === WebSocket.CLOSED || _ws.readyState === WebSocket.CLOSING) {
            _rosBridgeUrl = url;
            connect(url);
        } else {
            // Already connected — reflect current state immediately
            setConnected(_ws.readyState === WebSocket.OPEN);
        }

        return () => {
            _listeners.delete(handleChange);
        };
    }, [url]);

    /**
     * Publish a message to a ROS topic via rosbridge protocol.
     * Automatically sends op:advertise the first time a topic is used
     * so that `ros2 topic list` and `ros2 topic echo` work immediately.
     *
     * @param {string} topic    – ROS topic name, e.g. "/cmd_vel"
     * @param {string} msgType  – ROS message type, e.g. "geometry_msgs/Twist"
     * @param {object} msg      – Message payload object
     */
    const publish = useCallback((topic, msgType, msg) => {
        if (!_ws || _ws.readyState !== WebSocket.OPEN) {
            // Silently drop — robot will get stop from watchdog / no-movement
            return;
        }

        // Advertise first (no-op if already done for this connection)
        advertise(topic, msgType);

        const packet = JSON.stringify({
            op: "publish",
            topic,
            type: msgType,
            msg,
        });
        try {
            _ws.send(packet);
        } catch (err) {
            console.warn("[RosBridge] send error:", err);
        }
    }, []);

    return { publish, connected };
};
