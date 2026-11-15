import React, { useState, useEffect, useCallback, useRef } from 'react';
import {
  Shield,
  CheckCircle2,
  AlertTriangle,
  Info,
  Search,
  Filter,
  Download,
  Copy,
  Check,
  RefreshCw,
  FolderOpen,
  Box,
  Layers,
  FileText,
  Sparkles,
  Zap,
  ExternalLink,
  Cpu,
  HardDrive,
  Play,
  Square,
  Trash2,
  ArrowDownCircle,
  Laptop,
  Maximize2,
  ChevronDown,
  X
} from 'lucide-react';

const FALLBACK_MODEL_CATALOG = [
  { id: 'qwen2.5:0.5b', name: 'Qwen 2.5 0.5B (Ultra-Light)', min_ram_mb: 800, disk_mb: 398, languages: '29+ CS/EN/DE/ZH', speed_cpu: 'Fast (~1.5s/phrase)', compatibility: 'RECOMMENDED' },
  { id: 'qwen2.5:1.5b', name: 'Qwen 2.5 1.5B (Balanced)', min_ram_mb: 1600, disk_mb: 986, languages: '29+ CS/EN/DE/ZH', speed_cpu: 'Medium (~3.5s/phrase)', compatibility: 'COMPATIBLE' },
  { id: 'llama3.2:1b', name: 'Llama 3.2 1B (Meta)', min_ram_mb: 1200, disk_mb: 1300, languages: 'Multilingual', speed_cpu: 'Fast (~2s/phrase)', compatibility: 'COMPATIBLE' },
  { id: 'gemma2:2b', name: 'Gemma 2 2B (Google)', min_ram_mb: 2600, disk_mb: 1600, languages: 'Multilingual', speed_cpu: 'Moderate (~5s/phrase)', compatibility: 'COMPATIBLE' },
  { id: 'llama3.2:3b', name: 'Llama 3.2 3B (Meta)', min_ram_mb: 3200, disk_mb: 2000, languages: 'Multilingual', speed_cpu: 'Moderate (~4s/phrase)', compatibility: 'COMPATIBLE' },
  { id: 'qwen2.5:3b', name: 'Qwen 2.5 3B (High Accuracy)', min_ram_mb: 3200, disk_mb: 1900, languages: '29+ High Accuracy', speed_cpu: 'Slow without AVX2/GPU', compatibility: 'COMPATIBLE' },
  { id: 'mistral:7b', name: 'Mistral 7B (Mistral AI)', min_ram_mb: 5500, disk_mb: 4100, languages: 'Multilingual', speed_cpu: 'Requires GPU / >=16GB RAM', compatibility: 'HEAVY_FOR_CPU' },
  { id: 'qwen2.5:7b', name: 'Qwen 2.5 7B (Studio Grade)', min_ram_mb: 5800, disk_mb: 4700, languages: '29+ Studio Grade', speed_cpu: 'Requires GPU / >=16GB RAM', compatibility: 'HEAVY_FOR_CPU' },
  { id: 'llama3.1:8b', name: 'Llama 3.1 8B (Meta)', min_ram_mb: 6200, disk_mb: 4900, languages: 'Multilingual', speed_cpu: 'Requires GPU / >=16GB RAM', compatibility: 'HEAVY_FOR_CPU' },
];

export default function HmiInspectorTab({
  theme,
  aiEnabled = false,
  onToggleAi = null,
  onGlobalModelChange = null,
  beginAiWork = null,
  endAiWork = null,
}) {
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

  // Compute Infallible Effective Model Catalog (merging fallback + backend + locally installed)
  const effectiveModelCatalog = React.useMemo(() => {
    const catalogMap = new Map();

    // 1. Preload all standard fallback models
    FALLBACK_MODEL_CATALOG.forEach((m) => {
      catalogMap.set(m.id, { ...m, is_installed: false, is_recommended: false });
    });

    // 2. Overlay backend hardware telemetry catalog
    if (aiStatus?.hardware?.model_catalog && Array.isArray(aiStatus.hardware.model_catalog)) {
      aiStatus.hardware.model_catalog.forEach((m) => {
        const existing = catalogMap.get(m.id) || {};
        catalogMap.set(m.id, { ...existing, ...m });
      });
    }

    // 3. Overlay any locally installed models detected in Ollama daemon
    const installed = aiStatus?.ollama?.models || [];
    installed.forEach((ins) => {
      const insId = typeof ins === 'string' ? ins : ins?.name || '';
      if (!insId) return;
      if (catalogMap.has(insId)) {
        catalogMap.get(insId).is_installed = true;
      } else {
        catalogMap.set(insId, {
          id: insId,
          name: `Custom Local: ${insId}`,
          min_ram_mb: 2048,
          disk_mb: 0,
          languages: 'Local Custom Model',
          speed_cpu: 'Custom',
          compatibility: 'COMPATIBLE',
          is_installed: true,
          is_recommended: false,
        });
      }
    });

    // Mark recommended model if matching backend recommendation
    const recId = aiStatus?.hardware?.recommended_model || 'qwen2.5:0.5b';
    if (catalogMap.has(recId)) {
      catalogMap.get(recId).is_recommended = true;
    }

    return Array.from(catalogMap.values());
  }, [aiStatus]);

  // Fallback languages array so Target Locale dropdown is never empty
  const effectiveLanguages = React.useMemo(() => {
    if (languages && languages.length > 0) return languages;
    return [
      { locale: 'cs-CZ', phrase_count: 651 },
      { locale: 'de-DE', phrase_count: 651 },
      { locale: 'en-GB', phrase_count: 651 },
      { locale: 'fr-FR', phrase_count: 651 },
      { locale: 'it-IT', phrase_count: 651 },
      { locale: 'es-ES', phrase_count: 651 },
      { locale: 'zh-CN', phrase_count: 651 },
    ];
  }, [languages]);

  // Filter states for Semantic anomalies and AI scan results
  const [anomalyFilter, setAnomalyFilter] = useState('ALL'); // 'ALL' | 'OLLAMA_SCANNED' | 'AI_DEFECTS' | 'AI_VERIFIED' | 'GLOSSARY'
  const [aiResultFilter, setAiResultFilter] = useState('ALL'); // 'ALL' | 'DEFECTS' | 'VERIFIED'
  const [showAiModal, setShowAiModal] = useState(false);

  // Async action states
  const [isLoading, setIsLoading] = useState(false);
  const [isPatching, setIsPatching] = useState(false);
  const [patchResult, setPatchResult] = useState(null);
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

  const stopProgressPolling = useCallback(() => {
    if (progressPollRef.current) {
      clearInterval(progressPollRef.current);
      progressPollRef.current = null;
    }
  }, []);

  const pollProgress = useCallback(async () => {
    try {
      const res = await fetch('/api/hmi/ollama_progress');
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
      // Ignore network blips during polling
    }
  }, [stopProgressPolling, fetchAiStatus]);

  const startProgressPolling = useCallback(() => {
    stopProgressPolling();
    pollProgress();
    progressPollRef.current = setInterval(pollProgress, 350);
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
    if (isLoadingSemantic) {
      const pollSemanticProgress = async () => {
        try {
          const res = await fetch('/api/hmi/semantic/progress');
          const data = await res.json();
          if (data && data.success && data.progress) {
            setSemanticProgress(data.progress);
          }
        } catch (e) {
          // ignore network blips during polling
        }
      };
      pollSemanticProgress();
      semanticProgressPollRef.current = setInterval(pollSemanticProgress, 400);
    } else {
      if (semanticProgressPollRef.current) {
        clearInterval(semanticProgressPollRef.current);
        semanticProgressPollRef.current = null;
      }
    }
    return () => {
      if (semanticProgressPollRef.current) {
        clearInterval(semanticProgressPollRef.current);
        semanticProgressPollRef.current = null;
      }
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
      const res = await fetch(
        `/api/hmi/semantic?path=${encodeURIComponent(path)}&locale=${encodeURIComponent(loc)}&use_ollama=${activeAi ? 'true' : 'false'}&auto_unload=${autoUnload ? 'true' : 'false'}${ollamaModel ? `&model=${encodeURIComponent(ollamaModel)}` : ''}`
      );
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

  const fetchPhrases = useCallback(async (locale, query = '') => {
    if (!targetPath) return;
    try {
      const res = await fetch(
        `/api/hmi/phrases?path=${encodeURIComponent(targetPath)}&locale=${encodeURIComponent(locale)}&query=${encodeURIComponent(query)}`
      );
      const data = await res.json();
      if (data.success) {
        setPhrases(data.phrases || []);
      }
    } catch (e) {
      console.error('Failed to fetch phrases:', e);
    }
  }, [targetPath]);

  // Initial load: discover targets and load first found target if autoScan is enabled
  useEffect(() => {
    if (autoScanDownloads) {
      fetchDiscoveredTargets(true);
    }
  }, [fetchDiscoveredTargets, autoScanDownloads]);

  // Load phrases on tab or locale change
  useEffect(() => {
    if (subTab === 'explorer') {
      fetchPhrases(selectedLocale, searchQuery);
    }
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

  const copyToClipboard = (text) => {
    navigator.clipboard.writeText(text);
    setCopiedSha(true);
    setTimeout(() => setCopiedSha(false), 2000);
  };

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

  const renderAiResultsContent = (isModal = false) => {
    const tier3 = semanticReport?.tier3_ollama;
    if (!tier3 || !aiReviews.length) return null;

    return (
      <div className="space-y-3">
        {/* KPI Summary Badges */}
        <div className="flex flex-wrap items-center gap-2 text-xs font-mono">
          <span className="px-2.5 py-1 rounded bg-purple-950/80 border border-purple-700 text-purple-300 font-bold">
            Model: {tier3.active_model || ollamaModel || 'qwen2.5:1.5b'}
          </span>
          <span className="px-2.5 py-1 rounded bg-zinc-900 border border-zinc-700 text-gray-200">
            Scanned: <span className="font-bold text-white">{aiReviews.length}</span> phrases
          </span>
          <span className="px-2.5 py-1 rounded bg-rose-950/80 border border-rose-700 text-rose-300 font-bold">
            🚨 AI Confirmed Defects: {aiDefectsCount}
          </span>
          <span className="px-2.5 py-1 rounded bg-emerald-950/80 border border-emerald-700 text-emerald-300 font-bold">
            ✅ AI Verified OK: {aiVerifiedCount}
          </span>
          <span className="px-2.5 py-1 rounded bg-blue-950/80 border border-blue-700 text-blue-300">
            ⏱️ Scan Time: <span className="font-bold">{tier3.total_elapsed_ms || 0}</span> ms
          </span>
          {tier3.ram_unloaded && (
            <span className="px-2.5 py-1 rounded bg-cyan-950/80 border border-cyan-700 text-cyan-300 font-bold">
              🧹 RAM Unloaded
            </span>
          )}
        </div>

        {/* Filter Bar inside AI Scan Results */}
        <div className="flex flex-wrap items-center gap-1.5 pt-1 text-xs">
          <button
            onClick={() => setAiResultFilter('ALL')}
            className={`px-2.5 py-1 rounded font-bold transition-all ${
              aiResultFilter === 'ALL'
                ? 'bg-purple-600 text-white shadow-sm'
                : 'bg-zinc-900 hover:bg-zinc-800 text-zinc-300 border border-zinc-700'
            }`}
          >
            ALL SCANNED ({aiReviews.length})
          </button>
          <button
            onClick={() => setAiResultFilter('DEFECTS')}
            className={`px-2.5 py-1 rounded font-bold transition-all ${
              aiResultFilter === 'DEFECTS'
                ? 'bg-rose-600 text-white shadow-sm'
                : 'bg-zinc-900 hover:bg-zinc-800 text-rose-300 border border-zinc-700'
            }`}
          >
            🚨 AI CONFIRMED DEFECTS ({aiDefectsCount})
          </button>
          <button
            onClick={() => setAiResultFilter('VERIFIED')}
            className={`px-2.5 py-1 rounded font-bold transition-all ${
              aiResultFilter === 'VERIFIED'
                ? 'bg-emerald-600 text-white shadow-sm'
                : 'bg-zinc-900 hover:bg-zinc-800 text-emerald-300 border border-zinc-700'
            }`}
          >
            ✅ AI VERIFIED OK ({aiVerifiedCount})
          </button>
        </div>

        {/* AI Results Table */}
        <div className={`overflow-x-auto overflow-y-auto border border-zinc-800 rounded bg-black/40 ${isModal ? 'max-h-[55vh]' : 'max-h-[360px]'}`}>
          <table className="w-full text-left border-collapse text-[11px]">
            <thead className="sticky top-0 bg-zinc-900 border-b border-zinc-800 text-gray-400 text-[10px] uppercase font-mono z-10">
              <tr>
                <th className="p-2.5 w-40">AI Verdict</th>
                <th className="p-2.5">Key & English Baseline (en-GB)</th>
                <th className="p-2.5">Current Firmware ({auditLocale})</th>
                <th className="p-2.5">🤖 AI Suggested Fix</th>
                <th className="p-2.5">Diagnostic Reasoning</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-zinc-800/60 text-gray-200">
              {filteredAiReviews.map((r, idx) => {
                const isDiff = r.suggested_translation && r.suggested_translation !== r.target_val;
                return (
                  <tr key={idx} className="hover:bg-zinc-800/40">
                    <td className="p-2.5 align-top">
                      <div className="flex flex-col space-y-1">
                        {r.is_correct ? (
                          <span className="inline-flex items-center space-x-1 px-2 py-0.5 rounded text-[10px] font-bold bg-emerald-950 text-emerald-300 border border-emerald-700 w-fit">
                            <span>✅ VERIFIED OK</span>
                          </span>
                        ) : (
                          <span className="inline-flex items-center space-x-1 px-2 py-0.5 rounded text-[10px] font-bold bg-rose-950 text-rose-300 border border-rose-700 w-fit">
                            <span>🚨 DEFECT CONFIRMED</span>
                          </span>
                        )}
                        <span className="text-[10px] text-gray-500 font-mono">
                          {r.elapsed_ms ? `${r.elapsed_ms} ms` : ''}
                        </span>
                      </div>
                    </td>
                    <td className="p-2.5 align-top max-w-[220px]">
                      <div className="font-mono font-bold text-gray-200 truncate" title={r.key}>
                        {r.key}
                      </div>
                      <div className="text-gray-400 text-xs font-sans mt-0.5" title={r.en_val}>
                        {r.en_val}
                      </div>
                    </td>
                    <td className="p-2.5 align-top max-w-[200px]">
                      <div className="text-amber-300 font-mono text-xs break-words" title={r.target_val}>
                        {r.target_val}
                      </div>
                    </td>
                    <td className="p-2.5 align-top max-w-[220px]">
                      {isDiff ? (
                        <div className="text-emerald-300 font-mono font-bold text-xs bg-emerald-950/60 p-1.5 rounded border border-emerald-700/60 break-words shadow-sm">
                          {r.suggested_translation}
                        </div>
                      ) : (
                        <div className="text-gray-500 font-mono text-xs italic">
                          Matches current ({r.target_val})
                        </div>
                      )}
                    </td>
                    <td className="p-2.5 align-top">
                      <div className="text-xs text-gray-300 font-sans leading-relaxed">
                        {r.reason}
                      </div>
                    </td>
                  </tr>
                );
              })}
              {filteredAiReviews.length === 0 && (
                <tr>
                  <td colSpan={5} className="p-6 text-center text-gray-500 font-mono text-xs">
                    No phrases matching the current filter.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    );
  };

  return (
    <div className="space-y-4 font-sans text-xs">
      {/* ==================================================================== */}
      {/* 1. TOP HEADER & METADATA BAR */}
      {/* ==================================================================== */}
      <div className={`p-4 rounded border ${theme.border} ${theme.panelBg} space-y-3`}>
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="flex items-center space-x-2.5">
            <div className="p-2 bg-cyan-950/60 border border-cyan-500/40 rounded text-cyan-400">
              <Box className="w-5 h-5" />
            </div>
            <div>
              <div className="flex items-center space-x-2">
                <h2 className="text-sm font-extrabold tracking-wider text-cyan-400">
                  SPECTRA FIRMWARE INSPECTOR &amp; BINARY AUDITOR
                </h2>
                <span className="px-2 py-0.5 text-[10px] font-bold rounded bg-cyan-950/80 border border-cyan-800 text-cyan-300">
                  {hmiInfo?.container_badge || 'ELF32 ARM (LVGL)'}
                </span>
              </div>
              <p className="text-[11px] text-gray-400">
                Multi-Container Binary Analysis (ELF32 LVGL / Android APK / MCU CTR) • Localization Audit • Lab Patcher
              </p>
            </div>
          </div>

          {/* Action Toolbar */}
          <div className="flex items-center space-x-2">
            <button
              onClick={() => fetchAuditData()}
              disabled={isLoading}
              className="flex items-center space-x-1.5 px-3 py-1.5 font-bold rounded bg-zinc-800 hover:bg-zinc-700 text-zinc-200 border border-zinc-700 transition-all"
              title="Re-run static audit"
            >
              <RefreshCw className={`w-3.5 h-3.5 ${isLoading ? 'animate-spin text-cyan-400' : ''}`} />
              <span>RE-SCAN</span>
            </button>

            <button
              onClick={handleApplyPatches}
              disabled={isPatching || isLoading || !hmiInfo}
              className="flex items-center space-x-1.5 px-3 py-1.5 font-bold rounded bg-gradient-to-r from-cyan-600 to-blue-600 hover:from-cyan-500 hover:to-blue-500 text-black shadow-[0_0_12px_rgba(6,182,212,0.4)] transition-all font-mono"
              title="Create a patched laboratory copy of the binary fixing all detected defects"
            >
              <Sparkles className="w-3.5 h-3.5 text-black" />
              <span>{isPatching ? 'PATCHING...' : '🩹 PATCH BINARY (LAB)'}</span>
            </button>

            <div className="flex items-center rounded border border-zinc-700 bg-zinc-900/60 overflow-hidden">
              <button
                onClick={() => handleExportReport('md')}
                disabled={isExporting || !hmiInfo}
                className="px-2.5 py-1.5 font-bold text-gray-300 hover:text-white hover:bg-zinc-800 transition-colors flex items-center space-x-1"
                title="Export report as Markdown"
              >
                <FileText className="w-3.5 h-3.5 text-cyan-400" />
                <span>MD</span>
              </button>
              <button
                onClick={() => handleExportReport('html')}
                disabled={isExporting || !hmiInfo}
                className="px-2.5 py-1.5 font-bold text-gray-300 hover:text-white hover:bg-zinc-800 transition-colors border-l border-zinc-700"
                title="Export report as HTML"
              >
                HTML
              </button>
              <button
                onClick={() => handleExportReport('pdf')}
                disabled={isExporting || !hmiInfo}
                className="px-2.5 py-1.5 font-bold text-gray-300 hover:text-white hover:bg-zinc-800 transition-colors border-l border-zinc-700"
                title="Export report as PDF (via LibreOffice)"
              >
                PDF
              </button>
            </div>
          </div>
        </div>

        {/* Binary Path Selector */}
        <div className="flex items-center space-x-2 pt-1 flex-wrap gap-y-2">
          <div className="flex items-center space-x-2 flex-1 min-w-[320px]">
            <span className="text-gray-400 font-bold shrink-0">Target Binary / Update Dir:</span>
            <input
              type="text"
              value={targetPath}
              onChange={(e) => setTargetPath(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && fetchAuditData()}
              className="flex-1 bg-black/60 border border-zinc-700 rounded px-2.5 py-1 text-gray-200 font-mono text-[11px] focus:outline-none focus:border-cyan-500"
              placeholder="Select or enter firmware binary (ELF, .apk, .bin) or update directory..."
            />
            <button
              onClick={() => fetchAuditData()}
              className="px-3 py-1 font-bold rounded bg-cyan-950 border border-cyan-800 text-cyan-300 hover:bg-cyan-900 transition-colors shrink-0"
            >
              LOAD
            </button>
            <button
              onClick={handleBrowseTarget}
              className="px-2.5 py-1 font-bold rounded bg-zinc-800 border border-zinc-600 text-zinc-200 hover:bg-zinc-700 hover:text-white transition-colors text-[11px] flex items-center space-x-1 shrink-0"
              title="Open file chooser dialog"
            >
              <FolderOpen className="w-3.5 h-3.5 text-cyan-400" />
              <span>BROWSE...</span>
            </button>
            <button
              onClick={() => fetchDiscoveredTargets(false)}
              disabled={isDiscovering}
              className="p-1 rounded bg-zinc-800 border border-zinc-700 text-zinc-400 hover:text-cyan-300 transition-colors text-[10px] shrink-0"
              title="Re-scan ~/Downloads for firmware targets"
            >
              <RefreshCw className={`w-3.5 h-3.5 ${isDiscovering ? 'animate-spin text-cyan-400' : ''}`} />
            </button>
            <button
              onClick={toggleAutoScan}
              className={`px-2 py-1 font-mono font-bold rounded border text-[10px] transition-colors shrink-0 ${
                autoScanDownloads
                  ? 'bg-cyan-950/70 border-cyan-500/60 text-cyan-300 hover:bg-cyan-900/60'
                  : 'bg-zinc-800/80 border-zinc-700 text-zinc-400 hover:text-zinc-200'
              }`}
              title={autoScanDownloads ? 'Auto-scan is enabled (click to pause)' : 'Auto-scan is paused (click to enable)'}
            >
              AUTO-SCAN: {autoScanDownloads ? 'ON' : 'OFF'}
            </button>
          </div>

          {/* Dynamic Discovered Targets Chips */}
          {autoScanDownloads ? (
            discoveredTargets.length > 0 && (
              <div className="flex items-center space-x-1.5 shrink-0 overflow-x-auto max-w-full pb-0.5">
                {discoveredTargets.slice(0, 6).map((t, idx) => {
                  const isSelected = targetPath === t.path;
                  const isApk = t.container_type === 'ANDROID_APK';
                  const isBin = t.container_type === 'MCU_CTR_BIN';
                  const activeClass = isSelected
                    ? 'bg-cyan-900 border-cyan-400 text-cyan-200 ring-1 ring-cyan-400/50'
                    : isApk
                    ? 'bg-cyan-950/60 border-cyan-800/80 text-cyan-300 hover:bg-cyan-900/60'
                    : isBin
                    ? 'bg-amber-950/40 border-amber-800/80 text-amber-300 hover:bg-amber-900/60'
                    : 'bg-zinc-800 border-zinc-700 text-zinc-300 hover:bg-zinc-700 hover:text-white';

                  return (
                    <button
                      key={t.path || idx}
                      onClick={() => {
                        setTargetPath(t.path);
                        fetchAuditData(t.path);
                        fetchLanguages(t.path);
                      }}
                      className={`px-2 py-1 font-bold rounded border transition-colors text-[10px] truncate max-w-[160px] ${activeClass}`}
                      title={`${t.label}\nPath: ${t.path}\nSize: ${(t.size / 1024).toFixed(0)} KB`}
                    >
                      {t.label || t.name}
                    </button>
                  );
                })}
              </div>
            )
          ) : (
            <div className="text-[11px] font-mono text-zinc-500 italic flex items-center py-0.5">
              Auto-scan paused — use BROWSE... to select a firmware file/folder or enable AUTO-SCAN
            </div>
          )}
        </div>

        {/* Metadata KPI Row */}
        {hmiInfo && (
          <div className="grid grid-cols-1 md:grid-cols-4 gap-2 pt-2 border-t border-zinc-800/80">
            {/* 1. File Details */}
            <div className="p-2 bg-black/40 border border-zinc-800 rounded">
              <div className="text-[10px] text-gray-500 font-bold uppercase">BINARY CONTAINER</div>
              <div className="text-xs font-bold text-gray-200 truncate mt-0.5" title={hmiInfo.binary_path}>
                {hmiInfo.binary_path.split('/').pop()}
              </div>
              <div className="text-[10px] text-gray-400 font-mono">
                {(hmiInfo.file_size / (1024 * 1024)).toFixed(1)} MB ({hmiInfo.file_size?.toLocaleString()} bytes)
              </div>
              {hmiInfo.companion_ctr_bin && (
                <div className="text-[9px] text-amber-400 font-mono truncate mt-0.5" title={hmiInfo.companion_ctr_bin}>
                  CTR: {hmiInfo.companion_ctr_bin.split('/').pop()}
                </div>
              )}
            </div>

            {/* 2. SHA-256 */}
            <div className="p-2 bg-black/40 border border-zinc-800 rounded">
              <div className="text-[10px] text-gray-500 font-bold uppercase flex items-center justify-between">
                <span>SHA-256 CHECKSUM</span>
                <button
                  onClick={() => copyToClipboard(hmiInfo.sha256)}
                  className="text-cyan-400 hover:text-cyan-300 flex items-center space-x-0.5 text-[9px]"
                  title="Copy full SHA-256"
                >
                  {copiedSha ? <Check className="w-3 h-3 text-emerald-400" /> : <Copy className="w-3 h-3" />}
                  <span>{copiedSha ? 'COPIED' : 'COPY'}</span>
                </button>
              </div>
              <div className="text-xs font-mono font-bold text-cyan-300 truncate mt-0.5" title={hmiInfo.sha256}>
                {hmiInfo.sha256?.substring(0, 20)}...
              </div>
              <div className="text-[10px] text-gray-400 font-mono">
                {hmiInfo.sections_count} ELF sections • {hmiInfo.symbols_count} symbols
              </div>
            </div>

            {/* 3. Signature Status */}
            <div className="p-2 bg-black/40 border border-zinc-800 rounded">
              <div className="text-[10px] text-gray-500 font-bold uppercase">SIGNATURE PIPELINE</div>
              <div
                className={`text-xs font-bold mt-0.5 truncate ${
                  hmiInfo.signature_present ? 'text-emerald-400' : 'text-amber-400'
                }`}
              >
                {hmiInfo.signature_status}
              </div>
              <div className="text-[10px] text-gray-400 truncate" title={hmiInfo.warning}>
                {hmiInfo.signature_present ? 'RSA-2048 (KLM_SIGN.pem)' : 'No Signature Container'}
              </div>
            </div>

            {/* 4. Audit Summary */}
            <div className="p-2 bg-black/40 border border-zinc-800 rounded">
              <div className="text-[10px] text-gray-500 font-bold uppercase">AUDIT VERDICT</div>
              <div className="text-xs font-bold mt-0.5 flex items-center space-x-1.5">
                {findings.some((f) => f.status === 'DETECTED' && f.severity === 'CRITICAL') ? (
                  <span className="text-rose-400 flex items-center space-x-1">
                    <AlertTriangle className="w-3.5 h-3.5" />
                    <span>DEFECTS DETECTED</span>
                  </span>
                ) : (
                  <span className="text-emerald-400 flex items-center space-x-1">
                    <CheckCircle2 className="w-3.5 h-3.5" />
                    <span>ALL CHECKS PASSED</span>
                  </span>
                )}
              </div>
              <div className="text-[10px] text-gray-400 font-mono">
                {findings.filter((f) => f.status === 'FIXED').length} FIXED •{' '}
                {findings.filter((f) => f.status === 'DETECTED').length} VULNERABLE
              </div>
            </div>
          </div>
        )}

        {/* Status / Error Toast */}
        {statusMessage && (
          <div
            className={`p-2.5 rounded text-xs flex items-center justify-between ${
              statusMessage.type === 'error'
                ? 'bg-rose-950/80 border border-rose-600/60 text-rose-200'
                : 'bg-emerald-950/80 border border-emerald-600/60 text-emerald-200'
            }`}
          >
            <span>{statusMessage.text}</span>
            <button onClick={() => setStatusMessage(null)} className="text-gray-400 hover:text-white">
              ✕
            </button>
          </div>
        )}

        {exportNotice && (
          <div className="p-2.5 rounded text-xs bg-cyan-950/80 border border-cyan-600/60 text-cyan-200 flex items-center justify-between">
            <span>{exportNotice}</span>
            <button onClick={() => setExportNotice(null)} className="text-gray-400 hover:text-white">
              ✕
            </button>
          </div>
        )}
      </div>

      {/* ==================================================================== */}
      {/* 2. SUB-TABS NAVIGATION */}
      {/* ==================================================================== */}
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
          <span>🛡️ AUTOMATED FIRMWARE AUDIT ({findings.length})</span>
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
          <span>🧠 3-TIER OFFLINE AI & GLOSSARY</span>
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
          <span>🔍 TRANSLATION & POINTER EXPLORER</span>
        </button>
      </div>

      {/* ==================================================================== */}
      {/* TAB 1: AUTOMATED AUDIT FINDINGS */}
      {/* ==================================================================== */}
      {subTab === 'audit' && (
        <div className="space-y-4">
          {/* Filters Bar */}
          <div className="flex flex-wrap items-center justify-between gap-3 bg-zinc-900/60 p-2.5 rounded border border-zinc-800">
            <div className="flex items-center space-x-2">
              <span className="text-gray-400 font-bold">Severity Filter:</span>
              {['ALL', 'CRITICAL', 'WARNING', 'FIXED'].map((sev) => (
                <button
                  key={sev}
                  onClick={() => setSeverityFilter(sev)}
                  className={`px-2.5 py-0.5 rounded text-[11px] font-bold transition-all border ${
                    severityFilter === sev
                      ? 'bg-cyan-950 border-cyan-500 text-cyan-300 shadow-[0_0_8px_rgba(6,182,212,0.3)]'
                      : 'bg-zinc-900 border-zinc-800 text-gray-400 hover:text-gray-200'
                  }`}
                >
                  {sev}
                </button>
              ))}
            </div>

            <div className="flex items-center space-x-2">
              <span className="text-gray-400 font-bold">Target Audit Locale:</span>
              <select
                value={auditLocale}
                onChange={(e) => {
                  const newLoc = e.target.value;
                  setAuditLocale(newLoc);
                  fetchAuditData(null, newLoc);
                }}
                className="bg-black/80 border border-zinc-700 rounded px-2.5 py-1 text-cyan-300 font-mono text-[11px] focus:outline-none focus:border-cyan-500"
              >
                {(languages.length > 0 ? languages.map(l => l.locale) : [
                  'cs-CZ', 'en-GB', 'de-DE', 'da-DK', 'el-GR', 'es-ES', 'fr-FR',
                  'hr-HR', 'hu-HU', 'it-IT', 'ja-JP', 'ko-KR', 'nl-NL', 'pl-PL',
                  'pt-PT', 'ru-RU', 'sv-SE', 'zh-CN', 'zh-TW'
                ]).map((loc) => (
                  <option key={loc} value={loc} className="bg-zinc-900 text-gray-200">
                    {loc} {loc === 'cs-CZ' ? '(Czech Republic — Target)' : loc === 'en-GB' ? '(English UK — Base)' : ''}
                  </option>
                ))}
              </select>
            </div>
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-12 gap-4">
            {/* Findings Table */}
            <div className="lg:col-span-8 overflow-x-auto rounded border border-zinc-800 bg-[#121218]">
              <table className="w-full text-left border-collapse">
                <thead>
                  <tr className="border-b border-zinc-800 bg-zinc-900/60 text-gray-400 font-bold uppercase text-[10px]">
                    <th className="p-2.5">Severity</th>
                    <th className="p-2.5">Finding ID / Key</th>
                    <th className="p-2.5">Locale</th>
                    <th className="p-2.5">Current Value</th>
                    <th className="p-2.5">Target Value</th>
                    <th className="p-2.5">Status</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-zinc-800/60">
                  {filteredFindings.map((f) => {
                    const isSelected = selectedFinding?.id === f.id;
                    return (
                      <tr
                        key={f.id}
                        onClick={() => setSelectedFinding(f)}
                        className={`cursor-pointer transition-colors ${
                          isSelected ? 'bg-cyan-950/40 text-cyan-200' : 'hover:bg-zinc-800/40 text-gray-300'
                        }`}
                      >
                        <td className="p-2.5">
                          {f.severity === 'CRITICAL' && (
                            <span className="px-2 py-0.5 rounded font-extrabold text-[10px] bg-rose-950 border border-rose-500 text-rose-300">
                              CRITICAL
                            </span>
                          )}
                          {f.severity === 'WARNING' && (
                            <span className="px-2 py-0.5 rounded font-extrabold text-[10px] bg-amber-950 border border-amber-500 text-amber-300">
                              WARNING
                            </span>
                          )}
                          {f.severity === 'INFO' && (
                            <span className="px-2 py-0.5 rounded font-extrabold text-[10px] bg-blue-950 border border-blue-500 text-blue-300">
                              INFO
                            </span>
                          )}
                        </td>
                        <td className="p-2.5 font-mono text-[11px] font-bold">
                          <div>{f.id}</div>
                          <div className="text-[10px] text-gray-400 font-normal">{f.key}</div>
                        </td>
                        <td className="p-2.5 font-mono">{f.locale}</td>
                        <td className="p-2.5 text-gray-200 truncate max-w-[160px]" title={f.current_val}>
                          {f.current_val}
                        </td>
                        <td className="p-2.5 text-cyan-300 truncate max-w-[160px]" title={f.expected_val}>
                          {f.expected_val}
                        </td>
                        <td className="p-2.5">
                          {f.status === 'FIXED' ? (
                            <span className="px-2 py-0.5 rounded font-bold text-[10px] bg-emerald-950 border border-emerald-500 text-emerald-300 flex items-center space-x-1 w-fit">
                              <CheckCircle2 className="w-3 h-3" />
                              <span>FIXED</span>
                            </span>
                          ) : (
                            <span className="px-2 py-0.5 rounded font-bold text-[10px] bg-rose-950/80 border border-rose-600 text-rose-300 flex items-center space-x-1 w-fit">
                              <AlertTriangle className="w-3 h-3" />
                              <span>DETECTED</span>
                            </span>
                          )}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>

            {/* Finding Detail Card */}
            <div className="lg:col-span-4 rounded border border-zinc-800 bg-[#121218] p-4 space-y-3">
              <h3 className="text-xs font-bold uppercase tracking-wider text-cyan-400 flex items-center space-x-1.5 border-b border-zinc-800 pb-2">
                <Info className="w-4 h-4" />
                <span>Finding Root Cause & Remediation</span>
              </h3>

              {selectedFinding ? (
                <div className="space-y-3 text-gray-300">
                  <div>
                    <div className="text-[10px] text-gray-500 font-bold uppercase">DEFECT ID & CATEGORY</div>
                    <div className="text-xs font-bold text-gray-100">{selectedFinding.id}</div>
                    <div className="text-[11px] text-cyan-300">{selectedFinding.category}</div>
                  </div>

                  <div>
                    <div className="text-[10px] text-gray-500 font-bold uppercase">DESCRIPTION</div>
                    <div className="text-xs text-gray-300 leading-relaxed bg-black/40 p-2.5 rounded border border-zinc-800/80 mt-1">
                      {selectedFinding.description}
                    </div>
                  </div>

                  <div className="grid grid-cols-2 gap-2 text-[11px]">
                    <div>
                      <span className="text-gray-500">Locale:</span>{' '}
                      <span className="font-mono text-gray-200">{selectedFinding.locale}</span>
                    </div>
                    <div>
                      <span className="text-gray-500">Patchable:</span>{' '}
                      <span className="font-bold text-emerald-400">Yes (Pointer / Instruction)</span>
                    </div>
                  </div>

                  <div className="space-y-1.5 p-2 bg-black/60 rounded border border-zinc-800 text-[11px] font-mono">
                    <div>
                      <span className="text-gray-500">Current String:</span>{' '}
                      <span className="text-rose-300">"{selectedFinding.current_val}"</span>
                    </div>
                    <div>
                      <span className="text-gray-500">Target String:</span>{' '}
                      <span className="text-emerald-300">"{selectedFinding.expected_val}"</span>
                    </div>
                    <div>
                      <span className="text-gray-500">Virtual VMA:</span>{' '}
                      <span className="text-cyan-300">0x{selectedFinding.vma.toString(16).padStart(8, '0')}</span>
                    </div>
                    <div>
                      <span className="text-gray-500">File Offset:</span>{' '}
                      <span className="text-cyan-300">0x{selectedFinding.file_offset.toString(16).padStart(8, '0')}</span>
                    </div>
                  </div>
                </div>
              ) : (
                <div className="text-gray-500 text-center py-8">Select any audit finding to inspect technical details.</div>
              )}
            </div>
          </div>
        </div>
      )}

      {/* ==================================================================== */}
      {/* TAB 2: TRANSLATION & POINTER EXPLORER */}
      {/* ==================================================================== */}
      {/* ==================================================================== */}
      {/* TAB 3: 3-TIER OFFLINE SEMANTIC HYBRID AUDITOR & GLOSSARY */}
      {/* ==================================================================== */}
      {subTab === 'semantic' && (
        <div className="space-y-4">
          {/* Header & Offline Engine Status Badges */}
          <div className="p-3 bg-zinc-900/60 rounded border border-zinc-800 space-y-2">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <div className="flex items-center space-x-2">
                <Sparkles className="w-4 h-4 text-purple-400" />
                <span className="text-xs font-bold text-purple-300 uppercase tracking-wider">
                  3-Tier Offline Semantic Hybrid Auditor
                </span>
                <span className="px-2 py-0.5 text-[10px] font-bold rounded bg-emerald-950 text-emerald-400 border border-emerald-800">
                  100% OFFLINE ENGINE
                </span>
              </div>

              <div className="flex flex-wrap items-center gap-1.5 text-[10px] font-mono">
                <span className="px-2 py-0.5 rounded bg-cyan-950/80 border border-cyan-800 text-cyan-300">
                  Tier 1: Auto-Learned Glossary
                </span>
                <span className="px-2 py-0.5 rounded bg-blue-950/80 border border-blue-800 text-blue-300">
                  Tier 2: Vector Consensus
                </span>
                <span
                  className={`px-2 py-0.5 rounded border transition-all ${
                    isLoadingSemantic && useOllama
                      ? 'bg-purple-950/80 border-purple-500 text-purple-300 animate-pulse'
                      : semanticReport?.tier3_ollama?.available
                      ? 'bg-emerald-950/80 border-emerald-700 text-emerald-300'
                      : aiStatus?.ollama?.available
                      ? 'bg-cyan-950/80 border-cyan-700 text-cyan-300'
                      : 'bg-zinc-900 border-zinc-700 text-gray-500'
                  }`}
                >
                  Tier 3: Local AI 127.0.0.1 (
                  {isLoadingSemantic && useOllama
                    ? 'Active — Scanning...'
                    : semanticReport?.tier3_ollama?.available
                    ? `Active — ${semanticReport.tier3_ollama.active_model || 'Model Loaded'}`
                    : aiStatus?.ollama?.available
                    ? `Online — Ready [${aiStatus.ollama.loaded_models?.[0]?.name || aiStatus.ollama.loaded_models?.[0] || ollamaModel || 'Ready'}]`
                    : 'Offline / Inactive'}
                  )
                </span>
              </div>
            </div>

            {/* Controls Bar */}
            <div className="flex flex-wrap items-center justify-between gap-3 pt-2 border-t border-zinc-800/80">
              <div className="flex items-center space-x-3">
                <span className="text-gray-400 font-bold text-xs">Target Locale:</span>
                <select
                  value={auditLocale}
                  onChange={(e) => {
                    setAuditLocale(e.target.value);
                    fetchSemanticData(null, e.target.value);
                  }}
                  className="bg-black/60 border border-zinc-700 rounded px-2.5 py-1 text-gray-200 font-mono text-xs focus:outline-none focus:border-purple-500"
                >
                  {effectiveLanguages.map((l) => (
                    <option key={l.locale} value={l.locale}>
                      {l.locale} ({l.phrase_count} phrases)
                    </option>
                  ))}
                </select>

                <label className="flex items-center space-x-1.5 text-xs text-gray-300 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={useOllama && aiEnabled}
                    onChange={(e) => {
                      const next = e.target.checked;
                      setUseOllama(next);
                      if (onToggleAi) onToggleAi(next, ollamaModel);
                    }}
                    className="rounded bg-black/60 border-zinc-700 text-purple-500 focus:ring-purple-500"
                  />
                  <span>Query Local AI (127.0.0.1:11434 — default OFF)</span>
                </label>
              </div>

              <button
                onClick={() => fetchSemanticData()}
                disabled={isLoadingSemantic}
                className="flex items-center space-x-1.5 px-3 py-1.5 font-bold rounded bg-gradient-to-r from-purple-600 to-indigo-600 hover:from-purple-500 hover:to-indigo-500 text-white shadow-[0_0_12px_rgba(168,85,247,0.3)] transition-all text-xs"
              >
                <RefreshCw className={`w-3.5 h-3.5 ${isLoadingSemantic ? 'animate-spin' : ''}`} />
                <span>{isLoadingSemantic ? 'ANALYZING SEMANTICS...' : '🧠 RUN DEEP SEMANTIC AUDIT'}</span>
              </button>
            </div>

            {/* Deep AI Semantic Scan Progress Bar */}
            {(isLoadingSemantic || (semanticProgress && semanticProgress.active)) && (
              <div className="pt-2 border-t border-purple-900/40 space-y-1.5">
                <div className="flex items-center justify-between text-[11px] font-mono">
                  <span className="text-purple-300 font-bold flex items-center gap-1.5">
                    <span className="inline-block w-2 h-2 rounded-full bg-purple-400 animate-ping" />
                    {semanticProgress?.step || 'SEMANTIC_AUDIT'}: {semanticProgress?.detail || 'Scanning translations...'}
                  </span>
                  <div className="flex items-center space-x-2 text-gray-400">
                    {semanticProgress?.total > 0 && (
                      <span>
                        [{semanticProgress.current || 0} / {semanticProgress.total}]
                      </span>
                    )}
                    <span className="text-purple-300 font-bold">{semanticProgress?.percent || 0}%</span>
                    {semanticProgress?.eta_seconds !== null && semanticProgress?.eta_seconds !== undefined && semanticProgress.eta_seconds > 0 && (
                      <span className="text-xs text-amber-400 font-mono">
                        ~{Math.ceil(semanticProgress.eta_seconds)}s remaining
                      </span>
                    )}
                  </div>
                </div>
                <div className="w-full bg-black/60 rounded-full h-2 overflow-hidden border border-purple-900/60 p-[1px]">
                  <div
                    className="h-full rounded-full bg-gradient-to-r from-purple-600 via-indigo-500 to-cyan-400 transition-all duration-300 shadow-[0_0_8px_rgba(168,85,247,0.5)]"
                    style={{ width: `${Math.min(100, Math.max(2, semanticProgress?.percent || 0))}%` }}
                  />
                </div>
              </div>
            )}
          </div>

          {/* Warning Banner when useOllama is checked but no models installed */}
          {useOllama && (semanticReport?.tier3_ollama?.status_message || (aiStatus?.ollama?.available && (!aiStatus.ollama.models || aiStatus.ollama.models.length === 0))) && (
            <div className="p-3 bg-amber-950/60 border border-amber-600/80 rounded flex flex-wrap items-center justify-between gap-2 text-amber-200">
              <div className="flex items-center space-x-2">
                <AlertTriangle className="w-5 h-5 text-amber-400 shrink-0" />
                <span className="text-xs font-mono font-bold">
                  {semanticReport?.tier3_ollama?.status_message ||
                    "Local AI runtime is ready, but no models are installed yet. Click 'Pull Selected Model' below to download."}
                </span>
              </div>
              <button
                onClick={() => controlOllama('pull')}
                disabled={isOperatingOllama}
                className="px-3 py-1 bg-amber-500 hover:bg-amber-400 text-black font-bold text-xs rounded transition-all shrink-0 flex items-center space-x-1"
              >
                <ArrowDownCircle className="w-3.5 h-3.5" />
                <span>Pull Selected Model</span>
              </button>
            </div>
          )}

          {/* ================================================================ */}
          {/* HOST HARDWARE SELF-CHECK & ADAPTIVE MODEL SELECTOR PANEL */}
          {/* ================================================================ */}
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
                  onClick={() => fetchAiStatus()}
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
                      <span className="text-purple-400 font-mono text-[9px] truncate max-w-[110px]" title={aiStatus.ollama.loaded_models.map(m => m.name || m).join(', ')}>
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
                {(() => {
                  const activeModelId = ollamaModel || aiStatus?.hardware?.default_selected_model || 'qwen2.5:0.5b';
                  const selectedModelMeta = effectiveModelCatalog.find((m) => m.id === activeModelId) || effectiveModelCatalog[0] || {
                    id: activeModelId,
                    name: activeModelId,
                    min_ram_mb: 800,
                    compatibility: 'RECOMMENDED',
                  };

                  return (
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
                  );
                })()}

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
                    onClick={() => controlOllama('start')}
                    disabled={isOperatingOllama || aiStatus?.ollama?.available}
                    className="flex items-center space-x-1 px-2.5 py-1 text-xs font-bold rounded bg-emerald-900/60 hover:bg-emerald-800 text-emerald-200 border border-emerald-700 disabled:opacity-40 disabled:cursor-not-allowed transition-all"
                  >
                    <Play className="w-3 h-3 text-emerald-400" />
                    <span>Start Engine</span>
                  </button>

                  <button
                    onClick={() => controlOllama('unload')}
                    disabled={isOperatingOllama || !aiStatus?.ollama?.available}
                    className="flex items-center space-x-1 px-2.5 py-1 text-xs font-bold rounded bg-amber-900/60 hover:bg-amber-800 text-amber-200 border border-amber-700 disabled:opacity-40 disabled:cursor-not-allowed transition-all"
                  >
                    <Trash2 className="w-3 h-3 text-amber-400" />
                    <span>Unload RAM</span>
                  </button>

                  <button
                    onClick={() => controlOllama('stop')}
                    disabled={isOperatingOllama || !aiStatus?.ollama?.available}
                    className="flex items-center space-x-1 px-2.5 py-1 text-xs font-bold rounded bg-red-950/60 hover:bg-red-900 text-red-200 border border-red-800 disabled:opacity-40 disabled:cursor-not-allowed transition-all"
                  >
                    <Square className="w-3 h-3 text-red-400" />
                    <span>Stop Engine</span>
                  </button>

                  <button
                    onClick={() => controlOllama('pull')}
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
                          onClick={() => controlOllama('cancel_pull')}
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

          {/* Metrics Summary Cards */}
          {semanticReport?.summary && (
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
              <div className="p-2.5 bg-black/40 border border-zinc-800 rounded">
                <div className="text-[10px] text-gray-500 font-bold uppercase">TOTAL ANALYZED</div>
                <div className="text-sm font-bold text-gray-200 mt-0.5">
                  {semanticReport.summary.total_phrases} Phrases
                </div>
                <div className="text-[10px] text-gray-500">Cross-referenced against en-GB</div>
              </div>

              <div className="p-2.5 bg-black/40 border border-zinc-800 rounded">
                <div className="text-[10px] text-gray-500 font-bold uppercase">LEARNED GLOSSARY</div>
                <div className="text-sm font-bold text-cyan-300 mt-0.5">
                  {semanticReport.summary.glossary_terms_count} Domain Terms
                </div>
                <div className="text-[10px] text-gray-500">Mined from binary co-occurrence</div>
              </div>

              <div className="p-2.5 bg-black/40 border border-zinc-800 rounded">
                <div className="text-[10px] text-gray-500 font-bold uppercase">AVG ALIGNMENT SCORE</div>
                <div className="text-sm font-bold text-emerald-300 mt-0.5">
                  {(semanticReport.summary.average_alignment * 100).toFixed(1)}%
                </div>
                <div className="text-[10px] text-gray-500">Consensus & length consistency</div>
              </div>

              <div className="p-2.5 bg-black/40 border border-zinc-800 rounded">
                <div className="text-[10px] text-gray-500 font-bold uppercase">FLAGGED ANOMALIES</div>
                <div
                  className={`text-sm font-bold mt-0.5 ${
                    semanticReport.summary.flagged_count > 0 ? 'text-amber-400' : 'text-emerald-400'
                  }`}
                >
                  {semanticReport.summary.flagged_count} Outliers
                </div>
                <div className="text-[10px] text-gray-500">Low alignment or contradictions</div>
              </div>
            </div>
          )}

          {/* Prominent Local Ollama AI Scan Results Panel */}
          {semanticReport?.tier3_ollama?.reviews?.length > 0 && (
            <div className="p-3.5 bg-[#121218] border border-purple-800/70 rounded-lg space-y-3 shadow-[0_0_20px_rgba(168,85,247,0.15)]">
              <div className="flex flex-wrap items-center justify-between gap-2 border-b border-zinc-800/80 pb-2.5">
                <div className="flex items-center space-x-2">
                  <Sparkles className="w-4 h-4 text-purple-400" />
                  <span className="text-xs font-bold text-purple-200 uppercase tracking-wider font-mono">
                    🤖 LOCAL AI SCAN RESULTS
                  </span>
                  <span className="px-2 py-0.5 text-[10px] font-bold rounded bg-purple-950 text-purple-300 border border-purple-800 font-mono">
                    TIER 3 NEURAL AUDIT
                  </span>
                </div>
                <button
                  onClick={() => setShowAiModal(true)}
                  className="flex items-center space-x-1.5 px-3 py-1 text-xs font-bold rounded bg-purple-900/60 hover:bg-purple-800 text-purple-200 border border-purple-600 transition-all shadow-sm"
                  title="Open AI Scan Results in full-size window"
                >
                  <Maximize2 className="w-3.5 h-3.5" />
                  <span>🗖 Open AI Results Window</span>
                </button>
              </div>
              {renderAiResultsContent(false)}
            </div>
          )}

          {/* Tables Grid: 1. Learned Glossary, 2. Flagged Anomalies */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
            {/* Table 1: Self-Learned Domain Glossary */}
            <div className="bg-[#121218] border border-zinc-800 rounded overflow-hidden">
              <div className="p-2.5 bg-zinc-900/60 border-b border-zinc-800 flex items-center justify-between">
                <span className="text-xs font-bold text-cyan-400 flex items-center space-x-1.5">
                  <Box className="w-3.5 h-3.5" />
                  <span>Self-Learned Domain Glossary ({semanticReport?.tier1_glossary?.length || 0})</span>
                </span>
                <span className="text-[10px] text-gray-500 font-mono">
                  Dice Similarity &gt;= 0.45 • Support &gt;= 2
                </span>
              </div>
              <div className="overflow-x-auto max-h-[360px] overflow-y-auto">
                <table className="w-full text-left border-collapse text-[11px] font-mono">
                  <thead className="sticky top-0 bg-zinc-900 border-b border-zinc-800 text-gray-400 text-[10px] uppercase">
                    <tr>
                      <th className="p-2">English Concept</th>
                      <th className="p-2">Target Translation ({auditLocale})</th>
                      <th className="p-2 text-center">Support</th>
                      <th className="p-2 text-center">Confidence</th>
                      <th className="p-2 text-center">Dice</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-zinc-800/60 text-gray-300">
                    {semanticReport?.tier1_glossary?.map((g, idx) => (
                      <tr key={idx} className="hover:bg-zinc-800/40">
                        <td className="p-2">
                          <span className="font-bold text-gray-200">{g.en_term}</span>{' '}
                          <span className="text-gray-500 font-sans text-[10px]">({g.en_word})</span>
                        </td>
                        <td className="p-2">
                          <span className="font-bold text-cyan-300">{g.target_term}</span>{' '}
                          <span className="text-gray-400 font-sans text-[10px]">({g.target_word})</span>
                        </td>
                        <td className="p-2 text-center text-gray-400">{g.support}</td>
                        <td className="p-2 text-center text-emerald-400 font-bold">
                          {(g.confidence * 100).toFixed(0)}%
                        </td>
                        <td className="p-2 text-center text-blue-400">{g.dice.toFixed(2)}</td>
                      </tr>
                    ))}
                    {(!semanticReport || !semanticReport.tier1_glossary?.length) && (
                      <tr>
                        <td colSpan={5} className="p-4 text-center text-gray-500">
                          {isLoadingSemantic
                            ? 'Extracting domain glossary from binary...'
                            : 'No glossary loaded. Click "Run Deep Semantic Audit" above.'}
                        </td>
                      </tr>
                    )}
                  </tbody>
                </table>
              </div>
            </div>

            {/* Table 2: Flagged Anomalies & Substitutions */}
            <div className="bg-[#121218] border border-zinc-800 rounded overflow-hidden">
              <div className="p-2.5 bg-zinc-900/60 border-b border-zinc-800 flex items-center justify-between">
                <span className="text-xs font-bold text-amber-400 flex items-center space-x-1.5">
                  <AlertTriangle className="w-3.5 h-3.5" />
                  <span>Flagged Anomalies & Low Alignment ({flaggedAllCount})</span>
                </span>
                <span className="text-[10px] text-gray-500 font-mono">
                  Score &lt; 0.65 or Glossary Contradiction
                </span>
              </div>

              {/* Filter bar for Flagged Anomalies */}
              <div className="px-2.5 py-1.5 bg-black/40 border-b border-zinc-800/80 flex flex-wrap items-center gap-1.5 text-[10px]">
                <button
                  onClick={() => setAnomalyFilter('ALL')}
                  className={`px-2 py-0.5 rounded font-bold transition-all ${
                    anomalyFilter === 'ALL'
                      ? 'bg-zinc-700 text-white'
                      : 'bg-zinc-900 hover:bg-zinc-800 text-zinc-400'
                  }`}
                >
                  ALL ({flaggedAllCount})
                </button>
                <button
                  onClick={() => setAnomalyFilter('OLLAMA_SCANNED')}
                  className={`px-2 py-0.5 rounded font-bold transition-all ${
                    anomalyFilter === 'OLLAMA_SCANNED'
                      ? 'bg-purple-900/80 text-purple-200 border border-purple-600'
                      : 'bg-zinc-900 hover:bg-zinc-800 text-zinc-400'
                  }`}
                >
                  🤖 AI SCANNED ({flaggedScannedCount})
                </button>
                <button
                  onClick={() => setAnomalyFilter('AI_DEFECTS')}
                  className={`px-2 py-0.5 rounded font-bold transition-all ${
                    anomalyFilter === 'AI_DEFECTS'
                      ? 'bg-rose-900/80 text-rose-200 border border-rose-600'
                      : 'bg-zinc-900 hover:bg-zinc-800 text-zinc-400'
                  }`}
                >
                  🚨 AI CONFIRMED DEFECTS ({flaggedDefectsCount})
                </button>
                <button
                  onClick={() => setAnomalyFilter('GLOSSARY')}
                  className={`px-2 py-0.5 rounded font-bold transition-all ${
                    anomalyFilter === 'GLOSSARY'
                      ? 'bg-emerald-900/80 text-emerald-200 border border-emerald-600'
                      : 'bg-zinc-900 hover:bg-zinc-800 text-zinc-400'
                  }`}
                >
                  📚 WITH SUGGESTED FIX ({flaggedSuggestedCount})
                </button>
              </div>

              <div className="overflow-x-auto max-h-[360px] overflow-y-auto">
                <table className="w-full text-left border-collapse text-[11px]">
                  <thead className="sticky top-0 bg-zinc-900 border-b border-zinc-800 text-gray-400 text-[10px] uppercase font-mono">
                    <tr>
                      <th className="p-2 w-16 text-center">Score</th>
                      <th className="p-2">Key & Values</th>
                      <th className="p-2">Anomaly Diagnostics</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-zinc-800/60 text-gray-300">
                    {filteredFlaggedPhrases.map((fl, idx) => (
                      <tr key={idx} className="hover:bg-zinc-800/40">
                        <td className="p-2 text-center align-top">
                          <span
                            className={`px-1.5 py-0.5 rounded font-mono font-bold text-[10px] ${
                              fl.alignment_score < 0.45
                                ? 'bg-rose-950 text-rose-300 border border-rose-800'
                                : 'bg-amber-950 text-amber-300 border border-amber-800'
                            }`}
                          >
                            {(fl.alignment_score * 100).toFixed(0)}%
                          </span>
                        </td>
                        <td className="p-2 align-top">
                          <div className="flex items-center space-x-1.5">
                            <span className="font-mono font-bold text-gray-200">{fl.key}</span>
                            {fl.ollama_review && (
                              fl.ollama_review.is_correct ? (
                                <span className="px-1 py-0.2 text-[9px] font-bold rounded bg-emerald-950 text-emerald-400 border border-emerald-800">
                                  AI OK
                                </span>
                              ) : (
                                <span className="px-1 py-0.2 text-[9px] font-bold rounded bg-rose-950 text-rose-400 border border-rose-800">
                                  AI DEFECT
                                </span>
                              )
                            )}
                          </div>
                          <div className="text-gray-400 text-[10px] font-sans truncate max-w-[220px]" title={fl.en_val}>
                            EN: {fl.en_val}
                          </div>
                          <div className="text-amber-300 text-[10px] font-sans truncate max-w-[220px]" title={fl.target_val}>
                            {auditLocale}: {fl.target_val}
                          </div>
                        </td>
                        <td className="p-2 align-top">
                          <div className="text-[10px] text-gray-300 font-sans">{fl.reason}</div>
                          {fl.suggested_val && (
                            <div className="mt-1 text-[10px] text-emerald-400 font-mono flex items-center justify-between">
                              <span className="truncate max-w-[160px]" title={fl.suggested_val}>
                                Fix: {fl.suggested_val}
                              </span>
                            </div>
                          )}
                        </td>
                      </tr>
                    ))}
                    {(!filteredFlaggedPhrases || !filteredFlaggedPhrases.length) && (
                      <tr>
                        <td colSpan={3} className="p-4 text-center text-gray-500">
                          {isLoadingSemantic
                            ? 'Scoring cross-locale consensus...'
                            : 'No semantic anomalies match the current filter.'}
                        </td>
                      </tr>
                    )}
                  </tbody>
                </table>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* ==================================================================== */}
      {/* TAB 2: MULTI-LOCALE EXPLORER */}
      {/* ==================================================================== */}
      {subTab === 'explorer' && (
        <div className="space-y-3">
          {/* Controls Bar */}
          <div className="flex flex-wrap items-center justify-between gap-3 p-2.5 bg-[#121218] border border-zinc-800 rounded">
            <div className="flex items-center space-x-3">
              <span className="text-gray-400 font-bold">Select Locale:</span>
              <select
                value={selectedLocale}
                onChange={(e) => setSelectedLocale(e.target.value)}
                className="bg-black/60 border border-zinc-700 rounded px-2.5 py-1 text-gray-200 font-mono text-xs focus:outline-none focus:border-cyan-500"
              >
                {languages.map((l) => (
                  <option key={l.locale} value={l.locale}>
                    {l.locale} ({l.phrase_count} phrases)
                  </option>
                ))}
              </select>

              <span className="text-gray-500 text-[11px] font-mono">
                {phrases.length} phrases loaded
              </span>
            </div>

            <div className="flex items-center space-x-2">
              <Search className="w-3.5 h-3.5 text-gray-400" />
              <input
                type="text"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="bg-black/60 border border-zinc-700 rounded px-2.5 py-1 text-gray-200 text-xs w-64 focus:outline-none focus:border-cyan-500"
                placeholder="Search key, translation, or VMA..."
              />
            </div>
          </div>

          {/* Phrases Table */}
          <div className="overflow-x-auto rounded border border-zinc-800 bg-[#121218]">
            <table className="w-full text-left border-collapse">
              <thead>
                <tr className="border-b border-zinc-800 bg-zinc-900/60 text-gray-400 font-bold uppercase text-[10px]">
                  <th className="p-2 w-12 text-center">#</th>
                  <th className="p-2 w-64">Key Identifier</th>
                  <th className="p-2 w-24">Key VMA</th>
                  <th className="p-2">Translation ({selectedLocale})</th>
                  <th className="p-2 w-24">Val VMA</th>
                  <th className="p-2 w-24">File Offset</th>
                  <th className="p-2">English Reference (en-GB)</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-zinc-800/60 font-mono text-[11px]">
                {phrases.slice(0, 100).map((p) => (
                  <tr key={p.key} className="hover:bg-zinc-800/40 text-gray-300">
                    <td className="p-2 text-center text-gray-500">{p.index}</td>
                    <td className="p-2 font-bold text-gray-200 truncate max-w-[240px]" title={p.key}>
                      {p.key}
                    </td>
                    <td className="p-2 text-gray-400">{p.key_vma}</td>
                    <td className="p-2 font-sans text-cyan-300 truncate max-w-[300px]" title={p.val}>
                      {p.val}
                    </td>
                    <td className="p-2 text-gray-400">{p.val_vma}</td>
                    <td className="p-2 text-gray-400">{p.slot_file_off}</td>
                    <td className="p-2 font-sans text-gray-400 truncate max-w-[300px]" title={p.en_ref}>
                      {p.en_ref}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            {phrases.length > 100 && (
              <div className="p-2 text-center text-gray-500 text-[10px] border-t border-zinc-800">
                Showing first 100 of {phrases.length} phrases. Use live search above to filter.
              </div>
            )}
          </div>
        </div>
      )}

      {/* Pop-out Local Ollama AI Scan Results Window / Modal */}
      {showAiModal && semanticReport?.tier3_ollama?.reviews?.length > 0 && (
        <div className="fixed inset-0 z-50 bg-black/80 backdrop-blur-sm flex items-center justify-center p-3 sm:p-6">
          <div className="bg-[#121218] border border-cyan-800/80 rounded-lg shadow-2xl flex flex-col w-full max-w-6xl max-h-[90vh] overflow-hidden">
            {/* Modal Header */}
            <div className="p-3 bg-zinc-900/90 border-b border-zinc-800 flex items-center justify-between">
              <div className="flex items-center space-x-2">
                <Sparkles className="w-4 h-4 text-cyan-400" />
                <span className="text-sm font-bold text-gray-100 uppercase tracking-wider font-mono">
                  🤖 SPECTRA — LOCAL AI SCAN RESULTS
                </span>
                <span className="px-2 py-0.5 text-[10px] font-bold rounded bg-purple-950 text-purple-300 border border-purple-800 font-mono">
                  {semanticReport?.tier3_ollama?.active_model || 'Local LLM'}
                </span>
              </div>
              <button
                onClick={() => setShowAiModal(false)}
                className="p-1 rounded hover:bg-zinc-800 text-gray-400 hover:text-gray-200 transition-all"
                title="Close Window"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            {/* Modal Body */}
            <div className="p-4 overflow-y-auto space-y-4 flex-1">
              {renderAiResultsContent(true)}
            </div>

            {/* Modal Footer */}
            <div className="p-3 bg-zinc-900/80 border-t border-zinc-800 flex items-center justify-between text-xs text-gray-400 font-mono">
              <div>
                Target Audit Locale: <span className="text-cyan-300 font-bold">{auditLocale}</span>
              </div>
              <button
                onClick={() => setShowAiModal(false)}
                className="px-4 py-1.5 rounded bg-zinc-800 hover:bg-zinc-700 text-gray-200 font-bold text-xs"
              >
                Close
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
