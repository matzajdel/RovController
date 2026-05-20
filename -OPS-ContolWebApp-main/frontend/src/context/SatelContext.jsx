import React, { createContext, useContext, useState } from "react";
import { useSatelSerial } from "../Satel/useSatelSerial";

const SatelContext = createContext(null);

export const useSatel = () => {
    const ctx = useContext(SatelContext);
    if (!ctx) throw new Error("useSatel must be used within <SatelProvider>");
    return ctx;
};

export const SatelProvider = ({ children }) => {
    // Global toggle for Satel mode
    const [satelEnabled, setSatelEnabled] = useState(false);
    
    // The underlying serial hook
    const satel = useSatelSerial();

    const value = {
        satelEnabled,
        setSatelEnabled,
        satel,
    };

    return (
        <SatelContext.Provider value={value}>
            {children}
        </SatelContext.Provider>
    );
};
