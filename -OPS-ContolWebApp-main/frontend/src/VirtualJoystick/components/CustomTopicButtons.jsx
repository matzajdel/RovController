import React from "react";
import "./CustomTopicButtons.css";

/**
 * Renders UI for every custom topic button defined in CUSTOM_TOPIC_BUTTONS.
 *
 * Each controller object comes from useCustomTopics() and has:
 *   config, value, direction, press, release, increment, decrement,
 *   toggleDirection, setValue
 */
const CustomTopicButtons = ({ controllers }) => {
  if (!controllers || controllers.length === 0) return null;

  return (
    <div className="custom-topic-wrapper">
      <h4 className="custom-topic-title">Custom Topics</h4>

      <div className="custom-topic-grid">
        {controllers.map((ctrl, idx) => {
          const { config: cfg, value, direction } = ctrl;
          const accent = cfg.color || "#4facfe";

          /* ── incremental ──────────────────────────────── */
          if (cfg.mode === "incremental") {
            return (
              <div className="ct-card" key={idx}>
                <span className="ct-label">{cfg.name}</span>
                <span className="ct-topic">{cfg.topic}</span>
                <span className="ct-value" style={{ color: accent }}>{value}</span>

                <div className="ct-btn-row">
                  <button
                    className="ct-btn ct-minus"
                    style={{ borderColor: accent }}
                    onMouseDown={ctrl.decrement}
                  >
                    −{cfg.step}
                  </button>
                  <button
                    className="ct-btn ct-plus"
                    style={{ borderColor: accent }}
                    onMouseDown={ctrl.increment}
                  >
                    +{cfg.step}
                  </button>
                </div>

                <div className="ct-btn-row ct-extra-row">
                  <button
                    className="ct-btn ct-dir"
                    onClick={ctrl.toggleDirection}
                    title="Flip +/− direction"
                  >
                    Dir: {direction > 0 ? "normal" : "invert"}
                  </button>
                  <button
                    className="ct-btn ct-reset"
                    onClick={() => ctrl.setValue(cfg.defaultValue)}
                  >
                    Reset ({cfg.defaultValue})
                  </button>
                </div>
              </div>
            );
          }

          /* ── set (press sets, stays) ──────────────────── */
          if (cfg.mode === "set") {
            const isActive = value === cfg.pressValue;
            return (
              <div className="ct-card" key={idx}>
                <span className="ct-label">{cfg.name}</span>
                <span className="ct-topic">{cfg.topic}</span>
                <span className="ct-value" style={{ color: accent }}>{value}</span>

                <div className="ct-btn-row">
                  <button
                    className={`ct-btn ct-set ${isActive ? "ct-active" : ""}`}
                    style={{ background: isActive ? accent : undefined }}
                    onClick={ctrl.press}
                  >
                    Set {cfg.pressValue}
                  </button>
                  <button
                    className="ct-btn ct-reset"
                    onClick={() => ctrl.setValue(cfg.defaultValue)}
                  >
                    Off ({cfg.defaultValue})
                  </button>
                </div>
              </div>
            );
          }

          /* ── set_release (press → value, release → default) */
          if (cfg.mode === "set_release") {
            return (
              <div className="ct-card" key={idx}>
                <span className="ct-label">{cfg.name}</span>
                <span className="ct-topic">{cfg.topic}</span>
                <span className="ct-value" style={{ color: accent }}>{value}</span>

                <div className="ct-btn-row">
                  <button
                    className="ct-btn ct-hold"
                    style={{ borderColor: accent }}
                    onMouseDown={ctrl.press}
                    onMouseUp={ctrl.release}
                    onMouseLeave={ctrl.release}
                    onTouchStart={ctrl.press}
                    onTouchEnd={ctrl.release}
                  >
                    Hold → {cfg.pressValue}
                  </button>
                </div>
              </div>
            );
          }

          return null;
        })}
      </div>
    </div>
  );
};

export default CustomTopicButtons;
