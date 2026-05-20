/**
 * useSatelSerial — Web Serial API hook (rozszerzony)
 *
 * Daje bezpośredni dostęp do portu RS-232 z przeglądarki (Chrome/Edge).
 * Obsługuje wysyłanie WSZYSTKICH topicków przez Satel radiomodem TA13.
 *
 * Protokół: JSON-linie zakończone '\n'
 *   {"t":"cmd_vel","lx":0.5,"az":0.0}
 *   {"t":"array","data":[0,100,0,0,0,0]}
 *   {"t":"arrow","data":[1,90]}
 *   {"t":"rgb","r":255,"g":0,"b":0}
 *   {"t":"gps","lon":21.01,"lat":52.23}
 *   {"t":"led","state":[1,0,0]}
 *   {"t":"custom","topic":"/Serwa","msg":"UInt8MultiArray","data":[0,90,135,90]}
 *   {"t":"stop"}
 */

import { useState, useRef, useCallback } from "react";

// -------------------------------------------------------------------
// Packet builders (Binary Format)
// Format: $ [HEADER_2_BYTES] [DATA_N_BYTES] [CHECKSUM_1_BYTE] #
// -------------------------------------------------------------------

function floatToByte(val) {
    const clamped = Math.max(-1.0, Math.min(1.0, val));
    return Math.floor((clamped * 127.0) + 128.0);
}

function floatToByte100(val) {
    const clamped = Math.max(-100.0, Math.min(100.0, val));
    return Math.floor((clamped + 100.0) / 200.0 * 254.0);
}

function buildFrame(headerStr, dataArr) {
    let checksum = 0;
    for (let i = 0; i < dataArr.length; i++) {
        checksum = (checksum + dataArr[i]) % 256;
    }
    const encoder = new TextEncoder();
    const headerBytes = encoder.encode(headerStr);
    
    const frame = new Uint8Array(1 + headerBytes.length + dataArr.length + 2);
    frame[0] = 36; // '$'
    frame.set(headerBytes, 1);
    frame.set(dataArr, 1 + headerBytes.length);
    frame[frame.length - 2] = checksum;
    frame[frame.length - 1] = 35; // '#'
    return frame;
}

export function buildCmdVelPacket(linearX, angularZ) {
    return buildFrame("DV", [floatToByte(linearX), floatToByte(angularZ)]);
}

export function buildCmdVelFullPacket(lx, ly, lz, az) {
    return buildFrame("D4", [floatToByte(lx), floatToByte(ly), floatToByte(lz), floatToByte(az)]);
}

export function buildArrayPacket(data) {
    const vals = data.concat([0,0,0,0,0,0]).slice(0, 6).map(v => floatToByte100(parseFloat(v)));
    return buildFrame("MN", vals);
}

export function buildArrowPacket(data) {
    const vals = data.concat([0,0,0,0]).slice(0, 4).map(v => Math.max(0, Math.min(255, parseInt(v))));
    return buildFrame("GS", vals);
}

export function buildRgbPacket(r, g, b) {
    const rB = Math.max(0, Math.min(255, parseInt(r)));
    const gB = Math.max(0, Math.min(255, parseInt(g)));
    const bB = Math.max(0, Math.min(255, parseInt(b)));
    return buildFrame("RG", [rB, gB, bB]);
}

export function buildGpsPacket(lon, lat) {
    return new Uint8Array();
}

export function buildLedPacket(state) {
    const mode = state[0] || 0;
    const r = state[1] || 0;
    const b = state[3] || 0;

    const manual = b === 255 ? 1 : 0;
    const autonomy = r === 255 ? 1 : 0;
    const killSwitch = mode === 0 ? 1 : 0;

    const byteVal = (manual << 0) | (autonomy << 1) | (killSwitch << 2);
    return buildFrame("GL", [byteVal]);
}

export function buildKoszelnikPacket(drill, koszelnik, heater) {
    const byteVal = ((drill & 1) << 0) | ((koszelnik & 1) << 1) | ((heater & 1) << 2);
    return buildFrame("GK", [byteVal]);
}

export function buildScienceServoPacket(data) {
    const vals = data.concat([0,0,0,0,0,0]).slice(0, 6).map(v => Math.max(0, Math.min(255, parseInt(v))));
    return buildFrame("SS", vals);
}

export function buildSciencePumpPacket(p1, p2) {
    const byteVal = ((p1 & 1) << 0) | ((p2 & 1) << 1);
    return buildFrame("SP", [byteVal]);
}

export function buildCustomTopicPacket(topic, msgType, data) {
    return new Uint8Array();
}

export function buildStopPacket() {
    return buildCmdVelPacket(0.0, 0.0);
}

export function buildArrayIndexPacket(index, value) {
    return new Uint8Array();
}

// -------------------------------------------------------------------
// Hook
// -------------------------------------------------------------------

export function useSatelSerial() {
    const [isConnected, setIsConnected] = useState(false);
    const [portInfo, setPortInfo] = useState(null);     // { usbVendorId, usbProductId }
    const [error, setError] = useState(null);
    const [lastSent, setLastSent] = useState(null);
    const [received, setReceived] = useState([]);       // array of parsed packets

    // Transmission stats
    const [stats, setStats] = useState({
        totalPackets: 0,
        totalBytes: 0,
        packetsPerSec: 0,
        bytesPerSec: 0,
    });
    const statsWindowRef = useRef([]);  // { ts, bytes } entries for rate calc

    const portRef = useRef(null);
    const writerRef = useRef(null);
    const readerRef = useRef(null);
    const readLoopRef = useRef(false);

    // Check if Web Serial API is supported
    const isSupported = typeof navigator !== "undefined" && "serial" in navigator;

    // ---- Stats helper ---------------------------------------------------
    const updateStats = useCallback((bytesSent) => {
        const now = Date.now();
        statsWindowRef.current.push({ ts: now, bytes: bytesSent });
        // Keep only last 5 seconds of data
        const cutoff = now - 5000;
        statsWindowRef.current = statsWindowRef.current.filter(e => e.ts > cutoff);

        const windowMs = statsWindowRef.current.length > 1
            ? now - statsWindowRef.current[0].ts
            : 1000;
        const windowSec = Math.max(windowMs / 1000, 0.1);
        const windowBytes = statsWindowRef.current.reduce((sum, e) => sum + e.bytes, 0);
        const windowPackets = statsWindowRef.current.length;

        setStats(prev => ({
            totalPackets: prev.totalPackets + 1,
            totalBytes: prev.totalBytes + bytesSent,
            packetsPerSec: Math.round(windowPackets / windowSec * 10) / 10,
            bytesPerSec: Math.round(windowBytes / windowSec),
        }));
    }, []);

    // ---- Connect --------------------------------------------------------
    const connect = useCallback(async (baudRate = 9600) => {
        if (!isSupported) {
            setError("Web Serial API nie jest obsługiwany w tej przeglądarce. Użyj Chrome lub Edge.");
            return false;
        }
        setError(null);
        try {
            const port = await navigator.serial.requestPort();
            await port.open({ baudRate });
            portRef.current = port;

            // Writer
            const writer = port.writable.getWriter();
            writerRef.current = writer;

            // Reader (background loop)
            const reader = port.readable.getReader();
            readerRef.current = reader;
            readLoopRef.current = true;
            _startReadLoop(reader);

            const info = port.getInfo();
            setPortInfo(info);
            setIsConnected(true);
            // Reset stats
            statsWindowRef.current = [];
            setStats({ totalPackets: 0, totalBytes: 0, packetsPerSec: 0, bytesPerSec: 0 });
            return true;
        } catch (e) {
            if (e.name !== "NotFoundError") {
                setError(`Błąd połączenia: ${e.message}`);
            }
            return false;
        }
    }, [isSupported]);

    // ---- Background read loop --------------------------------------------
    const _startReadLoop = useCallback((reader) => {
        const decoder = new TextDecoder();
        let buffer = "";

        const loop = async () => {
            while (readLoopRef.current) {
                try {
                    const { value, done } = await reader.read();
                    if (done) break;

                    buffer += decoder.decode(value, { stream: true });
                    const lines = buffer.split("\n");
                    buffer = lines.pop(); // incomplete line stays in buffer

                    for (const line of lines) {
                        const trimmed = line.trim();
                        if (!trimmed) continue;
                        try {
                            const parsed = JSON.parse(trimmed);
                            setReceived((prev) => [...prev.slice(-49), { ts: Date.now(), raw: trimmed, parsed }]);
                        } catch {
                            setReceived((prev) => [...prev.slice(-49), { ts: Date.now(), raw: trimmed, parsed: null }]);
                        }
                    }
                } catch (e) {
                    if (readLoopRef.current) {
                        setError(`Błąd odczytu: ${e.message}`);
                    }
                    break;
                }
            }
        };
        loop();
    }, []);

    // ---- Disconnect ------------------------------------------------------
    const disconnect = useCallback(async () => {
        readLoopRef.current = false;
        try { readerRef.current?.cancel(); } catch { }
        try { writerRef.current?.releaseLock(); } catch { }
        try { await portRef.current?.close(); } catch { }
        portRef.current = null;
        writerRef.current = null;
        readerRef.current = null;
        setIsConnected(false);
        setPortInfo(null);
    }, []);

    // ---- Low-level write -------------------------------------------------
    const writeRaw = useCallback(async (data) => {
        if (!writerRef.current) {
            setError("Nie połączono z portem szeregowym.");
            return false;
        }
        try {
            let encoded;
            let displayStr = "";
            if (data instanceof Uint8Array) {
                encoded = data;
                // Zamieniamy na czytelny Hex np. 24 44 56 80 ...
                const hexStr = Array.from(data).map(b => b.toString(16).padStart(2, '0').toUpperCase()).join(' ');
                displayStr = `[Bin ${data.length}B]: ${hexStr}`;
            } else if (typeof data === 'string') {
                const encoder = new TextEncoder();
                encoded = encoder.encode(data);
                displayStr = data.trim();
            } else {
                return false;
            }
            
            if (encoded.length === 0) return true;

            await writerRef.current.write(encoded);
            setLastSent(displayStr);
            updateStats(encoded.length);
            return true;
        } catch (e) {
            setError(`Błąd zapisu: ${e.message}`);
            return false;
        }
    }, [updateStats]);

    // ---- High-level API ---------------------------------------------------

    /** Send cmd_vel command (2-axis) */
    const sendCmdVel = useCallback((linearX, angularZ) => {
        return writeRaw(buildCmdVelPacket(linearX, angularZ));
    }, [writeRaw]);

    /** Send cmd_vel full (4-axis: lx, ly, lz, az) */
    const sendCmdVelFull = useCallback((lx, ly, lz, az) => {
        return writeRaw(buildCmdVelFullPacket(lx, ly, lz, az));
    }, [writeRaw]);

    /** Send array_topic data */
    const sendArray = useCallback((data) => {
        return writeRaw(buildArrayPacket(data));
    }, [writeRaw]);

    /** Send array_topic single index */
    const sendArrayIndex = useCallback((index, value) => {
        return writeRaw(buildArrayIndexPacket(index, value));
    }, [writeRaw]);

    /** Send arrow keys */
    const sendArrow = useCallback((data) => {
        return writeRaw(buildArrowPacket(data));
    }, [writeRaw]);

    /** Send RGB colour */
    const sendRgb = useCallback((r, g, b) => {
        return writeRaw(buildRgbPacket(r, g, b));
    }, [writeRaw]);

    /** Send GPS waypoint */
    const sendGps = useCallback((lon, lat) => {
        return writeRaw(buildGpsPacket(lon, lat));
    }, [writeRaw]);

    /** Send LED state */
    const sendLed = useCallback((state) => {
        return writeRaw(buildLedPacket(state));
    }, [writeRaw]);

    /** Send custom topic (e.g. /Serwa, /serwoUART) */
    const sendCustomTopic = useCallback((topic, msgType, data) => {
        // Obsolete in binary protocol
        return writeRaw(buildCustomTopicPacket(topic, msgType, data));
    }, [writeRaw]);

    const sendKoszelnik = useCallback((drill, koszelnik, heater) => {
        return writeRaw(buildKoszelnikPacket(drill, koszelnik, heater));
    }, [writeRaw]);

    const sendScienceServo = useCallback((data) => {
        return writeRaw(buildScienceServoPacket(data));
    }, [writeRaw]);

    const sendSciencePump = useCallback((p1, p2) => {
        return writeRaw(buildSciencePumpPacket(p1, p2));
    }, [writeRaw]);

    const sendScienceLed = useCallback((brightness) => {
        return writeRaw(buildFrame("SL", [Math.max(0, Math.min(255, parseInt(brightness)))]));
    }, [writeRaw]);

    /** Send arbitrary topic (legacy compat) */
    const sendTopic = useCallback((name, data) => {
        return writeRaw(JSON.stringify({ t: "topic", name, data }) + "\n");
    }, [writeRaw]);

    /** Send emergency stop */
    const sendStop = useCallback(() => {
        return writeRaw(buildStopPacket());
    }, [writeRaw]);

    /** Send any raw string */
    const sendRaw = useCallback((text) => writeRaw(text), [writeRaw]);

    /** Clear received buffer */
    const clearReceived = useCallback(() => setReceived([]), []);

    /** Reset stats */
    const resetStats = useCallback(() => {
        statsWindowRef.current = [];
        setStats({ totalPackets: 0, totalBytes: 0, packetsPerSec: 0, bytesPerSec: 0 });
    }, []);

    return {
        // State
        isConnected,
        isSupported,
        portInfo,
        error,
        lastSent,
        received,
        stats,
        // Actions
        connect,
        disconnect,
        sendCmdVel,
        sendCmdVelFull,
        sendArray,
        sendArrayIndex,
        sendArrow,
        sendRgb,
        sendGps,
        sendLed,
        sendCustomTopic,
        sendKoszelnik,
        sendScienceServo,
        sendSciencePump,
        sendScienceLed,
        sendTopic,
        sendStop,
        sendRaw,
        clearReceived,
        resetStats,
    };
}
