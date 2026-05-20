import React, { useState } from "react";

function BluetoothManager({ backendUrl, onPaired }) {
  const [devices, setDevices] = useState([]);
  const [status, setStatus] = useState("");
  const [loading, setLoading] = useState(false);

  const scanDevices = () => {
    setLoading(true);
    setStatus("Skanowanie...");
    fetch(`${backendUrl}/bluetooth/scan`)
      .then(res => res.json())
      .then(data => {
        setDevices(data.devices || []);
        setStatus(data.devices && data.devices.length ? "Wybierz urządzenie do parowania" : "Nie znaleziono urządzeń");
        setLoading(false);
      })
      .catch(() => {
        setStatus("Błąd podczas skanowania");
        setLoading(false);
      });
  };

  const pairDevice = mac => {
    setStatus(`Parowanie z ${mac}...`);
    fetch(`${backendUrl}/bluetooth/pair`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ mac })
    })
      .then(res => res.json())
      .then(data => {
        if (data.status === "paired_and_connected") {
          setStatus(`Sparowano i połączono z ${mac}`);
          if (onPaired) onPaired(mac);
        } else {
          setStatus(`Błąd: ${data.error || "nieznany"}`);
        }
      })
      .catch(() => setStatus("Błąd podczas parowania"));
  };

  return (
    <div style={{ margin: "1rem 0" }}>
      <h4>Bluetooth: dodaj nowy pad</h4>
      <button onClick={scanDevices} disabled={loading} style={{ marginBottom: "1rem" }}>
        {loading ? "Skanowanie..." : "Skanuj urządzenia"}
      </button>
      <ul style={{ listStyle: "none", padding: 0 }}>
        {devices.map(d => (
          <li key={d.mac}>
            <button
              style={{ margin: "0.25rem", padding: "0.5rem 1rem", borderRadius: "5px", border: "1px solid #aaa", cursor: "pointer" }}
              onClick={() => pairDevice(d.mac)}
            >
              {d.name} ({d.mac})
            </button>
          </li>
        ))}
      </ul>
      {status && <div style={{ color: "#007bff", marginTop: "0.5rem" }}>{status}</div>}
    </div>
  );
}

export default BluetoothManager;