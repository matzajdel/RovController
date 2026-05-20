// hooks/useArrayTopicButtons.js
import { useState } from "react";
import { ARRAY_TOPIC_CONFIG, BACKEND_CONFIG } from "../Constants.js";

export const useArrayTopicButtons = (speed = 1) => {
  const [arrayState, setArrayState] = useState(
    Array(ARRAY_TOPIC_CONFIG.BUTTON_COUNT).fill(ARRAY_TOPIC_CONFIG.RESET_VALUE)
  );

  const sendArrayTopicButton = async (buttonId, value) => {
    const scaledValue =
      value === ARRAY_TOPIC_CONFIG.RESET_VALUE
        ? ARRAY_TOPIC_CONFIG.RESET_VALUE
        : Math.round(value * speed);

    try {
      const response = await fetch(
        `${BACKEND_CONFIG.BACKEND_URL}/array_topic/${buttonId}`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ value: scaledValue }),
        }
      );
      
      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }
      
      setArrayState((prev) =>
        prev.map((v, i) => (i === buttonId - 1 ? scaledValue : v))
      );
      
      console.log(
        `Button ${buttonId} set to ${scaledValue} (base ${value}, speed ${speed.toFixed(2)}) sent to /array_topic`
      );
    } catch (error) {
      console.error(`Error sending array_topic button ${buttonId}:`, error);
    }
  };

  const resetArrayTopicButton = async (buttonId) => {
    await sendArrayTopicButton(buttonId, ARRAY_TOPIC_CONFIG.RESET_VALUE);
  };

  return {
    arrayState,
    sendArrayTopicButton,
    resetArrayTopicButton,
  };
};