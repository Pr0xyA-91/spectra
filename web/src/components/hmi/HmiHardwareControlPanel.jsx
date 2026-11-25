import React, { useState, useEffect, useRef } from 'react';
import {
  Download,
  Check,
  RefreshCw,
  Sparkles,
  Zap,
  Cpu,
  HardDrive,
  Play,
  Square,
  Trash2,
  ArrowDownCircle,
  Laptop,
  ChevronDown
} from 'lucide-react';

export default function HmiHardwareControlPanel({
  aiStatus,
  isLoadingAiStatus,
  onRefreshAiStatus,
  ollamaModel,
  setOllamaModel,
  onGlobalModelChange,
  effectiveModelCatalog,
  autoUnload,
  setAutoUnload,
  isOperatingOllama,
  onControlOllama,
  pullProgress,
  setPullProgress
}) {
  const [isModelDropdownOpen, setIsModelDropdownOpen] = useState(false);
  const [modelSearchQuery, setModelSearchQuery] = useState('');
  const modelDropdownRef = useRef(null);

  // Close model dropdown on outside click
  useEffect(() => {
    const handleOutsideClick = (e) => {
      if (modelDropdownRef.current && !modelDropdownRef.current.contains(e.target)) {
        setIsModelDropdownOpen(false);
      }
    };
    if (isModelDropdownOpen) {
      document.addEventListener('mousedown', handleOutsideClick);
    }
    return () => {
      document.removeEventListener('mousedown', handleOutsideClick);
    };
  }, [isModelDropdownOpen]);

  const activeModelId = ollamaModel || aiStatus?.hardware?.default_selected_model || 'qwen2.5:0.5b';
  const selectedModelMeta = effectiveModelCatalog.find((m) => m.id === activeModelId) || effectiveModelCatalog[0] || {
    id: activeModelId,
    name: activeModelId,
    min_ram_mb: 800,
    compatibility: 'RECOMMENDED',
  };

  return (
    <div className="p-3.5 bg-zinc-950/80 rounded border border-zinc-800 space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center space-x-2">
          <Laptop className="w-4 h-4 text-cyan-400" />
          <span className="text-xs font-bold text-gray-200 uppercase tracking-wider">
            Host Hardware Self-Check & Adaptive Model Selector
          </span>
          {aiStatus?.hardware?.tier && (
            <span className="px-2 py-0.5 text-[10px] font-bold rounded bg-cyan-950 text-cyan-300 border border-cyan-800 font-mono">
              [{aiStatus.hardware.tier}]
            </span>
          )}
        </div>

        <div className="flex items-center space-x-2">
          <button
            onClick={() => onRefreshAiStatus()}
            disabled={isLoadingAiStatus}
            className="flex items-center space-x-1 px-2.5 py-1 text-[11px] font-bold rounded bg-zinc-800 hover:bg-zinc-700 text-gray-200 border border-zinc-700 transition-all"
            title="Re-run live hardware telemetry detection"
          >
            <RefreshCw className={`w-3 h-3 ${isLoadingAiStatus ? 'animate-spin' : ''}`} />
            <span>{isLoadingAiStatus ? 'Detecting...' : '🔍 Self-Check Hardware'}</span>
          </button>
        </div>
      </div>

      {/* Hardware Telemetry Chips */}
      {aiStatus?.hardware && (
        <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-4 gap-2 text-[11px] font-mono">
          <div className="p-2 bg-black/50 border border-zinc-800/80 rounded space-y-0.5">
            <div className="text-[10px] text-gray-400 flex items-center space-x-1">
              <Cpu className="w-3 h-3 text-amber-400" />
              <span>CPU & SIMD</span>
            </div>
            <div className="text-gray-200 font-bold truncate" title={aiStatus.hardware.cpu.model}>
              {aiStatus.hardware.cpu.model}
            </div>
            <div className="text-[10px] text-gray-400">
              {aiStatus.hardware.cpu.logical_cores} Cores • AVX2: {aiStatus.hardware.cpu.has_avx2 ? '✅ YES' : '❌ NO'}
            </div>
          </div>

          <div className="p-2 bg-black/50 border border-zinc-800/80 rounded space-y-0.5">
            <div className="text-[10px] text-gray-400 flex items-center space-x-1">
              <Zap className="w-3 h-3 text-blue-400" />
              <span>MEMORY (RAM)</span>
            </div>
            <div className="text-gray-200 font-bold">
              {(aiStatus.hardware.memory.ram_available_mb / 1024).toFixed(1)} GB Available
            </div>
            <div className="text-[10px] text-gray-400">
              Total: {(aiStatus.hardware.memory.ram_total_mb / 1024).toFixed(1)} GB
            </div>
          </div>

          <div className="p-2 bg-black/50 border border-zinc-800/80 rounded space-y-0.5">
            <div className="text-[10px] text-gray-400 flex items-center space-x-1">
              <Sparkles className="w-3 h-3 text-purple-400" />
              <span>ACCELERATION</span>
            </div>
            <div className="text-gray-200 font-bold truncate" title={aiStatus.hardware.gpu.name}>
              {aiStatus.hardware.gpu.has_discrete_gpu ? 'Discrete GPU' : 'CPU Inference'}
            </div>
            <div className="text-[10px] text-gray-400 truncate" title={aiStatus.hardware.gpu.name}>
              {aiStatus.hardware.gpu.name}
            </div>
          </div>

          <div className="p-2 bg-black/50 border border-zinc-800/80 rounded space-y-0.5">
            <div className="text-[10px] text-gray-400 flex items-center space-x-1">
              <HardDrive className="w-3 h-3 text-emerald-400" />
              <span>DISK & DAEMON</span>
            </div>
            <div className="text-gray-200 font-bold">
              {aiStatus.hardware.disk.disk_free_gb} GB Free Disk
            </div>
            <div className="text-[10px] flex items-center justify-between">
              {aiStatus.ollama.available ? (
                <span className="text-emerald-400">● AI Engine Online</span>
              ) : (
                <span className="text-amber-400">○ AI Engine Offline</span>
              )}
              {aiStatus.ollama?.loaded_models && aiStatus.ollama.loaded_models.length > 0 ? (
                <span className="text-purple-400 font-mono text-[9px] truncate max-w-[110px]" title={aiStatus.ollama.loaded_models.map((m) => m.name || m).join(', ')}>
                  RAM: {aiStatus.ollama.loaded_models[0].name || aiStatus.ollama.loaded_models[0]}
                </span>
              ) : (
                <span className="text-gray-500 font-mono text-[9px]">RAM: Idle (0 loaded)</span>
              )}
            </div>
          </div>
        </div>
      )}

      {/* Model Selection & Embedded Ollama Controls */}
      <div className="p-2.5 bg-black/60 border border-zinc-800 rounded space-y-2.5">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div className="flex flex-wrap items-center gap-2 relative" ref={modelDropdownRef}>
            <span className="text-xs font-bold text-gray-300">Target Model:</span>

            {/* Custom Cyber Dropdown Trigger Button */}
            <button
              type="button"
              onClick={() => setIsModelDropdownOpen((prev) => !prev)}
              className="flex items-center space-x-2 bg-zinc-900 hover:bg-zinc-800 border border-zinc-700 hover:border-cyan-500 rounded px-2.5 py-1.5 text-gray-200 font-mono text-xs focus:outline-none focus:ring-1 focus:ring-cyan-500 transition-all shadow-sm cursor-pointer"
            >
              <Cpu className="w-3.5 h-3.5 text-cyan-400 shrink-0" />
              <span className="font-bold text-white tracking-tight">
                {selectedModelMeta.is_recommended ? '⭐ ' : ''}{selectedModelMeta.id}
              </span>
              <span className="text-[10px] text-gray-400 hidden sm:inline">
                ({selectedModelMeta.min_ram_mb} MB RAM)
              </span>
              {selectedModelMeta.is_installed && (
                <span className="px-1.5 py-0.2 text-[9px] font-bold rounded bg-purple-950 text-purple-300 border border-purple-700">
                  ✓ INSTALLED
                </span>
              )}
              <ChevronDown className={`w-3.5 h-3.5 text-gray-400 transition-transform duration-200 ${isModelDropdownOpen ? 'rotate-180 text-cyan-400' : ''}`} />
            </button>

            {/* Compatibility Badge for Currently Selected Model */}
            {selectedModelMeta.compatibility === 'RECOMMENDED' && (
              <span className="px-2 py-0.5 text-[10px] font-bold rounded bg-emerald-950 text-emerald-300 border border-emerald-700">
                ⭐ RECOMMENDED FOR THIS MACHINE
              </span>
            )}
            {selectedModelMeta.compatibility === 'COMPATIBLE' && (
              <span className="px-2 py-0.5 text-[10px] font-bold rounded bg-cyan-950 text-cyan-300 border border-cyan-700">
                ✅ COMPATIBLE
              </span>
            )}
            {selectedModelMeta.compatibility === 'HEAVY_FOR_CPU' && (
              <span className="px-2 py-0.5 text-[10px] font-bold rounded bg-amber-950 text-amber-300 border border-amber-700">
                ⚠️ HEAVY ON CPU
              </span>
            )}
            {selectedModelMeta.compatibility === 'INSUFFICIENT_RAM' && (
              <span className="px-2 py-0.5 text-[10px] font-bold rounded bg-red-950 text-red-300 border border-red-700">
                ❌ INSUFFICIENT RAM
              </span>
            )}
            {!selectedModelMeta.is_installed && !(aiStatus?.ollama?.models || []).includes(activeModelId) && !aiStatus?.download?.active && (
              <button
                type="button"
                disabled={isOperatingOllama}
                onClick={() => onControlOllama('pull_async', activeModelId)}
                className="flex items-center space-x-1 px-2 py-0.5 text-[10px] font-bold rounded bg-[#FCEE09] hover:bg-yellow-300 text-black disabled:opacity-40 cursor-pointer"
                title={`Download ${activeModelId} now`}
              >
                <Download className="w-3 h-3" />
                <span>Pull {activeModelId}</span>
              </button>
            )}

            {/* Custom Cyber Dropdown Popup Menu */}
            {isModelDropdownOpen && (
              <div className="absolute top-full left-0 mt-1.5 w-80 sm:w-96 bg-zinc-950 border border-cyan-500/60 rounded-md shadow-[0_10px_30px_rgba(0,0,0,0.85)] z-50 p-2 space-y-1.5 backdrop-blur-xl animate-in fade-in zoom-in-95 duration-150">
                <div className="flex items-center justify-between px-1.5 pb-1 border-b border-zinc-800 text-[10px] text-gray-400 font-mono">
                  <span className="font-bold text-cyan-300 uppercase tracking-wider">Select AI Model</span>
                  <span>{effectiveModelCatalog.length} models available</span>
                </div>

                {/* Search box for models */}
                <div className="relative">
                  <input
                    type="text"
                    value={modelSearchQuery}
                    onChange={(e) => setModelSearchQuery(e.target.value)}
                    placeholder="Filter models (e.g. qwen, 7b, llama)..."
                    className="w-full bg-black/80 border border-zinc-700 rounded px-2.5 py-1 text-xs text-gray-200 placeholder-zinc-500 focus:outline-none focus:border-cyan-500 font-mono"
                    autoFocus
                  />
                </div>

                {/* Model Options List */}
                <div className="max-h-64 overflow-y-auto space-y-1 pr-1 custom-scrollbar">
                  {effectiveModelCatalog
                    .filter((m) =>
                      !modelSearchQuery ||
                      m.id.toLowerCase().includes(modelSearchQuery.toLowerCase()) ||
                      m.name.toLowerCase().includes(modelSearchQuery.toLowerCase())
                    )
                    .map((m) => {
                      const isSelected = m.id === activeModelId;
                      return (
                        <button
                          key={m.id}
                          type="button"
                          onClick={() => {
                            setOllamaModel(m.id);
                            if (onGlobalModelChange) onGlobalModelChange(m.id);
                            try {
                              localStorage.setItem('spectra_ollama_model', m.id);
                            } catch {}
                            setIsModelDropdownOpen(false);
                          }}
                          className={`w-full text-left p-2 rounded transition-all flex items-start justify-between gap-2 text-xs font-mono border cursor-pointer ${
                            isSelected
                              ? 'bg-cyan-950/80 border-cyan-500 text-cyan-200 shadow-[0_0_8px_rgba(6,182,212,0.2)]'
                              : 'bg-zinc-900/60 hover:bg-zinc-800/90 border-zinc-800 hover:border-zinc-700 text-gray-300'
                          }`}
                        >
                          <div className="space-y-0.5 min-w-0">
                            <div className="flex items-center space-x-1.5 font-bold truncate">
                              {m.is_recommended && <span className="text-amber-400">⭐</span>}
                              <span className={isSelected ? 'text-cyan-300' : 'text-gray-100'}>{m.id}</span>
                              {m.is_installed && (
                                <span className="px-1.5 py-0.2 text-[9px] font-bold rounded bg-purple-950 text-purple-300 border border-purple-700">
                                  INSTALLED
                                </span>
                              )}
                            </div>
                            <div className="text-[10px] text-gray-400 truncate">{m.name}</div>
                            <div className="text-[9px] text-gray-500 flex items-center space-x-2">
                              <span>RAM: {m.min_ram_mb} MB</span>
                              <span>•</span>
                              <span>{m.speed_cpu || 'Fast'}</span>
                            </div>
                          </div>

                          <div className="flex flex-col items-end shrink-0 space-y-1">
                            {isSelected && <Check className="w-4 h-4 text-cyan-400" />}
                            {m.compatibility === 'RECOMMENDED' && (
                              <span className="text-[9px] font-bold text-emerald-400">OPTIMAL</span>
                            )}
                            {m.compatibility === 'HEAVY_FOR_CPU' && (
                              <span className="text-[9px] font-bold text-amber-400">HEAVY</span>
                            )}
                          </div>
                        </button>
                      );
                    })}
                </div>
              </div>
            )}
          </div>

          {/* Auto-unload toggle */}
          <label className="flex items-center space-x-1.5 text-xs text-gray-300 cursor-pointer">
            <input
              type="checkbox"
              checked={autoUnload}
              onChange={(e) => setAutoUnload(e.target.checked)}
              className="rounded bg-black/60 border-zinc-700 text-cyan-500 focus:ring-cyan-500"
            />
            <span>Auto-Unload Model from RAM after Audit</span>
            {aiStatus?.hardware?.auto_unload_recommended && (
              <span className="text-[10px] text-amber-400 font-mono">(Recommended)</span>
            )}
          </label>
        </div>

        {/* Action Buttons for Embedded Ollama Daemon */}
        <div className="flex flex-wrap items-center justify-between gap-2 pt-2 border-t border-zinc-800/80">
          <div className="flex flex-wrap items-center gap-1.5">
            <button
              onClick={() => onControlOllama('start')}
              disabled={isOperatingOllama || aiStatus?.ollama?.available}
              className="flex items-center space-x-1 px-2.5 py-1 text-xs font-bold rounded bg-emerald-900/60 hover:bg-emerald-800 text-emerald-200 border border-emerald-700 disabled:opacity-40 disabled:cursor-not-allowed transition-all"
            >
              <Play className="w-3 h-3 text-emerald-400" />
              <span>Start Engine</span>
            </button>

            <button
              onClick={() => onControlOllama('unload')}
              disabled={isOperatingOllama || !aiStatus?.ollama?.available}
              className="flex items-center space-x-1 px-2.5 py-1 text-xs font-bold rounded bg-amber-900/60 hover:bg-amber-800 text-amber-200 border border-amber-700 disabled:opacity-40 disabled:cursor-not-allowed transition-all"
            >
              <Trash2 className="w-3 h-3 text-amber-400" />
              <span>Unload RAM</span>
            </button>

            <button
              onClick={() => onControlOllama('stop')}
              disabled={isOperatingOllama || !aiStatus?.ollama?.available}
              className="flex items-center space-x-1 px-2.5 py-1 text-xs font-bold rounded bg-red-950/60 hover:bg-red-900 text-red-200 border border-red-800 disabled:opacity-40 disabled:cursor-not-allowed transition-all"
            >
              <Square className="w-3 h-3 text-red-400" />
              <span>Stop Engine</span>
            </button>

            <button
              onClick={() => onControlOllama('pull')}
              disabled={isOperatingOllama}
              className="flex items-center space-x-1 px-2.5 py-1 text-xs font-bold rounded bg-purple-900/60 hover:bg-purple-800 text-purple-200 border border-purple-700 disabled:opacity-40 disabled:cursor-not-allowed transition-all"
            >
              <ArrowDownCircle className="w-3 h-3 text-purple-400" />
              <span>Pull Selected Model</span>
            </button>
          </div>

          <div className="text-[11px] text-gray-400 font-mono">
            {isOperatingOllama ? (
              <span className="text-cyan-400 animate-pulse">Processing Local AI operation...</span>
            ) : aiStatus?.binary_installed ? (
              <span className="text-emerald-400">Local AI CLI detected</span>
            ) : (
              <span className="text-zinc-500">Local AI runtime not installed yet</span>
            )}
          </div>
        </div>

        {/* Real-Time Streaming Download Progress Panel */}
        {pullProgress && (pullProgress.active || pullProgress.status === 'COMPLETED' || pullProgress.status === 'ERROR' || pullProgress.status === 'CANCELLED') && (
          <div className="mt-3 p-3 bg-zinc-950/80 border border-cyan-500/40 rounded-lg space-y-2 font-mono">
            {/* Header Row */}
            <div className="flex flex-wrap items-center justify-between text-xs gap-2">
              <div className="flex items-center space-x-2">
                <span className={`w-2 h-2 rounded-full ${pullProgress.active ? 'bg-cyan-400 animate-pulse' : pullProgress.status === 'COMPLETED' ? 'bg-emerald-400' : 'bg-rose-400'}`} />
                <span className="font-bold text-cyan-300 uppercase tracking-wide">
                  {pullProgress.phase_label || 'Downloading'}
                </span>
                {pullProgress.status_text && (
                  <span className="text-zinc-400 text-[11px] truncate max-w-[340px]" title={pullProgress.status_text}>
                    — {pullProgress.status_text}
                  </span>
                )}
              </div>

              <div className="flex items-center space-x-3 text-xs">
                {pullProgress.speed_mbps > 0 && pullProgress.active && (
                  <span className="text-zinc-400">
                    ⚡ <strong className="text-zinc-200">{pullProgress.speed_mbps} MB/s</strong>
                  </span>
                )}
                {pullProgress.eta_sec > 0 && pullProgress.active && (
                  <span className="text-zinc-400">
                    ETA: <strong className="text-zinc-200">{pullProgress.eta_sec}s</strong>
                  </span>
                )}
                <span className="font-extrabold text-cyan-300 text-sm">
                  {pullProgress.percent !== undefined ? `${pullProgress.percent}%` : '0%'}
                </span>
              </div>
            </div>

            {/* Animated Visual Progress Bar */}
            <div className="h-3 rounded-full bg-black/90 border border-zinc-700 overflow-hidden shadow-inner relative">
              <div
                className={`h-full transition-all duration-300 ease-out ${
                  pullProgress.status === 'COMPLETED'
                    ? 'bg-gradient-to-r from-emerald-500 to-green-400'
                    : pullProgress.status === 'ERROR'
                    ? 'bg-rose-600'
                    : pullProgress.status === 'CANCELLED'
                    ? 'bg-amber-600'
                    : 'bg-gradient-to-r from-cyan-500 via-blue-500 to-emerald-400'
                }`}
                style={{ width: `${Math.min(100, Math.max(0, pullProgress.percent || 0))}%` }}
              />
            </div>

            {/* Byte Counter & Cancel Action */}
            <div className="flex items-center justify-between text-[11px] text-zinc-400 pt-0.5">
              <div>
                {pullProgress.total_bytes > 0 ? (
                  <span>
                    {(pullProgress.completed_bytes / (1024 * 1024)).toFixed(1)} MB / {(pullProgress.total_bytes / (1024 * 1024)).toFixed(1)} MB
                  </span>
                ) : (
                  <span>{pullProgress.status_text || 'Connecting...'}</span>
                )}
              </div>

              <div className="flex items-center space-x-2">
                {pullProgress.active && (
                  <button
                    onClick={() => onControlOllama('cancel_pull')}
                    className="px-2 py-0.5 rounded bg-rose-950/60 hover:bg-rose-900 border border-rose-700 text-rose-300 font-bold text-[10px] flex items-center space-x-1"
                  >
                    <Square className="w-2.5 h-2.5 fill-current" />
                    <span>Cancel Download</span>
                  </button>
                )}
                {!pullProgress.active && (
                  <button
                    onClick={() => setPullProgress(null)}
                    className="text-zinc-500 hover:text-zinc-300 text-[10px]"
                  >
                    Dismiss
                  </button>
                )}
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
