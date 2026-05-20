import { useRef, useEffect } from 'react';
import * as THREE from 'three';
import { useFrame } from '@react-three/fiber';

/**
 * URDF Robot 3D model renderer
 * 
 * Procedural Three.js model matching the URDF kinematic tree:
 *   base_link
 *     ├── 4× steer_*_link (yaw) → wheel (spin)   ← crab drive
 *     └── arm_base_link → shoulder → elbow → wrist → gripper
 *
 * Joint states are read from the `jointStates` prop every frame.
 */
export function URDFRobot({ urdf, jointStates, showAxes }) {
  const robotRef = useRef();
  const jointsRef = useRef({});

  useEffect(() => {
    if (!urdf || !robotRef.current) return;
    console.log('URDF loaded, length:', urdf.length);
  }, [urdf]);

  // Update joint positions from jointStates
  useFrame(() => {
    if (!jointStates || !robotRef.current) return;

    Object.entries(jointStates).forEach(([jointName, value]) => {
      const joint = jointsRef.current[jointName];
      if (joint) {
        joint.rotation.z = value;
      }
    });
  });

  return (
    <group ref={robotRef}>
      <RoverChassis jointStates={jointStates} jointsRef={jointsRef} />
      <ManipulatorArm
        jointStates={jointStates}
        jointsRef={jointsRef}
        showAxes={showAxes}
      />
    </group>
  );
}

/**
 * Rover chassis with 4 crab-drive wheels.
 * Each wheel is wrapped in a steering group that rotates on Z (yaw).
 */
function RoverChassis({ jointStates, jointsRef }) {
  const steerFL = jointStates?.steer_front_left || 0;
  const steerFR = jointStates?.steer_front_right || 0;
  const steerRL = jointStates?.steer_rear_left || 0;
  const steerRR = jointStates?.steer_rear_right || 0;

  const wheels = [
    { pos: [0.25, -0.07, 0.25], steer: steerFL, name: 'steer_front_left', label: 'FL' },
    { pos: [0.25, -0.07, -0.25], steer: steerFR, name: 'steer_front_right', label: 'FR' },
    { pos: [-0.25, -0.07, 0.25], steer: steerRL, name: 'steer_rear_left', label: 'RL' },
    { pos: [-0.25, -0.07, -0.25], steer: steerRR, name: 'steer_rear_right', label: 'RR' },
  ];

  return (
    <group position={[0, 0.15, 0]}>
      {/* Main chassis */}
      <mesh castShadow receiveShadow>
        <boxGeometry args={[0.6, 0.15, 0.4]} />
        <meshStandardMaterial
          color="#2c3e50"
          metalness={0.6}
          roughness={0.4}
        />
      </mesh>

      {/* Wheels with steering pivots */}
      {wheels.map((w, i) => (
        <group key={i} position={w.pos}>
          {/* Steering pivot (yaw on Z) */}
          <group
            rotation={[0, w.steer, 0]}
            ref={(el) => { if (el) jointsRef.current[w.name] = el; }}
          >
            {/* Steering knuckle indicator */}
            <mesh>
              <cylinderGeometry args={[0.025, 0.025, 0.04, 8]} />
              <meshStandardMaterial color="#555" metalness={0.7} roughness={0.3} />
            </mesh>

            {/* Wheel (spin around Y via the cylinder, visually rotated to side) */}
            <mesh rotation={[0, 0, Math.PI / 2]} castShadow>
              <cylinderGeometry args={[0.08, 0.08, 0.06, 16]} />
              <meshStandardMaterial color="#1a1a1a" metalness={0.8} roughness={0.3} />
            </mesh>

            {/* Tire tread rings */}
            <mesh rotation={[0, 0, Math.PI / 2]}>
              <torusGeometry args={[0.08, 0.008, 6, 16]} />
              <meshStandardMaterial color="#333" metalness={0.4} roughness={0.8} />
            </mesh>

            {/* Direction arrow (visible when steered) */}
            <mesh position={[0.10, 0, 0]} rotation={[0, 0, -Math.PI / 2]}>
              <coneGeometry args={[0.015, 0.04, 6]} />
              <meshStandardMaterial
                color="#4ecdc4"
                emissive="#4ecdc4"
                emissiveIntensity={Math.abs(w.steer) > 0.05 ? 0.6 : 0.0}
              />
            </mesh>
          </group>
        </group>
      ))}

      {/* Solar panel on top */}
      <mesh position={[0, 0.12, 0]} castShadow>
        <boxGeometry args={[0.5, 0.02, 0.35]} />
        <meshStandardMaterial
          color="#1e3a8a"
          metalness={0.7}
          roughness={0.2}
          emissive="#1e3a8a"
          emissiveIntensity={0.1}
        />
      </mesh>

      {/* Antenna */}
      <mesh position={[-0.22, 0.20, 0.12]}>
        <cylinderGeometry args={[0.005, 0.005, 0.15, 6]} />
        <meshStandardMaterial color="#888" metalness={0.8} roughness={0.2} />
      </mesh>
      <mesh position={[-0.22, 0.28, 0.12]}>
        <sphereGeometry args={[0.012, 8, 8]} />
        <meshStandardMaterial color="#e74c3c" emissive="#e74c3c" emissiveIntensity={0.3} />
      </mesh>
    </group>
  );
}

/**
 * 6-DOF Manipulator arm with full joint control
 */
function ManipulatorArm({ jointStates, jointsRef, showAxes }) {
  const baseRotation = jointStates?.joint_base || 0;
  const shoulderAngle = jointStates?.joint_shoulder || 0;
  const elbowAngle = jointStates?.joint_elbow || 0;
  const wristPitch = jointStates?.joint_wrist_pitch || 0;
  const wristRoll = jointStates?.joint_wrist_roll || 0;
  const gripperOpen = jointStates?.joint_gripper || 0;

  return (
    <group position={[0, 0.23, 0]}>
      {/* Axes helper at base */}
      {showAxes && <axesHelper args={[0.3]} />}

      {/* Base rotation (Yaw) */}
      <group
        rotation={[0, baseRotation, 0]}
        ref={(el) => { if (el) jointsRef.current.joint_base = el; }}
      >
        <mesh position={[0, 0.05, 0]} castShadow>
          <cylinderGeometry args={[0.08, 0.08, 0.1, 16]} />
          <meshStandardMaterial color="#e74c3c" metalness={0.5} roughness={0.4} />
        </mesh>

        {/* Shoulder joint (Pitch) */}
        <group
          position={[0, 0.1, 0]}
          rotation={[0, 0, shoulderAngle]}
          ref={(el) => { if (el) jointsRef.current.joint_shoulder = el; }}
        >
          {showAxes && <axesHelper args={[0.2]} />}

          {/* Upper arm link */}
          <mesh position={[0, 0.15, 0]} castShadow>
            <boxGeometry args={[0.06, 0.3, 0.06]} />
            <meshStandardMaterial color="#e67e22" metalness={0.4} roughness={0.5} />
          </mesh>

          {/* Elbow joint */}
          <group
            position={[0, 0.3, 0]}
            rotation={[0, 0, elbowAngle]}
            ref={(el) => { if (el) jointsRef.current.joint_elbow = el; }}
          >
            {showAxes && <axesHelper args={[0.15]} />}

            {/* Forearm link */}
            <mesh position={[0, 0.12, 0]} castShadow>
              <boxGeometry args={[0.05, 0.24, 0.05]} />
              <meshStandardMaterial color="#f39c12" metalness={0.4} roughness={0.5} />
            </mesh>

            {/* Wrist pitch */}
            <group
              position={[0, 0.24, 0]}
              rotation={[0, 0, wristPitch]}
              ref={(el) => { if (el) jointsRef.current.joint_wrist_pitch = el; }}
            >
              {showAxes && <axesHelper args={[0.1]} />}

              {/* Wrist link */}
              <mesh position={[0, 0.05, 0]} castShadow>
                <cylinderGeometry args={[0.03, 0.03, 0.1, 12]} />
                <meshStandardMaterial color="#3498db" metalness={0.6} roughness={0.3} />
              </mesh>

              {/* Wrist roll */}
              <group
                position={[0, 0.1, 0]}
                rotation={[wristRoll, 0, 0]}
                ref={(el) => { if (el) jointsRef.current.joint_wrist_roll = el; }}
              >
                {showAxes && <axesHelper args={[0.08]} />}

                {/* Gripper base */}
                <mesh position={[0, 0.03, 0]} castShadow>
                  <boxGeometry args={[0.08, 0.06, 0.04]} />
                  <meshStandardMaterial color="#2ecc71" metalness={0.5} roughness={0.4} />
                </mesh>

                {/* Gripper fingers */}
                <group
                  ref={(el) => { if (el) jointsRef.current.joint_gripper = el; }}
                >
                  {/* Left finger */}
                  <mesh position={[-gripperOpen / 2 - 0.02, 0.08, 0]} castShadow>
                    <boxGeometry args={[0.015, 0.08, 0.025]} />
                    <meshStandardMaterial color="#27ae60" metalness={0.6} roughness={0.3} />
                  </mesh>

                  {/* Right finger */}
                  <mesh position={[gripperOpen / 2 + 0.02, 0.08, 0]} castShadow>
                    <boxGeometry args={[0.015, 0.08, 0.025]} />
                    <meshStandardMaterial color="#27ae60" metalness={0.6} roughness={0.3} />
                  </mesh>

                  {/* End-effector indicator */}
                  <mesh position={[0, 0.12, 0]}>
                    <sphereGeometry args={[0.015, 16, 16]} />
                    <meshStandardMaterial
                      color="#ffe66d"
                      emissive="#ff6b00"
                      emissiveIntensity={0.5}
                    />
                  </mesh>
                </group>
              </group>
            </group>
          </group>
        </group>
      </group>
    </group>
  );
}
