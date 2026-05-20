/**
 * useBackendHealth — shared hook for backend health monitoring.
 *
 * Polls the /health endpoint at a configurable interval and exposes:
 *   • backendData  — latest JSON response (or null)
 *   • isHealthy    — boolean availability flag
 *
 * Import from here instead of VirtualJoystick/hooks/ so the hook
 * is available to every module without reaching into another feature.
 */
import { useState, useEffect } from "react";
import { BACKEND_URL, HEALTH_CHECK_INTERVAL } from "../config";

export const useBackendHealth = () => {
    const [backendData, setBackendData] = useState(null);
    const [isHealthy, setIsHealthy] = useState(false);

    useEffect(() => {
        const checkBackendHealth = async () => {
            try {
                const response = await fetch(`${BACKEND_URL}/health`);
                if (response.ok) {
                    const data = await response.json();
                    setBackendData(data);
                    setIsHealthy(true);
                } else {
                    setBackendData(null);
                    setIsHealthy(false);
                }
            } catch (error) {
                console.error("Backend health check failed:", error);
                setBackendData(null);
                setIsHealthy(false);
            }
        };

        checkBackendHealth();
        const interval = setInterval(checkBackendHealth, HEALTH_CHECK_INTERVAL);

        return () => clearInterval(interval);
    }, []);

    return { backendData, isHealthy };
};
