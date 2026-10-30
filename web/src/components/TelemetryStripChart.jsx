import React, { useState, useEffect, useRef, useMemo } from 'react';
import {
  Play,
  Pause,
  Trash2,
  Download,
  Flame,
  Activity,
  Layers,
  Sparkles,
  Clock,
  Gauge,
  Sliders,
  Maximize2,
} from 'lucide-react';

/**
 * Functional Real-Time Telemetry Strip Chart Recorder
 * Displays physical time-series measurements over time:
 * - Coffee Thermoblock TB1 Temp (°C) & Steam TB2 Temp (°C)
 * - Turbine Flowmeter Water Flow Rate (ml/s) & Cumulative Volume (ml)
 * - Brew Unit Dynamic Stroke Encoder Position (ticks)
 * - Optical Bean Hopper Sensor IR Delta (counts)
 * 
 * Features:
 * - Real physical axes with metric units (°C, ml/s, ticks, counts)
 * - Nominal operating target bands (e.g. 90-95°C brew zone)
 * - Configurable rolling window (30s, 60s, 120s, 300s)
 * - Pause / Resume inspection without interrupting serial polling
 * - Clear buffer
 * - 1-Click CSV telemetry export of all recorded rows
 * - Interactive hover crosshair readout
 */
export default function TelemetryStripChart({
  theme,
  liveData,
  selectedPort,
}) {
  const [history, setHistory] = useState([]);
  const [isPaused, setIsPaused] = useState(false);
  const [windowSeconds, setWindowSeconds] = useState(60); // 30, 60, 120, 300
  const [hoverIndex, setHoverIndex] = useState(null);
  const [activeChannels, setActiveChannels] = useState({
    tb1: true,
    tb2: true,
    flow: true,
    bu: true,
    beans: true,
  });

  const canvasRef = useRef(null);

  // Extract latest physical metrics from liveData
  const telem = liveData?.telemetry || {};
  const currentTb1 = telem.heater_coffee_c != null ? Number(telem.heater_coffee_c) : null;
  const currentTb2 = telem.heater_steam_c != null ? Number(telem.heater_steam_c) : null;
  const currentFlow = telem.flow_rate_ml_s != null ? Number(telem.flow_rate_ml_s) : 0.0;
  const currentVol = telem.flow_volume_ml != null ? Number(telem.flow_volume_ml) : 0.0;
  const currentBu = telem.bu_encoder_pos != null ? Number(telem.bu_encoder_pos) : null;
  const currentBeanDelta = telem.optical_delta != null ? Number(telem.optical_delta) : null;
  const beansOk = telem.beans_ok ?? true;
  const timestampStr = liveData?.timestamp || new Date().toLocaleTimeString();

  // Append new telemetry point on every liveData change when not paused
  useEffect(() => {
    if (isPaused || currentTb1 === null) return;

    setHistory((prev) => {
      const newPt = {
        time: Date.now(),
        timeStr: timestampStr,
        tb1: currentTb1,
        tb2: currentTb2,
        flow: currentFlow,
        vol: currentVol,
        bu: currentBu,
        beanDelta: currentBeanDelta,
        beansOk,
      };

      // Keep up to 350 physical samples in rolling ring buffer
      const updated = [...prev, newPt];
      if (updated.length > 350) {
        return updated.slice(updated.length - 350);
      }
      return updated;
    });
  }, [liveData, isPaused, currentTb1, currentTb2, currentFlow, currentVol, currentBu, currentBeanDelta, beansOk, timestampStr]);

  // Compute live statistics for HUD (Min, Max, Rate of Change)
  const stats = useMemo(() => {
    if (history.length === 0) {
      return {
        tb1Cur: currentTb1 ?? 0,
        tb1Min: 0,
        tb1Max: 0,
        tb1Rate: 0,
        flowCur: currentFlow,
        flowMax: 0,
        buCur: currentBu ?? 0,
        beanCur: currentBeanDelta ?? 0,
      };
    }

    const tb1Vals = history.map((p) => p.tb1).filter((v) => v != null);
    const flowVals = history.map((p) => p.flow).filter((v) => v != null);

    const minT = tb1Vals.length > 0 ? Math.min(...tb1Vals) : 0;
    const maxT = tb1Vals.length > 0 ? Math.max(...tb1Vals) : 0;
    const maxF = flowVals.length > 0 ? Math.max(...flowVals) : 0;

    let rate = 0;
    if (history.length >= 2) {
      const last = history[history.length - 1];
      const prev = history[history.length - 2];
      const dt = (last.time - prev.time) / 1000.0;
      if (dt > 0.1) {
        rate = (last.tb1 - prev.tb1) / dt;
      }
    }

    return {
      tb1Cur: currentTb1 ?? (tb1Vals[tb1Vals.length - 1] || 0),
      tb1Min: minT,
      tb1Max: maxT,
      tb1Rate: rate,
      flowCur: currentFlow,
      flowMax: maxF,
      buCur: currentBu ?? 0,
      beanCur: currentBeanDelta ?? 0,
    };
  }, [history, currentTb1, currentFlow, currentBu, currentBeanDelta]);

  // 1-Click Telemetry CSV Export
  const handleExportCSV = () => {
    if (history.length === 0) {
      alert('No telemetry recorded yet to export.');
      return;
    }

    const headers = 'Timestamp,TimeStr,TB1_Coffee_Temp_C,TB2_Steam_Temp_C,Flow_Rate_ml_s,Flow_Volume_ml,BU_Encoder_Ticks,Optical_Bean_Delta,Beans_OK\n';
    const rows = history
      .map(
        (p) =>
          `${p.time},"${p.timeStr}",${p.tb1 ?? ''},${p.tb2 ?? ''},${p.flow ?? 0},${p.vol ?? 0},${p.bu ?? ''},${p.beanDelta ?? ''},${p.beansOk ? 'OK' : 'EMPTY'}`
      )
      .join('\n');

    const blob = new Blob([headers + rows], { type: 'text/csv;charset=utf-8;' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `spectra_telemetry_${new Date().toISOString().replace(/[:.]/g, '-')}.csv`;
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
    ctx.fillStyle = theme.canvasBg || '#0E0E12';
    ctx.fillRect(0, 0, w, h);

    // Layout: Two vertically stacked synchronized charts
    // Upper Chart: Thermal & Flow (60% height)
    // Lower Chart: Brew Unit & Optical Bean Delta (40% height)
    const splitY = Math.floor(h * 0.58);
    const padL = 48; // Left Y-Axis labels
    const padR = 48; // Right Y-Axis labels
    const padT = 24;
    const padB = 24;

    const plotW = Math.max(10, w - padL - padR);
    const plot1H = Math.max(10, splitY - padT - 16);
    const plot2Top = splitY + 16;
    const plot2H = Math.max(10, h - plot2Top - padB);

    // ------------------------------------------------------------------------
    // CHART 1: THERMAL (°C) & FLOW RATE (ml/s)
    // ------------------------------------------------------------------------
    // Grid Lines & Scales: Temp 20°C to 140°C
    const tMin = 20;
    const tMax = 140;
    const fMin = 0;
    const fMax = 10; // 0 to 10 ml/s

    // Horizontal Grid Lines for Chart 1
    const tempSteps = [20, 50, 80, 95, 110, 140];
    ctx.font = '10px monospace';
    ctx.textAlign = 'right';
    ctx.textBaseline = 'middle';

    // Nominal Brew Target Zone Shading (90°C - 95°C)
    const brewZoneY1 = padT + (1.0 - (95 - tMin) / (tMax - tMin)) * plot1H;
    const brewZoneY2 = padT + (1.0 - (90 - tMin) / (tMax - tMin)) * plot1H;
    ctx.fillStyle = 'rgba(16, 185, 129, 0.12)'; // Soft green band
    ctx.fillRect(padL, brewZoneY1, plotW, brewZoneY2 - brewZoneY1);

    tempSteps.forEach((tVal) => {
      const normY = 1.0 - (tVal - tMin) / (tMax - tMin);
      const gy = padT + normY * plot1H;

      // Grid line
      ctx.strokeStyle = tVal === 95 ? 'rgba(16, 185, 129, 0.35)' : (theme.gridColor || 'rgba(255,255,255,0.08)');
      ctx.lineWidth = tVal === 95 ? 1.5 : 1;
      ctx.setLineDash(tVal === 95 ? [4, 4] : []);
      ctx.beginPath();
      ctx.moveTo(padL, gy);
      ctx.lineTo(padL + plotW, gy);
      ctx.stroke();
      ctx.setLineDash([]);

      // Left Axis Label: Temperature
      ctx.fillStyle = tVal === 95 ? '#10B981' : (theme.textMuted || '#888');
      ctx.fillText(`${tVal}°C`, padL - 6, gy);

      // Right Axis Label: Flow Rate
      const fVal = ((tVal - tMin) / (tMax - tMin)) * (fMax - fMin);
      if (fVal >= 0 && fVal <= 10) {
        ctx.textAlign = 'left';
        ctx.fillStyle = '#06B6D4'; // Cyan
        ctx.fillText(`${fVal.toFixed(1)} ml/s`, padL + plotW + 6, gy);
        ctx.textAlign = 'right';
      }
    });

    // Chart 1 Title & Legend
    ctx.textAlign = 'left';
    ctx.font = 'bold 11px monospace';
    ctx.fillStyle = theme.textPrimary || '#FCEE09';
    ctx.fillText('01 // THERMAL PROFILE (°C) & HYDRAULIC WATER FLOW (ml/s)', padL, padT - 10);

    // Legend items
    ctx.font = '10px monospace';
    let legX = padL + plotW - 280;
    // TB1
    ctx.fillStyle = theme.primary || '#FF4F00';
    ctx.fillRect(legX, padT - 17, 10, 10);
    ctx.fillStyle = '#fff';
    ctx.fillText('TB1 (Coffee)', legX + 14, padT - 9);
    // Flow
    legX += 95;
    ctx.fillStyle = '#06B6D4';
    ctx.fillRect(legX, padT - 17, 10, 10);
    ctx.fillStyle = '#fff';
    ctx.fillText('Flow (ml/s)', legX + 14, padT - 9);
    // Target
    legX += 85;
    ctx.fillStyle = 'rgba(16, 185, 129, 0.8)';
    ctx.fillRect(legX, padT - 17, 10, 10);
    ctx.fillStyle = '#10B981';
    ctx.fillText('Target (90-95°)', legX + 14, padT - 9);

    // ------------------------------------------------------------------------
    // CHART 2: BREW UNIT ENCODER (TICKS) & BEAN DELTA (COUNTS)
    // ------------------------------------------------------------------------
    const buMin = 0;
    const buMax = 700;
    const bDeltaMin = 0;
    const bDeltaMax = 200;

    // Horizontal Grid Lines for Chart 2
    const buSteps = [0, 200, 400, 649];
    buSteps.forEach((buVal) => {
      const normY = 1.0 - (buVal - buMin) / (buMax - buMin);
      const gy = plot2Top + normY * plot2H;

      ctx.strokeStyle = buVal === 649 ? 'rgba(239, 68, 68, 0.35)' : (theme.gridColor || 'rgba(255,255,255,0.08)');
      ctx.lineWidth = 1;
      ctx.setLineDash(buVal === 649 ? [3, 3] : []);
      ctx.beginPath();
      ctx.moveTo(padL, gy);
      ctx.lineTo(padL + plotW, gy);
      ctx.stroke();
      ctx.setLineDash([]);

      // Left Axis: Encoder Ticks
      ctx.textAlign = 'right';
      ctx.fillStyle = buVal === 649 ? '#EF4444' : (theme.textMuted || '#888');
      ctx.fillText(`${buVal} tk`, padL - 6, gy);

      // Right Axis: Bean Delta
      const bVal = Math.round(((buVal - buMin) / (buMax - buMin)) * (bDeltaMax - bDeltaMin));
      ctx.textAlign = 'left';
      ctx.fillStyle = '#F59E0B'; // Amber
      ctx.fillText(`${bVal} cnt`, padL + plotW + 6, gy);
      ctx.textAlign = 'right';
    });

    // Calibrated Optical Bean Threshold line (115 counts)
    const beanThreshY = plot2Top + (1.0 - (115 - bDeltaMin) / (bDeltaMax - bDeltaMin)) * plot2H;
    ctx.strokeStyle = 'rgba(245, 158, 11, 0.6)';
    ctx.lineWidth = 1.5;
    ctx.setLineDash([5, 5]);
    ctx.beginPath();
    ctx.moveTo(padL, beanThreshY);
    ctx.lineTo(padL + plotW, beanThreshY);
    ctx.stroke();
    ctx.setLineDash([]);

    // Chart 2 Title & Legend
    ctx.textAlign = 'left';
    ctx.font = 'bold 11px monospace';
    ctx.fillStyle = theme.textSecondary || '#38BDF8';
    ctx.fillText('02 // BREW UNIT TRAVEL (TICKS) & BEAN HOPPER DELTA (COUNTS)', padL, plot2Top - 8);

    // Legend
    ctx.font = '10px monospace';
    let leg2X = padL + plotW - 270;
    // BU
    ctx.fillStyle = '#8B5CF6'; // Purple
    ctx.fillRect(leg2X, plot2Top - 15, 10, 10);
    ctx.fillStyle = '#fff';
    ctx.fillText('BU Encoder', leg2X + 14, plot2Top - 7);
    // Beans
    leg2X += 95;
    ctx.fillStyle = '#F59E0B';
    ctx.fillRect(leg2X, plot2Top - 15, 10, 10);
    ctx.fillStyle = '#fff';
    ctx.fillText('IR Delta', leg2X + 14, plot2Top - 7);
    // Thresh
    leg2X += 75;
    ctx.fillStyle = 'rgba(245, 158, 11, 0.7)';
    ctx.fillRect(leg2X, plot2Top - 15, 10, 10);
    ctx.fillStyle = '#F59E0B';
    ctx.fillText('Threshold (115)', leg2X + 14, plot2Top - 7);

    // ------------------------------------------------------------------------
    // PLOT TIME-SERIES DATA POINTS
    // ------------------------------------------------------------------------
    // Filter history to current window duration
    const now = Date.now();
    const windowMs = windowSeconds * 1000;
    const windowStart = now - windowMs;
    const pts = history.filter((p) => p.time >= windowStart);

    // Vertical Time Grid (-60s, -45s, -30s, -15s, Now)
    const timeDivs = 4;
    for (let i = 0; i <= timeDivs; i++) {
      const frac = i / timeDivs;
      const gx = padL + frac * plotW;
      const secAgo = Math.round((1.0 - frac) * windowSeconds);

      // Vertical line across both plots
      ctx.strokeStyle = theme.gridColor || 'rgba(255,255,255,0.06)';
      ctx.lineWidth = 1;
      ctx.beginPath();
      ctx.moveTo(gx, padT);
      ctx.lineTo(gx, padT + plot1H);
      ctx.moveTo(gx, plot2Top);
      ctx.lineTo(gx, plot2Top + plot2H);
      ctx.stroke();

      // Time label at bottom
      ctx.textAlign = 'center';
      ctx.fillStyle = theme.textMuted || '#888';
      ctx.font = '10px monospace';
      ctx.fillText(secAgo === 0 ? 'NOW' : `-${secAgo}s`, gx, h - 8);
    }

    if (pts.length < 2) {
      ctx.textAlign = 'center';
      ctx.fillStyle = theme.textMuted || '#888';
      ctx.font = '12px monospace';
      ctx.fillText('Awaiting live telemetry stream points...', padL + plotW / 2, padT + plot1H / 2);
      ctx.fillText('Collecting physical sensor readings...', padL + plotW / 2, plot2Top + plot2H / 2);
      return;
    }

    const getX = (t) => {
      const normX = Math.max(0, Math.min(1, (t - windowStart) / windowMs));
      return padL + normX * plotW;
    };

    // 1. Plot Water Flow Rate (Chart 1 - Cyan)
    if (activeChannels.flow) {
      ctx.strokeStyle = '#06B6D4';
      ctx.lineWidth = 2.0;
      ctx.beginPath();
      pts.forEach((p, idx) => {
        const x = getX(p.time);
        const normY = 1.0 - (Math.min(fMax, Math.max(fMin, p.flow)) - fMin) / (fMax - fMin);
        const y = padT + normY * plot1H;
        if (idx === 0) ctx.moveTo(x, y);
        else ctx.lineTo(x, y);
      });
      ctx.stroke();
    }

    // 2. Plot TB1 Coffee Thermoblock Temp (Chart 1 - Theme Primary)
    if (activeChannels.tb1) {
      ctx.strokeStyle = theme.primary || '#FF4F00';
      ctx.lineWidth = 2.5;
      ctx.beginPath();
      pts.forEach((p, idx) => {
        const x = getX(p.time);
        const normY = 1.0 - (Math.min(tMax, Math.max(tMin, p.tb1)) - tMin) / (tMax - tMin);
        const y = padT + normY * plot1H;
        if (idx === 0) ctx.moveTo(x, y);
        else ctx.lineTo(x, y);
      });
      ctx.stroke();

      // End point pulse dot
      const lastPt = pts[pts.length - 1];
      const endX = getX(lastPt.time);
      const endNormY = 1.0 - (Math.min(tMax, Math.max(tMin, lastPt.tb1)) - tMin) / (tMax - tMin);
      const endY = padT + endNormY * plot1H;
      ctx.fillStyle = theme.primary || '#FF4F00';
      ctx.beginPath();
      ctx.arc(endX, endY, 4, 0, Math.PI * 2);
      ctx.fill();
    }

    // 3. Plot BU Encoder Position (Chart 2 - Purple)
    if (activeChannels.bu) {
      ctx.strokeStyle = '#8B5CF6';
      ctx.lineWidth = 2.0;
      ctx.beginPath();
      pts.forEach((p, idx) => {
        const x = getX(p.time);
        const normY = 1.0 - (Math.min(buMax, Math.max(buMin, p.bu ?? 0)) - buMin) / (buMax - buMin);
        const y = plot2Top + normY * plot2H;
        if (idx === 0) ctx.moveTo(x, y);
        else ctx.lineTo(x, y);
      });
      ctx.stroke();
    }

    // 4. Plot Optical Bean Delta (Chart 2 - Amber)
    if (activeChannels.beans) {
      ctx.strokeStyle = '#F59E0B';
      ctx.lineWidth = 2.0;
      ctx.beginPath();
      pts.forEach((p, idx) => {
        const x = getX(p.time);
        const normY = 1.0 - (Math.min(bDeltaMax, Math.max(bDeltaMin, p.beanDelta ?? 0)) - bDeltaMin) / (bDeltaMax - bDeltaMin);
        const y = plot2Top + normY * plot2H;
        if (idx === 0) ctx.moveTo(x, y);
        else ctx.lineTo(x, y);
      });
      ctx.stroke();
    }

    // ------------------------------------------------------------------------
    // INTERACTIVE HOVER CROSSHAIR
    // ------------------------------------------------------------------------
    if (hoverIndex !== null && pts[hoverIndex]) {
      const hPt = pts[hoverIndex];
      const hx = getX(hPt.time);

      // Vertical cursor line
      ctx.strokeStyle = 'rgba(255, 255, 255, 0.4)';
      ctx.lineWidth = 1;
      ctx.setLineDash([3, 3]);
      ctx.beginPath();
      ctx.moveTo(hx, padT);
      ctx.lineTo(hx, h - padB);
      ctx.stroke();
      ctx.setLineDash([]);

      // Readout Box
      const tipX = Math.min(hx + 12, w - 190);
      const tipY = padT + 10;
      ctx.fillStyle = 'rgba(15, 23, 42, 0.95)';
      ctx.strokeStyle = theme.border || '#333';
      ctx.lineWidth = 1;
      ctx.fillRect(tipX, tipY, 175, 100);
      ctx.strokeRect(tipX, tipY, 175, 100);

      ctx.textAlign = 'left';
      ctx.font = 'bold 10px monospace';
      ctx.fillStyle = '#fff';
      ctx.fillText(`TIME: ${hPt.timeStr}`, tipX + 8, tipY + 16);

      ctx.fillStyle = theme.primary || '#FF4F00';
      ctx.fillText(`TB1 TEMP: ${hPt.tb1?.toFixed(1) ?? '--'} °C`, tipX + 8, tipY + 34);

      ctx.fillStyle = '#06B6D4';
      ctx.fillText(`FLOW: ${hPt.flow?.toFixed(2) ?? '0.00'} ml/s`, tipX + 8, tipY + 50);

      ctx.fillStyle = '#8B5CF6';
      ctx.fillText(`BU POS: ${hPt.bu ?? '--'} ticks`, tipX + 8, tipY + 66);

      ctx.fillStyle = '#F59E0B';
      ctx.fillText(`BEANS DELTA: ${hPt.beanDelta ?? '--'} (${hPt.beansOk ? 'OK' : 'EMPTY'})`, tipX + 8, tipY + 82);
    }
  }, [history, theme, windowSeconds, hoverIndex, activeChannels]);

  // Handle canvas mouse move for interactive inspection
  const handleMouseMove = (e) => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const rect = canvas.getBoundingClientRect();
    const mouseX = e.clientX - rect.left;

    const padL = 48;
    const padR = 48;
    const plotW = Math.max(10, rect.width - padL - padR);

    if (mouseX < padL || mouseX > padL + plotW) {
      setHoverIndex(null);
      return;
    }

    const windowMs = windowSeconds * 1000;
    const windowStart = Date.now() - windowMs;
    const pts = history.filter((p) => p.time >= windowStart);

    if (pts.length === 0) {
      setHoverIndex(null);
      return;
    }

    const targetTime = windowStart + ((mouseX - padL) / plotW) * windowMs;

    // Find closest index
    let closestIdx = 0;
    let minDiff = Infinity;
    pts.forEach((p, idx) => {
      const diff = Math.abs(p.time - targetTime);
      if (diff < minDiff) {
        minDiff = diff;
        closestIdx = idx;
      }
    });

    setHoverIndex(closestIdx);
  };

  const handleMouseLeave = () => {
    setHoverIndex(null);
  };

  return (
    <div className="space-y-3">
      {/* 1. TOP TELEMETRY HUD TILES (Real Numerical Metrics) */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-2.5">
        {/* Thermoblock TB1 */}
        <div className={`p-3 border rounded ${theme.surfaceClass}`}>
          <div className="flex items-center justify-between">
            <span className="text-[11px] font-bold text-gray-400 uppercase tracking-wider flex items-center space-x-1">
              <Flame className="w-3.5 h-3.5 text-rose-400" />
              <span>TB1 HEATER</span>
            </span>
            <span className={`text-[10px] font-bold px-1.5 py-0.5 rounded ${stats.tb1Cur >= 90 && stats.tb1Cur <= 100 ? 'bg-emerald-950 text-emerald-400 border border-emerald-700' : 'bg-gray-800 text-gray-300'}`}>
              {stats.tb1Cur >= 90 && stats.tb1Cur <= 100 ? 'READY' : 'HEATING'}
            </span>
          </div>
          <div className={`text-xl font-black font-mono my-1 ${theme.textPrimary}`}>
            {stats.tb1Cur.toFixed(1)} <span className="text-sm font-normal">°C</span>
          </div>
          <div className="text-[10px] text-gray-400 flex justify-between font-mono">
            <span>MIN: {stats.tb1Min.toFixed(1)}°</span>
            <span>MAX: {stats.tb1Max.toFixed(1)}°</span>
            <span>RATE: {stats.tb1Rate >= 0 ? `+${stats.tb1Rate.toFixed(2)}` : stats.tb1Rate.toFixed(2)}°/s</span>
          </div>
        </div>

        {/* Turbine Flowmeter */}
        <div className={`p-3 border rounded ${theme.surfaceClass}`}>
          <div className="flex items-center justify-between">
            <span className="text-[11px] font-bold text-gray-400 uppercase tracking-wider flex items-center space-x-1">
              <Activity className="w-3.5 h-3.5 text-cyan-400" />
              <span>WATER FLOW</span>
            </span>
            <span className="text-[10px] font-bold font-mono text-cyan-400">
              {stats.flowCur > 0 ? 'PUMPING' : 'IDLE'}
            </span>
          </div>
          <div className="text-xl font-black font-mono my-1 text-cyan-400">
            {stats.flowCur.toFixed(2)} <span className="text-sm font-normal">ml/s</span>
          </div>
          <div className="text-[10px] text-gray-400 flex justify-between font-mono">
            <span>PEAK: {stats.flowMax.toFixed(2)} ml/s</span>
            <span>TOTAL: {currentVol.toFixed(1)} ml</span>
          </div>
        </div>

        {/* Brew Unit Stroke */}
        <div className={`p-3 border rounded ${theme.surfaceClass}`}>
          <div className="flex items-center justify-between">
            <span className="text-[11px] font-bold text-gray-400 uppercase tracking-wider flex items-center space-x-1">
              <Sliders className="w-3.5 h-3.5 text-purple-400" />
              <span>BU ENCODER</span>
            </span>
            <span className="text-[10px] font-bold font-mono text-purple-300">
              649 REF
            </span>
          </div>
          <div className="text-xl font-black font-mono my-1 text-purple-400">
            {stats.buCur} <span className="text-sm font-normal">ticks</span>
          </div>
          <div className="text-[10px] text-gray-400 flex justify-between font-mono">
            <span>ZONE: {telem.bu_position_state || 'Home / Mill'}</span>
            <span>STROKE: {telem.bu_stroke_pct ?? 0}%</span>
          </div>
        </div>

        {/* Optical Bean Sensor */}
        <div className={`p-3 border rounded ${theme.surfaceClass}`}>
          <div className="flex items-center justify-between">
            <span className="text-[11px] font-bold text-gray-400 uppercase tracking-wider flex items-center space-x-1">
              <Sparkles className="w-3.5 h-3.5 text-amber-400" />
              <span>OPTICAL BEANS</span>
            </span>
            <span className={`text-[10px] font-bold px-1.5 py-0.5 rounded ${beansOk ? 'bg-emerald-950 text-emerald-400' : 'bg-rose-950 text-rose-400'}`}>
              {beansOk ? 'BEANS OK' : 'FILL BEANS'}
            </span>
          </div>
          <div className="text-xl font-black font-mono my-1 text-amber-400">
            {stats.beanCur} <span className="text-sm font-normal">counts</span>
          </div>
          <div className="text-[10px] text-gray-400 flex justify-between font-mono">
            <span>THRESH: 115 ± 5</span>
            <span>ADC: {telem.bean_adcs ? `${telem.bean_adcs[0]} / ${telem.bean_adcs[1]}` : '---'}</span>
          </div>
        </div>
      </div>

      {/* 2. RECORDER TOOLBAR & CONTROLS */}
      <div className={`p-2.5 border rounded flex flex-wrap items-center justify-between gap-2 text-xs ${theme.surfaceClass}`}>
        {/* Left: Recording state & Window buttons */}
        <div className="flex items-center space-x-2">
          <button
            onClick={() => setIsPaused(!isPaused)}
            className={`flex items-center space-x-1.5 px-3 py-1 font-bold rounded transition-colors ${
              isPaused
                ? 'bg-amber-600 text-white hover:bg-amber-500'
                : 'bg-emerald-600/30 text-emerald-300 border border-emerald-500/50 hover:bg-emerald-600/40'
            }`}
          >
            {isPaused ? <Play className="w-3.5 h-3.5" /> : <Pause className="w-3.5 h-3.5" />}
            <span>{isPaused ? 'RESUME CHART' : 'PAUSE CHART'}</span>
          </button>

          <button
            onClick={() => setHistory([])}
            className="flex items-center space-x-1 px-2.5 py-1 bg-gray-800 hover:bg-gray-700 text-gray-300 font-bold rounded"
          >
            <Trash2 className="w-3.5 h-3.5" />
            <span>CLEAR</span>
          </button>

          {/* Timebase Window Buttons */}
          <div className="flex items-center space-x-1 bg-black/40 p-0.5 rounded border border-gray-800">
            <Clock className="w-3.5 h-3.5 text-gray-400 ml-1.5" />
            {[30, 60, 120, 300].map((sec) => (
              <button
                key={sec}
                onClick={() => setWindowSeconds(sec)}
                className={`px-2 py-0.5 text-[11px] font-bold font-mono rounded ${
                  windowSeconds === sec
                    ? 'bg-sky-600 text-white'
                    : 'text-gray-400 hover:text-white'
                }`}
              >
                {sec >= 60 ? `${sec / 60}m` : `${sec}s`}
              </button>
            ))}
          </div>
        </div>

        {/* Right: Channel toggles & CSV Export */}
        <div className="flex items-center space-x-2">
          <div className="hidden sm:flex items-center space-x-2 text-[11px] font-mono">
            <label className="flex items-center space-x-1 cursor-pointer">
              <input
                type="checkbox"
                checked={activeChannels.tb1}
                onChange={(e) => setActiveChannels({ ...activeChannels, tb1: e.target.checked })}
                className="rounded accent-orange-500"
              />
              <span className="text-orange-400">TB1</span>
            </label>
            <label className="flex items-center space-x-1 cursor-pointer">
              <input
                type="checkbox"
                checked={activeChannels.flow}
                onChange={(e) => setActiveChannels({ ...activeChannels, flow: e.target.checked })}
                className="rounded accent-cyan-500"
              />
              <span className="text-cyan-400">Flow</span>
            </label>
            <label className="flex items-center space-x-1 cursor-pointer">
              <input
                type="checkbox"
                checked={activeChannels.bu}
                onChange={(e) => setActiveChannels({ ...activeChannels, bu: e.target.checked })}
                className="rounded accent-purple-500"
              />
              <span className="text-purple-400">BU</span>
            </label>
            <label className="flex items-center space-x-1 cursor-pointer">
              <input
                type="checkbox"
                checked={activeChannels.beans}
                onChange={(e) => setActiveChannels({ ...activeChannels, beans: e.target.checked })}
                className="rounded accent-amber-500"
              />
              <span className="text-amber-400">Beans</span>
            </label>
          </div>

          <button
            onClick={handleExportCSV}
            className="flex items-center space-x-1 px-3 py-1 bg-purple-950/60 hover:bg-purple-900 border border-purple-600/50 text-purple-200 font-bold rounded transition-colors"
          >
            <Download className="w-3.5 h-3.5" />
            <span>EXPORT CSV</span>
          </button>
        </div>
      </div>

      {/* 3. DUAL-PLOT STRIP CHART CANVAS */}
      <div className={`border rounded p-2 ${theme.surfaceClass} relative`}>
        <canvas
          ref={canvasRef}
          onMouseMove={handleMouseMove}
          onMouseLeave={handleMouseLeave}
          className="w-full h-[460px] cursor-crosshair block rounded"
        />
        {isPaused && (
          <div className="absolute top-4 right-4 px-2.5 py-1 bg-amber-500 text-black font-black font-mono text-xs rounded shadow uppercase tracking-wider animate-pulse">
            PAUSED — INSPECTION FREEZE
          </div>
        )}
      </div>
    </div>
  );
}
