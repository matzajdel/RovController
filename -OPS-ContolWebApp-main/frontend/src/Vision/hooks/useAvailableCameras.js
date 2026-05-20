import { useState, useEffect } from 'react';

/**
 * Custom hook for fetching available cameras from backend
 */
export const useAvailableCameras = () => {
  const [cameras, setCameras] = useState([]);
  const [loading, setLoading] = useState(true);
  const [discovering, setDiscovering] = useState(false);
  const [error, setError] = useState(null);

  const fetchCameras = async (options = {}) => {
    const shouldDiscover = Boolean(options.discover);
    try {
      if (shouldDiscover) {
        setDiscovering(true);
      } else {
        setLoading(true);
      }
      const response = await fetch(
        `http://${window.location.hostname}:2137/vision/cameras${shouldDiscover ? '?discover=1' : ''}`
      );

      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }

      const data = await response.json();

      if (data.cameras && data.cameras.length > 0) {
        setCameras(data.cameras);
        setError(null);
      } else {
        // No cameras found
        setError(data.message || 'No cameras detected');
        setCameras([]);
      }
    } catch (err) {
      console.error('Error fetching cameras:', err);
      setError(err.message);

      // Fallback to likely V4L2 devices (instead of ROS2 mock cameras)
      setCameras([
        {
          id: 'v4l:/dev/video0',
          name: 'USB Camera (video0)',
          device: '/dev/video0',
          available: false,  // Mark as unavailable since we couldn't confirm
          type: 'v4l2'
        },
        {
          id: 'v4l:/dev/video1',
          name: 'USB Camera (video1)',
          device: '/dev/video1',
          available: false,
          type: 'v4l2'
        }
      ]);
    } finally {
      if (shouldDiscover) {
        setDiscovering(false);
      } else {
        setLoading(false);
      }
    }
  };

  const discoverCameras = async () => {
    await fetchCameras({ discover: true });
  };

  useEffect(() => {
    fetchCameras();
  }, []);

  return { cameras, loading, discovering, error, refetch: fetchCameras, discoverCameras };
};

export default useAvailableCameras;
