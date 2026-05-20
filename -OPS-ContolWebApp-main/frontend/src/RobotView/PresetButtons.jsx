/**
 * Preset position buttons for quick robot configurations
 */
export function PresetButtons({ onPresetClick, disabled }) {
  const presets = [
    { name: 'home', label: '🏠 Home', description: 'Safe home position' },
    { name: 'pickup', label: '🤏 Pickup', description: 'Ground pickup' },
    { name: 'inspect', label: '🔍 Inspect', description: 'Forward inspect' },
    { name: 'stow', label: '📦 Stow', description: 'Compact stow' },
  ];

  return (
    <div className="preset-buttons">
      {presets.map((preset) => (
        <button
          key={preset.name}
          className="preset-button"
          onClick={() => onPresetClick(preset.name)}
          disabled={disabled}
          title={preset.description}
        >
          {preset.label}
        </button>
      ))}
    </div>
  );
}
