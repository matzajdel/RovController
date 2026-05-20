import React, { useState } from 'react';
import { BACKEND_CONFIG } from '../VirtualJoystick/Constants';

const CameraManager = ({ onCameraAdded }) => {
  const [isOpen, setIsOpen] = useState(false);
  const [name, setName] = useState('');
  const [cameraType, setCameraType] = useState('gstreamer');
  const [udpPort, setUdpPort] = useState('');
  const [url, setUrl] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError('');
    setLoading(true);

    const payload = { name, type: cameraType };

    if (cameraType === 'gstreamer') {
      const portNum = parseInt(udpPort, 10);
      if (isNaN(portNum) || portNum < 1 || portNum > 65535) {
        setError('UDP port must be a valid number between 1 and 65535.');
        setLoading(false);
        return;
      }
      payload.udp_port = portNum;
    } else {
      if (!url) {
        setError('Stream URL is required for HTTP cameras.');
        setLoading(false);
        return;
      }
      payload.url = url;
    }

    try {
      const response = await fetch(`${BACKEND_CONFIG.BACKEND_URL}/vision/cameras/add`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });

      if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.detail || 'Failed to add camera');
      }

      const data = await response.json();
      console.log('Camera added:', data);

      // Clear form
      setName('');
      setUdpPort('');
      setUrl('');
      setIsOpen(false);

      // Notify parent to refresh camera list
      if (onCameraAdded) {
        onCameraAdded();
      }
    } catch (err) {
      console.error('Error adding camera:', err);
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  if (!isOpen) {
    return (
      <button
        onClick={() => setIsOpen(true)}
        style={{
          padding: '10px 20px',
          backgroundColor: '#4CAF50',
          color: 'white',
          border: 'none',
          borderRadius: '5px',
          cursor: 'pointer',
          fontSize: '16px',
          marginBottom: '20px',
        }}
      >
        + Add Camera
      </button>
    );
  }

  return (
    <div style={{
      backgroundColor: '#2a2a2a',
      padding: '20px',
      borderRadius: '8px',
      marginBottom: '20px',
      border: '2px solid #4CAF50',
    }}>
      <h3 style={{ marginTop: 0, color: '#fff' }}>Add New Camera</h3>
      
      <form onSubmit={handleSubmit}>
        <div style={{ marginBottom: '15px' }}>
          <label style={{ display: 'block', marginBottom: '5px', color: '#ddd' }}>
            Camera Name:
          </label>
          <input
            type="text"
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="e.g., Front Camera, Arm Cam"
            required
            style={{
              width: '100%',
              padding: '8px',
              borderRadius: '4px',
              border: '1px solid #555',
              backgroundColor: '#333',
              color: '#fff',
              fontSize: '14px',
            }}
          />
        </div>

        <div style={{ marginBottom: '15px' }}>
          <label style={{ display: 'block', marginBottom: '5px', color: '#ddd' }}>
            Camera Type:
          </label>
          <select
            value={cameraType}
            onChange={(e) => setCameraType(e.target.value)}
            style={{
              width: '100%',
              padding: '8px',
              borderRadius: '4px',
              border: '1px solid #555',
              backgroundColor: '#333',
              color: '#fff',
              fontSize: '14px',
            }}
          >
            <option value="gstreamer">GStreamer UDP Feed</option>
            <option value="http_mjpeg">Remote HTTP/MJPEG</option>
          </select>
        </div>

        {cameraType === 'gstreamer' ? (
          <div style={{ marginBottom: '15px' }}>
            <label style={{ display: 'block', marginBottom: '5px', color: '#ddd' }}>
              UDP Port:
            </label>
            <input
              type="number"
              value={udpPort}
              onChange={(e) => setUdpPort(e.target.value)}
              placeholder="e.g. 2150"
              required
              min="1"
              max="65535"
              style={{
                width: '100%',
                padding: '8px',
                borderRadius: '4px',
                border: '1px solid #555',
                backgroundColor: '#333',
                color: '#fff',
                fontSize: '14px',
                fontFamily: 'monospace',
              }}
            />
            <small style={{ color: '#999', fontSize: '12px' }}>
              The port where the GStreamer UDP h264 stream is being sent.
            </small>
          </div>
        ) : (
          <div style={{ marginBottom: '15px' }}>
            <label style={{ display: 'block', marginBottom: '5px', color: '#ddd' }}>
              Stream URL:
            </label>
            <input
              type="url"
              value={url}
              onChange={(e) => setUrl(e.target.value)}
              placeholder="http://192.168.1.100:8080/?action=stream"
              required
              style={{
                width: '100%',
                padding: '8px',
                borderRadius: '4px',
                border: '1px solid #555',
                backgroundColor: '#333',
                color: '#fff',
                fontSize: '14px',
                fontFamily: 'monospace',
              }}
            />
          </div>
        )}

        {error && (
          <div style={{
            padding: '10px',
            backgroundColor: '#ff4444',
            color: 'white',
            borderRadius: '4px',
            marginBottom: '15px',
          }}>
            {error}
          </div>
        )}

        <div style={{ display: 'flex', gap: '10px' }}>
          <button
            type="submit"
            disabled={loading}
            style={{
              padding: '10px 20px',
              backgroundColor: loading ? '#666' : '#4CAF50',
              color: 'white',
              border: 'none',
              borderRadius: '5px',
              cursor: loading ? 'not-allowed' : 'pointer',
              fontSize: '14px',
            }}
          >
            {loading ? 'Adding...' : 'Add Camera'}
          </button>
          
          <button
            type="button"
            onClick={() => {
              setIsOpen(false);
              setError('');
              setName('');
              setUdpPort('');
            }}
            style={{
              padding: '10px 20px',
              backgroundColor: '#666',
              color: 'white',
              border: 'none',
              borderRadius: '5px',
              cursor: 'pointer',
              fontSize: '14px',
            }}
          >
            Cancel
          </button>
        </div>
      </form>

      <div style={{
        marginTop: '15px',
        padding: '10px',
        backgroundColor: '#1a1a1a',
        borderRadius: '4px',
        fontSize: '12px',
        color: '#aaa',
      }}>
        <strong style={{ color: '#4CAF50' }}>💡 Tip:</strong> Run the setup script on your robot first:
        <pre style={{ marginTop: '5px', padding: '5px', backgroundColor: '#000', borderRadius: '3px' }}>
          ./setup_robot_camera.sh
        </pre>
        Then copy the stream URL shown at the end.
      </div>
    </div>
  );
};

export default CameraManager;
