import React, { useState, useEffect } from 'react';
import { useSearchParams } from 'react-router-dom';
import { BACKEND_CONFIG } from '../VirtualJoystick/Constants';

export const MicroRosLogs = () => {
    const [searchParams] = useSearchParams();
    const session = searchParams.get('session');
    const [logs, setLogs] = useState([]);
    const [status, setStatus] = useState("Connecting...");
    const API = BACKEND_CONFIG.BACKEND_URL || "http://127.0.0.1:2137";

    useEffect(() => {
        if (!session) return;

        const fetchLogs = async () => {
            try {
                const response = await fetch(`${API}/ssh/logs/${session}`);
                if (response.ok) {
                    const data = await response.json();
                    setLogs(data.logs || []);
                    setStatus(data.running ? "Running" : "Stopped");
                } else {
                    setStatus("Session not found");
                }
            } catch (error) {
                console.error("Error fetching logs:", error);
                setStatus("Error connecting to backend");
            }
        };

        fetchLogs();
        const interval = setInterval(fetchLogs, 2000); // Poll every 2 seconds

        return () => clearInterval(interval);
    }, [session]);

    if (!session) return <div style={{ padding: 20, color: 'white', background: '#222' }}>No session specified</div>;

    return (
        <div style={{
            background: '#1a1a1a',
            color: '#e0e0e0',
            minHeight: '100vh',
            display: 'flex',
            flexDirection: 'column',
            fontFamily: 'monospace'
        }}>
            <div style={{
                padding: '10px 20px',
                background: '#333',
                borderBottom: '1px solid #444',
                display: 'flex',
                justifyContent: 'space-between',
                alignItems: 'center',
                position: 'sticky',
                top: 0
            }}>
                <h2 style={{ margin: 0, fontSize: '1.2rem' }}>Logs: {session}</h2>
                <span style={{
                    padding: '4px 8px',
                    borderRadius: '4px',
                    background: status === 'Running' ? '#2e7d32' : '#c62828',
                    color: 'white',
                    fontWeight: 'bold',
                    fontSize: '0.9rem'
                }}>
                    {status}
                </span>
            </div>
            <div style={{ padding: '20px', flex: 1, overflowY: 'auto' }}>
                <pre style={{ margin: 0, whiteSpace: 'pre-wrap', wordBreak: 'break-all' }}>
                    {logs.length > 0 ? logs.join('\n') : "No logs available..."}
                </pre>
            </div>
        </div>
    );
};

export default MicroRosLogs;
