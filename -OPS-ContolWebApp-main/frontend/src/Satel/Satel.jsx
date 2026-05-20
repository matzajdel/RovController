import { useState } from "react";
import { useSatel } from "../context/SatelContext";
import "./Satel.css";

export default function Satel() {
    const { satelEnabled, setSatelEnabled, satel } = useSatel();

    const [baud, setBaud] = useState(9600);
    const [testMessage, setTestMessage] = useState('{"t":"stop"}');
    const [slCommand, setSlCommand] = useState('SL@R?');

    const handleConnect = async () => {
        await satel.connect(+baud);
    };

    const handleDisconnect = async () => {
        await satel.disconnect();
    };

    const handleTestSend = () => {
        if (satel.isConnected) {
            satel.sendRaw(testMessage + "\n");
        }
    };

    const handleSlCommand = (cmd) => {
        if (satel.isConnected) {
            // Komendy SL dla Satel TA13 zwykle kończą się znakiem CR (\r)
            satel.sendRaw(cmd + "\r");
        }
    };

    return (
        <div className="satel-page">
            <div className="satel-header">
                <div className="satel-header__icon">📡</div>
                <div className="satel-header__text">
                    <h1>Satel TA13 Bridge</h1>
                    <p>Pełna komunikacja radiowa RS-232 (SATELLINE-Easy)</p>
                </div>
            </div>

            <div className="satel-info-bar">
                <span className="satel-badge">Satel TA13</span>
                {satel.isSupported
                    ? <span className="satel-badge" style={{ color: "#22c55e", borderColor: "rgba(34,197,94,.3)", background: "rgba(34,197,94,.1)" }}>🔌 Web Serial OK</span>
                    : <span className="satel-badge" style={{ color: "#ef4444", borderColor: "rgba(239,68,68,.3)", background: "rgba(239,68,68,.1)" }}>⚠ Chrome/Edge only</span>
                }
                {satel.isConnected && <span className="satel-badge" style={{ color: "#22c55e", borderColor: "rgba(34,197,94,.3)", background: "rgba(34,197,94,.1)" }}>✅ Port połączony</span>}
            </div>

            <div className="satel-grid">
                {/* === KARTA: Tryb Pracy === */}
                <div className="satel-card satel-card--highlight">
                    <h3 className="satel-card__title"><span className="satel-card__icon">⚙️</span>Główny Wyłącznik</h3>
                    
                    <div className="satel-toggle-row" style={{ marginTop: "1.5rem", marginBottom: "2rem" }}>
                        <input
                            id="global-satel-toggle"
                            type="checkbox"
                            className="satel-toggle satel-toggle--large"
                            checked={satelEnabled}
                            onChange={(e) => setSatelEnabled(e.target.checked)}
                        />
                        <label htmlFor="global-satel-toggle" className="satel-toggle-label" style={{ fontSize: "1.1rem", fontWeight: "600", color: satelEnabled ? "#ffa000" : "#8b95a7" }}>
                            {satelEnabled ? "TRYB SATEL: WŁĄCZONY" : "TRYB SATEL: WYŁĄCZONY"}
                        </label>
                    </div>
                    <p style={{ fontSize: "0.8rem", color: "#8b95a7", marginBottom: "1.5rem" }}>
                        Gdy włączone, <strong>wszystkie</strong> pakiety (sterowanie, LED, GPS, manipulator) są kierowane przez radiomodem Satel zamiast przez backend HTTP.
                    </p>

                    <label className="satel-label">Web Serial API</label>
                    <div className="satel-row">
                        <div>
                            <label className="satel-label">Baud Rate</label>
                            <select className="satel-select" value={baud} onChange={(e) => setBaud(+e.target.value)} disabled={satel.isConnected}>
                                {[1200, 2400, 4800, 9600, 19200, 38400, 115200].map((b) => <option key={b} value={b}>{b}</option>)}
                            </select>
                        </div>
                        <div style={{ display: "flex", flexDirection: "column", justifyContent: "flex-end", paddingBottom: "0.9rem" }}>
                            {!satel.isConnected
                                ? <button className="satel-btn satel-btn--primary" onClick={handleConnect} disabled={!satel.isSupported}>🔌 Połącz Radio</button>
                                : <button className="satel-btn satel-btn--danger" onClick={handleDisconnect}>Rozłącz</button>
                            }
                        </div>
                    </div>
                    {satel.error && <div className="satel-result satel-result--error"><div className="satel-result__header">⛔ {satel.error}</div></div>}
                </div>

                {/* === KARTA: Monitor Sieci === */}
                <div className="satel-card">
                    <h3 className="satel-card__title"><span className="satel-card__icon">📊</span>Monitor Sieci Satel</h3>
                    
                    <div style={{ display: "flex", gap: "1rem", marginBottom: "1.5rem" }}>
                        <div style={{ flex: 1, background: "rgba(0,0,0,0.3)", padding: "1rem", borderRadius: "8px", border: "1px solid rgba(255,160,0,0.2)" }}>
                            <div className="satel-label">Pakiety Wysłane</div>
                            <div style={{ fontSize: "1.5rem", fontWeight: "bold", color: "#ffa000", fontFamily: "monospace" }}>
                                {satel.stats.totalPackets}
                            </div>
                            <div style={{ fontSize: "0.8rem", color: "#8b95a7", marginTop: "0.5rem" }}>
                                {satel.stats.packetsPerSec.toFixed(1)} pkt/s
                            </div>
                        </div>
                        <div style={{ flex: 1, background: "rgba(0,0,0,0.3)", padding: "1rem", borderRadius: "8px", border: "1px solid rgba(255,160,0,0.2)" }}>
                            <div className="satel-label">Dane Wysłane</div>
                            <div style={{ fontSize: "1.5rem", fontWeight: "bold", color: "#ffa000", fontFamily: "monospace" }}>
                                {(satel.stats.totalBytes / 1024).toFixed(2)} KB
                            </div>
                            <div style={{ fontSize: "0.8rem", color: "#8b95a7", marginTop: "0.5rem" }}>
                                {satel.stats.bytesPerSec} B/s
                            </div>
                        </div>
                    </div>

                    <label className="satel-label">Ostatnio Wysłany Pakiet</label>
                    <div className="satel-result__decoded" style={{ minHeight: "2.5rem" }}>
                        {satel.lastSent || "brak"}
                    </div>

                    <label className="satel-label" style={{ marginTop: "1rem" }}>Test Wyślij</label>
                    <div className="satel-row">
                        <input className="satel-input" value={testMessage} onChange={e => setTestMessage(e.target.value)} style={{ marginBottom: 0 }} />
                        <button className="satel-btn satel-btn--secondary" onClick={handleTestSend} disabled={!satel.isConnected} style={{ width: "auto" }}>Wyślij</button>
                    </div>
                </div>

                {/* === KARTA: Architektura === */}
                <div className="satel-card satel-status-card">
                    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                        <h3 className="satel-card__title" style={{ margin: 0 }}><span className="satel-card__icon">🗺</span>Architektura Mostu</h3>
                        <button className="satel-btn satel-btn--secondary" onClick={satel.resetStats} style={{ width: "auto", padding: "0.3rem 0.8rem", fontSize: "0.7rem" }}>Reset Statystyk</button>
                    </div>
                    
                    <div className="satel-result__decoded" style={{ fontSize: "0.8rem", lineHeight: "1.8", marginTop: "1rem", marginBottom: "0.8rem" }}>
                        {`Baza:  Web App → RS-232 → Satel TA13 → 📻 radio\n` +
                         `Łazik: 📻 radio → Satel TA13 → RS-232 → rover_satel_bridge.py → ROS2`}
                    </div>
                    <label className="satel-label">Uruchom na łaziku</label>
                    <div className="satel-result__decoded" style={{ fontSize: "0.74rem" }}>
                        python3 rover_satel_bridge.py --port /dev/ttyUSB0 --baud 9600
                    </div>

                    {satel.received.length > 0 && (
                        <div style={{ marginTop: "1rem" }}>
                            <label className="satel-label">Odebrane pakiety (RX)</label>
                            <div style={{ display: "flex", flexDirection: "column", gap: "0.3rem", maxHeight: "140px", overflowY: "auto" }}>
                                {satel.received.map((r, i) => (
                                    <div key={i} style={{ display: "flex", alignItems: "center", gap: "0.6rem", fontSize: "0.75rem" }}>
                                        <span style={{ color: "#4b5563", flexShrink: 0 }}>{new Date(r.ts).toLocaleTimeString()}</span>
                                        <span>{r.parsed ? "✅" : "❌"}</span>
                                        <code className="satel-result__decoded" style={{ flex: 1, marginBottom: 0, padding: "0.15rem 0.5rem", fontSize: "0.72rem" }}>{r.raw}</code>
                                    </div>
                                ))}
                            </div>
                        </div>
                    )}
                </div>

                {/* === KARTA: Konfiguracja Modemu (SL) === */}
                <div className="satel-card">
                    <h3 className="satel-card__title"><span className="satel-card__icon">🛠️</span>Ustawienia Modemu (SL)</h3>
                    <p style={{ fontSize: "0.8rem", color: "#8b95a7", marginBottom: "1rem" }}>
                        Satel TA13 można konfigurować wysyłając komendy SL (wymaga włączonej obsługi komend SL w modemie). 
                        Odpowiedzi pojawią się w "Odebrane pakiety (RX)".
                    </p>

                    <div style={{ display: "flex", gap: "0.5rem", marginBottom: "1.5rem", flexWrap: "wrap" }}>
                        <button className="satel-btn satel-btn--secondary" onClick={() => handleSlCommand("SL@R?")} disabled={!satel.isConnected} style={{ width: "auto", flex: "1 1 auto", fontSize: "0.8rem" }}>
                            Odczytaj Wszystko (SL@R?)
                        </button>
                        <button className="satel-btn satel-btn--secondary" onClick={() => handleSlCommand("SL@F?")} disabled={!satel.isConnected} style={{ width: "auto", flex: "1 1 auto", fontSize: "0.8rem" }}>
                            Odczytaj Freq (SL@F?)
                        </button>
                        <button className="satel-btn satel-btn--secondary" onClick={() => handleSlCommand("SL@P?")} disabled={!satel.isConnected} style={{ width: "auto", flex: "1 1 auto", fontSize: "0.8rem" }}>
                            Odczytaj Moc (SL@P?)
                        </button>
                    </div>

                    <label className="satel-label">Własna komenda SL (np. SLA869.4000)</label>
                    <div className="satel-row">
                        <input className="satel-input" value={slCommand} onChange={e => setSlCommand(e.target.value)} style={{ marginBottom: 0, textTransform: "uppercase" }} placeholder="SLA..." />
                        <button className="satel-btn satel-btn--primary" onClick={() => handleSlCommand(slCommand)} disabled={!satel.isConnected} style={{ width: "auto" }}>Wyślij SL</button>
                    </div>
                </div>
            </div>
        </div>
    );
}
