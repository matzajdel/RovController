import React, { useState, useEffect } from 'react';
import { MapContainer, TileLayer, Marker, Popup, useMap, useMapEvents } from 'react-leaflet';
import L from 'leaflet';
import 'leaflet/dist/leaflet.css';

// --- NAPRAWA IKON LEAFLET (Standardowy bug biblioteki) ---
import iconMarker from 'leaflet/dist/images/marker-icon.png';
import iconRetina from 'leaflet/dist/images/marker-icon-2x.png';
import iconShadow from 'leaflet/dist/images/marker-shadow.png';

delete L.Icon.Default.prototype._getIconUrl;
L.Icon.Default.mergeOptions({
    iconRetinaUrl: iconRetina,
    iconUrl: iconMarker,
    shadowUrl: iconShadow,
});

// --- KONFIGURACJA ---
import { BACKEND_CONFIG } from '../VirtualJoystick/Constants';
import { useSatel } from '../context/SatelContext';
const BACKEND_URL = BACKEND_CONFIG.GPS_BACKEND_URL;
const MAIN_BACKEND_URL = BACKEND_CONFIG.BACKEND_URL;

// --- KOMPONENTY POMOCNICZE ---

// 1. Kontroler Mapy: Płynne przesuwanie i wyłączanie śledzenia przy interakcji
const MapController = ({ lat, lng, follow, disableFollow }) => {
    const map = useMap();

    useEffect(() => {
        if (follow && lat !== 0 && lng !== 0) {
            // panTo zapewnia płynną animację zamiast skoków
            map.panTo([lat, lng], { animate: true, duration: 0.5 });
        }
    }, [lat, lng, follow, map]);

    useMapEvents({
        dragstart: () => {
            if (follow) {
                console.log("Użytkownik ruszył mapą -> Wyłączam auto-śledzenie");
                disableFollow();
            }
        }
    });

    return null;
};

// 2. Wykrywanie kliknięć (Teleportacja łazika)
const LocationSetter = ({ isManualMode, onSetLocation }) => {
    useMapEvents({
        click(e) {
            // LOGOWANIE DLA CELÓW DIAGNOSTYCZNYCH
            console.log("Kliknięcie na mapie:", e.latlng);

            if (!isManualMode) {
                console.warn("Ignoruję kliknięcie: Tryb manualny jest WYŁĄCZONY w opcjach.");
                return;
            }

            if (!e.originalEvent.shiftKey) {
                console.warn("Ignoruję kliknięcie: Nie wciśnięto klawisza SHIFT.");
                return;
            }

            console.log("Wysyłam żądanie zmiany pozycji do:", e.latlng);
            onSetLocation(e.latlng.lat, e.latlng.lng);
        }
    });
    return null;
};

// 3. Wysyłanie współrzędnych do ROS po kliknięciu
const MapClickHandler = ({ onWaypointClick }) => {
    useMapEvents({
        click(e) {
            // Standardowe kliknięcie (bez SHIFT/CTRL) wysyła waypoint do ROS
            if (!e.originalEvent.shiftKey && !e.originalEvent.ctrlKey) {
                console.log("Wysyłam waypoint do ROS:", e.latlng);
                onWaypointClick(e.latlng.lat, e.latlng.lng);
            }
        }
    });
    return null;
};

// --- GŁÓWNY KOMPONENT ---
const Gps = () => {
    // Stan aplikacji
    const [roverPos, setRoverPos] = useState({ lat: 0, lng: 0, alt: 0.0 });
    const [heading, setHeading] = useState(0);
    const [followMode, setFollowMode] = useState(true);
    const [isOnline, setIsOnline] = useState(false);
    const [hasLoaded, setHasLoaded] = useState(false); // Czy załadowano pierwsze dane?
    const { satelEnabled, satel } = useSatel();

    // Konfiguracja
    const [showConfig, setShowConfig] = useState(false);
    const [config, setConfig] = useState({
        manual_mode: false,
        log_data: false,
        log_interval: 1.0
    });

    // Waypoint wysłany do ROS
    const [lastWaypoint, setLastWaypoint] = useState(null);

    // Manual coordinate input
    const [manualLat, setManualLat] = useState('');
    const [manualLon, setManualLon] = useState('');
    const [showManualInput, setShowManualInput] = useState(false);
    const [destinationMarker, setDestinationMarker] = useState(null);

    // 1. Pobieranie danych GPS co 500ms
    useEffect(() => {
        const interval = setInterval(async () => {
            try {
                // Używamy 127.0.0.1 zamiast localhost dla pewności
                const res = await fetch('http://127.0.0.1:5001/api/gps');
                if (res.ok) {
                    const data = await res.json();
                    setRoverPos({ lat: data.lat, lng: data.lng, alt: data.alt });
                    setHeading(data.heading);
                    setIsOnline(true);

                    // Odblokuj mapę dopiero jak przyjdą pierwsze sensowne dane
                    if (!hasLoaded && (data.lat !== 0 || data.lng !== 0)) {
                        setHasLoaded(true);
                    }
                }
            } catch (e) {
                setIsOnline(false);
            }
        }, 500);
        return () => clearInterval(interval);
    }, [hasLoaded]);

    // 2. Pobranie konfiguracji przy starcie
    useEffect(() => {
        fetch('http://127.0.0.1:5001/api/config')
            .then(res => res.json())
            .then(data => setConfig(data))
            .catch(err => console.error("Błąd pobierania configu:", err));
    }, []);

    // 3. Zapis konfiguracji
    const saveConfig = async (newConfig) => {
        const configToSend = newConfig || config;
        try {
            await fetch('http://127.0.0.1:5001/api/config', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(configToSend)
            });
            // Aktualizujemy stan lokalny od razu, żeby UI zareagowało
            setConfig(configToSend);
            console.log("Zapisano config:", configToSend);
        } catch (err) {
            alert("Błąd zapisu ustawień! Sprawdź czy backend działa.");
        }
    };

    // 4. Wysyłanie nowej pozycji (Tryb Manualny)
    const setManualLocation = async (lat, lng) => {
        // Pytanie o potwierdzenie (opcjonalne, można usunąć jeśli irytuje)
        if (!window.confirm(`Przesunąć łazika tutaj?\nLat: ${lat.toFixed(6)}\nLng: ${lng.toFixed(6)}`)) return;

        try {
            const res = await fetch(`${BACKEND_URL}/api/set_position`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ lat, lng })
            });

            if (res.ok) {
                // Optymistyczna aktualizacja (żeby nie czekać na odświeżenie interwału)
                setRoverPos(prev => ({ ...prev, lat, lng }));
                console.log("Pozycja zaktualizowana!");
            } else {
                alert("Backend odrzucił zmianę. Sprawdź czy Tryb Manualny jest włączony w Pythonie.");
            }
        } catch (err) {
            console.error(err);
        }
    };

    // 5. Wysyłanie punktu docelowego do ROS
    const sendDestinationToROS = async (lat, lng) => {
        if (satelEnabled && satel.isConnected) {
            satel.sendGps(lng, lat);
            console.log("Punkt docelowy wysłany przez Satel:", {lat, lng});
            setLastWaypoint({ lat, lng, timestamp: new Date().toISOString() });
            setDestinationMarker({ lat, lng });
            setTimeout(() => setLastWaypoint(null), 3000);
            return;
        }

        try {
            const res = await fetch(`${MAIN_BACKEND_URL}/gps/destination`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ lat: lat, lon: lng })
            });

            if (res.ok) {
                const data = await res.json();
                console.log("Punkt docelowy wysłany do ROS:", data);
                setLastWaypoint({ lat, lng, timestamp: new Date().toISOString() });
                setDestinationMarker({ lat, lng });
                // Usunięcie informacji po 3 sekundach
                setTimeout(() => setLastWaypoint(null), 3000);
            } else {
                console.error("Błąd wysyłania punktu docelowego:", res.statusText);
                alert("Nie udało się wysłać punktu docelowego do ROS. Sprawdź backend.");
            }
        } catch (err) {
            console.error("Błąd połączenia z backendem:", err);
            alert("Błąd połączenia z backendem!");
        }
    };

    // 6. Wysyłanie manualnie wpisanych koordynatów
    const sendManualDestination = () => {
        const lat = parseFloat(manualLat);
        const lon = parseFloat(manualLon);

        if (isNaN(lat) || isNaN(lon)) {
            alert("Nieprawidłowe koordynaty! Sprawdź format.");
            return;
        }

        if (lat < -90 || lat > 90) {
            alert("Latitude musi być między -90 a 90");
            return;
        }

        if (lon < -180 || lon > 180) {
            alert("Longitude musi być między -180 a 180");
            return;
        }

        sendDestinationToROS(lat, lon);
        setManualLat('');
        setManualLon('');
        setShowManualInput(false);
    };

    // Ikona Łazika
    const roverIcon = L.divIcon({
        className: 'custom-rover-icon',
        html: `
            <div style="
                transform: rotate(${heading}deg); 
                width: 50px; 
                height: 50px; 
                display: flex; 
                justify-content: center; 
                align-items: center; 
                transition: transform 0.5s linear;
            ">
                <img src="/rover.png" 
                     style="width: 100%; height: 100%; object-fit: contain;" 
                     onerror="this.style.display='none'; this.parentNode.innerHTML='❌';" 
                />
            </div>
        `,
        iconSize: [50, 50],
        iconAnchor: [25, 25]
    });

    return (
        <div style={{ height: '100vh', display: 'flex', flexDirection: 'column' }}>

            {/* --- PASEK STATUSU --- */}
            <div style={{ padding: '10px', background: '#222', color: 'white', display: 'flex', justifyContent: 'space-between', alignItems: 'center', borderBottom: '2px solid #444' }}>
                <div style={{ display: 'flex', gap: '15px', alignItems: 'center', fontSize: '14px' }}>
                    <div style={{
                        width: '12px', height: '12px', borderRadius: '50%',
                        background: isOnline ? '#0f0' : '#f00',
                        boxShadow: isOnline ? '0 0 10px #0f0' : 'none'
                    }} title={isOnline ? "Backend połączony" : "Brak połączenia"} />

                    <span style={{ fontFamily: 'monospace' }}>LAT: {roverPos.lat.toFixed(6)}</span>
                    <span style={{ fontFamily: 'monospace' }}>LNG: {roverPos.lng.toFixed(6)}</span>

                    {config.manual_mode && (
                        <span style={{ color: 'orange', fontWeight: 'bold', border: '1px solid orange', padding: '0 5px', borderRadius: '4px' }}>
                            MANUAL MODE
                        </span>
                    )}
                </div>

                <div style={{ display: 'flex', gap: '10px' }}>
                    {lastWaypoint && (
                        <div style={{
                            padding: '6px 12px', borderRadius: '4px',
                            background: '#4CAF50', color: 'white', fontWeight: 'bold',
                            animation: 'fadeIn 0.3s'
                        }}>
                            ✓ Waypoint wysłany
                        </div>
                    )}

                    <button
                        onClick={() => setFollowMode(!followMode)}
                        style={{
                            padding: '6px 12px', borderRadius: '4px', border: 'none', cursor: 'pointer',
                            background: followMode ? '#2196F3' : '#555', color: 'white'
                        }}
                    >
                        {followMode ? '🔒 Śledzenie' : '🔓 Mapa Wolna'}
                    </button>

                    <button
                        onClick={() => setShowManualInput(!showManualInput)}
                        style={{
                            padding: '6px 12px', borderRadius: '4px', border: 'none', cursor: 'pointer',
                            background: '#4CAF50', color: 'white', fontWeight: 'bold'
                        }}
                    >
                        📍 Wpisz Koordynaty
                    </button>

                    <button
                        onClick={() => setShowConfig(!showConfig)}
                        style={{
                            padding: '6px 12px', borderRadius: '4px', border: 'none', cursor: 'pointer',
                            background: 'orange', color: '#000', fontWeight: 'bold'
                        }}
                    >
                        ⚙️ Opcje
                    </button>
                </div>
            </div>

            {/* --- MODAL WPROWADZANIA KOORDYNATÓW --- */}
            {showManualInput && (
                <div style={{
                    position: 'absolute', top: '60px', left: '10px', zIndex: 9999,
                    background: 'rgba(0, 0, 0, 0.95)', color: 'white', padding: '20px',
                    borderRadius: '8px', border: '2px solid #4CAF50', width: '320px'
                }}>
                    <h3 style={{ marginTop: 0, color: '#4CAF50', borderBottom: '1px solid #555', paddingBottom: '10px' }}>
                        📍 Punkt Docelowy GPS
                    </h3>

                    <div style={{ marginBottom: '15px' }}>
                        <label style={{ display: 'block', marginBottom: '5px', fontSize: '14px' }}>
                            Latitude (-90 do 90):
                        </label>
                        <input
                            type="number"
                            step="0.000001"
                            value={manualLat}
                            onChange={(e) => setManualLat(e.target.value)}
                            placeholder="np. 52.237049"
                            style={{
                                width: '100%', padding: '8px', borderRadius: '4px',
                                border: '1px solid #555', background: '#222', color: 'white',
                                fontSize: '14px'
                            }}
                        />
                    </div>

                    <div style={{ marginBottom: '15px' }}>
                        <label style={{ display: 'block', marginBottom: '5px', fontSize: '14px' }}>
                            Longitude (-180 do 180):
                        </label>
                        <input
                            type="number"
                            step="0.000001"
                            value={manualLon}
                            onChange={(e) => setManualLon(e.target.value)}
                            placeholder="np. 21.017532"
                            style={{
                                width: '100%', padding: '8px', borderRadius: '4px',
                                border: '1px solid #555', background: '#222', color: 'white',
                                fontSize: '14px'
                            }}
                        />
                    </div>

                    <p style={{ fontSize: '12px', color: '#ccc', margin: '10px 0' }}>
                        💡 Możesz też kliknąć na mapę aby wybrać punkt
                    </p>

                    <div style={{ display: 'flex', gap: '10px' }}>
                        <button
                            onClick={sendManualDestination}
                            style={{
                                flex: 1, padding: '10px', background: '#4CAF50',
                                color: 'white', border: 'none', borderRadius: '4px',
                                cursor: 'pointer', fontWeight: 'bold'
                            }}
                        >
                            ✓ WYŚLIJ
                        </button>
                        <button
                            onClick={() => setShowManualInput(false)}
                            style={{
                                flex: 1, padding: '10px', background: '#444',
                                color: 'white', border: 'none', borderRadius: '4px',
                                cursor: 'pointer'
                            }}
                        >
                            ANULUJ
                        </button>
                    </div>
                </div>
            )}

            {/* --- MODAL KONFIGURACYJNY --- */}
            {showConfig && (
                <div style={{
                    position: 'absolute', top: '60px', right: '10px', zIndex: 9999,
                    background: 'rgba(0, 0, 0, 0.9)', color: 'white', padding: '20px',
                    borderRadius: '8px', border: '1px solid orange', width: '300px'
                }}>
                    <h3 style={{ marginTop: 0, color: 'orange', borderBottom: '1px solid #555', paddingBottom: '10px' }}>Ustawienia</h3>

                    <div style={{ marginBottom: '15px' }}>
                        <label style={{ display: 'flex', alignItems: 'center', gap: '10px', cursor: 'pointer', fontSize: '16px' }}>
                            <input
                                type="checkbox"
                                checked={config.manual_mode}
                                onChange={e => {
                                    const val = e.target.checked;
                                    // Najpierw zapisz, potem zaktualizuj stan
                                    saveConfig({ ...config, manual_mode: val });
                                }}
                                style={{ transform: 'scale(1.5)' }}
                            />
                            Tryb Manualny (Symulacja)
                        </label>
                        <p style={{ fontSize: '12px', color: '#ccc', margin: '5px 0 0 25px' }}>
                            Ignoruje GPS. Użyj <b>SHIFT + Klik</b> na mapie, aby ustawić pozycję.
                        </p>
                    </div>

                    <div style={{ marginBottom: '15px', borderTop: '1px solid #555', paddingTop: '10px' }}>
                        <label style={{ display: 'flex', alignItems: 'center', gap: '10px', cursor: 'pointer' }}>
                            <input
                                type="checkbox"
                                checked={config.log_data}
                                onChange={e => setConfig({ ...config, log_data: e.target.checked })}
                            />
                            Zapisuj historię (.csv)
                        </label>
                    </div>

                    <div style={{ display: 'flex', gap: '10px' }}>
                        <button
                            onClick={() => saveConfig()}
                            style={{ flex: 1, padding: '10px', background: 'green', color: 'white', border: 'none', borderRadius: '4px', cursor: 'pointer' }}
                        >
                            ZAPISZ
                        </button>
                        <button
                            onClick={() => setShowConfig(false)}
                            style={{ flex: 1, padding: '10px', background: '#444', color: 'white', border: 'none', borderRadius: '4px', cursor: 'pointer' }}
                        >
                            ZAMKNIJ
                        </button>
                    </div>
                </div>
            )}

            {/* --- MAPA --- */}
            <div style={{ flex: 1, position: 'relative' }}>
                <MapContainer
                    center={[roverPos.lat || 52.0, roverPos.lng || 21.0]}
                    zoom={18}
                    style={{ height: '100%', width: '100%' }}
                >
                    <TileLayer
                        attribution='&copy; OpenStreetMap'
                        url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
                    />

                    {/* Kontrolery */}
                    <MapController
                        lat={roverPos.lat}
                        lng={roverPos.lng}
                        follow={followMode}
                        disableFollow={() => setFollowMode(false)}
                    />

                    <LocationSetter
                        isManualMode={config.manual_mode}
                        onSetLocation={setManualLocation}
                    />

                    <MapClickHandler
                        onWaypointClick={sendDestinationToROS}
                    />

                    {/* Marker Łazika */}
                    {(roverPos.lat !== 0 || roverPos.lng !== 0) && (
                        <Marker position={[roverPos.lat, roverPos.lng]} icon={roverIcon}>
                            <Popup>
                                <strong>Twój Łazik</strong><br />
                                Lat: {roverPos.lat.toFixed(6)}<br />
                                Lng: {roverPos.lng.toFixed(6)}
                            </Popup>
                        </Marker>
                    )}

                    {/* Marker Punktu Docelowego */}
                    {destinationMarker && (
                        <Marker
                            position={[destinationMarker.lat, destinationMarker.lng]}
                            icon={L.icon({
                                iconUrl: 'https://raw.githubusercontent.com/pointhi/leaflet-color-markers/master/img/marker-icon-2x-green.png',
                                shadowUrl: 'https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.7.1/images/marker-shadow.png',
                                iconSize: [25, 41],
                                iconAnchor: [12, 41],
                                popupAnchor: [1, -34],
                                shadowSize: [41, 41]
                            })}
                        >
                            <Popup>
                                <strong>🎯 Punkt Docelowy</strong><br />
                                Lat: {destinationMarker.lat.toFixed(6)}<br />
                                Lng: {destinationMarker.lng.toFixed(6)}
                            </Popup>
                        </Marker>
                    )}
                </MapContainer>

                {/* Ekran ładowania (jeśli dane jeszcze nie spłynęły) */}
                {!hasLoaded && (
                    <div style={{
                        position: 'absolute', top: 0, left: 0, right: 0, bottom: 0,
                        background: 'rgba(0,0,0,0.7)', color: 'white', zIndex: 1000,
                        display: 'flex', justifyContent: 'center', alignItems: 'center', flexDirection: 'column'
                    }}>
                        <h2>Oczekiwanie na sygnał GPS...</h2>
                        <p>Upewnij się, że backend działa: <code>python3 gps_service.py</code></p>
                    </div>
                )}
            </div>
        </div>
    );
};

export default Gps;