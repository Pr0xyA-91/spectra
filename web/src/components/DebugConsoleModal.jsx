import React, { useState, useEffect, useMemo, useRef, useCallback } from 'react';
import {
  Terminal,
  Bug,
  Activity,
  Cpu,
  Layers,
  RefreshCw,
  Trash2,
  Copy,
  X,
  ChevronDown,
  ChevronRight,
  Square,
  Radio,
  Search,
  Check,
  AlertCircle,
  AlertTriangle,
  Info,
} from 'lucide-react';
import { createTranslator } from '../i18n/translations';
import { copyTextSafe } from '../utils/fetchSafe';

export default function DebugConsoleModal({ isOpen, onClose, lang = 'en' }) {
  const t = useMemo(() => createTranslator(lang), [lang]);
  const [diagnostics, setDiagnostics] = useState(null);
  const [logs, setLogs] = useState([]);
  const [errorCount, setErrorCount] = useState(0);
  const [warnCount, setWarnCount] = useState(0);
  const [activeFilter, setActiveFilter] = useState('ALL');
  const [searchQuery, setSearchQuery] = useState('');
  const [autoRefresh, setAutoRefresh] = useState(true);
  const [expandedLogId, setExpandedLogId] = useState(null);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [copiedNotice, setCopiedNotice] = useState(false);
  const [showThreads, setShowThreads] = useState(false);
  const [stoppingAi, setStoppingAi] = useState(false);
  const logContainerRef = useRef(null);

  const statusAbortRef = useRef(null);

  const fetchStatus = useCallback(async () => {
    if (statusAbortRef.current) {
      try { statusAbortRef.current.abort(); } catch {}
    }
    const controller = new AbortController();
    statusAbortRef.current = controller;
    try {
      setIsRefreshing(true);
      const res = await fetch('/api/debug/status', { signal: controller.signal });
      const data = await res.json();
      if (data && data.success) {
        setDiagnostics(data.diagnostics);
        setLogs(data.logs || []);
        setErrorCount(data.error_count || 0);
        setWarnCount(data.warn_count || 0);
      }
    } catch (e) {
      if (e?.name === 'AbortError') return;
      // Silently fail during teardown or network disconnect
    } finally {
      if (statusAbortRef.current === controller) {
        setIsRefreshing(false);
      }
    }
  }, []);

  useEffect(() => {
    if (!isOpen) return;
    if (document.visibilityState !== 'hidden') {
      fetchStatus();
    }

    let interval = null;
    if (autoRefresh) {
      interval = setInterval(() => {
        if (document.visibilityState === 'hidden') return;
        fetchStatus();
      }, 1500);
    }
    const handleVisibility = () => {
      if (document.visibilityState === 'visible') {
        fetchStatus();
      }
    };
    document.addEventListener('visibilitychange', handleVisibility);

    return () => {
      if (interval) clearInterval(interval);
      document.removeEventListener('visibilitychange', handleVisibility);
      if (statusAbortRef.current) {
        try { statusAbortRef.current.abort(); } catch {}
        statusAbortRef.current = null;
      }
    };
  }, [isOpen, autoRefresh, fetchStatus]);

  useEffect(() => {
    const handleKeyDown = (e) => {
      if (!isOpen) return;
      if (e.key === 'Escape') {
        onClose();
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [isOpen, onClose]);

  const handleClear = async () => {
    try {
      await fetch('/api/debug/clear', { method: 'POST' });
      fetchStatus();
    } catch (e) {}
  };

  const handleStopAi = async () => {
    try {
      setStoppingAi(true);
      await fetch('/api/hmi/ollama_control', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ action: 'stop' }),
      });
      setTimeout(fetchStatus, 600);
    } catch (e) {
    } finally {
      setStoppingAi(false);
    }
  };

  const handleCopyReport = async () => {
    const report = {
      timestamp: new Date().toISOString(),
      diagnostics,
      errorCount,
      warnCount,
      logsSummary: {
        total: logs.length,
        errors: logs.filter((l) => l.level === 'ERROR').map((l) => ({ t: l.timestamp, msg: l.message, details: l.details })),
        recent: logs.slice(-25),
      },
    };
    const ok = await copyTextSafe(JSON.stringify(report, null, 2));
    if (ok) {
      setCopiedNotice(true);
      setTimeout(() => setCopiedNotice(false), 2000);
    }
  };

  const filteredLogs = useMemo(() => {
    const q = searchQuery.toLowerCase().trim();
    return logs.filter((l) => {
      // Filter tab match
      if (activeFilter === 'ERRORS' && l.level !== 'ERROR' && l.level !== 'WARN') return false;
      if (activeFilter === 'API' && l.source !== 'API' && l.source !== 'HTTP') return false;
      if (activeFilter === 'BACKEND' && !['STDOUT', 'STDERR', 'DEBUG', 'OLLAMA'].includes(l.source)) return false;
      if (activeFilter === 'FRONTEND' && l.source !== 'FRONTEND') return false;

      // Query match
      if (q) {
        const msg = (l.message || '').toLowerCase();
        const det = (l.details || '').toLowerCase();
        const src = (l.source || '').toLowerCase();
        return msg.includes(q) || det.includes(q) || src.includes(q);
      }
      return true;
    });
  }, [logs, activeFilter, searchQuery]);

  if (!isOpen) return null;

  const proc = diagnostics?.process || {};
  const offsetDb = diagnostics?.offset_db || {};
  const offsetDbVersion = offsetDb.offset_db_version || proc.offset_db_version || '';
  const serial = diagnostics?.serial || {};
  const ollama = diagnostics?.ollama || {};
  const threads = diagnostics?.threads || [];
  const children = diagnostics?.children || [];

  return (
    <div className="fixed inset-0 z-50 bg-black/80 backdrop-blur-sm flex items-center justify-center p-3 sm:p-5 select-text font-sans">
      <div className="bg-[#0e0e14] border border-zinc-700/80 rounded-xl shadow-2xl max-h-[88vh] max-w-[94vw] w-[1240px] flex flex-col overflow-hidden text-zinc-200">
        {/* Header */}
        <div className="px-4 py-3 bg-[#13131c] border-b border-zinc-700/80 flex flex-wrap items-center justify-between gap-3 shrink-0">
          <div className="flex items-center space-x-2.5">
            <div className="p-1.5 bg-rose-500/10 border border-rose-500/30 rounded-lg text-rose-400">
              <Bug className="w-4 h-4" />
            </div>
            <div>
              <div className="flex items-center space-x-2 flex-wrap">
                <span className="font-mono font-black text-sm tracking-wide text-zinc-100 uppercase">
                  {t('dbgTitle')}
                </span>
                <span className="text-[10px] px-1.5 py-0.5 rounded font-mono font-bold bg-zinc-800 text-zinc-300 border border-zinc-700">
                  PID {proc.pid || '-'}
                </span>
                {offsetDbVersion && (
                  <span className="text-[10px] px-1.5 py-0.5 rounded font-mono font-bold bg-purple-950/60 text-purple-300 border border-purple-700/70">
                    OFFSET DB {offsetDbVersion}
                  </span>
                )}
              </div>
              <div className="text-[11px] text-zinc-400 font-mono flex items-center space-x-3 mt-0.5">
                <span>{t('dbgUptime')} <strong className="text-zinc-200">{proc.uptime_sec || 0}s</strong></span>
                <span>•</span>
                <span>RAM: <strong className="text-zinc-200">{proc.rss_mb || 0} MB</strong></span>
                <span>•</span>
                <span className={errorCount > 0 ? 'text-rose-400 font-bold' : ''}>
                  {t('dbgErrors')} {errorCount}
                </span>
                <span>•</span>
                <span className={warnCount > 0 ? 'text-amber-400 font-bold' : ''}>
                  {t('dbgWarnings')} {warnCount}
                </span>
              </div>
            </div>
          </div>

          {/* Action buttons */}
          <div className="flex items-center space-x-2 text-xs font-mono">
            <button
              onClick={() => setAutoRefresh(!autoRefresh)}
              className={`px-2.5 py-1 rounded border flex items-center space-x-1.5 text-[11px] font-bold transition-colors ${
                autoRefresh
                  ? 'bg-emerald-950/40 border-emerald-500/50 text-emerald-300'
                  : 'bg-zinc-800 border-zinc-700 text-zinc-400'
              }`}
              title={t('dbgAutoRefresh')}
            >
              <Activity className={`w-3 h-3 ${autoRefresh ? 'animate-pulse text-emerald-400' : ''}`} />
              <span>{autoRefresh ? t('dbgAutoRefresh') : t('dbgPaused')}</span>
            </button>

            <button
              onClick={fetchStatus}
              disabled={isRefreshing}
              className="px-2.5 py-1 rounded bg-zinc-800 hover:bg-zinc-700 border border-zinc-700 text-zinc-300 flex items-center space-x-1 text-[11px] font-bold"
              title={t('btnRefresh')}
            >
              <RefreshCw className={`w-3 h-3 ${isRefreshing ? 'animate-spin' : ''}`} />
              <span>{t('btnRefresh')}</span>
            </button>

            <button
              onClick={handleCopyReport}
              className="px-2.5 py-1 rounded bg-zinc-800 hover:bg-zinc-700 border border-zinc-700 text-zinc-300 flex items-center space-x-1 text-[11px] font-bold"
              title={t('dbgCopyReport')}
            >
              {copiedNotice ? <Check className="w-3 h-3 text-emerald-400" /> : <Copy className="w-3 h-3" />}
              <span>{copiedNotice ? t('dbgCopied') : t('dbgCopyReport')}</span>
            </button>

            <button
              onClick={handleClear}
              className="px-2.5 py-1 rounded bg-zinc-800 hover:bg-rose-950/40 border border-zinc-700 hover:border-rose-700 text-zinc-300 hover:text-rose-300 flex items-center space-x-1 text-[11px] font-bold"
              title={t('btnClear')}
            >
              <Trash2 className="w-3 h-3" />
              <span>{t('btnClear')}</span>
            </button>

            <button
              onClick={onClose}
              className="p-1 rounded bg-zinc-800 hover:bg-zinc-700 border border-zinc-700 text-zinc-400 hover:text-white"
              title={t('dbgClose')}
            >
              <X className="w-4 h-4" />
            </button>
          </div>
        </div>

        {/* Top Section: Process & Services Cards */}
        <div className="p-3 bg-[#111119] border-b border-zinc-800/80 grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-2.5 shrink-0 text-xs font-mono">
          {/* Card 1: SPECTRA Core Process */}
          <div className="bg-[#181824] border border-zinc-800 rounded-lg p-2.5 flex flex-col justify-between">
            <div className="flex items-center justify-between text-zinc-400 text-[11px] mb-1">
              <span className="flex items-center space-x-1 text-sky-400 font-bold">
                <Cpu className="w-3.5 h-3.5" />
                <span>{t('dbgCoreProcess')}</span>
              </span>
              <span className="text-[10px] text-zinc-500 uppercase">{proc.platform || '-'}</span>
            </div>
            <div className="text-zinc-200 font-bold text-sm">
              PID {proc.pid || '-'} • {proc.rss_mb || 0} MB
            </div>
            <div className="text-[11px] text-zinc-400 mt-1 flex justify-between">
              <span>Python: {proc.python_version || '-'}</span>
              <span>{t('dbgUptime')} {proc.uptime_sec || 0}s</span>
            </div>
            <div className="mt-1.5 pt-1.5 border-t border-zinc-800/80 flex items-center justify-between text-[10px]">
              <span className="text-zinc-500">ACCEL</span>
              {proc.rust_core_active ? (
                <span className="px-1.5 py-0.5 rounded font-bold bg-amber-500/20 text-amber-300 border border-amber-500/40">
                  {t('dbgRustActive')}
                </span>
              ) : (
                <span className="px-1.5 py-0.5 rounded text-zinc-500 bg-zinc-800/60 border border-zinc-800">
                  {t('dbgPythonFallback')}
                </span>
              )}
            </div>
          </div>

          {/* Card 2: Serial Worker Session */}
          <div className="bg-[#181824] border border-zinc-800 rounded-lg p-2.5 flex flex-col justify-between">
            <div className="flex items-center justify-between text-zinc-400 text-[11px] mb-1">
              <span className="flex items-center space-x-1 text-emerald-400 font-bold">
                <Radio className="w-3.5 h-3.5" />
                <span>{t('dbgHwSerial')}</span>
              </span>
              <span
                className={`text-[10px] px-1.5 py-0.2 rounded font-bold ${
                  serial.status === 'ACTIVE'
                    ? 'bg-emerald-500/20 text-emerald-300 border border-emerald-500/40'
                    : 'bg-zinc-800 text-zinc-400'
                }`}
              >
                {serial.status || 'IDLE'}
              </span>
            </div>
            <div className="text-zinc-200 font-bold text-xs truncate" title={serial.port}>
              Port: {serial.port || t('dbgNone')}
            </div>
            <div className="text-[11px] text-zinc-400 mt-1 flex justify-between">
              <span>{t('dbgDriver')} {serial.driver || t('dbgNone')}</span>
              {serial.error_state && (
                <span className="text-rose-400 font-bold">Err: {serial.consecutive_errors}</span>
              )}
            </div>
          </div>

          {/* Card 3: Embedded Local AI Engine */}
          <div className="bg-[#181824] border border-zinc-800 rounded-lg p-2.5 flex flex-col justify-between">
            <div className="flex items-center justify-between text-zinc-400 text-[11px] mb-1">
              <span className="flex items-center space-x-1 text-purple-400 font-bold">
                <Terminal className="w-3.5 h-3.5" />
                <span>{t('dbgLocalAiEngine')}</span>
              </span>
              <span
                className={`text-[10px] px-1.5 py-0.2 rounded font-bold ${
                  ollama.running
                    ? 'bg-purple-500/20 text-purple-300 border border-purple-500/40'
                    : 'bg-zinc-800 text-zinc-500'
                }`}
              >
                {ollama.running ? t('dbgRunning') : t('dbgStopped')}
              </span>
            </div>
            <div className="text-zinc-200 font-bold text-xs truncate">
              {ollama.running ? `PID ${ollama.pid || 'External'} (${ollama.active_model || 'Idle'})` : '0 MB (Offline)'}
            </div>
            <div className="text-[11px] text-zinc-400 mt-1 flex items-center justify-between">
              <span>{t('dbgManaged')} {ollama.managed_by_spectra ? t('dbgYes') : t('dbgNo')}</span>
              {ollama.running && (
                <button
                  onClick={handleStopAi}
                  disabled={stoppingAi}
                  className="px-1.5 py-0.5 rounded bg-rose-950/60 hover:bg-rose-900 border border-rose-700 text-[10px] text-rose-300 font-bold flex items-center space-x-1"
                >
                  <Square className="w-2.5 h-2.5 fill-current" />
                  <span>{stoppingAi ? t('dbgStopping') : t('dbgStopAi')}</span>
                </button>
              )}
            </div>
          </div>

          {/* Card 4: Threads & Subprocesses Summary */}
          <div
            onClick={() => setShowThreads(!showThreads)}
            className="bg-[#181824] border border-zinc-800 hover:border-zinc-700 rounded-lg p-2.5 flex flex-col justify-between cursor-pointer transition-colors"
          >
            <div className="flex items-center justify-between text-zinc-400 text-[11px] mb-1">
              <span className="flex items-center space-x-1 text-amber-400 font-bold">
                <Layers className="w-3.5 h-3.5" />
                <span>{t('dbgThreadsChildren')}</span>
              </span>
              <span className="text-[10px] text-zinc-500 flex items-center space-x-1">
                <span>{showThreads ? t('dbgCollapse') : t('dbgExpand')}</span>
                {showThreads ? <ChevronDown className="w-3 h-3" /> : <ChevronRight className="w-3 h-3" />}
              </span>
            </div>
            <div className="text-zinc-200 font-bold text-sm">
              {t('dbgThreadsCount', { threads: threads.length, children: children.length })}
            </div>
            <div className="text-[11px] text-zinc-400 mt-1 truncate">
              HTTP: {diagnostics?.http_daemon?.bind || '127.0.0.1:8080'}
            </div>
          </div>
        </div>

        {/* Collapsible Threads & Subprocesses Table */}
        {showThreads && (
          <div className="p-3 bg-[#0d0d12] border-b border-zinc-800 max-h-48 overflow-y-auto shrink-0 font-mono text-[11px]">
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
              <div>
                <h4 className="font-bold text-zinc-400 mb-1.5 text-xs flex items-center space-x-1">
                  <span className="w-2 h-2 rounded-full bg-amber-400" />
                  <span>{t('dbgActiveThreads', { count: threads.length })}</span>
                </h4>
                <div className="space-y-1">
                  {threads.map((t, idx) => (
                    <div
                      key={idx}
                      className="px-2 py-1 bg-[#14141d] rounded border border-zinc-800 flex items-center justify-between text-zinc-300"
                    >
                      <span className="font-bold truncate max-w-[220px]" title={t.name}>
                        {t.name}
                      </span>
                      <div className="flex items-center space-x-2 text-[10px] text-zinc-500">
                        <span>ID: {t.ident}</span>
                        {t.daemon && (
                          <span className="px-1 py-0.2 bg-zinc-800 text-zinc-400 rounded">DAEMON</span>
                        )}
                        <span className="text-emerald-400">ALIVE</span>
                      </div>
                    </div>
                  ))}
                </div>
              </div>

              <div>
                <h4 className="font-bold text-zinc-400 mb-1.5 text-xs flex items-center space-x-1">
                  <span className="w-2 h-2 rounded-full bg-purple-400" />
                  <span>{t('dbgChildProcesses', { count: children.length })}</span>
                </h4>
                {children.length === 0 ? (
                  <div className="text-zinc-500 italic p-2 bg-[#14141d] rounded border border-zinc-800">
                    {t('dbgNoChildren')}
                  </div>
                ) : (
                  <div className="space-y-1">
                    {children.map((c, idx) => (
                      <div
                        key={idx}
                        className="px-2 py-1 bg-[#14141d] rounded border border-zinc-800 flex items-center justify-between text-zinc-300"
                      >
                        <span className="font-bold truncate max-w-[200px]" title={c.cmdline}>
                          PID {c.pid}: {c.cmdline}
                        </span>
                        <span className="text-[10px] px-1 py-0.2 bg-purple-950/60 border border-purple-800 text-purple-300 rounded font-bold">
                          {c.state || 'ALIVE'}
                        </span>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </div>
          </div>
        )}

        {/* Bottom Section: Log Filter Bar */}
        <div className="px-4 py-2.5 bg-[#12121a] border-b border-zinc-800 flex flex-wrap items-center justify-between gap-2 shrink-0 font-mono text-xs">
          {/* Filters */}
          <div className="flex items-center space-x-1">
            {[
              { id: 'ALL', label: t('dbgFilterAll', { count: logs.length }) },
              { id: 'ERRORS', label: t('dbgFilterErrors', { count: errorCount + warnCount }) },
              { id: 'API', label: 'API / HTTP' },
              { id: 'BACKEND', label: 'BACKEND' },
              { id: 'FRONTEND', label: 'FRONTEND' },
            ].map((f) => (
              <button
                key={f.id}
                onClick={() => setActiveFilter(f.id)}
                className={`px-2.5 py-1 rounded text-[11px] font-bold transition-all ${
                  activeFilter === f.id
                    ? 'bg-zinc-200 text-zinc-950 shadow-sm'
                    : 'bg-zinc-800/80 text-zinc-400 hover:text-zinc-200 hover:bg-zinc-800'
                }`}
              >
                {f.label}
              </button>
            ))}
          </div>

          {/* Search Input */}
          <div className="flex items-center space-x-1.5 bg-black/40 px-2.5 py-1 rounded border border-zinc-800 min-w-[240px]">
            <Search className="w-3.5 h-3.5 text-zinc-500" />
            <input
              type="text"
              placeholder={t('dbgSearchPlaceholder')}
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="bg-transparent text-zinc-200 placeholder-zinc-500 text-[11px] outline-none w-full font-mono"
            />
            {searchQuery && (
              <button onClick={() => setSearchQuery('')} className="text-zinc-500 hover:text-zinc-300">
                <X className="w-3 h-3" />
              </button>
            )}
          </div>
        </div>

        {/* Live Logs Stream (500-line Ring Buffer) */}
        <div
          ref={logContainerRef}
          className="flex-1 overflow-y-auto p-3 space-y-1 bg-[#09090d] font-mono text-[11px] leading-relaxed select-text min-h-[220px]"
        >
          {filteredLogs.length === 0 ? (
            <div className="flex flex-col items-center justify-center h-44 text-zinc-500 italic">
              <Terminal className="w-8 h-8 text-zinc-700 mb-2" />
              <span>{t('dbgNoLogMatch')}</span>
            </div>
          ) : (
            filteredLogs.map((item) => {
              const isError = item.level === 'ERROR';
              const isWarn = item.level === 'WARN';
              const isApi = item.level === 'API' || item.source === 'API' || item.source === 'HTTP';
              const isExpanded = expandedLogId === item.id;
              const hasDetails = Boolean(item.details && item.details.trim());

              return (
                <div
                  key={item.id}
                  className={`px-2 py-1.5 rounded border transition-colors ${
                    isError
                      ? 'bg-rose-950/20 border-rose-900/40 text-rose-200'
                      : isWarn
                      ? 'bg-amber-950/20 border-amber-900/40 text-amber-200'
                      : isApi
                      ? 'bg-sky-950/15 border-sky-900/30 text-sky-200'
                      : 'bg-[#121219] border-zinc-800/80 text-zinc-300 hover:bg-[#151520]'
                  }`}
                >
                  <div className="flex items-start justify-between gap-2">
                    <div className="flex items-start space-x-2 flex-1 min-w-0">
                      {/* Timestamp */}
                      <span className="text-zinc-500 text-[10px] shrink-0 font-mono mt-0.5">
                        {item.timestamp}
                      </span>

                      {/* Level Badge */}
                      <span
                        className={`text-[9px] px-1.5 py-0.2 rounded font-bold uppercase shrink-0 mt-0.5 ${
                          isError
                            ? 'bg-rose-500/20 text-rose-400 border border-rose-500/30'
                            : isWarn
                            ? 'bg-amber-500/20 text-amber-400 border border-amber-500/30'
                            : isApi
                            ? 'bg-sky-500/20 text-sky-400 border border-sky-500/30'
                            : 'bg-emerald-500/10 text-emerald-400 border border-emerald-500/20'
                        }`}
                      >
                        {item.level}
                      </span>

                      {/* Source Badge */}
                      <span className="text-[9px] px-1 py-0.2 rounded bg-zinc-800 text-zinc-400 font-mono shrink-0 mt-0.5 border border-zinc-700/50">
                        {item.source}
                      </span>

                      {/* Message */}
                      <span className="break-all whitespace-pre-wrap flex-1">{item.message}</span>
                    </div>

                    {/* Expand Details Trigger */}
                    {hasDetails && (
                      <button
                        onClick={() => setExpandedLogId(isExpanded ? null : item.id)}
                        className="text-zinc-400 hover:text-zinc-100 flex items-center space-x-1 text-[10px] shrink-0 font-mono px-1.5 py-0.5 rounded bg-zinc-800 border border-zinc-700"
                      >
                        <span>{isExpanded ? t('dbgHideTrace') : t('dbgShowTrace')}</span>
                        {isExpanded ? <ChevronDown className="w-3 h-3" /> : <ChevronRight className="w-3 h-3" />}
                      </button>
                    )}
                  </div>

                  {/* Expandable Traceback / Stack Details */}
                  {isExpanded && hasDetails && (
                    <div className="mt-2 pt-2 border-t border-zinc-800/80">
                      <pre className="p-2.5 rounded bg-black/90 border border-rose-900/50 text-rose-300 font-mono text-[10px] overflow-x-auto whitespace-pre leading-relaxed select-text">
                        {item.details}
                      </pre>
                    </div>
                  )}
                </div>
              );
            })
          )}
        </div>

        {/* Footer Bar */}
        <div className="px-4 py-2 bg-[#101017] border-t border-zinc-800 flex items-center justify-between text-zinc-400 text-[11px] font-mono shrink-0">
          <div className="flex items-center space-x-3">
            <span>{t('dbgBuffer', { count: logs.length })}</span>
            <span>•</span>
            <span>{t('dbgShowing', { count: filteredLogs.length })}</span>
          </div>
          <div className="flex items-center space-x-2 text-zinc-500 text-[10px]">
            <span>{t('dbgShortcutHint')}</span>
          </div>
        </div>
      </div>
    </div>
  );
}
