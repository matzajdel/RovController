import React from "react";
import { useSteering } from "../../context/SteeringContext";

function GamepadDiagnostics() {
  const { liveGamepad, driveMode, DRIVE_MODES } = useSteering();
  const { rightX, rightY, leftX = 0, leftY = 0, rt, rb, lt = false, connected, twist, isSafetyStopActive,
    rawButtons = [], gamepadId = "",
    parsedPid = null, pidProfilePid = null, watchedBtnIndices = [] } = liveGamepad;

  const driveName = Object.values(DRIVE_MODES).find(m => m.id === driveMode)?.name || "?";

  return (
    <div className="diag-box" style={{
      border: '2px solid #555', padding: '15px', marginTop: '20px',
      borderRadius: '12px', background: 'rgba(0,0,0,0.3)', color: '#e2e8f0',
      fontFamily: 'monospace',
    }}>
      <h4 style={{ margin: '0 0 10px 0', color: '#fbbf24' }}>HARDWARE CHECK — Prawa gałka + RT</h4>
      {!connected ? (
        <p style={{ color: 'orange' }}>
          ⚠ Pad nieaktywny. Naciśnij przycisk na padzie, potem wybierz tryb Sterowanie!
        </p>
      ) : isSafetyStopActive ? (
        <p style={{ color: '#ef4444', fontWeight: 'bold', fontSize: '1.2em', textAlign: 'center', border: '2px solid #ef4444', padding: '10px', borderRadius: '8px' }}>
          🛑 SAFETY STOP AKTYWNY 🛑<br/>
          <span style={{ fontSize: '0.8em' }}>LT: {lt ? 'WCIŚNIĘTY' : 'NIE'}</span><br/>
          <span style={{ fontSize: '0.8em' }}>Wszystkie osie wymuszone na 0.000</span>
        </p>
      ) : (
        <div>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '8px' }}>
            <p>Prawa gałka X: <b style={{ color: '#60a5fa' }}>{rightX.toFixed(2)}</b></p>
            <p>Prawa gałka Y: <b style={{ color: '#60a5fa' }}>{rightY.toFixed(2)}</b></p>
            <p>Lewa gałka X (obrót): <b style={{ color: '#c084fc' }}>{leftX.toFixed(2)}</b></p>
            <p>Lewa gałka Y: <b style={{ color: '#c084fc' }}>{leftY.toFixed(2)}</b></p>
            <p>RT (gaz): <b style={{ color: rt > 0.05 ? '#4ade80' : '#94a3b8' }}>{rt.toFixed(2)}</b></p>
            <p>RB (reverse): <b style={{ color: rb ? '#f87171' : '#94a3b8' }}>{rb ? 'TAK' : 'NIE'}</b></p>
            <p>LT (stop): <b style={{ color: lt ? '#ef4444' : '#94a3b8' }}>{lt ? 'TAK' : 'NIE'}</b></p>
          </div>
          <hr style={{ borderColor: 'rgba(255,255,255,0.1)', margin: '10px 0' }} />
          <p style={{ color: '#4ade80', fontWeight: 'bold', margin: '0 0 6px 0' }}>
            WYSYŁANE NA CMD_VEL (tryb: {driveName}):
          </p>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: '4px' }}>
            <p>linear.x: <b>{twist.linear_x.toFixed(3)}</b></p>
            <p>linear.y: <b>{twist.linear_y.toFixed(3)}</b></p>
            <p>angular.z: <b>{twist.angular_z.toFixed(3)}</b></p>
          </div>
          <hr style={{ borderColor: 'rgba(255,255,255,0.1)', margin: '10px 0' }} />
          <p style={{ color: '#94a3b8', fontSize: '0.75em', margin: '0 0 4px 0', wordBreak: 'break-all' }}>
            ID: {gamepadId || '—'}
          </p>
          <p style={{ fontSize: '0.75em', margin: '2px 0' }}>
            Parsed PID:{' '}
            <b style={{ color: parsedPid ? '#60a5fa' : '#ef4444' }}>{parsedPid || 'nie rozpoznano'}</b>
            {' '}→ profil:{' '}
            <b style={{ color: pidProfilePid && pidProfilePid !== '*' ? '#4ade80' : '#f97316' }}>
              {pidProfilePid || 'brak'}
            </b>
            {pidProfilePid === '*' && <span style={{ color: '#f97316' }}> (fallback)</span>}
          </p>
          {watchedBtnIndices.length > 0 && (
            <p style={{ fontSize: '0.75em', margin: '2px 0', color: '#94a3b8' }}>
              Obserwowane indeksy: [{watchedBtnIndices.join(', ')}]
            </p>
          )}
          {rawButtons.length > 0 && (
            <>
              <p style={{ color: '#fbbf24', fontWeight: 'bold', margin: '6px 0 4px 0', fontSize: '0.85em' }}>
                RAW BUTTONS (indeks → wciśnięty):
              </p>
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: '4px' }}>
                {rawButtons.map((pressed, idx) => (
                  pressed ? (
                    <span key={idx} style={{
                      background: '#16a34a', color: '#fff', borderRadius: '4px',
                      padding: '2px 6px', fontSize: '0.78em', fontWeight: 'bold',
                    }}>
                      [{idx}]
                    </span>
                  ) : null
                ))}
                {rawButtons.every(b => !b) && (
                  <span style={{ color: '#64748b', fontSize: '0.78em' }}>brak wciśniętych przycisków</span>
                )}
              </div>
            </>
          )}
        </div>
      )}
    </div>
  );
}

export default GamepadDiagnostics;