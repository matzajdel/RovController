// hooks/useCustomTopics.js
import { useState, useCallback, useRef } from "react";
import { CUSTOM_TOPIC_BUTTONS, BACKEND_CONFIG } from "../Constants.js";

/**
 * Hook that manages state and publishing for every entry in
 * CUSTOM_TOPIC_BUTTONS.
 *
 * Returns an array of controller objects (same order as the config)
 * with: { config, value, direction, press, release, increment,
 *          decrement, toggleDirection, setValue }
 */
export const useCustomTopics = () => {
  // One state slot per button config
  const [values, setValues] = useState(() =>
    CUSTOM_TOPIC_BUTTONS.map((cfg) => cfg.defaultValue)
  );
  const [directions, setDirections] = useState(() =>
    CUSTOM_TOPIC_BUTTONS.map(() => 1)
  );
  // Keep refs so event handlers always see fresh values
  const valuesRef = useRef(values);
  valuesRef.current = values;

  /* ── Publish helper ─────────────────────────────────────────── */
  const publish = useCallback(async (topic, id, value, msgType) => {
    try {
      const res = await fetch(`${BACKEND_CONFIG.BACKEND_URL}/custom_topic`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ topic, data: [id, value], msg_type: msgType || "Int32MultiArray" }),
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      console.log(`[CustomTopic] ${topic} (${msgType}) → [${id}, ${value}]`);
    } catch (err) {
      console.error(`[CustomTopic] publish error (${topic}):`, err);
    }
  }, []);

  /* ── Per-button actions ─────────────────────────────────────── */

  const updateValue = useCallback((idx, newVal) => {
    setValues((prev) => {
      const next = [...prev];
      next[idx] = newVal;
      return next;
    });
  }, []);

  const press = useCallback(
    (idx) => {
      const cfg = CUSTOM_TOPIC_BUTTONS[idx];
      if (cfg.mode === "incremental") return; // handled by increment/decrement
      const val = cfg.pressValue ?? cfg.defaultValue;
      updateValue(idx, val);
      publish(cfg.topic, cfg.id, val);
    },
    [publish, updateValue]
  );

  const release = useCallback(
    (idx) => {
      const cfg = CUSTOM_TOPIC_BUTTONS[idx];
      if (cfg.mode === "set_release") {
        updateValue(idx, cfg.defaultValue);
        publish(cfg.topic, cfg.id, cfg.defaultValue);
      }
      // "set" and "incremental" do nothing on release
    },
    [publish, updateValue]
  );

  const increment = useCallback(
    (idx) => {
      const cfg = CUSTOM_TOPIC_BUTTONS[idx];
      const dir = directions[idx] ?? 1;
      const step = (cfg.step ?? 5) * dir;
      const cur = valuesRef.current[idx];
      const clamped = Math.max(cfg.min ?? -Infinity, Math.min(cfg.max ?? Infinity, cur + step));
      if (clamped !== cur) {
        updateValue(idx, clamped);
        publish(cfg.topic, cfg.id, clamped);
      }
    },
    [publish, updateValue, directions]
  );

  const decrement = useCallback(
    (idx) => {
      const cfg = CUSTOM_TOPIC_BUTTONS[idx];
      const dir = directions[idx] ?? 1;
      const step = (cfg.step ?? 5) * dir;
      const cur = valuesRef.current[idx];
      const clamped = Math.max(cfg.min ?? -Infinity, Math.min(cfg.max ?? Infinity, cur - step));
      if (clamped !== cur) {
        updateValue(idx, clamped);
        publish(cfg.topic, cfg.id, clamped);
      }
    },
    [publish, updateValue, directions]
  );

  const toggleDirection = useCallback((idx) => {
    setDirections((prev) => {
      const next = [...prev];
      next[idx] = prev[idx] * -1;
      return next;
    });
  }, []);

  const setValueDirect = useCallback(
    (idx, val) => {
      const cfg = CUSTOM_TOPIC_BUTTONS[idx];
      updateValue(idx, val);
      publish(cfg.topic, cfg.id, val, cfg.msgType);
    },
    [publish, updateValue]
  );

  /* ── Build controller array ─────────────────────────────────── */
  const controllers = CUSTOM_TOPIC_BUTTONS.map((cfg, idx) => ({
    config: cfg,
    value: values[idx],
    direction: directions[idx],
    press: () => press(idx),
    release: () => release(idx),
    increment: () => increment(idx),
    decrement: () => decrement(idx),
    toggleDirection: () => toggleDirection(idx),
    setValue: (v) => setValueDirect(idx, v),
  }));

  return controllers;
};
