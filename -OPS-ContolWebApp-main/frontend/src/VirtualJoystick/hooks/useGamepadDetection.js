import { useState, useEffect, useRef, useCallback } from "react";

export const useGamepadDetection = () => {
  const [gamepad, setGamepad] = useState({
    axes: [],
    buttons: [],
    connected: false,
    name: "",
    id: "",
    index: 0,
  });
  const requestRef = useRef();
  const connectedRef = useRef(false);

  const findGamepad = useCallback(() => {
    const pads = navigator.getGamepads ? navigator.getGamepads() : [];
    for (let i = 0; i < pads.length; i++) {
      if (pads[i] && pads[i].connected) {
        return pads[i];
      }
    }
    return null;
  }, []);

  const update = useCallback(() => {
    const found = findGamepad();

    if (found) {
      connectedRef.current = true;
      setGamepad({
        axes: [...found.axes],
        buttons: found.buttons.map(b => b.pressed),
        id: found.id,
        name: found.id,
        index: found.index,
        connected: true,
      });
    } else if (connectedRef.current) {
      // Was connected, now lost
      connectedRef.current = false;
      setGamepad({ axes: [], buttons: [], connected: false, name: "", id: "", index: 0 });
    }

    requestRef.current = requestAnimationFrame(update);
  }, [findGamepad]);

  useEffect(() => {
    // Listen for gamepad connect/disconnect events
    // These fire when user presses a button on a new gamepad
    const onConnect = (e) => {
      console.log("[Gamepad] Connected:", e.gamepad.id);
      connectedRef.current = true;
      setGamepad({
        axes: [...e.gamepad.axes],
        buttons: e.gamepad.buttons.map(b => b.pressed),
        id: e.gamepad.id,
        name: e.gamepad.id,
        index: e.gamepad.index,
        connected: true,
      });
    };

    const onDisconnect = (e) => {
      console.log("[Gamepad] Disconnected:", e.gamepad.id);
      connectedRef.current = false;
      setGamepad({ axes: [], buttons: [], connected: false, name: "", id: "", index: 0 });
    };

    window.addEventListener("gamepadconnected", onConnect);
    window.addEventListener("gamepaddisconnected", onDisconnect);

    // Start polling loop
    requestRef.current = requestAnimationFrame(update);

    return () => {
      cancelAnimationFrame(requestRef.current);
      window.removeEventListener("gamepadconnected", onConnect);
      window.removeEventListener("gamepaddisconnected", onDisconnect);
    };
  }, [update]);

  return gamepad;
};