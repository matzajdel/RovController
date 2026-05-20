// constants.js
export const CONTROL_MODES = {
  OFF: "off",
  JOYSTICK: "joystick",
  BLUETOOTH_MOBILE: "bluetooth_mobile",
  BLUETOOTH_JETSON: "bluetooth_jetson",
  STEERING_NEW: "steering_new"
};

export const ManipulatorElements = [
  " dolny",
  " środek",
  " góra",
  " dolny",
  " środek",
  " góra"
]
// Re-export backend configuration from the shared config module
// so existing imports like `import { BACKEND_CONFIG } from "../Constants"`
// continue to work without changes.
import { BACKEND_CONFIG } from "../config";
export { BACKEND_CONFIG };


export const JOYSTICK_CONFIG = {
  SIZE: 275,
  COLOR: "blue",
  MAX_DISTANCE: 100,
  SPEED_MULTIPLIER: 4 / 3
};

export const ARRAY_TOPIC_CONFIG = {
  BUTTON_COUNT: 6,
  POSITIVE_VALUE: 100,
  NEGATIVE_VALUE: -100,
  RESET_VALUE: 0
};

/**
 * GAMEPAD → ARRAY_TOPIC MAPPING
 * ==============================
 * Mapowanie fizycznych przycisków pada na pozycje w /array_topic.
 *
 * Każdy wpis:
 *   gamepadButton  – indeks przycisku na padzie (0=A, 1=B, 2=X, 3=Y, 4=LB, 5=RB, ...)
 *   arrayIndex     – pozycja w tablicy /array_topic (1-6)
 *   pressValue     – wartość wysyłana przy wciśnięciu (np. 100 lub -100)
 *
 * Przy puszczeniu przycisku automatycznie wysyłana jest wartość 0 (reset).
 *
 * Standardowy pad (Xbox-style):
 *   0=A  1=B  2=X  3=Y  4=LB  5=RB  6=Back/View  7=Start/Menu
 *   8=L3(LS click) 9=R3(RS click) 10=Xbox/Home
 *   12=DUp 13=DDown 14=DLeft 15=DRight
 */
export const GAMEPAD_ARRAY_MAPPING = [
  { gamepadButton: 0,  arrayIndex: 1, pressValue:  70 },  // A       → slot 1 +100
  { gamepadButton: 1,  arrayIndex: 1, pressValue: -70 },  // B       → slot 1 -100
  { gamepadButton: 2,  arrayIndex: 5, pressValue:  -100 },  // X       → slot 2 +100
  { gamepadButton: 3,  arrayIndex: 5, pressValue: 100 },  // Y       → slot 2 -100
  { gamepadButton: 12, arrayIndex: 3, pressValue:  100 },  // DUp     → slot 3 +100
  { gamepadButton: 13, arrayIndex: 3, pressValue: -100 },  // DDown   → slot 3 -100
  { gamepadButton: 14, arrayIndex: 2, pressValue:  -100 },  // DLeft   → slot 4 -100
  { gamepadButton: 15, arrayIndex: 2, pressValue: 100 },  // DRight  → slot 4 +100
  { gamepadButton: 10, arrayIndex: 4, pressValue:  100 },  // L3 (LS click) → slot 5 +100
  { gamepadButton: 11, arrayIndex: 4, pressValue: -100 },  // R3 (RS click) → slot 5 -100
  { gamepadButton: 8,  arrayIndex: 6, pressValue: 100 },  // Ldziwny - Back/View     → slot 6 +100
  { gamepadButton: 9,  arrayIndex: 6, pressValue: -100 },  // Pdziwny - Start/Menu    → slot 6 -100
  // { gamepadButton: 10, arrayIndex: ?, pressValue: ? },  // Xbox/Home — wolny, odkomentuj w razie potrzeby
];

/**
 * PID-BASED GAMEPAD → CUSTOM TOPIC ARRAY MAPPING
 * ===============================================
 * Umozliwia mapowanie przyciskow po PID kontrolera na dowolny topic
 * publikowany jako MultiArray (domyslnie Int32MultiArray).
 *
 * Schemat wpisu (profil):
 *   pid                - Product ID gamepada (hex, np. "0ce6") lub "*" dla fallbacku
 *   happyButtonOffset  - (opcjonalne) liczba przycisków PRZED seriä BTN_TRIGGER_HAPPY
 *                        w Gamepad API. Potrzebne tylko gdy uzywa sie pola `evdevCode`.
 *                        Przyklad: jesli BTN_TRIGGER_HAPPY5 (evdev 708) pojawia sie
 *                        jako gp.buttons[18], to offset = 18 - (708-704) = 14.
 *                        Sprawdz prawidlowy indeks w sekcji RAW BUTTONS w GamepadDiagnostics.
 *   mappings[]:
 *     gamepadButton  - indeks przycisku w Gamepad API (0-based)
 *     evdevCode      - ALTERNATYWA dla gamepadButton: kod Linux evdev z evtest
 *                      (np. 708 = BTN_TRIGGER_HAPPY5, 710 = BTN_TRIGGER_HAPPY7)
 *                      Przeliczany jako: (evdevCode - 704) + happyButtonOffset
 *     topic          - ROS topic (np. "/pid_topic")
 *     msgType        - typ wiadomosci (np. "Int32MultiArray")
 *     arrayTemplate  - bazowa tablica wysylana na topic
 *     element        - numer elementu (1-based), np. 3 = trzeci element
 *     pressValue     - wartosc ustawiana przy wcisnieciu
 *     releaseValue   - wartosc ustawiana przy puszczeniu
 *
 * Jak znalezc happyButtonOffset:
 *   1. Podlacz pada i wejdz w tryb Sterowanie (GamepadDiagnostics jest widoczny).
 *   2. Wcisnij przycisk - sekcja "RAW BUTTONS" pokaze jego indeks w Gamepad API.
 *   3. offset = wyswietlony_indeks - (evdevCode - 704)
 *
 * Praktycznie:
 * - Dodaj nowy profil PID i kolejne wpisy w `mappings`, bez zmian w logice.
 * - Dla przegladarek, PID zwykle pochodzi z gamepad.id, np. "Vendor: 045e Product: 0ce6".
 */
export const GAMEPAD_PID_TOPIC_MAPPINGS = [
  {
    // Przyklad: mapowanie tylko dla konkretnego pada po Product ID.
    // Zmien "0b00" na PID Twojego kontrolera.
    pid: "0b00",
    // happyButtonOffset: ile przycisków jest PRZED seria BTN_TRIGGER_HAPPY w tym padzie.
    // Sprawdz w GamepadDiagnostics → RAW BUTTONS jaki indeks ma Twoj przycisk, np.:
    //   BTN_TRIGGER_HAPPY5 (evdev 708) wyswietla sie jako [17] → offset = 17 - 4 = 13
    happyButtonOffset: 13,
    mappings: [
      {
        // Mozna uzyc evdevCode zamiast gamepadButton:
        evdevCode: 708,   // BTN_TRIGGER_HAPPY5 → Gamepad API index = (708-704)+13 = 17
        topic: "/Hbridge",
        msgType: "Int8MultiArray",
        arrayTemplate: [0, 0, 0, 0],
        element: 2,
        pressValue: 100,
        releaseValue: 0,
      },
      {
        evdevCode: 709,   // BTN_TRIGGER_HAPPY7 → Gamepad API index = (710-704)+13 = 19
        topic: "/Hbridge",
        msgType: "Int8MultiArray",
        arrayTemplate: [0, 0, 0, 0],
        element: 2,
        pressValue: -100,
        releaseValue: 0,
      },{
        // Mozna uzyc evdevCode zamiast gamepadButton:
        evdevCode: 710,   // BTN_TRIGGER_HAPPY5 → Gamepad API index = (708-704)+13 = 17
        topic: "/Hbridge",
        msgType: "Int8MultiArray",
        arrayTemplate: [0, 0, 0, 0],
        element: 3,
        pressValue: -100,
        releaseValue: 0,
      },
      {
        evdevCode: 711,   // BTN_TRIGGER_HAPPY7 → Gamepad API index = (710-704)+13 = 19
        topic: "/Hbridge",
        msgType: "Int8MultiArray",
        arrayTemplate: [0, 0, 0, 0],
        element: 3,
        pressValue: 100,
        releaseValue: 0,
      },
    ],
  },
  {
    // Fallback dla kazdego innego pada.
    pid: "*",
    mappings: [],
  },
];

/**
 * ARROW / KEY GROUPS
 * ==================
 * Array of independent control groups.  Each group:
 *   - publishes ONE shared array to ONE topic,
 *   - has two axes (VERTICAL / HORIZONTAL) mapped to indices in that array,
 *   - is driven by its own pair of keys.
 *
 * To add a new group: copy any entry and change name, topic, template,
 * axes, keys, etc.
 *
 * If SHARED_ARRAY is removed from a group, the axes fall back to legacy
 * per-axis [id, value] mode.
 */
export const ARROW_KEY_GROUPS = [
  /* ── Group 0: Serwa (Up/Down → changes only index 3) ───── */
  {
    name: "Serwa",
    SHARED_ARRAY: {
      TOPIC: "/Serwa",
      MSG_TYPE: "UInt8MultiArray",
      TEMPLATE: [180, 180, 180, 0],   // indices 0-2 fixed at 180, only index 3 changes
    },
    AXES: {
      VERTICAL: {
        ARRAY_INDEX: 3,                // only modifies index 3 in [180,180,180,X]
        DEFAULT_VALUE: 90,
        STEP: 5,
        MIN: 0,
        MAX: 180,
        WRAP: true,
        DIRECTION: 1,
        KEYS: { PLUS: "ArrowUp", MINUS: "ArrowDown" },
        LABEL: "↕ Serwa[3]",
        DIR_ICONS: { POS: "↑+", NEG: "↑−" },
      },
      HORIZONTAL: {
        // Unused axis — Left/Right handled by serwoUART group
        ARRAY_INDEX: 3,
        DEFAULT_VALUE: 180, STEP: 0, MIN: 0, MAX: 0, DIRECTION: 1,
        KEYS: { PLUS: "_UNUSED_1", MINUS: "_UNUSED_2" },
        LABEL: "—", DIR_ICONS: { POS: "—", NEG: "—" },
      },
    },
  },

  /* ── Group 1: serwoUART (Left/Right arrows) ─────────────── */
  {
    name: "serwoUART",
    // No SHARED_ARRAY → per-axis [id, value] mode
    AXES: {
      VERTICAL: {
        // Unused axis
        TOPIC: "/serwoUART", MSG_TYPE: "Int32MultiArray", ID: 1,
        DEFAULT_VALUE: 180, STEP: 0, MIN: 0, MAX: 0, DIRECTION: 1,
        KEYS: { PLUS: "_UNUSED_3", MINUS: "_UNUSED_4" },
        LABEL: "—", DIR_ICONS: { POS: "—", NEG: "—" },
      },
      HORIZONTAL: {
        TOPIC: "/serwoUART",
        MSG_TYPE: "Int32MultiArray",
        ID: 1,
        DEFAULT_VALUE: 180,
        STEP: 5,
        MIN: 0,
        MAX: 360,
        WRAP: true,
        DIRECTION: 1,
        KEYS: { PLUS: "ArrowRight", MINUS: "ArrowLeft" },
        LABEL: "↔ serwoUART",
        DIR_ICONS: { POS: "→+", NEG: "→−" },
      },
    },
  },

  /* ── Group 2: Hbridge (WASD keys) ────────────────────────── */
  {
    name: "Hbridge",
    SHARED_ARRAY: {
      TOPIC: "/Hbridge",
      MSG_TYPE: "Int8MultiArray",
      TEMPLATE: [0, 0, 0, 0],      // 4-element; indices 0,3 are static
    },
    AXES: {
      VERTICAL: {
        ARRAY_INDEX: 0,
        DEFAULT_VALUE: 0,
        STEP: 10,
        MIN: -100,
        MAX: 100,
        DIRECTION: 1,
        KEYS: { PLUS: "w", MINUS: "s" },
        LABEL: "↕ Hbridge[1]",
        DIR_ICONS: { POS: "W+", NEG: "W−" },
      },
      HORIZONTAL: {
        ARRAY_INDEX: 3,
        DEFAULT_VALUE: 0,
        STEP: 10,
        MIN: -100,
        MAX: 100,
        DIRECTION: 1,
        KEYS: { PLUS: "d", MINUS: "a" },
        LABEL: "↔ Hbridge[2]",
        DIR_ICONS: { POS: "D+", NEG: "D−" },
      },
    },
  },
];

// Legacy alias – points to the first group's axes for any old code that
// referenced ARROW_KEY_CONFIG.VERTICAL / .HORIZONTAL directly.
export const ARROW_KEY_CONFIG = ARROW_KEY_GROUPS[0].AXES;

/**
 * CUSTOM TOPIC BUTTONS
 * ====================
 * Define any number of custom topic groups.  Each group creates a pair of
 * buttons (+ / −) and publishes an Int32MultiArray to the given ROS 2 topic.
 *
 * Fields:
 *   name         – display label
 *   topic        – ROS 2 topic name (auto-created if it doesn't exist)
 *   id           – first element of the [id, value] array sent
 *   defaultValue – starting value
 *   mode         – one of:
 *       "incremental"  → each press adds/subtracts `step`; value persists
 *       "set"          → press sends pressValue, stays there
 *       "set_release"  → press sends pressValue, release sends defaultValue
 *   step         – (incremental only) change per press
 *   min / max    – (incremental only) clamping range
 *   pressValue   – (set / set_release) value sent on press
 *   msgType      – ROS 2 message type: "Int8MultiArray", "Int32MultiArray" (default),
 *                   "Float32MultiArray", etc.
 *   color        – optional accent colour for the buttons
 */
export const CUSTOM_TOPIC_BUTTONS = [
  // NOTE: /Serwa, /serwoUART, and /Hbridge are managed by ARROW_KEY_GROUPS.
  // Do NOT add entries here for those topics.
  // Example: a simple on/off toggle that resets on release
  // {
  //   name: "Gripper",
  //   topic: "/gripper_cmd",
  //   id: 1,
  //   defaultValue: 0,
  //   mode: "set_release",
  //   pressValue: 100,
  //   color: "#ff6b6b",
  // },
  // Example: a "set" button — press sets value, stays there
  // {
  //   name: "Light",
  //   topic: "/light_cmd",
  //   id: 2,
  //   defaultValue: 0,
  //   mode: "set",
  //   pressValue: 255,
  //   color: "#ffd93d",
  // },
];

export const CONNECTION_STATUS = {
  CONNECTED: "connected",
  DISCONNECTED: "disconnected",
  ERROR: "error"
};