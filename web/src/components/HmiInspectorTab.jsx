import React, { useState, useEffect, useCallback, useRef, useMemo } from 'react';
import { Shield, Layers, Sparkles } from 'lucide-react';
import { createTranslator } from '../i18n/translations';
import { FALLBACK_LANGUAGES, buildEffectiveModelCatalog } from './hmi/hmiConstants';
import HmiHeaderBar from './hmi/HmiHeaderBar';
import HmiAuditFindingsView from './hmi/HmiAuditFindingsView';
import HmiSemanticAuditView from './hmi/HmiSemanticAuditView';
import HmiPhraseExplorerView from './hmi/HmiPhraseExplorerView';
import { HmiAiResultsModal } from './hmi/HmiAiResultsView';
import { copyTextSafe } from '../utils/fetchSafe';

function HmiInspectorTab({
  theme,
  lang = 'en',
  aiEnabled = false,
  onToggleAi = null,
  onGlobalModelChange = null,
  beginAiWork = null,
  endAiWork = null,
}) {
  const t = useMemo(() => createTranslator(lang), [lang]);
  const [targetPath, setTargetPath] = useState('');
  const [autoScanDownloads, setAutoScanDownloads] = useState(() => {
    try {
      return localStorage.getItem('spectra_hmi_auto_scan') === 'true';
    } catch {
      return false;
    }
  });
  const [discoveredTargets, setDiscoveredTargets] = useState([]);
  const [isDiscovering, setIsDiscovering] = useState(false);
  const [defaultDir, setDefaultDir] = useState('');
  const [hmiInfo, setHmiInfo] = useState(null);
  const [findings, setFindings] = useState([]);
  const [languages, setLanguages] = useState([]);
  const [selectedLocale, setSelectedLocale] = useState('cs-CZ');
  const [auditLocale, setAuditLocale] = useState('cs-CZ');
  const [phrases, setPhrases] = useState([]);
  const [searchQuery, setSearchQuery] = useState('');
  const [subTab, setSubTab] = useState('audit'); // 'audit' | 'semantic' | 'explorer'
  const [selectedFinding, setSelectedFinding] = useState(null);
  const [severityFilter, setSeverityFilter] = useState('ALL');

  // Semantic audit & AI system states
  const [semanticReport, setSemanticReport] = useState(null);
  const [isLoadingSemantic, setIsLoadingSemantic] = useState(false);
  const [useOllama, setUseOllama] = useState(false);

  // Sync local Ollama toggle with global AI power switch (Default: OFF)
  useEffect(() => {
    if (!aiEnabled) {
      setUseOllama(false);
    }
  }, [aiEnabled]);

  const [ollamaModel, setOllamaModel] = useState(() => {
    try {
      return localStorage.getItem('spectra_ollama_model') || '';
    } catch {
      return '';
    }
  });
  const [autoUnload, setAutoUnload] = useState(true);
  const [aiStatus, setAiStatus] = useState(null);
  const [isLoadingAiStatus, setIsLoadingAiStatus] = useState(false);
  const [isOperatingOllama, setIsOperatingOllama] = useState(false);
  const [semanticProgress, setSemanticProgress] = useState(null);
  const semanticProgressPollRef = useRef(null);
  const semanticProgressInFlightRef = useRef(false);
  const semanticProgressAbortRef = useRef(null);

  // Compute Infallible Effective Model Catalog (merging fallback + backend + locally installed)
  const effectiveModelCatalog = useMemo(() => buildEffectiveModelCatalog(aiStatus), [aiStatus]);

  // Fallback languages array so Target Locale dropdown is never empty
  const effectiveLanguages = useMemo(() => {
    if (languages && languages.length > 0) return languages;
    return FALLBACK_LANGUAGES;
  }, [languages]);

  // Filter states for Semantic anomalies and AI scan results
  const [anomalyFilter, setAnomalyFilter] = useState('ALL'); // 'ALL' | 'OLLAMA_SCANNED' | 'AI_DEFECTS' | 'AI_VERIFIED' | 'GLOSSARY'
  const [aiResultFilter, setAiResultFilter] = useState('ALL'); // 'ALL' | 'DEFECTS' | 'VERIFIED'
  const [showAiModal, setShowAiModal] = useState(false);

  // Async action states
  const [isLoading, setIsLoading] = useState(false);
  const [isPatching, setIsPatching] = useState(false);
  const [, setPatchResult] = useState(null);
  const [isExporting, setIsExporting] = useState(false);
  const [exportNotice, setExportNotice] = useState(null);
  const [copiedSha, setCopiedSha] = useState(false);
  const [statusMessage, setStatusMessage] = useState(null);

  // Fetch Host Hardware Self-Check & Adaptive AI Status
  const fetchAiStatus = useCallback(async () => {
    setIsLoadingAiStatus(true);
    try {
      const res = await fetch('/api/hmi/ai_status');
      const data = await res.json();
      if (data.success && data.status) {
        setAiStatus(data.status);
        const saved = (() => {
          try {
            return localStorage.getItem('spectra_ollama_model');
          } catch {
            return null;
          }
        })();
        if (!saved && !ollamaModel && data.status.hardware?.default_selected_model) {
          setOllamaModel(data.status.hardware.default_selected_model);
          try {
            localStorage.setItem('spectra_ollama_model', data.status.hardware.default_selected_model);
          } catch {}
        }
        if (data.status.hardware?.auto_unload_recommended !== undefined) {
          setAutoUnload(data.status.hardware.auto_unload_recommended);
        }
      }
    } catch (err) {
      console.error('Failed to load AI system status:', err);
    } finally {
      setIsLoadingAiStatus(false);
    }
  }, [ollamaModel]);

  // Real-Time Streaming Download Progress State & Watchdog
  const [pullProgress, setPullProgress] = useState(null);
  const progressPollRef = useRef(null);
  const progressInFlightRef = useRef(false);
  const progressAbortRef = useRef(null);

  const stopProgressPolling = useCallback(() => {
    if (progressPollRef.current) {
      clearInterval(progressPollRef.current);
      progressPollRef.current = null;
    }
    if (progressAbortRef.current) {
      try { progressAbortRef.current.abort(); } catch {}
      progressAbortRef.current = null;
    }
    progressInFlightRef.current = false;
  }, []);

  const pollProgress = useCallback(async () => {
    if (document.visibilityState === 'hidden' || progressInFlightRef.current) return;
    progressInFlightRef.current = true;
    const controller = new AbortController();
    progressAbortRef.current = controller;
    try {
      const res = await fetch('/api/hmi/ollama_progress', { signal: controller.signal });
      const data = await res.json();
      if (data && data.success && data.progress) {
        const prog = data.progress;
        setPullProgress(prog);

        if (!prog.active) {
          stopProgressPolling();
          if (prog.status === 'COMPLETED') {
            fetchAiStatus();
            setStatusMessage({
              type: 'success',
              text: prog.status_text || 'Model downloaded and ready for offline use!',
            });
          } else if (prog.status === 'ERROR') {
            setStatusMessage({
              type: 'error',
              text: `Download error: ${prog.error || prog.status_text}`,
            });
          } else if (prog.status === 'CANCELLED') {
            setStatusMessage({
              type: 'warning',
              text: 'Download cancelled by user.',
            });
          }
        }
      }
    } catch (e) {
      if (e?.name === 'AbortError') return;
      // Ignore network blips during polling
    } finally {
      if (progressAbortRef.current === controller) {
        progressInFlightRef.current = false;
      }
    }
  }, [stopProgressPolling, fetchAiStatus]);

  const startProgressPolling = useCallback(() => {
    stopProgressPolling();
    pollProgress();
    progressPollRef.current = setInterval(() => {
      if (document.visibilityState === 'hidden') return;
      pollProgress();
    }, 350);
  }, [stopProgressPolling, pollProgress]);

  // Clean up polling interval on unmount
  useEffect(() => {
    return () => stopProgressPolling();
  }, [stopProgressPolling]);

  // Check if download is already in progress when entering tab
  useEffect(() => {
    if (subTab === 'semantic') {
      fetch('/api/hmi/ollama_progress')
        .then((r) => r.json())
        .then((d) => {
          if (d && d.success && d.progress && d.progress.active) {
            setPullProgress(d.progress);
            startProgressPolling();
          }
        })
        .catch(() => {});
    }
  }, [subTab, startProgressPolling]);

  // Real-Time Semantic Scan Progress Polling Watchdog
  useEffect(() => {
    let active = true;
    if (isLoadingSemantic) {
      const pollSemanticProgress = async () => {
        if (!active || document.visibilityState === 'hidden' || semanticProgressInFlightRef.current) return;
        semanticProgressInFlightRef.current = true;
        const controller = new AbortController();
        semanticProgressAbortRef.current = controller;
        try {
          const res = await fetch('/api/hmi/semantic/progress', { signal: controller.signal });
          const data = await res.json();
          if (active && data && data.success && data.progress) {
            setSemanticProgress(data.progress);
          }
        } catch (e) {
          if (e?.name === 'AbortError') return;
          // ignore network blips during polling
        } finally {
          if (semanticProgressAbortRef.current === controller) {
            semanticProgressInFlightRef.current = false;
          }
        }
      };
      pollSemanticProgress();
      semanticProgressPollRef.current = setInterval(pollSemanticProgress, 400);
    } else {
      if (semanticProgressPollRef.current) {
        clearInterval(semanticProgressPollRef.current);
        semanticProgressPollRef.current = null;
      }
      if (semanticProgressAbortRef.current) {
        try { semanticProgressAbortRef.current.abort(); } catch {}
        semanticProgressAbortRef.current = null;
      }
      semanticProgressInFlightRef.current = false;
    }
    return () => {
      active = false;
      if (semanticProgressPollRef.current) {
        clearInterval(semanticProgressPollRef.current);
        semanticProgressPollRef.current = null;
      }
      if (semanticProgressAbortRef.current) {
        try { semanticProgressAbortRef.current.abort(); } catch {}
        semanticProgressAbortRef.current = null;
      }
      semanticProgressInFlightRef.current = false;
    };
  }, [isLoadingSemantic]);

  // Embedded Ollama Daemon Controller (start, unload, stop, pull)
  const controlOllama = useCallback(async (action, modelTarget = null) => {
    setIsOperatingOllama(true);
    setStatusMessage(null);
    try {
      const res = await fetch('/api/hmi/ollama_control', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ action, model: modelTarget || ollamaModel }),
      });
      const data = await res.json();
      const resObj = data.result || {};
      const isErr = data.is_error || !data.success || ['ERROR', 'BINARY_NOT_FOUND', 'OLLAMA_OFFLINE', 'START_TIMEOUT'].includes(resObj.status);

      if (data.ai_status || resObj.ai_status) {
        setAiStatus(data.ai_status || resObj.ai_status);
      }

      if (isErr) {
        setStatusMessage({
          type: 'error',
          text: `Local AI: ${resObj.message || data.error || 'Operation failed'}`,
        });
      } else {
        setStatusMessage({
          type: 'success',
          text: `Local AI: ${resObj.message || 'Operation succeeded'}`,
        });
        fetchAiStatus();
      }

      if (action === 'pull' || action === 'pull_async') {
        startProgressPolling();
      }
    } catch (err) {
      setStatusMessage({ type: 'error', text: `Local AI network error: ${err.message}` });
    } finally {
      setIsOperatingOllama(false);
    }
  }, [ollamaModel, fetchAiStatus, startProgressPolling]);

  // Auto-fetch AI status on entering semantic tab
  useEffect(() => {
    if (subTab === 'semantic' && !aiStatus) {
      fetchAiStatus();
    }
  }, [subTab, aiStatus, fetchAiStatus]);

  // Fetch 3-Tier Offline Semantic Hybrid Report
  const fetchSemanticData = useCallback(async (pathOverride = null, localeOverride = null) => {
    setIsLoadingSemantic(true);
    setStatusMessage(null);
    const activeAi = Boolean(useOllama && aiEnabled);
    if (activeAi && beginAiWork) beginAiWork();
    const path = pathOverride || targetPath;
    const loc = localeOverride !== null && localeOverride !== undefined ? localeOverride : auditLocale;
    try {
      const res = await fetch('/api/hmi/semantic', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          path,
          locale: loc,
          use_ollama: activeAi,
          auto_unload: Boolean(autoUnload),
          model: ollamaModel || undefined,
        }),
      });
      const data = await res.json();
      if (data.success && data.report) {
        setSemanticReport(data.report);
        if (activeAi && data.report?.tier3_ollama?.reviews?.length > 0) {
          setShowAiModal(true);
        }
      } else {
        setStatusMessage({ type: 'error', text: data.error || 'Failed to execute semantic audit' });
      }
    } catch (err) {
      setStatusMessage({ type: 'error', text: `Semantic audit error: ${err.message}` });
    } finally {
      setIsLoadingSemantic(false);
      if (activeAi && endAiWork) endAiWork();
    }
  }, [targetPath, auditLocale, useOllama, aiEnabled, ollamaModel, autoUnload, beginAiWork, endAiWork]);

  // Fetch HMI binary info and audit findings
  const fetchAuditData = useCallback(async (pathOverride = null, localeOverride = null) => {
    const path = pathOverride || targetPath;
    if (!path) return;
    setIsLoading(true);
    setStatusMessage(null);
    const loc = localeOverride !== null && localeOverride !== undefined ? localeOverride : auditLocale;
    try {
      const [infoRes, auditRes] = await Promise.all([
        fetch(`/api/hmi/info?path=${encodeURIComponent(path)}`),
        fetch(`/api/hmi/audit?path=${encodeURIComponent(path)}&locale=${encodeURIComponent(loc)}`),
      ]);

      const infoData = await infoRes.json();
      const auditData = await auditRes.json();

      if (infoData.success) {
        setHmiInfo(infoData);
      } else {
        setStatusMessage({ type: 'error', text: infoData.error || 'Failed to inspect binary' });
      }

      if (auditData.success) {
        setFindings(auditData.findings || []);
        if (auditData.findings && auditData.findings.length > 0) {
          setSelectedFinding(auditData.findings[0]);
        } else {
          setSelectedFinding(null);
        }
      }
    } catch (err) {
      setStatusMessage({ type: 'error', text: `Network or Server Error: ${err.message}` });
    } finally {
      setIsLoading(false);
    }
  }, [targetPath, auditLocale]);

  // Fetch language list and phrases
  const fetchLanguages = useCallback(async (pathOverride = null) => {
    const path = pathOverride || targetPath;
    if (!path) return;
    try {
      const res = await fetch(`/api/hmi/languages?path=${encodeURIComponent(path)}`);
      const data = await res.json();
      if (data.success) {
        setLanguages(data.languages || []);
      }
    } catch (e) {
      console.error('Failed to fetch languages:', e);
    }
  }, [targetPath]);

  // Dynamically discover local firmware targets
  const fetchDiscoveredTargets = useCallback(async (autoSelect = false) => {
    setIsDiscovering(true);
    try {
      const res = await fetch('/api/hmi/discover');
      const data = await res.json();
      if (data.success && Array.isArray(data.targets)) {
        setDiscoveredTargets(data.targets);
        if (data.default_dir) setDefaultDir(data.default_dir);
        if (autoSelect && data.targets.length > 0) {
          setTargetPath((current) => {
            if (!current) {
              const first = data.targets[0].path;
              fetchAuditData(first);
              fetchLanguages(first);
              return first;
            }
            return current;
          });
        }
      }
    } catch (err) {
      console.error('Failed to discover firmware targets:', err);
    } finally {
      setIsDiscovering(false);
    }
  }, [fetchAuditData, fetchLanguages]);

  const toggleAutoScan = useCallback(() => {
    setAutoScanDownloads((prev) => {
      const next = !prev;
      try {
        localStorage.setItem('spectra_hmi_auto_scan', next ? 'true' : 'false');
      } catch (e) {
        console.warn('Failed to save auto scan preference:', e);
      }
      if (next) {
        fetchDiscoveredTargets(true);
      }
      return next;
    });
  }, [fetchDiscoveredTargets]);

  // Launch native OS file chooser
  const handleBrowseTarget = async () => {
    try {
      const res = await fetch('/api/hmi/browse', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ initial_dir: defaultDir || undefined }),
      });
      const data = await res.json();
      if (data.success && data.path) {
        setTargetPath(data.path);
        fetchAuditData(data.path);
        fetchLanguages(data.path);
        fetchDiscoveredTargets(false);
      }
    } catch (err) {
      console.error('Failed to browse target path:', err);
    }
  };

  const phrasesAbortRef = useRef(null);

  const fetchPhrases = useCallback(async (locale, query = '') => {
    if (!targetPath) return;
    if (phrasesAbortRef.current) {
      try { phrasesAbortRef.current.abort(); } catch {}
    }
    const controller = new AbortController();
    phrasesAbortRef.current = controller;
    try {
      const res = await fetch(
        `/api/hmi/phrases?path=${encodeURIComponent(targetPath)}&locale=${encodeURIComponent(locale)}&query=${encodeURIComponent(query)}`,
        { signal: controller.signal }
      );
      const data = await res.json();
      if (data.success) {
        setPhrases(data.phrases || []);
      }
    } catch (e) {
      if (e?.name === 'AbortError') return;
      console.error('Failed to fetch phrases:', e);
    }
  }, [targetPath]);

  // Initial load: discover targets and load first found target if autoScan is enabled
  useEffect(() => {
    if (autoScanDownloads) {
      fetchDiscoveredTargets(true);
    }
  }, [fetchDiscoveredTargets, autoScanDownloads]);

  // Load phrases on tab or locale change with 250 ms search debounce & AbortController cleanup
  useEffect(() => {
    if (subTab !== 'explorer') return;
    const delay = searchQuery ? 250 : 0;
    const timer = setTimeout(() => {
      fetchPhrases(selectedLocale, searchQuery);
    }, delay);
    return () => {
      clearTimeout(timer);
      if (phrasesAbortRef.current) {
        try { phrasesAbortRef.current.abort(); } catch {}
      }
    };
  }, [subTab, selectedLocale, searchQuery, fetchPhrases]);

  // Handle Patch Action
  const handleApplyPatches = async () => {
    if (!hmiInfo) return;
    setIsPatching(true);
    setStatusMessage(null);
    try {
      const res = await fetch('/api/hmi/patch', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ path: targetPath }),
      });
      const data = await res.json();
      if (data.success) {
        setPatchResult(data.result);
        setStatusMessage({
          type: 'success',
          text: `Patched binary created successfully at: ${data.result.output_path}`,
        });
        // Auto-switch inspector to the patched binary
        setTargetPath(data.result.output_path);
        fetchAuditData(data.result.output_path);
      } else {
        setStatusMessage({ type: 'error', text: `Patch Failed: ${data.error}` });
      }
    } catch (err) {
      setStatusMessage({ type: 'error', text: `Patch Request Error: ${err.message}` });
    } finally {
      setIsPatching(false);
    }
  };

  // Handle Export Report Action
  const handleExportReport = async (fmt = 'md') => {
    setIsExporting(true);
    setExportNotice(null);
    try {
      const res = await fetch('/api/hmi/export_report', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ path: targetPath, save_dialog: true, format: fmt, locale: auditLocale }),
      });
      let data;
      const contentType = res.headers.get('content-type') || '';
      if (contentType.includes('application/json')) {
        data = await res.json();
      } else {
        const text = await res.text();
        data = { success: false, error: !res.ok ? `Server error (${res.status}): ${text.slice(0, 200)}` : text };
      }
      if (data.success && data.saved_path) {
        setExportNotice(`✓ Audit report saved to: ${data.saved_path}`);
      } else if (data.cancelled) {
        setExportNotice('Export cancelled.');
      } else {
        setExportNotice(`Export Error: ${data.error || 'Failed to export'}`);
      }
    } catch (err) {
      setExportNotice(`Export Request Error: ${err.message}`);
    } finally {
      setIsExporting(false);
    }
  };

  const copyToClipboard = useCallback(async (text) => {
    const ok = await copyTextSafe(text);
    if (ok) {
      setCopiedSha(true);
      setTimeout(() => setCopiedSha(false), 2000);
    }
  }, []);

  const filteredFindings = findings.filter((f) => {
    if (severityFilter === 'ALL') return true;
    if (severityFilter === 'FIXED') return f.status === 'FIXED';
    return f.severity === severityFilter && f.status !== 'FIXED';
  });

  // AI Reviews computations & filtering
  const aiReviews = semanticReport?.tier3_ollama?.reviews || [];
  const aiDefectsCount = semanticReport?.tier3_ollama?.confirmed_defects_count ?? aiReviews.filter((r) => !r.is_correct).length;
  const aiVerifiedCount = semanticReport?.tier3_ollama?.verified_ok_count ?? aiReviews.filter((r) => r.is_correct).length;
  const filteredAiReviews = aiReviews.filter((r) => {
    if (aiResultFilter === 'DEFECTS') return !r.is_correct;
    if (aiResultFilter === 'VERIFIED') return r.is_correct;
    return true;
  });

  // Flagged phrases computations & filtering
  const flaggedList = semanticReport?.flagged_phrases || [];
  const flaggedAllCount = flaggedList.length;
  const flaggedScannedCount = flaggedList.filter((f) => f.ollama_review).length;
  const flaggedDefectsCount = flaggedList.filter((f) => f.ollama_review && !f.ollama_review.is_correct).length;
  const flaggedSuggestedCount = flaggedList.filter((f) => f.suggested_val).length;
  const filteredFlaggedPhrases = flaggedList.filter((f) => {
    if (anomalyFilter === 'OLLAMA_SCANNED') return Boolean(f.ollama_review);
    if (anomalyFilter === 'AI_DEFECTS') return f.ollama_review && !f.ollama_review.is_correct;
    if (anomalyFilter === 'AI_VERIFIED') return f.ollama_review && f.ollama_review.is_correct;
    if (anomalyFilter === 'GLOSSARY') return Boolean(f.suggested_val);
    return true;
  });

  return (
    <div className="space-y-4 font-sans text-xs">
      {/* 1. TOP HEADER & METADATA BAR */}
      <HmiHeaderBar
        theme={theme}
        lang={lang}
        t={t}
        hmiInfo={hmiInfo}
        findings={findings}
        targetPath={targetPath}
        setTargetPath={setTargetPath}
        autoScanDownloads={autoScanDownloads}
        discoveredTargets={discoveredTargets}
        isDiscovering={isDiscovering}
        isLoading={isLoading}
        isPatching={isPatching}
        isExporting={isExporting}
        copiedSha={copiedSha}
        statusMessage={statusMessage}
        setStatusMessage={setStatusMessage}
        exportNotice={exportNotice}
        setExportNotice={setExportNotice}
        onRescan={fetchAuditData}
        onApplyPatches={handleApplyPatches}
        onExportReport={handleExportReport}
        onBrowseTarget={handleBrowseTarget}
        onDiscoverTargets={fetchDiscoveredTargets}
        onToggleAutoScan={toggleAutoScan}
        onSelectTarget={(path) => {
          setTargetPath(path);
          fetchAuditData(path);
          fetchLanguages(path);
        }}
        onCopySha={copyToClipboard}
      />

      {/* 2. SUB-TABS NAVIGATION */}
      <div className="flex border-b border-zinc-800 space-x-2 px-1">
        <button
          onClick={() => setSubTab('audit')}
          className={`pb-2 px-3 font-bold tracking-wider transition-all border-b-2 flex items-center space-x-1.5 ${
            subTab === 'audit'
              ? 'border-cyan-400 text-cyan-300'
              : 'border-transparent text-gray-400 hover:text-gray-200'
          }`}
        >
          <Shield className="w-4 h-4" />
          <span>{t('hmiSubTabAudit', { count: findings.length })}</span>
        </button>
        <button
          onClick={() => {
            setSubTab('semantic');
            if (!semanticReport) fetchSemanticData();
          }}
          className={`pb-2 px-3 font-bold tracking-wider transition-all border-b-2 flex items-center space-x-1.5 ${
            subTab === 'semantic'
              ? 'border-purple-400 text-purple-300'
              : 'border-transparent text-gray-400 hover:text-gray-200'
          }`}
        >
          <Sparkles className="w-4 h-4" />
          <span>{t('hmiSubTabSemantic')}</span>
        </button>
        <button
          onClick={() => setSubTab('explorer')}
          className={`pb-2 px-3 font-bold tracking-wider transition-all border-b-2 flex items-center space-x-1.5 ${
            subTab === 'explorer'
              ? 'border-cyan-400 text-cyan-300'
              : 'border-transparent text-gray-400 hover:text-gray-200'
          }`}
        >
          <Layers className="w-4 h-4" />
          <span>{t('hmiSubTabExplorer')}</span>
        </button>
      </div>

      {/* TAB 1: AUTOMATED AUDIT FINDINGS */}
      {subTab === 'audit' && (
        <HmiAuditFindingsView
          severityFilter={severityFilter}
          setSeverityFilter={setSeverityFilter}
          auditLocale={auditLocale}
          languages={languages}
          filteredFindings={filteredFindings}
          selectedFinding={selectedFinding}
          setSelectedFinding={setSelectedFinding}
          onChangeAuditLocale={(newLoc) => {
            setAuditLocale(newLoc);
            fetchAuditData(null, newLoc);
          }}
        />
      )}

      {/* TAB 2: 3-TIER OFFLINE SEMANTIC HYBRID AUDITOR & GLOSSARY */}
      {subTab === 'semantic' && (
        <HmiSemanticAuditView
          auditLocale={auditLocale}
          setAuditLocale={setAuditLocale}
          effectiveLanguages={effectiveLanguages}
          useOllama={useOllama}
          setUseOllama={setUseOllama}
          aiEnabled={aiEnabled}
          onToggleAi={onToggleAi}
          ollamaModel={ollamaModel}
          setOllamaModel={setOllamaModel}
          onGlobalModelChange={onGlobalModelChange}
          effectiveModelCatalog={effectiveModelCatalog}
          autoUnload={autoUnload}
          setAutoUnload={setAutoUnload}
          aiStatus={aiStatus}
          isLoadingAiStatus={isLoadingAiStatus}
          onRefreshAiStatus={fetchAiStatus}
          isOperatingOllama={isOperatingOllama}
          onControlOllama={controlOllama}
          pullProgress={pullProgress}
          setPullProgress={setPullProgress}
          semanticReport={semanticReport}
          isLoadingSemantic={isLoadingSemantic}
          semanticProgress={semanticProgress}
          onRunSemanticAudit={fetchSemanticData}
          aiReviews={aiReviews}
          aiDefectsCount={aiDefectsCount}
          aiVerifiedCount={aiVerifiedCount}
          aiResultFilter={aiResultFilter}
          setAiResultFilter={setAiResultFilter}
          filteredAiReviews={filteredAiReviews}
          onOpenAiModal={() => setShowAiModal(true)}
          anomalyFilter={anomalyFilter}
          setAnomalyFilter={setAnomalyFilter}
          flaggedAllCount={flaggedAllCount}
          flaggedScannedCount={flaggedScannedCount}
          flaggedDefectsCount={flaggedDefectsCount}
          flaggedSuggestedCount={flaggedSuggestedCount}
          filteredFlaggedPhrases={filteredFlaggedPhrases}
        />
      )}

      {/* TAB 3: MULTI-LOCALE EXPLORER */}
      {subTab === 'explorer' && (
        <HmiPhraseExplorerView
          selectedLocale={selectedLocale}
          setSelectedLocale={setSelectedLocale}
          languages={languages}
          phrases={phrases}
          searchQuery={searchQuery}
          setSearchQuery={setSearchQuery}
        />
      )}

      {/* Pop-out Local Ollama AI Scan Results Window / Modal */}
      <HmiAiResultsModal
        show={showAiModal}
        onClose={() => setShowAiModal(false)}
        semanticReport={semanticReport}
        ollamaModel={ollamaModel}
        auditLocale={auditLocale}
        aiReviews={aiReviews}
        aiDefectsCount={aiDefectsCount}
        aiVerifiedCount={aiVerifiedCount}
        aiResultFilter={aiResultFilter}
        setAiResultFilter={setAiResultFilter}
        filteredAiReviews={filteredAiReviews}
      />
    </div>
  );
}

export default React.memo(HmiInspectorTab);
