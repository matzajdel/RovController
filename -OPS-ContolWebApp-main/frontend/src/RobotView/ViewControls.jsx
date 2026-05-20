/**
 * 3D view control overlay - camera angles and display options
 */
export function ViewControls({ 
  selectedView, 
  onViewChange, 
  showGrid, 
  onToggleGrid,
  showAxes,
  onToggleAxes 
}) {
  const views = [
    { id: 'orbit', label: '🔄 Orbit' },
    { id: 'top-down', label: '⬇️ Top' },
    { id: 'front', label: '👁️ Front' },
    { id: 'side', label: '↔️ Side' },
  ];

  return (
    <div className="view-controls-overlay">
      <div className="view-buttons">
        {views.map((view) => (
          <button
            key={view.id}
            className={`view-button ${selectedView === view.id ? 'active' : ''}`}
            onClick={() => onViewChange(view.id)}
          >
            {view.label}
          </button>
        ))}
      </div>

      <div className="view-toggles">
        <label className="toggle-option">
          <input
            type="checkbox"
            checked={showGrid}
            onChange={onToggleGrid}
          />
          <span>Show Grid</span>
        </label>
        
        <label className="toggle-option">
          <input
            type="checkbox"
            checked={showAxes}
            onChange={onToggleAxes}
          />
          <span>Show Axes</span>
        </label>
      </div>
    </div>
  );
}
