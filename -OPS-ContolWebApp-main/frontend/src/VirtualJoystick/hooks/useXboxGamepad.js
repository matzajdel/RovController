/**
 * useXboxGamepad — Dedykowany hook wykrywający pada Xbox przez USB
 * ================================================================
 *
 * Używa Gamepad API przeglądarki (navigator.getGamepads).
 * Obsługuje:
 *  - automatyczne wykrywanie po podłączeniu USB (event gamepadconnected)
 *  - rozróżnianie Xbox od innych padów
 *  - polling stanu (co klatkę rAF) z dedupekiem
 *
 * UWAGA: Przeglądarka wymaga min. 1 naciśnięcia przycisku na padzie
 * po podłączeniu, żeby go udostępnić przez API (polityka bezpieczeństwa).
 *
 * Zwraca:
 *   connected  — czy jakiś pad jest podłączony i aktywny
 *   padName    — pełny string id pada z przeglądarki
 *   padIndex   — indeks w navigator.getGamepads()
 *   isXbox     — czy pad ma "Xbox" lub "XInput" w nazwie
 *   axes       — aktualne osie (raw, do diagnostyki)
 *   buttons    — aktualne przyciski (raw, do diagnostyki)
 */

import { useState, useEffect, useRef, useCallback } from "react";

const XBOX_KEYWORDS = ["xbox", "xinput", "045e"];

function isXboxPad(id = "") {
    const lower = id.toLowerCase();
    return XBOX_KEYWORDS.some((kw) => lower.includes(kw));
}

export const useXboxGamepad = () => {
    const [state, setState] = useState({
        connected: false,
        padName: "",
        padIndex: -1,
        isXbox: false,
        axes: [],
        buttons: [],
    });

    const rafRef = useRef(null);
    const prevConnectedRef = useRef(false);
    const prevIdRef = useRef("");

    const findFirstGamepad = useCallback(() => {
        const pads = navigator.getGamepads ? navigator.getGamepads() : [];
        for (let i = 0; i < pads.length; i++) {
            if (pads[i] && pads[i].connected) return pads[i];
        }
        return null;
    }, []);

    const tick = useCallback(() => {
        const gp = findFirstGamepad();

        if (gp) {
            const idChanged = gp.id !== prevIdRef.current;
            const nowConnected = true;

            if (!prevConnectedRef.current || idChanged) {
                prevConnectedRef.current = true;
                prevIdRef.current = gp.id;
                setState({
                    connected: true,
                    padName: gp.id,
                    padIndex: gp.index,
                    isXbox: isXboxPad(gp.id),
                    axes: [...gp.axes],
                    buttons: gp.buttons.map((b) => ({ pressed: b.pressed, value: b.value })),
                });
            } else {
                // Update axes/buttons every frame (shallow copy to avoid mutation)
                setState((prev) => ({
                    ...prev,
                    connected: true,
                    axes: [...gp.axes],
                    buttons: gp.buttons.map((b) => ({ pressed: b.pressed, value: b.value })),
                }));
            }
        } else {
            if (prevConnectedRef.current) {
                prevConnectedRef.current = false;
                prevIdRef.current = "";
                setState({
                    connected: false,
                    padName: "",
                    padIndex: -1,
                    isXbox: false,
                    axes: [],
                    buttons: [],
                });
            }
        }

        rafRef.current = requestAnimationFrame(tick);
    }, [findFirstGamepad]);

    useEffect(() => {
        const onConnect = (e) => {
            console.log("[useXboxGamepad] Gamepad connected:", e.gamepad.id);
        };
        const onDisconnect = (e) => {
            console.log("[useXboxGamepad] Gamepad disconnected:", e.gamepad.id);
        };

        window.addEventListener("gamepadconnected", onConnect);
        window.addEventListener("gamepaddisconnected", onDisconnect);

        rafRef.current = requestAnimationFrame(tick);

        return () => {
            if (rafRef.current) cancelAnimationFrame(rafRef.current);
            window.removeEventListener("gamepadconnected", onConnect);
            window.removeEventListener("gamepaddisconnected", onDisconnect);
        };
    }, [tick]);

    return state;
};
