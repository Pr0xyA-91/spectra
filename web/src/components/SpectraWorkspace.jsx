import React, { useState, useEffect, useRef, useCallback } from 'react';
import {
  Activity,
  Cpu,
  Zap,
  Terminal,
  Play,
  Pause,
  RefreshCw,
  Search,
  Filter,
  CheckCircle2,
  AlertTriangle,
  Send,
  Layers,
  Flame,
  Gauge,
  Sliders,
  Radio,
  Eye,
  EyeOff,
  ChevronRight,
  Shield,
  Clock,
  Compass,
  Download,
  FileText,
  FileSpreadsheet,
  Database,
  Coffee,
  Sparkles,
  Wrench,
  Info,
  Check,
  X,
  SlidersHorizontal,
  Inbox,
  Droplet,
  Trash2,
  Copy,
  Box,
  Upload,
  ExternalLink,
  Key,
  LogOut,
  Github,
  Power,
  Settings,
} from 'lucide-react';

import OscilloscopeStripChart from './OscilloscopeStripChart';
import DigitalTwinSchematic from './DigitalTwinSchematic';
import DiagnosticAdvisorTab from './DiagnosticAdvisorTab';
import MemMapperTab from './MemMapperTab';
import HmiInspectorTab from './HmiInspectorTab';
import AiStatusBar from './AiStatusBar';
import ConfigModal from './ConfigModal';
import InteractiveGuideModal from './InteractiveGuideModal';
import {
  createTranslator,
  txVal,
  txBeverageName,
  txMaintenanceLabel,
} from '../i18n/translations';

// ============================================================================
// 1. THEME DEFINITION
// ============================================================================
export const THEMES = {
  cyberpunk: {
    id: 'cyberpunk',
    name: 'SPECTRA',
    subtitle: 'Hardware Telemetry & Logic Board Diagnostics',
    bg: 'bg-[#070709]',
    panelBg: 'bg-[#0E0E12]/95',
    headerBg: 'bg-[#121218]',
    border: 'border-[#FCEE09]/30',
    borderActive: 'border-[#FCEE09]',
    primary: '#FCEE09', // Hazard Yellow
    secondary: '#00F0FF', // Neon Cyan
    danger: '#FF003C', // Crimson
    success: '#00FF66',
    canvasBg: '#060609',
    gridColor: 'rgba(252, 238, 9, 0.08)',
    clipClass: 'clip-cyber',
    font: 'font-mono',
    isScanline: true,
    accentGlow: 'shadow-[0_0_15px_rgba(252,238,9,0.5)]',
    textPrimary: 'text-[#FCEE09]',
    textSecondary: 'text-[#00F0FF]',
    textMuted: 'text-zinc-400',
    surfaceClass: 'bg-[#0E0E12]/95 border border-[#FCEE09]/30 clip-cyber',
  },
};

// ============================================================================
// WORKSPACE NAVIGATION TABS (EXACT MATCH FOR SPECTRA GTK TABS + MEM MAPPER)
// ============================================================================
export default function SpectraWorkspace({
  lang = 'en',
  setLang = () => {},
  isDebugOpen = false,
  setIsDebugOpen = () => {},
  debugCounts = { errorCount: 0, warnCount: 0 },
  debugSummary = null,
  scaleMode = 'auto',
  setScaleMode = () => {},
  currentScale = 1.0,
} = {}) {
  const t = createTranslator(lang);
  const langRef = useRef(lang);
  langRef.current = lang;
  const theme = THEMES.cyberpunk;
  const WORKSPACE_TABS = [
    { id: 'overview', label: t('tabOverview') },
    { id: 'sensors', label: t('tabSensors') },
    { id: 'beverages', label: t('tabBeverages') },
    { id: 'maintenance', label: t('tabMaintenance') },
    { id: 'alerts', label: t('tabAlerts') },
    { id: 'system', label: t('tabSystem') },
    { id: 'bus_log', label: t('tabBusLog') },
    { id: 'mem_mapper', label: t('tabMemMapper') },
    { id: 'hmi_tools', label: t('tabHmiTools') },
  ];
  const [liveBuild, setLiveBuild] = useState(debugSummary?.build || '');
  const [bootReady, setBootReady] = useState(false);

  useEffect(() => {
    const timer = setTimeout(() => setBootReady(true), 150);
    return () => clearTimeout(timer);
  }, []);

  useEffect(() => {
    if (debugSummary?.build) {
      setLiveBuild(debugSummary.build);
    }
    let active = true;
    const applyOnboardingPrefs = (prefs) => {
      if (!active) return;
      let lsSeen = false;
      try {
        lsSeen = localStorage.getItem('spectra_onboarding_seen') === '1';
      } catch {}
      const diskSeen = Boolean(prefs?.onboarding_seen);
      const seen = diskSeen || lsSeen;
      if (seen) {
        try {
          localStorage.setItem('spectra_onboarding_seen', '1');
        } catch {}
        if (!diskSeen) {
          fetch('/api/ui_prefs', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ onboarding_seen: true }),
          }).catch(() => {});
        }
        setShowGuideOnStartup(false);
        setShowGuideModal(false);
      } else {
        setShowGuideOnStartup(true);
        setStartupGuideCheckbox(false);
        setShowGuideModal(true);
      }
    };

    fetch('/api/version')
      .then((r) => (r.ok ? r.json() : null))
      .then(async (d) => {
        if (!active) return;
        if (d?.build && !debugSummary?.build) setLiveBuild(d.build);
        if (d?.ui_prefs !== undefined) {
          applyOnboardingPrefs(d.ui_prefs);
        } else {
          const pr = await fetch('/api/ui_prefs').then((x) => (x.ok ? x.json() : null)).catch(() => null);
          applyOnboardingPrefs(pr?.prefs || {});
        }
      })
      .catch(() => {
        let lsSeen = false;
        try {
          lsSeen = localStorage.getItem('spectra_onboarding_seen') === '1';
        } catch {}
        if (!lsSeen && active) {
          setShowGuideOnStartup(true);
          setStartupGuideCheckbox(false);
          setShowGuideModal(true);
        }
      });

    return () => {
      active = false;
    };
  }, [debugSummary?.build]);

  // Active Workspace Tab (Default: overview)
  const [activeTab, setActiveTab] = useState('overview');

  // Hardware Connection & Port State
  const [availablePorts, setAvailablePorts] = useState([]);
  const [selectedPort, setSelectedPort] = useState('');
  const [isConnected, setIsConnected] = useState(false);
  const [isPolling, setIsPolling] = useState(true);
  const [isInterrogating, setIsInterrogating] = useState(false);
  const [hardwareError, setHardwareError] = useState(null);
  const [connectionStatusText, setConnectionStatusText] = useState(() => createTranslator(lang)('detectingPorts'));
  const [lastTimestamp, setLastTimestamp] = useState('---');

  // Live Telemetry from Hardware API
  const [liveData, setLiveData] = useState({
    switches: [],
    sensors: [],
    telemetry: {},
    alerts: [],
  });

  // Full Stats from Interrogation API
  const [statsData, setStatsData] = useState(null);

  // Machine Data Read Progress Bar State
  const [interrogationProgress, setInterrogationProgress] = useState(0);
  const [interrogationStage, setInterrogationStage] = useState('');

  // Optical Bean Calibration State
  const [beanThreshold, setBeanThreshold] = useState(115);
  const [beanHysteresis, setBeanHysteresis] = useState(5);
  const [isSavingCalib, setIsSavingCalib] = useState(false);

  // Real-Time Bus Event Stream & Safety Log (Matching GTK TextView)
  const [busEvents, setBusEvents] = useState([]);
  const [isStreamPaused, setIsStreamPaused] = useState(false);

  // UART Command Injector
  const [txCommand, setTxCommand] = useState('HZ:');
  const [txSuccessFlash, setTxSuccessFlash] = useState(false);
  const [txResponseHistory, setTxResponseHistory] = useState([]);

  // Export Modal Dialog State
  const [showExportModal, setShowExportModal] = useState(false);
  const [joeCsvContent, setJoeCsvContent] = useState('');
  const [joeFileName, setJoeFileName] = useState('');
  const [isDumping, setIsDumping] = useState(false);
  const [isHardwareBusy, setIsHardwareBusy] = useState(false);
  const [exportStatus, setExportStatus] = useState({ loading: false, msg: '', error: false });
  const [capturedBundle, setCapturedBundle] = useState(null);
  const [capturedId, setCapturedId] = useState('');
  const [capturedFilename, setCapturedFilename] = useState('');
  const [browserDownloadAvailable, setBrowserDownloadAvailable] = useState(null);
  const [githubAuth, setGithubAuth] = useState({ authenticated: false, login: null, method: null, device_flow_available: false });
  const [deviceFlow, setDeviceFlow] = useState(null);
  const [showPatInput, setShowPatInput] = useState(false);
  const [patInput, setPatInput] = useState('');
  const [isUploading, setIsUploading] = useState(false);
  const [uploadResult, setUploadResult] = useState(null);
  const [copiedCode, setCopiedCode] = useState(false);

  // Beverage Filter
  const [bevSearch, setBevSearch] = useState('');

  // Global Local AI State (Default: strictly OFF to preserve host CPU/RAM)
  const [aiEnabled, setAiEnabled] = useState(false);
  const [aiModel, setAiModel] = useState(() => {
    try {
      return localStorage.getItem('spectra_ollama_model') || '';
    } catch {
      return '';
    }
  });
  const [aiTask, setAiTask] = useState({ active: false });
  const [aiDownload, setAiDownload] = useState({ active: false });
  const [aiSystem, setAiSystem] = useState(null);
  const [aiAutoUnload, setAiAutoUnload] = useState(true);
  const [aiBusyCount, setAiBusyCount] = useState(0);
  const [showNoModelPromptModal, setShowNoModelPromptModal] = useState(false);
  const [noModelPromptChoice, setNoModelPromptChoice] = useState('');
  const [autoEnableAiAfterPull, setAutoEnableAiAfterPull] = useState(false);
  const [showConfigModal, setShowConfigModal] = useState(false);
  const [configInitialSection, setConfigInitialSection] = useState('ai');
  const [showGuideOnStartup, setShowGuideOnStartup] = useState(false);
  const [showGuideModal, setShowGuideModal] = useState(false);
  const [startupGuideCheckbox, setStartupGuideCheckbox] = useState(false);

  // Self-Updater State
  const [updateInfo, setUpdateInfo] = useState(null);
  const [updateProgress, setUpdateProgress] = useState({ status: 'idle', percent: 0, in_progress: false, restart_required: false, message: '', error: '' });
  const [isCheckingUpdates, setIsCheckingUpdates] = useState(false);
  const [isReconnectingAfterUpdate, setIsReconnectingAfterUpdate] = useState(false);

  const persistUiOnboardingSeen = useCallback((seenVal) => {
    const isSeen = Boolean(seenVal);
    try {
      if (isSeen) {
        localStorage.setItem('spectra_onboarding_seen', '1');
      } else {
        localStorage.removeItem('spectra_onboarding_seen');
      }
    } catch {}
    fetch('/api/ui_prefs', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ onboarding_seen: isSeen }),
    }).catch(() => {});
  }, []);

  const handleSetGuideOnStartup = useCallback((shouldShow) => {
    const val = Boolean(shouldShow);
    setShowGuideOnStartup(val);
    setStartupGuideCheckbox(val);
    persistUiOnboardingSeen(!val);
  }, [persistUiOnboardingSeen]);

  const handleCloseGuide = useCallback(() => {
    setShowGuideModal(false);
    const keepForNextStartup = Boolean(startupGuideCheckbox);
    setShowGuideOnStartup(keepForNextStartup);
    persistUiOnboardingSeen(!keepForNextStartup);
  }, [startupGuideCheckbox, persistUiOnboardingSeen]);

  const handleLaunchGuideFromConfig = useCallback(() => {
    setStartupGuideCheckbox(showGuideOnStartup);
    setShowGuideModal(true);
  }, [showGuideOnStartup]);

  const [useAiJoeMatch, setUseAiJoeMatch] = useState(false);
  const [aiServiceSummary, setAiServiceSummary] = useState(null);
  const [isCalibratingOffsets, setIsCalibratingOffsets] = useState(false);
  const [offsetCalibration, setOffsetCalibration] = useState(null);
  const [offsetAppliedLocally, setOffsetAppliedLocally] = useState(false);

  const checkForUpdates = useCallback(async (force = false) => {
    setIsCheckingUpdates(true);
    try {
      const res = await fetch(`/api/update/check?force=${force ? '1' : '0'}`);
      if (res.ok) {
        const data = await res.json();
        setUpdateInfo(data);
        return data;
      }
    } catch {}
    finally {
      setIsCheckingUpdates(false);
    }
    return null;
  }, []);

  // Silent non-blocking update check shortly after startup
  useEffect(() => {
    const timer = setTimeout(() => {
      checkForUpdates(false);
    }, 1500);
    return () => clearTimeout(timer);
  }, [checkForUpdates]);

  const pollServerAfterRestart = useCallback(() => {
    setIsReconnectingAfterUpdate(true);
    let attempts = 0;
    const pollTimer = setInterval(async () => {
      attempts += 1;
      try {
        const res = await fetch(`/api/version?ts=${Date.now()}`);
        if (res.ok) {
          clearInterval(pollTimer);
          window.location.reload();
        }
      } catch {}
      if (attempts >= 35) {
        clearInterval(pollTimer);
        setIsReconnectingAfterUpdate(false);
      }
    }, 800);
  }, []);

  const startSelfUpdate = useCallback(async () => {
    try {
      const res = await fetch('/api/update/apply', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({}),
      });
      const data = await res.json();
      if (data?.state) {
        setUpdateProgress(data.state);
      }
      if (!data?.ok) return;

      const statusTimer = setInterval(async () => {
        try {
          const stRes = await fetch('/api/update/status');
          if (!stRes.ok) throw new Error('status unavailable');
          const st = await stRes.json();
          setUpdateProgress(st);
          if (st.restart_required || st.status === 'restarting') {
            clearInterval(statusTimer);
            pollServerAfterRestart();
          } else if (!st.in_progress && ['up_to_date', 'error', 'cancelled'].includes(st.status)) {
            clearInterval(statusTimer);
          }
        } catch {
          clearInterval(statusTimer);
          pollServerAfterRestart();
        }
      }, 450);
    } catch {}
  }, [pollServerAfterRestart]);

  const cancelSelfUpdate = useCallback(async () => {
    try {
      const res = await fetch('/api/update/cancel', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({}),
      });
      if (res.ok) {
        const data = await res.json();
        if (data?.state) setUpdateProgress(data.state);
      }
    } catch {}
  }, []);

  const fetchAiGlobalStatus = useCallback(async () => {
    try {
      const res = await fetch('/api/ai/status');
      if (!res.ok) return;
      const data = await res.json();
      if (data && data.success) {
        setAiEnabled(Boolean(data.ai_enabled));
        if (data.preferred_model && !aiModel) {
          setAiModel(data.preferred_model);
        }
        if (typeof data.auto_unload === 'boolean') {
          setAiAutoUnload(data.auto_unload);
        }
        setAiTask(data.task || { active: false });
        setAiDownload(data.download || { active: false });
        if (data.system) {
          setAiSystem(data.system);
        }
      }
    } catch {}
  }, [aiModel]);

  const handleSaveAiConfig = useCallback(async ({ model, auto_unload }) => {
    if (model !== undefined) {
      setAiModel(model);
      try {
        localStorage.setItem('spectra_ollama_model', model || '');
      } catch {}
    }
    if (auto_unload !== undefined) {
      setAiAutoUnload(Boolean(auto_unload));
    }
    try {
      const res = await fetch('/api/ai/config', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ model, auto_unload }),
      });
      if (res.ok) {
        const data = await res.json();
        if (data.preferred_model) setAiModel(data.preferred_model);
        if (typeof data.auto_unload === 'boolean') setAiAutoUnload(data.auto_unload);
        if (data.system) setAiSystem(data.system);
      }
    } catch {}
  }, []);

  useEffect(() => {
    fetchAiGlobalStatus();
  }, [fetchAiGlobalStatus]);

  useEffect(() => {
    if (!aiTask?.active && !aiDownload?.active && aiBusyCount === 0) return;
    const iv = setInterval(() => {
      fetchAiGlobalStatus();
    }, 650);
    return () => clearInterval(iv);
  }, [aiTask?.active, aiDownload?.active, aiBusyCount, fetchAiGlobalStatus]);

  const handleToggleAi = useCallback(async (nextEnabled, modelOverride = null) => {
    const targetEnabled = Boolean(nextEnabled);
    if (!targetEnabled) {
      setAiEnabled(false);
      setUseAiJoeMatch(false);
    } else {
      let currentSystem = aiSystem;
      if (!currentSystem) {
        try {
          const stRes = await fetch('/api/ai/status');
          if (stRes.ok) {
            const stData = await stRes.json();
            if (stData?.system) {
              currentSystem = stData.system;
              setAiSystem(stData.system);
            }
          }
        } catch {}
      }
      const installedNow = Array.isArray(currentSystem?.ollama?.models)
        ? currentSystem.ollama.models
        : [];
      if (installedNow.length === 0) {
        setAiEnabled(false);
        setNoModelPromptChoice(
          modelOverride || currentSystem?.hardware?.recommended_model || 'qwen2.5:0.5b'
        );
        setShowNoModelPromptModal(true);
        return false;
      }
    }

    try {
      const res = await fetch('/api/ai/toggle', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          enabled: targetEnabled,
          model: modelOverride || aiModel || undefined,
        }),
      });
      if (res.ok) {
        const data = await res.json();
        if (targetEnabled && (data?.requires_model_install || !data?.success)) {
          setAiEnabled(false);
          if (data?.status?.system) setAiSystem(data.status.system);
          setNoModelPromptChoice(
            modelOverride || data?.status?.system?.hardware?.recommended_model || 'qwen2.5:0.5b'
          );
          setShowNoModelPromptModal(true);
          return false;
        }
        const finalEnabled = Boolean(data?.status?.ai_enabled ?? data?.ai_enabled ?? targetEnabled);
        setAiEnabled(finalEnabled);
        if (data?.preferred_model) setAiModel(data.preferred_model);
        if (data?.status) {
          setAiTask(data.status.task || { active: false });
          setAiDownload(data.status.download || { active: false });
          if (data.status.system) setAiSystem(data.status.system);
        }
        return finalEnabled;
      }
    } catch {}
    if (targetEnabled) setAiEnabled(false);
    return false;
  }, [aiModel, aiSystem]);

  const handleStartPullFromNoModelPrompt = useCallback(async (chosenModel) => {
    const modelTag = (chosenModel || aiSystem?.hardware?.recommended_model || 'qwen2.5:0.5b').trim();
    setShowNoModelPromptModal(false);
    setAutoEnableAiAfterPull(true);
    setConfigInitialSection('ai');
    setShowConfigModal(true);
    await handleSaveAiConfig({ model: modelTag, auto_unload: aiAutoUnload });
    try {
      await fetch('/api/hmi/ai/control', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ action: 'pull_async', model: modelTag }),
      });
      fetchAiGlobalStatus();
    } catch {}
  }, [aiSystem, aiAutoUnload, handleSaveAiConfig, fetchAiGlobalStatus]);

  useEffect(() => {
    if (!autoEnableAiAfterPull) return;
    if (!aiDownload?.active && aiDownload?.status === 'COMPLETED') {
      setAutoEnableAiAfterPull(false);
      (async () => {
        await fetchAiGlobalStatus();
        await handleToggleAi(true, aiDownload.model || noModelPromptChoice);
      })();
    } else if (!aiDownload?.active && ['ERROR', 'CANCELLED'].includes(aiDownload?.status)) {
      setAutoEnableAiAfterPull(false);
    }
  }, [autoEnableAiAfterPull, aiDownload, noModelPromptChoice, fetchAiGlobalStatus, handleToggleAi]);

  const beginAiWork = useCallback(() => {
    setAiBusyCount((c) => c + 1);
    fetchAiGlobalStatus();
  }, [fetchAiGlobalStatus]);

  const endAiWork = useCallback(() => {
    setAiBusyCount((c) => Math.max(0, c - 1));
    fetchAiGlobalStatus();
  }, [fetchAiGlobalStatus]);

  // In-flight guard and failure debounce for non-blocking auto-poll
  const inFlightPollRef = useRef(false);
  const pollFailCountRef = useRef(0);

  // --------------------------------------------------------------------------
  // 1. Query Live Sensors (Hardware or Demo)
  // --------------------------------------------------------------------------
  const querySensors = useCallback(async (isFast = true, portOverride = null, silent = false) => {
    const port = portOverride || selectedPort;
    if (!port) return;

    if (silent && inFlightPollRef.current) {
      return;
    }
    inFlightPollRef.current = true;

    try {
      const res = await fetch(`/api/sensors?port=${encodeURIComponent(port)}&fast=${isFast ? '1' : '0'}`);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();

      if (data.error) {
        pollFailCountRef.current += 1;
        if (!silent || pollFailCountRef.current >= 3) {
          setConnectionStatusText(createTranslator(langRef.current)('connWarning', { err: data.error }));
          setHardwareError(data.error);
        }
        return;
      }

      pollFailCountRef.current = 0;
      setHardwareError(null);
      setLiveData(data);
      setIsConnected(true);
      setLastTimestamp(data.timestamp || new Date().toLocaleTimeString());
      setConnectionStatusText(createTranslator(langRef.current)('connConnected', { port }));

      // Append to live bus event stream if not paused
      if (!isStreamPaused) {
        const tb = data.telemetry || {};
        const logLine = `[${data.timestamp || new Date().toLocaleTimeString()}] TB1: ${tb.heater_coffee_c ?? '--'}°C | BU: ${tb.bu_encoder_pos ?? '--'} ticks | FLOW: ${tb.flow_rate_ml_s ?? 0} ml/s | BEANS: ${tb.beans_ok ? 'OK' : 'EMPTY'} | STATE: ${tb.machine_state_status || 'Ready'}`;
        setBusEvents((prev) => [logLine, ...prev.slice(0, 99)]);
      }

    } catch (err) {
      pollFailCountRef.current += 1;
      if (!silent || pollFailCountRef.current >= 3) {
        setConnectionStatusText(createTranslator(langRef.current)('connError', { err: err.message }));
        setHardwareError(err.message);
      }
    } finally {
      inFlightPollRef.current = false;
    }
  }, [selectedPort, isStreamPaused]);

  // --------------------------------------------------------------------------
  // 2. Initial Load: Fetch Serial Ports & Calibration
  // --------------------------------------------------------------------------
  const fetchPorts = useCallback(async () => {
    try {
      const res = await fetch('/api/ports');
      if (!res.ok) return;
      const ports = await res.json();
      setAvailablePorts(ports);
      if (ports.length > 0) {
        const hwPort =
          ports.find((p) => p.includes('ttyUSB') || p.includes('ttyACM') || p.includes('USB') || p.includes('by-id') || p.toUpperCase().startsWith('COM')) ||
          ports.find((p) => p.includes('DEMO')) ||
          ports[0];
        setSelectedPort(hwPort);
        setIsPolling(true);
        querySensors(true, hwPort);
      }
    } catch (e) {
      console.warn('API error fetching ports:', e);
    }
  }, [querySensors]);

  const fetchCalibration = useCallback(async () => {
    try {
      const res = await fetch('/api/calibration');
      if (!res.ok) return;
      const calib = await res.json();
      if (calib.threshold) setBeanThreshold(calib.threshold);
      if (calib.hysteresis) setBeanHysteresis(calib.hysteresis);
    } catch (e) {
      console.warn('API error fetching calibration:', e);
    }
  }, []);

  useEffect(() => {
    fetchPorts();
    fetchCalibration();
  }, [fetchPorts, fetchCalibration]);

  // --------------------------------------------------------------------------
  // 3. Auto-Polling Timer
  // --------------------------------------------------------------------------
  useEffect(() => {
    if (!isPolling || !selectedPort || isInterrogating || isDumping || isCalibratingOffsets || isHardwareBusy) return;
    const interval = setInterval(() => {
      querySensors(true, null, true);
    }, 1100);
    return () => clearInterval(interval);
  }, [isPolling, selectedPort, isInterrogating, isDumping, isCalibratingOffsets, isHardwareBusy, querySensors]);

  // --------------------------------------------------------------------------
  // 4. Full Interrogation Routine (Read Statistics & EEPROM with Progress)
  // --------------------------------------------------------------------------
  const runFullInterrogation = async () => {
    if (!selectedPort) return;
    setIsInterrogating(true);
    setInterrogationProgress(8);
    setInterrogationStage(t('stageProbeIdentity'));
    setConnectionStatusText(t('connInterrogating', { port: selectedPort }));

    const t1 = setTimeout(() => {
      setInterrogationProgress(28);
      setInterrogationStage(t('stageReadGateways'));
    }, 600);

    const t2 = setTimeout(() => {
      setInterrogationProgress(55);
      setInterrogationStage(t('stageSweepBeverages'));
    }, 1400);

    const t3 = setTimeout(() => {
      setInterrogationProgress(78);
      setInterrogationStage(t('stageReadMaintenance'));
    }, 2400);

    const t4 = setTimeout(() => {
      setInterrogationProgress(92);
      setInterrogationStage(t('stageEvalHealth'));
    }, 3400);

    try {
      const res = await fetch(`/api/stats?port=${encodeURIComponent(selectedPort)}`);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      if (data.error) {
        setConnectionStatusText(t('connInterrogateFailed', { err: data.error }));
        setHardwareError(data.error);
        setInterrogationStage(t('stageError', { err: data.error }));
      } else {
        setInterrogationProgress(100);
        setInterrogationStage(t('stageComplete'));
        setStatsData(data);
        setConnectionStatusText(t('connInterrogateComplete', { model: data.machine_model || 'Appliance', preps: data.total_preparations || 0 }));
      }
    } catch (err) {
      setConnectionStatusText(t('connInterrogateError', { err: err.message }));
      setHardwareError(err.message);
      setInterrogationStage(t('stageError', { err: err.message }));
    } finally {
      clearTimeout(t1);
      clearTimeout(t2);
      clearTimeout(t3);
      clearTimeout(t4);
      setTimeout(() => {
        setIsInterrogating(false);
        setInterrogationProgress(0);
        setInterrogationStage('');
      }, 900);
    }
  };

  // --------------------------------------------------------------------------
  // 5. Optical Bean Threshold Calibration Controls
  // --------------------------------------------------------------------------
  const handleSaveThreshold = async (val) => {
    setBeanThreshold(val);
    try {
      setIsSavingCalib(true);
      const res = await fetch('/api/set_threshold', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ threshold: val }),
      });
      const data = await res.json();
      if (data.calib) {
        setBeanThreshold(data.calib.threshold);
        setBeanHysteresis(data.calib.hysteresis);
      }
    } catch (e) {
      console.warn('Error saving threshold:', e);
    } finally {
      setIsSavingCalib(false);
    }
  };

  const handleResetThreshold = async () => {
    try {
      setIsSavingCalib(true);
      const res = await fetch('/api/reset_threshold', { method: 'POST' });
      const data = await res.json();
      if (data.calib) {
        setBeanThreshold(data.calib.threshold);
        setBeanHysteresis(data.calib.hysteresis);
      }
    } catch (e) {
      console.warn('Error resetting threshold:', e);
    } finally {
      setIsSavingCalib(false);
    }
  };

  // --------------------------------------------------------------------------
  // 6. UART Command Injection Form
  // --------------------------------------------------------------------------
  const handleTransmitCommand = async (customCmd) => {
    const cmdToSend = customCmd || txCommand;
    if (!cmdToSend.trim() || !selectedPort) return;

    try {
      const res = await fetch('/api/command', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ port: selectedPort, cmd: cmdToSend.trim() }),
      });
      const data = await res.json();

      setTxSuccessFlash(true);
      setTimeout(() => setTxSuccessFlash(false), 800);

      const entry = {
        cmd: cmdToSend,
        reply: data.response || (data.error ? `ERR: ${data.error}` : '[NO_REPLY]'),
        timestamp: new Date().toLocaleTimeString(),
        ok: data.success,
      };
      setTxResponseHistory((prev) => [entry, ...prev.slice(0, 19)]);

      if (cmdToSend.includes('HZ') || cmdToSend.includes('AS')) {
        querySensors(true);
      }
    } catch (err) {
      console.warn('Error sending command:', err);
    }
  };

  // --------------------------------------------------------------------------
  // 7. Reports & Export Handlers
  // --------------------------------------------------------------------------
  const fetchGithubStatus = async () => {
    try {
      const res = await fetch('/api/github/auth/status');
      if (res.ok) {
        const data = await res.json();
        setGithubAuth(data);
      }
    } catch (e) {
      console.warn('Failed to fetch github status:', e);
    }
  };

  useEffect(() => {
    if (showExportModal || showConfigModal) {
      fetchGithubStatus();
    }
  }, [showExportModal, showConfigModal]);

  // GitHub Device Flow Polling Loop
  useEffect(() => {
    if (!deviceFlow?.device_code) return;
    let cancelled = false;
    let pollTimer = null;

    const poll = async (intervalSec) => {
      if (cancelled) return;
      try {
        const res = await fetch('/api/github/auth/device/poll', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ device_code: deviceFlow.device_code, interval: intervalSec }),
        });
        const data = await res.json();
        if (cancelled) return;

        if (data.status === 'complete' && data.login) {
          setGithubAuth({ authenticated: true, login: data.login, method: 'device_flow', device_flow_available: true });
          setDeviceFlow(null);
          setExportStatus({ loading: false, msg: `✓ Signed in as @${data.login}!`, error: false });
          return;
        }

        if (data.status === 'slow_down') {
          const nextInterval = data.interval || intervalSec + 5;
          pollTimer = setTimeout(() => poll(nextInterval), nextInterval * 1000);
          return;
        }

        if (data.status === 'pending') {
          pollTimer = setTimeout(() => poll(intervalSec), intervalSec * 1000);
          return;
        }

        // Error / expired / denied
        setDeviceFlow(null);
        setExportStatus({ loading: false, msg: data.error || 'Device authorization ended.', error: true });
      } catch (err) {
        if (!cancelled) {
          setDeviceFlow(null);
          setExportStatus({ loading: false, msg: `Device poll error: ${err.message}`, error: true });
        }
      }
    };

    pollTimer = setTimeout(() => poll(deviceFlow.interval || 5), (deviceFlow.interval || 5) * 1000);
    return () => {
      cancelled = true;
      if (pollTimer) clearTimeout(pollTimer);
    };
  }, [deviceFlow]);

  const triggerBrowserDownload = (content, filename, mime = 'application/json') => {
    try {
      const dataStr = typeof content === 'string' ? content : JSON.stringify(content, null, 2);
      const blob = new Blob([dataStr], { type: mime });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = filename || 'spectra_export.json';
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      setTimeout(() => URL.revokeObjectURL(url), 2000);
    } catch (err) {
      console.error('Browser download failed:', err);
    }
  };

  const handleOpenServiceReport = (includeAiSummary = false) => {
    if (!selectedPort) return;
    const aiParam = includeAiSummary && aiEnabled ? '&ai_summary=1' : '';
    window.open(`/api/service_report?port=${encodeURIComponent(selectedPort)}&lang=${encodeURIComponent(lang)}${aiParam}`, '_blank');
  };

  const handleTriggerExport = async (fmt) => {
    if (!selectedPort) return;
    setExportStatus({ loading: true, msg: 'Prompting file save location...', error: false });
    try {
      const res = await fetch(`/api/export?port=${encodeURIComponent(selectedPort)}&format=${fmt}&save_dialog=1`);
      let data;
      const contentType = res.headers.get('content-type') || '';
      if (contentType.includes('application/json')) {
        data = await res.json();
      } else {
        const text = await res.text();
        data = { success: false, error: !res.ok ? `Server error (${res.status}): ${text.slice(0, 200)}` : text };
      }

      if (data.success && data.saved_path) {
        setExportStatus({ loading: false, msg: `✓ Saved: ${data.saved_path}`, error: false });
        setTimeout(() => {
          setShowExportModal(false);
          setExportStatus({ loading: false, msg: '', error: false });
        }, 2200);
      } else if (data.cancelled) {
        setExportStatus({ loading: false, msg: 'Export cancelled.', error: false });
        if (data.content) {
          setBrowserDownloadAvailable({ content: data.content, filename: data.filename || `spectra_export.${fmt}`, mime: data.mime || 'text/plain' });
        }
      } else if (data.dialog_unavailable) {
        if (data.content) {
          triggerBrowserDownload(data.content, data.filename || `spectra_export.${fmt}`, data.mime || 'text/plain');
          setExportStatus({ loading: false, msg: `✓ Saved via browser download (${data.filename})`, error: false });
        } else {
          setExportStatus({ loading: false, msg: `Dialog unavailable: ${data.error}`, error: true });
        }
      } else {
        setExportStatus({ loading: false, msg: `Export failed: ${data.error || 'Unknown error'}`, error: true });
      }
    } catch (err) {
      setExportStatus({ loading: false, msg: `Export request error: ${err.message}`, error: true });
    }
  };

  const handleJoeFileUpload = (e) => {
    const file = e.target.files?.[0];
    if (!file) {
      setJoeCsvContent('');
      setJoeFileName('');
      return;
    }
    setJoeFileName(file.name);
    const reader = new FileReader();
    reader.onload = (event) => {
      setJoeCsvContent(event.target?.result || '');
    };
    reader.readAsText(file);
  };

  const handleTriggerDumpCapture = async () => {
    if (!selectedPort) return;
    setIsDumping(true);
    const usingAi = Boolean(aiEnabled && useAiJoeMatch && joeCsvContent);
    if (usingAi) beginAiWork();
    setExportStatus({ loading: true, msg: 'Sweeping EEPROM & capturing hardware dump...', error: false });
    try {
      const res = await fetch('/api/export_capture', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          port: selectedPort,
          joe_csv: joeCsvContent,
          save_dialog: false,
          use_ollama: usingAi,
          model: aiModel || undefined,
        })
      });
      let data;
      const contentType = res.headers.get('content-type') || '';
      if (contentType.includes('application/json')) {
        data = await res.json();
      } else {
        const text = await res.text();
        data = { success: false, error: !res.ok ? `Server error (${res.status}): ${text.slice(0, 200)}` : text };
      }

      if (data.success && data.bundle) {
        setCapturedBundle(data.bundle);
        setCapturedId(data.capture_id || '');
        setCapturedFilename(data.filename || 'spectra_capture.json');
        const words = Object.keys(data.bundle?.eeprom_words || {}).length;
        const model = data.bundle?.identity?.model_name || 'Machine';
        setExportStatus({
          loading: false,
          msg: `✓ Capture ready: ${model} (${words} words). Choose Save or Upload below.`,
          error: false
        });
      } else {
        setExportStatus({ loading: false, msg: `Dump failed: ${data.error || 'Unknown error'}`, error: true });
      }
    } catch (err) {
      setExportStatus({ loading: false, msg: `Dump capture failed: ${err.message}`, error: true });
    } finally {
      setIsDumping(false);
      if (usingAi) endAiWork();
    }
  };

  const handleCalibrateOffsetsFromJoe = async (enableFirst = false) => {
    if (!aiEnabled && !enableFirst) {
      setExportStatus({ loading: false, msg: 'Local AI is OFF. Enable Local AI to run EEPROM offset calibration.', error: true });
      return;
    }
    if (enableFirst && !aiEnabled) {
      const enabledOk = await handleToggleAi(true);
      if (!enabledOk) return;
    }
    if (!joeCsvContent && !(capturedBundle?.joe_ground_truth?.raw_lines?.length)) {
      setExportStatus({ loading: false, msg: 'Attach a J.O.E. CSV export first so Local AI has ground-truth counts to match.', error: true });
      return;
    }
    setIsCalibratingOffsets(true);
    setOffsetAppliedLocally(false);
    beginAiWork();
    setExportStatus({ loading: true, msg: 'Local AI is matching J.O.E. counts against EEPROM offsets...', error: false });
    try {
      const res = await fetch('/api/ai/calibrate_offsets', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          capture_id: capturedId || undefined,
          bundle: capturedBundle || undefined,
          port: selectedPort,
          joe_csv: joeCsvContent || undefined,
          model: aiModel || undefined,
        })
      });
      const data = await res.json();
      if (data.success && data.override) {
        if (data.bundle) setCapturedBundle(data.bundle);
        if (data.capture_id) setCapturedId(data.capture_id);
        setOffsetCalibration(data.override);
        setExportStatus({
          loading: false,
          msg: `✓ AI matched ${data.matched_products} product + ${data.matched_maintenance} maintenance offsets. Review and click Fix Locally or Report Upstream.`,
          error: false,
        });
      } else {
        setExportStatus({ loading: false, msg: `Offset calibration failed: ${data.error || 'Unknown error'}`, error: true });
      }
    } catch (err) {
      setExportStatus({ loading: false, msg: `Offset calibration error: ${err.message}`, error: true });
    } finally {
      setIsCalibratingOffsets(false);
      endAiWork();
    }
  };

  const handleApplyOffsetFixLocally = async () => {
    if (!offsetCalibration) return;
    setExportStatus({ loading: true, msg: 'Saving local EEPROM offset override & refreshing dashboard...', error: false });
    try {
      const res = await fetch('/api/offsets/apply_local', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          capture_id: capturedId || undefined,
          override: offsetCalibration,
          port: selectedPort,
        })
      });
      const data = await res.json();
      if (data.success) {
        setOffsetAppliedLocally(true);
        if (data.bundle) setCapturedBundle(data.bundle);
        if (data.updated_stats) setStatsData(data.updated_stats);
        setExportStatus({
          loading: false,
          msg: `✓ Offset fix saved locally (${data.saved_key})! Machine readings are updated now. You can also upload below so this fix is included in the next SPECTRA update.`,
          error: false,
        });
      } else {
        setExportStatus({ loading: false, msg: `Failed to apply fix: ${data.error || 'Error'}`, error: true });
      }
    } catch (err) {
      setExportStatus({ loading: false, msg: `Apply local fix error: ${err.message}`, error: true });
    }
  };

  const handleSaveLocally = async () => {
    if (!capturedBundle && !selectedPort) return;
    setExportStatus({ loading: true, msg: 'Prompting file save location...', error: false });
    try {
      const res = await fetch('/api/export_capture', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          capture_id: capturedId,
          port: selectedPort,
          joe_csv: joeCsvContent,
          save_dialog: true,
        })
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
        setExportStatus({ loading: false, msg: `✓ Saved locally: ${data.saved_path}`, error: false });
      } else if (data.cancelled) {
        setExportStatus({ loading: false, msg: 'Native save cancelled.', error: false });
        setBrowserDownloadAvailable({ bundle: data.bundle || capturedBundle, filename: data.filename || capturedFilename });
      } else if (data.dialog_unavailable) {
        triggerBrowserDownload(data.bundle || capturedBundle, data.filename || capturedFilename);
        setExportStatus({ loading: false, msg: `✓ Saved via browser download (${data.filename || capturedFilename})`, error: false });
      } else {
        setExportStatus({ loading: false, msg: `Save failed: ${data.error || 'Unknown error'}`, error: true });
      }
    } catch (err) {
      setExportStatus({ loading: false, msg: `Save error: ${err.message}`, error: true });
    }
  };

  const handleUploadToCommunity = async () => {
    if (!capturedBundle && !capturedId) return;
    setIsUploading(true);
    setExportStatus({ loading: true, msg: 'Uploading capture to community repository...', error: false });
    try {
      const res = await fetch('/api/upload-capture', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          capture_id: capturedId,
          capture_data: capturedBundle,
        })
      });
      let data;
      const contentType = res.headers.get('content-type') || '';
      if (contentType.includes('application/json')) {
        data = await res.json();
      } else {
        const text = await res.text();
        data = { success: false, error: !res.ok ? `Server error (${res.status}): ${text.slice(0, 200)}` : text };
      }

      if (data.success) {
        setUploadResult({ success: true, url: data.url, msg: data.message });
        setExportStatus({ loading: false, msg: `✓ Uploaded to community repository!`, error: false });
      } else {
        setUploadResult({ success: false, url: data.url, msg: data.message || data.error });
        setExportStatus({ loading: false, msg: `Upload failed: ${data.message || data.error || 'Error'}`, error: true });
      }
    } catch (err) {
      setExportStatus({ loading: false, msg: `Upload error: ${err.message}`, error: true });
    } finally {
      setIsUploading(false);
    }
  };

  const handleStartDeviceFlow = async () => {
    setExportStatus({ loading: true, msg: 'Requesting GitHub device authorization...', error: false });
    try {
      const res = await fetch('/api/github/auth/device/start', { method: 'POST' });
      const data = await res.json();
      if (data.success) {
        setDeviceFlow(data);
        setExportStatus({ loading: false, msg: `Enter code ${data.user_code} on GitHub`, error: false });
      } else {
        setExportStatus({ loading: false, msg: data.error || 'Device flow failed', error: true });
      }
    } catch (err) {
      setExportStatus({ loading: false, msg: `Device auth error: ${err.message}`, error: true });
    }
  };

  const handleSavePat = async () => {
    if (!patInput.trim()) return;
    setExportStatus({ loading: true, msg: 'Validating GitHub personal access token...', error: false });
    try {
      const res = await fetch('/api/github/auth/token', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ token: patInput.trim() }),
      });
      const data = await res.json();
      if (data.success) {
        setGithubAuth({ authenticated: true, login: data.login, method: 'pat', device_flow_available: githubAuth.device_flow_available });
        setPatInput('');
        setShowPatInput(false);
        setExportStatus({ loading: false, msg: `✓ Connected as @${data.login}!`, error: false });
      } else {
        setExportStatus({ loading: false, msg: data.error || 'Invalid personal access token', error: true });
      }
    } catch (err) {
      setExportStatus({ loading: false, msg: `Token auth error: ${err.message}`, error: true });
    }
  };

  const handleLogout = async () => {
    try {
      await fetch('/api/github/auth/logout', { method: 'POST' });
      setGithubAuth({ authenticated: false, login: null, method: null, device_flow_available: githubAuth.device_flow_available });
      setDeviceFlow(null);
      setExportStatus({ loading: false, msg: 'Signed out from GitHub.', error: false });
    } catch (err) {
      setExportStatus({ loading: false, msg: `Logout error: ${err.message}`, error: true });
    }
  };

  const handleCopyDeviceCode = (code) => {
    if (!code) return;
    navigator.clipboard?.writeText(code);
    setCopiedCode(true);
    setTimeout(() => setCopiedCode(false), 2000);
  };

  // Derived Telemetry Values (EMPTY until machine is read)
  const telem = liveData.telemetry || {};
  const hasTelem = isConnected && telem && Object.keys(telem).length > 0;
  const coffeeTemp = hasTelem && telem.heater_coffee_c != null ? telem.heater_coffee_c : null;
  const buPos = hasTelem && telem.bu_encoder_pos != null ? telem.bu_encoder_pos : null;
  const buUpper = hasTelem && telem.bu_encoder_upper != null ? telem.bu_encoder_upper : null;
  const flowRate = hasTelem && telem.flow_rate_ml_s != null ? telem.flow_rate_ml_s : null;
  const beansOk = hasTelem && telem.beans_ok != null ? telem.beans_ok : null;
  const opticalDelta = hasTelem && telem.optical_delta != null ? telem.optical_delta : null;

  // Find switch statuses (only when read)
  const tankSw = hasTelem ? (liveData?.switches || []).find((s) => s.id === 'water_tank') : null;
  const traySw = hasTelem ? (liveData?.switches || []).find((s) => s.id === 'drip_tray') : null;
  const filterSw = hasTelem ? (liveData?.switches || []).find((s) => s.id === 'claris_filter') : null;
  const beansSw = hasTelem ? (liveData?.switches || []).find((s) => s.id === 'bean_hopper') : null;

  // Interrogation Metrics (EMPTY until machine is read)
  const totalPreps = statsData?.total_preparations ?? null;
  const totalCups = statsData?.total_cups ?? null;
  const cleanCount = statsData?.maintenance?.find((m) => (m.label || m.name || '')?.toLowerCase().includes('clean'))?.count ?? null;
  const decalcCount = statsData?.maintenance?.find((m) => (m.label || m.name || '')?.toLowerCase().includes('descal') || (m.label || m.name || '')?.toLowerCase().includes('decalc'))?.count ?? null;

  // Filtered Beverages (EMPTY until machine is read)
  const beverages = statsData?.beverages || [];

  const filteredBeverages = beverages.filter(
    (b) =>
      bevSearch === '' ||
      (b.name || '').toLowerCase().includes(bevSearch.toLowerCase()) ||
      (b.type || '').toLowerCase().includes(bevSearch.toLowerCase()) ||
      String(b.code || '').includes(bevSearch)
  );

  return (
    <div className={`min-h-screen flex flex-col justify-between ${theme.bg} ${theme.font} transition-opacity duration-300 ${bootReady ? 'opacity-100' : 'opacity-0'} select-none ${theme.isScanline ? 'cyber-scanlines' : ''}`}>
      {/* ==================================================================== */}
      {/* ZONE 1: TOP BRANDING & HARDWARE CONNECTION BAR */}
      {/* ==================================================================== */}
      <header className={`sticky top-0 z-50 px-4 py-2 flex flex-wrap items-center justify-between border-b ${theme.border} ${theme.headerBg} backdrop-blur-md gap-3`}>
        {/* Left: Professional Brand Header */}
        <div className="flex items-center space-x-3">
          <div className="flex items-center space-x-2">
            <Zap className="w-5 h-5 text-[#FCEE09] animate-pulse" />
            <span className="text-sm font-black tracking-widest text-[#FCEE09] font-mono uppercase">
              SPECTRA
            </span>
          </div>
          <button
            type="button"
            onClick={() => {
              setConfigInitialSection('updates');
              setShowConfigModal(true);
              checkForUpdates(false);
            }}
            className="text-[10px] px-2 py-0.5 bg-black/60 hover:bg-zinc-900 text-zinc-300 border border-zinc-700 hover:border-zinc-500 font-mono font-bold tracking-wider rounded transition-colors cursor-pointer"
            title={t('headerBuildCheckTitle', { build: liveBuild || debugSummary?.build || '20261117.1859' })}
          >
            BUILD {liveBuild || debugSummary?.build || '20261117.1859'}
          </button>
          {updateInfo?.update_available && (
            <button
              type="button"
              onClick={() => {
                setConfigInitialSection('updates');
                setShowConfigModal(true);
              }}
              className="flex items-center space-x-1 text-[10px] px-2 py-0.5 bg-emerald-950/80 hover:bg-emerald-900 text-emerald-300 border border-emerald-500/70 font-mono font-extrabold tracking-wider rounded animate-pulse cursor-pointer transition-colors"
              title={t('headerUpdateTitle', { build: updateInfo.latest_build })}
            >
              <Download className="w-3 h-3" />
              <span>{t('headerUpdateBtn', { build: updateInfo.latest_build })}</span>
            </button>
          )}
          <span className="text-xs text-zinc-400 font-mono hidden xl:inline">
            {t('appSubtitle')}
          </span>
        </div>

        {/* Right: Hardware Port Controls & Report Actions */}
        <div className="flex flex-wrap items-center gap-2 text-xs">
          {/* Serial Port Dropdown */}
          <div className="flex items-center space-x-1 bg-black/40 px-2 py-1 rounded border border-gray-800">
            <Radio className="w-3.5 h-3.5 text-gray-400" />
            <select
              value={selectedPort}
              onChange={(e) => {
                const newPort = e.target.value;
                setSelectedPort(newPort);
                setHardwareError(null);
                querySensors(true, newPort);
              }}
              className="bg-transparent text-gray-200 text-xs font-mono outline-none cursor-pointer max-w-[200px]"
            >
              {availablePorts.map((p) => (
                <option key={p} value={p} className="bg-gray-900 text-gray-200">
                  {p}
                </option>
              ))}
            </select>
            <button onClick={fetchPorts} title={t('refreshPortsTitle')} className="text-gray-400 hover:text-white ml-1">
              <RefreshCw className="w-3 h-3" />
            </button>
          </div>

          {/* Action Buttons */}
          <button
            onClick={() => querySensors(true)}
            className="flex items-center space-x-1 px-2.5 py-1 bg-sky-950/40 hover:bg-sky-900/60 border border-sky-800/60 text-sky-300 font-bold rounded"
          >
            <Zap className="w-3.5 h-3.5" />
            <span>{t('btnRefresh')}</span>
          </button>

          <button
            onClick={() => setIsPolling(!isPolling)}
            className={`flex items-center space-x-1 px-3 py-1 font-bold rounded ${
              isPolling
                ? 'bg-emerald-600/30 text-emerald-400 border border-emerald-500/60 hover:bg-emerald-600/40'
                : 'bg-gray-800/40 text-gray-300 border border-gray-700 hover:bg-gray-800/60'
            }`}
          >
            {isPolling ? <Pause className="w-3.5 h-3.5" /> : <Play className="w-3.5 h-3.5" />}
            <span>{isPolling ? t('btnPolling') : t('btnStartPoll')}</span>
          </button>

          {/* Interrogate Button with Integrated Progress Fill */}
          <button
            onClick={runFullInterrogation}
            disabled={isInterrogating || !selectedPort}
            className={`relative overflow-hidden flex items-center space-x-1.5 px-3 py-1 font-bold rounded transition-all font-mono ${
              isInterrogating
                ? 'bg-purple-950/80 text-purple-200 border border-purple-500 shadow-[0_0_12px_rgba(168,85,247,0.4)]'
                : 'bg-purple-950/40 hover:bg-purple-900/60 text-purple-300 border border-purple-800/60'
            } disabled:opacity-50`}
            title={t('btnInterrogateTitle')}
          >
            {isInterrogating && (
              <div
                className="absolute inset-0 bg-purple-600/50 transition-all duration-300 ease-out"
                style={{ width: `${interrogationProgress}%` }}
              />
            )}
            <Sparkles className="w-3.5 h-3.5 text-purple-400 z-10" />
            <span className="z-10">{isInterrogating ? t('btnReadingPct', { pct: interrogationProgress }) : t('btnInterrogate')}</span>
          </button>

          {/* Service Report Trigger Button (Enabled ONLY when read) */}
          <button
            onClick={() => handleOpenServiceReport(false)}
            disabled={!statsData || isInterrogating}
            className={`flex items-center space-x-1 px-2.5 py-1 font-bold rounded transition-all ${
              statsData
                ? 'bg-amber-950/40 hover:bg-amber-900/60 border border-amber-800/60 text-amber-300 cursor-pointer'
                : 'bg-zinc-900/40 border border-zinc-800 text-zinc-600 cursor-not-allowed opacity-50'
            }`}
            title={statsData ? t('btnReportTitleReady') : t('btnReportTitleDisabled')}
          >
            <FileText className="w-3.5 h-3.5" />
            <span>{t('btnReport')}</span>
          </button>

          {/* Export Trigger Button (Enabled ONLY when read) */}
          <button
            onClick={() => {
              if (!statsData) return;
              setShowExportModal(true);
            }}
            disabled={!statsData || isInterrogating}
            className={`flex items-center space-x-1 px-2.5 py-1 font-bold rounded transition-all ${
              statsData
                ? 'bg-indigo-950/40 hover:bg-indigo-900/60 border border-indigo-800/60 text-indigo-300 cursor-pointer'
                : 'bg-zinc-900/40 border border-zinc-800 text-zinc-600 cursor-not-allowed opacity-50'
            }`}
            title={statsData ? t('btnExportTitleReady') : t('btnExportTitleDisabled')}
          >
            <Download className="w-3.5 h-3.5" />
            <span>{t('btnExport')}</span>
          </button>

          {/* Firmware Inspector Trigger Button */}
          <button
            onClick={() => setActiveTab('hmi_tools')}
            className={`flex items-center space-x-1 px-2.5 py-1 font-bold rounded transition-all ${
              activeTab === 'hmi_tools'
                ? 'bg-cyan-600 text-black border border-cyan-400 shadow-[0_0_12px_rgba(6,182,212,0.5)]'
                : 'bg-cyan-950/40 hover:bg-cyan-900/60 border border-cyan-800/60 text-cyan-300 cursor-pointer'
            }`}
            title={t('btnFirmwareInspectorTitle')}
          >
            <Box className="w-3.5 h-3.5" />
            <span>{t('btnFirmwareInspector')}</span>
          </button>

          {/* Global Local AI Power Switch (Default: OFF) */}
          <button
            onClick={() => handleToggleAi(!aiEnabled)}
            className={`flex items-center space-x-1.5 px-2.5 py-1 font-mono font-bold rounded text-[11px] transition-all cursor-pointer border ${
              aiTask?.active
                ? 'bg-purple-900/80 border-purple-400 text-purple-100 animate-pulse shadow-[0_0_10px_rgba(168,85,247,0.5)]'
                : aiEnabled
                ? 'bg-purple-950/70 hover:bg-purple-900/80 border-purple-500/70 text-purple-200'
                : 'bg-black/40 hover:bg-zinc-900 border-zinc-700 text-zinc-400'
            }`}
            title={aiEnabled ? t('aiTitleOn', { model: aiModel || 'auto' }) : t('aiTitleOff')}
          >
            <Power className={`w-3.5 h-3.5 ${aiEnabled ? 'text-emerald-400' : 'text-zinc-500'}`} />
            <span>
              {aiTask?.active
                ? `AI: ${Math.round(aiTask.percent || 0)}%`
                : aiEnabled
                ? t('aiStatusOn', { model: aiModel ? ` (${aiModel})` : '' })
                : t('aiStatusOff')}
            </span>
          </button>

          {/* Configuration & AI Model / GitHub Manager */}
          <button
            onClick={() => {
              setConfigInitialSection('ai');
              setShowConfigModal(true);
            }}
            className="flex items-center space-x-1 px-2.5 py-1 font-mono font-bold rounded text-[11px] bg-black/40 hover:bg-zinc-800 border border-zinc-700 text-zinc-200 transition-colors cursor-pointer"
            title={t('btnConfigTitle')}
          >
            <Settings className="w-3.5 h-3.5 text-[#FCEE09]" />
            <span>{t('btnConfig')}</span>
          </button>

          {/* Dynamic Viewport Scale Indicator */}
          <button
            onClick={() => {
              const modes = ['auto', 0.85, 1.0, 1.15];
              const nextIdx = (modes.indexOf(scaleMode) + 1) % modes.length;
              setScaleMode(modes[nextIdx]);
            }}
            className="flex items-center space-x-1 px-2 py-0.5 rounded text-[11px] font-mono font-bold bg-black/40 hover:bg-black/60 border border-zinc-700 text-zinc-300 transition-colors"
            title={t('scaleTitle', {
              pct: Math.round(currentScale * 100),
              mode: scaleMode === 'auto' ? t('scaleModeAuto') : t('scaleModeManual'),
            })}
          >
            <span>📐</span>
            <span>{scaleMode === 'auto' ? t('scaleAuto', { pct: Math.round(currentScale * 100) }) : `${Math.round(currentScale * 100)}%`}</span>
          </button>

          {/* Hidden Debug & Process Monitor Trigger */}
          <button
            onClick={() => setIsDebugOpen(!isDebugOpen)}
            className={`flex items-center space-x-1.5 px-2 py-0.5 rounded text-[11px] font-mono font-bold transition-all ${
              (debugCounts?.errorCount || 0) > 0
                ? 'bg-rose-950 text-rose-200 border border-rose-500 shadow-[0_0_10px_rgba(244,63,94,0.5)] animate-pulse'
                : (debugCounts?.warnCount || 0) > 0
                ? 'bg-amber-950/60 text-amber-300 border border-amber-600'
                : 'bg-black/40 text-zinc-400 hover:text-zinc-200 border border-zinc-700'
            }`}
            title={t('debugTitle')}
          >
            <span>🐞</span>
            {(debugCounts?.errorCount || 0) > 0 ? (
              <span className="font-extrabold text-rose-300">{debugCounts.errorCount}</span>
            ) : (debugCounts?.warnCount || 0) > 0 ? (
              <span className="text-amber-300">{debugCounts.warnCount}</span>
            ) : null}
          </button>

          {/* Hardware Online Pill */}
          <div className="flex items-center space-x-1.5 px-2 py-0.5 rounded text-[11px] font-bold bg-black/40 border border-emerald-500/30 text-emerald-400">
            <span className={`w-2 h-2 rounded-full ${isConnected ? 'bg-emerald-400 animate-pulse' : 'bg-gray-500'}`} />
            <span>{isConnected ? t('statusOnline') : t('statusStandby')}</span>
          </div>
        </div>
      </header>

      {/* ==================================================================== */}
      {/* GLOBAL AI PROGRESS & KILL-SWITCH STATUS BAR (VISIBLE WHENEVER WORKING) */}
      {/* ==================================================================== */}
      <AiStatusBar
        lang={lang}
        aiEnabled={aiEnabled}
        aiTask={aiTask}
        aiDownload={aiDownload}
        onTurnAiOff={() => handleToggleAi(false)}
      />

      {/* ==================================================================== */}
      {/* HIGH-VISIBILITY PROGRESS BAR FIELD DURING MACHINE DATA PULL */}
      {/* ==================================================================== */}
      {isInterrogating && (
        <div className="bg-[#121218] border-b border-[#FCEE09]/50 px-4 py-2.5 text-xs font-mono shadow-lg animate-pulse">
          <div className="flex items-center justify-between mb-1.5">
            <div className="flex items-center space-x-2 text-[#FCEE09]">
              <Zap className="w-4 h-4 text-[#FCEE09]" />
              <span className="font-extrabold uppercase tracking-wider">{t('readingMachineData')}</span>
              <span className="text-zinc-300 font-bold">{interrogationStage}</span>
            </div>
            <span className="font-extrabold text-[#FCEE09] text-sm">{interrogationProgress}%</span>
          </div>
          <div className="w-full h-2.5 bg-black/70 rounded-full overflow-hidden border border-zinc-800 shadow-inner">
            <div
              className="h-full bg-gradient-to-r from-[#FCEE09] via-yellow-400 to-[#00F0FF] transition-all duration-300 ease-out shadow-[0_0_10px_rgba(252,238,9,0.5)]"
              style={{ width: `${interrogationProgress}%` }}
            />
          </div>
        </div>
      )}

      {/* Hardware Warning Alert Banner */}
      {hardwareError && (
        <div className="bg-rose-950/90 border-b border-rose-500/60 px-4 py-2 flex items-center justify-between text-xs text-rose-200 backdrop-blur">
          <div className="flex items-center space-x-2">
            <AlertTriangle className="w-4 h-4 text-rose-400 shrink-0 animate-pulse" />
            <span>
              <strong>{t('hardwareStatusLabel')}</strong> {hardwareError}
            </span>
          </div>
          <button
            onClick={() => {
              pollFailCountRef.current = 0;
              setHardwareError(null);
              querySensors(true, null, false);
            }}
            className="px-2.5 py-0.5 bg-rose-800 hover:bg-rose-700 text-white font-bold rounded text-[11px] transition-colors"
          >
            {t('btnRetry')}
          </button>
        </div>
      )}

      {/* ==================================================================== */}
      {/* ZONE 2: 9 REAL-TIME UNIFIED HARDWARE & STATS KPI TILES (EMPTY UNTIL READ) */}
      {/* ==================================================================== */}
      <section className={`px-4 py-2.5 border-b ${theme.border} ${theme.panelBg}`}>
        <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-5 lg:grid-cols-9 gap-2">
          {/* 1. Total Preps */}
          <div className={`p-2 bg-black/40 border border-gray-800 rounded ${theme.clipClass}`}>
            <div className="text-[10px] text-gray-500 font-bold uppercase tracking-wider">
              {t('kpiTotalPreps')}
            </div>
            <div className="text-xs font-bold font-mono my-1 text-white">
              {totalPreps != null ? totalPreps : '---'}
            </div>
            <div className="text-[10px] text-gray-500 truncate">
              {totalCups != null ? t('kpiTotalCups', { cups: totalCups }) : t('kpiAwaitingRead')}
            </div>
          </div>

          {/* 2. Thermoblock TB1 */}
          <div className={`p-2 bg-black/40 border border-gray-800 rounded ${theme.clipClass}`}>
            <div className="text-[10px] text-gray-500 font-bold uppercase tracking-wider">
              {t('kpiTb1Heater')}
            </div>
            <div className={`text-xs font-bold font-mono my-1 ${theme.textPrimary}`}>
              {coffeeTemp != null ? `${coffeeTemp.toFixed(1)} °C` : '--- °C'}
            </div>
            <div className="text-[10px] text-gray-500 truncate">
              {hasTelem ? (telem.heater_coffee_status ? txVal(lang, telem.heater_coffee_status) : t('kpiReadyToBrew')) : t('kpiStandby')}
            </div>
          </div>

          {/* 3. Brew Unit Encoder */}
          <div className={`p-2 bg-black/40 border border-gray-800 rounded ${theme.clipClass}`}>
            <div className="text-[10px] text-gray-500 font-bold uppercase tracking-wider">
              {t('kpiBuEncoder')}
            </div>
            <div className="text-xs font-bold font-mono my-1 text-purple-400">
              {buPos != null ? `${buPos} / ${buUpper ?? '---'}` : '--- / ---'}
            </div>
            <div className="text-[10px] text-gray-500 truncate">
              {hasTelem ? (telem.bu_position_state || t('kpiOpticalQuad')) : t('kpiStandby')}
            </div>
          </div>

          {/* 4. Water Flow */}
          <div className={`p-2 bg-black/40 border border-gray-800 rounded ${theme.clipClass}`}>
            <div className="text-[10px] text-gray-500 font-bold uppercase tracking-wider">
              {t('kpiWaterFlow')}
            </div>
            <div className="text-xs font-bold font-mono my-1 text-cyan-400">
              {flowRate != null ? `${flowRate.toFixed(1)} ml/s` : '--- ml/s'}
            </div>
            <div className="text-[10px] text-gray-500 truncate">
              {hasTelem ? t('kpiFlowVol', { vol: (telem.flow_volume_ml ?? 0).toFixed(1) }) : t('kpiStandby')}
            </div>
          </div>

          {/* 5. Water Tank */}
          <div className={`p-2 bg-black/40 border border-gray-800 rounded ${theme.clipClass}`}>
            <div className="text-[10px] text-gray-500 font-bold uppercase tracking-wider">
              {t('kpiWaterTank')}
            </div>
            <div className={`text-xs font-bold font-mono my-1 ${tankSw ? (tankSw.ok ? 'text-emerald-400' : 'text-rose-400') : 'text-zinc-500'}`}>
              {tankSw ? (tankSw.ok ? t('kpiWaterOk') : t('kpiWaterEmpty')) : '---'}
            </div>
            <div className="text-[10px] text-gray-500 truncate">{hasTelem ? t('kpiFloatSwitch') : t('kpiStandby')}</div>
          </div>

          {/* 6. Drip Tray */}
          <div className={`p-2 bg-black/40 border border-gray-800 rounded ${theme.clipClass}`}>
            <div className="text-[10px] text-gray-500 font-bold uppercase tracking-wider">
              {t('kpiDripTray')}
            </div>
            <div className={`text-xs font-bold font-mono my-1 ${traySw ? (traySw.ok ? 'text-emerald-400' : 'text-rose-400') : 'text-zinc-500'}`}>
              {traySw ? (traySw.ok ? t('kpiInserted') : t('kpiMissing')) : '---'}
            </div>
            <div className="text-[10px] text-gray-500 truncate">{hasTelem ? t('kpiContactSwitch') : t('kpiStandby')}</div>
          </div>

          {/* 7. Bean Hopper */}
          <div className={`p-2 bg-black/40 border border-gray-800 rounded ${theme.clipClass}`} title={beansSw?.details || beansSw?.status || ''}>
            <div className="text-[10px] text-gray-500 font-bold uppercase tracking-wider">
              {t('kpiBeanHopper')}
            </div>
            <div className={`text-xs font-bold font-mono my-1 ${beansSw ? (beansSw.ok ? 'text-emerald-400' : 'text-rose-400') : (beansOk != null ? (beansOk ? 'text-emerald-400' : 'text-rose-400') : 'text-zinc-500')}`}>
              {beansSw?.details?.includes('Monitored Locally')
                ? t('kpiLocalEf518d')
                : (beansSw ? (beansSw.ok ? t('kpiBeansOk') : t('kpiFillBeans')) : (beansOk != null ? (beansOk ? t('kpiBeansOk') : t('kpiFillBeans')) : '---'))}
            </div>
            <div className="text-[10px] text-gray-500 truncate" title={beansSw?.details || beansSw?.status || ''}>
              {beansSw?.details ? txVal(lang, beansSw.details) : (beansOk != null ? (beansOk ? t('kpiHopperCharged') : t('kpiFillBeans')) : t('kpiStandby'))}
            </div>
          </div>

          {/* 8. Cleanings */}
          <div className={`p-2 bg-black/40 border border-gray-800 rounded ${theme.clipClass}`}>
            <div className="text-[10px] text-gray-500 font-bold uppercase tracking-wider">
              {t('kpiCleanings')}
            </div>
            <div className="text-xs font-bold font-mono my-1 text-sky-400">
              {cleanCount != null ? t('kpiCyclesCount', { count: cleanCount }) : '---'}
            </div>
            <div className="text-[10px] text-gray-500 truncate">
              {statsData ? t('kpiMaintRecord') : t('kpiAwaitingRead')}
            </div>
          </div>

          {/* 9. Descalings */}
          <div className={`p-2 bg-black/40 border border-gray-800 rounded ${theme.clipClass}`}>
            <div className="text-[10px] text-gray-500 font-bold uppercase tracking-wider">
              {t('kpiDecalcs')}
            </div>
            <div className="text-xs font-bold font-mono my-1 text-amber-400">
              {decalcCount != null ? t('kpiCyclesCount', { count: decalcCount }) : '---'}
            </div>
            <div className="text-[10px] text-gray-500 truncate">
              {statsData ? t('kpiMaintRecord') : t('kpiAwaitingRead')}
            </div>
          </div>
        </div>
      </section>

      {/* ==================================================================== */}
      {/* ZONE 3: MAIN NAVIGATION TABS */}
      {/* ==================================================================== */}
      <nav className={`px-4 pt-2 border-b ${theme.border} ${theme.panelBg} flex flex-wrap gap-1 text-xs`}>
        {WORKSPACE_TABS.map((tab) => {
          const isActive = activeTab === tab.id;
          const isDev = tab.id === 'mem_mapper' || tab.label.includes('[DEV]');
          return (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              className={`px-3 py-2 font-bold tracking-wider transition-all duration-150 border-b-2 flex items-center space-x-1.5 ${
                isActive
                  ? `${theme.borderActive} ${theme.textPrimary} bg-white/5`
                  : 'border-transparent text-gray-400 hover:text-gray-200 hover:border-gray-600'
              }`}
            >
              <span>{tab.label.replace(' [DEV]', '')}</span>
              {isDev && (
                <span className="text-[9px] px-1.5 py-0.2 bg-red-950/80 text-red-400 border border-red-500/70 font-mono font-extrabold rounded">
                  DEV
                </span>
              )}
            </button>
          );
        })}
      </nav>

      {/* ==================================================================== */}
      {/* ZONE 4: TAB CONTENT CONTAINER */}
      {/* ==================================================================== */}
      <main className="flex-1 p-4 overflow-y-auto">
        {/* TAB 1: OVERVIEW & AI DIAGNOSTIC ADVISOR */}
        {activeTab === 'overview' && (
          <DiagnosticAdvisorTab
            theme={theme}
            lang={lang}
            statsData={statsData}
            liveData={liveData}
            selectedPort={selectedPort}
            onOpenServiceReport={handleOpenServiceReport}
            onOpenExport={() => setShowExportModal(true)}
            onInterrogate={runFullInterrogation}
            isInterrogating={isInterrogating}
            aiEnabled={aiEnabled}
            aiModel={aiModel}
            onToggleAi={handleToggleAi}
            beginAiWork={beginAiWork}
            endAiWork={endAiWork}
            aiServiceSummary={aiServiceSummary}
            setAiServiceSummary={setAiServiceSummary}
            onStatsUpdated={(s) => setStatsData(s)}
            onOpenConfig={() => setShowConfigModal(true)}
          />
        )}

        {/* TAB 2: SENSORS & OSCILLOSCOPE STRIP CHART (MATCHING GTK _create_sensors_tab) */}
        {activeTab === 'sensors' && (
          <div className="space-y-4">
            {/* Top Paned Layout: Left Digital Twin / Right Oscilloscope & Event Stream */}
            <div className="grid grid-cols-1 lg:grid-cols-12 gap-4">
              {/* LEFT COLUMN: Interactive Digital Twin & Component Inspector */}
              <div className="lg:col-span-6 space-y-3">
                <DigitalTwinSchematic
                  theme={theme}
                  lang={lang}
                  liveData={liveData}
                  statsData={statsData}
                />

                {/* Coffee Heater NTC Diagnostic Sensor Card (AS: Check Sensor) */}
                <div className={`p-3.5 border rounded ${theme.surfaceClass}`}>
                  <div className="flex flex-wrap items-center justify-between gap-2 border-b border-gray-800 pb-1.5 mb-2">
                    <span className="text-xs font-bold text-amber-400 uppercase tracking-wider flex items-center space-x-1.5">
                      <SlidersHorizontal className="w-3.5 h-3.5" />
                      <span>{t('ntcSensorCardTitle')}</span>
                    </span>
                    <span className="text-[11px] font-mono text-gray-400">
                      {t('shuntLabel')} <strong className="text-amber-400">{telem.heater_ntc_shunt_ratio ? `${telem.heater_ntc_shunt_ratio} (+${telem.heater_ntc_shunt_gain_pct}%)` : (opticalDelta != null ? `Delta: ${opticalDelta}` : t('kpiStandby'))}</strong>
                    </span>
                  </div>
                  <div className="space-y-1.5 text-xs">
                    <div className="flex justify-between font-mono text-[11px]">
                      <span className="text-gray-400">{t('selfTestLabel')} <strong className={telem.heater_ntc_self_test_ok ? "text-emerald-400" : "text-amber-400"}>{telem.heater_ntc_self_test_ok ? t('nominalShuntOk') : (telem.heater_ntc_self_test_ok === false ? t('outOfRange') : t('kpiStandby'))}</strong></span>
                      <span className="text-amber-400">{t('p518ValidRange')}</span>
                    </div>
                    <div className="flex items-center justify-between pt-1">
                      <span className="text-[11px] font-mono text-gray-400">
                        {t('ambientOffOn', { off: telem.bean_adcs?.[0] ?? '--', on: telem.bean_adcs?.[1] ?? '--' })}
                      </span>
                      <span className={`text-[10px] font-bold px-2 py-0.5 rounded ${beansOk ? 'bg-emerald-950 text-emerald-400 border border-emerald-700' : 'bg-rose-950 text-rose-400 border border-rose-700'}`}>
                        {beansOk ? t('kpiBeansOk') : t('kpiFillBeans')}
                      </span>
                    </div>
                  </div>
                </div>
              </div>

              {/* RIGHT COLUMN: Oscilloscope Strip Chart (Temp over Time) & Event Stream Log */}
              <div className="lg:col-span-6 space-y-3">
                {/* 1. Real-Time Oscilloscope Strip Chart (Exact parity with old UI OscilloscopeWidget) */}
                <OscilloscopeStripChart
                  theme={theme}
                  lang={lang}
                  liveData={liveData}
                  maxSamples={60}
                />

                {/* 2. Real-Time Bus Event Stream & Safety Log */}
                <div className={`p-3 border rounded ${theme.surfaceClass} space-y-2`}>
                  <div className="flex flex-wrap items-center justify-between gap-2 border-b border-gray-800 pb-1.5 text-xs">
                    <span className="font-bold text-gray-200 uppercase tracking-wider flex items-center space-x-1.5">
                      <Terminal className="w-4 h-4 text-emerald-400" />
                      <span>{t('busStreamTitle')}</span>
                    </span>
                    <div className="flex items-center space-x-1.5">
                      <button
                        onClick={() => setIsStreamPaused(!isStreamPaused)}
                        className={`px-2 py-0.5 rounded text-[11px] font-bold font-mono flex items-center space-x-1 ${
                          isStreamPaused ? 'bg-amber-600 text-white' : 'bg-gray-800 hover:bg-gray-700 text-gray-300'
                        }`}
                      >
                        {isStreamPaused ? <Play className="w-3 h-3" /> : <Pause className="w-3 h-3" />}
                        <span>{isStreamPaused ? t('btnResume') : t('btnPause')}</span>
                      </button>
                      <button
                        onClick={() => setBusEvents([])}
                        className="px-2 py-0.5 rounded text-[11px] font-bold font-mono bg-gray-800 hover:bg-gray-700 text-gray-300 flex items-center space-x-1"
                      >
                        <Trash2 className="w-3 h-3" />
                        <span>{t('btnClear')}</span>
                      </button>
                    </div>
                  </div>

                  {/* Scrolling Log Box */}
                  <div className="h-44 bg-black/60 border border-gray-800 rounded p-2 overflow-y-auto font-mono text-[11px] space-y-1 text-gray-300 select-text">
                    {busEvents.length === 0 ? (
                      <div className="text-gray-600 italic">{t('busStreamEmpty')}</div>
                    ) : (
                      busEvents.map((evt, idx) => (
                        <div key={idx} className="hover:bg-white/5 py-0.5 px-1 rounded truncate">
                          {evt}
                        </div>
                      ))
                    )}
                  </div>
                </div>
              </div>
            </div>

            {/* Bottom Row: 7 Physical Microswitches & 15 Hardware Safety Registers */}
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
              {/* Microswitches */}
              <div className={`p-4 border rounded ${theme.surfaceClass}`}>
                <div className="text-xs font-bold text-gray-300 uppercase tracking-wider mb-2.5 flex items-center justify-between border-b border-gray-800 pb-2">
                  <span>{t('microswitchesTitle')}</span>
                  <span className="text-[10px] font-mono text-emerald-400">{t('microswitchesCount')}</span>
                </div>
                <div className="space-y-1.5">
                  {liveData.switches.map((sw) => (
                    <div key={sw.id} className="flex items-center justify-between p-2 bg-black/40 border border-gray-800/80 rounded text-xs font-mono">
                      <div className="flex items-center space-x-2">
                        <span>{sw.icon}</span>
                        <span className="font-bold text-gray-200">{txVal(lang, sw.name)}</span>
                      </div>
                      <div className="flex items-center space-x-2">
                        <span className="text-gray-400">{txVal(lang, sw.status)}</span>
                        <span className={`px-2 py-0.5 rounded text-[10px] font-bold ${sw.ok ? 'bg-emerald-950 text-emerald-400 border border-emerald-700' : 'bg-rose-950 text-rose-400 border border-rose-700'}`}>
                          {txVal(lang, sw.badge)}
                        </span>
                      </div>
                    </div>
                  ))}
                </div>
              </div>

              {/* Component Fault & Safety Diagnostic Registers */}
              <div className={`p-4 border rounded ${theme.surfaceClass}`}>
                <div className="text-xs font-bold text-gray-300 uppercase tracking-wider mb-2.5 flex items-center justify-between border-b border-gray-800 pb-2">
                  <span>{t('faultRegistersTitle')}</span>
                  <span className="text-[10px] font-mono text-sky-400">{t('faultRegistersCount')}</span>
                </div>
                <div className="max-h-[300px] overflow-y-auto space-y-1.5 pr-1">
                  {liveData.sensors.map((s) => (
                    <div key={s.id} className="flex items-center justify-between p-1.5 bg-black/40 border border-gray-800/60 rounded text-xs font-mono">
                      <span className="text-gray-300">{txVal(lang, s.name)}</span>
                      <div className="flex items-center space-x-2">
                        <span className="text-[11px] text-gray-400">{txVal(lang, s.status)}</span>
                        <span className={`px-1.5 py-0.2 rounded text-[9px] font-bold ${s.ok ? 'bg-emerald-950 text-emerald-400' : 'bg-rose-950 text-rose-400'}`}>
                          {txVal(lang, s.badge)}
                        </span>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          </div>
        )}

        {/* TAB 3: BEVERAGE REGISTRY TABLE */}
        {activeTab === 'beverages' && (
          <div className={`p-4 border rounded ${theme.surfaceClass} space-y-3`}>
            <div className="flex flex-wrap items-center justify-between gap-2 border-b border-gray-800 pb-2">
              <span className="text-xs font-bold text-gray-300 uppercase tracking-wider flex items-center space-x-1.5">
                <Coffee className="w-4 h-4 text-amber-400" />
                <span>{t('bevRegistryTitle')}</span>
              </span>
              <div className="flex items-center space-x-2">
                <div className="relative">
                  <Search className="w-3.5 h-3.5 text-gray-400 absolute left-2.5 top-2" />
                  <input
                    type="text"
                    value={bevSearch}
                    onChange={(e) => setBevSearch(e.target.value)}
                    placeholder={t('bevSearchPlaceholder')}
                    disabled={!statsData}
                    className="pl-8 pr-3 py-1 bg-black/40 border border-gray-800 rounded text-xs text-white placeholder-gray-500 outline-none w-48 font-mono disabled:opacity-40"
                  />
                </div>
                <span className="text-xs font-mono text-gray-400">
                  {statsData ? t('bevSpecialtiesCount', { count: filteredBeverages.length }) : t('bevAwaitingRead')}
                </span>
              </div>
            </div>

            {!statsData ? (
              <div className="p-8 text-center space-y-4 font-mono">
                <div className="w-14 h-14 rounded-full bg-black/40 border border-[#FCEE09]/30 flex items-center justify-center mx-auto text-[#FCEE09]">
                  <Coffee className="w-7 h-7 animate-pulse" />
                </div>
                <div className="space-y-1">
                  <h3 className="text-sm font-bold text-white uppercase tracking-wider">
                    {t('bevEmptyTitle')}
                  </h3>
                  <p className="text-xs text-zinc-400 max-w-md mx-auto">
                    {t('bevEmptyDesc', { port: selectedPort || t('serialPortFallback') })}
                  </p>
                </div>
                <div className="pt-1">
                  <button
                    onClick={runFullInterrogation}
                    disabled={isInterrogating || !selectedPort}
                    className="px-5 py-2.5 bg-[#FCEE09] hover:bg-yellow-300 text-black font-mono font-bold text-xs uppercase tracking-wider rounded transition-colors disabled:opacity-50"
                  >
                    {isInterrogating ? t('btnReadingEeprom') : t('btnInterrogateShort')}
                  </button>
                </div>
              </div>
            ) : filteredBeverages.length === 0 ? (
              <div className="p-8 text-center text-xs text-zinc-500 font-mono">
                {t('bevNoRecords')}
              </div>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-left text-xs font-mono">
                  <thead>
                    <tr className="border-b border-gray-800 text-gray-500 text-[10px] uppercase">
                      <th className="py-2 px-3">{t('colCode')}</th>
                      <th className="py-2 px-3">{t('colSpecialty')}</th>
                      <th className="py-2 px-3">{t('colQty')}</th>
                      <th className="py-2 px-3">{t('colShare')}</th>
                      <th className="py-2 px-3">{t('colCategory')}</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-gray-800/60">
                    {filteredBeverages.map((bev) => (
                      <tr key={bev.code} className="hover:bg-white/5 transition-colors">
                        <td className="py-2 px-3 text-gray-500">0x{bev.code.toString(16).padStart(2, '0').toUpperCase()}</td>
                        <td className="py-2 px-3 font-bold text-white">{txBeverageName(lang, bev.name)}</td>
                        <td className="py-2 px-3 text-amber-400 font-bold">{bev.count.toLocaleString()}</td>
                        <td className="py-2 px-3 text-gray-300">
                          {bev.share || (totalPreps > 0 ? `${((bev.count / totalPreps) * 100).toFixed(1)}%` : '0.0%')}
                        </td>
                        <td className="py-2 px-3">
                          <span className={`px-2 py-0.5 rounded text-[10px] font-bold ${
                            bev.type === 'Milk'
                              ? 'bg-purple-950 text-purple-300 border border-purple-800'
                              : bev.type === 'Water'
                              ? 'bg-cyan-950 text-cyan-300 border border-cyan-800'
                              : bev.is_double || bev.type === 'Double'
                              ? 'bg-amber-950 text-amber-300 border border-amber-800'
                              : 'bg-zinc-800 text-zinc-300 border border-zinc-700'
                          }`}>
                            {txVal(lang, bev.type || (bev.is_double ? 'Double' : 'Single'))}
                          </span>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        )}

        {/* TAB 4: MAINTENANCE CYCLES & PERCENTAGES */}
        {activeTab === 'maintenance' && (
          <div className={`p-4 border rounded ${theme.surfaceClass} space-y-4`}>
            <div className="text-xs font-bold text-gray-300 uppercase tracking-wider border-b border-gray-800 pb-2 flex items-center space-x-1.5">
              <Wrench className="w-4 h-4 text-sky-400" />
              <span>{t('maintTitle')}</span>
            </div>

            {!statsData ? (
              <div className="p-8 text-center space-y-4 font-mono">
                <div className="w-14 h-14 rounded-full bg-black/40 border border-[#FCEE09]/30 flex items-center justify-center mx-auto text-[#FCEE09]">
                  <Wrench className="w-7 h-7 animate-pulse" />
                </div>
                <div className="space-y-1">
                  <h3 className="text-sm font-bold text-white uppercase tracking-wider">
                    {t('maintEmptyTitle')}
                  </h3>
                  <p className="text-xs text-zinc-400 max-w-md mx-auto">
                    {t('maintEmptyDesc', { port: selectedPort || t('serialPortFallback') })}
                  </p>
                </div>
                <div className="pt-1">
                  <button
                    onClick={runFullInterrogation}
                    disabled={isInterrogating || !selectedPort}
                    className="px-5 py-2.5 bg-[#FCEE09] hover:bg-yellow-300 text-black font-mono font-bold text-xs uppercase tracking-wider rounded transition-colors disabled:opacity-50"
                  >
                    {isInterrogating ? t('btnReadingEeprom') : t('btnInterrogateShort')}
                  </button>
                </div>
              </div>
            ) : (
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                {/* Wear Percentages */}
                <div className="p-3 bg-black/40 border border-gray-800 rounded space-y-3">
                  <div className="text-xs font-bold text-gray-400 uppercase font-mono">
                    {t('maintWearBarsTitle')}
                  </div>

                  {/* Cleaning */}
                  <div className="space-y-1">
                    <div className="flex justify-between text-xs font-mono">
                      <span className="text-gray-300">{t('maintCoffeeClean')}</span>
                      <span className="text-emerald-400 font-bold">
                        {cleanCount != null ? t('maintTotalCycles', { count: cleanCount }) : t('maintNominal')}
                      </span>
                    </div>
                    <div className="w-full h-2 bg-gray-800 rounded-full overflow-hidden">
                      <div
                        className="h-full bg-emerald-500"
                        style={{ width: `${Math.min(100, Math.max(15, (totalPreps ? (totalPreps % 180) / 1.8 : 25)))}%` }}
                      />
                    </div>
                  </div>

                  {/* Descaling */}
                  <div className="space-y-1">
                    <div className="flex justify-between text-xs font-mono">
                      <span className="text-gray-300">{t('maintTbDescaling')}</span>
                      <span className="text-amber-400 font-bold">
                        {decalcCount != null ? t('maintTotalCycles', { count: decalcCount }) : t('maintNominal')}
                      </span>
                    </div>
                    <div className="w-full h-2 bg-gray-800 rounded-full overflow-hidden">
                      <div
                        className="h-full bg-amber-500"
                        style={{ width: `${Math.min(100, Math.max(20, (totalPreps ? (totalPreps % 350) / 3.5 : 40)))}%` }}
                      />
                    </div>
                  </div>

                  {/* Filter */}
                  <div className="space-y-1">
                    <div className="flex justify-between text-xs font-mono">
                      <span className="text-gray-300">{t('maintClarisFilter')}</span>
                      <span className="text-sky-400 font-bold">
                        {filterSw?.ok ? t('maintFilterActive') : t('maintFilterBypass')}
                      </span>
                    </div>
                    <div className="w-full h-2 bg-gray-800 rounded-full overflow-hidden">
                      <div className="h-full bg-sky-500" style={{ width: filterSw?.ok ? '60%' : '0%' }} />
                    </div>
                  </div>
                </div>

                {/* Maintenance Counters */}
                <div className="p-3 bg-black/40 border border-gray-800 rounded space-y-2">
                  <div className="text-xs font-bold text-gray-400 uppercase font-mono mb-2">
                    {t('maintCounterAuditTitle')}
                  </div>
                  <div className="space-y-1.5 font-mono text-xs">
                    {statsData.maintenance && statsData.maintenance.length > 0 ? (
                      statsData.maintenance.map((m, idx) => (
                        <div key={idx} className="flex justify-between py-1 border-b border-gray-800/60 last:border-0">
                          <span className="text-gray-400">{txMaintenanceLabel(lang, m.label || m.name)}:</span>
                          <strong className="text-white">{m.count?.toLocaleString() ?? 0} {t('maintCyclesSuffix')}</strong>
                        </div>
                      ))
                    ) : (
                      <div className="text-zinc-500 text-xs py-2">{t('maintNoRecords')}</div>
                    )}
                  </div>
                </div>
              </div>
            )}
          </div>
        )}

        {/* TAB 5: ALERTS & SYSTEM NOTIFICATIONS */}
        {activeTab === 'alerts' && (
          <div className={`p-4 border rounded ${theme.surfaceClass} space-y-3`}>
            <div className="text-xs font-bold text-gray-300 uppercase tracking-wider border-b border-gray-800 pb-2 flex items-center space-x-1.5">
              <AlertTriangle className="w-4 h-4 text-rose-400" />
              <span>{t('alertsTitle')}</span>
            </div>

            {!statsData ? (
              <div className="p-8 text-center space-y-4 font-mono">
                <div className="w-14 h-14 rounded-full bg-black/40 border border-[#FCEE09]/30 flex items-center justify-center mx-auto text-[#FCEE09]">
                  <AlertTriangle className="w-7 h-7 animate-pulse" />
                </div>
                <div className="space-y-1">
                  <h3 className="text-sm font-bold text-white uppercase tracking-wider">
                    {t('alertsEmptyTitle')}
                  </h3>
                  <p className="text-xs text-zinc-400 max-w-md mx-auto">
                    {t('alertsEmptyDesc', { port: selectedPort || t('serialPortFallback') })}
                  </p>
                </div>
                <div className="pt-1">
                  <button
                    onClick={runFullInterrogation}
                    disabled={isInterrogating || !selectedPort}
                    className="px-5 py-2.5 bg-[#FCEE09] hover:bg-yellow-300 text-black font-mono font-bold text-xs uppercase tracking-wider rounded transition-colors disabled:opacity-50"
                  >
                    {isInterrogating ? t('btnReadingEeprom') : t('btnInterrogateShort')}
                  </button>
                </div>
              </div>
            ) : (
              <div className="space-y-2 text-xs font-mono">
                {statsData.alerts && statsData.alerts.length > 0 ? (
                  statsData.alerts.map((al, idx) => (
                    <div key={idx} className="flex items-center justify-between p-3 bg-black/40 border border-rose-900/60 rounded">
                      <div className="flex items-center space-x-2">
                        <AlertTriangle className="w-4 h-4 text-rose-400" />
                        <span className="font-bold text-rose-300">{al.message || al.title || String(al)}</span>
                      </div>
                      <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-rose-950 text-rose-400 border border-rose-700">
                        {al.severity || 'ALARM'}
                      </span>
                    </div>
                  ))
                ) : (
                  <div className="flex items-center justify-between p-3 bg-black/40 border border-emerald-900/60 rounded">
                    <div className="flex items-center space-x-2">
                      <CheckCircle2 className="w-4 h-4 text-emerald-400" />
                      <span className="font-bold text-emerald-300">{t('alertsReadyNominal')}</span>
                    </div>
                    <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-emerald-950 text-emerald-400 border border-emerald-700">
                      {t('alertsReadyBadge')}
                    </span>
                  </div>
                )}

                <div className="p-3 bg-black/40 border border-gray-800 rounded space-y-1">
                  <div className="text-gray-400 font-bold">{t('alertsHistTitle')}</div>
                  <div className="text-gray-500 text-[11px]">
                    {t('alertsHistDesc', { model: statsData.machine_model || 'Appliance' })}
                  </div>
                </div>
              </div>
            )}
          </div>
        )}

        {/* TAB 6: APPLIANCE IDENTITY & SYSTEM INFO */}
        {activeTab === 'system' && (
          <div className={`p-4 border rounded ${theme.surfaceClass} space-y-4`}>
            <div className="text-xs font-bold text-gray-300 uppercase tracking-wider border-b border-gray-800 pb-2 flex items-center space-x-1.5">
              <Info className="w-4 h-4 text-sky-400" />
              <span>{t('identityTitle')}</span>
            </div>

            {!statsData ? (
              <div className="p-8 text-center space-y-4 font-mono">
                <div className="w-14 h-14 rounded-full bg-black/40 border border-[#FCEE09]/30 flex items-center justify-center mx-auto text-[#FCEE09]">
                  <Info className="w-7 h-7 animate-pulse" />
                </div>
                <div className="space-y-1">
                  <h3 className="text-sm font-bold text-white uppercase tracking-wider">
                    {t('identityEmptyTitle')}
                  </h3>
                  <p className="text-xs text-zinc-400 max-w-md mx-auto">
                    {t('identityEmptyDesc', { port: selectedPort || t('serialPortFallback') })}
                  </p>
                </div>
                <div className="pt-1">
                  <button
                    onClick={runFullInterrogation}
                    disabled={isInterrogating || !selectedPort}
                    className="px-5 py-2.5 bg-[#FCEE09] hover:bg-yellow-300 text-black font-mono font-bold text-xs uppercase tracking-wider rounded transition-colors disabled:opacity-50"
                  >
                    {isInterrogating ? t('btnReadingEeprom') : t('btnInterrogateShort')}
                  </button>
                </div>
              </div>
            ) : (
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4 text-xs font-mono">
                <div className="p-3 bg-black/40 border border-gray-800 rounded space-y-2">
                  <div className="text-gray-500 font-bold uppercase text-[10px]">{t('electronicIdentity')}</div>
                  <div className="flex justify-between py-1 border-b border-gray-800/60">
                    <span className="text-gray-400">{t('lblMachineModel')}</span>
                    <strong className="text-white">{statsData?.machine_model || '---'}</strong>
                  </div>
                  <div className="flex justify-between py-1 border-b border-gray-800/60">
                    <span className="text-gray-400">{t('lblFirmwareString')}</span>
                    <strong className="text-sky-400">{statsData?.firmware_string || '---'}</strong>
                  </div>
                  <div className="flex justify-between py-1 border-b border-gray-800/60">
                    <span className="text-gray-400">{t('lblEfCode')}</span>
                    <strong className="text-amber-400">{statsData?.ef_code || '---'}</strong>
                  </div>
                  <div className="flex justify-between py-1">
                    <span className="text-gray-400">{t('lblProtocolMode')}</span>
                    <strong className="text-emerald-400">{statsData?.protocol_mode || '---'}</strong>
                  </div>
                </div>

                <div className="p-3 bg-black/40 border border-gray-800 rounded space-y-2">
                  <div className="text-gray-500 font-bold uppercase text-[10px]">{t('electricalSpecs')}</div>
                  <div className="flex justify-between py-1 border-b border-gray-800/60">
                    <span className="text-gray-400">{t('lblPowerRating')}</span>
                    <strong className="text-white">{statsData?.power_spec || '---'}</strong>
                  </div>
                  <div className="flex justify-between py-1 border-b border-gray-800/60">
                    <span className="text-gray-400">{t('lblSerialEan')}</span>
                    <strong className="text-white">{statsData?.serial_number || '---'}</strong>
                  </div>
                  <div className="flex justify-between py-1 border-b border-gray-800/60">
                    <span className="text-gray-400">{t('lblRawHz')}</span>
                    <strong className="text-gray-400 truncate max-w-[200px]">{liveData?.raw_status || '---'}</strong>
                  </div>
                  <div className="flex justify-between py-1">
                    <span className="text-gray-400">{t('lblActivePort')}</span>
                    <strong className="text-white">{selectedPort}</strong>
                  </div>
                </div>
              </div>
            )}
          </div>
        )}

        {/* TAB 7: COMMAND INJECTOR (SAFE UART WIRE INJECTION) */}
        {activeTab === 'bus_log' && (
          <div className="space-y-3">
            <div className={`p-4 border rounded ${theme.surfaceClass} space-y-3`}>
              <div className="text-xs font-bold text-gray-300 uppercase tracking-wider flex items-center space-x-1.5">
                <Send className="w-4 h-4 text-sky-400" />
                <span>{t('injectorTitle')}</span>
              </div>

              {/* Quick Preset Buttons */}
              <div className="flex flex-wrap gap-1.5 text-xs font-mono">
                {['TY:', 'HZ:', 'AS:', 'CS:', 'IC:', 'RT:', 'RE:0028'].map((cmd) => (
                  <button
                    key={cmd}
                    onClick={() => handleTransmitCommand(cmd)}
                    className="px-2.5 py-1 bg-gray-800 hover:bg-gray-700 text-sky-300 font-bold rounded border border-gray-700"
                  >
                    {cmd}
                  </button>
                ))}
              </div>

              {/* Custom Input */}
              <div className="flex items-center space-x-2">
                <input
                  type="text"
                  value={txCommand}
                  onChange={(e) => setTxCommand(e.target.value)}
                  placeholder={t('injectorPlaceholder')}
                  className="flex-1 px-3 py-1.5 bg-black/40 border border-gray-800 rounded text-xs text-white font-mono outline-none"
                />
                <button
                  onClick={() => handleTransmitCommand()}
                  className="px-4 py-1.5 bg-sky-600 hover:bg-sky-500 text-white font-bold text-xs rounded font-mono"
                >
                  {t('btnSendWireCmd')}
                </button>
              </div>

              {/* Response Log */}
              {txResponseHistory.length > 0 && (
                <div className="space-y-1 pt-2 border-t border-gray-800 font-mono text-xs">
                  <div className="text-gray-500 text-[10px] uppercase font-bold">{t('txHistoryTitle')}</div>
                  {txResponseHistory.map((h, i) => (
                    <div key={i} className="flex justify-between p-1.5 bg-black/40 border border-gray-800/60 rounded">
                      <span className="text-sky-300">TX: <strong>{h.cmd}</strong></span>
                      <span className="text-emerald-400 font-bold">RX: {h.reply}</span>
                      <span className="text-gray-500 text-[10px]">{h.timestamp}</span>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        )}

        {/* TAB 8: MEM MAPPER (EEPROM REGISTER MATRIX & RAW SENSORS) */}
        {activeTab === 'mem_mapper' && (
          <MemMapperTab
            theme={theme}
            selectedPort={selectedPort}
            liveData={liveData}
            aiEnabled={aiEnabled}
            aiModel={aiModel}
            onToggleAi={handleToggleAi}
            beginAiWork={beginAiWork}
            endAiWork={endAiWork}
            onSweepStateChange={setIsHardwareBusy}
          />
        )}

        {/* TAB 9: FIRMWARE INSPECTOR (ELF32, APK & MCU BINARY INSPECTOR / AUDITOR) */}
        {activeTab === 'hmi_tools' && (
          <HmiInspectorTab
            theme={theme}
            lang={lang}
            aiEnabled={aiEnabled}
            onToggleAi={handleToggleAi}
            onGlobalModelChange={(m) => setAiModel(m)}
            beginAiWork={beginAiWork}
            endAiWork={endAiWork}
          />
        )}
      </main>

      {/* ==================================================================== */}
      {/* ZONE 5: EXPORT MODAL DIALOG */}
      {/* ==================================================================== */}
      {showExportModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm p-4">
          <div className={`w-full max-w-lg p-5 border rounded-lg shadow-2xl ${theme.panelBg} ${theme.border} space-y-4 max-h-[90vh] overflow-y-auto`}>
            <div className="flex items-center justify-between border-b border-gray-800 pb-2">
              <span className="text-sm font-bold text-white flex items-center space-x-2">
                <Download className="w-4 h-4 text-sky-400" />
                <span>{t('exportModalTitle')}</span>
              </span>
              <button onClick={() => setShowExportModal(false)} className="text-gray-400 hover:text-white">
                <X className="w-4 h-4" />
              </button>
            </div>

            <div className="space-y-2 text-xs">
              <p className="text-gray-300">
                {t('exportModalDesc')}
              </p>

              {exportStatus.msg && (
                <div className={`p-2.5 rounded text-xs font-mono border ${exportStatus.error ? 'bg-red-950/50 border-red-800 text-red-300' : 'bg-emerald-950/50 border-emerald-800 text-emerald-300'} flex items-center justify-between gap-2`}>
                  <div className="flex items-center gap-2 truncate">
                    {exportStatus.loading && <RefreshCw className="w-3.5 h-3.5 animate-spin text-sky-400 shrink-0" />}
                    {!exportStatus.loading && !exportStatus.error && <Check className="w-3.5 h-3.5 text-emerald-400 shrink-0" />}
                    <span className="truncate">{exportStatus.msg}</span>
                  </div>
                  {browserDownloadAvailable && (
                    <button
                      onClick={() => {
                        if (browserDownloadAvailable.bundle) {
                          triggerBrowserDownload(browserDownloadAvailable.bundle, browserDownloadAvailable.filename);
                        } else if (browserDownloadAvailable.content) {
                          triggerBrowserDownload(browserDownloadAvailable.content, browserDownloadAvailable.filename, browserDownloadAvailable.mime);
                        }
                      }}
                      className="text-[10px] text-sky-300 underline font-bold shrink-0 hover:text-white cursor-pointer"
                    >
                      {t('downloadNow')}
                    </button>
                  )}
                </div>
              )}

              <button
                onClick={() => handleTriggerExport('json')}
                disabled={exportStatus.loading || isDumping}
                className="w-full flex items-center justify-between p-3 bg-black/40 hover:bg-white/5 disabled:opacity-50 border border-gray-800 rounded text-left transition-colors cursor-pointer"
              >
                <div>
                  <div className="font-bold text-sky-300">{t('exportJsonTitle')}</div>
                  <div className="text-[11px] text-gray-500">{t('exportJsonDesc')}</div>
                </div>
                <Download className="w-4 h-4 text-gray-400" />
              </button>

              <button
                onClick={() => handleTriggerExport('csv')}
                disabled={exportStatus.loading || isDumping}
                className="w-full flex items-center justify-between p-3 bg-black/40 hover:bg-white/5 disabled:opacity-50 border border-gray-800 rounded text-left transition-colors cursor-pointer"
              >
                <div>
                  <div className="font-bold text-emerald-300">{t('exportCsvTitle')}</div>
                  <div className="text-[11px] text-gray-500">{t('exportCsvDesc')}</div>
                </div>
                <Download className="w-4 h-4 text-gray-400" />
              </button>

              <button
                onClick={() => handleTriggerExport('text')}
                disabled={exportStatus.loading || isDumping}
                className="w-full flex items-center justify-between p-3 bg-black/40 hover:bg-white/5 disabled:opacity-50 border border-gray-800 rounded text-left transition-colors cursor-pointer"
              >
                <div>
                  <div className="font-bold text-amber-300">{t('exportTxtTitle')}</div>
                  <div className="text-[11px] text-gray-500">{t('exportTxtDesc')}</div>
                </div>
                <Download className="w-4 h-4 text-gray-400" />
              </button>

              <div className="pt-3 border-t border-gray-800">
                <div className="text-[11px] font-semibold text-purple-400 uppercase tracking-wider mb-2 flex items-center justify-between">
                  <span className="flex items-center gap-1.5">
                    <Sparkles className="w-3.5 h-3.5 text-purple-400" />
                    {t('remoteCaptureTitle')}
                  </span>
                  {capturedBundle && (
                    <button
                      onClick={() => {
                        setCapturedBundle(null);
                        setCapturedId('');
                        setCapturedFilename('');
                        setUploadResult(null);
                        setBrowserDownloadAvailable(null);
                        setOffsetCalibration(null);
                        setOffsetAppliedLocally(false);
                      }}
                      className="text-[10px] text-gray-500 hover:text-gray-300 underline cursor-pointer"
                    >
                      {t('btnNewCapture')}
                    </button>
                  )}
                </div>
                <div className="p-3 bg-purple-950/20 border border-purple-800/40 rounded-lg space-y-3">
                  <div>
                    <div className="font-bold text-purple-300 flex items-center justify-between">
                      <span>{t('fullDumpTitle')}</span>
                      {isDumping && <span className="text-[10px] text-purple-400 animate-pulse font-mono">{t('sweepingEeprom')}</span>}
                    </div>
                    <div className="text-[11px] text-gray-400 mt-0.5">
                      {t('fullDumpDesc')}
                    </div>
                  </div>

                  {!capturedBundle && (
                    <>
                      <div className="pt-1 border-t border-purple-900/30">
                        <label className="block text-[11px] text-gray-300 font-medium mb-1">
                          {t('attachJoeCsv')}
                        </label>
                        <input
                          type="file"
                          accept=".csv,.txt"
                          onChange={handleJoeFileUpload}
                          className="w-full text-[11px] text-gray-400 file:mr-2 file:py-1 file:px-2.5 file:rounded file:border-0 file:text-[11px] file:font-medium file:bg-purple-900/50 file:text-purple-300 hover:file:bg-purple-800/60 cursor-pointer"
                        />
                        {joeFileName && (
                          <div className="space-y-1.5 mt-1">
                            <div className="text-[10px] text-emerald-400 flex items-center gap-1 font-mono">
                              <Check className="w-3 h-3 text-emerald-400" />
                              <span>{t('attachedFile', { file: joeFileName })}</span>
                            </div>
                            <label className="flex items-center space-x-1.5 text-[11px] text-gray-300 cursor-pointer">
                              <input
                                type="checkbox"
                                checked={aiEnabled && useAiJoeMatch}
                                onChange={(e) => {
                                  const checked = e.target.checked;
                                  if (checked && !aiEnabled) {
                                    handleToggleAi(true);
                                  }
                                  setUseAiJoeMatch(checked);
                                }}
                                className="rounded bg-black/60 border-zinc-700 text-purple-500"
                              />
                              <span>{t('useAiJoeMatchLabel')}</span>
                            </label>
                          </div>
                        )}
                      </div>

                      <button
                        onClick={handleTriggerDumpCapture}
                        disabled={isDumping || isCalibratingOffsets || exportStatus.loading || !selectedPort}
                        className="w-full mt-2 py-2.5 px-3 bg-purple-600 hover:bg-purple-500 disabled:opacity-50 text-white font-medium text-xs rounded flex items-center justify-center gap-2 transition-colors shadow-sm cursor-pointer"
                      >
                        <Sparkles className="w-4 h-4" />
                        <span>{isDumping ? t('btnSweepingBundle') : t('btnCaptureBundle')}</span>
                      </button>

                      {joeFileName && (
                        <button
                          onClick={() => handleCalibrateOffsetsFromJoe(true)}
                          disabled={isDumping || isCalibratingOffsets || exportStatus.loading || !selectedPort}
                          className="w-full py-2 px-3 bg-cyan-950/80 hover:bg-cyan-900/80 border border-cyan-500/70 disabled:opacity-50 text-cyan-300 font-bold text-xs rounded flex items-center justify-center gap-2 transition-colors cursor-pointer"
                        >
                          <Sparkles className="w-3.5 h-3.5" />
                          <span>{isCalibratingOffsets ? t('btnAnalyzingOffsets') : t('btnSweepAutoFix')}</span>
                        </button>
                      )}
                    </>
                  )}

                  {capturedBundle && (
                    <div className="space-y-3 pt-1">
                      {/* Bundle summary chip */}
                      <div className="p-2 bg-black/40 border border-purple-800/50 rounded flex items-center justify-between text-[11px]">
                        <div>
                          <div className="text-purple-300 font-bold flex items-center gap-1">
                            <Check className="w-3.5 h-3.5 text-emerald-400" />
                            <span>{t('bundleReadyTitle', { model: capturedBundle?.identity?.model_name || 'Machine' })}</span>
                          </div>
                          <div className="text-gray-400 font-mono text-[10px]">
                            {t('bundleSummaryLine', {
                              words: Object.keys(capturedBundle?.eeprom_words || {}).length,
                              joe: capturedBundle?.joe_ground_truth?.raw_lines?.length ? t('joeAttached') : t('joeNone'),
                            })}
                          </div>
                        </div>
                      </div>

                      {/* Destination Option 0: Local AI Offset Fixer & Immediate Calibration */}
                      {(capturedBundle?.joe_ground_truth?.raw_lines?.length > 0 || joeCsvContent) && (
                        <div className="p-2.5 bg-cyan-950/20 border border-cyan-800/50 rounded space-y-2">
                          <div className="flex items-center justify-between">
                            <span className="font-bold text-cyan-300 text-xs flex items-center gap-1.5">
                              <Sparkles className="w-3.5 h-3.5" />
                              <span>{t('offsetFixerTitle')}</span>
                            </span>
                            <button
                              type="button"
                              onClick={() => handleToggleAi(!aiEnabled)}
                              className={`px-2 py-0.5 rounded text-[10px] font-bold border ${
                                aiEnabled
                                  ? 'bg-red-950/60 hover:bg-red-900/70 text-red-300 border-red-700'
                                  : 'bg-zinc-800 hover:bg-zinc-700 text-zinc-300 border-zinc-600'
                              }`}
                            >
                              {aiEnabled ? t('btnTurnAiOff') : t('btnEnableAiOff')}
                            </button>
                          </div>
                          <p className="text-[11px] text-gray-400">
                            {t('offsetFixerDesc')}
                          </p>
                          <div className="flex flex-wrap gap-2">
                            <button
                              type="button"
                              onClick={() => handleCalibrateOffsetsFromJoe(false)}
                              disabled={!aiEnabled || isCalibratingOffsets}
                              className="flex-1 py-1.5 px-2.5 bg-cyan-700 hover:bg-cyan-600 disabled:opacity-40 text-white font-bold text-[11px] rounded cursor-pointer"
                            >
                              {isCalibratingOffsets ? t('btnCalibrating') : offsetCalibration ? t('btnRerunAiCalib') : t('btnAiMatchJoe')}
                            </button>
                            {offsetCalibration && (
                              <button
                                type="button"
                                onClick={handleApplyOffsetFixLocally}
                                className={`flex-1 py-1.5 px-2.5 font-extrabold text-[11px] rounded cursor-pointer ${
                                  offsetAppliedLocally
                                    ? 'bg-emerald-700 text-white'
                                    : 'bg-[#FCEE09] hover:bg-yellow-400 text-black'
                                }`}
                              >
                                {offsetAppliedLocally ? t('btnFixedLocallyNow') : t('btnFixLocallyNow')}
                              </button>
                            )}
                          </div>

                          {offsetCalibration && (
                            <div className="max-h-36 overflow-y-auto bg-black/50 border border-zinc-800 rounded p-2 space-y-1 font-mono text-[10px]">
                              <div className="text-zinc-300 font-bold">
                                {t('matchedLine', {
                                  products: offsetCalibration.products?.length || 0,
                                  maintenance: offsetCalibration.maintenance?.length || 0,
                                  pct: offsetCalibration.maintenance_pct?.length || 0,
                                })}
                              </div>
                              {(offsetCalibration.products || []).slice(0, 12).map((p, idx) => (
                                <div key={idx} className="flex justify-between text-zinc-400 border-b border-zinc-800/60 py-0.5">
                                  <span className="truncate pr-2">{p.name}{p.is_double ? ' [2x]' : ''}</span>
                                  <span className="text-cyan-400 shrink-0">{p.addr_hex} = {p.eeprom_val}</span>
                                </div>
                              ))}
                            </div>
                          )}
                        </div>
                      )}

                      {/* Destination Option 1: Save Locally */}
                      <div className="p-2.5 bg-black/30 border border-gray-800 rounded space-y-2">
                        <div className="flex items-center justify-between">
                          <span className="font-bold text-gray-200 text-xs">{t('dest1Title')}</span>
                          <span className="text-[10px] px-1.5 py-0.5 bg-purple-900/50 text-purple-300 rounded uppercase font-mono">{t('dest1Badge')}</span>
                        </div>
                        <p className="text-[11px] text-gray-400">{t('dest1Desc')}</p>
                        <button
                          onClick={handleSaveLocally}
                          disabled={exportStatus.loading}
                          className="w-full py-2 px-3 bg-sky-600 hover:bg-sky-500 disabled:opacity-50 text-white font-medium text-xs rounded flex items-center justify-center gap-2 transition-colors cursor-pointer"
                        >
                          <Download className="w-3.5 h-3.5" />
                          <span>{t('btnSaveLocallyDialog')}</span>
                        </button>
                        <div className="flex justify-end pt-0.5">
                          <button
                            onClick={() => triggerBrowserDownload(capturedBundle, capturedFilename)}
                            className="text-[10px] text-sky-400 hover:text-sky-300 underline cursor-pointer"
                          >
                            {t('btnDownloadBrowser')}
                          </button>
                        </div>
                      </div>

                      {/* Destination Option 2: Upload to Community Repository */}
                      <div className="p-2.5 bg-black/30 border border-gray-800 rounded space-y-2">
                        <div className="flex items-center justify-between">
                          <span className="font-bold text-gray-200 text-xs">{t('dest2Title')}</span>
                          <span className="text-[10px] text-gray-400 font-mono">Pr0xyA-91/spectra-captures</span>
                        </div>
                        <p className="text-[11px] text-gray-400">{t('dest2Desc')}</p>

                        {/* GitHub Auth Status Header */}
                        <div className="p-2 bg-zinc-900/70 border border-zinc-800 rounded text-[11px] flex items-center justify-between">
                          <div className="flex items-center gap-1.5">
                            <Github className="w-3.5 h-3.5 text-gray-400" />
                            {githubAuth.authenticated ? (
                              <span className="text-emerald-400 font-mono">
                                {t('ghSignedInAs', { login: githubAuth.login })}
                              </span>
                            ) : (
                              <span className="text-amber-400">{t('ghNotSignedIn')}</span>
                            )}
                          </div>
                          {githubAuth.authenticated ? (
                            <button
                              onClick={handleLogout}
                              className="text-[10px] text-gray-400 hover:text-rose-400 flex items-center gap-1 cursor-pointer"
                              title={t('ghSignOut')}
                            >
                              <LogOut className="w-3 h-3" />
                              <span>{t('ghSignOut')}</span>
                            </button>
                          ) : (
                            <div className="flex items-center gap-2">
                              {githubAuth.device_flow_available && (
                                <button
                                  onClick={handleStartDeviceFlow}
                                  className="text-[10px] text-sky-400 hover:text-sky-300 font-medium underline cursor-pointer"
                                >
                                  {t('ghDeviceCode')}
                                </button>
                              )}
                              <button
                                onClick={() => setShowPatInput(!showPatInput)}
                                className="text-[10px] text-sky-400 hover:text-sky-300 font-medium underline cursor-pointer"
                              >
                                {showPatInput ? t('ghCancel') : t('ghAccessToken')}
                              </button>
                            </div>
                          )}
                        </div>

                        {/* Device Flow in Progress */}
                        {deviceFlow && (
                          <div className="p-2.5 bg-sky-950/40 border border-sky-800/60 rounded space-y-2 text-xs">
                            <div className="text-[11px] text-sky-300 font-medium">{t('ghAuthorizeTitle')}</div>
                            <div className="flex items-center justify-between bg-black/60 p-2 rounded border border-sky-900">
                              <span className="font-mono text-sm font-bold text-sky-200 tracking-wider">{deviceFlow.user_code}</span>
                              <button
                                onClick={() => handleCopyDeviceCode(deviceFlow.user_code)}
                                className="px-2 py-1 bg-sky-800/80 hover:bg-sky-700 text-sky-200 rounded text-[10px] flex items-center gap-1 cursor-pointer"
                              >
                                {copiedCode ? <Check className="w-3 h-3 text-emerald-400" /> : <Copy className="w-3 h-3" />}
                                <span>{copiedCode ? t('ghCopied') : t('ghCopy')}</span>
                              </button>
                            </div>
                            <div className="flex items-center justify-between text-[11px]">
                              <a
                                href={deviceFlow.verification_uri}
                                target="_blank"
                                rel="noreferrer"
                                className="text-sky-400 hover:text-sky-300 underline flex items-center gap-1 font-medium"
                              >
                                <span>{t('ghOpenDeviceUrl')}</span>
                                <ExternalLink className="w-3 h-3" />
                              </a>
                              <button
                                onClick={() => setDeviceFlow(null)}
                                className="text-[10px] text-gray-400 hover:text-gray-200 cursor-pointer"
                              >
                                {t('ghCancel')}
                              </button>
                            </div>
                            <div className="text-[10px] text-gray-400 flex items-center gap-1.5 animate-pulse">
                              <RefreshCw className="w-3 h-3 animate-spin text-sky-400" />
                              <span>{t('ghWaitingAuth')}</span>
                            </div>
                          </div>
                        )}

                        {/* PAT Input Box */}
                        {showPatInput && !githubAuth.authenticated && (
                          <div className="p-2.5 bg-black/50 border border-zinc-700 rounded space-y-2 text-xs">
                            <label className="block text-[11px] text-gray-300 font-medium">
                              {t('ghPatLabel')}
                            </label>
                            <div className="flex gap-1.5">
                              <input
                                type="password"
                                value={patInput}
                                onChange={(e) => setPatInput(e.target.value)}
                                placeholder="ghp_... or github_pat_..."
                                className="flex-1 bg-zinc-900 border border-zinc-700 rounded px-2 py-1 text-xs text-white font-mono placeholder:text-zinc-600 focus:outline-none focus:border-sky-500"
                              />
                              <button
                                onClick={handleSavePat}
                                disabled={!patInput.trim()}
                                className="px-3 py-1 bg-sky-600 hover:bg-sky-500 disabled:opacity-50 text-white rounded font-medium text-xs cursor-pointer"
                              >
                                {t('ghConnect')}
                              </button>
                            </div>
                          </div>
                        )}

                        {/* Upload Button */}
                        <button
                          onClick={handleUploadToCommunity}
                          disabled={!githubAuth.authenticated || isUploading}
                          className="w-full py-2 px-3 bg-purple-600 hover:bg-purple-500 disabled:opacity-40 disabled:hover:bg-purple-600 text-white font-medium text-xs rounded flex items-center justify-center gap-2 transition-colors cursor-pointer disabled:cursor-not-allowed shadow-sm"
                        >
                          <Upload className="w-3.5 h-3.5" />
                          <span>{isUploading ? t('btnUploadingCommunity') : (githubAuth.authenticated ? t('btnUploadCommunity') : t('btnUploadCommunityNeedSignIn'))}</span>
                        </button>

                        {/* Upload Success Banner */}
                        {uploadResult?.success && (
                          <div className="p-2 bg-emerald-950/60 border border-emerald-800 rounded text-[11px] text-emerald-300 flex items-center justify-between">
                            <span className="flex items-center gap-1.5">
                              <Check className="w-3.5 h-3.5 text-emerald-400" />
                              <span>{t('uploadSuccessMsg')}</span>
                            </span>
                            {uploadResult.url && (
                              <a
                                href={uploadResult.url}
                                target="_blank"
                                rel="noreferrer"
                                className="underline text-emerald-200 hover:text-white flex items-center gap-1 font-mono font-bold"
                              >
                                <span>{t('viewIssue')}</span>
                                <ExternalLink className="w-3 h-3" />
                              </a>
                            )}
                          </div>
                        )}

                        {/* Unauthenticated fallback link */}
                        <div className="flex items-center justify-between pt-1 text-[10px] text-gray-500 border-t border-gray-800/50">
                          <span>{t('preferManualSubmit')}</span>
                          <a
                            href="https://github.com/Pr0xyA-91/spectra-captures/issues/new"
                            target="_blank"
                            rel="noreferrer"
                            className="text-purple-400 hover:text-purple-300 underline flex items-center gap-1"
                          >
                            <span>{t('openSubmissionBrowser')}</span>
                            <ExternalLink className="w-2.5 h-2.5" />
                          </a>
                        </div>
                      </div>
                    </div>
                  )}
                </div>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* ==================================================================== */}
      {/* ZONE 5b: CONFIGURATION & AI MODEL / GITHUB MANAGER MODAL */}
      {/* ==================================================================== */}
      <ConfigModal
        isOpen={showConfigModal}
        onClose={() => setShowConfigModal(false)}
        theme={theme}
        lang={lang}
        onChangeLang={setLang}
        initialSection={configInitialSection}
        onLaunchGuide={handleLaunchGuideFromConfig}
        showGuideOnStartup={showGuideOnStartup}
        onToggleGuideOnStartup={handleSetGuideOnStartup}
        aiEnabled={aiEnabled}
        aiModel={aiModel}
        aiSystem={aiSystem}
        aiDownload={aiDownload}
        autoUnload={aiAutoUnload}
        statsData={statsData}
        onStatsUpdated={(s) => setStatsData(s)}
        onToggleAi={(nextEnabled) => handleToggleAi(nextEnabled)}
        onSaveAiConfig={handleSaveAiConfig}
        onRefreshAiStatus={fetchAiGlobalStatus}
        githubAuth={githubAuth}
        deviceFlow={deviceFlow}
        patInput={patInput}
        setPatInput={setPatInput}
        copiedCode={copiedCode}
        authStatusMsg={exportStatus}
        onStartDeviceFlow={handleStartDeviceFlow}
        onSavePat={handleSavePat}
        onLogout={handleLogout}
        onCancelDeviceFlow={() => setDeviceFlow(null)}
        onCopyDeviceCode={handleCopyDeviceCode}
        updateInfo={updateInfo}
        updateProgress={updateProgress}
        isCheckingUpdates={isCheckingUpdates}
        isReconnectingAfterUpdate={isReconnectingAfterUpdate}
        onCheckUpdates={checkForUpdates}
        onStartUpdate={startSelfUpdate}
        onCancelUpdate={cancelSelfUpdate}
      />

      {/* ==================================================================== */}
      {/* ZONE 5b-ii: NO LOCAL AI MODEL INSTALLED PROMPT MODAL */}
      {/* ==================================================================== */}
      {showNoModelPromptModal && (
        <div className="fixed inset-0 z-[60] flex items-center justify-center bg-black/80 backdrop-blur-sm p-4">
          <div className={`w-full max-w-md border-2 border-[#00F0FF]/70 ${theme.panelBg} rounded-xl shadow-2xl overflow-hidden font-mono text-xs`}>
            <div className="flex items-center justify-between px-4 py-3 bg-[#14141c] border-b border-zinc-800">
              <div className="flex items-center gap-2">
                <Cpu className="w-4 h-4 text-[#00F0FF]" />
                <span className="font-extrabold text-white uppercase tracking-wider">
                  {t('aiNoModelModalTitle')}
                </span>
              </div>
              <button
                type="button"
                onClick={() => setShowNoModelPromptModal(false)}
                className="text-zinc-400 hover:text-white p-1 rounded hover:bg-zinc-800 cursor-pointer"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            <div className="p-4 space-y-3">
              <p className="text-zinc-300 leading-relaxed">
                {t('aiNoModelModalDesc')}
              </p>

              <div className="p-3 bg-black/50 border border-zinc-800 rounded space-y-2">
                <div className="flex items-center justify-between text-[11px]">
                  <span className="text-zinc-400 font-bold">{t('aiNoModelRecLabel')}</span>
                  <span className="text-cyan-400 font-bold">
                    {aiSystem?.hardware?.recommended_model || 'qwen2.5:0.5b'}
                  </span>
                </div>
                <select
                  value={noModelPromptChoice || aiSystem?.hardware?.recommended_model || 'qwen2.5:0.5b'}
                  onChange={(e) => setNoModelPromptChoice(e.target.value)}
                  className="w-full bg-zinc-950 border border-zinc-700 rounded px-2.5 py-2 text-xs text-white outline-none focus:border-[#00F0FF]"
                >
                  {(Array.isArray(aiSystem?.hardware?.model_catalog) && aiSystem.hardware.model_catalog.length > 0
                    ? aiSystem.hardware.model_catalog
                    : [
                        { id: 'qwen2.5:0.5b', name: 'Qwen 2.5 0.5B (Ultra-Light)', disk_mb: 398, is_recommended: true },
                        { id: 'gemma3:1b', name: 'Gemma 3 1B (Google Ultra-Light)', disk_mb: 815 },
                        { id: 'qwen2.5:1.5b', name: 'Qwen 2.5 1.5B (Balanced)', disk_mb: 986 },
                        { id: 'gemma3:4b', name: 'Gemma 3 4B (Google Vision + Text)', disk_mb: 3400 },
                      ]
                  ).map((m) => (
                    <option key={m.id} value={m.id}>
                      {m.name} [{m.id}]{m.disk_mb ? ` (~${m.disk_mb} MB)` : ''}{m.is_recommended ? ` ★ ${t('cfgRecommendedTag')}` : ''}
                    </option>
                  ))}
                </select>
              </div>
            </div>

            <div className="px-4 py-3 bg-[#101016] border-t border-zinc-800 flex flex-wrap items-center justify-between gap-2">
              <button
                type="button"
                onClick={() => {
                  setShowNoModelPromptModal(false);
                  setConfigInitialSection('ai');
                  setShowConfigModal(true);
                }}
                className="px-2.5 py-1.5 bg-zinc-900 hover:bg-zinc-800 border border-zinc-700 text-zinc-300 rounded font-bold cursor-pointer flex items-center gap-1"
              >
                <Settings className="w-3.5 h-3.5 text-[#FCEE09]" />
                <span>{t('aiNoModelBtnOpenConfig')}</span>
              </button>

              <div className="flex items-center gap-2 ml-auto">
                <button
                  type="button"
                  onClick={() => setShowNoModelPromptModal(false)}
                  className="px-2.5 py-1.5 bg-zinc-900 hover:bg-zinc-800 border border-zinc-700 text-zinc-300 rounded cursor-pointer"
                >
                  {t('cfgBtnKeepCurrentModel')}
                </button>
                <button
                  type="button"
                  onClick={() =>
                    handleStartPullFromNoModelPrompt(
                      noModelPromptChoice || aiSystem?.hardware?.recommended_model || 'qwen2.5:0.5b'
                    )
                  }
                  className="px-3 py-1.5 bg-[#00F0FF] hover:bg-cyan-300 text-black font-extrabold rounded flex items-center gap-1.5 cursor-pointer"
                >
                  <Download className="w-3.5 h-3.5" />
                  <span>
                    {t('aiNoModelBtnDownloadAndEnable', {
                      model: noModelPromptChoice || aiSystem?.hardware?.recommended_model || 'qwen2.5:0.5b',
                    })}
                  </span>
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* ==================================================================== */}
      {/* ZONE 5c: INTERACTIVE FIRST-RUN & REFRESHER WALKTHROUGH GUIDE */}
      {/* ==================================================================== */}
      <InteractiveGuideModal
        isOpen={showGuideModal}
        onClose={handleCloseGuide}
        theme={theme}
        lang={lang}
        onChangeLang={setLang}
        showOnStartup={startupGuideCheckbox}
        onSetShowOnStartup={(checked) => setStartupGuideCheckbox(Boolean(checked))}
        hasStats={Boolean(statsData)}
        isInterrogating={isInterrogating}
        onSelectDemoPort={() => {
          const demo = availablePorts.find((p) => p.toUpperCase().includes('DEMO')) || 'DEMO / SIMULATION';
          setSelectedPort(demo);
          setHardwareError(null);
          querySensors(true, demo);
        }}
        onRunInterrogate={() => {
          if (!selectedPort) {
            const demo = availablePorts.find((p) => p.toUpperCase().includes('DEMO')) || 'DEMO / SIMULATION';
            setSelectedPort(demo);
          }
          runFullInterrogation();
        }}
        onSwitchTab={(tabId) => setActiveTab(tabId)}
        onOpenConfig={(section = 'ai') => {
          setConfigInitialSection(section);
          setShowConfigModal(true);
        }}
        onJumpToOffsetCalibrator={() => {
          setActiveTab('overview');
          if (!aiEnabled) {
            handleToggleAi(true);
          }
        }}
      />

      {/* ==================================================================== */}
      {/* ZONE 6: FOOTER STATUS BAR */}
      {/* ==================================================================== */}
      <footer className={`px-4 py-2 border-t ${theme.border} ${theme.headerBg} text-[11px] text-gray-400 flex flex-wrap items-center justify-between gap-2`}>
        <div className="flex items-center space-x-2">
          <span className={`w-2 h-2 rounded-full ${isConnected ? 'bg-emerald-400' : 'bg-gray-500'}`} />
          <span className="font-mono text-gray-300">{connectionStatusText}</span>
        </div>
        <div className="flex items-center space-x-4 font-mono text-[10px] text-gray-500">
          <span>TB1: {coffeeTemp != null ? `${coffeeTemp.toFixed(1)}°C` : '---'}</span>
          <span>{lang === 'cs' ? 'PRŮTOK' : 'FLOW'}: {flowRate != null ? `${flowRate.toFixed(1)} ml/s` : '---'}</span>
          <span>BU: {buPos != null ? `${buPos} tk` : '---'}</span>
          <span>{t('footerPoll')} {isPolling ? '1.1s' : t('footerPollOff')}</span>
          <span>{t('footerTimestamp')} {lastTimestamp || '---'}</span>
        </div>
      </footer>
    </div>
  );
}
