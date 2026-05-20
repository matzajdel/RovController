import React from "react";

const ControlModeButtons = ({ controlMode, onControlModeChange, onEmergencyStop }) => (
  <div className="control-modes">
    <button
      className={`control-btn ${controlMode === "off" ? "active" : ""}`}
      onClick={() => onControlModeChange("off")}
    >
      Off
    </button>
    <button
      className={`control-btn ${controlMode === "joystick" ? "active" : ""}`}
      onClick={() => onControlModeChange("joystick")}
    >
      Joystick
    </button>
    <button
      className={`control-btn ${controlMode === "steering_new" ? "active" : ""}`}
      onClick={() => onControlModeChange("steering_new")}
    >
      🎮 Sterowanie
    </button>
    <button className="emergency-stop-btn" onClick={onEmergencyStop}>
      EMERGENCY STOP
    </button>
  </div>
);

export default ControlModeButtons;