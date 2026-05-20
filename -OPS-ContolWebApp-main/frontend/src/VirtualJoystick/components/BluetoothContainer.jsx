import React, { useRef } from "react";
import BluetoothManager from "./BluetoothManager";
import GamepadSelector from "./GamepadSelector.jsx";
import { BACKEND_CONFIG } from "../Constants.js";

const BluetoothContainer = () => {
  const bluetoothManagerRef = useRef(null);

  const handleDisconnectBluetooth = () => {
    if (
      bluetoothManagerRef.current &&
      bluetoothManagerRef.current.disconnectBluetooth
    ) {
      bluetoothManagerRef.current.disconnectBluetooth();
    }
  };

  return (
    <>
      <BluetoothManager
        ref={bluetoothManagerRef}
        backendUrl={BACKEND_CONFIG.BACKEND_URL}
      />
      <GamepadSelector backendUrl={BACKEND_CONFIG.BACKEND_URL} />
      <button
        className="disconnect-bluetooth-btn"
        onClick={handleDisconnectBluetooth}
      >
        Rozłącz Bluetooth
      </button>
    </>
  );
};

export default BluetoothContainer;