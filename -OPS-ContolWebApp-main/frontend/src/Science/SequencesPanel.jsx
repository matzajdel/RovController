import React, { useState, useEffect, useRef, useCallback } from 'react';

const BACKEND_URL = window.BACKEND_URL || 'http://localhost:2137';

// ──────────────────────────────────────────────────────────────────────────────
// Condition labels
// ──────────────────────────────────────────────────────────────────────────────
const CONDITIONS = [
    { value: 'eq', label: '== (równe)' },
    { value: 'neq', label: '!= (różne)' },
    { value: 'gt', label: '> (większe)' },
    { value: 'gte', label: '>= (większe lub równe)' },
    { value: 'lt', label: '< (mniejsze)' },
    { value: 'lte', label: '<= (mniejsze lub równe)' },
    { value: 'contains', label: 'contains (zawiera)' },
];

const STEP_TYPES = ['publish', 'wait', 'delay', 'loop'];

const emptyStep = (type = 'publish') => {
    if (type === 'publish') return { type: 'publish', topic: '', value: 0 };
    if (type === 'wait') return { type: 'wait', topic: '', condition: 'eq', value: 0, timeout_s: 30 };
    if (type === 'delay') return { type: 'delay', seconds: 1 };
    if (type === 'loop') return { type: 'loop', loop_to: 1, repeat: 2, infinite: false };
    return { type };
};

const emptySeq = () => ({ id: '', name: 'Nowa sekwencja', steps: [] });

// ──────────────────────────────────────────────────────────────────────────────
// Step status icon
// ──────────────────────────────────────────────────────────────────────────────
function StepIcon({ state }) {
    const map = { done: '✅', running: '⏳', error: '❌', pending: '⬜', stopped: '🛑' };
    return <span>{map[state] || '⬜'}</span>;
}

// ──────────────────────────────────────────────────────────────────────────────
// Dynamic Input Component for ROS Message Types
// ──────────────────────────────────────────────────────────────────────────────
function DynamicValueInput({ value, onChange, topicInfo, inputStyle, labelStyle }) {
    const topicType = topicInfo?.type;

    if (!topicType) {
        return <input style={inputStyle} type="text" value={typeof value === 'object' ? JSON.stringify(value) : value} onChange={e => {
            try { onChange(JSON.parse(e.target.value)); } catch { onChange(e.target.value); }
        }} />;
    }

    if (topicType === 'std_msgs/msg/Bool') {
        return (
            <select style={{ ...inputStyle, cursor: 'pointer' }} value={value ? 'true' : 'false'} onChange={e => onChange(e.target.value === 'true')}>
                <option value="true">True</option>
                <option value="false">False</option>
            </select>
        );
    }

    if (topicType.includes('Float') || topicType.includes('Int')) {
        if (topicType.includes('MultiArray')) {
            const arr = Array.isArray(value) ? value : [];
            const arrInfo = topicInfo?.array_info;

            if (arrInfo && arrInfo.labels) {
                const len = arrInfo.length || arrInfo.labels.length;
                while (arr.length < len) arr.push(0);

                const updateNode = (idx, val) => {
                    const newArr = [...arr];
                    newArr[idx] = val;
                    onChange(newArr);
                };

                const smInp = { ...inputStyle, width: 50, padding: '4px 2px', textAlign: 'center', fontSize: '0.75em' };
                return (
                    <div style={{ display: 'flex', gap: 6, alignItems: 'center', flexWrap: 'wrap' }}>
                        {arrInfo.labels.map((lbl, i) => (
                            <div key={i} style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
                                <span style={{ ...labelStyle, margin: 0, color: '#aaa' }}>{lbl}:</span>
                                <input style={smInp} type="number" step="any" value={arr[i] || 0} onChange={e => updateNode(i, Number(e.target.value))} />
                            </div>
                        ))}
                    </div>
                );
            }

            const defaultArr = arr.length > 0 ? arr : [0];
            return (
                <input style={inputStyle} type="text" value={defaultArr.join(', ')} placeholder="1.0, 2.0"
                    onChange={e => {
                        const str = e.target.value;
                        if (str === '') { onChange([]); }
                        else { onChange(str.split(',').map(v => Number(v.trim()) || 0)); }
                    }} />
            );
        }
        return <input style={inputStyle} type="number" step="any" value={value === undefined ? 0 : value} onChange={e => onChange(e.target.value === '' ? '' : Number(e.target.value))} />;
    }

    if (topicType === 'geometry_msgs/msg/Twist') {
        const v = typeof value === 'object' && value ? value : { linear: { x: 0, y: 0, z: 0 }, angular: { x: 0, y: 0, z: 0 } };
        const update = (cat, axis, num) => onChange({ ...v, [cat]: { ...v[cat], [axis]: num } });
        const twInp = { ...inputStyle, width: 45, padding: '4px 2px', textAlign: 'center', fontSize: '0.75em' };
        return (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
                <div style={{ display: 'flex', gap: 4, alignItems: 'center' }}>
                    <span style={{ ...labelStyle, margin: 0, width: 22, color: '#aaa' }}>Lin:</span>
                    <input style={twInp} type="number" step="any" value={v.linear?.x || 0} onChange={e => update('linear', 'x', Number(e.target.value))} title="linear X" />
                    <input style={twInp} type="number" step="any" value={v.linear?.y || 0} onChange={e => update('linear', 'y', Number(e.target.value))} title="linear Y" />
                    <input style={twInp} type="number" step="any" value={v.linear?.z || 0} onChange={e => update('linear', 'z', Number(e.target.value))} title="linear Z" />
                </div>
                <div style={{ display: 'flex', gap: 4, alignItems: 'center' }}>
                    <span style={{ ...labelStyle, margin: 0, width: 22, color: '#aaa' }}>Ang:</span>
                    <input style={twInp} type="number" step="any" value={v.angular?.x || 0} onChange={e => update('angular', 'x', Number(e.target.value))} title="angular X" />
                    <input style={twInp} type="number" step="any" value={v.angular?.y || 0} onChange={e => update('angular', 'y', Number(e.target.value))} title="angular Y" />
                    <input style={twInp} type="number" step="any" value={v.angular?.z || 0} onChange={e => update('angular', 'z', Number(e.target.value))} title="angular Z" />
                </div>
            </div>
        );
    }

    // fallback string/other
    return <input style={inputStyle} type="text" value={value} onChange={e => onChange(e.target.value)} />;
}

// ──────────────────────────────────────────────────────────────────────────────
// Step editor row
// ──────────────────────────────────────────────────────────────────────────────
function StepRow({ step, index, availableTopics, onChange, onRemove, onMoveUp, onMoveDown }) {
    const inp = (field, val) => onChange(index, { ...step, [field]: val });
    const numInp = (field, val) => inp(field, val === '' ? '' : Number(val));

    const labelStyle = { color: '#888', fontSize: '0.75em', marginBottom: 2 };
    const inputStyle = {
        background: '#1a1d22', border: '1px solid #444', borderRadius: 4,
        color: '#eee', padding: '4px 8px', fontSize: '0.85em', width: '100%', boxSizing: 'border-box'
    };
    const selectStyle = { ...inputStyle, cursor: 'pointer' };

    const typeColor = { publish: '#4CAF50', wait: '#FF9800', delay: '#2196F3', loop: '#9C27B0' };

    const topicInfo = availableTopics?.find(t => t.name === step.topic);
    const topicType = topicInfo ? topicInfo.type : null;

    const handleTopicChange = (newTopic) => {
        const info = availableTopics?.find(t => t.name === newTopic);
        let defaultVal = step.value;
        if (info) {
            if (info.type === 'geometry_msgs/msg/Twist') {
                if (typeof defaultVal !== 'object') defaultVal = { linear: { x: 0, y: 0, z: 0 }, angular: { x: 0, y: 0, z: 0 } };
            } else if (info.type === 'std_msgs/msg/Bool') {
                if (typeof defaultVal !== 'boolean') defaultVal = false;
            } else if (info.type?.includes('MultiArray')) {
                if (!Array.isArray(defaultVal)) defaultVal = [0];
            } else if (info.type?.includes('Float') || info.type?.includes('Int')) {
                if (typeof defaultVal !== 'number') defaultVal = 0;
            } else {
                if (typeof defaultVal !== 'string') defaultVal = '';
            }
        }
        onChange(index, { ...step, topic: newTopic, value: defaultVal });
    };

    return (
        <div style={{
            background: '#2a2d36', borderRadius: 6, padding: '10px 14px',
            marginBottom: 8, borderLeft: `3px solid ${typeColor[step.type] || '#555'}`,
            display: 'flex', gap: 10, alignItems: 'flex-start',
        }}>
            {/* Order controls */}
            <div style={{ display: 'flex', flexDirection: 'column', gap: 2, paddingTop: 2 }}>
                <button onClick={() => onMoveUp(index)} style={btnSmall} title="↑">▲</button>
                <button onClick={() => onMoveDown(index)} style={btnSmall} title="↓">▼</button>
            </div>

            {/* Step index badge */}
            <div style={{
                background: '#444', borderRadius: 4, padding: '2px 7px',
                fontSize: '0.8em', color: '#ccc', alignSelf: 'center', minWidth: 24, textAlign: 'center',
            }}>{index + 1}</div>

            {/* Type selector */}
            <div style={{ minWidth: 90 }}>
                <div style={labelStyle}>Typ</div>
                <select style={selectStyle} value={step.type}
                    onChange={e => onChange(index, { ...emptyStep(e.target.value) })}>
                    {STEP_TYPES.map(t => <option key={t} value={t}>{t}</option>)}
                </select>
            </div>

            {/* Type-specific fields */}
            {step.type === 'publish' && <>
                <div style={{ flex: 1 }}>
                    <div style={labelStyle}>Temat (topic)</div>
                    <input list="ros-topics-list" style={inputStyle} placeholder="/servo_commands" value={step.topic}
                        onChange={e => handleTopicChange(e.target.value)} />
                    {topicType && <div style={{ fontSize: '0.65em', color: '#666', marginTop: 2 }}>{topicType}</div>}
                </div>
                <div style={{ minWidth: 90 }}>
                    <div style={labelStyle}>Akcja</div>
                    <select style={selectStyle} value={step.operation || '='}
                        onChange={e => inp('operation', e.target.value)}>
                        <option value="=">Ustaw (=)</option>
                        {topicType !== 'std_msgs/msg/Bool' && <option value="+=">Dodaj (+)</option>}
                        {topicType !== 'std_msgs/msg/Bool' && <option value="-=">Odejmij (-)</option>}
                        {topicType === 'std_msgs/msg/Bool' && <option value="!">Przełącz (!)</option>}
                    </select>
                </div>
                {step.operation !== '!' && (
                    <div style={{ minWidth: 100 }}>
                        <div style={labelStyle}>Wartość</div>
                        <DynamicValueInput value={step.value} onChange={v => inp('value', v)} topicInfo={topicInfo} inputStyle={inputStyle} labelStyle={labelStyle} />
                    </div>
                )}
                <div style={{ minWidth: 60, display: 'flex', flexDirection: 'column', alignItems: 'center' }}>
                    <div style={labelStyle}>W tle</div>
                    <input type="checkbox" checked={step.run_in_background || false} onChange={e => inp('run_in_background', e.target.checked)} style={{ marginTop: 5, cursor: 'pointer' }} />
                </div>
                <div style={{ minWidth: 60 }}>
                    <div style={labelStyle}>Interwał (s)</div>
                    <input type="number" step="0.1" style={inputStyle} min={0} value={step.interval_s ?? 0} onChange={e => inp('interval_s', parseFloat(e.target.value) || 0)} />
                </div>
            </>}

            {step.type === 'wait' && <>
                <div style={{ flex: 1 }}>
                    <div style={labelStyle}>Temat (topic)</div>
                    <input list="ros-topics-list" style={inputStyle} placeholder="/status_topic" value={step.topic}
                        onChange={e => handleTopicChange(e.target.value)} />
                    {topicType && <div style={{ fontSize: '0.65em', color: '#666', marginTop: 2 }}>{topicType}</div>}
                </div>
                <div style={{ minWidth: 155 }}>
                    <div style={labelStyle}>Warunek</div>
                    <select style={selectStyle} value={step.condition}
                        onChange={e => inp('condition', e.target.value)}>
                        {CONDITIONS.map(c => <option key={c.value} value={c.value}>{c.label}</option>)}
                    </select>
                </div>
                <div style={{ minWidth: 85 }}>
                    <div style={labelStyle}>Wartość ref.</div>
                    <DynamicValueInput value={step.value} onChange={v => inp('value', v)} topicInfo={topicInfo} inputStyle={inputStyle} labelStyle={labelStyle} />
                </div>
                <div style={{ minWidth: 75 }}>
                    <div style={labelStyle}>Timeout (s)</div>
                    <input style={inputStyle} type="number" min={1} value={step.timeout_s}
                        onChange={e => numInp('timeout_s', e.target.value)} />
                </div>
            </>}

            {step.type === 'delay' && <>
                <div style={{ minWidth: 110 }}>
                    <div style={labelStyle}>Czas (s)</div>
                    <input style={inputStyle} type="number" min={0.1} step={0.1} value={step.seconds}
                        onChange={e => numInp('seconds', e.target.value)} />
                </div>
            </>}

            {step.type === 'loop' && <>
                <div style={{ minWidth: 140 }}>
                    <div style={labelStyle}>Wroc do kroku #</div>
                    <input
                        style={inputStyle}
                        type="number"
                        min={1}
                        max={Math.max(1, index)}
                        value={step.loop_to ?? 1}
                        onChange={e => numInp('loop_to', e.target.value)}
                    />
                </div>
                <div style={{ minWidth: 120 }}>
                    <div style={labelStyle}>Powtorz (razy)</div>
                    <input
                        style={inputStyle}
                        type="number"
                        min={1}
                        value={step.repeat ?? 2}
                        disabled={!!step.infinite}
                        onChange={e => numInp('repeat', e.target.value)}
                    />
                </div>
                <div style={{ minWidth: 140, display: 'flex', flexDirection: 'column', justifyContent: 'center' }}>
                    <label style={{ ...labelStyle, display: 'flex', alignItems: 'center', gap: 6, marginBottom: 0 }}>
                        <input
                            type="checkbox"
                            checked={!!step.infinite}
                            onChange={e => inp('infinite', e.target.checked)}
                            style={{ cursor: 'pointer' }}
                        />
                        Nieskonczona
                    </label>
                </div>
                <div style={{ minWidth: 250, color: '#9b9b9b', fontSize: '0.78em', paddingTop: 20 }}>
                    Po tym kroku sekwencja skoczy do wskazanego kroku i wykona petle.
                </div>
            </>}

            {/* Remove */}
            <button onClick={() => onRemove(index)}
                style={{ ...btnSmall, background: '#5a1a1a', color: '#ff8888', alignSelf: 'center', marginLeft: 'auto' }}>✕</button>

            {/* Datalist for autocomplete */}
            <datalist id="ros-topics-list">
                {availableTopics?.map(t => <option key={t.name} value={t.name}>{t.type}</option>)}
            </datalist>
        </div>
    );
}

const btnSmall = {
    background: '#333', border: 'none', borderRadius: 3, color: '#ccc',
    cursor: 'pointer', fontSize: '0.7em', padding: '2px 5px', lineHeight: 1.5,
};

// ──────────────────────────────────────────────────────────────────────────────
// Sequence editor modal
// ──────────────────────────────────────────────────────────────────────────────
function SequenceEditor({ seq, availableTopics, onSave, onClose }) {
    const [name, setName] = useState(seq.name || '');
    const [steps, setSteps] = useState(seq.steps || []);

    const changeStep = (idx, newStep) => setSteps(s => s.map((x, i) => i === idx ? newStep : x));
    const removeStep = (idx) => setSteps(s => s.filter((_, i) => i !== idx));
    const moveUp = (idx) => {
        if (idx === 0) return;
        setSteps(s => { const a = [...s];[a[idx - 1], a[idx]] = [a[idx], a[idx - 1]]; return a; });
    };
    const moveDown = (idx) => {
        setSteps(s => {
            if (idx >= s.length - 1) return s;
            const a = [...s];[a[idx], a[idx + 1]] = [a[idx + 1], a[idx]]; return a;
        });
    };
    const addStep = (type) => setSteps(s => [...s, emptyStep(type)]);

    const overlay = {
        position: 'fixed', inset: 0, background: 'rgba(0,0,0,.75)', zIndex: 1000,
        display: 'flex', alignItems: 'center', justifyContent: 'center',
    };
    const modal = {
        background: '#1e2128', borderRadius: 10, padding: 24, width: 820,
        maxWidth: '95vw', maxHeight: '90vh', display: 'flex', flexDirection: 'column',
        boxShadow: '0 8px 40px rgba(0,0,0,.6)',
    };
    const btn = (color) => ({
        background: color, border: 'none', borderRadius: 5, color: '#fff',
        cursor: 'pointer', padding: '7px 18px', fontSize: '0.9em',
    });

    return (
        <div style={overlay} onClick={(e) => e.target === e.currentTarget && onClose()}>
            <div style={modal}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
                    <h3 style={{ margin: 0, color: '#eee' }}>✏️ Edytor sekwencji</h3>
                    <button onClick={onClose} style={{ ...btn('#333'), padding: '4px 10px' }}>✕</button>
                </div>

                {/* Name */}
                <div style={{ marginBottom: 14 }}>
                    <label style={{ color: '#888', fontSize: '0.8em' }}>Nazwa sekwencji</label>
                    <input
                        value={name} onChange={e => setName(e.target.value)}
                        style={{
                            display: 'block', width: '100%', marginTop: 4,
                            background: '#252830', border: '1px solid #444', borderRadius: 5,
                            color: '#eee', padding: '6px 10px', fontSize: '1em', boxSizing: 'border-box',
                        }}
                    />
                </div>

                {/* Steps list */}
                <div style={{ flex: 1, overflowY: 'auto', marginBottom: 12 }}>
                    {steps.length === 0 && (
                        <div style={{ textAlign: 'center', color: '#555', padding: 30 }}>
                            Brak kroków — dodaj krok poniżej
                        </div>
                    )}
                    {steps.map((s, i) => (
                        <StepRow key={i} step={s} index={i} availableTopics={availableTopics}
                            onChange={changeStep} onRemove={removeStep}
                            onMoveUp={moveUp} onMoveDown={moveDown} />
                    ))}
                </div>

                {/* Add step buttons */}
                <div style={{ display: 'flex', gap: 8, marginBottom: 16, flexWrap: 'wrap' }}>
                    <span style={{ color: '#888', fontSize: '0.85em', alignSelf: 'center' }}>+ Dodaj krok:</span>
                    <button onClick={() => addStep('publish')} style={{ ...btn('#2e5a3a') }}>📤 Publish</button>
                    <button onClick={() => addStep('wait')} style={{ ...btn('#5a4010') }}>⏳ Wait</button>
                    <button onClick={() => addStep('delay')} style={{ ...btn('#1a3a5a') }}>💤 Delay</button>
                    <button onClick={() => addStep('loop')} style={{ ...btn('#4b2666') }}>🔁 Loop</button>
                </div>

                {/* Footer actions */}
                <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 10 }}>
                    <button onClick={onClose} style={btn('#333')}>Anuluj</button>
                    <button onClick={() => onSave({ ...seq, name, steps })} style={btn('#4CAF50')}>💾 Zapisz</button>
                </div>
            </div>
        </div>
    );
}

// ──────────────────────────────────────────────────────────────────────────────
// Run status panel
// ──────────────────────────────────────────────────────────────────────────────
function RunStatus({ run, onStop, onDismiss }) {
    if (!run) return null;

    const statusColor = {
        running: '#FF9800', done: '#4CAF50', error: '#f44336', stopped: '#888',
    };

    const card = {
        background: '#1e2128', borderRadius: 8, padding: '14px 18px',
        border: `1px solid ${statusColor[run.status] || '#444'}`,
        marginBottom: 12,
    };

    return (
        <div style={card}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 10 }}>
                <strong style={{ color: statusColor[run.status] }}>
                    {run.status === 'running' ? '⏳ Uruchomiona' :
                        run.status === 'done' ? '✅ Zakończona' :
                            run.status === 'error' ? '❌ Błąd' : '🛑 Zatrzymana'}
                </strong>
                <div style={{ display: 'flex', gap: 6 }}>
                    {run.status === 'running' && (
                        <button onClick={onStop} style={{
                            background: '#5a1a1a', border: 'none', borderRadius: 4, color: '#ff8888',
                            cursor: 'pointer', padding: '4px 12px', fontSize: '0.85em',
                        }}>⏹ Stop</button>
                    )}
                    {run.status !== 'running' && (
                        <button onClick={onDismiss} style={{
                            background: '#333', border: 'none', borderRadius: 4, color: '#aaa',
                            cursor: 'pointer', padding: '4px 10px', fontSize: '0.85em',
                        }}>✕</button>
                    )}
                </div>
            </div>

            {/* Step progress */}
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 5 }}>
                {run.step_states.map((state, i) => (
                    <div key={i} style={{
                        background: '#2a2d36', borderRadius: 4, padding: '3px 8px',
                        fontSize: '0.8em', color: '#ccc', display: 'flex', gap: 4, alignItems: 'center',
                    }}>
                        <StepIcon state={state} />
                        <span>#{i + 1}</span>
                    </div>
                ))}
            </div>

            {/* Message */}
            {run.message && (
                <div style={{ marginTop: 8, fontSize: '0.8em', color: run.status === 'error' ? '#ff8888' : '#888' }}>
                    {run.message}
                </div>
            )}
        </div>
    );
}

// ──────────────────────────────────────────────────────────────────────────────
// Main SequencesPanel component
// ──────────────────────────────────────────────────────────────────────────────
export default function SequencesPanel() {
    const [sequences, setSequences] = useState([]);
    const [availableTopics, setAvailableTopics] = useState([]);
    const [editingSeq, setEditingSeq] = useState(null);   // null | sequence object
    const [activeRun, setActiveRun] = useState(null);     // null | run status object
    const pollRef = useRef(null);

    // Load saved sequences
    const loadSequences = useCallback(async () => {
        try {
            const res = await fetch(`${BACKEND_URL}/science/sequences`);
            if (res.ok) setSequences((await res.json()).sequences || []);
        } catch (e) { /* ignore */ }
    }, []);

    useEffect(() => { loadSequences(); }, [loadSequences]);

    // Load available topics for dropdown autocomplete
    const loadTopics = useCallback(async () => {
        try {
            const res = await fetch(`${BACKEND_URL}/ros2/topics`);
            if (res.ok) setAvailableTopics((await res.json()).topics || []);
        } catch (e) { /* ignore */ }
    }, []);

    useEffect(() => { loadTopics(); }, [loadTopics]);

    // Poll run status while running
    useEffect(() => {
        if (!activeRun || activeRun.status !== 'running') {
            if (pollRef.current) clearInterval(pollRef.current);
            return;
        }
        pollRef.current = setInterval(async () => {
            try {
                const res = await fetch(`${BACKEND_URL}/science/sequence/status/${activeRun.run_id}`);
                if (res.ok) {
                    const status = await res.json();
                    setActiveRun(status);
                    if (status.status !== 'running') clearInterval(pollRef.current);
                }
            } catch (e) { /* ignore */ }
        }, 300);
        return () => clearInterval(pollRef.current);
    }, [activeRun]);

    const saveSeq = async (seq) => {
        await fetch(`${BACKEND_URL}/science/sequences`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(seq),
        });
        setEditingSeq(null);
        loadSequences();
    };

    const deleteSeq = async (id) => {
        if (!confirm('Usunąć sekwencję?')) return;
        await fetch(`${BACKEND_URL}/science/sequences/${id}`, { method: 'DELETE' });
        loadSequences();
    };

    const runSeq = async (seq) => {
        try {
            const res = await fetch(`${BACKEND_URL}/science/sequence/run`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ steps: seq.steps }),
            });
            if (res.ok) {
                const { run_id } = await res.json();
                setActiveRun({
                    run_id, status: 'running',
                    current_step: 0, total_steps: seq.steps.length,
                    step_states: seq.steps.map(() => 'pending'),
                    message: '',
                });
            }
        } catch (e) { alert('Błąd uruchamiania sekwencji: ' + e.message); }
    };

    const stopRun = async () => {
        if (!activeRun) return;
        await fetch(`${BACKEND_URL}/science/sequence/stop/${activeRun.run_id}`, { method: 'POST' });
    };

    // ── Styles ──
    const sectionStyle = {
        background: '#1a1d22', borderRadius: 8, padding: '16px 20px', marginTop: 16,
    };
    const headerStyle = {
        display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 14,
    };
    const btnPrimary = {
        background: '#4CAF50', border: 'none', borderRadius: 5, color: '#fff',
        cursor: 'pointer', padding: '6px 14px', fontSize: '0.85em',
    };

    return (
        <div style={sectionStyle}>
            <div style={headerStyle}>
                <h3 style={{ margin: 0, color: '#eee', fontSize: '1em', display: 'flex', alignItems: 'center', gap: 8 }}>
                    🎬 Sekwencje automatyzacji
                </h3>
                <button style={btnPrimary} onClick={() => setEditingSeq(emptySeq())}>
                    + Nowa sekwencja
                </button>
            </div>

            {/* Active run status */}
            <RunStatus
                run={activeRun}
                onStop={stopRun}
                onDismiss={() => setActiveRun(null)}
            />

            {/* Sequences list */}
            {sequences.length === 0 ? (
                <div style={{ color: '#555', textAlign: 'center', padding: 20 }}>
                    Brak zapisanych sekwencji
                </div>
            ) : (
                <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                    {sequences.map(seq => (
                        <div key={seq.id} style={{
                            background: '#252830', borderRadius: 6, padding: '10px 14px',
                            display: 'flex', justifyContent: 'space-between', alignItems: 'center',
                        }}>
                            <div>
                                <div style={{ color: '#eee', fontWeight: 500 }}>{seq.name || '(bez nazwy)'}</div>
                                <div style={{ color: '#666', fontSize: '0.8em', marginTop: 2 }}>
                                    {seq.steps?.length || 0} kroków
                                    {seq.steps && seq.steps.map((s, i) => (
                                        <span key={i} style={{
                                            marginLeft: 6, background: '#333', borderRadius: 3,
                                            padding: '1px 5px', fontSize: '0.9em',
                                            color: s.type === 'publish' ? '#4CAF50' : s.type === 'wait' ? '#FF9800' : '#2196F3',
                                        }}>{s.type}</span>
                                    ))}
                                </div>
                            </div>
                            <div style={{ display: 'flex', gap: 6 }}>
                                <button
                                    onClick={() => runSeq(seq)}
                                    disabled={activeRun?.status === 'running'}
                                    style={{
                                        background: activeRun?.status === 'running' ? '#333' : '#2e5a3a',
                                        border: 'none', borderRadius: 4, color: activeRun?.status === 'running' ? '#666' : '#4CAF50',
                                        cursor: activeRun?.status === 'running' ? 'not-allowed' : 'pointer',
                                        padding: '5px 12px', fontSize: '0.85em',
                                    }}>
                                    ▶ Uruchom
                                </button>
                                <button onClick={() => setEditingSeq(seq)} style={{
                                    background: '#333', border: 'none', borderRadius: 4, color: '#aaa',
                                    cursor: 'pointer', padding: '5px 10px', fontSize: '0.85em',
                                }}>✏️</button>
                                <button onClick={() => deleteSeq(seq.id)} style={{
                                    background: '#3a1a1a', border: 'none', borderRadius: 4, color: '#f44336',
                                    cursor: 'pointer', padding: '5px 10px', fontSize: '0.85em',
                                }}>🗑</button>
                            </div>
                        </div>
                    ))}
                </div>
            )}

            {/* Editor modal */}
            {editingSeq && (
                <SequenceEditor
                    seq={editingSeq}
                    availableTopics={availableTopics}
                    onSave={saveSeq}
                    onClose={() => setEditingSeq(null)}
                />
            )}
        </div>
    );
}
