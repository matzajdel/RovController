/**
 * LED — URC 2026 Rover LED Control Panel
 *
 * URC 2026 §1.f.vi — LED na tyle rovera:
 *  🔴 Czerwony        → Autonomia
 *  🔵 Niebieski       → Teleoperacja
 *  💚 Zielony migający → Dotarcie do celu
 */

import { useState, useEffect, useCallback } from "react";
import { BACKEND_URL } from "../config";
import { useSatel } from "../context/SatelContext";
import "./Led.css";

const API = BACKEND_URL;

async function apiFetch(path, opts = {}) {
    try {
        const res = await fetch(`${API}${path}`, {
            headers: { "Content-Type": "application/json" },
            ...opts,
        });
        return res.json();
    } catch (e) {
        return { status: "error", detail: String(e) };
    }
}

// ---------------------------------------------------------------------------
// URC LED presets per §1.f.vi
// ---------------------------------------------------------------------------
const URC_PRESETS = [
    {
        id: "autonomous",
        label: "🔴 AUTONOMIA",
        sublabel: "Autonomous operation",
        endpoint: "/led/autonomous",
        color: "#ef4444",
        glowColor: "rgba(239,68,68,0.4)",
        borderColor: "rgba(239,68,68,0.5)",
        bg: "rgba(239,68,68,0.08)",
        flash: false,
    },
    {
        id: "teleop",
        label: "🔵 TELEOPERACJA",
        sublabel: "Teleoperation (manual driving)",
        endpoint: "/led/teleop",
        color: "#3b82f6",
        glowColor: "rgba(59,130,246,0.4)",
        borderColor: "rgba(59,130,246,0.5)",
        bg: "rgba(59,130,246,0.08)",
        flash: false,
    },
    {
        id: "arrived",
        label: "💚 DOTARCIE",
        sublabel: "Flashing Green — arrived at target",
        endpoint: "/led/arrived",
        color: "#22c55e",
        glowColor: "rgba(34,197,94,0.4)",
        borderColor: "rgba(34,197,94,0.5)",
        bg: "rgba(34,197,94,0.08)",
        flash: true,
    },
    {
        id: "off",
        label: "⬛ WYŁĄCZ",
        sublabel: "LED off",
        endpoint: "/led/off",
        color: "#4b5563",
        glowColor: "rgba(75,85,99,0.2)",
        borderColor: "rgba(75,85,99,0.3)",
        bg: "rgba(75,85,99,0.05)",
        flash: false,
    },
];

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

function LedPreviewDot({ activeId, preset, animTick }) {
    const isActive = activeId === preset.id;
    const isFlashing = isActive && preset.flash;
    const visible = !isFlashing || animTick % 2 === 0;

    return (
        <div
            className="led-dot"
            style={{
                background: isActive && visible ? preset.color : "rgba(255,255,255,0.06)",
                boxShadow: isActive && visible ? `0 0 18px 6px ${preset.glowColor}` : "none",
                border: `2px solid ${isActive ? preset.borderColor : "rgba(255,255,255,0.1)"}`,
                transition: isFlashing ? "none" : "all 0.3s ease",
            }}
        />
    );
}

function LedPresetButton({ preset, isActive, onClick, loading }) {
    return (
        <button
            id={`led-btn-${preset.id}`}
            className={`led-preset-btn ${isActive ? "led-preset-btn--active" : ""}`}
            style={{
                "--preset-color": preset.color,
                "--preset-glow": preset.glowColor,
                "--preset-border": preset.borderColor,
                "--preset-bg": preset.bg,
            }}
            onClick={onClick}
            disabled={loading}
        >
            <div className="led-preset-btn__label">{preset.label}</div>
            <div className="led-preset-btn__sub">{preset.sublabel}</div>
            {isActive && <div className="led-preset-btn__active-dot" />}
        </button>
    );
}

// ---------------------------------------------------------------------------
// Main
// ---------------------------------------------------------------------------
export default function Led() {
    const [activeId, setActiveId] = useState(null);
    const [lastResult, setLastResult] = useState(null);
    const [loading, setLoading] = useState(false);
    const [animTick, setAnimTick] = useState(0);
    const { satelEnabled, satel } = useSatel();

    // Fetch current state on mount
    useEffect(() => {
        apiFetch("/led/state").then((d) => {
            if (d.status === "ok") {
                // Map color back to preset id
                const colorMap = {
                    red: "autonomous",
                    blue: "teleop",
                    green: "arrived",
                    none: "off",
                };
                setActiveId(colorMap[d.color] ?? null);
            }
        });
    }, []);

    // Flash animation tick (500ms)
    useEffect(() => {
        const id = setInterval(() => setAnimTick((t) => t + 1), 500);
        return () => clearInterval(id);
    }, []);

    const handlePreset = useCallback(async (preset) => {
        setLoading(true);
        if (satelEnabled && satel.isConnected) {
            const stateMap = {
                autonomous: [1, 255, 0, 0],
                teleop: [1, 0, 0, 255],
                arrived: [2, 0, 255, 0],
                off: [0, 0, 0, 0]
            };
            const ledState = stateMap[preset.id] || [0, 0, 0, 0];
            satel.sendLed(ledState);
            setLastResult({ 
                status: "success", 
                urc_meaning: preset.label, 
                led_state: ledState, 
                ros_published: true, 
                preset: preset.id 
            });
            setActiveId(preset.id);
        } else {
            const res = await apiFetch(preset.endpoint, { method: "POST" });
            setLastResult({ ...res, preset: preset.id });
            if (res.status === "success" || res.ros_published !== undefined) {
                setActiveId(preset.id);
            }
        }
        setLoading(false);
    }, [satelEnabled, satel]);

    const activePreset = URC_PRESETS.find((p) => p.id === activeId);

    return (
        <div className="led-page">
            {/* Header */}
            <div className="led-header">
                <div className="led-header__preview">
                    {URC_PRESETS.filter((p) => p.id !== "off").map((p) => (
                        <LedPreviewDot
                            key={p.id}
                            preset={p}
                            activeId={activeId}
                            animTick={animTick}
                        />
                    ))}
                </div>
                <div className="led-header__text">
                    <h1>LED Control</h1>
                    <p>URC 2026 §1.f.vi — Rover Status Indicator</p>
                </div>
            </div>

            {/* Active state badge */}
            <div className="led-status-bar">
                <div
                    className="led-status-badge"
                    style={{
                        color: activePreset?.color ?? "#6b7280",
                        borderColor: activePreset?.borderColor ?? "rgba(107,114,128,.3)",
                        background: activePreset?.bg ?? "rgba(107,114,128,.05)",
                        animation: activePreset?.flash ? "ledFlash 1s ease-in-out infinite" : "none",
                    }}
                >
                    Aktywny:{" "}
                    <strong>{activePreset?.label ?? "—"}</strong>
                </div>
                <div className="led-urc-ref">
                    Wymaganie URC 2026 §1.f.vi
                </div>
            </div>

            {/* Main grid */}
            <div className="led-grid">

                {/* Preset buttons */}
                <div className="led-card led-card--presets">
                    <h3 className="led-card__title">
                        <span>🚦</span> Tryby LED (URC)
                    </h3>

                    <div className="led-presets">
                        {URC_PRESETS.map((preset) => (
                            <LedPresetButton
                                key={preset.id}
                                preset={preset}
                                isActive={activeId === preset.id}
                                onClick={() => handlePreset(preset)}
                                loading={loading}
                            />
                        ))}
                    </div>

                    {lastResult && (
                        <div
                            className={`led-result ${lastResult.status === "success" ? "led-result--ok" : "led-result--error"}`}
                            style={{ marginTop: "1rem" }}
                        >
                            <div className="led-result__header">
                                {lastResult.status === "success" ? "✅ Wysłano" : "⛔ Błąd"}
                            </div>
                            <div className="led-result__body">
                                {lastResult.urc_meaning && (
                                    <div>URC: <strong>{lastResult.urc_meaning}</strong></div>
                                )}
                                {lastResult.led_state && (
                                    <code>[{lastResult.led_state.join(", ")}]</code>
                                )}
                                {lastResult.detail && <div>{lastResult.detail}</div>}
                                <div style={{ fontSize: "0.72rem", color: "#4b5563", marginTop: "0.3rem" }}>
                                    ROS: {lastResult.ros_published ? "✅ opublikowano" : "⚠ brak ROS node"}
                                </div>
                            </div>
                        </div>
                    )}
                </div>

                {/* URC rules reference */}
                <div className="led-card">
                    <h3 className="led-card__title">
                        <span>📋</span> Zasady URC 2026
                    </h3>
                    <div className="led-rules">
                        <div className="led-rule">
                            <div className="led-rule__dot" style={{ background: "#ef4444", boxShadow: "0 0 8px rgba(239,68,68,.6)" }} />
                            <div className="led-rule__text">
                                <strong>Czerwony</strong> — tryb autonomiczny
                                <div className="led-rule__ref">§1.f.vi: Red: Autonomous operation</div>
                            </div>
                        </div>
                        <div className="led-rule">
                            <div className="led-rule__dot" style={{ background: "#3b82f6", boxShadow: "0 0 8px rgba(59,130,246,.6)" }} />
                            <div className="led-rule__text">
                                <strong>Niebieski</strong> — teleoperacja
                                <div className="led-rule__ref">§1.f.vi: Blue: Teleoperation (manually driving)</div>
                            </div>
                        </div>
                        <div className="led-rule">
                            <div className="led-rule__dot" style={{ background: "#22c55e", boxShadow: "0 0 8px rgba(34,197,94,.6)", animation: "ledPulse 1s ease-in-out infinite" }} />
                            <div className="led-rule__text">
                                <strong>Zielony migający</strong> — dotarcie do celu
                                <div className="led-rule__ref">§1.f.vi: Flashing Green: Successful arrival at target</div>
                            </div>
                        </div>
                        <div className="led-rule-note">
                            💡 LED musi być widoczny w pełnym słońcu (LED array lub high power LED) i umieszczony z tyłu rovera.
                        </div>
                    </div>

                    <div style={{ marginTop: "1.2rem", borderTop: "1px solid rgba(255,255,255,.06)", paddingTop: "0.8rem" }}>
                        <h4 className="led-card__subtitle">Protokół ROS</h4>
                        <div className="led-code-block">
                            {`Topic: /ESP32_GIZ/led_state_topic\nType:  Int32MultiArray\n\nFormat: [mode, r, g, b]\n  mode 0 = off\n  mode 1 = solid\n  mode 2 = flash (migający)\n\nTeleop:      [1, 0,   0,   255]\nAutonomia:   [1, 255, 0,   0  ]\nDotarcie:    [2, 0,   255, 0  ]\nWyłączony:   [0, 0,   0,   0  ]`}
                        </div>
                    </div>
                </div>

            </div>
        </div>
    );
}
