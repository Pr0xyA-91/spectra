import React, { useState, useEffect, useCallback } from 'react';
import {
  Settings,
  X,
  Power,
  Cpu,
  Download,
  Trash2,
  RefreshCw,
  Check,
  Copy,
  ExternalLink,
  Github,
  LogOut,
  Play,
  Square,
  Sliders,
  Database,
  Search,
  Upload
} from 'lucide-react';

export default function ConfigModal({
  isOpen,
  onClose,
  theme,
  aiEnabled,
  aiModel,
  aiSystem,
  aiDownload,
  autoUnload = true,
  statsData = null,
  onStatsUpdated = null,
  onToggleAi,
  onSaveAiConfig,
  onRefreshAiStatus,
  githubAuth,
  deviceFlow,
  patInput,
  setPatInput,
  copiedCode,
  authStatusMsg = null,
  onStartDeviceFlow,
  onSavePat,
  onLogout,
  onCancelDeviceFlow,
  onCopyDeviceCode
}) {
  const [activeSection, setActiveSection] = useState('ai');
  const [pullModelInput, setPullModelInput] = useState('gemma3:1b');
  const [ollamaBusy, setOllamaBusy] = useState(false);
  const [isPullPolling, setIsPullPolling] = useState(false);
  const [statusBanner, setStatusBanner] = useState({ msg: '', error: false });

  // Machine Library state
  const [machineCatalog, setMachineCatalog] = useState([]);
  const [connectedMatch, setConnectedMatch] = useState(null);
  const [libraryStats, setLibraryStats] = useState({ total_machines: 0, verified_specs_count: 0, local_overrides_count: 0 });
  const [librarySearch, setLibrarySearch] = useState('');
  const [expandedMachineId, setExpandedMachineId] = useState('');
  const [isLoadingLibrary, setIsLoadingLibrary] = useState(false);

  // Overrides & Calibration state
  const [overrides, setOverrides] = useState({});
  const [beanCalib, setBeanCalib] = useState({ threshold: 115, min_threshold: 30, max_threshold: 250 });
  const [thresholdInput, setThresholdInput] = useState(115);

  const loadOverridesAndCalib = useCallback(async () => {
    try {
      const [ovRes, calRes] = await Promise.all([
        fetch('/api/offsets/overrides'),
        fetch('/api/calibration')
      ]);
      if (ovRes.ok) {
        const ovData = await ovRes.json();
        if (ovData.success) setOverrides(ovData.overrides || {});
      }
      if (calRes.ok) {
        const calData = await calRes.json();
        if (typeof calData.threshold === 'number') {
          setBeanCalib(calData);
          setThresholdInput(calData.threshold);
        }
      }
    } catch {}
  }, []);

  const loadMachineLibrary = useCallback(async () => {
    setIsLoadingLibrary(true);
    try {
      const qs = new URLSearchParams();
      if (statsData?.ef_code) qs.set('ef', statsData.ef_code);
      if (statsData?.article_number) qs.set('art', String(statsData.article_number));
      if (statsData?.model_name || statsData?.model_family) qs.set('model', statsData.model_name || statsData.model_family);
      const res = await fetch(`/api/machines?${qs.toString()}`);
      if (res.ok) {
        const data = await res.json();
        if (data.success) {
          setMachineCatalog(data.machines || []);
          setConnectedMatch(data.connected_match || null);
          setLibraryStats({
            total_machines: data.total_machines || 0,
            verified_specs_count: data.verified_specs_count || 0,
            local_overrides_count: data.local_overrides_count || 0,
          });
        }
      }
    } catch {}
    finally {
      setIsLoadingLibrary(false);
    }
  }, [statsData?.ef_code, statsData?.article_number, statsData?.model_name, statsData?.model_family]);

  useEffect(() => {
    if (!isOpen) return;
    if (onRefreshAiStatus) onRefreshAiStatus();
    loadOverridesAndCalib();
    loadMachineLibrary();
  }, [isOpen, onRefreshAiStatus, loadOverridesAndCalib, loadMachineLibrary]);

  // Live poll while portable engine install or model download is active
  useEffect(() => {
    if (!isOpen) return;
    const active = Boolean(aiDownload?.active || isPullPolling);
    if (!active) return;

    const timer = setInterval(async () => {
      if (onRefreshAiStatus) await onRefreshAiStatus();
    }, 650);

    return () => clearInterval(timer);
  }, [isOpen, aiDownload?.active, isPullPolling, onRefreshAiStatus]);

  useEffect(() => {
    if (!isPullPolling) return;
    if (!aiDownload?.active && ['COMPLETED', 'ERROR', 'CANCELLED'].includes(aiDownload?.status)) {
      setIsPullPolling(false);
      if (aiDownload.status === 'COMPLETED') {
        setStatusBanner({
          msg: aiDownload.status_text || `Model '${aiDownload.model || pullModelInput}' installed and ready.`,
          error: false,
        });
      } else if (aiDownload.status === 'ERROR') {
        setStatusBanner({
          msg: aiDownload.error || aiDownload.status_text || 'Model installation failed.',
          error: true,
        });
      } else if (aiDownload.status === 'CANCELLED') {
        setStatusBanner({ msg: 'Download cancelled.', error: true });
      }
    }
  }, [aiDownload, isPullPolling, pullModelInput]);

  if (!isOpen) return null;

  const ollamaInfo = aiSystem?.ollama || {};
  const hardware = aiSystem?.hardware || {};
  const installedModels = Array.isArray(ollamaInfo.models) ? ollamaInfo.models : [];
  const loadedModels = Array.isArray(ollamaInfo.loaded_models) ? ollamaInfo.loaded_models : [];
  const catalog = Array.isArray(hardware.model_catalog) ? hardware.model_catalog : [];

  // Combine installed models + catalog entries for the Default Model selector
  const selectableModels = Array.from(
    new Set([
      ...installedModels,
      ...catalog.map((c) => c.id),
      ...(aiModel ? [aiModel] : [])
    ])
  );

  const runOllamaAction = async (action, model = null) => {
    setOllamaBusy(true);
    setStatusBanner({ msg: '', error: false });
    try {
      const res = await fetch('/api/hmi/ai/control', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ action, model })
      });
      const data = await res.json();
      const outcome = (data && data.result && typeof data.result === 'object') ? data.result : data;
      const errStatuses = ['ERROR', 'BINARY_NOT_FOUND', 'START_TIMEOUT', 'OLLAMA_OFFLINE'];
      const isErr = !res.ok || data.is_error || errStatuses.includes(outcome?.status);

      if (isErr) {
        setStatusBanner({ msg: outcome?.message || data?.error || `Action '${action}' failed.`, error: true });
      } else {
        setStatusBanner({ msg: outcome?.message || `Completed: ${action}`, error: false });
      }

      if (action === 'pull_async' || action === 'pull') {
        setIsPullPolling(true);
      }
      if (onRefreshAiStatus) await onRefreshAiStatus();
    } catch (err) {
      setStatusBanner({ msg: `Local AI error: ${err.message}`, error: true });
    } finally {
      setOllamaBusy(false);
    }
  };

  const handleImportPatchFile = async (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    try {
      const text = await file.text();
      const res = await fetch('/api/machines/import', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ payload: text }),
      });
      const data = await res.json();
      if (!res.ok || !data.success) {
        setStatusBanner({ msg: data.error || 'Failed to import offset patch.', error: true });
      } else {
        setMachineCatalog(data.machines || []);
        setConnectedMatch(data.connected_match || null);
        setLibraryStats({
          total_machines: data.total_machines || 0,
          verified_specs_count: data.verified_specs_count || 0,
          local_overrides_count: data.local_overrides_count || 0,
        });
        if (data.updated_stats && onStatsUpdated) onStatsUpdated(data.updated_stats);
        loadOverridesAndCalib();
        setStatusBanner({ msg: data.message || 'Offset patch imported into Machine Library.', error: false });
      }
    } catch (err) {
      setStatusBanner({ msg: `Import error: ${err.message}`, error: true });
    } finally {
      e.target.value = '';
    }
  };

  const handleExportMachinePatch = async (machine) => {
    const override = {
      ef_code: machine.ef_code,
      article_number: (machine.article_numbers || [])[0] || '',
      model_name: machine.model_family,
      products: machine.offsets?.products || [],
      maintenance: machine.offsets?.maintenance || [],
      maintenance_pct: machine.offsets?.maintenance_pct || [],
      notes: machine.notes || `Exported from SPECTRA Machine Library (${machine.active_source})`,
    };
    try {
      const res = await fetch('/api/offsets/export_patch', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ override, save_dialog: true }),
      });
      const data = await res.json();
      if (data.dialog_unavailable && data.patch_json) {
        const blob = new Blob([data.patch_json], { type: 'application/json' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = data.filename || 'spectra_offset_patch.json';
        document.body.appendChild(a);
        a.click();
        a.remove();
        URL.revokeObjectURL(url);
        setStatusBanner({ msg: `Downloaded ${data.filename}`, error: false });
      } else if (data.success) {
        setStatusBanner({ msg: `Exported patch to ${data.saved_path || data.filename}`, error: false });
      } else if (!data.cancelled) {
        setStatusBanner({ msg: data.error || 'Failed to export offset patch.', error: true });
      }
    } catch (err) {
      setStatusBanner({ msg: `Export error: ${err.message}`, error: true });
    }
  };

  const handleSelectDefaultModel = async (nextModel) => {
    setStatusBanner({ msg: '', error: false });
    if (onSaveAiConfig) {
      await onSaveAiConfig({ model: nextModel, auto_unload: autoUnload });
      setStatusBanner({ msg: `Default AI model set to '${nextModel}'.`, error: false });
    }
  };

  const handleDeleteOverride = async (key) => {
    try {
      const res = await fetch('/api/offsets/delete', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ key })
      });
      const data = await res.json();
      if (data.success) {
        setOverrides(data.overrides || {});
        setStatusBanner({ msg: `Removed local offset override '${key}'.`, error: false });
      }
    } catch (err) {
      setStatusBanner({ msg: err.message, error: true });
    }
  };

  const handleSaveThreshold = async () => {
    try {
      const res = await fetch('/api/set_threshold', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ threshold: Number(thresholdInput) })
      });
      const data = await res.json();
      if (data.success) {
        setBeanCalib(data.calib || beanCalib);
        setThresholdInput(data.threshold);
        setStatusBanner({ msg: `Saved optical bean threshold (${data.threshold}).`, error: false });
      }
    } catch (err) {
      setStatusBanner({ msg: err.message, error: true });
    }
  };

  const handleResetThreshold = async () => {
    try {
      const res = await fetch('/api/reset_threshold', { method: 'POST' });
      const data = await res.json();
      if (data.success) {
        setBeanCalib(data.calib || beanCalib);
        setThresholdInput(data.threshold);
        setStatusBanner({ msg: `Reset optical bean threshold to default (${data.threshold}).`, error: false });
      }
    } catch (err) {
      setStatusBanner({ msg: err.message, error: true });
    }
  };

  const overrideEntries = Object.entries(overrides || {});

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/75 backdrop-blur-sm p-4">
      <div className={`w-full max-w-2xl border ${theme.border} ${theme.panelBg} rounded-lg shadow-2xl flex flex-col max-h-[90vh] font-mono`}>
        {/* Header */}
        <div className="flex items-center justify-between px-5 py-3 border-b border-zinc-800">
          <div className="flex items-center space-x-2">
            <Settings className="w-4 h-4 text-[#FCEE09]" />
            <span className="text-sm font-extrabold text-white tracking-wider uppercase">
              SPECTRA CONFIGURATION &amp; AI ENGINE
            </span>
          </div>
          <button
            onClick={onClose}
            className="text-zinc-400 hover:text-white p-1 rounded hover:bg-zinc-800 cursor-pointer"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Navigation Tabs */}
        <div className="flex flex-wrap border-b border-zinc-800 bg-black/30 px-4 pt-2 gap-1.5 text-xs">
          <button
            type="button"
            onClick={() => setActiveSection('ai')}
            className={`px-3 py-1.5 rounded-t font-bold flex items-center space-x-1.5 border-b-2 transition-colors cursor-pointer ${
              activeSection === 'ai'
                ? 'border-[#00F0FF] text-[#00F0FF] bg-cyan-950/20'
                : 'border-transparent text-zinc-400 hover:text-zinc-200'
            }`}
          >
            <Cpu className="w-3.5 h-3.5" />
            <span>Local AI &amp; Models</span>
          </button>
          <button
            type="button"
            onClick={() => setActiveSection('library')}
            className={`px-3 py-1.5 rounded-t font-bold flex items-center space-x-1.5 border-b-2 transition-colors cursor-pointer ${
              activeSection === 'library'
                ? 'border-purple-400 text-purple-300 bg-purple-950/20'
                : 'border-transparent text-zinc-400 hover:text-zinc-200'
            }`}
          >
            <Database className="w-3.5 h-3.5" />
            <span>Machine Library ({libraryStats.total_machines || machineCatalog.length})</span>
          </button>
          <button
            type="button"
            onClick={() => setActiveSection('github')}
            className={`px-3 py-1.5 rounded-t font-bold flex items-center space-x-1.5 border-b-2 transition-colors cursor-pointer ${
              activeSection === 'github'
                ? 'border-[#FCEE09] text-[#FCEE09] bg-yellow-950/15'
                : 'border-transparent text-zinc-400 hover:text-zinc-200'
            }`}
          >
            <Github className="w-3.5 h-3.5" />
            <span>GitHub Connection</span>
          </button>
          <button
            type="button"
            onClick={() => setActiveSection('calibration')}
            className={`px-3 py-1.5 rounded-t font-bold flex items-center space-x-1.5 border-b-2 transition-colors cursor-pointer ${
              activeSection === 'calibration'
                ? 'border-emerald-400 text-emerald-400 bg-emerald-950/15'
                : 'border-transparent text-zinc-400 hover:text-zinc-200'
            }`}
          >
            <Sliders className="w-3.5 h-3.5" />
            <span>Overrides &amp; Calibration</span>
          </button>
        </div>

        {/* Status Feedback */}
        {statusBanner.msg && (
          <div
            className={`mx-5 mt-3 px-3 py-2 rounded text-[11px] border ${
              statusBanner.error
                ? 'bg-red-950/50 border-red-800 text-red-300'
                : 'bg-emerald-950/40 border-emerald-800 text-emerald-300'
            }`}
          >
            {statusBanner.msg}
          </div>
        )}

        {/* Body */}
        <div className="p-5 overflow-y-auto space-y-4 text-xs">
          {/* SECTION 1: LOCAL AI & MODELS */}
          {activeSection === 'ai' && (
            <div className="space-y-4">
              {/* Master AI Power Card */}
              <div className="p-3.5 bg-black/40 border border-zinc-800 rounded space-y-3">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <div>
                    <div className="font-bold text-white flex items-center gap-2">
                      <span>Global Local AI Engine</span>
                      <span
                        className={`text-[10px] px-1.5 py-0.5 rounded font-bold ${
                          aiEnabled
                            ? 'bg-emerald-950 text-emerald-400 border border-emerald-700'
                            : 'bg-zinc-900 text-zinc-400 border border-zinc-700'
                        }`}
                      >
                        {aiEnabled ? 'ON (OPT-IN ACTIVE)' : 'OFF (DEFAULT • 0 CPU/RAM)'}
                      </span>
                    </div>
                    <div className="text-[11px] text-zinc-400 mt-0.5">
                      Local AI Runtime (127.0.0.1:11434):{' '}
                      <strong className={ollamaInfo.available ? 'text-emerald-400' : 'text-zinc-400'}>
                        {ollamaInfo.available ? 'ONLINE' : aiSystem?.binary_installed ? 'STOPPED (IDLE)' : 'NOT INSTALLED (AUTO-INSTALL READY)'}
                      </strong>
                      {hardware?.memory?.ram_total_mb ? (
                        <span className="text-zinc-500">
                          {' '}
                          • RAM: {Math.round(hardware.memory.ram_total_mb / 1024)} GB ({hardware.tier || 'CPU'})
                        </span>
                      ) : null}
                    </div>
                  </div>

                  <button
                    type="button"
                    onClick={() => onToggleAi(!aiEnabled)}
                    className={`px-3 py-1.5 rounded font-extrabold text-[11px] flex items-center space-x-1.5 border cursor-pointer ${
                      aiEnabled
                        ? 'bg-red-950/70 hover:bg-red-900/80 border-red-600 text-red-200'
                        : 'bg-purple-700 hover:bg-purple-600 border-purple-400 text-white'
                    }`}
                  >
                    <Power className="w-3.5 h-3.5" />
                    <span>{aiEnabled ? 'TURN AI OFF' : 'ENABLE LOCAL AI'}</span>
                  </button>
                </div>

                {/* Runtime Controls */}
                <div className="flex flex-wrap items-center gap-2 pt-2 border-t border-zinc-800/70">
                  <button
                    type="button"
                    disabled={ollamaBusy}
                    onClick={() => runOllamaAction('start')}
                    className="px-2.5 py-1 bg-zinc-800 hover:bg-zinc-700 disabled:opacity-40 border border-zinc-700 text-emerald-300 rounded text-[11px] font-bold flex items-center gap-1 cursor-pointer"
                  >
                    <Play className="w-3 h-3" />
                    <span>Start Engine</span>
                  </button>
                  <button
                    type="button"
                    disabled={ollamaBusy}
                    onClick={() => runOllamaAction('unload')}
                    className="px-2.5 py-1 bg-zinc-800 hover:bg-zinc-700 disabled:opacity-40 border border-zinc-700 text-amber-300 rounded text-[11px] font-bold cursor-pointer"
                  >
                    Unload RAM
                  </button>
                  <button
                    type="button"
                    disabled={ollamaBusy}
                    onClick={() => runOllamaAction('stop')}
                    className="px-2.5 py-1 bg-zinc-800 hover:bg-zinc-700 disabled:opacity-40 border border-zinc-700 text-rose-300 rounded text-[11px] font-bold flex items-center gap-1 cursor-pointer"
                  >
                    <Square className="w-3 h-3" />
                    <span>Stop Engine</span>
                  </button>
                  <button
                    type="button"
                    disabled={ollamaBusy}
                    onClick={() => onRefreshAiStatus && onRefreshAiStatus()}
                    className="ml-auto px-2.5 py-1 bg-zinc-900 hover:bg-zinc-800 border border-zinc-700 text-zinc-300 rounded text-[11px] flex items-center gap-1 cursor-pointer"
                  >
                    <RefreshCw className={`w-3 h-3 ${ollamaBusy ? 'animate-spin' : ''}`} />
                    <span>Refresh</span>
                  </button>
                </div>
              </div>

              {/* Global Default Model Selector */}
              <div className="p-3.5 bg-black/40 border border-zinc-800 rounded space-y-2.5">
                <div className="flex items-center justify-between">
                  <label className="font-bold text-white uppercase text-[11px]">
                    Default Model (Shared Across All SPECTRA Tools)
                  </label>
                  {hardware?.recommended_model && (
                    <span className="text-[10px] text-cyan-400">
                      Recommended: {hardware.recommended_model}
                    </span>
                  )}
                </div>

                <select
                  value={aiModel || hardware?.default_selected_model || selectableModels[0] || ''}
                  onChange={(e) => handleSelectDefaultModel(e.target.value)}
                  className="w-full bg-zinc-950 border border-zinc-700 rounded px-2.5 py-2 text-xs text-white outline-none focus:border-[#00F0FF]"
                >
                  {selectableModels.map((mId) => {
                    const cat = catalog.find((c) => c.id === mId);
                    const isInstalled = installedModels.includes(mId);
                    const tagParts = [
                      isInstalled ? 'INSTALLED' : 'NOT PULLED',
                      cat?.is_recommended ? 'RECOMMENDED' : cat?.compatibility || ''
                    ].filter(Boolean);
                    return (
                      <option key={mId} value={mId}>
                        {cat ? `${cat.name} [${mId}]` : mId} — {tagParts.join(' • ')}
                      </option>
                    );
                  })}
                </select>

                <label className="flex items-center space-x-2 text-[11px] text-zinc-300 cursor-pointer pt-1">
                  <input
                    type="checkbox"
                    checked={Boolean(autoUnload)}
                    onChange={(e) =>
                      onSaveAiConfig && onSaveAiConfig({ model: aiModel, auto_unload: e.target.checked })
                    }
                    className="rounded bg-black border-zinc-700 text-cyan-500"
                  />
                  <span>Auto-unload model weights from RAM immediately after each task finishes</span>
                </label>
              </div>

              {/* Manage Installed Local Models + Pull New */}
              <div className="p-3.5 bg-black/40 border border-zinc-800 rounded space-y-3">
                <div className="font-bold text-white uppercase text-[11px]">
                  Local Models ({installedModels.length} Installed)
                </div>

                {installedModels.length === 0 ? (
                  <div className="p-2.5 bg-zinc-950/70 border border-zinc-800 rounded text-[11px] text-zinc-400">
                    No local AI models installed yet. Click <strong>Pull Model</strong> below — SPECTRA will automatically install the portable engine and download your selected model tag (e.g. <span className="text-cyan-300">gemma3:1b</span>, <span className="text-cyan-300">qwen2.5:0.5b</span>, or <span className="text-purple-300">gemma3:4b</span> for screenshot OCR).
                  </div>
                ) : (
                  <div className="max-h-40 overflow-y-auto space-y-1.5 pr-1">
                    {installedModels.map((m) => {
                      const isLoaded = loadedModels.includes(m);
                      const isDefault = m === aiModel;
                      return (
                        <div
                          key={m}
                          className="flex items-center justify-between gap-2 px-2.5 py-1.5 bg-zinc-950 border border-zinc-800 rounded text-[11px]"
                        >
                          <div className="flex items-center gap-2 min-w-0">
                            <span className="text-zinc-100 font-bold truncate">{m}</span>
                            {isDefault && (
                              <span className="px-1.5 py-0.5 bg-cyan-950 text-cyan-300 border border-cyan-700 rounded text-[9px] font-bold">
                                DEFAULT
                              </span>
                            )}
                            {isLoaded && (
                              <span className="px-1.5 py-0.5 bg-emerald-950 text-emerald-300 border border-emerald-700 rounded text-[9px] font-bold animate-pulse">
                                IN RAM
                              </span>
                            )}
                          </div>
                          <div className="flex items-center gap-1.5 shrink-0">
                            {!isDefault && (
                              <button
                                type="button"
                                onClick={() => handleSelectDefaultModel(m)}
                                className="px-2 py-0.5 bg-zinc-800 hover:bg-zinc-700 text-cyan-300 rounded text-[10px] font-bold cursor-pointer"
                              >
                                Use
                              </button>
                            )}
                            {isLoaded && (
                              <button
                                type="button"
                                disabled={ollamaBusy}
                                onClick={() => runOllamaAction('unload', m)}
                                className="px-2 py-0.5 bg-amber-950/60 hover:bg-amber-900/70 border border-amber-700 text-amber-300 rounded text-[10px] font-bold cursor-pointer"
                              >
                                Unload
                              </button>
                            )}
                            <button
                              type="button"
                              disabled={ollamaBusy}
                              onClick={() => runOllamaAction('delete', m)}
                              className="p-1 text-rose-400 hover:text-rose-300 hover:bg-rose-950/40 rounded cursor-pointer"
                              title={`Delete ${m} from disk`}
                            >
                              <Trash2 className="w-3.5 h-3.5" />
                            </button>
                          </div>
                        </div>
                      );
                    })}
                  </div>
                )}

                {/* Download / Pull New Model */}
                <div className="pt-2 border-t border-zinc-800/80 space-y-2">
                  <div className="text-[11px] text-zinc-400 font-bold uppercase">Download / Pull Model Tag (Auto-Installs Engine):</div>
                  <div className="flex gap-2">
                    <input
                      type="text"
                      value={pullModelInput}
                      onChange={(e) => setPullModelInput(e.target.value)}
                      placeholder="e.g. gemma3:1b, gemma3:4b, qwen2.5:0.5b"
                      className="flex-1 bg-zinc-950 border border-zinc-700 rounded px-2.5 py-1.5 text-xs text-white outline-none focus:border-[#00F0FF]"
                    />
                    {aiDownload?.active ? (
                      <button
                        type="button"
                        onClick={() => runOllamaAction('cancel_pull')}
                        className="px-3 py-1.5 bg-red-700 hover:bg-red-600 text-white font-bold rounded text-xs cursor-pointer"
                      >
                        Cancel Pull
                      </button>
                    ) : (
                      <button
                        type="button"
                        disabled={ollamaBusy || !pullModelInput.trim()}
                        onClick={() => runOllamaAction('pull_async', pullModelInput.trim())}
                        className="px-3 py-1.5 bg-cyan-700 hover:bg-cyan-600 disabled:opacity-40 text-white font-bold rounded text-xs flex items-center gap-1.5 cursor-pointer"
                      >
                        <Download className="w-3.5 h-3.5" />
                        <span>Pull Model</span>
                      </button>
                    )}
                  </div>
                  <div className="flex flex-wrap gap-1.5">
                    {['qwen2.5:0.5b', 'gemma3:1b', 'qwen2.5:1.5b', 'gemma2:2b', 'gemma3:4b', 'qwen2.5:3b'].map((preset) => (
                      <button
                        key={preset}
                        type="button"
                        onClick={() => setPullModelInput(preset)}
                        className={`px-2 py-0.5 border rounded text-[10px] cursor-pointer ${
                          pullModelInput === preset
                            ? 'bg-cyan-950/70 border-cyan-500 text-cyan-200 font-bold'
                            : 'bg-zinc-900 hover:bg-zinc-800 border-zinc-700 text-zinc-300'
                        }`}
                      >
                        {preset}{preset === 'gemma3:4b' ? ' (Vision)' : ''}
                      </button>
                    ))}
                  </div>

                  {/* Live Inline Engine Install & Model Download Progress */}
                  {aiDownload && (aiDownload.active || ['COMPLETED', 'ERROR', 'CANCELLED'].includes(aiDownload.status)) && (
                    <div className="mt-2 p-3 bg-zinc-950/90 border border-cyan-500/40 rounded space-y-1.5">
                      <div className="flex items-center justify-between text-[11px]">
                        <span className="font-bold text-cyan-300">
                          {aiDownload.phase_label || 'Installing Local AI...'}
                        </span>
                        <span className="text-zinc-300 font-bold">
                          {Math.round(aiDownload.percent || 0)}%
                        </span>
                      </div>
                      <div className="w-full h-2 bg-zinc-800 rounded-full overflow-hidden">
                        <div
                          className={`h-full transition-all duration-300 ${
                            aiDownload.status === 'ERROR'
                              ? 'bg-rose-500'
                              : aiDownload.status === 'COMPLETED'
                              ? 'bg-emerald-500'
                              : 'bg-gradient-to-r from-cyan-500 to-purple-500'
                          }`}
                          style={{ width: `${Math.max(4, Math.min(100, aiDownload.percent || 0))}%` }}
                        />
                      </div>
                      <div className="flex items-center justify-between text-[10px] text-zinc-400">
                        <span className="truncate pr-2">
                          {aiDownload.error || aiDownload.status_text || 'Working...'}
                        </span>
                        {aiDownload.active && aiDownload.speed_mbps > 0 && (
                          <span className="shrink-0 text-cyan-400">
                            {aiDownload.speed_mbps} MB/s {aiDownload.eta_sec > 0 ? `• ETA ${aiDownload.eta_sec}s` : ''}
                          </span>
                        )}
                      </div>
                    </div>
                  )}
                </div>
              </div>
            </div>
          )}

          {/* SECTION 1b: UNIFIED MACHINE LIBRARY */}
          {activeSection === 'library' && (
            <div className="space-y-3">
              <div className="p-3 bg-black/40 border border-zinc-800 rounded flex flex-wrap items-center justify-between gap-2">
                <div>
                  <div className="font-bold text-white flex items-center gap-2">
                    <Database className="w-4 h-4 text-purple-400" />
                    <span>Unified SPECTRA Machine Offset Library</span>
                  </div>
                  <div className="text-[10px] text-zinc-400 mt-0.5">
                    {libraryStats.total_machines} machines indexed • {libraryStats.verified_specs_count} verified specs •{' '}
                    <span className="text-emerald-400">{libraryStats.local_overrides_count} local/imported fixes</span>
                  </div>
                </div>
                <div className="flex items-center gap-2">
                  <label className="px-2.5 py-1 bg-purple-900/60 hover:bg-purple-800 border border-purple-500/60 text-purple-200 rounded text-[11px] font-bold flex items-center gap-1 cursor-pointer">
                    <Upload className="w-3.5 h-3.5" />
                    <span>Import Patch (.json)</span>
                    <input type="file" accept=".json,application/json" onChange={handleImportPatchFile} className="hidden" />
                  </label>
                  <button
                    type="button"
                    onClick={loadMachineLibrary}
                    disabled={isLoadingLibrary}
                    className="px-2 py-1 bg-zinc-900 hover:bg-zinc-800 border border-zinc-700 text-zinc-300 rounded text-[11px] flex items-center gap-1 cursor-pointer"
                  >
                    <RefreshCw className={`w-3 h-3 ${isLoadingLibrary ? 'animate-spin' : ''}`} />
                  </button>
                </div>
              </div>

              {connectedMatch && (
                <div className="p-3 bg-emerald-950/30 border border-emerald-500/60 rounded space-y-1.5">
                  <div className="flex items-center justify-between text-[11px]">
                    <span className="font-bold text-emerald-300">
                      CONNECTED MACHINE MATCH: {connectedMatch.model_family} ({connectedMatch.ef_code || 'No EF'})
                    </span>
                    <span className="px-2 py-0.5 bg-emerald-950 border border-emerald-600 text-emerald-300 rounded text-[10px] font-bold">
                      {connectedMatch.active_source}
                    </span>
                  </div>
                  <div className="text-[10px] text-zinc-300">
                    Products: {connectedMatch.product_count} • Maintenance: {connectedMatch.maintenance_count}
                    {connectedMatch.article_numbers?.length > 0 && ` • Articles: ${connectedMatch.article_numbers.slice(0, 6).join(', ')}`}
                  </div>
                </div>
              )}

              <div className="relative">
                <Search className="w-3.5 h-3.5 text-zinc-500 absolute left-2.5 top-2.5" />
                <input
                  type="text"
                  value={librarySearch}
                  onChange={(e) => setLibrarySearch(e.target.value)}
                  placeholder="Search by EF code (e.g. EF634), model (ENA 7, WE8, Z10), or article number..."
                  className="w-full bg-zinc-950 border border-zinc-700 rounded pl-8 pr-3 py-1.5 text-xs text-white outline-none focus:border-purple-400"
                />
              </div>

              <div className="max-h-72 overflow-y-auto space-y-1.5 pr-1">
                {machineCatalog
                  .filter((m) => {
                    const q = librarySearch.trim().toLowerCase();
                    if (!q) return true;
                    return (
                      (m.ef_code || '').toLowerCase().includes(q) ||
                      (m.model_family || '').toLowerCase().includes(q) ||
                      (m.active_source || '').toLowerCase().includes(q) ||
                      (m.article_numbers || []).some((a) => String(a).toLowerCase().includes(q))
                    );
                  })
                  .slice(0, 80)
                  .map((m) => {
                    const isOpenRow = expandedMachineId === m.id;
                    const hasOffsets = (m.offsets?.products?.length || 0) + (m.offsets?.maintenance?.length || 0) > 0;
                    return (
                      <div key={m.id} className="bg-zinc-950 border border-zinc-800 rounded p-2.5 space-y-2 text-[11px]">
                        <div className="flex items-center justify-between gap-2">
                          <button
                            type="button"
                            onClick={() => setExpandedMachineId(isOpenRow ? '' : m.id)}
                            className="text-left flex-1 min-w-0 cursor-pointer"
                          >
                            <div className="flex items-center gap-2 flex-wrap">
                              <span className="font-bold text-white">{m.model_family}</span>
                              {m.ef_code && (
                                <span className="px-1.5 py-0.5 bg-zinc-900 border border-zinc-700 rounded text-[10px] text-cyan-300">
                                  {m.ef_code}
                                </span>
                              )}
                              <span
                                className={`px-1.5 py-0.5 rounded text-[9px] font-bold border ${
                                  m.has_local_override
                                    ? 'bg-emerald-950 text-emerald-300 border-emerald-700'
                                    : m.has_verified_spec
                                    ? 'bg-purple-950 text-purple-300 border-purple-700'
                                    : 'bg-zinc-900 text-zinc-400 border-zinc-700'
                                }`}
                              >
                                {m.active_source}
                              </span>
                              {m.is_connected_match && (
                                <span className="px-1.5 py-0.5 bg-sky-950 border border-sky-600 text-sky-300 rounded text-[9px] font-bold">
                                  ACTIVE
                                </span>
                              )}
                            </div>
                            <div className="text-[10px] text-zinc-400 mt-0.5">
                              {m.product_count} products • {m.maintenance_count} maintenance
                              {m.article_numbers?.length > 0 ? ` • Art: ${m.article_numbers.slice(0, 4).join(', ')}` : ''}
                            </div>
                          </button>
                          {hasOffsets && (
                            <button
                              type="button"
                              onClick={() => handleExportMachinePatch(m)}
                              className="px-2 py-1 bg-zinc-800 hover:bg-zinc-700 border border-zinc-700 text-zinc-200 rounded text-[10px] font-bold shrink-0 cursor-pointer"
                            >
                              Export JSON
                            </button>
                          )}
                        </div>

                        {isOpenRow && (
                          <div className="pt-2 border-t border-zinc-800 space-y-1.5 text-[10px]">
                            {m.notes && <div className="text-zinc-300 italic">{m.notes}</div>}
                            {hasOffsets ? (
                              <div className="grid grid-cols-1 sm:grid-cols-2 gap-1.5">
                                {(m.offsets?.products || []).slice(0, 12).map((p, i) => (
                                  <div key={`p-${i}`} className="flex justify-between px-2 py-0.5 bg-black/50 rounded border border-zinc-800/80">
                                    <span className="text-zinc-300 truncate">{p.name}</span>
                                    <span className="text-cyan-300 font-bold">{p.addr_hex}</span>
                                  </div>
                                ))}
                                {(m.offsets?.maintenance || []).slice(0, 12).map((mt, i) => (
                                  <div key={`m-${i}`} className="flex justify-between px-2 py-0.5 bg-black/50 rounded border border-zinc-800/80">
                                    <span className="text-amber-300 truncate">{mt.name}</span>
                                    <span className="text-amber-400 font-bold">{mt.addr_hex}</span>
                                  </div>
                                ))}
                              </div>
                            ) : (
                              <div className="text-zinc-500">
                                Standard factory EF map ({(m.product_labels || []).slice(0, 8).join(', ')}).
                              </div>
                            )}
                          </div>
                        )}
                      </div>
                    );
                  })}
              </div>
            </div>
          )}

          {/* SECTION 2: GITHUB COMMUNITY CONNECTION */}
          {activeSection === 'github' && (
            <div className="p-4 bg-black/40 border border-zinc-800 rounded space-y-3">
              <div className="flex items-center justify-between border-b border-zinc-800 pb-2.5">
                <div className="flex items-center gap-2">
                  <Github className="w-4 h-4 text-[#FCEE09]" />
                  <div>
                    <div className="font-bold text-white">GitHub Community Upload Account</div>
                    <div className="text-[10px] text-zinc-400">
                      Used to submit captures &amp; EEPROM offset fixes to Pr0xyA-91/spectra-captures
                    </div>
                  </div>
                </div>
                {githubAuth?.authenticated ? (
                  <span className="px-2 py-0.5 bg-emerald-950 border border-emerald-700 text-emerald-300 rounded text-[10px] font-bold">
                    CONNECTED: @{githubAuth.login}
                  </span>
                ) : (
                  <span className="px-2 py-0.5 bg-amber-950 border border-amber-700 text-amber-300 rounded text-[10px] font-bold">
                    DISCONNECTED
                  </span>
                )}
              </div>

              {authStatusMsg?.msg && (
                <div
                  className={`px-3 py-2 rounded text-[11px] border ${
                    authStatusMsg.error
                      ? 'bg-red-950/50 border-red-800 text-red-300'
                      : 'bg-emerald-950/40 border-emerald-800 text-emerald-300'
                  }`}
                >
                  {authStatusMsg.msg}
                </div>
              )}

              {githubAuth?.authenticated ? (
                <div className="flex items-center justify-between p-3 bg-zinc-950 border border-zinc-800 rounded">
                  <div className="text-xs text-zinc-300">
                    Signed in as <strong className="text-emerald-400">@{githubAuth.login}</strong>{' '}
                    <span className="text-zinc-500">({githubAuth.method || 'token'})</span>
                  </div>
                  <button
                    type="button"
                    onClick={onLogout}
                    className="px-3 py-1.5 bg-rose-950/70 hover:bg-rose-900/80 border border-rose-700 text-rose-200 rounded font-bold text-xs flex items-center gap-1.5 cursor-pointer"
                  >
                    <LogOut className="w-3.5 h-3.5" />
                    <span>Sign Out</span>
                  </button>
                </div>
              ) : (
                <div className="space-y-3">
                  {githubAuth?.device_flow_available && !deviceFlow && (
                    <button
                      type="button"
                      onClick={onStartDeviceFlow}
                      className="w-full py-2 px-3 bg-sky-700 hover:bg-sky-600 text-white font-bold rounded text-xs flex items-center justify-center gap-2 cursor-pointer"
                    >
                      <Github className="w-4 h-4" />
                      <span>Sign in via GitHub Device Code (Browser)</span>
                    </button>
                  )}

                  {deviceFlow && (
                    <div className="p-3 bg-sky-950/40 border border-sky-800 rounded space-y-2">
                      <div className="text-[11px] text-sky-300 font-bold">Authorize SPECTRA on GitHub:</div>
                      <div className="flex items-center justify-between bg-black/70 p-2 rounded border border-sky-900">
                        <span className="text-sm font-bold text-sky-200 tracking-widest">{deviceFlow.user_code}</span>
                        <button
                          type="button"
                          onClick={() => onCopyDeviceCode(deviceFlow.user_code)}
                          className="px-2 py-1 bg-sky-800 hover:bg-sky-700 text-sky-100 rounded text-[10px] flex items-center gap-1 cursor-pointer"
                        >
                          {copiedCode ? <Check className="w-3 h-3 text-emerald-400" /> : <Copy className="w-3 h-3" />}
                          <span>{copiedCode ? 'Copied' : 'Copy Code'}</span>
                        </button>
                      </div>
                      <div className="flex items-center justify-between text-[11px]">
                        <a
                          href={deviceFlow.verification_uri}
                          target="_blank"
                          rel="noreferrer"
                          className="text-sky-400 hover:text-sky-300 underline flex items-center gap-1"
                        >
                          <span>Open github.com/login/device</span>
                          <ExternalLink className="w-3 h-3" />
                        </a>
                        <button
                          type="button"
                          onClick={onCancelDeviceFlow}
                          className="text-zinc-400 hover:text-white cursor-pointer"
                        >
                          Cancel
                        </button>
                      </div>
                    </div>
                  )}

                  <div className="p-3 bg-zinc-950 border border-zinc-800 rounded space-y-2">
                    <label className="block text-[11px] text-zinc-300 font-bold">
                      Or Connect with Personal Access Token (public_repo &amp; gist):
                    </label>
                    <div className="flex gap-2">
                      <input
                        type="password"
                        value={patInput}
                        onChange={(e) => setPatInput(e.target.value)}
                        placeholder="ghp_... or github_pat_..."
                        className="flex-1 bg-black border border-zinc-700 rounded px-2.5 py-1.5 text-xs text-white outline-none focus:border-[#FCEE09]"
                      />
                      <button
                        type="button"
                        disabled={!patInput?.trim()}
                        onClick={onSavePat}
                        className="px-3 py-1.5 bg-[#FCEE09] hover:bg-yellow-400 disabled:opacity-40 text-black font-extrabold rounded text-xs cursor-pointer"
                      >
                        Connect
                      </button>
                    </div>
                  </div>
                </div>
              )}
            </div>
          )}

          {/* SECTION 3: LOCAL OVERRIDES & SENSOR CALIBRATION */}
          {activeSection === 'calibration' && (
            <div className="space-y-4">
              {/* Saved Local EEPROM Offset Overrides */}
              <div className="p-3.5 bg-black/40 border border-zinc-800 rounded space-y-2.5">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2 font-bold text-white">
                    <Database className="w-4 h-4 text-emerald-400" />
                    <span>Saved Local EEPROM Offset Overrides ({overrideEntries.length})</span>
                  </div>
                  <button
                    type="button"
                    onClick={loadOverridesAndCalib}
                    className="text-[10px] text-zinc-400 hover:text-white underline cursor-pointer"
                  >
                    Refresh
                  </button>
                </div>

                {overrideEntries.length === 0 ? (
                  <div className="p-2.5 bg-zinc-950 border border-zinc-800 rounded text-[11px] text-zinc-400">
                    No local EEPROM offset overrides saved yet. Use Export → J.O.E. AI Offset Fixer if a machine reads wrong counters.
                  </div>
                ) : (
                  <div className="space-y-1.5 max-h-44 overflow-y-auto">
                    {overrideEntries.map(([key, ov]) => (
                      <div
                        key={key}
                        className="flex items-center justify-between p-2.5 bg-zinc-950 border border-zinc-800 rounded text-[11px]"
                      >
                        <div>
                          <div className="text-emerald-300 font-bold">
                            {ov.model_name || key}{' '}
                            <span className="text-zinc-500">({key})</span>
                          </div>
                          <div className="text-[10px] text-zinc-400">
                            {(ov.products || []).length} beverages • {(ov.maintenance || []).length} maintenance • Updated {ov.updated_at || 'recently'}
                          </div>
                        </div>
                        <button
                          type="button"
                          onClick={() => handleDeleteOverride(key)}
                          className="px-2 py-1 bg-rose-950/60 hover:bg-rose-900/70 border border-rose-700 text-rose-300 rounded text-[10px] font-bold flex items-center gap-1 cursor-pointer"
                        >
                          <Trash2 className="w-3 h-3" />
                          <span>Revert</span>
                        </button>
                      </div>
                    ))}
                  </div>
                )}
              </div>

              {/* Optical Bean Sensor Threshold */}
              <div className="p-3.5 bg-black/40 border border-zinc-800 rounded space-y-2.5">
                <div className="font-bold text-white flex items-center gap-2">
                  <Sliders className="w-4 h-4 text-[#FCEE09]" />
                  <span>Optical Bean Hopper Sensor Threshold</span>
                </div>
                <p className="text-[11px] text-zinc-400">
                  Adjusts ADC count cutoff used on AS: optical hopper diagnostics (range {beanCalib.min_threshold ?? 30}–{beanCalib.max_threshold ?? 250}).
                </p>
                <div className="flex items-center gap-3">
                  <input
                    type="range"
                    min={beanCalib.min_threshold ?? 30}
                    max={beanCalib.max_threshold ?? 250}
                    value={thresholdInput}
                    onChange={(e) => setThresholdInput(Number(e.target.value))}
                    className="flex-1 accent-[#FCEE09]"
                  />
                  <span className="w-12 text-center font-bold text-[#FCEE09] bg-zinc-950 border border-zinc-700 rounded py-1">
                    {thresholdInput}
                  </span>
                  <button
                    type="button"
                    onClick={handleSaveThreshold}
                    className="px-3 py-1.5 bg-[#FCEE09] hover:bg-yellow-400 text-black font-extrabold rounded text-xs cursor-pointer"
                  >
                    Save
                  </button>
                  <button
                    type="button"
                    onClick={handleResetThreshold}
                    className="px-2.5 py-1.5 bg-zinc-800 hover:bg-zinc-700 text-zinc-300 border border-zinc-700 rounded text-xs cursor-pointer"
                  >
                    Reset
                  </button>
                </div>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
