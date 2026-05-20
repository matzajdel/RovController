import React, { useState, useEffect } from 'react';
import { useParams, useSearchParams } from 'react-router-dom';
import useVisionStream from './hooks/useVisionStream';
import './CameraPopout.css';

export const CameraPopout = () => {
  const [searchParams] = useSearchParams();
  const cameraId = searchParams.get('cameraId');
  const cameraName = searchParams.get('name') || cameraId;
  const mode = searchParams.get('mode') || 'full';
  
  // Get settings from URL params
  const [settings] = useState({
    resolution: searchParams.get('resolution') || '640x480',
    fps: parseInt(searchParams.get('fps')) || 15,
    compression: searchParams.get('compression') || 'compressed',
    jpeg_quality: parseInt(searchParams.get('quality')) || 50,
    zoom_preset: searchParams.get('zoom') || 'none',
  });

  // Stream hook
  const { 
    currentFrame, 
    streamMetrics, 
    isConnected, 
    error,
    frameCount 
  } = useVisionStream(cameraId, settings, true);

  // Keyboard shortcuts
  useEffect(() => {
    const handleKeyPress = (e) => {
      if (e.key === 'Escape') {
        window.close();
      }
      if (e.key === 'f' || e.key === 'F') {
        if (!document.fullscreenElement) {
          document.documentElement.requestFullscreen();
        } else {
          document.exitFullscreen();
        }
      }
    };
    
    window.addEventListener('keydown', handleKeyPress);
    return () => window.removeEventListener('keydown', handleKeyPress);
  }, []);

  return (
    <div className={`camera-popout ${mode}`}>
      <div className='camera-popout-header'>
        <div className='camera-popout-title'>
          <h1>{cameraName}</h1>
          <div className='camera-popout-info'>
            <span>{settings.resolution} @ {settings.fps}fps</span>
            <span className={`connection-dot ${isConnected ? 'connected' : 'disconnected'}`}></span>
          </div>
        </div>
        <div className='camera-popout-controls'>
          <button 
            className='control-btn'
            onClick={() => {
              if (!document.fullscreenElement) {
                document.documentElement.requestFullscreen();
              } else {
                document.exitFullscreen();
              }
            }}
            title='Toggle Fullscreen (F)'
          >
            ⛶ Fullscreen
          </button>
          <button 
            className='close-btn'
            onClick={() => window.close()}
            title='Close Window (ESC)'
          >
            ✕ Close
          </button>
        </div>
      </div>
      
      <div className='camera-popout-preview'>
        {currentFrame ? (
          <img 
            src={`data:image/jpeg;base64,${currentFrame}`} 
            alt={`${cameraName} Stream`} 
            className="popout-image"
          />
        ) : (
          <div className="placeholder">
            {error ? (
              <div className='error-display'>
                <p className='error-icon'>⚠️</p>
                <p className='error-message'>Stream Error</p>
                <p className='error-detail'>{error}</p>
              </div>
            ) : (
              <div className='loading-display'>
                <div className='spinner'></div>
                <p>Connecting to {cameraName}...</p>
              </div>
            )}
          </div>
        )}
      </div>
      
      <div className='camera-popout-footer'>
        <div className='metrics-grid'>
          <div className='metric-item'>
            <span className='metric-label'>Bandwidth</span>
            <span className='metric-value'>{streamMetrics?.bandwidth_mbps?.toFixed(2) || 0} Mb/s</span>
          </div>
          <div className='metric-item'>
            <span className='metric-label'>Latency</span>
            <span className='metric-value'>{streamMetrics?.latency_ms?.toFixed(0) || 0} ms</span>
          </div>
          <div className='metric-item'>
            <span className='metric-label'>FPS</span>
            <span className='metric-value'>{streamMetrics?.actual_fps?.toFixed(1) || 0} fps</span>
          </div>
          <div className='metric-item'>
            <span className='metric-label'>Frames</span>
            <span className='metric-value'>{frameCount || 0}</span>
          </div>
        </div>
        <div className='keyboard-hints'>
          <kbd>ESC</kbd> Close • <kbd>F</kbd> Fullscreen
        </div>
      </div>
    </div>
  );
};

export default CameraPopout;
