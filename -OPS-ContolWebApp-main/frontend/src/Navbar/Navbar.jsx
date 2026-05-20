import { useState, useEffect } from "react";
import "./Navbar.css";
import { Link } from "react-router-dom";
import { useSteering } from "../context/SteeringContext";
import { useSatel } from "../context/SatelContext";

// Ikony do Navbara
import Home from "../icons/home.svg";
import Memory from "../icons/memory.svg";
import GPS from "../icons/location.svg";
import Science from "../icons/science.svg";
import Vision from "../icons/vision.svg";
import Manipulator from "../icons/manipulator.svg";
import Satel from "../icons/satel.svg";

function currentDay() {
  const now = new Date();
  const monthName = new Intl.DateTimeFormat("en-US", { month: "long" }).format(now);
  return `${monthName} ${now.getFullYear()}`;
}

function getCurrentTime() {
  const now = new Date();
  const h = String(now.getHours()).padStart(2, "0");
  const m = String(now.getMinutes()).padStart(2, "0");
  const s = String(now.getSeconds()).padStart(2, "0");
  return `Godzina ${h}:${m}:${s}`;
}

const Navbar = ({ connectionStatus }) => {
  const [currentTime, setCurrentTime] = useState(getCurrentTime());
  const { controlMode, targetTopic, CONTROL_MODES } = useSteering();
  const { satelEnabled, satel } = useSatel();

  useEffect(() => {
    setCurrentTime(getCurrentTime());
    const now = new Date();
    const delay = 1000 - now.getMilliseconds();
    const timeout = setTimeout(() => {
      setCurrentTime(getCurrentTime());
      const interval = setInterval(() => setCurrentTime(getCurrentTime()), 1000);
      return () => clearInterval(interval);
    }, delay);
    return () => clearTimeout(timeout);
  }, []);

  // Determine steering badge
  const getSteeringBadge = () => {
    switch (controlMode) {
      case CONTROL_MODES.STEERING_NEW: return "🎮 STEERING";
      case CONTROL_MODES.JOYSTICK: return "🕹️ JOYSTICK";
      case CONTROL_MODES.BLUETOOTH_JETSON: return "📶 BT";
      case CONTROL_MODES.BLUETOOTH_MOBILE: return "📱 MOBILE";
      default: return null;
    }
  };

  const badge = getSteeringBadge();

  return (
    <div>
      <div className="navbar">
        <div className="navbar__item">
          {currentDay()} {currentTime}
        </div>
        <div className="navbar__item">
          Topic:{" "}
          <span style={{ color: "orange", fontWeight: "bold" }}>/{targetTopic}</span>
          {badge && (
            <span className="steering-badge">{badge}</span>
          )}
          {satelEnabled && (
            <span className="steering-badge" style={{ background: satel.isConnected ? "#16a34a" : "#ca8a04", marginLeft: "0.5rem" }}>
              📡 SATEL {satel.isConnected ? "OK" : "WAIT"}
            </span>
          )}
        </div>
        <div className="navbar__item">
          Backend Status:{" "}
          {connectionStatus === true ? (
            <span className="status--connected">Connected</span>
          ) : (
            <span className="status--disconnected">
              Disconnected <span className="status__icon">❌</span>
            </span>
          )}
        </div>
        <div className="navbar__item">
          <span className="navbar__version">FrontV0.5</span>
        </div>
      </div>
      <div className="links-grid">
        <Link to="/" className="link-tile">
          Home <img src={Home} className="link-icon" alt="home-icon" />
        </Link>
        <Link to="/wizja" className="link-tile">
          Wizja <img src={Vision} className="link-icon" alt="vision-icon" />
        </Link>
        <Link to="/manipulator" className="link-tile">
          Manipulator <img src={Manipulator} className="link-icon" alt="manipulator-icon" />
        </Link>
        <Link to="/science" className="link-tile">
          Science <img src={Science} className="link-icon" alt="science-icon" />
        </Link>
        <Link to="/status-jetson" className="link-tile">
          Status Jetsona <img src={Memory} className="link-icon" alt="status-icon" />
        </Link>
        <Link to="/gps" className="link-tile">
          GPS <img src={GPS} className="link-icon" alt="gps-icon" />
        </Link>
        <Link to="/satel" className="link-tile">
          Satel <img src={Satel} className="link-icon" alt="satel-icon" />
        </Link>
      </div>
    </div>
  );
};

export default Navbar;
