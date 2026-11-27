import React, { useState, useEffect, useRef, useCallback, useMemo, Suspense } from 'react';
import { Zap, AlertTriangle, Database, Download, X } from 'lucide-react';

import AiStatusBar from './AiStatusBar';
import ErrorBoundary from './ErrorBoundary';
import DiagnosticAdvisorTab from './DiagnosticAdvisorTab';
import { createTranslator } from '../i18n/translations';
import { THEMES, computeSpectraActivity } from './workspace/workspaceHelpers';
import { useSelfUpdater } from './workspace/useSelfUpdater';
import { useOffsetDbSync } from './workspace/useOffsetDbSync';
import { useGlobalAiControl } from './workspace/useGlobalAiControl';
import { useHardwareTelemetry } from './workspace/useHardwareTelemetry';
import { useExportAndGithub } from './workspace/useExportAndGithub';
import WorkspaceHeader from './workspace/WorkspaceHeader';
import KpiRibbon from './workspace/KpiRibbon';
import {
  BeveragesTabView,
  MaintenanceTabView,
  AlertsTabView,
  SystemIdentityTabView,
  CommandInjectorTabView,
} from './workspace/TelemetryTabsView';

export { THEMES };
export const FALLBACK_BUILD = '20261127.1905';

const SensorsTabView = React.lazy(() => import('./workspace/SensorsTabView'));
const MemMapperTab = React.lazy(() => import('./MemMapperTab'));
const HmiInspectorTab = React.lazy(() => import('./HmiInspectorTab'));
const ExportCaptureModal = React.lazy(() => import('./workspace/ExportCaptureModal'));
const NoAiModelPromptModal = React.lazy(() => import('./workspace/NoAiModelPromptModal'));
const ConfigModal = React.lazy(() => import('./ConfigModal'));
const InteractiveGuideModal = React.lazy(() => import('./InteractiveGuideModal'));
const UserGuideModal = React.lazy(() => import('./UserGuideModal'));
const IssueReportModal = React.lazy(() => import('./IssueReportModal'));

const TabSuspenseFallback = (
  <div className="p-8 text-center text-xs font-mono text-zinc-400 animate-pulse">
    Loading module...
  </div>
);

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
  const t = useMemo(() => createTranslator(lang), [lang]);
  const langRef = useRef(lang);
  langRef.current = lang;
  const theme = THEMES.cyberpunk;
  const WORKSPACE_TABS = useMemo(() => [
    { id: 'overview', label: t('tabOverview') },
    { id: 'sensors', label: t('tabSensors') },
    { id: 'beverages', label: t('tabBeverages') },
    { id: 'maintenance', label: t('tabMaintenance') },
    { id: 'alerts', label: t('tabAlerts') },
    { id: 'system', label: t('tabSystem') },
    { id: 'bus_log', label: t('tabBusLog') },
    { id: 'mem_mapper', label: t('tabMemMapper') },
    { id: 'hmi_tools', label: t('tabHmiTools') },
  ], [t]);

  const [liveBuild, setLiveBuild] = useState(debugSummary?.build || '');
  const [bootReady, setBootReady] = useState(false);
  const serverBootIdRef = useRef('');

  // Top-level workspace UI states
  const [activeTab, setActiveTab] = useState('overview');
  const [isHardwareBusy, setIsHardwareBusy] = useState(false);
  const [bevSearch, setBevSearch] = useState('');
  const [aiServiceSummary, setAiServiceSummary] = useState(null);

  // Modal visibility states
  const [showExportModal, setShowExportModal] = useState(false);
  const [showIssueModal, setShowIssueModal] = useState(false);
  const [isReportingIssue, setIsReportingIssue] = useState(false);
  const [showConfigModal, setShowConfigModal] = useState(false);
  const [configInitialSection, setConfigInitialSection] = useState('ai');
  const [showGuideOnStartup, setShowGuideOnStartup] = useState(false);
  const [showGuideModal, setShowGuideModal] = useState(false);
  const [showUserGuideModal, setShowUserGuideModal] = useState(false);
  const [startupGuideCheckbox, setStartupGuideCheckbox] = useState(false);

  useEffect(() => {
    const timer = setTimeout(() => setBootReady(true), 150);
    return () => clearTimeout(timer);
  }, []);

  // Version & Onboarding Preferences Bootstrap
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
        if (d?.boot_id) serverBootIdRef.current = d.boot_id;
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

  // 1. Self-Updater Hook
  const {
    updateInfo,
    updateProgress,
    isCheckingUpdates,
    isReconnectingAfterUpdate,
    checkForUpdates,
    startSelfUpdate,
    cancelSelfUpdate,
  } = useSelfUpdater({ t, serverBootIdRef });

  // 2. Global Local AI Lifecycle Hook (Default: strictly OFF)
  const handleOpenAiConfigSection = useCallback(() => {
    setConfigInitialSection('ai');
    setShowConfigModal(true);
  }, []);

  const {
    aiEnabled,
    aiModel,
    setAiModel,
    aiTask,
    aiDownload,
    aiSystem,
    aiAutoUnload,
    aiBusyCount,
    showNoModelPromptModal,
    setShowNoModelPromptModal,
    noModelPromptChoice,
    setNoModelPromptChoice,
    fetchAiGlobalStatus,
    handleSaveAiConfig,
    handleToggleAi,
    handleStartPullFromNoModelPrompt,
    beginAiWork,
    endAiWork,
  } = useGlobalAiControl({
    onOpenAiConfig: handleOpenAiConfigSection,
  });

  // 3. Hardware Connection, Polling, Interrogation & UART Command Injection Hook
  const {
    availablePorts,
    selectedPort,
    setSelectedPort,
    activePortRef,
    pollFailCountRef,
    isConnected,
    isPolling,
    setIsPolling,
    isInterrogating,
    hardwareError,
    setHardwareError,
    connectionStatusText,
    lastTimestamp,
    liveData,
    setLiveData,
    statsData,
    setStatsData,
    interrogationProgress,
    interrogationStage,
    busEvents,
    setBusEvents,
    isStreamPaused,
    setIsStreamPaused,
    txCommand,
    setTxCommand,
    txResponseHistory,
    querySensors,
    fetchPorts,
    runFullInterrogation,
    handleTransmitCommand,
  } = useHardwareTelemetry({ lang, langRef });

  const liveDataRef = useRef(liveData);
  liveDataRef.current = liveData;

  // 3b. Ed25519 Signed Machine Offset DB Sync Hook (Read-Only Check + Explicit 1-Click Sync)
  const {
    offsetDbStatus,
    offsetDbCheck,
    isCheckingOffsetDb,
    isSyncingOffsetDb,
    offsetDbSyncNotice,
    offsetDbBannerDismissed,
    setOffsetDbBannerDismissed,
    checkOffsetDbUpdates,
    syncOffsetDb,
  } = useOffsetDbSync({ onStatsUpdated: setStatsData });

  // 4. Export, Remote Capture, J.O.E. AI Calibration & GitHub Community Auth Hook
  const {
    exportPrefix,
    setExportPrefix,
    joeCsvContent,
    joeFileName,
    isDumping,
    exportStatus,
    capturedBundle,
    capturedFilename,
    browserDownloadAvailable,
    githubAuth,
    deviceFlow,
    setDeviceFlow,
    showPatInput,
    setShowPatInput,
    patInput,
    setPatInput,
    isUploading,
    uploadResult,
    copiedCode,
    useAiJoeMatch,
    setUseAiJoeMatch,
    isCalibratingOffsets,
    offsetCalibration,
    offsetAppliedLocally,
    handleCancelDeviceFlow,
    handleTriggerExport,
    handleJoeFileUpload,
    handleTriggerDumpCapture,
    handleCalibrateOffsetsFromJoe,
    handleApplyOffsetFixLocally,
    handleSaveLocally,
    handleUploadToCommunity,
    handleStartDeviceFlow,
    handleSavePat,
    handleLogout,
    handleCopyDeviceCode,
    handleResetCapture,
  } = useExportAndGithub({
    selectedPort,
    aiEnabled,
    aiModel,
    handleToggleAi,
    beginAiWork,
    endAiWork,
    setStatsData,
    showExportModal,
    setShowExportModal,
    showConfigModal,
    showIssueModal,
  });

  // Auto-Polling Timer (paused when tab hidden or hardware busy with sweep/dump/calibration)
  useEffect(() => {
    if (!isPolling || !selectedPort || isInterrogating || isDumping || isCalibratingOffsets || isHardwareBusy) return;
    const interval = setInterval(() => {
      if (document.visibilityState === 'hidden') return;
      querySensors(true, null, true);
    }, 1100);
    const handleVisibility = () => {
      if (document.visibilityState === 'visible') {
        querySensors(true, null, true);
      }
    };
    document.addEventListener('visibilitychange', handleVisibility);
    return () => {
      clearInterval(interval);
      document.removeEventListener('visibilitychange', handleVisibility);
    };
  }, [isPolling, selectedPort, isInterrogating, isDumping, isCalibratingOffsets, isHardwareBusy, querySensors]);

  // Onboarding & Modal Navigation Callbacks
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

  const handleOpenServiceReport = useCallback((includeAiSummary = false) => {
    const port = activePortRef.current;
    if (!port) return;
    const aiParam = includeAiSummary && aiEnabled ? '&ai_summary=1' : '';
    window.open(
      `/api/service_report?port=${encodeURIComponent(port)}&lang=${encodeURIComponent(langRef.current)}${aiParam}`,
      '_blank',
      'noopener,noreferrer'
    );
  }, [aiEnabled, activePortRef]);

  const handleOpenExportModal = useCallback(() => setShowExportModal(true), []);
  const handleOpenConfigModal = useCallback((section = 'ai') => {
    setConfigInitialSection(typeof section === 'string' ? section : 'ai');
    setShowConfigModal(true);
  }, []);
  const handleCloseConfigModal = useCallback(() => setShowConfigModal(false), []);
  const handleCloseIssueModal = useCallback(() => setShowIssueModal(false), []);
  const handleOpenGithubConfigFromIssue = useCallback(() => {
    setConfigInitialSection('github');
    setShowConfigModal(true);
  }, []);
  const handleSelectDemoPortFromGuide = useCallback(() => {
    const demo = availablePorts.find((p) => p.toUpperCase().includes('DEMO')) || 'DEMO / SIMULATION';
    activePortRef.current = demo;
    setSelectedPort(demo);
    setHardwareError(null);
    querySensors(true, demo);
  }, [availablePorts, activePortRef, setSelectedPort, setHardwareError, querySensors]);
  const handleRunInterrogateFromGuide = useCallback(() => {
    if (!activePortRef.current) {
      const demo = availablePorts.find((p) => p.toUpperCase().includes('DEMO')) || 'DEMO / SIMULATION';
      activePortRef.current = demo;
      setSelectedPort(demo);
    }
    runFullInterrogation();
  }, [availablePorts, activePortRef, setSelectedPort, runFullInterrogation]);
  const handleJumpToOffsetCalibrator = useCallback(() => {
    setActiveTab('overview');
    if (!aiEnabled) {
      handleToggleAi(true);
    }
  }, [aiEnabled, handleToggleAi]);
  const handleSetGuideCheckboxFromGuide = useCallback((checked) => {
    setStartupGuideCheckbox(Boolean(checked));
  }, []);

  const handleOpenUpdates = useCallback((forceCheck) => {
    setConfigInitialSection('updates');
    setShowConfigModal(true);
    if (forceCheck !== null) checkForUpdates(forceCheck);
  }, [checkForUpdates]);

  const handleOpenOffsetDb = useCallback(() => {
    setConfigInitialSection('library');
    setShowConfigModal(true);
  }, []);

  const handleSelectPort = useCallback((newPort) => {
    activePortRef.current = newPort;
    setSelectedPort(newPort);
    setHardwareError(null);
    setBusEvents([]);
    setLiveData({ switches: [], sensors: [], telemetry: {}, alerts: [] });
    querySensors(true, newPort);
  }, [activePortRef, setSelectedPort, setHardwareError, setBusEvents, setLiveData, querySensors]);

  const handleRefreshPorts = useCallback(() => fetchPorts(true), [fetchPorts]);
  const handleQuerySensorsClick = useCallback(() => querySensors(true), [querySensors]);
  const handleOpenServiceReportDefault = useCallback(() => handleOpenServiceReport(false), [handleOpenServiceReport]);
  const handleOpenFirmwareInspector = useCallback(() => setActiveTab('hmi_tools'), []);
  const handleOpenUserGuide = useCallback(() => setShowUserGuideModal(true), []);
  const handleCloseUserGuide = useCallback(() => setShowUserGuideModal(false), []);
  const handleOpenIssueModal = useCallback(() => setShowIssueModal(true), []);
  const handleCloseExportModal = useCallback(() => {
    setShowExportModal(false);
    setPatInput('');
    setShowPatInput(false);
  }, [setPatInput, setShowPatInput]);
  const handleTurnAiOff = useCallback(() => handleToggleAi(false), [handleToggleAi]);
  const handleDismissOffsetDbBanner = useCallback(() => setOffsetDbBannerDismissed(true), [setOffsetDbBannerDismissed]);
  const handleCloseNoModelPrompt = useCallback(() => setShowNoModelPromptModal(false), [setShowNoModelPromptModal]);
  const handleOpenInteractiveTourFromUserGuide = useCallback(() => {
    setStartupGuideCheckbox(showGuideOnStartup);
    setShowGuideModal(true);
  }, [showGuideOnStartup]);

  // Derived Telemetry Values (EMPTY until machine is read)
  const effectiveBuild = liveBuild || debugSummary?.build || FALLBACK_BUILD;
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
  const beverages = statsData?.beverages;
  const filteredBeverages = useMemo(() => {
    const list = beverages || [];
    const q = bevSearch.toLowerCase();
    return list.filter(
      (b) =>
        q === '' ||
        (b.name || '').toLowerCase().includes(q) ||
        (b.type || '').toLowerCase().includes(q) ||
        String(b.code || '').includes(bevSearch)
    );
  }, [beverages, bevSearch]);

  // Live SPECTRA Application Activity Indicator
  const spectraActivity = computeSpectraActivity({
    t,
    isReconnectingAfterUpdate,
    updateProgress,
    isInterrogating,
    interrogationProgress,
    interrogationStage,
    selectedPort,
    isDumping,
    isHardwareBusy,
    aiDownload,
    aiTask,
    aiBusyCount,
    isCalibratingOffsets,
    isUploading,
    isReportingIssue,
    exportStatus,
    isCheckingUpdates,
    hardwareError,
    isConnected,
    isPolling,
    connectionStatusText,
  });

  return (
    <div className={`min-h-screen flex flex-col justify-between ${theme.bg} ${theme.font} transition-opacity duration-300 ${bootReady ? 'opacity-100' : 'opacity-0'} select-none ${theme.isScanline ? 'cyber-scanlines' : ''}`}>
      {/* ZONE 1: TOP BRANDING & HARDWARE CONNECTION BAR */}
      <WorkspaceHeader
        theme={theme}
        t={t}
        effectiveBuild={effectiveBuild}
        spectraActivity={spectraActivity}
        updateInfo={updateInfo}
        isCheckingUpdates={isCheckingUpdates}
        onOpenUpdates={handleOpenUpdates}
        offsetDbCheck={offsetDbCheck}
        onOpenOffsetDb={handleOpenOffsetDb}
        selectedPort={selectedPort}
        availablePorts={availablePorts}
        onSelectPort={handleSelectPort}
        onRefreshPorts={handleRefreshPorts}
        onQuerySensors={handleQuerySensorsClick}
        isPolling={isPolling}
        setIsPolling={setIsPolling}
        isInterrogating={isInterrogating}
        interrogationProgress={interrogationProgress}
        onRunInterrogation={runFullInterrogation}
        statsData={statsData}
        onOpenServiceReport={handleOpenServiceReportDefault}
        onOpenExportModal={handleOpenExportModal}
        activeTab={activeTab}
        onOpenFirmwareInspector={handleOpenFirmwareInspector}
        aiEnabled={aiEnabled}
        aiModel={aiModel}
        aiTask={aiTask}
        onToggleAi={handleToggleAi}
        onOpenConfig={handleOpenAiConfigSection}
        onOpenUserGuide={handleOpenUserGuide}
        scaleMode={scaleMode}
        setScaleMode={setScaleMode}
        currentScale={currentScale}
        isDebugOpen={isDebugOpen}
        setIsDebugOpen={setIsDebugOpen}
        debugCounts={debugCounts}
        onOpenIssueModal={handleOpenIssueModal}
      />

      {/* GLOBAL AI PROGRESS & KILL-SWITCH STATUS BAR */}
      <AiStatusBar
        lang={lang}
        aiEnabled={aiEnabled}
        aiTask={aiTask}
        aiDownload={aiDownload}
        onTurnAiOff={handleTurnAiOff}
      />

      {/* SIGNED MACHINE OFFSET DB UPDATE NOTIFICATION BANNER (Explicit 1-Click Sync, Never Silent) */}
      {offsetDbCheck?.update_available && !offsetDbBannerDismissed && (
        <div className="bg-purple-950/85 border-b border-purple-500/60 px-4 py-2 flex flex-wrap items-center justify-between gap-2 text-xs font-mono text-purple-100 backdrop-blur">
          <div className="flex flex-wrap items-center gap-2 min-w-0">
            <Database className="w-4 h-4 text-purple-300 shrink-0" />
            <span className="font-extrabold text-white">
              {t('offsetDbBannerTitle', { version: offsetDbCheck.latest_version || 'new' })}
            </span>
            {offsetDbCheck.added_machines?.length > 0 && (
              <span className="text-[11px] text-emerald-300">
                + {t('offsetDbAddedLabel')}:{' '}
                {offsetDbCheck.added_machines
                  .map((m) => `${m.model_family}${m.ef_code ? ` [${m.ef_code}]` : ''}`)
                  .join(', ')}
              </span>
            )}
            {offsetDbCheck.updated_machines?.length > 0 && (
              <span className="text-[11px] text-cyan-300">
                ↻ {t('offsetDbUpdatedLabel')}:{' '}
                {offsetDbCheck.updated_machines
                  .map((m) => `${m.model_family}${m.ef_code ? ` [${m.ef_code}]` : ''}`)
                  .join(', ')}
              </span>
            )}
          </div>
          <div className="flex items-center gap-2 shrink-0">
            <button
              type="button"
              disabled={isSyncingOffsetDb}
              onClick={syncOffsetDb}
              className="flex items-center space-x-1.5 px-3 py-1 bg-emerald-500 hover:bg-emerald-400 disabled:opacity-50 text-black font-extrabold rounded text-[11px] cursor-pointer transition-colors shadow-[0_0_10px_rgba(16,185,129,0.45)]"
            >
              <Download className="w-3.5 h-3.5" />
              <span>{isSyncingOffsetDb ? t('offsetDbBtnSyncing') : t('offsetDbBtnSync')}</span>
            </button>
            <button
              type="button"
              onClick={handleDismissOffsetDbBanner}
              className="p-1 text-purple-300 hover:text-white rounded cursor-pointer"
              title="Dismiss"
            >
              <X className="w-3.5 h-3.5" />
            </button>
          </div>
        </div>
      )}

      {/* HIGH-VISIBILITY PROGRESS BAR FIELD DURING MACHINE DATA PULL */}
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

      {/* ZONE 2: 9 REAL-TIME UNIFIED HARDWARE & STATS KPI TILES */}
      <KpiRibbon
        theme={theme}
        lang={lang}
        t={t}
        hasTelem={hasTelem}
        telem={telem}
        statsData={statsData}
        totalPreps={totalPreps}
        totalCups={totalCups}
        coffeeTemp={coffeeTemp}
        buPos={buPos}
        buUpper={buUpper}
        flowRate={flowRate}
        beansOk={beansOk}
        tankSw={tankSw}
        traySw={traySw}
        beansSw={beansSw}
        cleanCount={cleanCount}
        decalcCount={decalcCount}
      />

      {/* ZONE 3: MAIN NAVIGATION TABS */}
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

      {/* ZONE 4: TAB CONTENT CONTAINER */}
      <main className="flex-1 p-4 overflow-y-auto">
        {activeTab === 'overview' && (
          <ErrorBoundary variant="panel" onReset={() => setActiveTab('overview')}>
            <DiagnosticAdvisorTab
              theme={theme}
              lang={lang}
              statsData={statsData}
              liveDataRef={liveDataRef}
              machineModel={liveData?.machine_model || ''}
              selectedPort={selectedPort}
              onOpenServiceReport={handleOpenServiceReport}
              onOpenExport={handleOpenExportModal}
              onInterrogate={runFullInterrogation}
              isInterrogating={isInterrogating}
              aiEnabled={aiEnabled}
              aiModel={aiModel}
              onToggleAi={handleToggleAi}
              beginAiWork={beginAiWork}
              endAiWork={endAiWork}
              aiServiceSummary={aiServiceSummary}
              setAiServiceSummary={setAiServiceSummary}
              onStatsUpdated={setStatsData}
              onOpenConfig={handleOpenConfigModal}
            />
          </ErrorBoundary>
        )}

        {activeTab === 'sensors' && (
          <ErrorBoundary variant="panel" onReset={() => setActiveTab('overview')}>
            <Suspense fallback={TabSuspenseFallback}>
              <SensorsTabView
                theme={theme}
                lang={lang}
                t={t}
                liveData={liveData}
                statsData={statsData}
                selectedPort={selectedPort}
                effectiveBuild={effectiveBuild}
                telem={telem}
                beansOk={beansOk}
                opticalDelta={opticalDelta}
                busEvents={busEvents}
                setBusEvents={setBusEvents}
                isStreamPaused={isStreamPaused}
                setIsStreamPaused={setIsStreamPaused}
              />
            </Suspense>
          </ErrorBoundary>
        )}

        {activeTab === 'beverages' && (
          <BeveragesTabView
            theme={theme}
            lang={lang}
            t={t}
            statsData={statsData}
            selectedPort={selectedPort}
            isInterrogating={isInterrogating}
            onRunInterrogation={runFullInterrogation}
            bevSearch={bevSearch}
            setBevSearch={setBevSearch}
            filteredBeverages={filteredBeverages}
            totalPreps={totalPreps}
          />
        )}

        {activeTab === 'maintenance' && (
          <MaintenanceTabView
            theme={theme}
            lang={lang}
            t={t}
            statsData={statsData}
            selectedPort={selectedPort}
            isInterrogating={isInterrogating}
            onRunInterrogation={runFullInterrogation}
            cleanCount={cleanCount}
            decalcCount={decalcCount}
            totalPreps={totalPreps}
            filterSw={filterSw}
          />
        )}

        {activeTab === 'alerts' && (
          <AlertsTabView
            theme={theme}
            t={t}
            statsData={statsData}
            selectedPort={selectedPort}
            isInterrogating={isInterrogating}
            onRunInterrogation={runFullInterrogation}
          />
        )}

        {activeTab === 'system' && (
          <SystemIdentityTabView
            theme={theme}
            t={t}
            statsData={statsData}
            liveData={liveData}
            selectedPort={selectedPort}
            isInterrogating={isInterrogating}
            onRunInterrogation={runFullInterrogation}
          />
        )}

        {activeTab === 'bus_log' && (
          <CommandInjectorTabView
            theme={theme}
            t={t}
            txCommand={txCommand}
            setTxCommand={setTxCommand}
            txResponseHistory={txResponseHistory}
            onTransmitCommand={handleTransmitCommand}
          />
        )}

        {activeTab === 'mem_mapper' && (
          <ErrorBoundary variant="panel" onReset={() => setActiveTab('overview')}>
            <Suspense fallback={TabSuspenseFallback}>
              <MemMapperTab
                theme={theme}
                selectedPort={selectedPort}
                liveDataRef={liveDataRef}
                machineModel={liveData?.machine_model || ''}
                aiEnabled={aiEnabled}
                aiModel={aiModel}
                onToggleAi={handleToggleAi}
                beginAiWork={beginAiWork}
                endAiWork={endAiWork}
                onSweepStateChange={setIsHardwareBusy}
              />
            </Suspense>
          </ErrorBoundary>
        )}

        {activeTab === 'hmi_tools' && (
          <ErrorBoundary variant="panel" onReset={() => setActiveTab('overview')}>
            <Suspense fallback={TabSuspenseFallback}>
              <HmiInspectorTab
                theme={theme}
                lang={lang}
                aiEnabled={aiEnabled}
                onToggleAi={handleToggleAi}
                onGlobalModelChange={setAiModel}
                beginAiWork={beginAiWork}
                endAiWork={endAiWork}
              />
            </Suspense>
          </ErrorBoundary>
        )}
      </main>

      {/* ZONE 5: EXPORT MODAL DIALOG */}
      {showExportModal && (
        <ErrorBoundary variant="panel" onReset={handleCloseExportModal}>
          <Suspense fallback={null}>
            <ExportCaptureModal
              show={showExportModal}
              onClose={handleCloseExportModal}
              theme={theme}
              t={t}
              statsData={statsData}
              selectedPort={selectedPort}
              exportPrefix={exportPrefix}
              setExportPrefix={setExportPrefix}
              exportStatus={exportStatus}
              browserDownloadAvailable={browserDownloadAvailable}
              isDumping={isDumping}
              isCalibratingOffsets={isCalibratingOffsets}
              onTriggerExport={handleTriggerExport}
              capturedBundle={capturedBundle}
              capturedFilename={capturedFilename}
              onResetCapture={handleResetCapture}
              joeFileName={joeFileName}
              joeCsvContent={joeCsvContent}
              onJoeFileUpload={handleJoeFileUpload}
              aiEnabled={aiEnabled}
              useAiJoeMatch={useAiJoeMatch}
              setUseAiJoeMatch={setUseAiJoeMatch}
              onToggleAi={handleToggleAi}
              onTriggerDumpCapture={handleTriggerDumpCapture}
              onCalibrateOffsetsFromJoe={handleCalibrateOffsetsFromJoe}
              offsetCalibration={offsetCalibration}
              offsetAppliedLocally={offsetAppliedLocally}
              onApplyOffsetFixLocally={handleApplyOffsetFixLocally}
              onSaveLocally={handleSaveLocally}
              githubAuth={githubAuth}
              deviceFlow={deviceFlow}
              setDeviceFlow={setDeviceFlow}
              showPatInput={showPatInput}
              setShowPatInput={setShowPatInput}
              patInput={patInput}
              setPatInput={setPatInput}
              isUploading={isUploading}
              uploadResult={uploadResult}
              copiedCode={copiedCode}
              onStartDeviceFlow={handleStartDeviceFlow}
              onSavePat={handleSavePat}
              onLogout={handleLogout}
              onCopyDeviceCode={handleCopyDeviceCode}
              onUploadToCommunity={handleUploadToCommunity}
            />
          </Suspense>
        </ErrorBoundary>
      )}

      {/* ZONE 5b: CONFIGURATION & AI MODEL / GITHUB MANAGER MODAL */}
      {showConfigModal && (
        <ErrorBoundary variant="panel" onReset={handleCloseConfigModal}>
          <Suspense fallback={null}>
            <ConfigModal
              isOpen={showConfigModal}
              onClose={handleCloseConfigModal}
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
              onStatsUpdated={setStatsData}
              onToggleAi={handleToggleAi}
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
              onCancelDeviceFlow={handleCancelDeviceFlow}
              onCopyDeviceCode={handleCopyDeviceCode}
              updateInfo={updateInfo}
              updateProgress={updateProgress}
              isCheckingUpdates={isCheckingUpdates}
              isReconnectingAfterUpdate={isReconnectingAfterUpdate}
              onCheckUpdates={checkForUpdates}
              onStartUpdate={startSelfUpdate}
              onCancelUpdate={cancelSelfUpdate}
              offsetDbStatus={offsetDbStatus}
              offsetDbCheck={offsetDbCheck}
              isCheckingOffsetDb={isCheckingOffsetDb}
              isSyncingOffsetDb={isSyncingOffsetDb}
              offsetDbSyncNotice={offsetDbSyncNotice}
              onCheckOffsetDb={checkOffsetDbUpdates}
              onSyncOffsetDb={syncOffsetDb}
            />
          </Suspense>
        </ErrorBoundary>
      )}

      {/* ZONE 5b-ii: NO LOCAL AI MODEL INSTALLED PROMPT MODAL */}
      {showNoModelPromptModal && (
        <ErrorBoundary variant="panel" onReset={handleCloseNoModelPrompt}>
          <Suspense fallback={null}>
            <NoAiModelPromptModal
              show={showNoModelPromptModal}
              theme={theme}
              t={t}
              aiSystem={aiSystem}
              noModelPromptChoice={noModelPromptChoice}
              setNoModelPromptChoice={setNoModelPromptChoice}
              onClose={handleCloseNoModelPrompt}
              onOpenConfig={handleOpenAiConfigSection}
              onStartPull={handleStartPullFromNoModelPrompt}
            />
          </Suspense>
        </ErrorBoundary>
      )}

      {/* ZONE 5c: INTERACTIVE FIRST-RUN & REFRESHER WALKTHROUGH GUIDE */}
      {showGuideModal && (
        <ErrorBoundary variant="panel" onReset={handleCloseGuide}>
          <Suspense fallback={null}>
            <InteractiveGuideModal
              isOpen={showGuideModal}
              onClose={handleCloseGuide}
              theme={theme}
              lang={lang}
              onChangeLang={setLang}
              showOnStartup={startupGuideCheckbox}
              onSetShowOnStartup={handleSetGuideCheckboxFromGuide}
              hasStats={Boolean(statsData)}
              isInterrogating={isInterrogating}
              onSelectDemoPort={handleSelectDemoPortFromGuide}
              onRunInterrogate={handleRunInterrogateFromGuide}
              onSwitchTab={setActiveTab}
              onOpenConfig={handleOpenConfigModal}
              onJumpToOffsetCalibrator={handleJumpToOffsetCalibrator}
            />
          </Suspense>
        </ErrorBoundary>
      )}

      {/* ZONE 5c-ii: BUILT-IN ILLUSTRATED USER GUIDE MODAL (EN + CS) */}
      {showUserGuideModal && (
        <ErrorBoundary variant="panel" onReset={handleCloseUserGuide}>
          <Suspense fallback={null}>
            <UserGuideModal
              isOpen={showUserGuideModal}
              onClose={handleCloseUserGuide}
              theme={theme}
              lang={lang}
              onOpenInteractiveTour={handleOpenInteractiveTourFromUserGuide}
            />
          </Suspense>
        </ErrorBoundary>
      )}

      {/* ZONE 5d: REPORT ISSUE TO GITHUB MODAL */}
      {showIssueModal && (
        <ErrorBoundary variant="panel" onReset={handleCloseIssueModal}>
          <Suspense fallback={null}>
            <IssueReportModal
              isOpen={showIssueModal}
              onClose={handleCloseIssueModal}
              theme={theme}
              lang={lang}
              githubAuth={githubAuth}
              statsData={statsData}
              liveData={liveData}
              selectedPort={selectedPort}
              liveBuild={effectiveBuild}
              offsetDbVersion={offsetDbStatus?.offset_db_version || ''}
              onOpenGitHubConfig={handleOpenGithubConfigFromIssue}
              onSubmittingChange={setIsReportingIssue}
            />
          </Suspense>
        </ErrorBoundary>
      )}

      {/* ZONE 6: FOOTER STATUS BAR */}
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
