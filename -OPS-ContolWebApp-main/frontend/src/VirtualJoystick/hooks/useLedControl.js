// hooks/useLedControl.js
// Automatic RGB control based on steering mode:
//   OFF            → White (200,200,200)
//   JOYSTICK/STEER → Cyan countdown (2s) then Blue (0,0,200)
import { useRef, useCallback, useEffect } from "react";
import { BACKEND_CONFIG, CONTROL_MODES } from "../Constants.js";

const RGB_WHITE = { r: 200, g: 200, b: 200 };
const RGB_CYAN  = { r: 0,   g: 200, b: 200 };
const RGB_BLUE  = { r: 0,   g: 0,   b: 200 };

const COUNTDOWN_MS = 2000;

const postRgb = async (rgb) => {
  try {
    await fetch(`${BACKEND_CONFIG.BACKEND_URL}/set_rgb`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(rgb),
    });
  } catch (error) {
    console.error("[useLedControl] RGB send error:", error);
  }
};

export const useLedControl = () => {
  const countdownRef = useRef(null);
  const intervalRef = useRef(null);

  const clearTimers = useCallback(() => {
    if (countdownRef.current) {
      clearTimeout(countdownRef.current);
      countdownRef.current = null;
    }
    if (intervalRef.current) {
      clearInterval(intervalRef.current);
      intervalRef.current = null;
    }
  }, []);

  const sendLedCommand = useCallback(async (mode) => {
    clearTimers();

    if (mode === CONTROL_MODES.OFF) {
      // Steering off → white
      await postRgb(RGB_WHITE);
      return;
    }

    if (
      mode === CONTROL_MODES.JOYSTICK ||
      mode === CONTROL_MODES.STEERING_NEW
    ) {
      // Show cyan immediately as a visual countdown warning
      await postRgb(RGB_CYAN);

      // After countdown, switch to blue (active steering colour)
      countdownRef.current = setTimeout(async () => {
        countdownRef.current = null;
        await postRgb(RGB_BLUE);
        
        // Spam blue at 1 Hz during STEERING_NEW
        if (mode === CONTROL_MODES.STEERING_NEW) {
          intervalRef.current = setInterval(() => {
            postRgb(RGB_BLUE);
          }, 1000);
        }
      }, COUNTDOWN_MS);
    }
  }, [clearTimers]);

  /** Send initial white on app load (robot started, idle). */
  const sendInitialWhite = useCallback(() => {
    postRgb(RGB_WHITE);
  }, []);

  // Cleanup timers on unmount
  useEffect(() => {
    return clearTimers;
  }, [clearTimers]);

  return { sendLedCommand, sendInitialWhite };
};
