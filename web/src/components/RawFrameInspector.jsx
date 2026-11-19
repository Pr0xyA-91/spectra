import React, { useState, useEffect, useRef } from 'react';
import { Cpu, Copy, Check, ChevronDown, ChevronRight } from 'lucide-react';
import { createTranslator } from '../i18n/translations';

/**
 * Collapsible Live Raw Telemetry Frame Inspector (Tab 02)
 * Designed for multi-device live testing:
 * - Shows detected Vendor, Topology, EF Code, Protocol, and Live Frame status
 * - Tokenizes the raw frame (HZ: / @TF: / Modbus / Jetinno) by index [0], [1], ...
 * - Highlights any token that flipped since the previous poll in bright amber/cyan
 * - 1-click "Copy Frame Snapshot" copies structured telemetry JSON for protocol mapping
 */
export default function RawFrameInspector({
  theme,
  lang = 'en',
  liveData,
  statsData,
  selectedPort = '',
  liveBuild = '',
}) {
  const t = createTranslator(lang);
  const [expanded, setExpanded] = useState(false);
  const [copied, setCopied] = useState(false);
  const [changedIndices, setChangedIndices] = useState({});
  const prevTokensRef = useRef([]);
  const prevPortRef = useRef(selectedPort);

  const caps = liveData?.capabilities || {};
  const rawFrames = liveData?.raw_frames || {};
  const tokens = Array.isArray(rawFrames.tokens) ? rawFrames.tokens : [];
  const primaryCmd = rawFrames.primary_cmd || 'HZ:';
  const primaryRaw = rawFrames.primary_raw || liveData?.raw_status || '';
  const hasLiveFrame = caps.has_live_frame !== undefined ? Boolean(caps.has_live_frame) : Boolean(primaryRaw && primaryRaw !== 'N/A');

  useEffect(() => {
    if (prevPortRef.current !== selectedPort) {
      prevPortRef.current = selectedPort;
      prevTokensRef.current = [];
      setChangedIndices({});
      return;
    }
    const prev = prevTokensRef.current;
    if (prev.length > 0 && tokens.length > 0) {
      const diffs = {};
      tokens.forEach((tok, idx) => {
        if (prev[idx] !== undefined && prev[idx] !== tok) {
          diffs[idx] = prev[idx];
        }
      });
      if (Object.keys(diffs).length > 0) {
        setChangedIndices(diffs);
      }
    }
    prevTokensRef.current = tokens;
  }, [selectedPort, primaryRaw, tokens.join('|')]);

  const handleCopySnapshot = async (e) => {
    e.stopPropagation();
    const portType = selectedPort
      ? selectedPort.toUpperCase().startsWith('DEMO')
        ? 'DEMO'
        : selectedPort.toUpperCase().startsWith('COM')
        ? 'COM'
        : 'SERIAL'
      : 'NONE';

    const snapshot = {
      spectra_build: liveBuild || 'current',
      captured_at: new Date().toISOString(),
      port_type: portType,
      model: statsData?.identity?.model_name || statsData?.model_family || '',
      ef_code: caps.ef_code || statsData?.identity?.ef_code || '',
      protocol: liveData?.protocol || caps.protocol || '',
      capabilities: caps,
      raw_frames: rawFrames,
      switches: (liveData?.switches || []).map((sw) => ({
        id: sw.id,
        ok: sw.ok,
        badge: sw.badge,
        status: sw.status,
      })),
    };

    try {
      await navigator.clipboard.writeText(JSON.stringify(snapshot, null, 2));
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      // Clipboard fallback ignored if blocked
    }
  };

  const changedCount = Object.keys(changedIndices).length;

  return (
    <div className={`border rounded ${theme.surfaceClass} overflow-hidden`}>
      {/* Compact Header Strip */}
      <div
        role="button"
        tabIndex={0}
        onClick={() => setExpanded((v) => !v)}
        onKeyDown={(e) => {
          if (e.key === 'Enter' || e.key === ' ') {
            e.preventDefault();
            setExpanded((v) => !v);
          }
        }}
        className="w-full px-3.5 py-2 flex flex-wrap items-center justify-between gap-2 bg-black/40 hover:bg-black/60 transition-colors cursor-pointer select-none"
      >
        <div className="flex flex-wrap items-center gap-2 text-xs font-mono">
          {expanded ? (
            <ChevronDown className="w-3.5 h-3.5 text-sky-400" />
          ) : (
            <ChevronRight className="w-3.5 h-3.5 text-gray-400" />
          )}
          <Cpu className="w-3.5 h-3.5 text-sky-400" />
          <span className="font-bold text-gray-200 uppercase tracking-wider">
            {t('rawFrameTitle')}
          </span>
          <span
            className={`px-1.5 py-0.5 rounded text-[10px] font-bold border ${
              hasLiveFrame
                ? 'bg-emerald-950/70 border-emerald-700 text-emerald-300'
                : 'bg-amber-950/60 border-amber-700 text-amber-300'
            }`}
          >
            {hasLiveFrame ? t('rawFrameLive') : t('rawFrameNone')}
          </span>
          {caps.topology && (
            <span className="px-1.5 py-0.5 rounded text-[10px] bg-zinc-900 border border-zinc-700 text-zinc-300">
              {caps.topology}
            </span>
          )}
          {caps.ef_code && (
            <span className="px-1.5 py-0.5 rounded text-[10px] bg-sky-950/60 border border-sky-800 text-sky-300">
              {caps.ef_code}
            </span>
          )}
          {changedCount > 0 && (
            <span className="px-1.5 py-0.5 rounded text-[10px] bg-amber-950/80 border border-amber-500/70 text-amber-300 animate-pulse">
              {t('rawFrameDelta', { count: changedCount })}
            </span>
          )}
        </div>

        <button
          type="button"
          onClick={handleCopySnapshot}
          className="flex items-center space-x-1 px-2.5 py-0.5 rounded text-[11px] font-mono font-bold bg-sky-950/60 hover:bg-sky-900/70 border border-sky-700/70 text-sky-200 cursor-pointer transition-colors"
          title={t('rawFrameCopyTitle')}
        >
          {copied ? <Check className="w-3 h-3 text-emerald-400" /> : <Copy className="w-3 h-3" />}
          <span>{copied ? t('rawFrameCopied') : t('rawFrameCopyBtn')}</span>
        </button>
      </div>

      {/* Expanded Inspector Body */}
      {expanded && (
        <div className="p-3.5 space-y-3 border-t border-gray-800 text-xs font-mono">
          {/* Primary Raw Frame */}
          <div className="space-y-1">
            <div className="flex items-center justify-between text-[10px] text-gray-500 uppercase tracking-wider">
              <span>{t('rawFramePrimary', { cmd: primaryCmd })}</span>
              <span>{liveData?.protocol || caps.protocol || '---'}</span>
            </div>
            <div className="p-2 bg-black/70 border border-gray-800 rounded text-[11px] text-emerald-300 break-all select-text">
              {primaryRaw || t('rawFrameEmpty')}
            </div>
          </div>

          {/* Tokenized Fields with Live Delta Highlight */}
          {tokens.length > 0 && (
            <div className="space-y-1.5">
              <div className="text-[10px] text-gray-500 uppercase tracking-wider">
                {t('rawFrameTokensLabel', { count: tokens.length })}
              </div>
              <div className="flex flex-wrap gap-1.5">
                {tokens.map((tok, idx) => {
                  const prevVal = changedIndices[idx];
                  const isChanged = prevVal !== undefined;
                  return (
                    <div
                      key={idx}
                      className={`px-2 py-1 rounded border text-[11px] select-text transition-colors ${
                        isChanged
                          ? 'bg-amber-950/70 border-amber-400 text-amber-200 shadow-[0_0_8px_rgba(251,191,36,0.3)]'
                          : 'bg-black/50 border-gray-800 text-gray-200'
                      }`}
                      title={isChanged ? `Changed from "${prevVal}" to "${tok}"` : `Field [${idx}]`}
                    >
                      <span className="text-gray-500 mr-1">[{idx}]</span>
                      <span className="font-bold">{tok}</span>
                    </div>
                  );
                })}
              </div>
            </div>
          )}

          {/* Secondary Raw Frames (CS:, IC:, AS:) if present */}
          {(rawFrames.cs || rawFrames.ic || rawFrames.as) && (
            <div className="grid grid-cols-1 md:grid-cols-3 gap-2 pt-1 border-t border-gray-800/80 text-[10px]">
              {rawFrames.cs && (
                <div className="p-2 bg-black/50 border border-gray-800 rounded break-all select-text">
                  <div className="text-gray-500 mb-0.5">CS:</div>
                  <div className="text-sky-300">{rawFrames.cs}</div>
                </div>
              )}
              {rawFrames.ic && (
                <div className="p-2 bg-black/50 border border-gray-800 rounded break-all select-text">
                  <div className="text-gray-500 mb-0.5">IC:</div>
                  <div className="text-purple-300">{rawFrames.ic}</div>
                </div>
              )}
              {rawFrames.as && (
                <div className="p-2 bg-black/50 border border-gray-800 rounded break-all select-text">
                  <div className="text-gray-500 mb-0.5">AS:</div>
                  <div className="text-amber-300">{rawFrames.as}</div>
                </div>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
