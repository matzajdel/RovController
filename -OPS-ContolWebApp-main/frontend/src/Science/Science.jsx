import React, { useState, useEffect, useRef, useCallback } from 'react'
import ScienceGraph from './ScienceGraph'
import ScienceDashboard from './ScienceDashboard'
import SequencesPanel from './SequencesPanel'
import { BACKEND_URL } from '../config'

// ----------------------------------------------------------------------
// Helper
// ----------------------------------------------------------------------
const generateId = () => Math.random().toString(36).substr(2, 9);

const normalizeArrayIndices = (indices) => {
  if (!Array.isArray(indices)) return [];
  const unique = Array.from(new Set(
    indices
      .map((idx) => parseInt(idx, 10))
      .filter((idx) => Number.isInteger(idx) && idx >= 0)
  ));
  return unique.sort((a, b) => a - b);
};

const getSliderTargetIndices = (slider) => {
  const normalized = normalizeArrayIndices(slider?.arrayIndices);
  if (normalized.length > 0) return normalized;
  if (Number.isInteger(slider?.arrayIndex) && slider.arrayIndex >= 0) return [slider.arrayIndex];
  return [];
};

const Science = () => {
  // Layout (graphs + sliders — buttons moved to StatusJetson via ScienceDashboard)
  const [layout, setLayout] = useState({ graphs: [], sliders: [], gridColumns: 4, maxWidth: 1200 });
  const [isEditMode, setIsEditMode] = useState(false);
  const [showGridSettings, setShowGridSettings] = useState(false);

  // Graph Modal State
  const [showGraphModal, setShowGraphModal] = useState(false);
  const [editingGraphId, setEditingGraphId] = useState(null);
  const [graphConfig, setGraphConfig] = useState({
    topic: '',
    title: '',
    frequencyHz: 2,
    maxPoints: 50,
    labels: [],
    height: 200
  });

  // Graph Data State
  const [graphData, setGraphData] = useState({});
  const graphPollingRef = useRef(null);

  // Drag-to-resize state
  const [resizingGraphId, setResizingGraphId] = useState(null);
  const resizeStartXRef = useRef(0);
  const resizeStartSpanRef = useRef(0);
  const gridContainerRef = useRef(null);

  // ROS topics for graph topic picker
  const [topics, setTopics] = useState([]);
  const [loading, setLoading] = useState(false);
  const [statusMessage, setStatusMessage] = useState({ type: '', text: '' });

  // Slider Modal State
  const [showSliderModal, setShowSliderModal] = useState(false);
  const [editingSliderId, setEditingSliderId] = useState(null);
  const [sliderConfig, setSliderConfig] = useState({
    topic: '', label: '', min: 0, max: 100, step: 1, defaultValue: 0,
    arrayIndex: -1, // -1 = publish raw value, >= 0 = publish to specific index in MultiArray
    arrayIndices: [], // preferred mode: publish the same value to multiple selected indices
    arrayLength: 6
  });
  // Live slider values (not persisted — reset on reload)
  const [sliderValues, setSliderValues] = useState({});

  useEffect(() => {
    loadLayout();
    fetchTopics();
  }, []);

  const loadLayout = async () => {
    try {
      const res = await fetch(`${BACKEND_URL}/ros/science_layout`);
      const data = await res.json();
      setLayout({
        graphs: data.graphs || [],
        sliders: data.sliders || [],
        gridColumns: data.gridColumns || 4,
        maxWidth: data.maxWidth || 1200
      });
    } catch (e) {
      console.error("Failed to load layout", e);
    }
  };

  const saveLayout = async (newLayout) => {
    showStatus('info', 'Saving layout...');
    try {
      const res = await fetch(`${BACKEND_URL}/ros/science_layout`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(newLayout)
      });
      if (!res.ok) throw new Error("Backend rejected save");
      setLayout(newLayout);
      showStatus('success', 'Layout saved successfully!');
    } catch (e) {
      console.error("Failed to save layout", e);
      showStatus('error', 'Failed to save layout: ' + e.message);
    }
  };

  const fetchTopics = async () => {
    setLoading(true);
    try {
      const response = await fetch(`${BACKEND_URL}/ros/topics`);
      const data = await response.json();
      setTopics(data.topics || []);
    } catch (error) {
      console.error('Error fetching topics:', error);
    } finally {
      setLoading(false);
    }
  };

  const showStatus = (type, text) => {
    setStatusMessage({ type, text });
    setTimeout(() => setStatusMessage({ type: '', text: '' }), 3000);
  };

  // ----------------------------------------------------------------------
  // Slider Management
  // ----------------------------------------------------------------------

  const openNewSliderModal = () => {
    setEditingSliderId(null);
    setSliderConfig({ topic: '', label: '', min: 0, max: 100, step: 1, defaultValue: 0, arrayIndex: -1, arrayIndices: [], arrayLength: 6 });
    setShowSliderModal(true);
  };

  const openSliderSettings = (slider) => {
    setEditingSliderId(slider.id);
    const arrayIndices = getSliderTargetIndices(slider);
    setSliderConfig({
      topic: slider.topic,
      label: slider.label || '',
      min: slider.min ?? 0,
      max: slider.max ?? 100,
      step: slider.step ?? 1,
      defaultValue: slider.defaultValue ?? 0,
      arrayIndex: arrayIndices.length > 0 ? arrayIndices[0] : -1,
      arrayIndices,
      arrayLength: Math.max(slider.arrayLength ?? 6, ...(arrayIndices.map((idx) => idx + 1)), 1)
    });
    setShowSliderModal(true);
  };

  const handleSliderSave = async () => {
    if (!sliderConfig.topic) {
      showStatus('error', 'Please select a topic');
      return;
    }

    const normalizedIndices = normalizeArrayIndices(sliderConfig.arrayIndices);
    const hasIndexedPublish = normalizedIndices.length > 0;
    const minArrayLengthFromIndices = hasIndexedPublish ? Math.max(...normalizedIndices) + 1 : 1;

    const newSlider = {
      id: editingSliderId || generateId(),
      topic: sliderConfig.topic,
      label: sliderConfig.label || sliderConfig.topic,
      min: sliderConfig.min,
      max: sliderConfig.max,
      step: sliderConfig.step,
      defaultValue: sliderConfig.defaultValue,
      // Keep legacy field for compatibility with older saved layouts.
      arrayIndex: hasIndexedPublish ? normalizedIndices[0] : -1,
      arrayIndices: normalizedIndices,
      arrayLength: Math.max(minArrayLengthFromIndices, parseInt(sliderConfig.arrayLength, 10) || 1),
      gridRow: 1,
      gridColSpan: 2
    };

    const newLayout = { ...layout };
    if (!newLayout.sliders) newLayout.sliders = [];

    if (editingSliderId) {
      const idx = newLayout.sliders.findIndex(s => s.id === editingSliderId);
      if (idx !== -1) {
        newSlider.gridRow = newLayout.sliders[idx].gridRow || 1;
        newSlider.gridColSpan = newLayout.sliders[idx].gridColSpan || 2;
        newLayout.sliders[idx] = newSlider;
      }
    } else {
      const allRows = [...(newLayout.graphs || []), ...(newLayout.sliders || [])].map(i => i.gridRow || 0);
      newSlider.gridRow = allRows.length > 0 ? Math.max(...allRows) + 1 : 1;
      newLayout.sliders.push(newSlider);
    }

    await saveLayout(newLayout);
    setShowSliderModal(false);
    showStatus('success', `Slider ${editingSliderId ? 'updated' : 'added'} successfully`);
  };

  const removeSlider = async (sliderId) => {
    if (!confirm('Remove this slider?')) return;
    const newLayout = { ...layout, sliders: layout.sliders.filter(s => s.id !== sliderId) };
    await saveLayout(newLayout);
  };

  const publishSliderValue = async (slider, value) => {
    try {
      const targetIndices = getSliderTargetIndices(slider);
      const sliderArrayLength = Math.max(
        parseInt(slider?.arrayLength, 10) || 0,
        ...(targetIndices.map((idx) => idx + 1)),
        1
      );

      if (targetIndices.length === 0) {
        await fetch(`${BACKEND_URL}/ros/publish`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ topic: slider.topic, value })
        });
        return;
      }

      // Backend currently accepts one arrayIndex per publish call,
      // so send the same value to each selected index.
      await Promise.all(targetIndices.map((arrayIndex) => fetch(`${BACKEND_URL}/ros/publish`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ topic: slider.topic, value, arrayIndex, arrayLength: sliderArrayLength })
      })));
    } catch (e) {
      console.warn('[Slider] publish error:', e);
    }
  };

  // ----------------------------------------------------------------------
  // Graph Data Polling
  // ----------------------------------------------------------------------

  const fetchGraphData = useCallback(async (topic) => {
    try {
      const res = await fetch(`${BACKEND_URL}/science/data?topic=${encodeURIComponent(topic)}`);
      if (res.ok) {
        const result = await res.json();
        setGraphData(prev => ({ ...prev, [topic]: result.data || [] }));
      }
    } catch (e) {
      console.error(`Failed to fetch graph data for ${topic}:`, e);
    }
  }, []);

  useEffect(() => {
    const graphs = layout.graphs || [];
    if (graphs.length === 0) {
      if (graphPollingRef.current) {
        clearInterval(graphPollingRef.current);
        graphPollingRef.current = null;
      }
      return;
    }

    const registerWatchers = async () => {
      for (const graph of graphs) {
        try {
          await fetch(`${BACKEND_URL}/science/watchers`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              topic: graph.topic,
              frequency_hz: graph.frequencyHz || 2,
              max_points: graph.maxPoints || 50
            })
          });
        } catch (e) {
          console.error(`Failed to register watcher for ${graph.topic}:`, e);
        }
      }
    };
    registerWatchers();
    graphs.forEach(g => fetchGraphData(g.topic));

    graphPollingRef.current = setInterval(() => {
      graphs.forEach(g => fetchGraphData(g.topic));
    }, 500);

    return () => {
      if (graphPollingRef.current) {
        clearInterval(graphPollingRef.current);
        graphPollingRef.current = null;
      }
    };
  }, [layout.graphs, fetchGraphData]);

  // ----------------------------------------------------------------------
  // Graph Management
  // ----------------------------------------------------------------------

  const openNewGraphModal = () => {
    setEditingGraphId(null);
    setGraphConfig({ topic: '', title: '', frequencyHz: 2, maxPoints: 50, labels: [], height: 200 });
    setShowGraphModal(true);
  };

  const openGraphSettings = (graph) => {
    setEditingGraphId(graph.id);
    setGraphConfig({
      topic: graph.topic,
      title: graph.title || '',
      frequencyHz: graph.frequencyHz || 2,
      maxPoints: graph.maxPoints || 50,
      labels: graph.labels || [],
      height: graph.height || 200
    });
    setShowGraphModal(true);
  };

  const handleGraphSave = async () => {
    if (!graphConfig.topic) {
      showStatus('error', 'Please select a topic');
      return;
    }

    const newGraph = {
      id: editingGraphId || generateId(),
      topic: graphConfig.topic,
      title: graphConfig.title || graphConfig.topic,
      frequencyHz: graphConfig.frequencyHz,
      maxPoints: graphConfig.maxPoints,
      labels: graphConfig.labels,
      height: graphConfig.height,
      gridRow: 1,
      gridColSpan: 2
    };

    const newLayout = { ...layout };
    if (!newLayout.graphs) newLayout.graphs = [];

    if (editingGraphId) {
      const idx = newLayout.graphs.findIndex(g => g.id === editingGraphId);
      if (idx !== -1) {
        newGraph.gridRow = newLayout.graphs[idx].gridRow || 1;
        newGraph.gridColSpan = newLayout.graphs[idx].gridColSpan || 2;
        newLayout.graphs[idx] = newGraph;
      }
    } else {
      const existingRows = newLayout.graphs.map(g => g.gridRow || 0);
      newGraph.gridRow = existingRows.length > 0 ? Math.max(...existingRows) + 1 : 1;
      newLayout.graphs.push(newGraph);
    }

    await saveLayout(newLayout);
    setShowGraphModal(false);
    showStatus('success', `Graph ${editingGraphId ? 'updated' : 'added'} successfully`);
  };

  const removeGraph = async (graphId) => {
    if (!confirm('Remove this graph?')) return;

    const graph = layout.graphs.find(g => g.id === graphId);
    if (graph) {
      try {
        await fetch(`${BACKEND_URL}/science/watchers?topic=${encodeURIComponent(graph.topic)}`, {
          method: 'DELETE'
        });
      } catch (e) {
        console.error('Failed to unregister watcher:', e);
      }
    }

    const newLayout = { ...layout, graphs: layout.graphs.filter(g => g.id !== graphId) };
    await saveLayout(newLayout);
  };

  // Graph resize handlers
  const handleGraphResizeStart = (e, graphId, currentSpan) => {
    e.preventDefault();
    e.stopPropagation();
    setResizingGraphId(graphId);
    resizeStartXRef.current = e.clientX || e.touches?.[0]?.clientX || 0;
    resizeStartSpanRef.current = currentSpan;

    document.addEventListener('mousemove', handleGraphResizeMove);
    document.addEventListener('mouseup', handleGraphResizeEnd);
    document.addEventListener('touchmove', handleGraphResizeMove);
    document.addEventListener('touchend', handleGraphResizeEnd);
  };

  const handleGraphResizeMove = (e) => {
    if (!resizingGraphId || !gridContainerRef.current) return;

    const clientX = e.clientX || e.touches?.[0]?.clientX || 0;
    const deltaX = clientX - resizeStartXRef.current;

    const containerWidth = gridContainerRef.current.offsetWidth;
    const gap = 20;
    const columnWidth = (containerWidth - (gap * (layout.gridColumns - 1))) / layout.gridColumns;

    const spanDelta = Math.round(deltaX / (columnWidth + gap));
    let newSpan = resizeStartSpanRef.current + spanDelta;
    newSpan = Math.max(1, Math.min(layout.gridColumns, newSpan));

    const newLayout = { ...layout };
    const graph = newLayout.graphs.find(g => g.id === resizingGraphId);
    if (graph && graph.gridColSpan !== newSpan) {
      graph.gridColSpan = newSpan;
      setLayout(newLayout);
    }
  };

  const handleGraphResizeEnd = () => {
    if (resizingGraphId) {
      saveLayout(layout);
    }
    setResizingGraphId(null);
    document.removeEventListener('mousemove', handleGraphResizeMove);
    document.removeEventListener('mouseup', handleGraphResizeEnd);
    document.removeEventListener('touchmove', handleGraphResizeMove);
    document.removeEventListener('touchend', handleGraphResizeEnd);
  };

  useEffect(() => {
    return () => {
      document.removeEventListener('mousemove', handleGraphResizeMove);
      document.removeEventListener('mouseup', handleGraphResizeEnd);
      document.removeEventListener('touchmove', handleGraphResizeMove);
      document.removeEventListener('touchend', handleGraphResizeEnd);
    };
  }, []);

  // ----------------------------------------------------------------------
  // Render
  // ----------------------------------------------------------------------

  return (
    <div style={{ padding: '20px', color: 'white', maxWidth: `${layout.maxWidth}px`, margin: '0 auto' }}>
      <ScienceDashboard />

      {/* Header */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '20px', borderBottom: '1px solid #444', paddingBottom: '10px' }}>
        <h2>Science Graphs</h2>
        <div style={{ display: 'flex', gap: '10px' }}>
          {isEditMode && (
            <button
              onClick={() => setShowGridSettings(true)}
              style={{ padding: '8px 16px', backgroundColor: '#9C27B0', color: 'white', border: 'none', borderRadius: '4px', cursor: 'pointer' }}
            >
              ⚙ Grid Settings
            </button>
          )}
          <button
            onClick={() => setIsEditMode(!isEditMode)}
            style={{ padding: '8px 16px', backgroundColor: isEditMode ? '#4CAF50' : '#2196F3', color: 'white', border: 'none', borderRadius: '4px', cursor: 'pointer' }}
          >
            {isEditMode ? 'Done Editing' : 'Edit Dashboard'}
          </button>
        </div>
      </div>

      {/* Grid Settings Modal */}
      {showGridSettings && (
        <div style={{ position: 'fixed', top: 0, left: 0, right: 0, bottom: 0, backgroundColor: 'rgba(0,0,0,0.8)', zIndex: 1100, display: 'flex', justifyContent: 'center', alignItems: 'center' }}>
          <div style={{ backgroundColor: '#2a2e33', padding: '25px', borderRadius: '10px', width: '400px' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '20px' }}>
              <h3 style={{ margin: 0 }}>⚙ Grid Settings</h3>
              <button onClick={() => setShowGridSettings(false)} style={{ background: 'none', border: 'none', color: '#aaa', cursor: 'pointer', fontSize: '1.2em' }}>✕</button>
            </div>

            <div style={{ marginBottom: '20px' }}>
              <label style={{ display: 'block', marginBottom: '8px', color: '#ccc' }}>Number of Columns:</label>
              <input
                type="number"
                min="1"
                max="12"
                value={layout.gridColumns}
                onChange={(e) => {
                  const val = Math.min(12, Math.max(1, parseInt(e.target.value) || 4));
                  const newLayout = { ...layout, gridColumns: val };
                  saveLayout(newLayout);
                }}
                style={{ width: '100%', padding: '10px', background: '#333', border: '1px solid #555', color: 'white', borderRadius: '4px' }}
              />
            </div>

            <div style={{ marginBottom: '20px' }}>
              <label style={{ display: 'block', marginBottom: '8px', color: '#ccc' }}>Max Width (px):</label>
              <input
                type="number"
                min="400"
                max="2400"
                step="100"
                value={layout.maxWidth}
                onChange={(e) => {
                  const val = Math.min(2400, Math.max(400, parseInt(e.target.value) || 1200));
                  const newLayout = { ...layout, maxWidth: val };
                  saveLayout(newLayout);
                }}
                style={{ width: '100%', padding: '10px', background: '#333', border: '1px solid #555', color: 'white', borderRadius: '4px' }}
              />
            </div>

            <button
              onClick={() => setShowGridSettings(false)}
              style={{ width: '100%', padding: '10px', backgroundColor: '#4CAF50', color: 'white', border: 'none', borderRadius: '5px', cursor: 'pointer', fontWeight: 'bold' }}
            >
              Done
            </button>
          </div>
        </div>
      )}

      {/* Graph Configuration Modal */}
      {showGraphModal && (
        <div style={{ position: 'fixed', top: 0, left: 0, right: 0, bottom: 0, backgroundColor: 'rgba(0,0,0,0.8)', zIndex: 1100, display: 'flex', justifyContent: 'center', alignItems: 'center' }}>
          <div style={{ backgroundColor: '#2a2e33', padding: '25px', borderRadius: '10px', width: '500px', maxHeight: '90vh', overflowY: 'auto' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '20px' }}>
              <h3 style={{ margin: 0 }}>{editingGraphId ? 'Edit Graph' : 'Add New Graph'}</h3>
              <button onClick={() => setShowGraphModal(false)} style={{ background: 'none', border: 'none', color: '#aaa', cursor: 'pointer', fontSize: '1.2em' }}>✕</button>
            </div>

            <div style={{ marginBottom: '15px' }}>
              <label style={{ display: 'block', marginBottom: '5px', color: '#ccc' }}>ROS Topic:</label>
              <div style={{ display: 'flex', gap: '10px' }}>
                <select
                  value={graphConfig.topic}
                  onChange={(e) => setGraphConfig({ ...graphConfig, topic: e.target.value, title: graphConfig.title || e.target.value })}
                  style={{ flex: 1, padding: '10px', background: '#333', color: 'white', border: '1px solid #555', borderRadius: '4px' }}
                >
                  <option value="">-- Select Topic --</option>
                  {topics.map(t => <option key={t} value={t}>{t}</option>)}
                </select>
                <button
                  onClick={fetchTopics}
                  disabled={loading}
                  style={{ padding: '10px', backgroundColor: '#555', border: 'none', borderRadius: '4px', color: 'white', cursor: 'pointer' }}
                >
                  ↻
                </button>
              </div>
            </div>

            <div style={{ marginBottom: '15px' }}>
              <label style={{ display: 'block', marginBottom: '5px', color: '#ccc' }}>Graph Title:</label>
              <input
                type="text"
                value={graphConfig.title}
                onChange={(e) => setGraphConfig({ ...graphConfig, title: e.target.value })}
                placeholder="e.g., Temperature Sensor"
                style={{ width: '100%', padding: '10px', background: '#333', border: '1px solid #555', color: 'white', borderRadius: '4px', boxSizing: 'border-box' }}
              />
            </div>

            <div style={{ marginBottom: '15px' }}>
              <label style={{ display: 'block', marginBottom: '5px', color: '#ccc' }}>Update Frequency / Period:</label>
              <div style={{ display: 'flex', gap: '10px', alignItems: 'center' }}>
                <div style={{ flex: 1, display: 'flex', alignItems: 'center', background: '#333', border: '1px solid #555', borderRadius: '4px' }}>
                  <input
                    type="number"
                    min="0.01"
                    step="0.1"
                    value={graphConfig.frequencyHz}
                    onChange={(e) => {
                      const hz = parseFloat(e.target.value);
                      setGraphConfig({ ...graphConfig, frequencyHz: isNaN(hz) || hz <= 0 ? '' : hz });
                    }}
                    style={{ width: '100%', padding: '10px', background: 'transparent', border: 'none', color: 'white', boxSizing: 'border-box', outline: 'none' }}
                  />
                  <span style={{ paddingRight: '10px', color: '#aaa', fontSize: '0.9em' }}>Hz</span>
                </div>
                <span style={{ color: '#888' }}>≈</span>
                <div style={{ flex: 1, display: 'flex', alignItems: 'center', background: '#333', border: '1px solid #555', borderRadius: '4px' }}>
                  <input
                    type="number"
                    min="1"
                    step="10"
                    value={graphConfig.frequencyHz ? Math.round(1000 / graphConfig.frequencyHz) : ''}
                    onChange={(e) => {
                      const ms = parseFloat(e.target.value);
                      setGraphConfig({ ...graphConfig, frequencyHz: isNaN(ms) || ms <= 0 ? '' : Number((1000 / ms).toFixed(3)) });
                    }}
                    style={{ width: '100%', padding: '10px', background: 'transparent', border: 'none', color: 'white', boxSizing: 'border-box', outline: 'none' }}
                  />
                  <span style={{ paddingRight: '10px', color: '#aaa', fontSize: '0.9em' }}>ms</span>
                </div>
              </div>
            </div>

            <div style={{ marginBottom: '15px' }}>
              <label style={{ display: 'block', marginBottom: '5px', color: '#ccc' }}>Max Data Points:</label>
              <input
                type="number"
                min="1"
                max="500"
                value={graphConfig.maxPoints}
                onChange={(e) => setGraphConfig({ ...graphConfig, maxPoints: parseInt(e.target.value) || 50 })}
                style={{ width: '100%', padding: '10px', background: '#333', border: '1px solid #555', color: 'white', borderRadius: '4px', boxSizing: 'border-box' }}
              />
              <p style={{ fontSize: '0.8em', color: '#888', margin: '5px 0 0 0' }}>
                <strong>1 point</strong> = single value display | <strong>2+ points</strong> = line graph
              </p>
            </div>

            <div style={{ marginBottom: '15px' }}>
              <label style={{ display: 'block', marginBottom: '5px', color: '#ccc' }}>Graph Height (px):</label>
              <input
                type="number"
                min="100"
                max="500"
                step="50"
                value={graphConfig.height}
                onChange={(e) => setGraphConfig({ ...graphConfig, height: parseInt(e.target.value) || 200 })}
                style={{ width: '100%', padding: '10px', background: '#333', border: '1px solid #555', color: 'white', borderRadius: '4px', boxSizing: 'border-box' }}
              />
            </div>

            <div style={{ marginBottom: '20px' }}>
              <label style={{ display: 'block', marginBottom: '5px', color: '#ccc' }}>Series Labels (for array topics):</label>
              <input
                type="text"
                value={graphConfig.labels.join(', ')}
                onChange={(e) => {
                  // Keep positional labels aligned with array indices (do not compact empties).
                  const newLabels = e.target.value.split(',').map(l => l.trim());
                  setGraphConfig({ ...graphConfig, labels: newLabels });
                }}
                placeholder="e.g., X, Y, Z (comma-separated)"
                style={{ width: '100%', padding: '10px', background: '#333', border: '1px solid #555', color: 'white', borderRadius: '4px', boxSizing: 'border-box' }}
              />
            </div>

            <div style={{ display: 'flex', gap: '10px' }}>
              <button
                onClick={handleGraphSave}
                style={{ flex: 1, padding: '12px', backgroundColor: '#4CAF50', border: 'none', borderRadius: '5px', color: 'white', cursor: 'pointer', fontWeight: 'bold' }}
              >
                {editingGraphId ? 'Update Graph' : 'Add Graph'}
              </button>
              <button
                onClick={() => setShowGraphModal(false)}
                style={{ padding: '12px 20px', backgroundColor: '#555', border: 'none', borderRadius: '5px', color: 'white', cursor: 'pointer' }}
              >
                Cancel
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Editor Controls */}
      {isEditMode && (
        <div style={{ marginBottom: '20px', padding: '15px', backgroundColor: '#2a2e33', borderRadius: '8px', display: 'flex', gap: '10px', alignItems: 'center', flexWrap: 'wrap' }}>
          <button
            onClick={openNewGraphModal}
            style={{ padding: '8px 16px', backgroundColor: '#4CAF50', border: 'none', borderRadius: '4px', color: 'white', cursor: 'pointer' }}
          >
            📊 Add Graph
          </button>
          <button
            onClick={openNewSliderModal}
            style={{ padding: '8px 16px', backgroundColor: '#FF9800', border: 'none', borderRadius: '4px', color: 'white', cursor: 'pointer' }}
          >
            🎚️ Add Slider
          </button>
          <span style={{ color: '#888', fontSize: '0.9em' }}>Grid: {layout.gridColumns} columns × auto rows | Max Width: {layout.maxWidth}px</span>
        </div>
      )}

      {/* Graphs Grid */}
      <div
        ref={gridContainerRef}
        style={{
          display: 'grid',
          gridTemplateColumns: `repeat(${layout.gridColumns}, 1fr)`,
          gap: '20px',
          alignItems: 'start'
        }}
      >
        {(layout.graphs || [])
          .sort((a, b) => ((a.gridRow || 0) - (b.gridRow || 0)))
          .map(graph => (
            <div
              key={graph.id}
              style={{
                gridColumn: `span ${Math.min(graph.gridColSpan || 2, layout.gridColumns)}`,
                position: 'relative',
                transition: resizingGraphId === graph.id ? 'none' : 'all 0.2s ease',
                outline: resizingGraphId === graph.id ? '2px solid #4CAF50' : 'none'
              }}
            >
              {isEditMode && (
                <div style={{
                  position: 'absolute',
                  top: '-25px',
                  left: '0',
                  display: 'flex',
                  gap: '8px',
                  alignItems: 'center',
                  fontSize: '0.8em',
                  color: '#888'
                }}>
                  <label>Row:</label>
                  <input
                    type="number"
                    min="1"
                    value={graph.gridRow || 1}
                    onChange={(e) => {
                      const newRow = parseInt(e.target.value) || 1;
                      const newLayout = { ...layout };
                      const g = newLayout.graphs.find(gr => gr.id === graph.id);
                      if (g) {
                        g.gridRow = newRow;
                        saveLayout(newLayout);
                      }
                    }}
                    style={{
                      width: '50px',
                      padding: '3px 6px',
                      background: '#333',
                      border: '1px solid #555',
                      color: 'white',
                      borderRadius: '3px'
                    }}
                  />
                  <span style={{ color: '#4CAF50' }}>
                    ↔ Span: {graph.gridColSpan || 2}/{layout.gridColumns}
                  </span>
                </div>
              )}

              <ScienceGraph
                data={graphData[graph.topic] || []}
                title={graph.title || graph.topic}
                labels={graph.labels || []}
                maxPoints={graph.maxPoints || 50}
                height={graph.height || 200}
                isEditMode={isEditMode}
                onRemove={() => removeGraph(graph.id)}
                onSettings={() => openGraphSettings(graph)}
              />

              {isEditMode && (
                <div
                  onMouseDown={(e) => handleGraphResizeStart(e, graph.id, graph.gridColSpan || 2)}
                  onTouchStart={(e) => handleGraphResizeStart(e, graph.id, graph.gridColSpan || 2)}
                  style={{
                    position: 'absolute',
                    top: '0',
                    right: '-6px',
                    width: '12px',
                    height: '100%',
                    cursor: 'ew-resize',
                    backgroundColor: resizingGraphId === graph.id ? '#4CAF50' : 'transparent',
                    borderRadius: '0 8px 8px 0',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    transition: 'background-color 0.2s'
                  }}
                  onMouseEnter={(e) => { if (!resizingGraphId) e.currentTarget.style.backgroundColor = 'rgba(76, 175, 80, 0.5)'; }}
                  onMouseLeave={(e) => { if (!resizingGraphId) e.currentTarget.style.backgroundColor = 'transparent'; }}
                >
                  <div style={{
                    width: '3px',
                    height: '40px',
                    backgroundColor: '#4CAF50',
                    borderRadius: '2px'
                  }} />
                </div>
              )}
            </div>
          ))}
      </div>

      {/* Sliders */}
      {(layout.sliders || []).length > 0 && (
        <div style={{ marginTop: '20px' }}>
          <h3 style={{ marginBottom: '15px', borderBottom: '1px solid #444', paddingBottom: '8px' }}>🎚️ Sliders</h3>
          <div
            style={{
              display: 'grid',
              gridTemplateColumns: `repeat(${layout.gridColumns}, 1fr)`,
              gap: '20px',
              alignItems: 'start'
            }}
          >
            {(layout.sliders || [])
              .sort((a, b) => ((a.gridRow || 0) - (b.gridRow || 0)))
              .map(slider => {
                const val = sliderValues[slider.id] ?? slider.defaultValue ?? 0;
                const sliderIndices = getSliderTargetIndices(slider);
                return (
                  <div
                    key={slider.id}
                    style={{
                      gridColumn: `span ${Math.min(slider.gridColSpan || 2, layout.gridColumns)}`,
                      backgroundColor: '#1e2124',
                      borderRadius: '8px',
                      padding: '15px',
                      borderLeft: '4px solid #FF9800'
                    }}
                  >
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '10px' }}>
                      <div>
                        <h4 style={{ margin: 0, fontSize: '1em' }}>{slider.label || slider.topic}</h4>
                        <span style={{ fontSize: '0.75em', color: '#888' }}>{slider.topic}{sliderIndices.length > 0 ? ` [${sliderIndices.join(', ')}]` : ''}</span>
                      </div>
                      <div style={{ display: 'flex', gap: '6px', alignItems: 'center' }}>
                        <span style={{
                          fontSize: '1.2em',
                          fontWeight: 'bold',
                          color: '#FF9800',
                          fontFamily: 'monospace',
                          minWidth: '60px',
                          textAlign: 'right'
                        }}>
                          {val}
                        </span>
                        {isEditMode && (
                          <>
                            <button
                              onClick={() => openSliderSettings(slider)}
                              style={{ padding: '4px 8px', backgroundColor: '#555', border: 'none', borderRadius: '3px', color: 'white', cursor: 'pointer', fontSize: '0.8em' }}
                            >
                              ⚙
                            </button>
                            <button
                              onClick={() => removeSlider(slider.id)}
                              style={{ padding: '4px 8px', backgroundColor: '#f44336', border: 'none', borderRadius: '3px', color: 'white', cursor: 'pointer', fontSize: '0.8em' }}
                            >
                              ✕
                            </button>
                          </>
                        )}
                      </div>
                    </div>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                      <span style={{ fontSize: '0.8em', color: '#888', minWidth: '40px', textAlign: 'right' }}>{slider.min}</span>
                      <button
                        onClick={() => {
                          const step = parseFloat(slider.step) || 1;
                          const newVal = Math.max(parseFloat(slider.min), parseFloat((val - step).toFixed(5)));
                          setSliderValues(prev => ({ ...prev, [slider.id]: newVal }));
                          publishSliderValue(slider, newVal);
                        }}
                        style={{ padding: '0px 8px', backgroundColor: '#444', border: '1px solid #555', borderRadius: '4px', color: 'white', cursor: 'pointer', fontSize: '1.2em', height: '24px', display: 'flex', alignItems: 'center', justifyContent: 'center' }}
                      >
                        ◄
                      </button>
                      <input
                        type="range"
                        min={slider.min}
                        max={slider.max}
                        step={slider.step}
                        value={val}
                        onChange={(e) => {
                          const newVal = parseFloat(e.target.value);
                          setSliderValues(prev => ({ ...prev, [slider.id]: newVal }));
                          publishSliderValue(slider, newVal);
                        }}
                        style={{
                          flex: 1,
                          height: '8px',
                          accentColor: '#FF9800',
                          cursor: 'pointer'
                        }}
                      />
                      <button
                        onClick={() => {
                          const step = parseFloat(slider.step) || 1;
                          const newVal = Math.min(parseFloat(slider.max), parseFloat((val + step).toFixed(5)));
                          setSliderValues(prev => ({ ...prev, [slider.id]: newVal }));
                          publishSliderValue(slider, newVal);
                        }}
                        style={{ padding: '0px 8px', backgroundColor: '#444', border: '1px solid #555', borderRadius: '4px', color: 'white', cursor: 'pointer', fontSize: '1.2em', height: '24px', display: 'flex', alignItems: 'center', justifyContent: 'center' }}
                      >
                        ►
                      </button>
                      <span style={{ fontSize: '0.8em', color: '#888', minWidth: '40px' }}>{slider.max}</span>
                    </div>
                    {isEditMode && (
                      <div style={{ marginTop: '8px', display: 'flex', gap: '8px', fontSize: '0.75em', color: '#666' }}>
                        <span>Step: {slider.step}</span>
                        <span>Default: {slider.defaultValue}</span>
                      </div>
                    )}
                  </div>
                );
              })}
          </div>
        </div>
      )}

      {/* Slider Configuration Modal */}
      {showSliderModal && (
        <div style={{ position: 'fixed', top: 0, left: 0, right: 0, bottom: 0, backgroundColor: 'rgba(0,0,0,0.8)', zIndex: 1100, display: 'flex', justifyContent: 'center', alignItems: 'center' }}>
          <div style={{ backgroundColor: '#2a2e33', padding: '25px', borderRadius: '10px', width: '500px', maxHeight: '90vh', overflowY: 'auto' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '20px' }}>
              <h3 style={{ margin: 0 }}>{editingSliderId ? 'Edit Slider' : 'Add New Slider'}</h3>
              <button onClick={() => setShowSliderModal(false)} style={{ background: 'none', border: 'none', color: '#aaa', cursor: 'pointer', fontSize: '1.2em' }}>✕</button>
            </div>

            {/* Topic */}
            <div style={{ marginBottom: '15px' }}>
              <label style={{ display: 'block', marginBottom: '5px', color: '#ccc' }}>ROS Topic:</label>
              <div style={{ display: 'flex', gap: '10px' }}>
                <select
                  value={sliderConfig.topic}
                  onChange={(e) => setSliderConfig({ ...sliderConfig, topic: e.target.value, label: sliderConfig.label || e.target.value })}
                  style={{ flex: 1, padding: '10px', background: '#333', color: 'white', border: '1px solid #555', borderRadius: '4px' }}
                >
                  <option value="">-- Select Topic --</option>
                  {topics.map(t => <option key={t} value={t}>{t}</option>)}
                </select>
                <button
                  onClick={fetchTopics}
                  disabled={loading}
                  style={{ padding: '10px', backgroundColor: '#555', border: 'none', borderRadius: '4px', color: 'white', cursor: 'pointer' }}
                >
                  ↻
                </button>
              </div>
            </div>

            {/* Label */}
            <div style={{ marginBottom: '15px' }}>
              <label style={{ display: 'block', marginBottom: '5px', color: '#ccc' }}>Label:</label>
              <input
                type="text"
                value={sliderConfig.label}
                onChange={(e) => setSliderConfig({ ...sliderConfig, label: e.target.value })}
                placeholder="e.g., Motor Speed"
                style={{ width: '100%', padding: '10px', background: '#333', border: '1px solid #555', color: 'white', borderRadius: '4px', boxSizing: 'border-box' }}
              />
            </div>

            {/* Min / Max / Step / Default in a grid */}
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '15px', marginBottom: '15px' }}>
              <div>
                <label style={{ display: 'block', marginBottom: '5px', color: '#ccc' }}>Min:</label>
                <input
                  type="number"
                  value={sliderConfig.min}
                  onChange={(e) => setSliderConfig({ ...sliderConfig, min: parseFloat(e.target.value) || 0 })}
                  style={{ width: '100%', padding: '10px', background: '#333', border: '1px solid #555', color: 'white', borderRadius: '4px', boxSizing: 'border-box' }}
                />
              </div>
              <div>
                <label style={{ display: 'block', marginBottom: '5px', color: '#ccc' }}>Max:</label>
                <input
                  type="number"
                  value={sliderConfig.max}
                  onChange={(e) => setSliderConfig({ ...sliderConfig, max: parseFloat(e.target.value) || 100 })}
                  style={{ width: '100%', padding: '10px', background: '#333', border: '1px solid #555', color: 'white', borderRadius: '4px', boxSizing: 'border-box' }}
                />
              </div>
              <div>
                <label style={{ display: 'block', marginBottom: '5px', color: '#ccc' }}>Step:</label>
                <input
                  type="number"
                  value={sliderConfig.step}
                  onChange={(e) => setSliderConfig({ ...sliderConfig, step: parseFloat(e.target.value) || 1 })}
                  style={{ width: '100%', padding: '10px', background: '#333', border: '1px solid #555', color: 'white', borderRadius: '4px', boxSizing: 'border-box' }}
                />
              </div>
              <div>
                <label style={{ display: 'block', marginBottom: '5px', color: '#ccc' }}>Default Value:</label>
                <input
                  type="number"
                  value={sliderConfig.defaultValue}
                  onChange={(e) => setSliderConfig({ ...sliderConfig, defaultValue: parseFloat(e.target.value) || 0 })}
                  style={{ width: '100%', padding: '10px', background: '#333', border: '1px solid #555', color: 'white', borderRadius: '4px', boxSizing: 'border-box' }}
                />
              </div>
            </div>

            {/* Array Indexes */}
            <div style={{ marginBottom: '20px' }}>
              <label style={{ display: 'block', marginBottom: '8px', color: '#ccc' }}>Array Indexes (for MultiArray topics):</label>
              <div style={{
                display: 'grid',
                gridTemplateColumns: 'repeat(auto-fill, minmax(64px, 1fr))',
                gap: '8px',
                padding: '10px',
                background: '#333',
                border: '1px solid #555',
                borderRadius: '4px'
              }}>
                {Array.from({ length: Math.max(1, sliderConfig.arrayLength) }, (_, idx) => {
                  const checked = sliderConfig.arrayIndices.includes(idx);
                  return (
                    <label key={idx} style={{ display: 'flex', alignItems: 'center', gap: '6px', color: '#ddd', fontSize: '0.9em', cursor: 'pointer' }}>
                      <input
                        type="checkbox"
                        checked={checked}
                        onChange={(e) => {
                          const next = e.target.checked
                            ? [...sliderConfig.arrayIndices, idx]
                            : sliderConfig.arrayIndices.filter((selected) => selected !== idx);
                          const normalized = normalizeArrayIndices(next);
                          setSliderConfig({
                            ...sliderConfig,
                            arrayIndices: normalized,
                            arrayIndex: normalized.length > 0 ? normalized[0] : -1
                          });
                        }}
                      />
                      <span>{idx}</span>
                    </label>
                  );
                })}
              </div>
              <p style={{ fontSize: '0.8em', color: '#888', margin: '5px 0 0 0' }}>
                Leave all unchecked to publish raw value. Select one or more indexes to send the same value to each selected index.
              </p>
            </div>

            {/* Array Length */}
            <div style={{ marginBottom: '20px' }}>
              <label style={{ display: 'block', marginBottom: '5px', color: '#ccc' }}>Array Length (for MultiArray topics):</label>
              <input
                type="number"
                min="1"
                value={sliderConfig.arrayLength}
                onChange={(e) => {
                  const nextLength = Math.max(1, parseInt(e.target.value, 10) || 1);
                  const filtered = normalizeArrayIndices(sliderConfig.arrayIndices).filter((idx) => idx < nextLength);
                  setSliderConfig({
                    ...sliderConfig,
                    arrayLength: nextLength,
                    arrayIndices: filtered,
                    arrayIndex: filtered.length > 0 ? filtered[0] : -1
                  });
                }}
                style={{ width: '100%', padding: '10px', background: '#333', border: '1px solid #555', color: 'white', borderRadius: '4px', boxSizing: 'border-box' }}
              />
              <p style={{ fontSize: '0.8em', color: '#888', margin: '5px 0 0 0' }}>
                Used only for indexed publish mode. If you lower the length, out-of-range selected indexes are removed.
              </p>
            </div>

            {/* Actions */}
            <div style={{ display: 'flex', gap: '10px' }}>
              <button
                onClick={handleSliderSave}
                style={{ flex: 1, padding: '12px', backgroundColor: '#FF9800', border: 'none', borderRadius: '5px', color: 'white', cursor: 'pointer', fontWeight: 'bold' }}
              >
                {editingSliderId ? 'Update Slider' : 'Add Slider'}
              </button>
              <button
                onClick={() => setShowSliderModal(false)}
                style={{ padding: '12px 20px', backgroundColor: '#555', border: 'none', borderRadius: '5px', color: 'white', cursor: 'pointer' }}
              >
                Cancel
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Empty state */}
      {(!layout.graphs || layout.graphs.length === 0) && (!layout.sliders || layout.sliders.length === 0) && !isEditMode && (
        <div style={{ textAlign: 'center', padding: '40px', color: '#888' }}>
          <p>No graphs or sliders configured yet.</p>
          <div style={{ display: 'flex', gap: '10px', justifyContent: 'center' }}>
            <button
              onClick={() => { setIsEditMode(true); openNewGraphModal(); }}
              style={{ padding: '10px 20px', backgroundColor: '#4CAF50', border: 'none', borderRadius: '5px', color: 'white', cursor: 'pointer' }}
            >
              📊 Add Graph
            </button>
            <button
              onClick={() => { setIsEditMode(true); openNewSliderModal(); }}
              style={{ padding: '10px 20px', backgroundColor: '#FF9800', border: 'none', borderRadius: '5px', color: 'white', cursor: 'pointer' }}
            >
              🎚️ Add Slider
            </button>
          </div>
        </div>
      )}

      {/* Sequences automation panel */}
      <SequencesPanel />

      {/* Status Toast */}
      {statusMessage.text && (
        <div style={{ padding: '15px', position: 'fixed', top: '20px', right: '20px', backgroundColor: statusMessage.type === 'success' ? '#4CAF50' : statusMessage.type === 'info' ? '#2196F3' : '#f44336', color: 'white', borderRadius: '5px', zIndex: 2000 }}>
          {statusMessage.text}
        </div>
      )}
    </div>
  );
};

export default Science;