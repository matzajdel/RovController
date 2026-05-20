import { useEffect, useRef } from "react";
import { BACKEND_CONFIG, CONTROL_MODES } from "../Constants.js";

const BUTTON_CODE_MAP = {
  0: "A",
  1: "B",
  2: "X",
  3: "Y",
  4: "LB",
  5: "RB",
  6: "LT",
  7: "RT",
  8: "Back",
  9: "Start",
  10: "LJoyBut",
  11: "RJoyBut",
  12: "DPadUp",
  13: "DPadDown",
  14: "DPadLeft",
  15: "DPadRight",
};

const AXIS_THRESHOLD = 0.02;
const TRIGGER_THRESHOLD = 0.02;

const round = (value) => Number(value.toFixed(3));

export const useGamepadHidBridge = (
  controlMode,
  backendUrl = BACKEND_CONFIG.BACKEND_URL
) => {
  const rafRef = useRef(null);
  const prevStateRef = useRef({});
  const hidHandlersRef = useRef(new Map());

  useEffect(() => {
    if (typeof window === "undefined" || typeof navigator === "undefined") {
      console.warn("[HID] navigator is unavailable in this environment");
      return undefined;
    }

    const gamepadSupported = typeof navigator.getGamepads === "function";
    const hidSupported = typeof navigator.hid !== "undefined";

    if (!gamepadSupported && !hidSupported) {
      console.warn("[HID] Neither Gamepad API nor WebHID is supported in this browser");
      return undefined;
    }

    const shouldTrack = 
      controlMode === CONTROL_MODES.BLUETOOTH_MOBILE ||
      controlMode === CONTROL_MODES.BLUETOOTH_JETSON ||
      controlMode === CONTROL_MODES.STEERING_NEW;
    const endpoint = `${backendUrl}/gamepads/hid-event`;
    const cleanupFns = [];
    const hidHandlers = hidHandlersRef.current;

    const cancelAnimation = () => {
      if (rafRef.current) {
        cancelAnimationFrame(rafRef.current);
        rafRef.current = null;
      }
    };

    const unbindHidDevice = (device) => {
      const handler = hidHandlers.get(device);
      if (handler) {
        device.removeEventListener("inputreport", handler);
        hidHandlers.delete(device);
      }
    };

    const unbindAllHid = () => {
      hidHandlers.forEach((handler, device) => {
        device.removeEventListener("inputreport", handler);
      });
      hidHandlers.clear();
    };

    if (!shouldTrack) {
      prevStateRef.current = {};
      cancelAnimation();
      unbindAllHid();
      return undefined;
    }

    prevStateRef.current = {};

    const sendEvent = (payload) => {
      const enriched = {
        ...payload,
        control_mode: controlMode,
        timestamp: payload.timestamp || new Date().toISOString(),
      };
      console.log("[HID]", enriched);
      fetch(endpoint, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(enriched),
        keepalive: true,
      }).catch((error) => {
        console.warn("Failed to send HID event", error);
      });
    };

    if (gamepadSupported) {
      const pollGamepad = () => {
        const pads = navigator.getGamepads ? navigator.getGamepads() : [];
        const activePads = pads ? Array.from(pads).filter((gp) => gp && gp.connected) : [];
        const seenIndices = new Set();

        activePads.forEach((gp) => {
          const index = gp.index;
          seenIndices.add(index);
          const state = prevStateRef.current[index] || {
            buttons: [],
            leftStick: { x: 0, y: 0 },
            rightStick: { x: 0, y: 0 },
            pressedCodes: [],
          };

          gp.buttons.forEach((button, buttonIndex) => {
            const code = BUTTON_CODE_MAP[buttonIndex] || `BTN_${buttonIndex}`;
            const previous = state.buttons[buttonIndex] || { pressed: false, value: 0 };
            const pressedChanged = button.pressed !== previous.pressed;
            const valueChanged = Math.abs(button.value - previous.value) >= TRIGGER_THRESHOLD;

            if (pressedChanged || valueChanged) {
              sendEvent({
                code,
                action: pressedChanged ? (button.pressed ? "press" : "release") : "move",
                value: round(button.value),
                raw_index: buttonIndex,
                gamepad_index: index,
                gamepad_id: gp.id,
              });
            }
          });

          const leftStick = {
            x: round(gp.axes[0] || 0),
            y: round(gp.axes[1] || 0),
          };
          if (
            Math.abs(leftStick.x - state.leftStick.x) >= AXIS_THRESHOLD ||
            Math.abs(leftStick.y - state.leftStick.y) >= AXIS_THRESHOLD
          ) {
            sendEvent({
              code: "LJoy",
              action: "move",
              axes: leftStick,
              gamepad_index: index,
              gamepad_id: gp.id,
            });
          }

          const rightStick = {
            x: round(gp.axes[2] || 0),
            y: round(gp.axes[3] || 0),
          };
          if (
            Math.abs(rightStick.x - state.rightStick.x) >= AXIS_THRESHOLD ||
            Math.abs(rightStick.y - state.rightStick.y) >= AXIS_THRESHOLD
          ) {
            sendEvent({
              code: "RJoy",
              action: "move",
              axes: rightStick,
              gamepad_index: index,
              gamepad_id: gp.id,
            });
          }

          const pressedCodes = gp.buttons.reduce((acc, button, buttonIndex) => {
            if (button.pressed) {
              const code = BUTTON_CODE_MAP[buttonIndex] || `BTN_${buttonIndex}`;
              acc.push(code);
            }
            return acc;
          }, []);

          const prevPressed = state.pressedCodes || [];
          const pressedChanged =
            pressedCodes.length !== prevPressed.length ||
            pressedCodes.some((code, idx) => code !== prevPressed[idx]);

          if (pressedChanged) {
            sendEvent({
              code: "Buttons",
              action: "state",
              pressed_codes: pressedCodes,
              gamepad_index: index,
              gamepad_id: gp.id,
            });
          }

          prevStateRef.current[index] = {
            buttons: gp.buttons.map((b) => ({ pressed: b.pressed, value: b.value })),
            leftStick,
            rightStick,
            pressedCodes,
          };
        });

        Object.keys(prevStateRef.current).forEach((key) => {
          const numericKey = Number(key);
          if (!seenIndices.has(numericKey)) {
            delete prevStateRef.current[numericKey];
          }
        });

        rafRef.current = requestAnimationFrame(pollGamepad);
      };

      rafRef.current = requestAnimationFrame(pollGamepad);
    } else {
      console.debug("[HID] Gamepad API not available, relying on WebHID only");
    }

    if (hidSupported) {
      const bindHidDevice = async (device) => {
        try {
          if (!device.opened) {
            await device.open();
          }
        } catch (error) {
          console.warn("[HID] Failed to open device", device?.productName, error);
          return;
        }

        if (hidHandlers.has(device)) {
          return;
        }

        const handler = (event) => {
          try {
            const dataView = event.data;
            const dataArray = dataView
              ? new Uint8Array(dataView.buffer, dataView.byteOffset, dataView.byteLength)
              : new Uint8Array();
            const reportHex = Array.from(dataArray)
              .map((byte) => byte.toString(16).padStart(2, "0"))
              .join("");
            sendEvent({
              code: "HID",
              action: "report",
              report_id: event.reportId,
              report_hex: reportHex,
              vendor_id: device.vendorId,
              product_id: device.productId,
              usage_page: device.collections?.[0]?.usagePage,
              usage: device.collections?.[0]?.usage,
              gamepad_id: device.productName,
            });
          } catch (error) {
            console.warn("[HID] Failed to parse input report", error);
          }
        };

        device.addEventListener("inputreport", handler);
        hidHandlers.set(device, handler);
      };

      const handleConnect = (event) => {
        bindHidDevice(event.device).catch((error) => {
          console.warn("[HID] Failed to bind new device", error);
        });
      };
      const handleDisconnect = (event) => {
        unbindHidDevice(event.device);
        sendEvent({
          code: "HID",
          action: "state",
          pressed_codes: [],
          vendor_id: event.device.vendorId,
          product_id: event.device.productId,
          gamepad_id: event.device.productName,
        });
      };

      navigator.hid.addEventListener("connect", handleConnect);
      navigator.hid.addEventListener("disconnect", handleDisconnect);
      cleanupFns.push(() => {
        navigator.hid.removeEventListener("connect", handleConnect);
        navigator.hid.removeEventListener("disconnect", handleDisconnect);
      });

      navigator.hid
        .getDevices()
        .then((devices) => {
          if (!devices.length) {
            console.info(
              "[HID] No authorised devices. Use navigator.hid.requestDevice() in a user gesture to grant access."
            );
          }
          devices.forEach((device) => {
            bindHidDevice(device).catch((error) => {
              console.warn("[HID] Failed to bind device", device?.productName, error);
            });
          });
        })
        .catch((error) => {
          console.warn("[HID] Failed to enumerate HID devices", error);
        });
    } else {
      console.debug("[HID] WebHID API not available in this browser");
    }

    return () => {
      cancelAnimation();
      unbindAllHid();
      cleanupFns.forEach((fn) => fn());
    };
  }, [backendUrl, controlMode]);
};
