import React, { useCallback, useEffect, useMemo, useState } from 'react';
import './Vision.css';
import DEFAULT_CAMERAS from './cameras.json';

const INT_FIELDS = new Set([
  'width',
  'height',
  'framerate',
  'bitrate',
  'target_port',
  'ssh_port',
  'rotation',
]);

const BASE_URL = `http://${window.location.hostname}:2137/vision`;
const DEVICE_PATH_REGEX = /\/dev\/video\d+/g;
const SINGLE_DEVICE_PATH_REGEX = /^\/dev\/video\d+$/;
const SOURCE_FORMAT_FALLBACK = ['auto', 'raw', 'h264', 'mjpeg', 'yuy2'];

const FIELD_GROUPS = [
  [
    { key: 'width', label: 'Width', type: 'number' },
    { key: 'height', label: 'Height', type: 'number' },
    { key: 'framerate', label: 'Framerate', type: 'number' },
    { key: 'bitrate', label: 'Bitrate', type: 'number' },
    { key: 'target_ip', label: 'Target IP', type: 'text' },
    { key: 'target_port', label: 'Target Port', type: 'number' },
  ],
  [
    { key: 'ssh_host', label: 'SSH Host', type: 'text' },
    { key: 'ssh_port', label: 'SSH Port', type: 'number' },
    { key: 'ssh_user', label: 'SSH User', type: 'text' },
    { key: 'ssh_password', label: 'SSH Password', type: 'password' },
  ],
];

const safeText = (value) => (value === null || value === undefined ? '' : String(value));

const toDraft = (config) => {
  const draft = { ...config };
  Object.keys(draft).forEach((key) => {
    if (INT_FIELDS.has(key)) {
      draft[key] = safeText(draft[key]);
    }
  });
  return draft;
};

const buildPayload = (draft) => {
  const payload = { ...draft };
  INT_FIELDS.forEach((field) => {
    if (field in payload) {
      const parsed = parseInt(payload[field], 10);
      if (Number.isNaN(parsed)) {
        throw new Error(`${field} must be an integer`);
      }
      payload[field] = parsed;
    }
  });
  payload.mirror_horizontal = Boolean(payload.mirror_horizontal);
  payload.force_software_transcode = Boolean(payload.force_software_transcode);
  return payload;
};

const ensureOk = async (response, fallbackMessage) => {
  if (response.ok) {
    return;
  }
  const errorData = await response.json().catch(() => ({}));
  throw new Error(errorData.detail || fallbackMessage);
};

const extractDevicePaths = (cameraList) => {
  if (!Array.isArray(cameraList)) {
    return [];
  }
  const devices = [];
  cameraList.forEach((camera) => {
    if (camera?.source !== 'ssh_auto_discovery') {
      return;
    }
    if (typeof camera?.device === 'string') {
      const matches = camera.device.match(DEVICE_PATH_REGEX);
      if (matches) {
        matches.forEach((match) => devices.push(match));
      }
    }
    if (typeof camera?.id === 'string') {
      const matches = camera.id.match(DEVICE_PATH_REGEX);
      if (matches) {
        matches.forEach((match) => devices.push(match));
      }
    }
  });
  return Array.from(new Set(devices)).sort();
};

const labelDeviceOption = (devicePath, discoveredSet, manualSet) => {
  if (!devicePath) {
    return '';
  }
  if (discoveredSet.has(devicePath)) {
    return `${devicePath} (discovered)`;
  }
  if (manualSet.has(devicePath)) {
    return `${devicePath} (manual)`;
  }
  return devicePath;
};

export const Vision = () => {
  const [cameraConfigs, setCameraConfigs] = useState({});
  const [drafts, setDrafts] = useState({});
  const [executionModes, setExecutionModes] = useState(['local', 'ssh']);
  const [sourceFormatModes, setSourceFormatModes] = useState(SOURCE_FORMAT_FALLBACK);
  const [zoomOptions, setZoomOptions] = useState(['1x', '1.5x', '2x', '3x']);
  const [resolutionPresets, setResolutionPresets] = useState({
    'Full HD (1920x1080)': { width: 1920, height: 1080 },
    'HD (1280x720)': { width: 1280, height: 720 },
    'qHD (960x540)': { width: 960, height: 540 },
    'VGA (640x480)': { width: 640, height: 480 },
    'SD Wide (854x480)': { width: 854, height: 480 },
    'nHD (640x360)': { width: 640, height: 360 },
    'QVGA Wide (426x240)': { width: 426, height: 240 },
  });
  const [statusText, setStatusText] = useState('Connecting to backend...');
  const [errorText, setErrorText] = useState('');
  const [busy, setBusy] = useState({});
  const [discovering, setDiscovering] = useState(false);
  const [probing, setProbing] = useState(false);
  const [discoveredDevices, setDiscoveredDevices] = useState([]);
  const [manualDeviceInputs, setManualDeviceInputs] = useState(['']);
  const [probeResult, setProbeResult] = useState(null);
  const [discoveredCameraMeta, setDiscoveredCameraMeta] = useState([]);
  // [{name, nodes:['/dev/video0', ...]}, ...]
  const [cameraGroups, setCameraGroups] = useState([]);
  // Per-card selected physical camera name: { camId -> groupName }
  const [selectedGroups, setSelectedGroups] = useState({});

  const cameraIds = useMemo(() => Object.keys(cameraConfigs).sort(), [cameraConfigs]);

  const manualDevices = useMemo(() => {
    const valid = [];
    manualDeviceInputs.forEach((value) => {
      const candidate = safeText(value).trim();
      if (SINGLE_DEVICE_PATH_REGEX.test(candidate) && !valid.includes(candidate)) {
        valid.push(candidate);
      }
    });
    return valid;
  }, [manualDeviceInputs]);

  const deviceOptions = useMemo(() => {
    const merged = [...discoveredDevices, ...manualDevices];
    return Array.from(new Set(merged));
  }, [discoveredDevices, manualDevices]);

  const discoveredDeviceSet = useMemo(() => new Set(discoveredDevices), [discoveredDevices]);
  const manualDeviceSet = useMemo(() => new Set(manualDevices), [manualDevices]);
  const discoveredDeviceLabelMap = useMemo(() => {
    const entries = [];
    discoveredCameraMeta.forEach((camera) => {
      const device = safeText(camera?.device).trim();
      if (!device) {
        return;
      }
      const detectedName = safeText(camera?.detected_name).trim();
      const displayName = safeText(camera?.name).trim();
      const labelBase = detectedName || displayName || 'Detected Camera';
      entries.push([device, `${labelBase} (${device})`]);
    });
    return new Map(entries);
  }, [discoveredCameraMeta]);

  const mergeDrafts = useCallback((configs) => {
    setDrafts((prev) => {
      const next = {};
      Object.entries(configs).forEach(([camId, config]) => {
        next[camId] = prev[camId] ? { ...prev[camId] } : toDraft(config);
      });
      return next;
    });
  }, []);

  const loadOptions = useCallback(async () => {
    const response = await fetch(`${BASE_URL}/api/camera-options`);
    if (!response.ok) {
      throw new Error('Failed to fetch camera options');
    }
    const data = await response.json();
    if (Array.isArray(data.execution_modes) && data.execution_modes.length > 0) {
      setExecutionModes(data.execution_modes);
    }
    if (Array.isArray(data.source_format_modes) && data.source_format_modes.length > 0) {
      setSourceFormatModes(data.source_format_modes);
    }
    if (Array.isArray(data.zoom_options) && data.zoom_options.length > 0) {
      setZoomOptions(data.zoom_options);
    }
    if (data.resolution_presets && typeof data.resolution_presets === 'object') {
      setResolutionPresets(data.resolution_presets);
    }
  }, []);

  const loadCameras = useCallback(async (message) => {
    const response = await fetch(`${BASE_URL}/api/cameras?force=1`);
    if (!response.ok) {
      throw new Error('Failed to fetch camera configuration');
    }
    const data = await response.json();
    setCameraConfigs(data);
    mergeDrafts(data);
    const count = Object.keys(data || {}).length;
    if (count === 0) {
      setStatusText('No cameras discovered. Run Auto Discover Cameras to probe 192.168.2.50.');
    } else {
      setStatusText(message || 'Statuses refreshed');
    }
  }, [mergeDrafts]);

  const refreshAll = useCallback(async (message) => {
    setErrorText('');
    try {
      await Promise.all([loadOptions(), loadCameras(message)]);
    } catch (err) {
      setErrorText(err.message || 'Unable to load vision camera data');
      setStatusText('Failed to refresh statuses');
    }
  }, [loadCameras, loadOptions]);

  useEffect(() => {
    refreshAll('Loaded camera configuration');
  }, [refreshAll]);

  useEffect(() => {
    const timer = window.setInterval(() => {
      loadCameras('Statuses refreshed').catch(() => {
        // Silent in polling; user gets manual refresh + error state from actions.
      });
    }, 5000);
    return () => window.clearInterval(timer);
  }, [loadCameras]);

  const setField = (camId, field, value) => {
    setDrafts((prev) => ({
      ...prev,
      [camId]: {
        ...prev[camId],
        [field]: value,
      },
    }));
  };

  const resolutionPresetForDraft = (draft) => {
    const width = parseInt(safeText(draft?.width), 10);
    const height = parseInt(safeText(draft?.height), 10);
    if (Number.isNaN(width) || Number.isNaN(height)) {
      return '';
    }

    const match = Object.entries(resolutionPresets).find(([, values]) => {
      return Number(values?.width) === width && Number(values?.height) === height;
    });
    return match ? match[0] : '';
  };

  const applyResolutionPreset = (camId, presetLabel) => {
    const preset = resolutionPresets[presetLabel];
    if (!preset) {
      return;
    }

    setDrafts((prev) => ({
      ...prev,
      [camId]: {
        ...prev[camId],
        width: safeText(preset.width),
        height: safeText(preset.height),
      },
    }));
  };

  const withBusy = async (camId, action, fn) => {
    const key = `${camId}:${action}`;
    setBusy((prev) => ({ ...prev, [key]: true }));
    setErrorText('');
    try {
      await fn();
    } catch (err) {
      setErrorText(err.message || `Failed action ${action} on camera ${camId}`);
    } finally {
      setBusy((prev) => {
        const next = { ...prev };
        delete next[key];
        return next;
      });
    }
  };

  const isBusy = (camId, action) => Boolean(busy[`${camId}:${action}`]);

  const persistDraft = useCallback(async (camId) => {
    const payload = buildPayload(drafts[camId] || {});
    const response = await fetch(`${BASE_URL}/api/cameras/${camId}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    await ensureOk(response, `Failed to apply settings for camera ${camId}`);

    const updatedConfig = await response.json();
    setCameraConfigs((prev) => ({
      ...prev,
      [camId]: updatedConfig,
    }));
    setDrafts((prev) => ({
      ...prev,
      [camId]: toDraft(updatedConfig),
    }));
  }, [drafts]);

  const applyChanges = async (camId) => {
    await withBusy(camId, 'apply', async () => {
      await persistDraft(camId);
      await loadCameras(`Applied settings for camera ${camId}`);
    });
  };

  const postAction = async (camId, action, message) => {
    await withBusy(camId, action, async () => {
      if (action === 'sender/start' || action === 'receiver/start') {
        await persistDraft(camId);
      }

      const response = await fetch(`${BASE_URL}/api/cameras/${camId}/${action}`, {
        method: 'POST',
      });
      await ensureOk(response, `Failed action ${action} for camera ${camId}`);
      await loadCameras(message);
    });
  };

  const runAutoDiscovery = async () => {
    setErrorText('');
    setDiscovering(true);
    try {
      const response = await fetch(`${BASE_URL}/cameras/discover`, {
        method: 'POST',
      });
      await ensureOk(response, 'Failed to auto-discover cameras');

      const data = await response.json();
      const discovered = extractDevicePaths(data?.cameras || []);
      setDiscoveredDevices(discovered);
      setDiscoveredCameraMeta(Array.isArray(data?.cameras) ? data.cameras : []);
      if (Array.isArray(data?.camera_groups) && data.camera_groups.length > 0) {
        setCameraGroups(data.camera_groups);
      }
      const discoveredCount = Array.isArray(data?.cameras)
        ? data.cameras.filter((camera) => camera?.source === 'ssh_auto_discovery').length
        : 0;

      if (discovered.length > 0) {
        setDrafts((prev) => {
          const next = { ...prev };
          cameraIds.forEach((camId, idx) => {
            if (!next[camId]) {
              return;
            }
            next[camId] = {
              ...next[camId],
              device: discovered[idx] || next[camId].device || '',
            };
          });
          return next;
        });
      }

      if (discoveredCount > 0) {
        setStatusText(`Auto discovery found ${discoveredCount} camera(s)`);
      } else {
        const backendMessage = typeof data?.message === 'string' ? data.message : '';
        setStatusText(backendMessage || 'Auto discovery finished (no cameras found)');
      }
    } catch (err) {
      setErrorText(err.message || 'Failed to auto-discover cameras');
    } finally {
      setDiscovering(false);
    }
  };

  const runProbeDebug = async () => {
    setErrorText('');
    setProbing(true);
    try {
      const response = await fetch(`${BASE_URL}/cameras/discovery-debug?force=1`);
      await ensureOk(response, 'Failed to run v4l2 probe');
      const data = await response.json();
      setProbeResult(data);

      const devices = Array.isArray(data?.devices) ? data.devices : [];
      if (devices.length > 0) {
        setStatusText(`v4l2-ctl --list-devices detected ${devices.length} device(s)`);
      } else {
        const message = data?.diagnostics?.last_error || 'v4l2-ctl --list-devices detected 0 devices';
        setStatusText(message);
      }
    } catch (err) {
      setErrorText(err.message || 'Failed to run v4l2 probe');
    } finally {
      setProbing(false);
    }
  };

  const updateManualDeviceInput = (index, value) => {
    setManualDeviceInputs((prev) => {
      const next = [...prev];
      next[index] = value;

      // Keep exactly one empty field at the end; typing into the last field creates a new one.
      if (index === next.length - 1 && safeText(value).trim() !== '') {
        next.push('');
      }

      while (
        next.length > 1
        && safeText(next[next.length - 1]).trim() === ''
        && safeText(next[next.length - 2]).trim() === ''
      ) {
        next.pop();
      }

      return next;
    });
  };

  return (
    <div className="vision-controller-page">
      <div className="vision-controller-header">
        <div>
          <h2>Vision App Controller</h2>
          <p>Standalone-style sender/receiver camera control for all detected devices.</p>
        </div>
        <div className="vision-controller-header-actions">
          <button
            className="vision-controller-button"
            onClick={runAutoDiscovery}
            disabled={Object.keys(busy).length > 0 || discovering}
          >
            {discovering ? 'Discovering...' : 'Auto Discover Cameras'}
          </button>
          <button
            className="vision-controller-button secondary"
            onClick={() => refreshAll('Statuses refreshed')}
            disabled={Object.keys(busy).length > 0 || discovering || probing}
          >
            Refresh Status
          </button>
          <button
            className="vision-controller-button secondary"
            onClick={runProbeDebug}
            disabled={Object.keys(busy).length > 0 || discovering || probing}
          >
            {probing ? 'Probing v4l2...' : 'Probe v4l2-ctl'}
          </button>
        </div>
      </div>

      <div className="vision-controller-status-row">
        <span className="status-chip">{statusText}</span>
        {errorText && <span className="status-chip error">{errorText}</span>}
      </div>

      {probeResult && (
        <div className="vision-probe-panel">
          <div className="vision-probe-title">Remote v4l2 probe (`v4l2-ctl --list-devices`)</div>
          <div className="vision-probe-meta">
            Host: {safeText(probeResult?.probe?.ssh_host)} | User: {safeText(probeResult?.probe?.ssh_user)} | Port: {safeText(probeResult?.probe?.ssh_port)}
          </div>
          <div className="vision-probe-meta">
            Exit: {safeText(probeResult?.probe?.exit_code)} | Timed out: {String(Boolean(probeResult?.probe?.timed_out))}
          </div>
          <div className="vision-probe-meta">
            Devices: {(Array.isArray(probeResult?.devices) ? probeResult.devices : []).join(', ') || '(none)'}
          </div>
          <pre className="vision-probe-output">{safeText(probeResult?.probe?.stdout) || '(no stdout)'}</pre>
          {safeText(probeResult?.probe?.stderr) && (
            <pre className="vision-probe-output error">{safeText(probeResult?.probe?.stderr)}</pre>
          )}
        </div>
      )}

      <div className="vision-input-row single">
        <label>Manual Camera Device Paths</label>
        <div className="vision-manual-device-list">
          {manualDeviceInputs.map((value, index) => (
            <input
              key={`manual-device-${index}`}
              type="text"
              placeholder={`/dev/video${index}`}
              value={value}
              onChange={(e) => updateManualDeviceInput(index, e.target.value)}
            />
          ))}
        </div>
      </div>

      <div className="vision-controller-grid">
        {cameraIds.map((camId) => {
          const config = cameraConfigs[camId] || {};
          const draft = drafts[camId] || toDraft(config);
          const configuredCameraName =
            safeText(config.camera_name || draft.camera_name).trim() || 'Camera';
          const cameraHeaderLabel = `${configuredCameraName} [ID: ${camId}]`;
          const selectedResolutionPreset = resolutionPresetForDraft(draft);
          // Determine which physical camera group is currently selected for this card.
          const savedDevice = safeText(draft.device) || safeText(config.device);
          const defaultGroup = cameraGroups.find((g) => Array.isArray(g.nodes) && g.nodes.includes(savedDevice))?.name || '';
          const selectedGroupName = selectedGroups[camId] !== undefined ? selectedGroups[camId] : defaultGroup;

          // Nodes to offer in the video-node dropdown – only those belonging to the chosen group.
          const groupNodes = cameraGroups.find((g) => g.name === selectedGroupName)?.nodes || [];
          // Fall back to manual + full discovered list when no group is selected yet.
          const cardDeviceOptions = selectedGroupName && groupNodes.length > 0
            ? groupNodes
            : Array.from(new Set(deviceOptions));
          const selectedDevice = cardDeviceOptions.includes(savedDevice) ? savedDevice : '';
          const cameraSupportedFormats = Array.isArray(config.supported_source_formats)
            ? config.supported_source_formats
            : sourceFormatModes;
          const selectedSourceFormat = cameraSupportedFormats.includes(safeText(draft.source_format))
            ? safeText(draft.source_format)
            : 'auto';

          return (
            <section key={camId} className="vision-camera-card">
              <div className="vision-camera-card-head">
                <h3>{cameraHeaderLabel}</h3>
                <span className="vision-camera-device">Device: {safeText(draft.device) || safeText(config.device)}</span>
              </div>

              <div className="vision-camera-state-row">
                <span className={`state-pill ${config.sender_running ? 'running' : 'stopped'}`}>
                  Sender: {config.sender_running ? 'Running' : 'Stopped'}
                </span>
                <span className={`state-pill ${config.receiver_running ? 'running' : 'stopped'}`}>
                  Listener: {config.receiver_running ? 'Running' : 'Stopped'}
                </span>
              </div>

              <div className="vision-input-row single">
                <label>Execution Mode</label>
                <select
                  value={safeText(draft.execution_mode)}
                  onChange={(e) => setField(camId, 'execution_mode', e.target.value)}
                >
                  {executionModes.map((mode) => (
                    <option key={mode} value={mode}>{mode}</option>
                  ))}
                </select>
              </div>

              <div className="vision-input-row single">
                <label>Resolution Preset</label>
                <select
                  value={selectedResolutionPreset}
                  onChange={(e) => applyResolutionPreset(camId, e.target.value)}
                >
                  <option value="">Custom</option>
                  {Object.keys(resolutionPresets).map((label) => (
                    <option key={label} value={label}>{label}</option>
                  ))}
                </select>
              </div>

              {cameraGroups.length > 0 && (
                <div className="vision-input-row single">
                  <label>Camera</label>
                  <select
                    value={selectedGroupName}
                    onChange={(e) => {
                      const groupName = e.target.value;
                      setSelectedGroups((prev) => ({ ...prev, [camId]: groupName }));
                      // Auto-select first video node of the chosen group.
                      const nodes = cameraGroups.find((g) => g.name === groupName)?.nodes || [];
                      if (nodes.length > 0) {
                        setField(camId, 'device', nodes[0]);
                      }
                    }}
                  >
                    <option value="">— pick a camera —</option>
                    {cameraGroups.map((g) => (
                      <option key={g.name} value={g.name}>{g.name}</option>
                    ))}
                  </select>
                </div>
              )}

              <div className="vision-input-row single">
                <label>{cameraGroups.length > 0 ? '/dev/video node' : 'Device'}</label>
                <select
                  value={selectedDevice}
                  onChange={(e) => setField(camId, 'device', e.target.value)}
                >
                  <option value="">{cameraGroups.length > 0 ? '— pick a node —' : 'Select a device'}</option>
                  {cardDeviceOptions.map((devicePath) => (
                    <option key={devicePath} value={devicePath}>
                      {cameraGroups.length > 0
                        ? devicePath
                        : (discoveredDeviceLabelMap.get(devicePath) || labelDeviceOption(devicePath, discoveredDeviceSet, manualDeviceSet))}
                    </option>
                  ))}
                </select>
              </div>

              <div className="vision-input-row single">
                <label>V4L2 Source Type</label>
                <select
                  value={selectedSourceFormat}
                  onChange={(e) => setField(camId, 'source_format', e.target.value)}
                >
                  {cameraSupportedFormats.map((mode) => (
                    <option key={`${camId}:source:${mode}`} value={mode}>{mode}</option>
                  ))}
                </select>
              </div>

              <div className="vision-input-row single checkbox-row">
                <label className="checkbox-label">
                  <input
                    type="checkbox"
                    checked={Boolean(draft.force_software_transcode)}
                    onChange={(e) => setField(camId, 'force_software_transcode', e.target.checked)}
                  />
                  Force Software Resolution/FPS/Bitrate Override
                </label>
              </div>

              {safeText(config.v4l2_caps_error) && (
                <div className="vision-source-warning">
                  V4L2 capability read failed: {safeText(config.v4l2_caps_error)}
                </div>
              )}

              {safeText(config.v4l2_formats_output) && (
                <details className="vision-caps-details">
                  <summary>Show v4l2 supported modes</summary>
                  <pre>{safeText(config.v4l2_formats_output)}</pre>
                </details>
              )}

              {FIELD_GROUPS[0].map((field) => (
                <div className="vision-input-row" key={`${camId}:${field.key}`}>
                  <label>{field.label}</label>
                  <input
                    type={field.type}
                    value={safeText(draft[field.key])}
                    onChange={(e) => setField(camId, field.key, e.target.value)}
                  />
                </div>
              ))}

              {FIELD_GROUPS[1].map((field) => (
                <div className="vision-input-row" key={`${camId}:${field.key}`}>
                  <label>{field.label}</label>
                  <input
                    type={field.type}
                    value={safeText(draft[field.key])}
                    onChange={(e) => setField(camId, field.key, e.target.value)}
                  />
                </div>
              ))}

              <div className="vision-input-row single">
                <label>Zoom</label>
                <select
                  value={safeText(draft.zoom)}
                  onChange={(e) => setField(camId, 'zoom', e.target.value)}
                >
                  {zoomOptions.map((zoom) => (
                    <option key={zoom} value={zoom}>{zoom}</option>
                  ))}
                </select>
              </div>

              <div className="vision-input-row single checkbox-row">
                <label className="checkbox-label">
                  <input
                    type="checkbox"
                    checked={Boolean(draft.mirror_horizontal)}
                    onChange={(e) => setField(camId, 'mirror_horizontal', e.target.checked)}
                  />
                  Mirror Horizontally
                </label>
              </div>

              <div className="vision-input-row single">
                <label>Rotation</label>
                <select
                  value={safeText(draft.rotation || '0')}
                  onChange={(e) => setField(camId, 'rotation', e.target.value)}
                >
                  {[0, 90, 180, 270].map((rot) => (
                    <option key={rot} value={rot}>{rot}°</option>
                  ))}
                </select>
              </div>

              <div className="vision-crop-summary">
                Auto crop L/R {config.crop_left}/{config.crop_right} | T/B {config.crop_top}/{config.crop_bottom}
              </div>

              <div className="vision-action-row">
                <button
                  className="vision-controller-button"
                  onClick={() => postAction(camId, 'sender/start', `Started sender for camera ${camId}`)}
                  disabled={isBusy(camId, 'sender/start')}
                >
                  Start Sender
                </button>
                <button
                  className="vision-controller-button danger"
                  onClick={() => postAction(camId, 'sender/stop', `Stopped sender for camera ${camId}`)}
                  disabled={isBusy(camId, 'sender/stop')}
                >
                  Stop Sender
                </button>
                <button
                  className="vision-controller-button accent"
                  onClick={() => applyChanges(camId)}
                  disabled={isBusy(camId, 'apply')}
                >
                  Apply Settings
                </button>
              </div>

              <div className="vision-action-row">
                <button
                  className="vision-controller-button"
                  onClick={() => postAction(camId, 'receiver/start', `Started listener for camera ${camId}`)}
                  disabled={isBusy(camId, 'receiver/start')}
                >
                  Start Listener
                </button>
                <button
                  className="vision-controller-button danger"
                  onClick={() => postAction(camId, 'receiver/stop', `Stopped listener for camera ${camId}`)}
                  disabled={isBusy(camId, 'receiver/stop')}
                >
                  Stop Listener
                </button>
              </div>
            </section>
          );
        })}
      </div>
    </div>
  );
};
