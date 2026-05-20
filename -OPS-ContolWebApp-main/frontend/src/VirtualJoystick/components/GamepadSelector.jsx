import React, { useState, useEffect } from "react";

function GamepadSelector({ backendUrl, onSelect }) {
  const [gamepads, setGamepads] = useState([]);
  const [selected, setSelected] = useState(null);
  const [status, setStatus] = useState("");

  useEffect(() => {
    fetch(`${backendUrl}/gamepads`)
      .then(res => res.json())
      .then(data => setGamepads(data.gamepads || []));
  }, [backendUrl]);

  const handleSelect = idx => {
    fetch(`${backendUrl}/gamepads/select`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ index: idx })
    })
      .then(res => res.json())
      .then(data => {
        setSelected(idx);
        setStatus("Pad selected!");
        if (onSelect) onSelect(idx);
      })
      .catch(() => setStatus("Błąd połączenia z backendem"));
  };

  return (
    <div style={{ margin: "1rem 0" }}>
      <h4>Wybierz pada Bluetooth (Jetson):</h4>
      <ul style={{ listStyle: "none", padding: 0 }}>
        {gamepads.map((g, i) => (
          <li key={g}>
            <button
              style={{
                background: selected === i ? "#007bff" : "#eee",
                color: selected === i ? "white" : "black",
                margin: "0.25rem",
                padding: "0.5rem 1rem",
                borderRadius: "5px",
                border: "1px solid #aaa",
                cursor: "pointer"
              }}
              onClick={() => handleSelect(i)}
            >
              {g}
            </button>
          </li>
        ))}
      </ul>
      {status && <div style={{ color: "#28a745", marginTop: "0.5rem" }}>{status}</div>}
    </div>
  );
}

export default GamepadSelector;
