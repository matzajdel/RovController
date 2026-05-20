/**
 * Virtual Joystick Control Interface
 * 
 * Main control page with 3 modes: Off, Joystick, Sterowanie.
 * Uses SteeringContext for shared state (gamepad bridge persists across pages).
 */
import React, { useState, useEffect } from "react";
import { useSteering } from "../context/SteeringContext";

import ControlModeButtons from "./components/ControlModeButtons";
import SpeedControl from "./components/SpeedControl";
import JoystickContainer from "./components/JoystickContainer";
import GamepadDiagnostics from "./components/GamepadDiagnostics";
import SteeringNewControl from "./components/SteeringNewControl";

import { useWebSocket } from "./hooks/useWebSocket";
import { useLedControl } from "./hooks/useLedControl";
import { useArrayTopicButtons } from './hooks/useArrayTopicButtons.js';
import { useArrowKeys } from './hooks/useArrowKeys.js';
import { useCustomTopics } from './hooks/useCustomTopics.js';
import { BACKEND_CONFIG } from "./Constants.js";
import CustomTopicButtons from "./components/CustomTopicButtons";
import "./VirtualJoystick.css";

function VirtualJoystick() {
  const {
    controlMode, setControlMode,
    gamepadInfo,
    speed, setSpeed,
    CONTROL_MODES,
  } = useSteering();

  const { sendJoystickCommand, sendJoystickRelease, activateJoystick, deactivateJoystick } = useWebSocket(controlMode);
  const { sendLedCommand, sendInitialWhite } = useLedControl();

  // Send white RGB on initial mount (robot started, idle)
  useEffect(() => {
    sendInitialWhite();
  }, []); // eslint-disable-line react-hooks/exhaustive-deps
  const { arrayState, sendArrayTopicButton, resetArrayTopicButton } = useArrayTopicButtons(speed);
  const { groups: arrowGroups, activeGroup: activeArrowGroup, setActiveGroup: setActiveArrowGroup } =
    useArrowKeys(controlMode !== CONTROL_MODES.OFF);
  const customTopicControllers = useCustomTopics();

  const handleControlModeChange = async (mode) => {
    setControlMode(mode);
    await sendLedCommand(mode);
  };

  const emergencyStop = async () => {
    try {
      await fetch(`${BACKEND_CONFIG.BACKEND_URL}/stop`, { method: "POST" });
    } catch (error) {
      console.error("Error stop:", error);
    }
  };

  return (
    <>
      <div className="joystick--wrapper">
        <ControlModeButtons
          controlMode={controlMode}
          onControlModeChange={handleControlModeChange}
          onEmergencyStop={emergencyStop}
        />

        {controlMode !== CONTROL_MODES.OFF && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 8, margin: '6px 0', fontSize: 13 }}>
            {/* Group selector */}
            <div style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
              <span style={{ fontWeight: 600, fontSize: 12 }}>Active:</span>
              {arrowGroups.map((g) => (
                <button
                  key={g.groupIndex}
                  onClick={() => setActiveArrowGroup(g.groupIndex)}
                  style={{
                    padding: '3px 10px', fontSize: 12, cursor: 'pointer',
                    fontWeight: g.isActive ? 700 : 400,
                    background: g.isActive ? '#4facfe' : '#333',
                    color: '#fff', border: 'none', borderRadius: 4,
                  }}
                >
                  {g.name}
                </button>
              ))}
              <span style={{ fontSize: 11, color: '#888', marginLeft: 4 }}>(Tab to switch)</span>
            </div>
            {arrowGroups.map((group) => {
              const shared = group.config.SHARED_ARRAY;
              const isActive = group.isActive;
              // Collect which indices are controlled by axes
              const controlledIndices = new Set(
                Object.values(group.config.AXES).map((a) => a.ARRAY_INDEX)
              );
              // Get live array (falls back to per-axis display if no shared array)
              const liveArray = shared
                ? group.sharedArrays.current[group.groupIndex]
                : null;

              return (
                <div key={group.name} style={{ opacity: isActive ? 1 : 0.4, transition: 'opacity 0.15s' }}>
                  {/* Full array display */}
                  {liveArray && (
                    <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 4 }}>
                      <span style={{ fontWeight: 600 }}>{group.name}:</span>
                      <span style={{ fontFamily: 'monospace', letterSpacing: 1 }}>[
                        {liveArray.map((val, i) => (
                          <span key={i}>
                            {i > 0 && ', '}
                            <span style={{
                              fontWeight: controlledIndices.has(i) ? 700 : 400,
                              color: controlledIndices.has(i) ? '#4facfe' : '#888',
                            }}>
                              {controlledIndices.has(i)
                                ? (() => {
                                    // Find which axis controls this index
                                    const axis = Object.keys(group.config.AXES).find(
                                      (a) => group.config.AXES[a].ARRAY_INDEX === i
                                    );
                                    return group.values.current[group.groupIndex][axis];
                                  })()
                                : val}
                            </span>
                          </span>
                        ))}
                      ]</span>
                    </div>
                  )}
                  {/* Per-axis controls */}
                  <div style={{ display: 'flex', flexWrap: 'wrap', alignItems: 'center', gap: 12 }}>
                    {["VERTICAL", "HORIZONTAL"].map((axis) => {
                      const axisCfg = group.config.AXES[axis];
                      return (
                        <span key={axis} style={{ display: 'inline-flex', alignItems: 'center', gap: 4 }}>
                          <span>{axisCfg.LABEL}: <b>{group.values.current[group.groupIndex][axis]}</b></span>
                          <button
                            onClick={() => group.toggleDirection(axis)}
                            style={{ padding: '2px 8px', fontSize: 12, cursor: 'pointer' }}
                            title={`Flip ${axis.toLowerCase()} direction (${group.name})`}
                          >
                            {group.directions[axis] > 0 ? axisCfg.DIR_ICONS.POS : axisCfg.DIR_ICONS.NEG}
                          </button>
                        </span>
                      );
                    })}
                  </div>
                </div>
              );
            })}
          </div>
        )}

        {controlMode !== CONTROL_MODES.OFF && (
          <CustomTopicButtons controllers={customTopicControllers} />
        )}

        {controlMode === CONTROL_MODES.JOYSTICK && (
          <>
            <SpeedControl speed={speed} onSpeedChange={setSpeed} />
            <JoystickContainer
              speed={speed}
              sendJoystickCommand={sendJoystickCommand}
              sendJoystickRelease={sendJoystickRelease}
              activateJoystick={activateJoystick}
              deactivateJoystick={deactivateJoystick}
              arrayState={arrayState}
              sendArrayTopicButton={sendArrayTopicButton}
              resetArrayTopicButton={resetArrayTopicButton}
            />
          </>
        )}

        {controlMode === CONTROL_MODES.STEERING_NEW && (
          <>
            <SteeringNewControl />
            <GamepadDiagnostics />
          </>
        )}
      </div>
    </>
  );
}

export default VirtualJoystick;