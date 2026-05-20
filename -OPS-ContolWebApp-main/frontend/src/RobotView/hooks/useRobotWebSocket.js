import { useState, useEffect, useCallback, useRef } from 'react';

/**
 * WebSocket hook for robot state streaming
 * Connects to backend /ws/robot endpoint
 */
export function useRobotWebSocket(url) {
  const [connected, setConnected] = useState(false);
  const [jointState, setJointState] = useState(null);
  const wsRef = useRef(null);
  const reconnectTimeoutRef = useRef(null);

  // Connect to WebSocket
  useEffect(() => {
    let ws = null;

    const connect = () => {
      try {
        ws = new WebSocket(url);
        wsRef.current = ws;

        ws.onopen = () => {
          console.log('Robot WebSocket connected');
          setConnected(true);
          
          // Request initial state
          ws.send(JSON.stringify({ type: 'request_state' }));
        };

        ws.onmessage = (event) => {
          try {
            const data = JSON.parse(event.data);
            
            if (data.type === 'robot_state' || data.type === 'joint_update') {
              setJointState(data);
            }
          } catch (error) {
            console.error('Failed to parse WebSocket message:', error);
          }
        };

        ws.onerror = (error) => {
          console.error('Robot WebSocket error:', error);
        };

        ws.onclose = () => {
          console.log('Robot WebSocket disconnected');
          setConnected(false);
          wsRef.current = null;

          // Attempt reconnection after 3 seconds
          reconnectTimeoutRef.current = setTimeout(() => {
            console.log('Attempting to reconnect...');
            connect();
          }, 3000);
        };
      } catch (error) {
        console.error('Failed to create WebSocket:', error);
        setConnected(false);
      }
    };

    connect();

    // Cleanup
    return () => {
      if (reconnectTimeoutRef.current) {
        clearTimeout(reconnectTimeoutRef.current);
      }
      if (ws && ws.readyState === WebSocket.OPEN) {
        ws.close();
      }
    };
  }, [url]);

  // Send joint command
  const sendJointCommand = useCallback(async (command) => {
    try {
      const response = await fetch('http://localhost:2137/robot/set_joints', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(command),
      });

      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }

      return await response.json();
    } catch (error) {
      console.error('Failed to send joint command:', error);
      return null;
    }
  }, []);

  // Request current state
  const requestState = useCallback(() => {
    if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({ type: 'request_state' }));
    }
  }, []);

  // Send ping
  const sendPing = useCallback(() => {
    if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({ type: 'ping' }));
    }
  }, []);

  // Periodic ping to keep connection alive
  useEffect(() => {
    const interval = setInterval(() => {
      if (connected) {
        sendPing();
      }
    }, 30000); // Ping every 30 seconds

    return () => clearInterval(interval);
  }, [connected, sendPing]);

  return {
    connected,
    jointState,
    sendJointCommand,
    requestState,
    sendPing,
  };
}
