import { useState, useEffect } from 'react';

/**
 * Custom hook for fetching camera metrics from backend
 * Polls the metrics endpoint at regular intervals
 */
export const useVisionMetrics = (cameraId, pollingInterval = 1000) => {
  const [metrics, setMetrics] = useState({
    bandwidth_mbps: 0,
    latency_ms: 0,
    actual_fps: 0,
    frame_count: 0,
    last_update: null
  });
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  useEffect(() => {
    if (!cameraId) {
      return;
    }

    let isMounted = true;
    let intervalId = null;

    const fetchMetrics = async () => {
      try {
        setLoading(true);
        const response = await fetch(
          `http://${window.location.hostname}:2137/vision/metrics/${cameraId}`
        );
        
        if (!response.ok) {
          throw new Error(`HTTP error! status: ${response.status}`);
        }
        
        const data = await response.json();
        
        if (isMounted) {
          setMetrics(data);
          setError(null);
        }
      } catch (err) {
        if (isMounted) {
          console.error('Error fetching metrics:', err);
          setError(err.message);
        }
      } finally {
        if (isMounted) {
          setLoading(false);
        }
      }
    };

    // Initial fetch
    fetchMetrics();

    // Set up polling
    intervalId = setInterval(fetchMetrics, pollingInterval);

    return () => {
      isMounted = false;
      if (intervalId) {
        clearInterval(intervalId);
      }
    };
  }, [cameraId, pollingInterval]);

  return { metrics, loading, error };
};

export default useVisionMetrics;
