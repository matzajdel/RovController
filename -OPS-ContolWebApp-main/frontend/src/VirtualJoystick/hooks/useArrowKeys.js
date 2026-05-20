// hooks/useArrowKeys.js
import { useEffect, useRef, useCallback, useState } from "react";
import { ARROW_KEY_GROUPS, BACKEND_CONFIG } from "../Constants.js";

const AXIS_NAMES = ["VERTICAL", "HORIZONTAL"];

/**
 * Hook that manages multiple key-controlled groups.
 *
 * Each group in ARROW_KEY_GROUPS has its own shared array, topic, and axes.
 * The hook listens for all configured keys simultaneously and publishes
 * to the correct topic when a key is pressed.
 *
 * Returns an array of group controllers (same order as ARROW_KEY_GROUPS):
 *   { name, values (ref), directions, toggleDirection, axes (config) }
 */
export const useArrowKeys = (enabled = true) => {
  /* ── Active group (only one responds to keys at a time) ─── */
  const [activeGroup, setActiveGroup] = useState(0);
  const activeGroupRef = useRef(activeGroup);
  useEffect(() => { activeGroupRef.current = activeGroup; }, [activeGroup]);

  /* ── Build initial state for all groups ─────────────────── */
  const buildDirs = () =>
    ARROW_KEY_GROUPS.map((g) =>
      Object.fromEntries(AXIS_NAMES.map((a) => [a, g.AXES[a].DIRECTION]))
    );

  const buildVals = () =>
    ARROW_KEY_GROUPS.map((g) =>
      Object.fromEntries(AXIS_NAMES.map((a) => [a, g.AXES[a].DEFAULT_VALUE]))
    );

  const [allDirs, setAllDirs] = useState(buildDirs);
  const valRefs = useRef(buildVals());
  const dirsRef = useRef(allDirs);
  useEffect(() => { dirsRef.current = allDirs; }, [allDirs]);

  // One shared-array snapshot per group
  const sharedArraysRef = useRef(
    ARROW_KEY_GROUPS.map((g) => (g.SHARED_ARRAY ? [...g.SHARED_ARRAY.TEMPLATE] : null))
  );

  /* ── Publish helper ────────────────────────────────────────── */
  const publish = useCallback(async (groupIdx, axis, value) => {
    const group = ARROW_KEY_GROUPS[groupIdx];
    const shared = group.SHARED_ARRAY;
    let topic, msgType, data, extraBody = {};

    if (shared) {
      const axisCfg = group.AXES[axis];
      // Use partial update: only change the controlled index,
      // the backend keeps all other indices as they were.
      topic = shared.TOPIC;
      msgType = shared.MSG_TYPE;
      data = [value];
      extraBody = { update_index: axisCfg.ARRAY_INDEX };
    } else {
      const axisCfg = group.AXES[axis];
      topic = axisCfg.TOPIC;
      msgType = axisCfg.MSG_TYPE;
      data = [axisCfg.ID, value];
    }

    try {
      const res = await fetch(`${BACKEND_CONFIG.BACKEND_URL}/custom_topic`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ topic, data, msg_type: msgType, ...extraBody }),
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      console.log(`[ArrowKeys:${group.name}] ${topic} (${msgType}) index=${extraBody.update_index ?? 'full'} → ${value}`);
    } catch (err) {
      console.error(`[ArrowKeys:${group.name}] error (${topic}):`, err);
    }
  }, []);

  /* ── Key listener (scans all groups × axes) ────────────────── */
  useEffect(() => {
    if (!enabled) return;

    const handleKeyDown = (e) => {
      // All groups respond to their keys simultaneously
      for (let gi = 0; gi < ARROW_KEY_GROUPS.length; gi++) {
        const group = ARROW_KEY_GROUPS[gi];
        for (const axis of AXIS_NAMES) {
          const cfg = group.AXES[axis];
          const dir = dirsRef.current[gi][axis];
          let delta = null;

          if (e.key === cfg.KEYS.PLUS) delta = cfg.STEP * dir;
          if (e.key === cfg.KEYS.MINUS) delta = -cfg.STEP * dir;

          if (delta !== null) {
            e.preventDefault();
            const cur = valRefs.current[gi][axis];
            let next;
            if (cfg.WRAP) {
              // Wrap-around: overflow past MAX → MIN, underflow past MIN → MAX
              next = cur + delta;
              if (next > cfg.MAX) next = cfg.MIN;
              if (next < cfg.MIN) next = cfg.MAX;
            } else {
              next = Math.max(cfg.MIN, Math.min(cfg.MAX, cur + delta));
            }
            if (next !== cur) {
              valRefs.current[gi][axis] = next;
              publish(gi, axis, next);
            }
            return; // one key → one axis
          }
        }
      }

      // Tab cycles through groups
      if (e.key === "Tab") {
        e.preventDefault();
        const next = (activeGroupRef.current + 1) % ARROW_KEY_GROUPS.length;
        activeGroupRef.current = next;
        setActiveGroup(next);
      }
    };

    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [enabled, publish]);

  /* ── Direction toggle ──────────────────────────────────────── */
  const toggleDirection = useCallback((groupIdx, axis) => {
    setAllDirs((prev) => {
      const next = [...prev];
      next[groupIdx] = { ...next[groupIdx], [axis]: next[groupIdx][axis] * -1 };
      return next;
    });
  }, []);

  /* ── Build per-group controller objects ─────────────────────── */
  const groups = ARROW_KEY_GROUPS.map((groupCfg, gi) => ({
    name: groupCfg.name,
    config: groupCfg,
    values: valRefs,           // valRefs.current[gi].VERTICAL / .HORIZONTAL
    groupIndex: gi,
    directions: allDirs[gi],
    toggleDirection: (axis) => toggleDirection(gi, axis),
    /** Full shared array snapshot (read sharedArrays.current[gi]) */
    sharedArrays: sharedArraysRef,
    isActive: gi === activeGroup,
  }));

  return { groups, activeGroup, setActiveGroup };
};
