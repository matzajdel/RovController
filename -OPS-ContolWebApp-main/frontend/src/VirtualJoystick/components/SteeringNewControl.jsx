/**
 * Sterowanie Nowe — Advanced Steering Control
 * Now fully powered by SteeringContext.
 * 
 * Features:
 * - 4 Drive Modes: PROSTY, SKRĘT, OBRÓT, FREESTYLE
 * - Motor Mode: PID/PWM toggle
 * - Speed/Turn limits
 * - RGB LED control with presets
 * - Manipulator control (6 DOF)
 * - Topic selection (cmd_vel, cmd_vel_nav, custom)
 * - Gamepad selection & axis/button mapping
 * - Emergency Stop
 */
import React, { useState, useEffect, useCallback } from "react";
import { useSteering } from "../../context/SteeringContext";
import { BACKEND_CONFIG } from "../../config";
import "./SteeringNewControl.css";

// ── Sub-component: GamepadList ──────────────────────────────────────────
// Shows all browser-detected gamepads and lets user pick one
const GamepadList = ({ backendUrl, gamepadInfo }) => {
  const [browserPads, setBrowserPads] = useState([]);

  useEffect(() => {
    const scan = () => {
      const pads = navigator.getGamepads ? navigator.getGamepads() : [];
      const found = [];
      for (let i = 0; i < pads.length; i++) {
        if (pads[i] && pads[i].connected) {
          found.push({ index: i, id: pads[i].id });
        }
      }
      setBrowserPads(found);
    };
    scan();
    const interval = setInterval(scan, 2000);
    return () => clearInterval(interval);
  }, []);

  const handleSelect = useCallback(async (index, id) => {
    try {
      await fetch(`${backendUrl}/gamepads/select`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ index, gamepad_id: id }),
      });
    } catch (e) {
      console.error("[GamepadList] Error selecting pad:", e);
    }
  }, [backendUrl]);

  if (browserPads.length === 0) return null;

  return (
    <div className="gamepad-list">
      <p className="gamepad-list-label">Wykryte gamepady:</p>
      {browserPads.map((pad) => (
        <button
          key={pad.index}
          className={`gamepad-list-btn ${gamepadInfo.index === pad.index ? "selected" : ""}`}
          onClick={() => handleSelect(pad.index, pad.id)}
          title={pad.id}
        >
          🎮 #{pad.index}: {pad.id.substring(0, 30)}{pad.id.length > 30 ? "…" : ""}
        </button>
      ))}
    </div>
  );
};

// ── Sub-component: GamepadMappingPanel ───────────────────────────────────
// Collapsible axis/button mapping configuration
const AVAILABLE_BUTTONS = [
  { value: 0, label: "A / Krzyżyk (0)" },
  { value: 1, label: "B / Kółko (1)" },
  { value: 2, label: "X / Kwadrat (2)" },
  { value: 3, label: "Y / Trójkąt (3)" },
  { value: 4, label: "LB / L1 (4)" },
  { value: 5, label: "RB / R1 (5)" },
  { value: 6, label: "LT / L2 (6)" },
  { value: 7, label: "RT / R2 (7)" },
  { value: 8, label: "Back / Select (8)" },
  { value: 9, label: "Start (9)" },
  { value: 10, label: "L3 (10)" },
  { value: 11, label: "R3 (11)" },
  { value: 12, label: "D-Pad Góra (12)" },
  { value: 13, label: "D-Pad Dół (13)" },
  { value: 14, label: "D-Pad Lewo (14)" },
  { value: 15, label: "D-Pad Prawo (15)" },
];

const GamepadMappingPanel = ({ backendUrl }) => {
  const [config, setConfig] = useState(null);

  useEffect(() => {
    fetch(`${backendUrl}/get_gamepad_config`)
      .then(res => res.json())
      .then(data => { if (data && data.mapping) setConfig(data); })
      .catch(() => { });
  }, [backendUrl]);

  const update = useCallback(async (field, value) => {
    const newConfig = {
      ...config,
      mapping: { ...config.mapping, [field]: value },
    };
    setConfig(newConfig);
    try {
      await fetch(`${backendUrl}/save_gamepad_config`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(newConfig),
      });
    } catch (e) {
      console.error("[GamepadMapping] Save error:", e);
    }
  }, [config, backendUrl]);

  if (!config || !config.mapping) {
    return <p className="mapping-loading">Ładowanie konfiguracji...</p>;
  }

  const renderSelect = (label, fieldKey, options) => (
    <div className="mapping-row" key={fieldKey}>
      <label>{label}</label>
      <select value={config.mapping[fieldKey] ?? 0} onChange={(e) => update(fieldKey, parseInt(e.target.value))}>
        {options.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
      </select>
    </div>
  );

  const renderButtonSelect = (label, fieldKey) => renderSelect(label, fieldKey, AVAILABLE_BUTTONS);

  return (
    <div className="mapping-panel">
      <div className="mapping-group">
        <h4>Drążki</h4>
        {renderSelect("Jazda (pion)", "linearAxis", [
          { value: 1, label: "Lewy Analog Y (1)" },
          { value: 3, label: "Prawy Analog Y (3)" },
        ])}
        {renderSelect("Skręt (poziom)", "angularAxis", [
          { value: 0, label: "Lewy Analog X (0)" },
          { value: 2, label: "Prawy Analog X (2)" },
        ])}
      </div>
      <div className="mapping-group">
        <h4>Przyciski</h4>
        {renderButtonSelect("Przycisk A", "btnA")}
        {renderButtonSelect("Przycisk B", "btnB")}
        {renderButtonSelect("Przycisk X", "btnX")}
        {renderButtonSelect("Przycisk Y", "btnY")}
        {renderButtonSelect("LB", "btnLB")}
        {renderButtonSelect("RB", "btnRB")}
      </div>
      <div className="mapping-group">
        <h4>D-Pad</h4>
        {renderButtonSelect("↑ Góra", "dpadUp")}
        {renderButtonSelect("↓ Dół", "dpadDown")}
        {renderButtonSelect("← Lewo", "dpadLeft")}
        {renderButtonSelect("→ Prawo", "dpadRight")}
      </div>
      <p className="mapping-hint">Zmiany zapisywane automatycznie.</p>
    </div>
  );
};

// Backend przyjmuje standardową kolejność R, G, B
const RGB_PRESETS = [
  { name: "Czerwony", r: 200, g: 0, b: 0, color: "#FF0000", textColor: "white" },
  { name: "Zielony", r: 0, g: 200, b: 0, color: "#00FF00", textColor: "black" },
  { name: "Niebieski", r: 0, g: 0, b: 200, color: "#0000FF", textColor: "white" },
  { name: "Żółty", r: 200, g: 200, b: 0, color: "#FFFF00", textColor: "black" },
  { name: "Cyjan", r: 0, g: 200, b: 200, color: "#00FFFF", textColor: "black" },
  { name: "Magenta", r: 200, g: 0, b: 200, color: "#FF00FF", textColor: "white" },
  { name: "Biały", r: 200, g: 200, b: 200, color: "#FFFFFF", textColor: "black" },
];

const MANIPULATOR_DEGREES = [
  "Podstawa",
  "Ramię (dół)",
  "Ramię (góra)",
  "Nadgarstek",
  "Chwytak obrót",
  "Chwytak zacisk",
];

const SteeringNewControl = () => {
  const {
    driveMode, setDriveMode,
    motorMode, toggleMotorMode,
    maxSpeed, setMaxSpeed,
    maxTurn, setMaxTurn,
    rgb, setRgbChannel, applyRgbPreset, turnOffRgb,
    manipSensitivities, setManipSensitivity, setGlobalSensitivity,
    manipValues,
    targetTopic, setTargetTopic, availableTopics,
    gamepadInfo,
    speed,
    emergencyStop,
    auxStickEnabled, setAuxStickEnabled,
    DRIVE_MODES,
  } = useSteering();

  const backendUrl = BACKEND_CONFIG.BACKEND_URL;

  // Custom topic input
  const [customTopic, setCustomTopic] = useState("");
  const [showCustomInput, setShowCustomInput] = useState(false);

  // Reverse mode from RB button (local polling — visual-only)
  const [reverseMode, setReverseMode] = useState(false);

  useEffect(() => {
    if (!gamepadInfo.connected) return;
    const checkGamepad = () => {
      const gamepad = navigator.getGamepads()[gamepadInfo.index];
      if (!gamepad) return;
      const rbPressed = gamepad.buttons[5]?.pressed || false;
      if (driveMode === DRIVE_MODES.PROSTY.id || driveMode === DRIVE_MODES.SKRET.id) {
        setReverseMode(rbPressed);
      }
    };
    const interval = setInterval(checkGamepad, 50);
    return () => clearInterval(interval);
  }, [gamepadInfo, driveMode]);

  const handleTopicChange = (e) => {
    const val = e.target.value;
    if (val === "__custom__") {
      setShowCustomInput(true);
    } else {
      setShowCustomInput(false);
      setTargetTopic(val);
    }
  };

  const applyCustomTopic = () => {
    if (customTopic.trim()) {
      setTargetTopic(customTopic.trim());
      setShowCustomInput(false);
    }
  };

  return (
    <div className="steering-new-container">
      <h2 className="steering-title">🎮 Sterowanie NOWE</h2>

      {/* Emergency Stop */}
      <button className="emergency-stop-btn-steering" onClick={emergencyStop}>
        🛑 EMERGENCY STOP
      </button>

      {/* Two Column Layout */}
      <div className="steering-columns">
        {/* LEFT COLUMN */}
        <div className="steering-column">
          {/* Gamepad Selection & Config */}
          <div className="steering-section gamepad-config-section">
            <h3>🎮 Gamepad</h3>

            {/* Current status */}
            <div className="gamepad-status-row">
              <span className={gamepadInfo.connected ? "status-connected" : "status-disconnected"}>
                {gamepadInfo.connected ? `✓ ${gamepadInfo.name}` : "✗ Brak gamepada — naciśnij przycisk na padzie"}
              </span>
            </div>

            {/* Browser-detected gamepads list */}
            <GamepadList backendUrl={backendUrl} gamepadInfo={gamepadInfo} />

            {/* Axis/button mapping (collapsible) */}
            <details className="gamepad-mapping-details">
              <summary>⚙️ Mapowanie osi i przycisków</summary>
              <GamepadMappingPanel backendUrl={backendUrl} />
            </details>

            {/* Left stick → servo toggle */}
            <div className="aux-stick-toggle">
              <button
                className={`motor-mode-btn ${auxStickEnabled ? 'pid-mode' : 'pwm-mode'}`}
                onClick={() => setAuxStickEnabled(!auxStickEnabled)}
                title="Enable/disable left stick control of serwoUART and /Serwa"
              >
                {auxStickEnabled ? '🎮 Left Stick Servo: ON' : '🚫 Left Stick Servo: OFF'}
              </button>
            </div>
          </div>

          {/* Drive Mode Selection */}
          <div className="steering-section">
            <h3>Tryby Jazdy</h3>
            <div className="mode-buttons">
              {Object.values(DRIVE_MODES).map((mode) => (
                <button
                  key={mode.id}
                  className={`mode-btn ${driveMode === mode.id ? 'active' : ''}`}
                  onClick={() => setDriveMode(mode.id)}
                  title={mode.desc}
                >
                  {mode.name}
                </button>
              ))}
            </div>
            <p className="mode-description">
              {Object.values(DRIVE_MODES).find(m => m.id === driveMode)?.desc}
            </p>
          </div>

          {/* Motor Control Mode */}
          <div className="steering-section">
            <h3>Tryb Silników</h3>
            <button
              className={`motor-mode-btn ${motorMode === 1 ? 'pwm-mode' : 'pid-mode'}`}
              onClick={toggleMotorMode}
            >
              {motorMode === 0 ? "PWM SERIO" : "PID 100%"}
            </button>
          </div>

          {/* Speed Controls */}
          <div className="steering-section">
            <h3>Limity Prędkości</h3>
            <div className="control-row">
              <label>Max Prędkość: {maxSpeed.toFixed(2)} m/s</label>
              <input type="range" min="0" max="3" step="0.1" value={maxSpeed}
                onChange={(e) => setMaxSpeed(parseFloat(e.target.value))} />
            </div>
            <div className="control-row">
              <label>Max Obrót: {maxTurn.toFixed(3)} rad/s</label>
              <input type="range" min="0" max="3" step="0.1" value={maxTurn}
                onChange={(e) => setMaxTurn(parseFloat(e.target.value))} />
            </div>
          </div>

          {/* ── Topic Selection ── */}
          <div className="steering-section topic-section">
            <h3>📡 Topic docelowy</h3>
            <div className="topic-selector">
              <select
                value={showCustomInput ? "__custom__" : targetTopic}
                onChange={handleTopicChange}
                className="topic-select"
              >
                {availableTopics.map(t => (
                  <option key={t} value={t}>/{t}</option>
                ))}
                {/* Show current topic even if not in defaults */}
                {!availableTopics.includes(targetTopic) && !showCustomInput && (
                  <option value={targetTopic}>/{targetTopic}</option>
                )}
                <option value="__custom__">✏️ Własny...</option>
              </select>
              {showCustomInput && (
                <div className="custom-topic-input">
                  <input
                    type="text"
                    placeholder="np. cmd_vel_nav"
                    value={customTopic}
                    onChange={(e) => setCustomTopic(e.target.value)}
                    onKeyDown={(e) => e.key === "Enter" && applyCustomTopic()}
                  />
                  <button onClick={applyCustomTopic}>OK</button>
                </div>
              )}
            </div>
            <p className="topic-current">Aktywny: <strong>/{targetTopic}</strong></p>
          </div>

          {/* RGB Control */}
          <div className="steering-section rgb-section">
            <h3>🌈 RGB Control</h3>
            <div className="rgb-sliders">
              <div className="rgb-slider-row red">
                <label>R: {rgb.r}</label>
                <input type="range" min="0" max="255" value={rgb.r}
                  onChange={(e) => setRgbChannel('r', parseInt(e.target.value))} />
              </div>
              <div className="rgb-slider-row green">
                <label>G: {rgb.g}</label>
                <input type="range" min="0" max="255" value={rgb.g}
                  onChange={(e) => setRgbChannel('g', parseInt(e.target.value))} />
              </div>
              <div className="rgb-slider-row blue">
                <label>B: {rgb.b}</label>
                <input type="range" min="0" max="255" value={rgb.b}
                  onChange={(e) => setRgbChannel('b', parseInt(e.target.value))} />
              </div>
            </div>
            <div className="rgb-presets">
              {RGB_PRESETS.map((preset) => (
                <button
                  key={preset.name}
                  className="rgb-preset-btn"
                  style={{ backgroundColor: preset.color, color: preset.textColor }}
                  onClick={() => applyRgbPreset(preset)}
                  title={preset.name}
                >
                  {preset.name}
                </button>
              ))}
              <button className="rgb-preset-btn off" onClick={turnOffRgb}>
                Wyłącz
              </button>
            </div>
          </div>
        </div>

        {/* RIGHT COLUMN */}
        <div className="steering-column">
          {/* Manipulator Control */}
          <div className="steering-section manipulator-section">
            <h3>🦾 Sterowanie Manipulatorem</h3>
            <div className="manip-global">
              <label>Globalna czułość: {manipSensitivities[0]}</label>
              <input type="range" min="1" max="100" value={manipSensitivities[0]}
                onChange={(e) => setGlobalSensitivity(parseInt(e.target.value))} />
            </div>
            <div className="manip-degrees">
              {MANIPULATOR_DEGREES.map((name, idx) => (
                <div key={idx} className="manip-degree-row">
                  <span className="manip-name">{name}</span>
                  <span className="manip-value">{manipValues[idx].toFixed(1)}</span>
                  <input type="range" min="1" max="100" value={manipSensitivities[idx]}
                    onChange={(e) => setManipSensitivity(idx, parseInt(e.target.value))}
                    title={`Czułość: ${manipSensitivities[idx]}`} />
                </div>
              ))}
            </div>
          </div>

          {/* Instructions */}
          <div className="steering-section instructions-section">
            <h3>📖 Instrukcja</h3>
            <div className="instruction-list">
              <div className="instruction-item"><span className="key">RT</span><span>Gaz (przytrzymaj aby jechać)</span></div>
              <div className="instruction-item"><span className="key">RB</span><span>Odwrócenie kierunku (PROSTY/SKRĘT)</span></div>
              <div className="instruction-item"><span className="key">Prawa gałka</span><span>Kierunek jazdy</span></div>
              <div className="instruction-item"><span className="key">A / B</span><span>Podstawa +/−</span></div>
              <div className="instruction-item"><span className="key">X / Y</span><span>Chwytak obrót +/−</span></div>
              <div className="instruction-item"><span className="key">D-pad ↑↓</span><span>Ramię dół −/+</span></div>
              <div className="instruction-item"><span className="key">D-pad ←→</span><span>Ramię góra +/−</span></div>
              <div className="instruction-item"><span className="key">Back / Start</span><span>Chwytak zacisk −/+</span></div>
              <div className="instruction-item"><span className="key">L3 / R3</span><span>Nadgarstek +/−</span></div>
            </div>
          </div>

          {/* Info Box */}
          <div className="steering-section info-box">
            <p>Tryb: <strong>{Object.values(DRIVE_MODES).find(m => m.id === driveMode)?.name}</strong></p>
            <p>Silniki: <strong>{motorMode === 0 ? "PID" : "PWM"}</strong></p>
            <p>Prędkość globalna: <strong>{speed.toFixed(2)}</strong></p>
            <p>Topic: <strong>/{targetTopic}</strong></p>
            {(driveMode === DRIVE_MODES.PROSTY.id || driveMode === DRIVE_MODES.SKRET.id) && (
              <p>Reverse: <strong className={reverseMode ? "reverse-active" : "reverse-inactive"}>
                {reverseMode ? "AKTYWNY (RB)" : "NIE"}
              </strong></p>
            )}
          </div>
        </div>
      </div>
    </div>
  );
};

export default SteeringNewControl;
