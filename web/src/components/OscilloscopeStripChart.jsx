import React, { useState, useEffect, useRef } from 'react';
import { Play, Pause, Trash2, Download, Activity } from 'lucide-react';
import { createTranslator } from '../i18n/translations';

/**
 * Real-Time Rolling Strip Chart Graph (Oscilloscope Widget)
 * - Auto-resets traces whenever `selectedPort` changes (zero cross-machine trace bleed)
 * - Right-aligns samples to the 'Now' edge with real elapsed-time X-axis labels
 * - Handles dual-heater/dual-boiler models (TB1 + TB2) and displays a clear protocol
 *   notice on Smart Connect (@TF:-only) devices where numeric temps/flow are not exposed.
 */
export default function OscilloscopeStripChart({
  theme,
  lang = 'en',
  liveData,
  selectedPort = '',
  maxSamples = 60,
}) {
  const t = createTranslator(lang);
  const [tb1Data, setTb1Data] = useState([]);
  const [tb2Data, setTb2Data] = useState([]);
  const [flowData, setFlowData] = useState([]);
  const [sampleTimes, setSampleTimes] = useState([]);
  const [isPaused, setIsPaused] = useState(false);

  const canvasRef = useRef(null);

  // Extract latest readings & capabilities
  const telem = liveData?.telemetry || {};
  const caps = liveData?.capabilities || {};
  const protocol = liveData?.protocol || caps.protocol || '';
  const currentTb1 = telem.heater_coffee_c != null ? Number(telem.heater_coffee_c) : null;
  const currentTb2 = telem.heater_steam_c != null ? Number(telem.heater_steam_c) : null;
  const currentFlow = telem.flow_rate_ml_s != null ? Number(telem.flow_rate_ml_s) : 0.0;
  const hasTb2 = Boolean(caps.has_steam_temp || telem.is_dual_heater);
  const isNumericUnsupported = Boolean(
    protocol &&
    caps.has_coffee_temp === false &&
    caps.has_flowmeter === false
  );

  // Auto-clear rolling buffers whenever the user switches ports / machines
  useEffect(() => {
    setTb1Data([]);
    setTb2Data([]);
    setFlowData([]);
    setSampleTimes([]);
  }, [selectedPort]);

  // Append new sample on each liveData update
  useEffect(() => {
    if (isPaused || currentTb1 === null) return;
    const nowMs = Date.now();

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

    setSampleTimes((prev) => {
      const next = [...prev, nowMs];
      return next.length > maxSamples ? next.slice(next.length - maxSamples) : next;
    });
  }, [liveData, isPaused, currentTb1, currentTb2, currentFlow, maxSamples]);

  const handleClear = () => {
    setTb1Data([]);
    setTb2Data([]);
    setFlowData([]);
    setSampleTimes([]);
  };

  const handleExportCSV = () => {
    if (tb1Data.length === 0) return;
    const header = 'Sample_Index,Timestamp_ISO,Elapsed_Sec,TB1_Coffee_C,TB2_Steam_C,Flow_Rate_ml_s\n';
    const lastMs = sampleTimes[sampleTimes.length - 1] || Date.now();
    const rows = tb1Data
      .map((t1, i) => {
        const tsMs = sampleTimes[i] || lastMs;
        const secAgo = Math.round((lastMs - tsMs) / 1000);
        const t2 = tb2Data[i] ?? '';
        const fl = flowData[i] ?? 0;
        return `${i},${new Date(tsMs).toISOString()},-${secAgo}s,${t1},${t2},${fl}`;
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

  // High-DPI Canvas Rendering
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

    const padLeft = 46;
    const padRight = 20;
    const padTop = 26;
    const padBottom = 26;
    const plotW = Math.max(10, w - padLeft - padRight);
    const plotH = Math.max(10, h - padTop - padBottom);

    const tempMin = 20.0;
    const tempMax = 160.0;
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

    // Dynamic Time Window Axis (computed from real sample timestamps, right-aligned to 'Now')
    const nPts = tb1Data.length;
    const nowLabel = t('oscNow');
    let spanSec = 50;
    if (sampleTimes.length >= 2) {
      const actualSpan = Math.max(5, Math.round((sampleTimes[sampleTimes.length - 1] - sampleTimes[0]) / 1000));
      spanSec = nPts >= maxSamples ? actualSpan : Math.max(actualSpan, 50);
    }
    const timeLabels = [
      `-${spanSec}s`,
      `-${Math.round(spanSec * 0.8)}s`,
      `-${Math.round(spanSec * 0.6)}s`,
      `-${Math.round(spanSec * 0.4)}s`,
      `-${Math.round(spanSec * 0.2)}s`,
      nowLabel,
    ];
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

      ctx.fillStyle = label === nowLabel ? (theme.textPrimary || '#FCEE09') : (theme.textMuted || '#6c7086');
      ctx.fillText(label, gx, h - 10);
    });

    // Empty or Unsupported Protocol state
    if (nPts === 0) {
      ctx.textAlign = 'left';
      ctx.font = 'bold 10px monospace';
      ctx.fillStyle = '#f38ba8';
      ctx.fillText('■ TB1: ---', padLeft, 14);

      ctx.fillStyle = '#fab387';
      ctx.fillText(hasTb2 ? '■ TB2: ---' : t('oscTb2Single'), padLeft + 110, 14);

      ctx.fillStyle = '#74c7ec';
      ctx.fillText(`${t('oscFlowPrefix')} ---`, padLeft + 260, 14);

      ctx.textAlign = 'center';
      ctx.fillStyle = isNumericUnsupported ? '#FBBF24' : (theme.textMuted || '#6c7086');
      ctx.font = isNumericUnsupported ? 'bold 11px monospace' : '11px monospace';
      if (isNumericUnsupported) {
        ctx.fillText(t('oscUnsupportedTitle'), padLeft + plotW / 2, padTop + plotH / 2 - 8);
        ctx.fillStyle = theme.textMuted || '#94A3B8';
        ctx.font = '10px monospace';
        ctx.fillText(t('oscUnsupportedSub'), padLeft + plotW / 2, padTop + plotH / 2 + 10);
      } else {
        ctx.fillText(t('oscAwaiting'), padLeft + plotW / 2, padTop + plotH / 2);
      }
      return;
    }

    // Right-align samples to 'Now' (right edge) so traces scroll leftward naturally
    const total = Math.max(2, maxSamples);
    const ptX = (idx) => {
      const offsetFromRight = nPts - 1 - idx;
      return padLeft + plotW - (offsetFromRight / (total - 1)) * plotW;
    };

    const ptYTemp = (val) => {
      const clamped = Math.max(tempMin, Math.min(tempMax, val));
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
      ctx.strokeStyle = '#74c7ec';
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

    // 2. TB2 Steam/Instant Boiler Curve (Orange)
    if (hasTb2 && tb2Data.length > 0) {
      ctx.strokeStyle = '#fab387';
      ctx.lineWidth = 2.0;
      ctx.beginPath();
      let started = false;
      tb2Data.forEach((t2, idx) => {
        if (t2 == null) return;
        const x = ptX(idx);
        const y = ptYTemp(t2);
        if (!started) {
          ctx.moveTo(x, y);
          started = true;
        } else {
          ctx.lineTo(x, y);
        }
      });
      ctx.stroke();
    }

    // 3. TB1 Coffee Boiler Curve (Pink / Theme Primary)
    if (tb1Data.length > 0) {
      ctx.strokeStyle = theme.primary || '#f38ba8';
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

    // Latest Value Dots at 'Now' right edge
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

    // Top Legend HUD Header
    ctx.textAlign = 'left';
    ctx.font = 'bold 10px monospace';

    ctx.fillStyle = theme.primary || '#f38ba8';
    ctx.fillText(`■ TB1: ${lastTb1 != null ? lastTb1.toFixed(1) : '---'}°C`, padLeft, 14);

    ctx.fillStyle = '#fab387';
    if (hasTb2 && lastTb2 != null) {
      ctx.fillText(`■ TB2: ${lastTb2.toFixed(1)}°C`, padLeft + 115, 14);
    } else {
      ctx.fillText(t('oscTb2Single'), padLeft + 115, 14);
    }

    ctx.fillStyle = '#74c7ec';
    ctx.fillText(`${t('oscFlowPrefix')} ${lastFlow != null ? lastFlow.toFixed(1) : '---'} ml/s`, padLeft + 275, 14);
  }, [tb1Data, tb2Data, flowData, sampleTimes, theme, hasTb2, isNumericUnsupported, maxSamples, lang, t]);

  return (
    <div className={`p-3 border rounded ${theme.surfaceClass} space-y-2`}>
      {/* Title & Control Bar */}
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-gray-800 pb-1.5 text-xs">
        <div className="flex items-center space-x-2">
          <span className="font-bold text-gray-200 uppercase tracking-wider flex items-center space-x-1.5">
            <Activity className="w-4 h-4 text-emerald-400" />
            <span>{t('oscTitle')}</span>
          </span>
          <span className="text-[10px] text-gray-500 font-mono">
            {t('oscAxes')}
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
            <span>{isPaused ? t('btnResume') : t('btnPause')}</span>
          </button>

          <button
            onClick={handleClear}
            className="px-2 py-0.5 rounded text-[11px] font-bold font-mono bg-gray-800 hover:bg-gray-700 text-gray-300 flex items-center space-x-1"
          >
            <Trash2 className="w-3 h-3" />
            <span>{t('btnClear')}</span>
          </button>

          <button
            onClick={handleExportCSV}
            disabled={tb1Data.length === 0}
            className="px-2 py-0.5 rounded text-[11px] font-bold font-mono bg-purple-950/80 hover:bg-purple-900 text-purple-200 border border-purple-700 flex items-center space-x-1 disabled:opacity-40"
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
          <div className="absolute top-2 right-2 px-2 py-0.5 rounded bg-amber-600/90 text-white text-[10px] font-bold font-mono">
            {t('oscPausedBadge')}
          </div>
        )}
      </div>
    </div>
  );
}
