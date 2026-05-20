import React from "react";

const SpeedControl = ({ speed, onSpeedChange }) => (
  <div className="speed-control">
    <label>
      Speed: {speed.toFixed(2)}
      <input
        type="range"
        min="0"
        max="4"
        step="0.05"
        value={speed}
        onChange={(e) => onSpeedChange(Number(e.target.value))}
      />
    </label>
  </div>
);

export default SpeedControl;