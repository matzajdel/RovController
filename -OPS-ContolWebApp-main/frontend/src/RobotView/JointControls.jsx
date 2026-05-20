import { useState } from 'react';

/**
 * Joint angle sliders for manual manipulator and steering control.
 *
 * Two sections:
 *   🤖 Manipulator — 6-DOF arm joints
 *   🚗 Wheel Steering — 4 independent crab-drive yaw joints
 */
export function JointControls({ jointStates, onJointChange, disabled }) {
  // ── Manipulator joints ──
  const armJoints = [
    { name: 'joint_base', label: 'Base Rotation', min: -3.14, max: 3.14, step: 0.01 },
    { name: 'joint_shoulder', label: 'Shoulder', min: -1.57, max: 1.57, step: 0.01 },
    { name: 'joint_elbow', label: 'Elbow', min: -2.0, max: 2.0, step: 0.01 },
    { name: 'joint_wrist_pitch', label: 'Wrist Pitch', min: -1.57, max: 1.57, step: 0.01 },
    { name: 'joint_wrist_roll', label: 'Wrist Roll', min: -3.14, max: 3.14, step: 0.01 },
    { name: 'joint_gripper', label: 'Gripper', min: 0.0, max: 0.08, step: 0.001 },
  ];

  // ── Crab-drive steering joints ──
  const steerJoints = [
    { name: 'steer_front_left', label: 'FL Steer', min: -1.57, max: 1.57, step: 0.01 },
    { name: 'steer_front_right', label: 'FR Steer', min: -1.57, max: 1.57, step: 0.01 },
    { name: 'steer_rear_left', label: 'RL Steer', min: -1.57, max: 1.57, step: 0.01 },
    { name: 'steer_rear_right', label: 'RR Steer', min: -1.57, max: 1.57, step: 0.01 },
  ];

  // ── Crab preset: all wheels same angle ──
  const [crabAngle, setCrabAngle] = useState(0);

  const handleChange = (jointName, value) => {
    const numValue = parseFloat(value);
    onJointChange(jointName, numValue);
  };

  const handleCrabChange = (value) => {
    const angle = parseFloat(value);
    setCrabAngle(angle);
    steerJoints.forEach(j => onJointChange(j.name, angle));
  };

  const renderSlider = (joint) => {
    const currentValue = jointStates[joint.name] || 0;
    return (
      <div key={joint.name} className="joint-slider">
        <label>
          <span className="joint-name">{joint.label}</span>
          <span className="joint-value">
            {currentValue.toFixed(joint.name === 'joint_gripper' ? 3 : 2)} rad
          </span>
        </label>
        <input
          type="range"
          min={joint.min}
          max={joint.max}
          step={joint.step}
          value={currentValue}
          onChange={(e) => handleChange(joint.name, e.target.value)}
          disabled={disabled}
        />
        <div className="joint-limits">
          <span style={{ fontSize: '0.7rem', color: '#888' }}>
            {joint.min.toFixed(2)}
          </span>
          <span style={{ fontSize: '0.7rem', color: '#888' }}>
            {joint.max.toFixed(2)}
          </span>
        </div>
      </div>
    );
  };

  return (
    <div className="joint-controls">
      {/* ── Arm joints ── */}
      {armJoints.map(renderSlider)}

      {/* ── Steering section ── */}
      <div style={{ marginTop: '1rem', paddingTop: '1rem', borderTop: '1px solid rgba(78, 205, 196, 0.2)' }}>
        <h4 style={{ fontSize: '0.9rem', color: '#4ecdc4', marginBottom: '0.5rem' }}>
          🚗 Wheel Steering (Crab Drive)
        </h4>

        {/* Crab master slider — moves all 4 wheels together */}
        <div className="joint-slider" style={{ marginBottom: '0.75rem' }}>
          <label>
            <span className="joint-name" style={{ color: '#ff6b6b' }}>🦀 All Wheels</span>
            <span className="joint-value">{crabAngle.toFixed(2)} rad</span>
          </label>
          <input
            type="range"
            min={-1.57}
            max={1.57}
            step={0.01}
            value={crabAngle}
            onChange={(e) => handleCrabChange(e.target.value)}
            disabled={disabled}
            style={{ accentColor: '#ff6b6b' }}
          />
        </div>

        {/* Individual wheel sliders */}
        {steerJoints.map(renderSlider)}
      </div>

      {/* IK Control Section (future enhancement) */}
      <div className="ik-section" style={{ marginTop: '1rem', paddingTop: '1rem', borderTop: '1px solid rgba(78, 205, 196, 0.2)' }}>
        <h4 style={{ fontSize: '0.9rem', color: '#4ecdc4', marginBottom: '0.5rem' }}>
          🎯 IK Control (Coming Soon)
        </h4>
        <p style={{ fontSize: '0.75rem', color: '#888', margin: 0 }}>
          Click in 3D view to move end-effector
        </p>
      </div>
    </div>
  );
}
