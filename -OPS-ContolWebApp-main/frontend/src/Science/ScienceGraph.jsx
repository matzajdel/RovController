import React, { useRef, useEffect, useState, useCallback } from 'react';

/**
 * ScienceGraph - A Canvas-based graph component for visualizing ROS topic data
 * 
 * Props:
 * - data: Array of {timestamp, value} where value can be number or array
 * - title: Graph title
 * - labels: Array of labels for each data series (for array values)
 * - maxPoints: Number of points to display (1 = single value mode)
 * - width: Component width (auto-calculated from container if not set)
 * - height: Component height (default 200)
 * - colors: Optional array of colors for each series
 * - showLegend: Whether to show the legend (default true for arrays)
 */
const ScienceGraph = ({
    data = [],
    title = '',
    labels = [],
    maxPoints = 50,
    height = 200,
    colors = null,
    showLegend = true,
    isEditMode = false,
    onRemove = null,
    onSettings = null
}) => {
    const canvasRef = useRef(null);
    const containerRef = useRef(null);
    const [dimensions, setDimensions] = useState({ width: 300, height });

    // Default color palette
    const defaultColors = [
        '#4CAF50', '#2196F3', '#FF9800', '#E91E63', '#9C27B0',
        '#00BCD4', '#FFEB3B', '#795548', '#607D8B', '#F44336'
    ];

    // Resize observer
    useEffect(() => {
        if (!containerRef.current) return;

        const resizeObserver = new ResizeObserver(entries => {
            for (const entry of entries) {
                setDimensions({
                    width: entry.contentRect.width,
                    height
                });
            }
        });

        resizeObserver.observe(containerRef.current);
        return () => resizeObserver.disconnect();
    }, [height]);

    // Determine if data is multi-series (array values)
    const isMultiSeries = data.length > 0 && Array.isArray(data[0]?.value);
    const seriesCount = isMultiSeries && data.length > 0 ? data[0].value.length : 1;
    const seriesColors = colors || defaultColors.slice(0, seriesCount);

    // Get series labels
    const seriesLabels = isMultiSeries
        ? Array.from({ length: seriesCount }, (_, i) => {
            const configured = labels[i];
            return (typeof configured === 'string' && configured.trim() !== '')
                ? configured.trim()
                : `Series ${i}`;
        })
        : ['Value'];

    // Extract value at index for multi-series, or direct value for single series
    const getValue = useCallback((point, seriesIndex = 0) => {
        if (!point || point.value === undefined) return null;
        if (Array.isArray(point.value)) {
            return point.value[seriesIndex] ?? null;
        }
        return seriesIndex === 0 ? point.value : null;
    }, []);

    // Calculate min/max for auto-scaling
    const getMinMax = useCallback(() => {
        let min = Infinity;
        let max = -Infinity;

        data.forEach(point => {
            for (let s = 0; s < seriesCount; s++) {
                const val = getValue(point, s);
                if (val !== null && typeof val === 'number' && !isNaN(val)) {
                    min = Math.min(min, val);
                    max = Math.max(max, val);
                }
            }
        });

        if (min === Infinity) min = 0;
        if (max === -Infinity) max = 1;
        if (min === max) {
            min -= 0.5;
            max += 0.5;
        }

        // Add 10% padding
        const range = max - min;
        min -= range * 0.1;
        max += range * 0.1;

        return { min, max };
    }, [data, seriesCount, getValue]);

    // Determine if we are in single-value mode (must be computed before any early return)
    // Only maxPoints===1 triggers single-value display; data.length is irrelevant
    const isSingleValue = maxPoints === 1;

    // Canvas drawing effect — must be declared before any conditional return
    // (React Rules of Hooks: hooks must always be called in the same order)
    useEffect(() => {
        // Skip canvas drawing in single-value mode OR when not enough data
        if (isSingleValue || data.length < 2) return;

        const canvas = canvasRef.current;
        if (!canvas) return;

        const ctx = canvas.getContext('2d');
        const { width } = dimensions;
        const graphHeight = height - 40; // Leave room for title
        const padding = { top: 10, right: 10, bottom: 25, left: 50 };
        const graphWidth = width - padding.left - padding.right;
        const graphAreaHeight = graphHeight - padding.top - padding.bottom;

        // Clear canvas
        ctx.fillStyle = '#252830';
        ctx.fillRect(0, 0, width, graphHeight);

        if (data.length < 2) {
            ctx.fillStyle = '#555';
            ctx.font = '14px sans-serif';
            ctx.textAlign = 'center';
            ctx.fillText('Collecting data...', width / 2, graphHeight / 2);
            return;
        }

        const { min, max } = getMinMax();

        // Draw grid lines
        ctx.strokeStyle = '#3a3f45';
        ctx.lineWidth = 1;
        ctx.beginPath();

        // Horizontal grid lines (5 lines)
        for (let i = 0; i <= 4; i++) {
            const y = padding.top + (graphAreaHeight * i) / 4;
            ctx.moveTo(padding.left, y);
            ctx.lineTo(width - padding.right, y);
        }
        ctx.stroke();

        // Draw Y-axis labels
        ctx.fillStyle = '#888';
        ctx.font = '10px sans-serif';
        ctx.textAlign = 'right';
        for (let i = 0; i <= 4; i++) {
            const y = padding.top + (graphAreaHeight * i) / 4;
            const value = max - ((max - min) * i) / 4;
            ctx.fillText(value.toFixed(1), padding.left - 5, y + 3);
        }

        // Draw each series
        for (let s = 0; s < seriesCount; s++) {
            ctx.strokeStyle = seriesColors[s % seriesColors.length];
            ctx.lineWidth = 2;
            ctx.beginPath();

            let started = false;
            let validPoints = 0;
            data.forEach((point, i) => {
                const val = getValue(point, s);
                if (val === null || typeof val !== 'number' || isNaN(val)) return;

                const x = padding.left + (i / (data.length - 1)) * graphWidth;
                const y = padding.top + graphAreaHeight - ((val - min) / (max - min)) * graphAreaHeight;

                if (!started) {
                    ctx.moveTo(x, y);
                    started = true;
                } else {
                    ctx.lineTo(x, y);
                }
                validPoints++;
            });

            if (validPoints > 0) {
                ctx.stroke();
            }
        }

        // Draw X-axis time labels
        if (data.length > 1) {
            ctx.fillStyle = '#666';
            ctx.font = '9px sans-serif';
            ctx.textAlign = 'center';

            const firstTime = new Date(data[0].timestamp);
            const lastTime = new Date(data[data.length - 1].timestamp);

            ctx.fillText(firstTime.toLocaleTimeString(), padding.left, graphHeight - 5);
            ctx.fillText(lastTime.toLocaleTimeString(), width - padding.right, graphHeight - 5);
        }
    }, [data, dimensions, height, isSingleValue, getMinMax, seriesCount, seriesColors, getValue]);

    // Single value mode — display large numeric value
    if (isSingleValue) {
        const latestValue = data.length > 0 ? data[data.length - 1]?.value : null;
        const timestamp = data.length > 0 ? data[data.length - 1]?.timestamp : '';

        return (
            <div
                ref={containerRef}
                style={{
                    backgroundColor: '#252830',
                    borderRadius: '8px',
                    padding: '15px',
                    height: '100%',
                    display: 'flex',
                    flexDirection: 'column',
                    position: 'relative'
                }}
            >
                {/* Title */}
                {title && (
                    <div style={{
                        fontSize: '0.9em',
                        color: '#888',
                        marginBottom: '10px',
                        display: 'flex',
                        justifyContent: 'space-between',
                        alignItems: 'center'
                    }}>
                        <span>{title}</span>
                        {isEditMode && (
                            <div style={{ display: 'flex', gap: '5px' }}>
                                {onSettings && (
                                    <button
                                        onClick={onSettings}
                                        style={{ background: 'none', border: 'none', color: '#888', cursor: 'pointer', fontSize: '1em' }}
                                    >⚙</button>
                                )}
                                {onRemove && (
                                    <button
                                        onClick={onRemove}
                                        style={{ background: 'none', border: 'none', color: '#f44336', cursor: 'pointer', fontSize: '1em' }}
                                    >✕</button>
                                )}
                            </div>
                        )}
                    </div>
                )}

                {/* Value Display */}
                <div style={{
                    flex: 1,
                    display: 'flex',
                    flexDirection: 'column',
                    justifyContent: 'center',
                    alignItems: 'center'
                }}>
                    {latestValue === null ? (
                        <span style={{ color: '#555', fontSize: '1.2em' }}>Waiting for data...</span>
                    ) : isMultiSeries ? (
                        <div style={{ display: 'flex', flexWrap: 'wrap', gap: '15px', justifyContent: 'center' }}>
                            {latestValue.map((val, i) => (
                                <div key={i} style={{ textAlign: 'center' }}>
                                    <div style={{
                                        fontSize: '2em',
                                        fontWeight: 'bold',
                                        color: seriesColors[i % seriesColors.length]
                                    }}>
                                        {typeof val === 'number' ? val.toFixed(2) : String(val)}
                                    </div>
                                    <div style={{ fontSize: '0.8em', color: '#888' }}>
                                        {seriesLabels[i] || `[${i}]`}
                                    </div>
                                </div>
                            ))}
                        </div>
                    ) : (
                        <div style={{
                            fontSize: '3em',
                            fontWeight: 'bold',
                            color: '#4CAF50'
                        }}>
                            {typeof latestValue === 'number' ? latestValue.toFixed(2) : String(latestValue)}
                        </div>
                    )}
                </div>

                {/* Timestamp */}
                {timestamp && (
                    <div style={{ fontSize: '0.7em', color: '#555', textAlign: 'center', marginTop: '5px' }}>
                        {new Date(timestamp).toLocaleTimeString()}
                    </div>
                )}
            </div>
        );
    }


    return (
        <div
            ref={containerRef}
            style={{
                backgroundColor: '#252830',
                borderRadius: '8px',
                padding: '10px',
                position: 'relative'
            }}
        >
            {/* Title and controls */}
            <div style={{
                display: 'flex',
                justifyContent: 'space-between',
                alignItems: 'center',
                marginBottom: '5px'
            }}>
                <span style={{ fontSize: '0.9em', color: '#888' }}>{title || 'Graph'}</span>
                <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                    {/* Legend */}
                    {showLegend && isMultiSeries && (
                        <div style={{ display: 'flex', gap: '8px', fontSize: '0.75em' }}>
                            {seriesLabels.slice(0, seriesCount).map((label, i) => (
                                <span key={i} style={{ display: 'flex', alignItems: 'center', gap: '3px' }}>
                                    <span style={{
                                        width: '10px',
                                        height: '3px',
                                        backgroundColor: seriesColors[i % seriesColors.length],
                                        display: 'inline-block'
                                    }} />
                                    <span style={{ color: '#888' }}>{label}</span>
                                </span>
                            ))}
                        </div>
                    )}
                    {isEditMode && (
                        <div style={{ display: 'flex', gap: '5px' }}>
                            {onSettings && (
                                <button
                                    onClick={onSettings}
                                    style={{ background: 'none', border: 'none', color: '#888', cursor: 'pointer' }}
                                >⚙</button>
                            )}
                            {onRemove && (
                                <button
                                    onClick={onRemove}
                                    style={{ background: 'none', border: 'none', color: '#f44336', cursor: 'pointer' }}
                                >✕</button>
                            )}
                        </div>
                    )}
                </div>
            </div>

            {/* Canvas */}
            <canvas
                ref={canvasRef}
                width={dimensions.width - 20}
                height={height - 40}
                style={{ display: 'block', width: '100%' }}
            />
        </div>
    );
};

export default ScienceGraph;
