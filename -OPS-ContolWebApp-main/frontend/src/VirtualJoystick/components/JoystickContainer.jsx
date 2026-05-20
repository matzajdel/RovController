import React, { useEffect, useRef } from "react";
import nipplejs from "nipplejs";
import ArrayTopicButtons from "./ArrayTopicButtons";
import { JOYSTICK_CONFIG, BACKEND_CONFIG } from "../Constants.js";

const JoystickContainer = ({
  speed,
  sendJoystickCommand,
  sendJoystickRelease,
  activateJoystick,
  deactivateJoystick,
  arrayState,
  sendArrayTopicButton,
  resetArrayTopicButton
}) => {
  const joystickRef = useRef(null);
  const managerRef = useRef(null);

  useEffect(() => {
    const cleanupResources = () => {
      if (managerRef.current) {
        managerRef.current.destroy();
        managerRef.current = null;
      }
    };

    const joystickContainer = joystickRef.current;
    if (!joystickContainer) return cleanupResources;

    activateJoystick();

    managerRef.current = nipplejs.create({
      zone: joystickContainer,
      mode: "static",
      position: { left: "50%", top: "50%" },
      color: JOYSTICK_CONFIG.COLOR,
      size: JOYSTICK_CONFIG.SIZE,
    });

    managerRef.current.on("move", (evt, data) => {
      const angle = data.angle?.radian || 0;
      const distance = Math.min(data.distance || 0, JOYSTICK_CONFIG.MAX_DISTANCE);

      const forward = (distance / 100) * Math.cos(angle);
      const turn = -(distance / 100) * Math.sin(angle);

      const sent = sendJoystickCommand(turn, forward, speed);
      if (!sent) {
        sendRestCommand(turn, forward, speed);
      }
    });

    managerRef.current.on("end", () => {
      const sent = sendJoystickRelease();
      if (!sent) {
        sendRestCommand(0, 0, speed);
      }
      console.log("Joystick released: sending stop command");
    });

    return () => {
      cleanupResources();
      deactivateJoystick();
    };
  }, [speed, sendJoystickCommand, sendJoystickRelease, activateJoystick, deactivateJoystick]);

  const sendRestCommand = async (x, y, speed) => {
    try {
      const response = await fetch(`${BACKEND_CONFIG.BACKEND_URL}/joystick`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          x: x * speed,
          y: y * speed,
          timestamp: new Date().toISOString(),
        }),
      });

      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }

      const result = await response.json();
      console.log("Command sent successfully:", result);
    } catch (error) {
      console.error("Error sending REST command:", error);
    }
  };

  return (
    <div className="joystick-container">
      <div ref={joystickRef} className="joystick" />
      <p className="joystick-info">
        Use the joystick above to control the robot.
        <br />
        Forward/Back: Y-axis, Left/Right: X-axis
        <br />
        Commands sent to <strong>/cmd_vel</strong> topic
      </p>
      <ArrayTopicButtons
        arrayState={arrayState}
        speed={speed}
        sendArrayTopicButton={sendArrayTopicButton}
        resetArrayTopicButton={resetArrayTopicButton}
      />
    </div>
  );
};

export default JoystickContainer;