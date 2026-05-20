/**
 * GamepadStatusBar — Pasek statusu pada Xbox
 * ==========================================
 * Pokazuje:
 *  - Status połączenia (🟢 / 🟠)
 *  - Nazwę pada
 *  - Live wartości: RT (gaz), Prawa gałka X/Y, RB
 *  - Aktualne cmd_vel: linear.x, linear.y, angular.z
 */
import React from "react";
import { useSteering } from "../../context/SteeringContext";
import "./GamepadStatusBar.css";

const Bar = ({ value, max = 1, color = "#4ade80" }) => {
    const pct = Math.abs(value / max) * 100;
    return (
        <div className="gsb-bar-track">
            <div
                className="gsb-bar-fill"
                style={{ width: `${pct}%`, background: color }}
            />
        </div>
    );
};

const GsbValue = ({ label, value, max, color, unit = "" }) => (
    <div className="gsb-value-cell">
        <span className="gsb-label">{label}</span>
        <span className="gsb-num" style={{ color }}>
            {typeof value === "number" ? value.toFixed(2) : value}
            {unit}
        </span>
        {max !== undefined && <Bar value={value} max={max} color={color} />}
    </div>
);

function GamepadStatusBar() {
    const { liveGamepad, xboxGamepad, rosBridgeConnected } = useSteering();

    // Fallback jeśli xboxGamepad nie jest jeszcze w kontekście
    const pad = xboxGamepad || liveGamepad;
    const connected = pad?.connected || false;
    const padName = xboxGamepad?.padName || "";
    const isXbox = xboxGamepad?.isXbox || false;

    const { rightX = 0, rightY = 0, rt = 0, rb = false, twist = {} } = liveGamepad || {};
    const { linear_x = 0, linear_y = 0, angular_z = 0 } = twist;

    // Skrócona nazwa pada (max 40 znaków)
    const shortName = padName.length > 40 ? padName.slice(0, 40) + "…" : padName;

    return (
        <div className={`gsb-container ${connected ? "gsb-connected" : "gsb-disconnected"}`}>
            {/* ── Nagłówek ── */}
            <div className="gsb-header">
                <div className="gsb-status-row">
                    <span className={`gsb-dot ${connected ? "gsb-dot-on" : "gsb-dot-off"}`} />
                    <span className="gsb-title">
                        {connected
                            ? (isXbox ? "🎮 Xbox Controller" : "🎮 Gamepad")
                            : "🎮 Brak pada"}
                    </span>
                    {connected && shortName && (
                        <span className="gsb-name" title={padName}>{shortName}</span>
                    )}
                    {/* RosBridge status */}
                    <span className={`gsb-ros ${rosBridgeConnected ? "gsb-ros-ok" : "gsb-ros-err"}`}>
                        ROS {rosBridgeConnected ? "✓" : "✗"}
                    </span>
                </div>

                {!connected && (
                    <p className="gsb-hint">
                        ⚠ Podłącz pada Xbox przez USB, a następnie naciśnij dowolny przycisk.
                    </p>
                )}
            </div>

            {/* ── Live dane (tylko gdy pad połączony) ── */}
            {connected && (
                <div className="gsb-data">
                    {/* Wejścia */}
                    <div className="gsb-section">
                        <span className="gsb-section-title">WEJŚCIE PADA</span>
                        <div className="gsb-grid">
                            <GsbValue label="RT (gaz)" value={rt} max={1} color={rt > 0.05 ? "#4ade80" : "#64748b"} />
                            <GsbValue label="Gałka X" value={rightX} max={1} color="#60a5fa" />
                            <GsbValue label="Gałka Y" value={rightY} max={1} color="#60a5fa" />
                            <div className="gsb-value-cell">
                                <span className="gsb-label">RB (wstecz)</span>
                                <span className="gsb-num" style={{ color: rb ? "#f87171" : "#64748b" }}>
                                    {rb ? "TAK" : "NIE"}
                                </span>
                            </div>
                        </div>
                    </div>

                    {/* cmd_vel */}
                    <div className="gsb-section">
                        <span className="gsb-section-title">CMD_VEL</span>
                        <div className="gsb-grid">
                            <GsbValue label="linear.x" value={linear_x} max={6} color={Math.abs(linear_x) > 0.01 ? "#34d399" : "#64748b"} unit=" m/s" />
                            <GsbValue label="linear.y" value={linear_y} max={6} color={Math.abs(linear_y) > 0.01 ? "#34d399" : "#64748b"} unit=" m/s" />
                            <GsbValue label="angular.z" value={angular_z} max={6} color={Math.abs(angular_z) > 0.01 ? "#fbbf24" : "#64748b"} unit=" r/s" />
                        </div>
                    </div>
                </div>
            )}
        </div>
    );
}

export default GamepadStatusBar;
