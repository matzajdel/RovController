import { useState, useEffect, useRef, useCallback } from 'react';

/**
 * Custom hook for managing vision camera WebSocket stream
 * Connects to backend WebSocket and handles frame reception
 */
export const useVisionStream = (cameraId, settings, isStreaming) => {
  const [currentFrame, setCurrentFrame] = useState(null);
  const [streamMetrics, setStreamMetrics] = useState({
    bandwidth_mbps: 0,
    latency_ms: 0,
    actual_fps: 0
  });
  const [isConnected, setIsConnected] = useState(false);
  const [error, setError] = useState(null);

  const wsRef = useRef(null);
  const reconnectTimeoutRef = useRef(null);
  const frameCountRef = useRef(0);

  const connect = useCallback(() => {
    if (!cameraId || !isStreaming) return;

    try {
      // Close existing connection
      if (wsRef.current) {
        wsRef.current.close();
      }

      // Create WebSocket connection to backend
      const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
      const encodedId = encodeURIComponent(cameraId);
      const wsUrl = `${protocol}//${window.location.hostname}:2137/vision/stream/${encodedId}`;

      console.log(`Connecting to vision stream: ${wsUrl}`);
      const ws = new WebSocket(wsUrl);

      ws.onopen = () => {
        console.log(`Vision stream connected for ${cameraId}`);
        setIsConnected(true);
        setError(null);
        frameCountRef.current = 0;
      };

      ws.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);

          if (data.type === 'frame') {
            setCurrentFrame(data.image);
            frameCountRef.current = data.frame_number;

            // Update metrics from frame data
            if (data.metrics) {
              setStreamMetrics(data.metrics);
            }
          } else if (data.type === 'error') {
            console.error('Stream error:', data.message);
            setError(data.message);
          }
        } catch (err) {
          console.error('Error parsing WebSocket message:', err);
        }
      };

      ws.onerror = (err) => {
        console.error('WebSocket error:', err);
        setError('WebSocket connection error');
        setIsConnected(false);
      };

      ws.onclose = () => {
        console.log(`Vision stream disconnected for ${cameraId}`);
        setIsConnected(false);

        // Auto-reconnect if still supposed to be streaming
        if (isStreaming) {
          reconnectTimeoutRef.current = setTimeout(() => {
            console.log('Attempting to reconnect...');
            connect();
          }, 3000);
        }
      };

      wsRef.current = ws;
    } catch (err) {
      console.error('Error creating WebSocket:', err);
      setError(err.message);
    }
  }, [cameraId, isStreaming]);

  const disconnect = useCallback(() => {
    if (wsRef.current) {
      wsRef.current.close();
      wsRef.current = null;
    }
    if (reconnectTimeoutRef.current) {
      clearTimeout(reconnectTimeoutRef.current);
      reconnectTimeoutRef.current = null;
    }
    setIsConnected(false);
    setCurrentFrame(null);
  }, []);

  // Connect/disconnect based on streaming state
  useEffect(() => {
    if (isStreaming && cameraId) {
      connect();
    } else {
      disconnect();
    }

    return () => {
      disconnect();
    };
  }, [cameraId, isStreaming, connect, disconnect]);

  // Apply settings when they change - REMOVED AUTO-SYNC
  // Settings are now applied manually via handleApplySettings in Vision.jsx
  // to avoid restarting streams on page load.

  return {
    currentFrame,
    streamMetrics,
    isConnected,
    error,
    frameCount: frameCountRef.current,
    reconnect: connect,
  };
};

export default useVisionStream;
