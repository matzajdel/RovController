/**
 * Shared Application Configuration
 * ==================================
 *
 * Central configuration for the entire frontend application.
 * All backend URLs, WebSocket endpoints, and global constants are
 * defined here so that every module imports from a single source.
 *
 * URL generation is dynamic — the backend host matches the browser's
 * current hostname, which ensures the app works both on localhost and
 * when accessed from another machine on the same network.
 *
 * Used by: VirtualJoystick, Science, GPS, Vision, StatusJetson, and
 * all custom hooks.
 */

// ---------------------------------------------------------------------------
// URL helpers — derive backend addresses from the browser hostname
// ---------------------------------------------------------------------------

const getBackendUrl = (port) => {
  const hostname = window.location.hostname;
  return `http://${hostname}:${port}`;
};

const getWsUrl = (port) => {
  const hostname = window.location.hostname;
  return `ws://${hostname}:${port}/ws`;
};

const getRosBridgeUrl = (port) => {
  const hostname = window.location.hostname;
  return `ws://${hostname}:${port}`;
};

// ---------------------------------------------------------------------------
// Backend connection settings
// ---------------------------------------------------------------------------

/** Primary backend (FastAPI on port 2137) */
export const BACKEND_URL = getBackendUrl(2137);

/** GPS micro-service (Flask on port 5001) */
export const GPS_BACKEND_URL = getBackendUrl(5001);

/** WebSocket endpoint for real-time updates */
export const WS_URL = getWsUrl(2137);

/** Rosbridge WebSocket (direct ROS publishing, no backend needed) */
export const ROSBRIDGE_URL = getRosBridgeUrl(9090);

/** How often to poll /health (ms) */
export const HEALTH_CHECK_INTERVAL = 1000;

// Also export a grouped object for backwards compatibility with
// existing code that imports BACKEND_CONFIG from Constants.js
export const BACKEND_CONFIG = {
  BACKEND_URL,
  GPS_BACKEND_URL,
  WS_URL,
  ROSBRIDGE_URL,
  HEALTH_CHECK_INTERVAL,
};
