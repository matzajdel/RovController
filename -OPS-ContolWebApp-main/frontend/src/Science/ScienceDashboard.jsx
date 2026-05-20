/**
 * ScienceDashboard — Button Dashboard for ROS Topic Actions
 * ==========================================================
 * 
 * Extracted from Science.jsx — a self-contained dashboard with
 * configurable action button groups that publish to ROS topics.
 *
 * Features:
 * - Dynamic button groups and subgroups (radio-style)
 * - Edit mode: add/remove groups, buttons, subgroups, drag-resize
 * - Config modal for button configuration
 * - Global defaults modal
 * - Layout persistence via backend API
 * - Active state persistence via localStorage
 */
import React, { useState, useEffect, useRef, useCallback } from 'react'
import { BACKEND_URL } from '../config'
import { useSatel } from '../context/SatelContext'

// ----------------------------------------------------------------------
// Helpers
// ----------------------------------------------------------------------

const generateId = () => Math.random().toString(36).substr(2, 9);

const ScienceDashboard = ({ instanceName = 'default' }) => {
    const { satelEnabled, satel } = useSatel();

    // Global State
    const [layout, setLayout] = useState({ groups: [], gridColumns: 4, maxWidth: 1200 });
    const [isEditMode, setIsEditMode] = useState(false);
    const [showGridSettings, setShowGridSettings] = useState(false);

    // Modal State
    const [editingGroupId, setEditingGroupId] = useState(null);
    const [editingButtonId, setEditingButtonId] = useState(null);
    const [showConfigModal, setShowConfigModal] = useState(false);
    const [showDefaultsModal, setShowDefaultsModal] = useState(false);
    const [selectedSubgroupId, setSelectedSubgroupId] = useState('');

    // Drag-to-resize state
    const [resizingGroupId, setResizingGroupId] = useState(null);
    const resizeStartXRef = useRef(0);
    const resizeStartSpanRef = useRef(0);
    const gridContainerRef = useRef(null);

    // ROS State
    const [topics, setTopics] = useState([]);
    const [selectedTopic, setSelectedTopic] = useState('');
    const [topicType, setTopicType] = useState('');
    const [message, setMessage] = useState('');
    const [arrayValues, setArrayValues] = useState([]);
    const [arrayLabels, setArrayLabels] = useState([]);
    const [twistValues, setTwistValues] = useState({
        linear_x: 0, linear_y: 0, linear_z: 0,
        angular_x: 0, angular_y: 0, angular_z: 0
    });
    const [activeIndices, setActiveIndices] = useState({});
    const [isContinuous, setIsContinuous] = useState(false);
    const [publishFrequencyHz, setPublishFrequencyHz] = useState(1);

    // UI state
    const [loading, setLoading] = useState(false);
    const [statusMessage, setStatusMessage] = useState({ type: '', text: '' });
    const [savedCommands, setSavedCommands] = useState({});

    // Macro state
    const [isMacro, setIsMacro] = useState(false);
    const [macroSteps, setMacroSteps] = useState([]);

    useEffect(() => {
        loadLayout();
        loadSavedCommands();
        fetchTopics();
    }, []);

    const loadLayout = async () => {
        try {
            const res = await fetch(`${BACKEND_URL}/ros/science_layout?instance=${instanceName}`);
            const data = await res.json();
            setLayout({
                groups: data.groups || [],
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
            const res = await fetch(`${BACKEND_URL}/ros/science_layout?instance=${instanceName}`, {
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

    const loadSavedCommands = async () => {
        try {
            const response = await fetch(`${BACKEND_URL}/ros/saved_commands`);
            if (response.ok) {
                const data = await response.json();
                setSavedCommands(data.commands || {});
            }
        } catch (e) { console.error(e); }
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

    // ----------------------------------------------------------------------
    // Button Actuation Logic
    // ----------------------------------------------------------------------

    const topicValuesRef = useRef((() => {
        try {
            const saved = localStorage.getItem(`science_${instanceName}_topicValues`);
            return saved ? JSON.parse(saved) : {};
        } catch { return {}; }
    })());

    useEffect(() => {
        if (Object.keys(savedCommands).length > 0) {
            Object.keys(savedCommands).forEach(topic => {
                const def = savedCommands[topic].find(c => c.isDefault);
                if (def && !topicValuesRef.current[topic]) {
                    topicValuesRef.current[topic] = JSON.parse(JSON.stringify(def.value));
                }
            });
        }
    }, [savedCommands]);

    const deactivateSubgroupButtons = async (groupId, subgroupId, exceptButtonId) => {
        const group = layout.groups.find(g => g.id === groupId);
        if (!group) return;

        const buttonsToDeactivate = group.buttons.filter(
            b => b.subgroupId === subgroupId && b.id !== exceptButtonId && activeStates[b.id]
        );

        for (const btn of buttonsToDeactivate) {
            await handleButtonDeactivation(btn);
            setActiveStates(prev => ({ ...prev, [btn.id]: false }));
        }
    };

    const handleButtonDeactivation = async (btn) => {
        const topic = btn.topic;
        const type = btn.type;

        let currentState = topicValuesRef.current[topic];
        if (!currentState) {
            const def = savedCommands[topic]?.find(c => c.isDefault);
            if (def) {
                currentState = JSON.parse(JSON.stringify(def.value));
            } else {
                if (type && type.includes('MultiArray')) {
                    currentState = new Array(btn.array_length || 6).fill(0);
                } else if (type && type.includes('Twist')) {
                    currentState = { linear_x: 0, linear_y: 0, linear_z: 0, angular_x: 0, angular_y: 0, angular_z: 0 };
                } else {
                    currentState = "";
                }
            }
        }

        let nextState;
        if (Array.isArray(currentState)) nextState = [...currentState];
        else if (typeof currentState === 'object' && currentState !== null) nextState = { ...currentState };
        else nextState = currentState;

        let defaultStateForTopic;
        const defObj = savedCommands[topic]?.find(c => c.isDefault);
        if (defObj) defaultStateForTopic = defObj.value;
        else {
            if (type && type.includes('MultiArray')) {
                const targetLen = btn.array_length || (nextState ? nextState.length : 6) || 6;
                defaultStateForTopic = new Array(targetLen).fill(0);
            }
            else if (type && type.includes('Twist')) defaultStateForTopic = { linear_x: 0, linear_y: 0, linear_z: 0, angular_x: 0, angular_y: 0, angular_z: 0 };
            else defaultStateForTopic = "";
        }

        if (type && type.includes('MultiArray')) {
            if (!Array.isArray(nextState)) nextState = [];
            const targetLen = btn.array_length || nextState.length || 6;
            if (nextState.length !== targetLen) {
                const newArray = new Array(targetLen).fill(0);
                for(let i=0; i<Math.min(targetLen, nextState.length); i++) newArray[i] = nextState[i];
                nextState = newArray;
            }

            if (!Array.isArray(defaultStateForTopic)) defaultStateForTopic = [];
            btn.activeIndices.forEach(idx => {
                const defVal = defaultStateForTopic[idx] !== undefined ? defaultStateForTopic[idx] : 0;
                nextState[idx] = defVal;
            });
        } else if (type && type.includes('Twist')) {
            nextState = defaultStateForTopic;
        } else {
            nextState = defaultStateForTopic;
        }

        topicValuesRef.current[topic] = nextState;
        await postPublish(topic, nextState);
    };

    const handleDashboardButtonClick = async (btn, groupId) => {
        const isCurrentlyActive = activeStates[btn.id];
        const newState = !isCurrentlyActive;

        try {
            if (btn.subgroupId && newState) {
                await deactivateSubgroupButtons(groupId, btn.subgroupId, btn.id);
            }

            // Branch for Macros
            if (btn.isMacro && newState) {
                setActiveStates(prev => ({ ...prev, [btn.id]: true }));
                showStatus('success', `Started Macro: ${btn.label}`);
                const res = await fetch(`${BACKEND_URL}/ros/macro`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ steps: btn.macroSteps || [] })
                });
                if (!res.ok) throw new Error("Macro start failed");
                // Auto-toggle off visually after a brief moment since macros are self-terminating operations
                setTimeout(() => setActiveStates(prev => ({ ...prev, [btn.id]: false })), 1000);
                return;
            } else if (btn.isMacro && !newState) {
                return; // Can't "stop" a macro easily via frontend yet, just visual toggle
            }

            // Normal Topic Logic
            const topic = btn.topic;
            const type = btn.type;
            let currentState = topicValuesRef.current[topic];

            if (!currentState) {
                const def = savedCommands[topic]?.find(c => c.isDefault);
                if (def) {
                    currentState = JSON.parse(JSON.stringify(def.value));
                } else {
                    if (type && type.includes('MultiArray')) {
                        const len = btn.array_length || 6;
                        currentState = new Array(len).fill(0);
                    } else if (type && type.includes('Twist')) {
                        currentState = { linear_x: 0, linear_y: 0, linear_z: 0, angular_x: 0, angular_y: 0, angular_z: 0 };
                    } else {
                        currentState = "";
                    }
                }
            }

            let nextState;
            if (Array.isArray(currentState)) nextState = [...currentState];
            else if (typeof currentState === 'object' && currentState !== null) nextState = { ...currentState };
            else nextState = currentState;

            let defaultStateForTopic;
            const defObj = savedCommands[topic]?.find(c => c.isDefault);
            if (defObj) defaultStateForTopic = defObj.value;
            else {
                if (type && type.includes('MultiArray')) {
                    const targetLen = btn.array_length || (nextState ? nextState.length : 6) || 6;
                    defaultStateForTopic = new Array(targetLen).fill(0);
                }
                else if (type && type.includes('Twist')) defaultStateForTopic = { linear_x: 0, linear_y: 0, linear_z: 0, angular_x: 0, angular_y: 0, angular_z: 0 };
                else defaultStateForTopic = "";
            }

            if (type && type.includes('MultiArray')) {
                if (!Array.isArray(nextState)) nextState = [];
                const targetLen = btn.array_length || nextState.length || 6;
                if (nextState.length !== targetLen) {
                    const newArray = new Array(targetLen).fill(0);
                    for(let i=0; i<Math.min(targetLen, nextState.length); i++) newArray[i] = nextState[i];
                    nextState = newArray;
                }

                if (!Array.isArray(defaultStateForTopic)) defaultStateForTopic = [];

                btn.activeIndices.forEach(idx => {
                    if (newState) {
                        if (btn.values && btn.values[idx] !== undefined) {
                            nextState[idx] = btn.values[idx];
                        }
                    } else {
                        const defVal = defaultStateForTopic[idx] !== undefined ? defaultStateForTopic[idx] : 0;
                        nextState[idx] = defVal;
                    }
                });
            }
            else if (type && type.includes('Twist')) {
                if (newState) {
                    nextState = btn.values;
                } else {
                    nextState = defaultStateForTopic;
                }
            }
            else {
                if (newState) {
                    nextState = btn.values;
                } else {
                    nextState = defaultStateForTopic;
                }
            }

            topicValuesRef.current[topic] = nextState;
            setActiveStates(prev => ({ ...prev, [btn.id]: newState }));
            await postPublish(topic, nextState);
            showStatus('success', `${newState ? 'Activated' : 'Deactivated'} ${btn.label}`);

        } catch (e) {
            console.error(e);
            showStatus('error', e.message);
        }
    };

    const [activeStates, setActiveStates] = useState(() => {
        try {
            const saved = localStorage.getItem(`science_${instanceName}_activeStates`);
            return saved ? JSON.parse(saved) : {};
        } catch { return {}; }
    });

    useEffect(() => {
        localStorage.setItem(`science_${instanceName}_activeStates`, JSON.stringify(activeStates));
    }, [activeStates, instanceName]);

    useEffect(() => {
        localStorage.setItem(`science_${instanceName}_topicValues`, JSON.stringify(topicValuesRef.current));
    }, [activeStates, instanceName]);

    const postPublish = async (topic, value) => {
        let processedValue = value;
        if (typeof value === 'string' && (value.trim().startsWith('{') || value.trim().startsWith('['))) {
            try {
                processedValue = JSON.parse(value);
            } catch (e) { }
        }

        if (satelEnabled && satel.isConnected) {
            if (topic === '/ESP32_GIZ/output_state_topic') {
                const arr = Array.isArray(processedValue) ? processedValue : [0,0,0];
                satel.sendKoszelnik(arr[0]||0, arr[1]||0, arr[2]||0);
            } else if (topic === '/servos_urc_control') {
                const arr = Array.isArray(processedValue) ? processedValue : [];
                satel.sendScienceServo(arr);
            } else if (topic === '/pumps_urc_control') {
                const arr = Array.isArray(processedValue) ? processedValue : [0,0];
                satel.sendSciencePump(arr[0]||0, arr[1]||0);
            } else if (topic === '/led_urc_control') {
                satel.sendScienceLed(processedValue);
            } else if (topic === '/ESP32_GIZ/led_state_topic') {
                const arr = Array.isArray(processedValue) ? processedValue : [0,0,0,0];
                satel.sendLed(arr);
            } else if (topic === '/array_topic') {
                const arr = Array.isArray(processedValue) ? processedValue : [];
                satel.sendArray(arr);
            }
        }

        const response = await fetch(`${BACKEND_URL}/ros/publish`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ topic, value: processedValue })
        });
        if (!response.ok) throw new Error('Failed to publish');
    };

    useEffect(() => {
        const intervals = {};

        layout.groups.forEach(group => {
            group.buttons.forEach(btn => {
                if (activeStates[btn.id] && btn.isContinuous) {
                    const freq = btn.publishFrequencyHz > 0 ? btn.publishFrequencyHz : 1;
                    const intervalMs = 1000 / freq;

                    intervals[btn.id] = setInterval(() => {
                        const topic = btn.topic;
                        const currentState = topicValuesRef.current[topic];
                        if (currentState !== undefined) {
                            postPublish(topic, currentState).catch(e => console.warn('Continuous publish error:', e));
                        }
                    }, intervalMs);
                }
            });
        });

        return () => {
            Object.values(intervals).forEach(clearInterval);
        };
    }, [activeStates, layout.groups]);

    const showStatus = (type, text) => {
        setStatusMessage({ type, text });
        setTimeout(() => setStatusMessage({ type: '', text: '' }), 3000);
    };

    // ----------------------------------------------------------------------
    // Config Modal Logic
    // ----------------------------------------------------------------------

    const openNewButtonModal = (groupId) => {
        setEditingGroupId(groupId);
        setEditingButtonId(null);
        setSelectedTopic('');
        setArrayValues([]);
        setTwistValues({ linear_x: 0, linear_y: 0, linear_z: 0, angular_x: 0, angular_y: 0, angular_z: 0 });
        setMessage('');
        setActiveIndices({});
        setTopicType('');
        setSelectedSubgroupId('');
        setIsContinuous(false);
        setPublishFrequencyHz(1);
        setIsMacro(false);
        setMacroSteps([]);
        setShowConfigModal(true);
    };

    const handleConfigSave = () => {
        if (!isMacro && !selectedTopic) return alert("Select a topic");
        if (isMacro && macroSteps.length === 0) return alert("Add at least one macro step");

        const newBtn = {
            id: editingButtonId || generateId(),
            label: prompt("Button Label:", "New Action") || "New Action",
            topic: selectedTopic || null,
            type: topicType,
            values: {},
            activeIndices: [],
            array_length: 0,
            subgroupId: selectedSubgroupId || null,
            isContinuous: isContinuous || false,
            publishFrequencyHz: publishFrequencyHz || 1,
            isMacro: isMacro,
            macroSteps: macroSteps
        };

        if (topicType.includes('MultiArray')) {
            newBtn.array_length = arrayValues.length;
            Object.keys(activeIndices).forEach(idx => {
                if (activeIndices[idx]) {
                    newBtn.values[idx] = arrayValues[idx];
                    newBtn.activeIndices.push(parseInt(idx));
                }
            });
        } else if (topicType.includes('Twist')) {
            newBtn.values = twistValues;
        } else {
            newBtn.values = message;
        }

        const newLayout = { ...layout };
        const group = newLayout.groups.find(g => g.id === editingGroupId);
        if (group) {
            if (editingButtonId) {
                const idx = group.buttons.findIndex(b => b.id === editingButtonId);
                if (idx !== -1) group.buttons[idx] = newBtn;
            } else {
                group.buttons.push(newBtn);
            }
        }
        saveLayout(newLayout);
        setShowConfigModal(false);
    };

    const handleTopicChange = async (topic) => {
        setSelectedTopic(topic);
        setArrayValues([]);
        setTwistValues({ linear_x: 0, linear_y: 0, linear_z: 0, angular_x: 0, angular_y: 0, angular_z: 0 });
        setMessage('');
        setActiveIndices({});

        if (topic) {
            try {
                const res = await fetch(`${BACKEND_URL}/ros2/topic_info?name=${encodeURIComponent(topic)}`);
                const data = await res.json();
                setTopicType(data.type);

                if (data.type && data.type.includes('MultiArray')) {
                    const len = data.array_length || 6;
                    setArrayValues(new Array(len).fill(0));
                }
            } catch (e) {
                console.error(e);
            }
        }
    };

    // Defaults modal reset
    useEffect(() => {
        if (showDefaultsModal) {
            setSelectedTopic('');
            setTopicType('');
            setMessage('');
            setArrayValues([]);
            fetchTopics();
        }
    }, [showDefaultsModal]);

    const renderSavedCommands = () => {
        if (!selectedTopic || !savedCommands[selectedTopic]) return null;

        return (
            <div style={{ marginBottom: '20px', backgroundColor: '#1e2124', padding: '10px', borderRadius: '5px' }}>
                <h4 style={{ marginTop: 0 }}>Current Defaults:</h4>
                <div style={{ display: 'flex', gap: '10px', flexWrap: 'wrap' }}>
                    {savedCommands[selectedTopic]
                        .filter(cmd => cmd.isDefault)
                        .map((cmd, idx) => (
                            <div key={idx} style={{ padding: '5px 10px', backgroundColor: '#333', borderRadius: '4px', borderLeft: '3px solid #FFC107' }}>
                                <span style={{ fontWeight: 'bold', color: '#FFC107' }}>Default</span>
                                <div style={{ fontSize: '0.8em', color: '#ccc' }}>
                                    {JSON.stringify(cmd.value)}
                                </div>
                            </div>
                        ))}
                    {!savedCommands[selectedTopic].some(c => c.isDefault) && <span style={{ color: '#888' }}>No defaults set. System will use 0.</span>}
                </div>
            </div>
        );
    };

    const renderInputFields = () => {
        if (!topicType) return null;

        if (topicType.includes('MultiArray')) {
            return (
                <div>
                    <div style={{ marginBottom: '10px', display: 'flex', alignItems: 'center', gap: '10px' }}>
                        <label style={{ color: '#ccc', fontSize: '0.9em' }}>Array Length:</label>
                        <input
                            type="number"
                            min="1"
                            value={arrayValues.length}
                            onChange={(e) => {
                                const newLen = Math.max(1, parseInt(e.target.value) || 1);
                                const newArray = new Array(newLen).fill(0);
                                for(let i=0; i<Math.min(newLen, arrayValues.length); i++){
                                    newArray[i] = arrayValues[i];
                                }
                                setArrayValues(newArray);
                            }}
                            style={{ padding: '6px', background: '#333', border: '1px solid #555', color: 'white', borderRadius: '4px', width: '80px' }}
                        />
                    </div>
                    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: '10px' }}>
                        {arrayValues.map((val, i) => (
                            <div key={i} style={{ display: 'flex', alignItems: 'center', gap: '5px' }}>
                                <label style={{ width: '30px', color: '#888' }}>{i}:</label>
                                <input
                                    type="number"
                                    value={val}
                                    onChange={(e) => {
                                        const nv = [...arrayValues];
                                        nv[i] = parseFloat(e.target.value);
                                        setArrayValues(nv);
                                    }}
                                    style={{ flex: 1, padding: '8px', background: '#333', border: '1px solid #444', color: 'white', borderRadius: '4px' }}
                                />
                            </div>
                        ))}
                    </div>
                </div>
            );
        } else if (topicType.includes('Twist')) {
            return (
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: '10px' }}>
                    {['linear_x', 'linear_y', 'linear_z', 'angular_x', 'angular_y', 'angular_z'].map(k => (
                        <div key={k}>
                            <label style={{ display: 'block', fontSize: '0.8em', color: '#aaa', marginBottom: '2px' }}>{k}</label>
                            <input
                                type="number"
                                value={twistValues[k]}
                                onChange={(e) => setTwistValues({ ...twistValues, [k]: parseFloat(e.target.value) })}
                                style={{ width: '100%', padding: '8px', background: '#333', border: '1px solid #444', color: 'white', borderRadius: '4px' }}
                            />
                        </div>
                    ))}
                </div>
            );
        } else {
            return (
                <input
                    type="text"
                    value={message}
                    onChange={(e) => setMessage(e.target.value)}
                    placeholder="Enter Message..."
                    style={{ width: '100%', padding: '10px', background: '#333', border: '1px solid #444', color: 'white', borderRadius: '4px' }}
                />
            );
        }
    };

    // ----------------------------------------------------------------------
    // Drag-to-Resize Handlers
    // ----------------------------------------------------------------------

    const handleResizeStart = (e, groupId, currentSpan) => {
        e.preventDefault();
        e.stopPropagation();
        setResizingGroupId(groupId);
        resizeStartXRef.current = e.clientX || e.touches?.[0]?.clientX || 0;
        resizeStartSpanRef.current = currentSpan;

        document.addEventListener('mousemove', handleResizeMove);
        document.addEventListener('mouseup', handleResizeEnd);
        document.addEventListener('touchmove', handleResizeMove);
        document.addEventListener('touchend', handleResizeEnd);
    };

    const handleResizeMove = (e) => {
        if (!resizingGroupId || !gridContainerRef.current) return;

        const clientX = e.clientX || e.touches?.[0]?.clientX || 0;
        const deltaX = clientX - resizeStartXRef.current;

        const containerWidth = gridContainerRef.current.offsetWidth;
        const gap = 20;
        const columnWidth = (containerWidth - (gap * (layout.gridColumns - 1))) / layout.gridColumns;

        const spanDelta = Math.round(deltaX / (columnWidth + gap));
        let newSpan = resizeStartSpanRef.current + spanDelta;
        newSpan = Math.max(1, Math.min(layout.gridColumns, newSpan));

        const newLayout = { ...layout };
        const group = newLayout.groups.find(g => g.id === resizingGroupId);
        if (group && group.gridColSpan !== newSpan) {
            group.gridColSpan = newSpan;
            setLayout(newLayout);
        }
    };

    const handleResizeEnd = () => {
        if (resizingGroupId) {
            saveLayout(layout);
        }
        setResizingGroupId(null);
        document.removeEventListener('mousemove', handleResizeMove);
        document.removeEventListener('mouseup', handleResizeEnd);
        document.removeEventListener('touchmove', handleResizeMove);
        document.removeEventListener('touchend', handleResizeEnd);
    };

    useEffect(() => {
        return () => {
            document.removeEventListener('mousemove', handleResizeMove);
            document.removeEventListener('mouseup', handleResizeEnd);
            document.removeEventListener('touchmove', handleResizeMove);
            document.removeEventListener('touchend', handleResizeEnd);
        };
    }, []);

    // ----------------------------------------------------------------------
    // Render
    // ----------------------------------------------------------------------

    return (
        <div style={{ color: 'white' }}>

            {/* Header */}
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '20px', borderBottom: '1px solid #444', paddingBottom: '10px' }}>
                <h3 style={{ margin: 0 }}>🔬 Action Dashboard</h3>
                <div style={{ display: 'flex', gap: '10px' }}>
                    <button
                        onClick={() => setShowDefaultsModal(true)}
                        style={{ padding: '8px 16px', backgroundColor: '#555', color: 'white', border: 'none', borderRadius: '4px', cursor: 'pointer' }}
                    >
                        Global Defaults
                    </button>
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
                            <p style={{ fontSize: '0.8em', color: '#888', margin: '5px 0 0 0' }}>How many columns in the grid (1-12)</p>
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
                            <p style={{ fontSize: '0.8em', color: '#888', margin: '5px 0 0 0' }}>Maximum dashboard width in pixels</p>
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

            {/* Defaults Modal */}
            {showDefaultsModal && (
                <div style={{ position: 'fixed', top: 0, left: 0, right: 0, bottom: 0, backgroundColor: 'rgba(0,0,0,0.8)', zIndex: 1100, display: 'flex', justifyContent: 'center', alignItems: 'center' }}>
                    <div style={{ backgroundColor: '#2a2e33', padding: '25px', borderRadius: '10px', width: '700px', maxHeight: '90vh', overflowY: 'auto' }}>
                        <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '20px' }}>
                            <h3 style={{ margin: 0 }}>Configure Global Defaults</h3>
                            <button onClick={() => setShowDefaultsModal(false)} style={{ background: 'none', border: 'none', color: '#aaa', cursor: 'pointer', fontSize: '1.2em' }}>✕</button>
                        </div>

                        <p style={{ color: '#ccc', fontSize: '0.9em', marginBottom: '15px' }}>
                            Set the default values for topics. These values are used when switches are turned <strong>OFF</strong>.
                        </p>

                        <div style={{ marginBottom: '20px' }}>
                            <button onClick={fetchTopics} disabled={loading} style={{ padding: '5px 10px', marginRight: '10px' }}>Actualiser Topics</button>
                            <label style={{ marginLeft: '10px' }}>Select Topic:</label>
                            <select value={selectedTopic} onChange={(e) => handleTopicChange(e.target.value)} style={{ width: '100%', padding: '10px', marginTop: '5px', background: '#333', color: 'white', border: '1px solid #555' }}>
                                <option value="">-- Select --</option>
                                {topics.map(t => <option key={t} value={t}>{t}</option>)}
                            </select>
                        </div>

                        {renderSavedCommands()}

                        {selectedTopic && (
                            <div style={{ borderTop: '1px solid #444', paddingTop: '15px' }}>
                                <h4 style={{ margin: '0 0 10px 0' }}>Set New Default</h4>
                                {renderInputFields()}

                                <div style={{ marginTop: '20px', display: 'flex', gap: '10px' }}>
                                    <button
                                        onClick={async () => {
                                            if (!selectedTopic) return;
                                            let value;
                                            if (topicType.includes('MultiArray')) value = arrayValues;
                                            else if (topicType.includes('Twist')) value = twistValues;
                                            else value = message;

                                            try {
                                                const response = await fetch(`${BACKEND_URL}/ros/saved_commands`, {
                                                    method: 'POST',
                                                    headers: { 'Content-Type': 'application/json' },
                                                    body: JSON.stringify({
                                                        topic: selectedTopic,
                                                        name: "Default",
                                                        value: value,
                                                        type: topicType,
                                                        isDefault: true,
                                                        labels: arrayLabels
                                                    })
                                                });
                                                if (response.ok) {
                                                    await loadSavedCommands();
                                                    showStatus('success', `✓ Defaults updated for ${selectedTopic}`);
                                                } else {
                                                    const err = await response.json();
                                                    showStatus('error', err.detail);
                                                }
                                            } catch (e) { showStatus('error', e.message); }
                                        }}
                                        style={{ flex: 1, padding: '10px', backgroundColor: '#FFC107', color: 'black', border: 'none', borderRadius: '5px', cursor: 'pointer', fontWeight: 'bold' }}
                                    >
                                        ⭐ Save as Default
                                    </button>
                                </div>
                            </div>
                        )}
                    </div>
                </div>
            )}

            {/* Editor Controls */}
            {isEditMode && (
                <div style={{ marginBottom: '20px', padding: '15px', backgroundColor: '#2a2e33', borderRadius: '8px', display: 'flex', gap: '10px', alignItems: 'center', flexWrap: 'wrap' }}>
                    <button
                        onClick={() => {
                            const label = prompt("Group Name:");
                            if (label) {
                                const existingPositions = layout.groups.map(g => g.gridRow || 0);
                                const nextRow = existingPositions.length > 0 ? Math.max(...existingPositions) + 1 : 1;
                                const newLayout = {
                                    ...layout,
                                    groups: [...layout.groups, {
                                        id: generateId(),
                                        label,
                                        buttons: [],
                                        gridRow: nextRow,
                                        gridCol: 1,
                                        gridColSpan: layout.gridColumns
                                    }]
                                };
                                saveLayout(newLayout);
                            }
                        }}
                        style={{ padding: '8px 16px', backgroundColor: '#666', border: 'none', borderRadius: '4px', color: 'white', cursor: 'pointer' }}
                    >
                        + Add Action Group
                    </button>
                    <span style={{ color: '#888', fontSize: '0.9em' }}>Grid: {layout.gridColumns} columns × auto rows | Max Width: {layout.maxWidth}px</span>
                </div>
            )}

            {/* Dashboard Grid */}
            <div
                ref={gridContainerRef}
                style={{
                    display: 'grid',
                    gridTemplateColumns: `repeat(${layout.gridColumns}, 1fr)`,
                    gap: '20px',
                    alignItems: 'start',
                    maxWidth: `${layout.maxWidth}px`
                }}
            >
                {[...layout.groups]
                    .sort((a, b) => ((a.gridRow || 0) - (b.gridRow || 0)) || ((a.gridCol || 0) - (b.gridCol || 0)))
                    .map(group => (
                        <div
                            key={group.id}
                            style={{
                                gridColumn: `span ${Math.min(group.gridColSpan || layout.gridColumns, layout.gridColumns)}`,
                                display: 'flex',
                                flexDirection: 'column',
                                gap: '10px',
                                padding: '15px',
                                backgroundColor: '#1e2124',
                                borderRadius: '8px',
                                borderLeft: '4px solid #2196F3',
                                position: 'relative',
                                transition: resizingGroupId === group.id ? 'none' : 'all 0.2s ease',
                                outline: resizingGroupId === group.id ? '2px solid #9C27B0' : 'none'
                            }}
                        >
                            {/* Resize Handle */}
                            {isEditMode && (
                                <div
                                    onMouseDown={(e) => handleResizeStart(e, group.id, group.gridColSpan || layout.gridColumns)}
                                    onTouchStart={(e) => handleResizeStart(e, group.id, group.gridColSpan || layout.gridColumns)}
                                    style={{
                                        position: 'absolute',
                                        right: 0,
                                        top: 0,
                                        bottom: 0,
                                        width: '12px',
                                        cursor: 'ew-resize',
                                        background: resizingGroupId === group.id ? '#9C27B0' : 'linear-gradient(to right, transparent, rgba(156, 39, 176, 0.3))',
                                        borderTopRightRadius: '8px',
                                        borderBottomRightRadius: '8px',
                                        display: 'flex',
                                        alignItems: 'center',
                                        justifyContent: 'center',
                                        transition: 'background 0.2s ease'
                                    }}
                                    onMouseEnter={(e) => e.currentTarget.style.background = 'rgba(156, 39, 176, 0.5)'}
                                    onMouseLeave={(e) => e.currentTarget.style.background = resizingGroupId === group.id ? '#9C27B0' : 'linear-gradient(to right, transparent, rgba(156, 39, 176, 0.3))'}
                                >
                                    <div style={{
                                        width: '3px',
                                        height: '30px',
                                        borderRadius: '2px',
                                        backgroundColor: '#9C27B0'
                                    }} />
                                </div>
                            )}

                            {/* Group Label */}
                            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: '10px', flexWrap: 'wrap' }}>
                                <div style={{ minWidth: '120px' }}>
                                    <h3 style={{ margin: '0 0 5px 0' }}>{group.label}</h3>
                                    {isEditMode && (
                                        <button
                                            onClick={() => {
                                                if (confirm("Delete group?")) {
                                                    const newLayout = { ...layout, groups: layout.groups.filter(g => g.id !== group.id) };
                                                    saveLayout(newLayout);
                                                }
                                            }}
                                            style={{ fontSize: '0.8em', color: '#f44336', background: 'none', border: 'none', cursor: 'pointer', padding: 0 }}
                                        >
                                            Remove Group
                                        </button>
                                    )}
                                </div>

                                {isEditMode && (
                                    <div style={{ display: 'flex', gap: '8px', alignItems: 'center', flexWrap: 'wrap', fontSize: '0.85em' }}>
                                        <div style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
                                            <label style={{ color: '#888' }}>Row:</label>
                                            <input
                                                type="number"
                                                min="1"
                                                value={group.gridRow || 1}
                                                onChange={(e) => {
                                                    const val = Math.max(1, parseInt(e.target.value) || 1);
                                                    const newLayout = { ...layout };
                                                    const g = newLayout.groups.find(gr => gr.id === group.id);
                                                    if (g) g.gridRow = val;
                                                    saveLayout(newLayout);
                                                }}
                                                style={{ width: '50px', padding: '4px 6px', background: '#333', border: '1px solid #555', color: 'white', borderRadius: '3px' }}
                                            />
                                        </div>
                                        <span style={{ color: '#9C27B0', fontSize: '0.9em' }}>
                                            ↔ Span: {group.gridColSpan || layout.gridColumns}/{layout.gridColumns} (drag edge)
                                        </span>
                                    </div>
                                )}
                            </div>

                            {/* Buttons Container */}
                            <div style={{ display: 'flex', flexWrap: 'wrap', gap: '15px', flex: 1 }}>
                                {/* Regular buttons */}
                                {group.buttons.filter(btn => !btn.subgroupId).map(btn => (
                                    <div key={btn.id} style={{ position: 'relative' }}>
                                        <button
                                            onClick={() => !isEditMode && handleDashboardButtonClick(btn, group.id)}
                                            style={{
                                                padding: '15px 25px',
                                                backgroundColor: activeStates[btn.id] ? '#4CAF50' : '#3a3f45',
                                                color: 'white',
                                                borderRadius: '5px',
                                                cursor: isEditMode ? 'default' : 'pointer',
                                                minWidth: '100px',
                                                fontWeight: 'bold',
                                                opacity: isEditMode ? 0.6 : 1,
                                                border: activeStates[btn.id] ? '2px solid #66bb6a' : '2px solid transparent'
                                            }}
                                        >
                                            {btn.label} {btn.isContinuous && '🔁'} {btn.isMacro && '⚡'}
                                        </button>

                                        {isEditMode && (
                                            <div style={{ position: 'absolute', top: '-8px', right: '-8px' }}>
                                                <button
                                                    onClick={() => {
                                                        const newLayout = { ...layout };
                                                        const g = newLayout.groups.find(gr => gr.id === group.id);
                                                        g.buttons = g.buttons.filter(b => b.id !== btn.id);
                                                        saveLayout(newLayout);
                                                    }}
                                                    style={{ width: '20px', height: '20px', borderRadius: '50%', backgroundColor: '#f44336', color: 'white', border: 'none', cursor: 'pointer', display: 'flex', justifyContent: 'center', alignItems: 'center', fontSize: '12px' }}
                                                >
                                                    x
                                                </button>
                                            </div>
                                        )}
                                    </div>
                                ))}

                                {/* Subgroups */}
                                {(() => {
                                    const subgroupIds = [...new Set(group.buttons.filter(b => b.subgroupId).map(b => b.subgroupId))];
                                    return subgroupIds.map(subgroupId => {
                                        const subgroupButtons = group.buttons.filter(b => b.subgroupId === subgroupId);
                                        const subgroupName = group.subgroups?.find(sg => sg.id === subgroupId)?.name || 'Subgroup';
                                        return (
                                            <div key={subgroupId} style={{
                                                display: 'flex',
                                                flexDirection: 'column',
                                                gap: '8px',
                                                padding: '10px',
                                                backgroundColor: '#252830',
                                                borderRadius: '8px',
                                                border: '1px solid #3a3f45',
                                                minWidth: '120px'
                                            }}>
                                                <div style={{
                                                    display: 'flex',
                                                    justifyContent: 'space-between',
                                                    alignItems: 'center',
                                                    borderBottom: '1px solid #444',
                                                    paddingBottom: '6px',
                                                    marginBottom: '4px'
                                                }}>
                                                    <span style={{ fontSize: '0.8em', color: '#888', fontWeight: 'bold' }}>{subgroupName}</span>
                                                    <span style={{ fontSize: '0.7em', color: '#555' }}>◉ 1 only</span>
                                                </div>

                                                {subgroupButtons.map(btn => (
                                                    <div key={btn.id} style={{ position: 'relative' }}>
                                                        <button
                                                            onClick={() => !isEditMode && handleDashboardButtonClick(btn, group.id)}
                                                            style={{
                                                                width: '100%',
                                                                padding: '12px 20px',
                                                                backgroundColor: activeStates[btn.id] ? '#4CAF50' : '#3a3f45',
                                                                color: 'white',
                                                                borderRadius: '4px',
                                                                cursor: isEditMode ? 'default' : 'pointer',
                                                                fontWeight: 'bold',
                                                                opacity: isEditMode ? 0.6 : 1,
                                                                border: activeStates[btn.id] ? '2px solid #66bb6a' : '2px solid transparent',
                                                                textAlign: 'left'
                                                            }}
                                                        >
                                                            {btn.label} {btn.isContinuous && '🔁'} {btn.isMacro && '⚡'}
                                                        </button>

                                                        {isEditMode && (
                                                            <div style={{ position: 'absolute', top: '-6px', right: '-6px' }}>
                                                                <button
                                                                    onClick={() => {
                                                                        const newLayout = { ...layout };
                                                                        const g = newLayout.groups.find(gr => gr.id === group.id);
                                                                        g.buttons = g.buttons.filter(b => b.id !== btn.id);
                                                                        saveLayout(newLayout);
                                                                    }}
                                                                    style={{ width: '18px', height: '18px', borderRadius: '50%', backgroundColor: '#f44336', color: 'white', border: 'none', cursor: 'pointer', display: 'flex', justifyContent: 'center', alignItems: 'center', fontSize: '10px' }}
                                                                >
                                                                    x
                                                                </button>
                                                            </div>
                                                        )}
                                                    </div>
                                                ))}

                                                {isEditMode && (
                                                    <button
                                                        onClick={() => {
                                                            if (confirm(`Delete subgroup "${subgroupName}"? Buttons will become regular buttons.`)) {
                                                                const newLayout = { ...layout };
                                                                const g = newLayout.groups.find(gr => gr.id === group.id);
                                                                g.buttons = g.buttons.map(b =>
                                                                    b.subgroupId === subgroupId ? { ...b, subgroupId: null } : b
                                                                );
                                                                g.subgroups = (g.subgroups || []).filter(sg => sg.id !== subgroupId);
                                                                saveLayout(newLayout);
                                                            }
                                                        }}
                                                        style={{ fontSize: '0.7em', color: '#f44336', background: 'none', border: 'none', cursor: 'pointer', padding: '4px 0', marginTop: '4px' }}
                                                    >
                                                        Remove Subgroup
                                                    </button>
                                                )}
                                            </div>
                                        );
                                    });
                                })()}

                                {isEditMode && (
                                    <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                                        <button
                                            onClick={() => openNewButtonModal(group.id)}
                                            style={{ padding: '10px 20px', backgroundColor: 'transparent', border: '2px dashed #555', color: '#888', borderRadius: '5px', cursor: 'pointer' }}
                                        >
                                            + Add Button
                                        </button>
                                        <button
                                            onClick={() => {
                                                const name = prompt("Subgroup Name:");
                                                if (name) {
                                                    const newLayout = { ...layout };
                                                    const g = newLayout.groups.find(gr => gr.id === group.id);
                                                    if (!g.subgroups) g.subgroups = [];
                                                    g.subgroups.push({ id: generateId(), name });
                                                    saveLayout(newLayout);
                                                }
                                            }}
                                            style={{ padding: '10px 20px', backgroundColor: 'transparent', border: '2px dashed #9C27B0', color: '#9C27B0', borderRadius: '5px', cursor: 'pointer', fontSize: '0.9em' }}
                                        >
                                            + Add Subgroup
                                        </button>
                                    </div>
                                )}
                            </div>
                        </div>
                    ))}
            </div>

            {/* Configuration Modal */}
            {showConfigModal && (
                <div style={{ position: 'fixed', top: 0, left: 0, right: 0, bottom: 0, backgroundColor: 'rgba(0,0,0,0.8)', zIndex: 1000, display: 'flex', justifyContent: 'center', alignItems: 'center' }}>
                    <div style={{ backgroundColor: '#2a2e33', padding: '25px', borderRadius: '10px', width: '800px', maxHeight: '90vh', overflowY: 'auto' }}>
                        <h3>Configure Button</h3>

                        <div style={{ display: 'flex', gap: '20px', marginBottom: '15px' }}>
                            <label style={{ display: 'flex', alignItems: 'center', gap: '8px', cursor: 'pointer' }}>
                                <input type="radio" checked={!isMacro} onChange={() => setIsMacro(false)} />
                                Single Topic Action
                            </label>
                            <label style={{ display: 'flex', alignItems: 'center', gap: '8px', cursor: 'pointer', color: '#FFC107' }}>
                                <input type="radio" checked={isMacro} onChange={() => setIsMacro(true)} />
                                ⚡ Macro Sequence
                            </label>
                        </div>

                        <div>
                            {!isMacro ? (
                                <>
                                    <div style={{ marginBottom: '15px' }}>
                                        <label>Select Topic:</label>
                                        <select value={selectedTopic} onChange={(e) => handleTopicChange(e.target.value)} style={{ width: '100%', padding: '10px', marginTop: '5px', background: '#333', color: 'white', border: '1px solid #555' }}>
                                            <option value="">-- Select --</option>
                                            {topics.map(t => <option key={t} value={t}>{t}</option>)}
                                        </select>
                                    </div>

                                    {/* Subgroup Assignment */}
                                    {(() => {
                                        const currentGroup = layout.groups.find(g => g.id === editingGroupId);
                                        const subgroups = currentGroup?.subgroups || [];
                                        if (subgroups.length === 0) return null;
                                        return (
                                            <div style={{ marginBottom: '15px' }}>
                                                <label>Assign to Subgroup (optional):</label>
                                                <select
                                                    value={selectedSubgroupId}
                                                    onChange={(e) => setSelectedSubgroupId(e.target.value)}
                                                    style={{ width: '100%', padding: '10px', marginTop: '5px', background: '#333', color: 'white', border: '1px solid #9C27B0' }}
                                                >
                                                    <option value="">-- No Subgroup (regular button) --</option>
                                                    {subgroups.map(sg => <option key={sg.id} value={sg.id}>{sg.name} (◉ 1 only)</option>)}
                                                </select>
                                                <p style={{ fontSize: '0.8em', color: '#888', margin: '5px 0 0 0' }}>
                                                    Buttons in the same subgroup work like radio buttons - only one can be active at a time.
                                                </p>
                                            </div>
                                        );
                                    })()}

                                    {topicType && (
                                        <div style={{ marginBottom: '20px', border: '1px solid #444', padding: '15px', borderRadius: '5px' }}>
                                            <h4 style={{ margin: '0 0 10px 0' }}>Configure Values (When Switched ON)</h4>

                                            {topicType.includes('MultiArray') && (
                                                <>
                                                    <div style={{ marginBottom: '10px', display: 'flex', alignItems: 'center', gap: '10px' }}>
                                                        <label style={{ color: '#ccc', fontSize: '0.9em' }}>Array Length:</label>
                                                        <input
                                                            type="number"
                                                            min="1"
                                                            value={arrayValues.length}
                                                            onChange={(e) => {
                                                                const newLen = Math.max(1, parseInt(e.target.value) || 1);
                                                                const newArray = new Array(newLen).fill(0);
                                                                for(let i=0; i<Math.min(newLen, arrayValues.length); i++){
                                                                    newArray[i] = arrayValues[i];
                                                                }
                                                                setArrayValues(newArray);
                                                                
                                                                const newActiveIndices = { ...activeIndices };
                                                                Object.keys(newActiveIndices).forEach(k => {
                                                                    if(parseInt(k) >= newLen) delete newActiveIndices[k];
                                                                });
                                                                setActiveIndices(newActiveIndices);
                                                            }}
                                                            style={{ padding: '6px', background: '#333', border: '1px solid #555', color: 'white', borderRadius: '4px', width: '80px' }}
                                                        />
                                                    </div>
                                                    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: '10px' }}>
                                                        {Object.keys(activeIndices).length === 0 && <p style={{ color: '#888', fontStyle: 'italic', gridColumn: 'span 2' }}>Check boxes to control specific indices.</p>}
                                                        {arrayValues.map((val, i) => (
                                                            <div key={i} style={{ display: 'flex', alignItems: 'center', gap: '8px', backgroundColor: '#1e2124', padding: '8px', borderRadius: '4px' }}>
                                                                <input
                                                                    type="checkbox"
                                                                    checked={!!activeIndices[i]}
                                                                    onChange={(e) => setActiveIndices({ ...activeIndices, [i]: e.target.checked })}
                                                                />
                                                                <span style={{ fontSize: '0.9em', color: '#aaa', width: '40px' }}>Id {i}</span>
                                                                <input
                                                                    type="number"
                                                                    value={val}
                                                                    onChange={(e) => {
                                                                        const nv = [...arrayValues];
                                                                        nv[i] = parseFloat(e.target.value);
                                                                        setArrayValues(nv);
                                                                        if (!activeIndices[i]) setActiveIndices({ ...activeIndices, [i]: true });
                                                                    }}
                                                                    style={{ flex: 1, padding: '5px', background: '#333', border: '1px solid #555', color: 'white' }}
                                                                />
                                                            </div>
                                                        ))}
                                                    </div>
                                                </>
                                            )}

                                            {topicType.includes('Twist') && (
                                                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: '10px' }}>
                                                    {['linear_x', 'linear_y', 'linear_z', 'angular_x', 'angular_y', 'angular_z'].map(k => (
                                                        <div key={k}>
                                                            <label style={{ display: 'block', fontSize: '0.8em', color: '#aaa', marginBottom: '2px' }}>{k}</label>
                                                            <input
                                                                type="number"
                                                                value={twistValues[k]}
                                                                onChange={(e) => setTwistValues({ ...twistValues, [k]: parseFloat(e.target.value) })}
                                                                style={{ width: '100%', padding: '8px', background: '#333', border: '1px solid #444', color: 'white', borderRadius: '4px' }}
                                                            />
                                                        </div>
                                                    ))}
                                                </div>
                                            )}

                                            {!topicType.includes('MultiArray') && !topicType.includes('Twist') && (
                                                <input
                                                    type="text"
                                                    value={message}
                                                    onChange={(e) => setMessage(e.target.value)}
                                                    placeholder="Enter Message (JSON or String)"
                                                    style={{ width: '100%', padding: '10px', background: '#333', border: '1px solid #444', color: 'white', borderRadius: '4px' }}
                                                />
                                            )}

                                            <div style={{ marginTop: '15px', paddingTop: '15px', borderTop: '1px solid #555' }}>
                                                <h4 style={{ margin: '0 0 10px 0' }}>Continuous Publishing</h4>
                                                <label style={{ display: 'flex', alignItems: 'center', gap: '8px', cursor: 'pointer', color: '#ccc' }}>
                                                    <input
                                                        type="checkbox"
                                                        checked={isContinuous}
                                                        onChange={(e) => setIsContinuous(e.target.checked)}
                                                        style={{ cursor: 'pointer' }}
                                                    />
                                                    Enable Continuous Publishing (Sequence)
                                                </label>

                                                {isContinuous && (
                                                    <div style={{ marginTop: '10px' }}>
                                                        <label style={{ display: 'block', marginBottom: '5px', fontSize: '0.9em', color: '#aaa' }}>Publish Frequency / Period:</label>
                                                        <div style={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
                                                            <div style={{ flex: 1, display: 'flex', alignItems: 'center', background: '#333', border: '1px solid #444', borderRadius: '4px' }}>
                                                                <input
                                                                    type="number"
                                                                    min="0.01"
                                                                    step="0.1"
                                                                    value={publishFrequencyHz}
                                                                    onChange={(e) => {
                                                                        const hz = parseFloat(e.target.value);
                                                                        setPublishFrequencyHz(isNaN(hz) || hz <= 0 ? '' : hz);
                                                                    }}
                                                                    style={{ width: '100%', padding: '8px', background: 'transparent', border: 'none', color: 'white', outline: 'none' }}
                                                                />
                                                                <span style={{ paddingRight: '8px', color: '#aaa', fontSize: '0.9em' }}>Hz</span>
                                                            </div>
                                                            <span style={{ color: '#888' }}>≈</span>
                                                            <div style={{ flex: 1, display: 'flex', alignItems: 'center', background: '#333', border: '1px solid #444', borderRadius: '4px' }}>
                                                                <input
                                                                    type="number"
                                                                    min="1"
                                                                    step="10"
                                                                    value={publishFrequencyHz ? Math.round(1000 / publishFrequencyHz) : ''}
                                                                    onChange={(e) => {
                                                                        const ms = parseFloat(e.target.value);
                                                                        setPublishFrequencyHz(isNaN(ms) || ms <= 0 ? '' : Number((1000 / ms).toFixed(3)));
                                                                    }}
                                                                    style={{ width: '100%', padding: '8px', background: 'transparent', border: 'none', color: 'white', outline: 'none' }}
                                                                />
                                                                <span style={{ paddingRight: '8px', color: '#aaa', fontSize: '0.9em' }}>ms</span>
                                                            </div>
                                                        </div>
                                                    </div>
                                                )}
                                            </div>
                                        </div>
                                    )}
                                </>
                            ) : (
                                <div style={{ border: '1px solid #555', padding: '15px', borderRadius: '5px', backgroundColor: '#1e2124' }}>
                                    <h4>Macro Steps</h4>
                                    {macroSteps.map((step, idx) => (
                                        <div key={idx} style={{ padding: '15px', backgroundColor: '#333', marginBottom: '10px', borderRadius: '5px', position: 'relative' }}>
                                            <button
                                                onClick={() => setMacroSteps(macroSteps.filter((_, i) => i !== idx))}
                                                style={{ position: 'absolute', top: '10px', right: '10px', background: 'none', border: 'none', color: '#f44336', cursor: 'pointer' }}>✕</button>

                                            <div style={{ display: 'flex', gap: '10px', marginBottom: '10px' }}>
                                                <span style={{ fontWeight: 'bold', color: '#aaa', minWidth: '20px' }}>{idx + 1}.</span>
                                                <select
                                                    value={step.action}
                                                    onChange={(e) => {
                                                        const ns = [...macroSteps];
                                                        ns[idx].action = e.target.value;
                                                        setMacroSteps(ns);
                                                    }}
                                                    style={{ flex: 1, padding: '8px', background: '#444', color: 'white', border: '1px solid #555' }}
                                                >
                                                    <option value="publish">📢 Publish</option>
                                                    <option value="wait_topic">⏳ Wait for Topic</option>
                                                    <option value="wait_time">⏱ Wait Time (Delay)</option>
                                                </select>
                                            </div>

                                            {step.action === 'publish' && (
                                                <div style={{ display: 'flex', flexDirection: 'column', gap: '5px', paddingLeft: '30px' }}>
                                                    <input type="text" placeholder="Topic (e.g. /cmd_vel)" value={step.topic || ''} onChange={e => {
                                                        const ns = [...macroSteps]; ns[idx].topic = e.target.value; setMacroSteps(ns);
                                                    }} style={{ padding: '8px', background: '#222', color: 'white', border: '1px solid #555' }} />
                                                    
                                                    <div style={{ display: 'flex', gap: '5px' }}>
                                                        <input type="text" placeholder='JSON Value (e.g. {"linear_x": 1.0}) or Number' value={typeof step.value === 'object' ? JSON.stringify(step.value) : (step.value || '')} onChange={e => {
                                                            const ns = [...macroSteps];
                                                            try { ns[idx].value = JSON.parse(e.target.value); } catch { ns[idx].value = e.target.value; }
                                                            setMacroSteps(ns);
                                                        }} style={{ flex: 1, padding: '8px', background: '#222', color: 'white', border: '1px solid #555' }} />
                                                        
                                                        <input type="number" placeholder="Arr Index (Opt)" value={step.arrayIndex !== undefined ? step.arrayIndex : ''} onChange={e => {
                                                            const ns = [...macroSteps]; 
                                                            if (e.target.value === '') delete ns[idx].arrayIndex;
                                                            else ns[idx].arrayIndex = parseInt(e.target.value);
                                                            setMacroSteps(ns);
                                                        }} style={{ width: '120px', padding: '8px', background: '#222', color: 'white', border: '1px solid #555' }} title="If publishing to a MultiArray, update only this index" />
                                                    </div>
                                                </div>
                                            )}

                                            {step.action === 'wait_topic' && (
                                                <div style={{ display: 'flex', flexDirection: 'column', gap: '5px', paddingLeft: '30px' }}>
                                                    <input type="text" placeholder="Topic to watch (e.g. /status)" value={step.topic || ''} onChange={e => {
                                                        const ns = [...macroSteps]; ns[idx].topic = e.target.value; setMacroSteps(ns);
                                                    }} style={{ padding: '8px', background: '#222', color: 'white', border: '1px solid #555' }} />

                                                    <div style={{ display: 'flex', gap: '5px' }}>
                                                        <select value={step.condition || '=='} onChange={e => {
                                                            const ns = [...macroSteps]; ns[idx].condition = e.target.value; setMacroSteps(ns);
                                                        }} style={{ padding: '8px', background: '#222', color: 'white', border: '1px solid #555', width: '80px' }}>
                                                            <option value="==">==</option>
                                                            <option value="!=">!=</option>
                                                            <option value=">">&gt;</option>
                                                            <option value="<">&lt;</option>
                                                        </select>
                                                        <input type="text" placeholder="Expected Value" value={step.value || ''} onChange={e => {
                                                            const ns = [...macroSteps]; ns[idx].value = e.target.value; setMacroSteps(ns);
                                                        }} style={{ flex: 1, padding: '8px', background: '#222', color: 'white', border: '1px solid #555' }} />
                                                    </div>

                                                    <input type="number" placeholder="Timeout (seconds)" value={step.timeout || 30} onChange={e => {
                                                        const ns = [...macroSteps]; ns[idx].timeout = parseFloat(e.target.value); setMacroSteps(ns);
                                                    }} style={{ padding: '8px', background: '#222', color: 'white', border: '1px solid #555' }} />
                                                </div>
                                            )}

                                            {step.action === 'wait_time' && (
                                                <div style={{ display: 'flex', alignItems: 'center', gap: '10px', paddingLeft: '30px' }}>
                                                    <input type="number" step="0.1" placeholder="Seconds" value={step.delay || 1.0} onChange={e => {
                                                        const ns = [...macroSteps]; ns[idx].delay = parseFloat(e.target.value); setMacroSteps(ns);
                                                    }} style={{ width: '100px', padding: '8px', background: '#222', color: 'white', border: '1px solid #555' }} />
                                                    <span style={{ color: '#aaa' }}>Seconds</span>
                                                </div>
                                            )}
                                        </div>
                                    ))}

                                    <button
                                        onClick={() => setMacroSteps([...macroSteps, { action: 'publish', topic: '', value: '' }])}
                                        style={{ width: '100%', padding: '10px', background: 'transparent', border: '2px dashed #9C27B0', color: '#9C27B0', borderRadius: '5px', cursor: 'pointer' }}
                                    >
                                        + Add Macro Step
                                    </button>
                                </div>
                            )}

                            <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '10px', marginTop: '20px' }}>
                                <button onClick={() => setShowConfigModal(false)} style={{ padding: '10px 20px', backgroundColor: '#666', border: 'none', borderRadius: '5px', color: 'white', cursor: 'pointer' }}>Cancel</button>
                                <button onClick={handleConfigSave} style={{ padding: '10px 20px', backgroundColor: '#2196F3', border: 'none', borderRadius: '5px', color: 'white', cursor: 'pointer' }}>Save Button</button>
                            </div>
                        </div>
                    </div>
                </div>
            )}

            {/* Status Toast */}
            {statusMessage.text && (
                <div style={{ padding: '15px', position: 'fixed', top: '20px', right: '20px', backgroundColor: statusMessage.type === 'success' ? '#4CAF50' : statusMessage.type === 'info' ? '#2196F3' : '#f44336', color: 'white', borderRadius: '5px', zIndex: 2000 }}>
                    {statusMessage.text}
                </div>
            )}
        </div>
    );
};

export default ScienceDashboard;
