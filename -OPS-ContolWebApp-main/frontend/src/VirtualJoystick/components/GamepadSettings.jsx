import React from "react";

// Lista dostępnych przycisków w standardzie Gamepad API
const availableButtons = [
  { value: 0, label: "A / Krzyżyk (0)" },
  { value: 1, label: "B / Kółko (1)" },
  { value: 2, label: "X / Kwadrat (2)" },
  { value: 3, label: "Y / Trójkąt (3)" },
  { value: 4, label: "LB / L1 (4)" },
  { value: 5, label: "RB / R1 (5)" },
  { value: 12, label: "Strzałka Góra (12)" },
  { value: 13, label: "Strzałka Dół (13)" },
  { value: 14, label: "Strzałka Lewo (14)" },
  { value: 15, label: "Strzałka Prawo (15)" },
];

const GamepadSettings = ({ config, onSave }) => {
  if (!config || !config.mapping) return null;

  const update = (field, value) => {
    onSave({
      ...config,
      mapping: { ...config.mapping, [field]: value }
    });
  };

  // Pomocnicza funkcja do renderowania selectów dla przycisków
  const renderButtonSelect = (label, fieldKey) => (
    <div className="input-group" style={{ marginBottom: '10px' }}>
      <label style={{ display: 'inline-block', width: '120px', fontWeight: '500' }}>
        {label}:
      </label>
      <select 
        value={config.mapping[fieldKey] ?? 0} // Domyślnie 0 jeśli brak w configu
        onChange={(e) => update(fieldKey, parseInt(e.target.value))}
        style={{ padding: '4px', borderRadius: '4px', border: '1px solid #ccc' }}
      >
        {availableButtons.map((btn) => (
          <option key={btn.value} value={btn.value}>
            {btn.label}
          </option>
        ))}
      </select>
    </div>
  );

  return (
    <div className="settings-card" style={{ background: '#eee', padding: '20px', borderRadius: '8px', maxWidth: '400px' }}>
      <h3 style={{ marginTop: 0 }}>Ustawienia Kontrolera</h3>

      {/* --- SEKCJA ANALOGÓW --- */}
      <div style={{ marginBottom: '20px', borderBottom: '1px solid #ccc', paddingBottom: '15px' }}>
        <h4 style={{ marginBottom: '10px' }}>Konfiguracja Drążków</h4>
        
        <div className="input-group" style={{ marginBottom: '10px' }}>
          <label style={{ display: 'block', marginBottom: '5px' }}>Jazda (Pionowo):</label>
          <select 
            value={config.mapping.linearAxis} 
            onChange={(e) => update('linearAxis', parseInt(e.target.value))}
            style={{ width: '100%', padding: '5px' }}
          >
            <option value={1}>Lewy Analog (Oś 1)</option>
            <option value={3}>Prawy Analog (Oś 3)</option>
          </select>
        </div>

        <div className="input-group">
          <label style={{ display: 'block', marginBottom: '5px' }}>Skręcanie (Poziomo):</label>
          <select 
            value={config.mapping.angularAxis} 
            onChange={(e) => update('angularAxis', parseInt(e.target.value))}
            style={{ width: '100%', padding: '5px' }}
          >
            <option value={0}>Lewy Analog (Oś 0)</option>
            <option value={2}>Prawy Analog (Oś 2)</option>
          </select>
        </div>
      </div>

      {/* --- SEKCJA PRZYCISKÓW --- */}
      <div>
        <h4 style={{ marginBottom: '10px' }}>Mapowanie Przycisków</h4>
        
        {/* Podstawowe przyciski */}
        {renderButtonSelect("Przycisk A", "btnA")}
        {renderButtonSelect("Przycisk B", "btnB")}
        {renderButtonSelect("Przycisk X", "btnX")}
        {renderButtonSelect("Przycisk Y", "btnY")}
        
        <div style={{ height: '10px' }}></div> {/* Odstęp */}
        
        {/* Bumpers */}
        {renderButtonSelect("Bumper LB", "btnLB")}
        {renderButtonSelect("Bumper RB", "btnRB")}

        {/* Opcjonalne Strzałki (D-Pad) */}
        <details style={{ marginTop: '10px', cursor: 'pointer' }}>
          <summary style={{ fontSize: '12px', color: '#555' }}>Pokaż ustawienia strzałek (D-Pad)</summary>
          <div style={{ marginTop: '10px', paddingLeft: '10px', borderLeft: '2px solid #ccc' }}>
            {renderButtonSelect("Strzałka Góra", "dpadUp")}
            {renderButtonSelect("Strzałka Dół", "dpadDown")}
            {renderButtonSelect("Strzałka Lewo", "dpadLeft")}
            {renderButtonSelect("Strzałka Prawo", "dpadRight")}
          </div>
        </details>
      </div>

      <p style={{ fontSize: '11px', color: '#666', marginTop: '20px', borderTop: '1px solid #ddd', paddingTop: '10px' }}>
        Zmienione mapowanie zostanie zapisane w pliku konfiguracyjnym.
      </p>
    </div>
  );
};

export default GamepadSettings;