import React, { useCallback, useEffect, useRef, useState } from "react";
import "./StatusJetson.css";
import { BACKEND_CONFIG } from "../VirtualJoystick/Constants";
import { useBackendHealth } from "../hooks/useBackendHealth";
import ScienceDashboard from "../Science/ScienceDashboard";

const API = BACKEND_CONFIG.BACKEND_URL;

const emptyScriptForm = {
  name: "",
  session: "",
  command: "",
  working_dir: "",
  auto_restart: false,
  description: "",
  tags: "",
};

const toTagArray = (value) => {
  if (Array.isArray(value)) {
    return value.filter(Boolean);
  }
  if (!value) {
    return [];
  }
  return String(value)
    .split(",")
    .map((tag) => tag.trim())
    .filter(Boolean);
};

const toTagString = (value) => toTagArray(value).join(", ");

const createLogState = (overrides = {}) => ({
  text: "",
  session: "",
  updatedAt: null,
  startedAt: null,
  autoRestart: false,
  lines: 0,
  ...overrides,
});

export const StatusJetson = () => {
  useBackendHealth();
  const [screens, setScreens] = useState([]);
  const [scripts, setScripts] = useState([]);
  const [selectedScript, setSelectedScript] = useState("");
  const [selectedSession, setSelectedSession] = useState("");
  const [logState, setLogState] = useState(createLogState());
  const [logLines, setLogLines] = useState(200);
  const [autoRefreshScreens, setAutoRefreshScreens] = useState(true);
  const [autoRefreshLogs, setAutoRefreshLogs] = useState(true);
  const [scriptForm, setScriptForm] = useState({ ...emptyScriptForm });
  const [customCommand, setCustomCommand] = useState("");
  const [customSession, setCustomSession] = useState("");
  const [customAutoRestart, setCustomAutoRestart] = useState(false);
  const [statusMessage, setStatusMessage] = useState("");
  const [errorMessage, setErrorMessage] = useState("");
  const [showScriptForm, setShowScriptForm] = useState(false);

  const [microrosDevices, setMicrorosDevices] = useState([]);
  const logViewerRef = useRef(null);

  const pushStatus = useCallback((msg) => {
    setStatusMessage(msg);
    setTimeout(() => setStatusMessage(""), 4000);
  }, []);

  const pushError = useCallback((msg) => {
    setErrorMessage(msg);
    setTimeout(() => setErrorMessage(""), 5000);
  }, []);

  // =======================================================================
  // Screen Management
  // =======================================================================

  const fetchScreens = useCallback(async () => {
    try {
      const res = await fetch(`${API}/ros2/screens`);
      if (res.ok) {
        const data = await res.json();
        setScreens(data.screens || []);
      }
    } catch (err) {
      console.error("Failed to fetch screens", err);
    }
  }, []);

  const fetchScripts = useCallback(async () => {
    try {
      const res = await fetch(`${API}/ros2/scripts`);
      if (res.ok) {
        const data = await res.json();
        setScripts(data.scripts || []);
      }
    } catch (err) {
      console.error("Failed to fetch scripts", err);
    }
  }, []);

  const runScript = async (scriptName) => {
    try {
      const res = await fetch(`${API}/ros2/screens/run`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ script_name: scriptName }),
      });
      if (res.ok) {
        pushStatus(`Started script: ${scriptName}`);
        setTimeout(fetchScreens, 800);
      } else {
        const err = await res.json();
        pushError(`Failed to start: ${err.detail}`);
      }
    } catch (e) {
      pushError(`Error: ${e.message}`);
    }
  };

  const runCustomCommand = async () => {
    if (!customCommand.trim()) return;
    try {
      const res = await fetch(`${API}/ros2/screens/run`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          command: customCommand,
          session: customSession || undefined,
          auto_restart: customAutoRestart,
        }),
      });
      if (res.ok) {
        pushStatus(`Custom command started`);
        setCustomCommand("");
        setCustomSession("");
        setTimeout(fetchScreens, 800);
      } else {
        const err = await res.json();
        pushError(`Failed: ${err.detail}`);
      }
    } catch (e) {
      pushError(`Error: ${e.message}`);
    }
  };

  const killScreen = async (session) => {
    try {
      const res = await fetch(`${API}/ros2/screens/kill`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ session }),
      });
      if (res.ok) {
        pushStatus(`Killed session: ${session}`);
        setTimeout(fetchScreens, 500);
        if (selectedSession === session) {
          setSelectedSession("");
          setLogState(createLogState());
        }
      } else {
        pushError("Failed to kill session");
      }
    } catch (e) {
      pushError(`Error: ${e.message}`);
    }
  };

  const fetchLogs = useCallback(
    async (session) => {
      if (!session) return;
      try {
        const res = await fetch(
          `${API}/ros2/screens/logs/${encodeURIComponent(session)}?lines=${logLines}`
        );
        if (res.ok) {
          const data = await res.json();
          setLogState({
            text: data.log_text || data.text || "",
            session: data.session || session,
            updatedAt: data.updated_at || new Date().toISOString(),
            startedAt: data.started_at || null,
            autoRestart: data.auto_restart || false,
            lines: data.line_count || data.lines || 0,
          });
          // Auto-scroll to bottom
          if (logViewerRef.current) {
            setTimeout(() => {
              logViewerRef.current.scrollTop = logViewerRef.current.scrollHeight;
            }, 50);
          }
        }
      } catch (err) {
        console.error("Failed to fetch logs", err);
      }
    },
    [logLines]
  );

  const selectSession = (session) => {
    setSelectedSession(session);
    fetchLogs(session);
  };

  // Script CRUD
  const saveScript = async () => {
    const payload = {
      name: scriptForm.name,
      command: scriptForm.command,
      session: scriptForm.session || undefined,
      working_dir: scriptForm.working_dir || undefined,
      auto_restart: scriptForm.auto_restart,
      description: scriptForm.description || undefined,
      tags: toTagArray(scriptForm.tags),
    };
    if (!payload.name || !payload.command) {
      pushError("Name and Command are required");
      return;
    }
    try {
      const res = await fetch(`${API}/ros2/scripts`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      if (res.ok) {
        pushStatus(`Script "${payload.name}" saved`);
        setShowScriptForm(false);
        setScriptForm({ ...emptyScriptForm });
        fetchScripts();
      } else {
        const err = await res.json();
        pushError(`Failed: ${err.detail}`);
      }
    } catch (e) {
      pushError(`Error: ${e.message}`);
    }
  };

  const deleteScript = async (name) => {
    if (!confirm(`Delete script "${name}"?`)) return;
    try {
      const res = await fetch(`${API}/ros2/scripts/${encodeURIComponent(name)}`, {
        method: "DELETE",
      });
      if (res.ok) {
        pushStatus(`Script "${name}" deleted`);
        fetchScripts();
      } else {
        pushError("Failed to delete script");
      }
    } catch (e) {
      pushError(`Error: ${e.message}`);
    }
  };

  const editScript = (script) => {
    setScriptForm({
      name: script.name || "",
      session: script.session || "",
      command: script.command || "",
      working_dir: script.working_dir || script.workingDir || "",
      auto_restart: script.auto_restart || script.autoRestart || false,
      description: script.description || "",
      tags: toTagString(script.tags),
    });
    setShowScriptForm(true);
  };

  // =======================================================================
  // MicroROS Agent SSH Functions
  // =======================================================================

  const fetchMicrorosStatus = useCallback(async () => {
    try {
      const response = await fetch(`${API}/ssh/microros/devices`);
      if (response.ok) {
        const data = await response.json();
        setMicrorosDevices(Array.isArray(data.devices) ? data.devices : []);
      }
    } catch (err) {
      console.error("Failed to fetch MicroROS status", err);
    }
  }, []);

  const startMicrorosAgent = async (device) => {
    try {
      const response = await fetch(`${API}/ssh/microros/start`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ device_id: device.device_id }),
      });
      if (response.ok) {
        pushStatus(`Starting MicroROS agent for ${device.display_name}...`);
        setTimeout(fetchMicrorosStatus, 1000);
      } else {
        const err = await response.json();
        pushError(`Failed to start agent: ${err.detail}`);
      }
    } catch (e) {
      pushError(`Error starting agent: ${e.message}`);
    }
  };

  const stopMicrorosAgent = async (device) => {
    try {
      const response = await fetch(`${API}/ssh/microros/stop`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ device_id: device.device_id }),
      });
      if (response.ok) {
        pushStatus(`Stopped MicroROS agent for ${device.display_name}`);
        setTimeout(fetchMicrorosStatus, 1000);
      } else {
        pushError("Failed to stop agent");
      }
    } catch (e) {
      pushError(`Error stopping agent: ${e.message}`);
    }
  };

  const openMicrorosLog = (device) => {
    window.open(`/microros-logs?session=${encodeURIComponent(device.session)}`, "_blank");
  };

  // =======================================================================
  // Lifecycle & Polling
  // =======================================================================

  useEffect(() => {
    fetchMicrorosStatus();
    fetchScreens();
    fetchScripts();
  }, [fetchMicrorosStatus, fetchScreens, fetchScripts]);

  // Auto-refresh screens
  useEffect(() => {
    if (!autoRefreshScreens) return;
    const id = setInterval(fetchScreens, 5000);
    return () => clearInterval(id);
  }, [autoRefreshScreens, fetchScreens]);

  // Auto-refresh logs
  useEffect(() => {
    if (!autoRefreshLogs || !selectedSession) return;
    const id = setInterval(() => fetchLogs(selectedSession), 3000);
    return () => clearInterval(id);
  }, [autoRefreshLogs, selectedSession, fetchLogs]);

  // =======================================================================
  // Render
  // =======================================================================

  return (
    <div className="status-jetson">
      {/* Status Messages */}
      {statusMessage && (
        <div className="sj-status ok">{statusMessage}</div>
      )}
      {errorMessage && (
        <div className="sj-status error">{errorMessage}</div>
      )}

      {/* Action Dashboard (moved from Science) */}
      <section className="status-panel">
        <ScienceDashboard instanceName="jetson" />
      </section>

      {/* MicroROS Agent SSH Section */}
      <section className="status-panel microros-panel">
        <div className="panel-header">
          <h3>🤖 MicroROS Agents (Robot SSH)</h3>
          <div className="panel-controls">
            <button type="button" onClick={fetchMicrorosStatus}>
              Refresh
            </button>
          </div>
        </div>

        <div className="microros-grid">
          {microrosDevices.map((device) => (
            <div
              key={device.device_id}
              className={`microros-card ${device.running ? "running" : ""}`}
            >
              <div className="card-header">
                <h4>{device.display_name}</h4>
              </div>
              <div style={{ fontSize: "0.8rem", color: "#888", marginBottom: 8 }}>
                <div>{device.tty_device}</div>
                <div title={device.device_id}>{device.device_id}</div>
              </div>
              <div className="card-controls">
                <button
                  className="success"
                  onClick={() => startMicrorosAgent(device)}
                  disabled={device.running}
                >
                  ON
                </button>
                <button
                  className="danger"
                  onClick={() => stopMicrorosAgent(device)}
                  disabled={!device.running}
                >
                  OFF
                </button>
                <button onClick={() => openMicrorosLog(device)}>LOGS</button>
              </div>
            </div>
          ))}
          {microrosDevices.length === 0 && (
            <p className="empty" style={{ gridColumn: "1 / -1" }}>
              No STM32 devices detected on robot (/dev/serial/by-id).
            </p>
          )}
        </div>
      </section>

      {/* Active Screens Section */}
      <section className="status-panel">
        <div className="panel-header">
          <h3>🖥️ Active Screens</h3>
          <div className="panel-controls">
            <label>
              <input
                type="checkbox"
                checked={autoRefreshScreens}
                onChange={(e) => setAutoRefreshScreens(e.target.checked)}
              />
              Auto-refresh
            </label>
            <button type="button" onClick={fetchScreens}>
              Refresh
            </button>
          </div>
        </div>

        {screens.length === 0 ? (
          <p className="empty">No active screen sessions</p>
        ) : (
          <ul className="screen-list">
            {screens.map((scr) => (
              <li
                key={scr.session || scr.name}
                className={`screen-item ${selectedSession === (scr.session || scr.name) ? "active" : ""}`}
              >
                <div className="screen-title">
                  <strong>{scr.session || scr.name}</strong>
                  {scr.source_script && (
                    <span className="tag" style={{ marginLeft: 8 }}>
                      {scr.source_script}
                    </span>
                  )}
                </div>
                {scr.started_at && (
                  <div className="screen-meta">
                    <span>Started: {scr.started_at}</span>
                    {scr.auto_restart && <span className="tag">auto-restart</span>}
                  </div>
                )}
                <div className="screen-actions">
                  <button
                    onClick={() => selectSession(scr.session || scr.name)}
                  >
                    View Logs
                  </button>
                  <button
                    className="danger"
                    onClick={() => killScreen(scr.session || scr.name)}
                  >
                    Kill
                  </button>
                </div>
              </li>
            ))}
          </ul>
        )}

        {/* Quick Run */}
        <div className="quick-tools">
          <h4 style={{ margin: "8px 0 4px" }}>Quick Run</h4>
          <div className="quick-actions">
            <input
              placeholder="Command..."
              value={customCommand}
              onChange={(e) => setCustomCommand(e.target.value)}
              style={{ flex: 1 }}
            />
            <input
              placeholder="Session name (optional)"
              value={customSession}
              onChange={(e) => setCustomSession(e.target.value)}
              style={{ width: 180 }}
            />
            <label style={{ display: "flex", alignItems: "center", gap: 4, fontSize: "0.85rem" }}>
              <input
                type="checkbox"
                checked={customAutoRestart}
                onChange={(e) => setCustomAutoRestart(e.target.checked)}
              />
              Auto-restart
            </label>
            <button onClick={runCustomCommand}>Run</button>
          </div>
        </div>
      </section>

      {/* Log Viewer */}
      {selectedSession && (
        <section className="status-panel">
          <div className="panel-header">
            <h3>📋 Logs: {selectedSession}</h3>
            <div className="panel-controls">
              <label>
                <input
                  type="checkbox"
                  checked={autoRefreshLogs}
                  onChange={(e) => setAutoRefreshLogs(e.target.checked)}
                />
                Auto-refresh
              </label>
              <label>
                Lines:
                <select
                  value={logLines}
                  onChange={(e) => {
                    setLogLines(Number(e.target.value));
                    fetchLogs(selectedSession);
                  }}
                  style={{ marginLeft: 4 }}
                >
                  <option value={50}>50</option>
                  <option value={100}>100</option>
                  <option value={200}>200</option>
                  <option value={500}>500</option>
                  <option value={1000}>1000</option>
                </select>
              </label>
              <button type="button" onClick={() => fetchLogs(selectedSession)}>
                Refresh
              </button>
              <button
                className="danger"
                onClick={() => {
                  setSelectedSession("");
                  setLogState(createLogState());
                }}
              >
                Close
              </button>
            </div>
          </div>
          <div className="log-meta">
            <span>Lines: {logState.lines}</span>
            {logState.updatedAt && <span>Updated: {logState.updatedAt}</span>}
            {logState.autoRestart && <span className="tag">auto-restart</span>}
          </div>
          <pre className="log-viewer" ref={logViewerRef}>
            {logState.text || "No logs yet..."}
          </pre>
        </section>
      )}

      {/* Scripts Section */}
      <section className="status-panel">
        <div className="panel-header">
          <h3>📝 Scripts</h3>
          <div className="panel-controls">
            <button type="button" onClick={fetchScripts}>
              Refresh
            </button>
            <button
              type="button"
              onClick={() => {
                setScriptForm({ ...emptyScriptForm });
                setShowScriptForm((prev) => !prev);
              }}
            >
              {showScriptForm ? "Cancel" : "+ New Script"}
            </button>
          </div>
        </div>

        {/* Script Form */}
        {showScriptForm && (
          <div className="script-form">
            <label>
              Name *
              <input
                value={scriptForm.name}
                onChange={(e) =>
                  setScriptForm({ ...scriptForm, name: e.target.value })
                }
                placeholder="e.g. navigation_bringup"
              />
            </label>
            <label>
              Command *
              <textarea
                value={scriptForm.command}
                onChange={(e) =>
                  setScriptForm({ ...scriptForm, command: e.target.value })
                }
                placeholder="e.g. ros2 launch nav_bringup bringup_launch.py"
              />
            </label>
            <label>
              Session Name
              <input
                value={scriptForm.session}
                onChange={(e) =>
                  setScriptForm({ ...scriptForm, session: e.target.value })
                }
                placeholder="(auto-generated if empty)"
              />
            </label>
            <label>
              Working Directory
              <input
                value={scriptForm.working_dir}
                onChange={(e) =>
                  setScriptForm({ ...scriptForm, working_dir: e.target.value })
                }
                placeholder="(optional)"
              />
            </label>
            <label>
              Description
              <input
                value={scriptForm.description}
                onChange={(e) =>
                  setScriptForm({ ...scriptForm, description: e.target.value })
                }
                placeholder="(optional)"
              />
            </label>
            <label>
              Tags (comma-separated)
              <input
                value={scriptForm.tags}
                onChange={(e) =>
                  setScriptForm({ ...scriptForm, tags: e.target.value })
                }
                placeholder="e.g. launch, nav"
              />
            </label>
            <div className="checkbox-field">
              <input
                type="checkbox"
                checked={scriptForm.auto_restart}
                onChange={(e) =>
                  setScriptForm({ ...scriptForm, auto_restart: e.target.checked })
                }
              />
              Auto-restart on crash
            </div>
            <div className="form-actions">
              <button onClick={saveScript}>Save Script</button>
              <button
                className="danger"
                onClick={() => {
                  setShowScriptForm(false);
                  setScriptForm({ ...emptyScriptForm });
                }}
              >
                Cancel
              </button>
            </div>
          </div>
        )}

        {/* Script List */}
        {scripts.length === 0 && !showScriptForm ? (
          <p className="empty">No scripts configured</p>
        ) : (
          <ul className="script-list">
            {scripts.map((script) => (
              <li key={script.name} className="script-item">
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start" }}>
                  <div>
                    <strong>{script.name}</strong>
                    {script.description && (
                      <div style={{ fontSize: "0.85em", color: "#666", marginTop: 2 }}>
                        {script.description}
                      </div>
                    )}
                  </div>
                  <div style={{ display: "flex", gap: 4 }}>
                    {toTagArray(script.tags).map((tag) => (
                      <span key={tag} className="tag">
                        {tag}
                      </span>
                    ))}
                  </div>
                </div>
                <div className="script-meta">
                  <span>
                    <code>{script.command}</code>
                  </span>
                  {script.session && <span>Session: {script.session}</span>}
                  {(script.auto_restart || script.autoRestart) && (
                    <span className="tag">auto-restart</span>
                  )}
                </div>
                <div className="script-actions">
                  <button onClick={() => runScript(script.name)}>▶ Run</button>
                  <button className="secondary" onClick={() => editScript(script)}>
                    Edit
                  </button>
                  <button
                    className="danger"
                    onClick={() => deleteScript(script.name)}
                  >
                    Delete
                  </button>
                </div>
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
};
