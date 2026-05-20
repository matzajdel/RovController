/**
 * Robot 3D Visualization Component
 * 
 * Interactive 3D visualization of the robot manipulator using Three.js and React Three Fiber.
 * 
 * Features:
 * - URDF model loading and rendering
 * - Real-time joint state visualization via WebSocket
 * - Manual joint control with sliders
 * - Preset position buttons for common poses
 * - Multiple camera views (orbit, top-down, follow end-effector)
 * - Toggleable grid and axis helpers
 * - Interactive 3D scene navigation
 */
import { Canvas } from '@react-three/fiber';
import { OrbitControls, PerspectiveCamera, Grid, Environment, Sky } from '@react-three/drei';
import { Suspense, useState, useEffect, useRef } from 'react';
import { URDFRobot } from './URDFRobot';
import { JointControls } from './JointControls';
import { PresetButtons } from './PresetButtons';
import { ViewControls } from './ViewControls';
import { useRobotWebSocket } from './hooks/useRobotWebSocket';
import { BACKEND_URL, WS_URL } from '../config';
import './RobotView.css';

/**
 * Main Robot 3D Visualization Tab
 * Displays URDF model with interactive controls
 */
export function RobotView() {
  // Component state
  const [urdfData, setUrdfData] = useState(null);
  const [jointStates, setJointStates] = useState({});
  const [selectedView, setSelectedView] = useState('orbit'); // Camera view mode
  const [showGrid, setShowGrid] = useState(true);
  const [showAxes, setShowAxes] = useState(true);

  // Refs for camera and controls
  const cameraRef = useRef();
  const controlsRef = useRef();

  // WebSocket connection for real-time joint states
  const {
    connected,
    jointState,
    sendJointCommand,
    requestState
  } = useRobotWebSocket(`${WS_URL.replace('/ws', '')}/robot/ws`);

  /**
   * Fetch URDF model from backend on component mount
   */
  useEffect(() => {
    fetchURDF();
  }, []);

  /**
   * Update local joint states when WebSocket data arrives
   */
  useEffect(() => {
    if (jointState && jointState.joints) {
      setJointStates(jointState.joints);
    }
  }, [jointState]);

  /**
   * Fetch the robot URDF description from the backend
   */
  const fetchURDF = async () => {
    try {
      const response = await fetch(`${BACKEND_URL}/robot/urdf`);
      const data = await response.json();
      setUrdfData(data.urdf);
      console.log('URDF loaded:', data.source);
    } catch (error) {
      console.error('Failed to fetch URDF:', error);
      // Use minimal fallback if fetch fails
      setUrdfData(null);
    }
  };

  /**
   * Handle joint position change from slider
   * @param {string} jointName - Name of the joint to control
   * @param {number} value - Target position value
   */
  const handleJointChange = async (jointName, value) => {
    // Update local state immediately for responsive UI
    setJointStates(prev => ({
      ...prev,
      [jointName]: value
    }));

    // Send command to backend
    await sendJointCommand({
      joint_names: [jointName],
      positions: [value],
      duration: 0.5
    });
  };

  /**
   * Execute a preset pose
   * @param {string} presetName - Name of the preset to execute
   */
  const handlePresetClick = async (presetName) => {
    try {
      const response = await fetch(`${BACKEND_URL}/robot/preset/${presetName}`, {
        method: 'POST'
      });
      const result = await response.json();
      console.log(`Preset ${presetName} executed:`, result);

      // Update local state with preset positions
      if (result.joints) {
        setJointStates(result.joints);
      }
    } catch (error) {
      console.error('Failed to execute preset:', error);
    }
  };

  /**
   * Handle camera view change
   * @param {string} view - View mode ('orbit', 'top-down', 'follow-ee')
   */
  const handleViewChange = (view) => {
    setSelectedView(view);

    if (cameraRef.current && controlsRef.current) {
      switch (view) {
        case 'top-down':
          // Position camera directly above the robot
          cameraRef.current.position.set(0, 5, 0.01);
          controlsRef.current.target.set(0, 0, 0);
          break;
        case 'orbit':
          // Standard orbit view
          cameraRef.current.position.set(3, 2, 3);
          controlsRef.current.target.set(0, 0.5, 0);
          break;
        case 'front':
          cameraRef.current.position.set(0, 1, 4);
          controlsRef.current.target.set(0, 0.5, 0);
          break;
        case 'side':
          cameraRef.current.position.set(4, 1, 0);
          controlsRef.current.target.set(0, 0.5, 0);
          break;
      }
      controlsRef.current.update();
    }
  };

  return (
    <div className="robot-view-container">
      <div className="robot-view-header">
        <h1>🤖 Manipulator & Rover Visualization</h1>
        <div className="connection-status">
          <span className={`status-indicator ${connected ? 'connected' : 'disconnected'}`} />
          <span>{connected ? 'Connected' : 'Disconnected'}</span>
        </div>
      </div>

      <div className="robot-view-main">
        {/* 3D Canvas */}
        <div className="canvas-container">
          <Canvas shadows>
            <PerspectiveCamera
              ref={cameraRef}
              makeDefault
              position={[3, 2, 3]}
              fov={50}
            />

            <OrbitControls
              ref={controlsRef}
              enableDamping
              dampingFactor={0.05}
              target={[0, 0.5, 0]}
            />

            {/* Lighting */}
            <ambientLight intensity={0.5} />
            <directionalLight
              position={[5, 5, 5]}
              intensity={0.8}
              castShadow
              shadow-mapSize-width={2048}
              shadow-mapSize-height={2048}
            />
            <spotLight position={[-5, 5, 2]} intensity={0.3} />

            {/* Environment */}
            <Suspense fallback={null}>
              <Sky sunPosition={[100, 20, 100]} />
              <Environment preset="sunset" />
            </Suspense>

            {/* Grid */}
            {showGrid && (
              <Grid
                args={[10, 10]}
                cellSize={0.5}
                cellThickness={0.5}
                cellColor="#6f6f6f"
                sectionSize={1}
                sectionThickness={1}
                sectionColor="#9d4b4b"
                fadeDistance={25}
                fadeStrength={1}
                followCamera={false}
                infiniteGrid
              />
            )}

            {/* Robot Model */}
            <Suspense fallback={<Placeholder />}>
              {urdfData ? (
                <URDFRobot
                  urdf={urdfData}
                  jointStates={jointStates}
                  showAxes={showAxes}
                />
              ) : (
                <FallbackRobot jointStates={jointStates} />
              )}
            </Suspense>
          </Canvas>

          {/* View Controls Overlay */}
          <ViewControls
            selectedView={selectedView}
            onViewChange={handleViewChange}
            showGrid={showGrid}
            onToggleGrid={() => setShowGrid(!showGrid)}
            showAxes={showAxes}
            onToggleAxes={() => setShowAxes(!showAxes)}
          />
        </div>

        {/* Control Panel */}
        <div className="control-panel">
          <div className="control-section">
            <h3>🎮 Manipulator Control</h3>
            <JointControls
              jointStates={jointStates}
              onJointChange={handleJointChange}
              disabled={!connected}
            />
          </div>

          <div className="control-section">
            <h3>📋 Preset Positions</h3>
            <PresetButtons
              onPresetClick={handlePresetClick}
              disabled={!connected}
            />
          </div>

          <div className="control-section">
            <h3>📊 Status</h3>
            <div className="status-info">
              <div className="status-row">
                <span>Joints Active:</span>
                <span className="value">{Object.keys(jointStates).length}</span>
              </div>
              <div className="status-row">
                <span>URDF Loaded:</span>
                <span className="value">{urdfData ? '✓ Yes' : '✗ No'}</span>
              </div>
              <div className="status-row">
                <span>WebSocket:</span>
                <span className={`value ${connected ? 'success' : 'error'}`}>
                  {connected ? '✓ Connected' : '✗ Disconnected'}
                </span>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

/**
 * Loading placeholder for 3D scene
 */
function Placeholder() {
  return (
    <mesh>
      <boxGeometry args={[1, 1, 1]} />
      <meshStandardMaterial color="gray" wireframe />
    </mesh>
  );
}

/**
 * Fallback robot visualization (simple boxes)
 * Used when URDF is not available
 */
function FallbackRobot({ jointStates }) {
  const baseRotation = jointStates.joint_base || 0;
  const shoulderAngle = jointStates.joint_shoulder || 0;
  const elbowAngle = jointStates.joint_elbow || 0;

  return (
    <group>
      {/* Base */}
      <mesh position={[0, 0.1, 0]} receiveShadow castShadow>
        <boxGeometry args={[0.5, 0.2, 0.3]} />
        <meshStandardMaterial color="#555555" />
      </mesh>

      {/* Rotating base for manipulator */}
      <group rotation={[0, baseRotation, 0]}>
        {/* Shoulder joint */}
        <group position={[0, 0.2, 0]} rotation={[0, 0, shoulderAngle]}>
          <mesh position={[0, 0.15, 0]} castShadow>
            <boxGeometry args={[0.08, 0.3, 0.08]} />
            <meshStandardMaterial color="#ff6b6b" />
          </mesh>

          {/* Elbow joint */}
          <group position={[0, 0.3, 0]} rotation={[0, 0, elbowAngle]}>
            <mesh position={[0, 0.15, 0]} castShadow>
              <boxGeometry args={[0.06, 0.3, 0.06]} />
              <meshStandardMaterial color="#4ecdc4" />
            </mesh>

            {/* End effector */}
            <mesh position={[0, 0.3, 0]} castShadow>
              <sphereGeometry args={[0.05, 16, 16]} />
              <meshStandardMaterial color="#ffe66d" emissive="#ff6b00" emissiveIntensity={0.3} />
            </mesh>
          </group>
        </group>
      </group>

      {/* Ground shadow plane */}
      <mesh rotation={[-Math.PI / 2, 0, 0]} position={[0, 0, 0]} receiveShadow>
        <planeGeometry args={[10, 10]} />
        <shadowMaterial opacity={0.3} />
      </mesh>
    </group>
  );
}

export default RobotView;
