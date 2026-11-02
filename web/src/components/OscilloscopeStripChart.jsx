import React, { useState, useEffect, useRef } from 'react';
import { Play, Pause, Trash2, Download, Flame, Activity } from 'lucide-react';

/**
 * Real-Time Rolling Strip Chart Graph (Oscilloscope Widget)
 * Exact parity with SPECTRA's GTK OscilloscopeWidget (gui_widgets.py):
 * - X Axis: Time (-50s, -40s, -30s, -20s, -10s, Now)
 * - Y Axis: Temperature in °C (20°C to 160°C) with grid lines (20, 60, 90, 110, 140, 160°C)
 * - Nominal brew target band (90°C - 95°C) shaded
 * - Thermoblock 1 (Coffee) Temperature in °C (Pink / Theme Primary)
 * - Thermoblock 2 (Steam) Temperature in °C (Orange)
 * - Water Flow Rate in ml/s (Cyan dashed curve, scaled in bottom 40%)
 * - Real-time value dots at right margin ('Now')
 * - Top Legend HUD: ■ TB1: xx.x°C   ■ TB2: xx.x°C   ■ Flow: x.x ml/s
 */
export default function OscilloscopeStripChart({
  theme,
  liveData,
  maxSamples = 60,
}) {
  const [tb1Data, setTb1Data] = useState([]);
  const [tb2Data, setTb2Data] = useState([]);
  const [flowData, setFlowData] = useState([]);
  const [isPaused, setIsPaused] = useState(false);

  const canvasRef = useRef(null);

  // Extract latest readings
  const telem = liveData?.telemetry || {};
  const currentTb1 = telem.heater_coffee_c != null ? Number(telem.heater_coffee_c) : null;
  const currentTb2 = telem.heater_steam_c != null ? Number(telem.heater_steam_c) : null;
  const currentFlow = telem.flow_rate_ml_s != null ? Number(telem.flow_rate_ml_s) : 0.0;
  const hasTb2 = telem.is_dual_heater ?? false;

  // Append new sample on each liveData update
  useEffect(() => {
    if (isPaused || currentTb1 === null) return;

    setTb1Data((prev) => {
      const next = [...prev, currentTb1];
      return next.length > maxSamples ? next.slice(next.length - maxSamples) : next;
    });

    setTb2Data((prev) => {
      const next = [...prev, currentTb2];
      return next.length > maxSamples ? next.slice(next.length - maxSamples) : next;
    });

    setFlowData((prev) => {
      const next = [...prev, currentFlow];
      return next.length > maxSamples ? next.slice(next.length - maxSamples) : next;
    });
  }, [liveData, isPaused, currentTb1, currentTb2, currentFlow, maxSamples]);

  // Clear buffers
  const handleClear = () => {
    setTb1Data([]);
    setTb2Data([]);
    setFlowData([]);
  };

  // Export CSV
  const handleExportCSV = () => {
    if (tb1Data.length === 0) return;
    const header = 'Sample_Index,Time_Seconds_Ago,TB1_Coffee_C,TB2_Steam_C,Flow_Rate_ml_s\n';
    const rows = tb1Data
      .map((t1, i) => {
        const secAgo = tb1Data.length - 1 - i;
        const t2 = tb2Data[i] ?? '';
        const fl = flowData[i] ?? 0;
        return `${i},-${secAgo}s,${t1},${t2},${fl}`;
      })
      .join('\n');

    const blob = new Blob([header + rows], { type: 'text/csv;charset=utf-8;' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `spectra_stripchart_${new Date().toISOString().replace(/[:.]/g, '-')}.csv`;
    a.click();
    URL.revokeObjectURL(url);
  };

  // High-DPI Canvas Rendering matching gui_widgets.py OscilloscopeWidget
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');

    const dpr = window.devicePixelRatio || 1;
    const rect = canvas.getBoundingClientRect();
    const w = rect.width;
    const h = rect.height;

    canvas.width = w * dpr;
    canvas.height = h * dpr;
    ctx.scale(dpr, dpr);

    // Background
    ctx.fillStyle = theme.canvasBg || '#070B10';
    ctx.fillRect(0, 0, w, h);

    // Inner plot area bounds (matching GTK OscilloscopeWidget)
    const padLeft = 46;
    const padRight = 20;
    const padTop = 26;
    const padBottom = 26;
    const plotW = Math.max(10, w - padLeft - padRight);
    const plotH = Math.max(10, h - padTop - padBottom);

    // Temperature range: 20.0°C to 160.0°C
    const tempMin = 20.0;
    const tempMax = 160.0;

    // Horizontal Grid Lines & Labels: 20°C, 60°C, 90°C, 110°C, 140°C, 160°C
    const tempSteps = [20, 60, 90, 110, 140, 160];

    // Shaded nominal brew target band (90°C - 95°C)
    const brewY1 = padTop + (1.0 - (95 - tempMin) / (tempMax - tempMin)) * plotH;
    const brewY2 = padTop + (1.0 - (90 - tempMin) / (tempMax - tempMin)) * plotH;
    ctx.fillStyle = 'rgba(16, 185, 129, 0.12)';
    ctx.fillRect(padLeft, brewY1, plotW, brewY2 - brewY1);

    ctx.font = '9.5px monospace';
    ctx.textAlign = 'right';
    ctx.textBaseline = 'middle';

    tempSteps.forEach((tVal) => {
      const normY = 1.0 - (tVal - tempMin) / (tempMax - tempMin);
      const gy = padTop + normY * plotH;

      ctx.strokeStyle = tVal === 90 ? 'rgba(16, 185, 129, 0.4)' : (theme.gridColor || 'rgba(255,255,255,0.08)');
      ctx.lineWidth = tVal === 90 ? 1.5 : 1;
      ctx.beginPath();
      ctx.moveTo(padLeft, gy);
      ctx.lineTo(padLeft + plotW, gy);
      ctx.stroke();

      ctx.fillStyle = tVal === 90 ? '#10B981' : (theme.textMuted || '#6c7086');
      ctx.fillText(`${tVal}°C`, padLeft - 6, gy);
    });

    // Vertical Time Grid Lines (-50s, -40s, -30s, -20s, -10s, Now)
    const timeLabels = ['-50s', '-40s', '-30s', '-20s', '-10s', 'Now'];
    ctx.textAlign = 'center';
    ctx.font = '9.5px monospace';
    timeLabels.forEach((label, i) => {
      const gx = padLeft + (i / 5.0) * plotW;

      ctx.strokeStyle = theme.gridColor || 'rgba(255,255,255,0.08)';
      ctx.lineWidth = 1;
      ctx.beginPath();
      ctx.moveTo(gx, padTop);
      ctx.lineTo(gx, padTop + plotH);
      ctx.stroke();

      ctx.fillStyle = label === 'Now' ? (theme.textPrimary || '#FCEE09') : (theme.textMuted || '#6c7086');
      ctx.fillText(label, gx, h - 10);
    });

    // Helper functions matching gui_widgets.py pt_x, pt_y_temp, pt_y_flow
    const nPts = tb1Data.length;

    // Empty state
    if (nPts === 0) {
      // Empty HUD Header
      ctx.textAlign = 'left';
      ctx.font = 'bold 10px monospace';
      ctx.fillStyle = '#f38ba8';
      ctx.fillText('■ TB1: ---', padLeft, 14);

      ctx.fillStyle = '#fab387';
      ctx.fillText('■ TB2: ---', padLeft + 110, 14);

      ctx.fillStyle = '#74c7ec';
      ctx.fillText('■ Flow: ---', padLeft + 220, 14);

      // Center Prompt
      ctx.textAlign = 'center';
      ctx.fillStyle = theme.textMuted || '#6c7086';
      ctx.font = '11px monospace';
      ctx.fillText('Awaiting live telemetry stream...', padLeft + plotW / 2, padTop + plotH / 2);
      return;
    }

    // Map sample index to X position so latest sample is at 'Now' (right edge)
    const ptX = (idx) => {
      const total = Math.max(2, maxSamples);
      if (nPts >= total) {
        return padLeft + (idx / (total - 1)) * plotW;
      } else {
        // Build progressively from left to right as samples arrive
        return padLeft + (idx / (total - 1)) * plotW;
      }
    };

    const ptYTemp = (t) => {
      const clamped = Math.max(tempMin, Math.min(tempMax, t));
      const norm = 1.0 - (clamped - tempMin) / (tempMax - tempMin);
      return padTop + norm * plotH;
    };

    const ptYFlow = (fl) => {
      const clamped = Math.max(0.0, Math.min(10.0, fl));
      const norm = 1.0 - (clamped / 10.0) * 0.35;
      return padTop + norm * plotH;
    };

    // 1. Water Flow Rate Curve (Cyan / Dashed)
    if (flowData.length > 0) {
      ctx.strokeStyle = '#74c7ec'; // #74c7ec Cyan
      ctx.lineWidth = 1.8;
      ctx.setLineDash([4, 2]);
      ctx.beginPath();
      flowData.forEach((fl, idx) => {
        const x = ptX(idx);
        const y = ptYFlow(fl);
        if (idx === 0) ctx.moveTo(x, y);
        else ctx.lineTo(x, y);
      });
      ctx.stroke();
      ctx.setLineDash([]);
    }

    // 2. TB2 Steam Boiler Curve (Orange) - only if dual heater
    if (hasTb2 && tb2Data.length > 0) {
      ctx.strokeStyle = '#fab387'; // #fab387 Orange
      ctx.lineWidth = 2.0;
      ctx.beginPath();
      tb2Data.forEach((t2, idx) => {
        if (t2 == null) return;
        const x = ptX(idx);
        const y = ptYTemp(t2);
        if (idx === 0) ctx.moveTo(x, y);
        else ctx.lineTo(x, y);
      });
      ctx.stroke();
    }

    // 3. TB1 Coffee Boiler Curve (Pink / Theme Primary)
    if (tb1Data.length > 0) {
      ctx.strokeStyle = theme.primary || '#f38ba8'; // #f38ba8 Pink
      ctx.lineWidth = 2.5;
      ctx.beginPath();
      tb1Data.forEach((t1, idx) => {
        const x = ptX(idx);
        const y = ptYTemp(t1);
        if (idx === 0) ctx.moveTo(x, y);
        else ctx.lineTo(x, y);
      });
      ctx.stroke();
    }

    // Current Value Dots at Latest Position
    const lx = ptX(nPts - 1);
    const lastTb1 = tb1Data[nPts - 1];
    const lastTb2 = hasTb2 ? tb2Data[nPts - 1] : null;
    const lastFlow = flowData[nPts - 1];

    if (lastTb1 != null) {
      ctx.fillStyle = theme.primary || '#f38ba8';
      ctx.beginPath();
      ctx.arc(lx, ptYTemp(lastTb1), 4, 0, Math.PI * 2);
      ctx.fill();
    }

    if (lastTb2 != null) {
      ctx.fillStyle = '#fab387';
      ctx.beginPath();
      ctx.arc(lx, ptYTemp(lastTb2), 4, 0, Math.PI * 2);
      ctx.fill();
    }

    // Top Legend HUD Header (matching gui_widgets.py)
    ctx.textAlign = 'left';
    ctx.font = 'bold 10px monospace';

    // TB1
    ctx.fillStyle = theme.primary || '#f38ba8';
    ctx.fillText(`■ TB1: ${lastTb1 != null ? lastTb1.toFixed(1) : '---'}°C`, padLeft, 14);

    // TB2
    ctx.fillStyle = '#fab387';
    if (hasTb2 && lastTb2 != null) {
      ctx.fillText(`■ TB2: ${lastTb2.toFixed(1)}°C`, padLeft + 110, 14);
    } else {
      ctx.fillText('■ TB2: N/A (Single Heater)', padLeft + 110, 14);
    }

    // Flow
    ctx.fillStyle = '#74c7ec';
    ctx.fillText(`■ Flow: ${lastFlow != null ? lastFlow.toFixed(1) : '---'} ml/s`, padLeft + 280, 14);
  }, [tb1Data, tb2Data, flowData, theme, hasTb2, maxSamples]);

  return (
    <div className={`p-3 border rounded ${theme.surfaceClass} space-y-2`}>
      {/* Title & Control Bar */}
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-gray-800 pb-1.5 text-xs">
        <div className="flex items-center space-x-2">
          <span className="font-bold text-gray-200 uppercase tracking-wider flex items-center space-x-1.5">
            <Activity className="w-4 h-4 text-emerald-400" />
            <span>REAL-TIME OSCILLOSCOPE &amp; STRIP CHART</span>
          </span>
          <span className="text-[10px] text-gray-500 font-mono">
            (X: Time / Y: Temperature °C)
          </span>
        </div>

        <div className="flex items-center space-x-1.5">
          <button
            onClick={() => setIsPaused(!isPaused)}
            className={`px-2 py-0.5 rounded text-[11px] font-bold font-mono flex items-center space-x-1 ${
              isPaused
                ? 'bg-amber-600 text-white'
                : 'bg-emerald-950/80 text-emerald-300 border border-emerald-600'
            }`}
          >
            {isPaused ? <Play className="w-3 h-3" /> : <Pause className="w-3 h-3" />}
            <span>{isPaused ? 'RESUME' : 'PAUSE'}</span>
          </button>

          <button
            onClick={handleClear}
            className="px-2 py-0.5 rounded text-[11px] font-bold font-mono bg-gray-800 hover:bg-gray-700 text-gray-300 flex items-center space-x-1"
          >
            <Trash2 className="w-3 h-3" />
            <span>CLEAR</span>
          </button>

          <button
            onClick={handleExportCSV}
            className="px-2 py-0.5 rounded text-[11px] font-bold font-mono bg-purple-950/80 hover:bg-purple-900 text-purple-200 border border-purple-700 flex items-center space-x-1"
          >
            <Download className="w-3 h-3" />
            <span>CSV</span>
          </button>
        </div>
      </div>

      {/* Canvas */}
      <div className="relative">
        <canvas
          ref={canvasRef}
          className="w-full h-[220px] block rounded"
        />
        {isPaused && (
          <div className="absolute top-3 right-3 px-2 py-0.5 bg-amber-500 text-black font-black font-mono text-[10px] rounded shadow uppercase tracking-wider animate-pulse">
            PAUSED
          </div>
        )}
      </div>
    </div>
  );
}
