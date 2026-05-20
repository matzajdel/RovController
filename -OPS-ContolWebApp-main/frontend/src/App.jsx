/**
 * Main Application Component
 * 
 * Root component wrapping all routes in <SteeringProvider> so that
 * gamepad HID bridge and steering state persist across tab navigation.
 */
import { BrowserRouter, Route, Routes } from "react-router-dom";
import { SteeringProvider } from "./context/SteeringContext";
import { SatelProvider } from "./context/SatelContext";
import VirtualJoystick from "./VirtualJoystick/VirtualJoystick";
import Science from "./Science/Science";
import { StatusJetson } from "./StatusJetson/StatusJetson";
import Gps from "./GPS/Gps";
import Navbar from "./Navbar/Navbar";
import { useBackendHealth } from "./hooks/useBackendHealth.js";
import { Vision } from "./Vision/Vision.jsx";
import { CameraPopout } from "./Vision/CameraPopout.jsx";
import { RobotView } from "./RobotView/RobotView.jsx";
import { MicroRosLogs } from "./StatusJetson/MicroRosLogs";
import Satel from "./Satel/Satel";

function App() {
  const { backendData, isHealthy } = useBackendHealth();

  return (
    <div style={{ padding: "2rem", textAlign: "center" }}>
      <SatelProvider>
        <SteeringProvider>
        <BrowserRouter>
          <Routes>
            {/* Standalone route for camera popout window (no navigation bar) */}
            <Route path="/camera-popout" element={<CameraPopout />} />
            <Route path="/microros-logs" element={<MicroRosLogs />} />

            {/* Main application routes with navigation bar */}
            <Route path="*" element={
              <>
                <Navbar connectionStatus={isHealthy} />
                <Routes>
                  <Route path="/" element={<VirtualJoystick />} />
                  <Route path="/wizja" element={<Vision />} />
                  <Route path="/manipulator" element={<RobotView />} />
                  <Route path="/science" element={<Science />} />
                  <Route path="/status-jetson" element={<StatusJetson />} />
                  <Route path="/gps" element={<Gps />} />
                  <Route path="/satel" element={<Satel />} />
                </Routes>
              </>
            } />
          </Routes>
        </BrowserRouter>
        </SteeringProvider>
      </SatelProvider>
    </div>
  );
}

export default App;
