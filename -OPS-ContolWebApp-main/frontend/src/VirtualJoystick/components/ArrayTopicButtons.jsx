import React from "react";
import { ARRAY_TOPIC_CONFIG, ManipulatorElements } from "../Constants.js";

const ArrayTopicButtons = ({ arrayState, speed = 1, sendArrayTopicButton, resetArrayTopicButton }) => {
  const scaledPositive = Math.round(ARRAY_TOPIC_CONFIG.POSITIVE_VALUE * speed);
  const scaledNegative = Math.round(ARRAY_TOPIC_CONFIG.NEGATIVE_VALUE * speed);
  const handleButtonInteraction = (buttonId, value, eventType) => {
    if (eventType === "start") {
      sendArrayTopicButton(buttonId, value);
    } else if (eventType === "end") {
      resetArrayTopicButton(buttonId);
    }
  };


  const createButton = (buttonId, value, className, label,elementName) => (
    <button
      key={`${className}-${buttonId}`}
      className={`topic-btn ${className}`}
      onMouseDown={() => handleButtonInteraction(buttonId, value, "start")}
      onMouseUp={() => handleButtonInteraction(buttonId, value, "end")}
      onTouchStart={() => handleButtonInteraction(buttonId, value, "start")}
      onTouchEnd={() => handleButtonInteraction(buttonId, value, "end")}
    >
      {label}
      {elementName}
    </button>
  );

  return (
    <div className="topic-buttons-wrapper">
      <div className="topic-buttons-grid">
        {Array.from({ length: ARRAY_TOPIC_CONFIG.BUTTON_COUNT }, (_, i) =>
          createButton(
            i + 1,
            ARRAY_TOPIC_CONFIG.POSITIVE_VALUE,
            "plus",
            `+${scaledPositive} [${i + 1}]`,
            ManipulatorElements[i]
          )
        )}
        {Array.from({ length: ARRAY_TOPIC_CONFIG.BUTTON_COUNT }, (_, i) =>
          createButton(
            i + 1,
            ARRAY_TOPIC_CONFIG.NEGATIVE_VALUE,
            "minus",
            `${scaledNegative} [${i + 1}]`,
            ManipulatorElements[i]
          )
        )}
      </div>
      <div className="array-state">
        Aktualny stan: [ {arrayState.join(", ")} ]
      </div>
    </div>
  );
};

export default ArrayTopicButtons;