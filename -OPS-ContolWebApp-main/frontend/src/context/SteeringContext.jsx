/**
 * SteeringContext — Global Steering State Management
 * ===================================================
 *
 * Logika sterowania:
 * 1. RT (Trigger) = Pedał Gazu (0.0 do 1.0).
 * 2. Prawa Gałka = Kierownica (Kierunek i Proporcja).
 * 3. RB (Bumper) = Wsteczny (odwraca działanie silników).
 * 4. Wynik = (Wychylenie Gałki) * (Siła Gazu) * (Wsteczny).
 *
 * Aktualizacja: W trybie FREESTYLE wsteczny (RB) odwraca OBA osie (X i Z).
 */
import React, { createContext, useContext, useState, useEffect, useCallback, useRef } from "react";
import { BACKEND_CONFIG, ROSBRIDGE_URL } from "../config";
import { GAMEPAD_ARRAY_MAPPING, ARRAY_TOPIC_CONFIG, GAMEPAD_PID_TOPIC_MAPPINGS } from "../VirtualJoystick/Constants";
import { useGamepadDetection } from "../VirtualJoystick/hooks/useGamepadDetection";
import { useGamepadHidBridge } from "../VirtualJoystick/hooks/useGamepadHidBridge";
import { useRosBridge } from "../VirtualJoystick/hooks/useRosBridge";
import { useSatel } from "./SatelContext";

// ── Constants ──────────────────────────────────────────────────────────────

export const CONTROL_MODES = {
  OFF: "off",
  JOYSTICK: "joystick",
  BLUETOOTH_MOBILE: "bluetooth_mobile",
  BLUETOOTH_JETSON: "bluetooth_jetson",
  STEERING_NEW: "steering_new",
};

export const DRIVE_MODES = {
  PROSTY: { id: 0, name: "PROSTY", desc: "Jazda po krzyżu (X lub Y)" },
  SKRET: { id: 1, name: "SKRĘT", desc: "Jazda po skosie (Mix X i Y)" },
  OBROT: { id: 2, name: "OBRÓT", desc: "Tylko Angular Z" },
  FREESTYLE: { id: 3, name: "FREESTYLE", desc: "Arcade (1 Gałka)" },
};

const DEFAULT_TOPICS = ["cmd_vel", "cmd_vel_nav"];
const AUX_TOPICS_INIT_STORAGE_KEY = "steering_aux_topics_initialized_v1";

// ── Context ────────────────────────────────────────────────────────────────

const SteeringContext = createContext(null);

export const useSteering = () => {
  const ctx = useContext(SteeringContext);
  if (!ctx) throw new Error("useSteering must be used within <SteeringProvider>");
  return ctx;
};

// ── Provider ───────────────────────────────────────────────────────────────

export const SteeringProvider = ({ children }) => {
  // Control mode
  const [controlMode, setControlMode] = useState(CONTROL_MODES.OFF);

  // Drive parameters
  const [driveMode, setDriveModeState] = useState(DRIVE_MODES.FREESTYLE.id);
  const [motorMode, setMotorModeState] = useState(0); // 0=PWM (linear.z=0), 1=PID (linear.z=1) — default PID
  const [maxSpeed, setMaxSpeedState] = useState(1.5);
  const [maxTurn, setMaxTurnState] = useState(1.5);

  // Manipulator
  const [manipSensitivities, setManipSensitivitiesState] = useState([100, 100, 100, 100, 100, 100]);
  const [manipValues, setManipValues] = useState([0, 0, 0, 0, 0, 0]);

  // RGB
  const [rgb, setRgb] = useState({ r: 0, g: 0, b: 0 });

  // Topic selection
  const [targetTopic, setTargetTopicState] = useState("cmd_vel");
  const [availableTopics] = useState(DEFAULT_TOPICS);

  // Gamepad info
  const gamepadInfo = useGamepadDetection();

  // Speed (global multiplier)
  const [speed, setSpeed] = useState(1.0);

  // Left stick → servo topics toggle
  const [auxStickEnabled, setAuxStickEnabled] = useState(true);

  // Hardware gate: blocks driving when backend reports disconnected hardware.
  const [hardwareStatus, setHardwareStatus] = useState({
    ok: true,
    rosConnected: true,
    robotConnected: true,
    lastChecked: null,
    error: null,
  });

  const { satelEnabled, satel } = useSatel();

  // ── Rosbridge (direct ROS publishing — no backend needed) ────────────

  const backendUrl = BACKEND_CONFIG.BACKEND_URL;
  const { publish: rosPublish, connected: rosBridgeConnected } = useRosBridge(ROSBRIDGE_URL);

  // ── Setters (frontend-only state, no backend dependency) ────────────

  const setDriveMode = useCallback(async (modeId) => {
    setDriveModeState(modeId);
    try {
      await fetch(`${backendUrl}/steering/set_drive_mode`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ mode_id: modeId }),
      });
    } catch (e) {
      console.warn("[SteeringCtx] Sync drive mode failed:", e);
    }
  }, [backendUrl]);

  const toggleMotorMode = useCallback(async () => {
    const newMode = motorMode === 0 ? 1 : 0;
    setMotorModeState(newMode);
    try {
      await fetch(`${backendUrl}/steering/set_motor_mode`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ motor_mode: parseFloat(newMode) }),
      });
    } catch (e) {
      console.warn("[SteeringCtx] Sync motor mode failed:", e);
    }
  }, [motorMode, backendUrl]);

  const setMaxSpeed = useCallback(async (val) => {
    setMaxSpeedState(val);
    try {
      await fetch(`${backendUrl}/steering/set_speed_limits`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ max_speed: val, max_turn: maxTurn }),
      });
    } catch (e) {
      console.warn("[SteeringCtx] Sync speed limits failed:", e);
    }
  }, [backendUrl, maxTurn]);

  const setMaxTurn = useCallback(async (val) => {
    setMaxTurnState(val);
    try {
      await fetch(`${backendUrl}/steering/set_speed_limits`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ max_speed: maxSpeed, max_turn: val }),
      });
    } catch (e) {
      console.warn("[SteeringCtx] Sync speed limits failed:", e);
    }
  }, [backendUrl, maxSpeed]);

  const setManipSensitivity = useCallback((index, value) => {
    const newSens = [...manipSensitivities];
    newSens[index] = value;
    setManipSensitivitiesState(newSens);
  }, [manipSensitivities]);

  const setGlobalSensitivity = useCallback((value) => {
    const newSens = Array(6).fill(value);
    setManipSensitivitiesState(newSens);
  }, []);

  // ── RGB (uses backend — not part of steering) ───────────────────────

  const postBackend = useCallback(async (path, body) => {
    try {
      const res = await fetch(`${backendUrl}${path}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      return res.ok ? await res.json() : null;
    } catch (err) {
      console.warn(`[SteeringCtx] POST ${path} failed:`, err);
      return null;
    }
  }, [backendUrl]);

  const setRgbChannel = useCallback(async (channel, value) => {
    const newRgb = { ...rgb, [channel]: value };
    setRgb(newRgb);
    if (satelEnabled && satel.isConnected) {
      satel.sendRgb(newRgb.r, newRgb.g, newRgb.b);
    } else {
      await postBackend("/set_rgb", newRgb);
    }
  }, [rgb, postBackend, satelEnabled, satel]);

  const applyRgbPreset = useCallback(async (preset) => {
    const val = { r: preset.r, g: preset.g, b: preset.b };
    setRgb(val);
    if (satelEnabled && satel.isConnected) {
      satel.sendRgb(val.r, val.g, val.b);
    } else {
      await postBackend("/set_rgb", val);
    }
  }, [postBackend, satelEnabled, satel]);

  const turnOffRgb = useCallback(async () => {
    const val = { r: 0, g: 0, b: 0 };
    setRgb(val);
    if (satelEnabled && satel.isConnected) {
      satel.sendRgb(0, 0, 0);
    } else {
      await postBackend("/set_rgb", val);
    }
  }, [postBackend, satelEnabled, satel]);

  const setTargetTopic = useCallback(async (topic) => {
    setTargetTopicState(topic);
    try {
      await fetch(`${backendUrl}/steering/set_target_topic`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ topic }),
      });
    } catch (e) {
      console.warn("[SteeringCtx] Sync target topic failed:", e);
    }
  }, [backendUrl]);

  useEffect(() => {
    const shouldPublish = controlMode === CONTROL_MODES.STEERING_NEW;

    fetch(`${backendUrl}/cmd_vel/publishing?enabled=${shouldPublish}`, {
      method: "POST",
    }).catch((e) => {
      console.warn("[SteeringCtx] Toggle cmd_vel publishing failed:", e);
    });
  }, [controlMode, backendUrl]);

  useEffect(() => {
    fetch(`${backendUrl}/steering/set_target_topic`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ topic: targetTopic }),
    }).catch((e) => {
      console.warn("[SteeringCtx] Initial target topic sync failed:", e);
    });
  }, [targetTopic, backendUrl]);

  const emergencyStop = useCallback(() => {
    // Send zero twist to backend (updates the 250Hz timer to publish zeros)
    fetch(`${backendUrl}/cmd_vel_full`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        linear_x: 0, linear_y: 0, linear_z: 0,
        angular_x: 0, angular_y: 0, angular_z: 0,
      }),
      keepalive: true,
    }).catch(() => { });
    
    if (satelEnabled && satel.isConnected) {
      satel.sendStop();
    } else {
      // Also send via rosbridge as safety fallback
      rosPublish(`/${targetTopic}`, "geometry_msgs/msg/Twist", {
        linear: { x: 0, y: 0, z: 0 },
        angular: { x: 0, y: 0, z: 0 },
      });
    }
    setManipValues([0, 0, 0, 0, 0, 0]);
  }, [rosPublish, targetTopic, backendUrl, satelEnabled, satel]);

  // ── Gamepad HID Bridge ───────────────────────────────────────────────
  useGamepadHidBridge(controlMode, backendUrl);

  // ── MAIN DRIVE LOGIC ─────────────────────────────────────────────────

  const [liveGamepad, setLiveGamepad] = useState({
    rightX: 0, rightY: 0, rt: 0, rb: false, lt: false, connected: false,
    isSafetyStopActive: false,
    twist: { linear_x: 0, linear_y: 0, angular_z: 0 },
  });

  const gamepadLoopRef = useRef(null);
  const topicArrayStateRef = useRef({});
  const hardwareOkRef = useRef(true);
  const ltAxisBaselineRef = useRef(null);
  const auxStickStateRef = useRef({
    initialized: false,
    serwoUartValue: 180,
    serwaArray: [0, 180, 135, 90],
    lastHorizontalStepAt: 0,
    lastVerticalStepAt: 0,
  });

  useEffect(() => {
    let intervalId = null;
    let cancelled = false;

    const checkHardware = async () => {
      try {
        const res = await fetch(`${backendUrl}/health`, {
          method: "GET",
          cache: "no-store",
        });
        if (!res.ok) throw new Error(`HTTP ${res.status}`);

        const data = await res.json();
        const rosConnected = !!data?.ros_connected;
        const robotConnected = !!data?.robot_connected;
        const ok = data?.status === "healthy" && rosConnected && robotConnected;

        hardwareOkRef.current = ok;
        if (!cancelled) {
          setHardwareStatus({
            ok,
            rosConnected,
            robotConnected,
            lastChecked: new Date().toISOString(),
            error: null,
          });
        }
      } catch (e) {
        hardwareOkRef.current = false;
        if (!cancelled) {
          setHardwareStatus((prev) => ({
            ...prev,
            ok: false,
            lastChecked: new Date().toISOString(),
            error: String(e),
          }));
        }
      }
    };

    if (controlMode === CONTROL_MODES.STEERING_NEW) {
      checkHardware();
      intervalId = setInterval(checkHardware, 1000);
    } else {
      hardwareOkRef.current = true;
      setHardwareStatus({
        ok: true,
        rosConnected: true,
        robotConnected: true,
        lastChecked: null,
        error: null,
      });
    }

    return () => {
      cancelled = true;
      if (intervalId) clearInterval(intervalId);
    };
  }, [controlMode, backendUrl]);

  useEffect(() => {
    if (controlMode !== CONTROL_MODES.STEERING_NEW) {
      ltAxisBaselineRef.current = null;
      auxStickStateRef.current.initialized = false;
      if (gamepadLoopRef.current) {
        cancelAnimationFrame(gamepadLoopRef.current);
        gamepadLoopRef.current = null;
      }
      return;
    }

    const DEADZONE = 0.15;
    const SEND_INTERVAL_MS = 50; // 20Hz — throttle HTTP requests
    const AUX_STICK_THRESHOLD = 0.25;
    const AUX_STEP_INTERVAL_MS = 120;
    const round3 = (v) => Math.round(v * 1000) / 1000;
    const clamp = (v, limit) => Math.max(-limit, Math.min(limit, v));

    let lastSendTime = 0;
    let lastLx = 0, lastLy = 0, lastLz = 0, lastAz = 0;

    const sendTwist = (lx, ly, lz, az) => {
      // W trybie OFF nie wysyłaj nic
      if (controlMode === CONTROL_MODES.OFF) return;

      // W trybie JOYSTICK wysyłaj tylko jeśli wartości się zmieniły
      if (controlMode === CONTROL_MODES.JOYSTICK) {
        if (lx === lastLx && ly === lastLy && lz === lastLz && az === lastAz) return;
      } else if (controlMode !== CONTROL_MODES.STEERING_NEW) {
        // W innych trybach niż JOYSTICK i STEERING_NEW nie wysyłaj
        return;
      }

      const now = performance.now();
      if (now - lastSendTime < SEND_INTERVAL_MS) return;
      lastSendTime = now;

      // Store latest values (after throttle, so changes aren't missed)
      lastLx = lx; lastLy = ly; lastLz = lz; lastAz = az;

      if (satelEnabled && satel.isConnected) {
        satel.sendCmdVelFull(lastLx, lastLy, lastLz, lastAz);
      } else {
        fetch(`${backendUrl}/cmd_vel_full`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            linear_x: lastLx, linear_y: lastLy, linear_z: lastLz,
            angular_x: 0, angular_y: 0, angular_z: lastAz,
          }),
          keepalive: true,
        }).catch((e) => console.warn("[Steering] cmd_vel_full error:", e));
      }
    };

    let frameCount = 0;

    // ── GAMEPAD → ARRAY_TOPIC: śledzenie stanu przycisków ──
    const prevBtnState = {};
    const sendArrayTopic = (arrayIndex, value) => {
      // Send manipulator command as-is (no global drive speed scaling).
      const commandValue = value;
      
      if (satelEnabled && satel.isConnected) {
        satel.sendArrayIndex(arrayIndex, commandValue);
      } else {
        fetch(`${backendUrl}/array_topic/${arrayIndex}`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ value: commandValue }),
          keepalive: true,
        }).catch((e) => console.warn(`[Gamepad] array_topic error:`, e));
      }

      // Mirror command values in the manipulator panel (arrayIndex is 1-based).
      setManipValues((prev) => {
        const next = [...prev];
        const idx = arrayIndex - 1;
        if (idx >= 0 && idx < next.length) {
          next[idx] = commandValue;
        }
        return next;
      });
    };

    const sendCustomTopicArray = (topic, msgType, data) => {
      if (satelEnabled && satel.isConnected) {
        satel.sendCustomTopic(topic, msgType, data);
      } else {
        fetch(`${backendUrl}/custom_topic`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            topic,
            msg_type: msgType,
            data,
          }),
          keepalive: true,
        })
          .then(async (res) => {
            if (!res.ok) {
              const bodyText = await res.text().catch(() => "");
              console.warn(`[Gamepad] custom_topic ${topic} HTTP ${res.status}: ${bodyText}`);
            }
          })
          .catch((e) => console.warn(`[Gamepad] custom_topic ${topic} error:`, e));
      }
    };

    const wrapAdd = (current, delta, min, max) => {
      const next = current + delta;
      if (next > max) return min;
      if (next < min) return max;
      return next;
    };

    const publishSerwoUart = (value) => {
      sendCustomTopicArray("/serwoUART", "Int32MultiArray", [1, value]);
    };

    const publishSerwaArray = (arrayData) => {
      sendCustomTopicArray("/Serwa", "UInt8MultiArray", arrayData);
    };

    if (!auxStickStateRef.current.initialized) {
      auxStickStateRef.current = {
        initialized: true,
        serwoUartValue: 180,
        serwaArray: [0, 90, 75, 90],
        lastHorizontalStepAt: 0,
        lastVerticalStepAt: 0,
      };

      // Publish default aux topics only once across page reloads.
      let shouldPublishInitialAux = true;
      try {
        if (typeof window !== "undefined" && window.localStorage) {
          shouldPublishInitialAux =
            window.localStorage.getItem(AUX_TOPICS_INIT_STORAGE_KEY) !== "1";
        }
      } catch (_e) {
        // If storage is unavailable, fall back to publishing once for this runtime.
      }

      if (shouldPublishInitialAux) {
        publishSerwoUart(auxStickStateRef.current.serwoUartValue);
        publishSerwaArray(auxStickStateRef.current.serwaArray);
        try {
          if (typeof window !== "undefined" && window.localStorage) {
            window.localStorage.setItem(AUX_TOPICS_INIT_STORAGE_KEY, "1");
          }
        } catch (_e) {
          // Ignore storage write failures.
        }
      }
    }

    const parseGamepadPid = (gamepadId) => {
      if (!gamepadId || typeof gamepadId !== "string") return null;

      const productMatch = gamepadId.match(/Product:\s*([0-9a-f]{4})/i);
      if (productMatch?.[1]) return productMatch[1].toLowerCase();

      const dashMatch = gamepadId.match(/^[0-9a-f]{4}-([0-9a-f]{4})-/i);
      if (dashMatch?.[1]) return dashMatch[1].toLowerCase();

      const pidMatch = gamepadId.match(/PID[_:\s-]*([0-9a-f]{4})/i);
      if (pidMatch?.[1]) return pidMatch[1].toLowerCase();

      return null;
    };

    const getPidProfile = (gamepadId) => {
      const pid = parseGamepadPid(gamepadId);
      const directProfile = GAMEPAD_PID_TOPIC_MAPPINGS.find(
        (entry) => entry?.pid && entry.pid !== "*" && entry.pid.toLowerCase() === pid
      );
      if (directProfile?.mappings?.length) return directProfile;
      return GAMEPAD_PID_TOPIC_MAPPINGS.find((entry) => entry?.pid === "*") || { mappings: [] };
    };

    const resolveButtonIndex = (mapping, happyButtonOffset) => {
      if (typeof mapping.evdevCode === "number") {
        return (mapping.evdevCode - 704) + (happyButtonOffset || 0);
      }
      return mapping.gamepadButton;
    };

    const resolveElementIndex = (mapping) => {
      if (!mapping) return -1;
      if (Number.isInteger(mapping.element)) return mapping.element - 1;
      if (Number.isInteger(mapping.arrayIndex)) return mapping.arrayIndex;
      return -1;
    };

    const sendPidMappedTopicArray = (mapping, nextValue) => {
      const topic = mapping?.topic;
      if (!topic || !Array.isArray(mapping?.arrayTemplate)) return;

      const msgType = mapping.msgType || "Int32MultiArray";
      const key = `${topic}__${msgType}`;

      if (!topicArrayStateRef.current[key]) {
        topicArrayStateRef.current[key] = [...mapping.arrayTemplate];
      }

      const elementIndex = resolveElementIndex(mapping);
      if (elementIndex < 0 || elementIndex >= topicArrayStateRef.current[key].length) {
        console.warn("[Gamepad] Invalid mapped element index:", mapping);
        return;
      }

      topicArrayStateRef.current[key][elementIndex] = nextValue;

      if (satelEnabled && satel.isConnected) {
        satel.sendCustomTopic(topic, msgType, topicArrayStateRef.current[key]);
      } else {
        fetch(`${backendUrl}/custom_topic`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            topic,
            msg_type: msgType,
            data: topicArrayStateRef.current[key],
          }),
          keepalive: true,
        }).catch((e) => console.warn("[Gamepad] custom_topic error:", e));
      }
    };

    const poll = () => {
      const pads = navigator.getGamepads ? navigator.getGamepads() : [];
      let gp = null;
      for (let i = 0; i < pads.length; i++) {
        if (pads[i] && pads[i].connected) { gp = pads[i]; break; }
      }

      if (!gp) {
        ltAxisBaselineRef.current = null;
        setLiveGamepad(prev => prev.connected ? { ...prev, connected: false } : prev);
        gamepadLoopRef.current = requestAnimationFrame(poll);
        return;
      }

      // 1. ODCZYT GAŁKI (KIERUNEK)
      let rawRX = gp.axes[2] || 0;
      let rawRY = gp.axes[3] || 0;

      // Deadzone na start
      if (Math.abs(rawRX) < DEADZONE) rawRX = 0;
      if (Math.abs(rawRY) < DEADZONE) rawRY = 0;

      // 2. ODCZYT GAZU (RT) - Wartość od 0.0 do 1.0
      let gas = 0;

      // Metoda A: Standardowy obiekt Button
      if (gp.buttons[7] && typeof gp.buttons[7].value === "number") {
        gas = gp.buttons[7].value;
      }

      // Metoda B: Fallback na osie (Linux/Android)
      // Wartości zazwyczaj: -1.0 (luz) do 1.0 (max) -> Wzór: (val + 1) / 2
      if (gas < 0.1 && gp.axes.length > 5) {
        const rawAxis = gp.axes[5];
        const normalized = (rawAxis + 1.0);
        if (normalized > gas) gas = normalized;
      }

      // Bezpiecznik i Deadzone na gaz
      gas = Math.max(0, Math.min(1, gas));
      if (gas < 0.05) gas = 0;


      // 3. ODCZYT RB (WSTECZNY)
      const rbPressed = gp.buttons[5]?.pressed || false;
      const ltButton = gp.buttons[6];
      const ltButtonPressed = !!ltButton?.pressed;
      const ltButtonValue = Number.isFinite(ltButton?.value) ? ltButton.value : 0;

      // Some controllers expose LT as axis instead of a digital button.
      // Calibrate baseline on connect, then detect significant movement.
      let ltAxisPressed = false;
      if (gp.axes.length > 4) {
        const rawLtAxis = Number(gp.axes[4]);
        if (Number.isFinite(rawLtAxis)) {
          if (ltAxisBaselineRef.current === null) {
            ltAxisBaselineRef.current = rawLtAxis;
          }
          const deltaFromBaseline = Math.abs(rawLtAxis - ltAxisBaselineRef.current);
          ltAxisPressed = deltaFromBaseline > 0.35;
        }
      }

      const ltPressed = ltButtonPressed || ltButtonValue > 0.2 || ltAxisPressed;

      // Left stick mapping:
      // - X axis -> /serwoUART as [1, value], range 0..360, default 330, wrap-around
      // - Y axis -> /Serwa array element #4 (index 3), range 0..270, default 75, wrap-around
      const leftX = gp.axes[0] || 0;
      const leftY = gp.axes[1] || 0;
      const auxNow = performance.now();
      const auxState = auxStickStateRef.current;

      if (auxStickEnabled) {
        if (
          Math.abs(leftX) >= AUX_STICK_THRESHOLD &&
          auxNow - auxState.lastHorizontalStepAt >= AUX_STEP_INTERVAL_MS
        ) {
          const horizontalStep = leftX > 0 ? -5 : 5;
          auxState.serwoUartValue = wrapAdd(auxState.serwoUartValue, horizontalStep, 0, 360);
          publishSerwoUart(auxState.serwoUartValue);
          auxState.lastHorizontalStepAt = auxNow;
        }

        if (
          Math.abs(leftY) >= AUX_STICK_THRESHOLD &&
          auxNow - auxState.lastVerticalStepAt >= AUX_STEP_INTERVAL_MS
        ) {
          // In Gamepad API, up is negative Y; up increases value.
          const verticalStep = leftY < 0 ? -5 : 5;
          const currentThird = auxState.serwaArray[3] ?? 75;
          auxState.serwaArray[3] = wrapAdd(currentThird, verticalStep, 0, 270);
          publishSerwaArray(auxState.serwaArray);
          auxState.lastVerticalStepAt = auxNow;
        }
      }

      // 4. HAPPY BUTTONS (paddles) — detection kept for future safety-stop usage.
      // Te przyciski często mapują się na indeksy 16, 17, 18, 19+ w przeglądarce.
      let happyPaddlesPressed = false;
      for (let bIdx = 16; bIdx < gp.buttons.length; bIdx++) {
        if (gp.buttons[bIdx] && gp.buttons[bIdx].pressed) {
          happyPaddlesPressed = true;
          break;
        }
      }

      // Safety stop by paddles is currently disabled on purpose.
      // Keep this scaffold for fast re-enable later:
      // const safetyStopActive = happyPaddlesPressed;
      const hardwareBlocked = !hardwareOkRef.current;
      const safetyStopActive = hardwareBlocked;

      // ══════════════════════════════════════════════════════════
      // LOGIKA OBLICZANIA — port z advanced_steering.py._publish_twist()
      // ══════════════════════════════════════════════════════════

      // Axis mapping (matches advanced_steering._publish_twist lines 365-371)
      // Browser Y: UP = -1, DOWN = +1 → negate to match SteeringTest
      const val_vert = -rawRY;
      // Browser X: used directly (advanced_steering line 371: val_horz = right_x)
      const val_horz = rawRX;

      // RT conversion: Browser 0..1 → ROS convention 1..-1
      // (matches advanced_steering._handle_move line 264: 1.0 - value * 2.0)
      const val_trigger = 1.0 - (gas * 2.0);

      // Throttle (SteeringTest lines 197-199)
      let throttle = (1.0 - val_trigger) / 2;
      if (throttle < 0.05) throttle = 0.0;

      // Helper values (SteeringTest lines 201-206)
      const abs_vert = Math.abs(val_vert);
      const abs_horz = Math.abs(val_horz);
      const in_vertical = (abs_vert >= abs_horz) && (abs_vert > DEADZONE);
      const in_horizontal = (abs_horz > abs_vert) && (abs_horz > DEADZONE);

      // RB reverse — only PROSTY & SKRET (SteeringTest lines 178-190)
      const rbActive = rbPressed && (driveMode === 0 || driveMode === 1);
      const dirMul = rbActive ? -1.0 : 1.0;

      let lx = 0, ly = 0, az = 0;
      const mSpeed = maxSpeed;
      const mTurn = maxTurn;
      const mMode = motorMode === 1 ? 1.0 : 0.0;

      if (driveMode === 0) {
        // ── PROSTY (advanced_steering lines 390-402) ──
        if (in_vertical || (throttle > 0.0 && !in_horizontal)) {
          const direction = val_vert >= 0 ? 1.0 : -1.0;
          lx = throttle * mSpeed * dirMul * direction;
          ly = 0;
        } else if (in_horizontal) {
          lx = 0;
          ly = (throttle * mSpeed) * dirMul * (val_horz >= 0 ? -1.0 : 1.0)
            + (val_horz >= 0 ? -0.05 : 0.05);
        } else {
          lx = 0;
          ly = 0;
        }
        az = 0;

      } else if (driveMode === 1) {
        // ── SKRĘT (advanced_steering lines 404-415) ──
        // NOTE: skret_gain = 0.005 (adjusted from SteeringTest's 0.05)
        const skretGain = 0.005;

        if (abs_vert > 0.1) {
          lx = (val_vert * skretGain) * dirMul
            * (throttle > 0.0 ? throttle * 280 : 1)

        } else {
          lx = 0;
        }

        if (abs_horz > 0.1) {
          ly = (-val_horz * skretGain) * -dirMul
            * (throttle > 0.0 ? throttle * 280 : 1);
        } else {
          ly = 0;
        }
        az = 0;

      } else if (driveMode === 2) {
        // ── OBRÓT (advanced_steering lines 418-425) ──
        lx = 0;
        ly = 0;
        if (abs_horz > DEADZONE) {
          az = (val_horz * mTurn) * throttle * dirMul
            + (val_horz >= 0 ? -0.05 : 0.05);
        } else {
          az = 0;
        }

      } else if (driveMode === 3) {
        // ── FREESTYLE ze "square mapping" (kwadratowe mapowanie gałki) ──
        // Gałki pada domyślnie generują koło (x^2 + y^2 <= 1).
        // W rogach (np. maksymalnie po przekątnej) x i y mają wartości ok. 0.707.
        // Skalujemy wartości, aby osiągały 1.0 w rogach "kwadratu".

        let mappedVert = val_vert;
        let mappedHorz = val_horz;

        // Zabezpieczenie przed dzieleniem przez 0 dla obszaru martwego/srodka
        if (abs_vert > DEADZONE || abs_horz > DEADZONE) {
          const length = Math.sqrt(val_horz * val_horz + val_vert * val_vert);
          const maxLength = Math.max(abs_horz, abs_vert);
          // Skala "rozciągająca" koło do kwadratu:
          const scale = length > 0 ? (maxLength / length) : 1;

          mappedVert = val_vert * scale;
          mappedHorz = -val_horz * scale;
        }

        if (abs_vert == 0 && abs_horz !== 0) {
          mappedHorz = -mappedHorz;
        }

        lx = mappedVert * mSpeed;
        ly = 0;
        const p = 3;
        az = Math.sign(mappedHorz) * Math.pow(Math.abs(mappedHorz), p) * mTurn;

        if (mappedHorz > 0.05) {
          mappedHorz = -mappedHorz;
        }

      }

      // ── Apply global speed multiplier to all steering types ──
      lx *= speed;
      ly *= speed;
      az *= speed;

      // Zaokrąglenie i wysłanie
      lx = round3(lx);
      ly = round3(ly);
      az = round3(az);

      // Jeśli Safety Stop jest aktywny (Happy Buttons), wymuś 0
      if (safetyStopActive) {
        lx = 0;
        ly = 0;
        az = 0;
      }

      sendTwist(lx, ly, mMode, az);

      // ── 5. GAMEPAD → ARRAY_TOPIC MAPPING ──
      for (const mapping of GAMEPAD_ARRAY_MAPPING) {
        const btn = gp.buttons[mapping.gamepadButton];
        const pressed = btn?.pressed || false;
        const wasPressed = prevBtnState[mapping.gamepadButton] || false;
        const manipIndex = mapping.arrayIndex - 1;
        const configuredMagnitude =
          manipIndex >= 0 && manipIndex < manipSensitivities.length
            ? manipSensitivities[manipIndex]
            : Math.abs(mapping.pressValue);
        const direction = mapping.pressValue >= 0 ? 1 : -1;
        const pressValueFromManipulator = configuredMagnitude * direction;

        if (pressed && !wasPressed) {
          // Wciśnięcie → wyślij wartość z konfiguracji "Sterowanie Manipulatorem"
          sendArrayTopic(mapping.arrayIndex, pressValueFromManipulator);
        } else if (!pressed && wasPressed) {
          // Puszczenie → wyślij reset (0)
          sendArrayTopic(mapping.arrayIndex, ARRAY_TOPIC_CONFIG.RESET_VALUE);
        }
        prevBtnState[mapping.gamepadButton] = pressed;
      }

      // ── 6. GAMEPAD (PID) → CUSTOM TOPIC ARRAY MAPPING (includes paddles) ──
      const pidProfile = getPidProfile(gp.id);
      const pidMappings = pidProfile.mappings || [];
      const happyOffset = pidProfile.happyButtonOffset || 0;
      const watchedIndices = [];
      for (const mapping of pidMappings) {
        const btnIdx = resolveButtonIndex(mapping, happyOffset);
        watchedIndices.push(btnIdx);
        const btn = gp.buttons[btnIdx];
        const pressed = btn?.pressed || false;
        const btnKey = `pid:${gp.id}:${mapping.topic}:${btnIdx}`;
        const wasPressed = prevBtnState[btnKey] || false;

        if (pressed && !wasPressed) {
          sendPidMappedTopicArray(mapping, mapping.pressValue);
        } else if (!pressed && wasPressed) {
          const releaseValue =
            typeof mapping.releaseValue === "number"
              ? mapping.releaseValue
              : ARRAY_TOPIC_CONFIG.RESET_VALUE;
          sendPidMappedTopicArray(mapping, releaseValue);
        }

        prevBtnState[btnKey] = pressed;
      }

      // Aktualizacja UI
      frameCount++;
      if (frameCount % 4 === 0) {
        setLiveGamepad({
          rightX: round3(rawRX), rightY: round3(rawRY),
          rt: round3(gas), rb: rbPressed, lt: ltPressed, connected: true,
          isSafetyStopActive: safetyStopActive,
          hardwareBlocked,
          happyPaddlesPressed,
          twist: { linear_x: lx, linear_y: ly, angular_z: az },
          rawButtons: Array.from(gp.buttons, (b) => b.pressed),
          gamepadId: gp.id,
          parsedPid: parseGamepadPid(gp.id),
          pidProfilePid: pidProfile.pid || null,
          watchedBtnIndices: watchedIndices,
        });
      }

      gamepadLoopRef.current = requestAnimationFrame(poll);
    };

    gamepadLoopRef.current = requestAnimationFrame(poll);

    return () => {
      if (gamepadLoopRef.current) {
        cancelAnimationFrame(gamepadLoopRef.current);
        gamepadLoopRef.current = null;
      }
      // Send stop to backend on cleanup (resets 250Hz timer to zeros)
      fetch(`${backendUrl}/cmd_vel_full`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          linear_x: 0, linear_y: 0, linear_z: 0,
          angular_x: 0, angular_y: 0, angular_z: 0,
        }),
        keepalive: true,
      }).catch(() => { });
    };
  }, [controlMode, driveMode, maxSpeed, maxTurn, motorMode, backendUrl, targetTopic, speed, manipSensitivities, auxStickEnabled, satelEnabled, satel]);

  // ── Context Value ────────────────────────────────────────────────────

  const value = {
    controlMode, setControlMode,
    driveMode, setDriveMode,
    motorMode, toggleMotorMode,
    maxSpeed, setMaxSpeed,
    maxTurn, setMaxTurn,
    manipSensitivities, setManipSensitivity, setGlobalSensitivity,
    manipValues, setManipValues,
    rgb, setRgbChannel, applyRgbPreset, turnOffRgb,
    targetTopic, setTargetTopic, availableTopics,
    gamepadInfo, liveGamepad,
    speed, setSpeed,
    hardwareStatus,
    emergencyStop,
    rosBridgeConnected,
    auxStickEnabled, setAuxStickEnabled,
    DRIVE_MODES, CONTROL_MODES,
  };

  return (
    <SteeringContext.Provider value={value}>
      {children}
    </SteeringContext.Provider>
  );
};

export default SteeringContext;