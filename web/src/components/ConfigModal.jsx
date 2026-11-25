import React, { useState, useEffect, useCallback, useMemo } from 'react';
import {
  Settings,
  X,
  Cpu,
  Download,
  RefreshCw,
  Github,
  Sliders,
  Database,
  Globe,
  Compass
} from 'lucide-react';
import { createTranslator, SUPPORTED_LANGUAGES } from '../i18n/translations';
import LocalAiSection from './config/LocalAiSection';
import MachineLibrarySection from './config/MachineLibrarySection';
import GitHubAuthSection from './config/GitHubAuthSection';
import CalibrationSection from './config/CalibrationSection';
import SoftwareUpdateSection from './config/SoftwareUpdateSection';

function ConfigModal({
  isOpen,
  onClose,
  theme,
  lang = 'en',
  onChangeLang = () => {},
  initialSection = 'ai',
  onLaunchGuide = null,
  showGuideOnStartup = false,
  onToggleGuideOnStartup = null,
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
  onCopyDeviceCode,
  updateInfo = null,
  updateProgress = {},
  isCheckingUpdates = false,
  isReconnectingAfterUpdate = false,
  onCheckUpdates = null,
  onStartUpdate = null,
  onCancelUpdate = null,
  offsetDbStatus = null,
  offsetDbCheck = null,
  isCheckingOffsetDb = false,
  isSyncingOffsetDb = false,
  offsetDbSyncNotice = null,
  onCheckOffsetDb = null,
  onSyncOffsetDb = null,
}) {
  const t = useMemo(() => createTranslator(lang), [lang]);
  const [activeSection, setActiveSection] = useState('ai');
  const [pullModelInput, setPullModelInput] = useState('gemma3:1b');
  const [ollamaBusy, setOllamaBusy] = useState(false);
  const [isPullPolling, setIsPullPolling] = useState(false);
  const [pendingUnpulledModel, setPendingUnpulledModel] = useState(null);
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
    if (initialSection) setActiveSection(initialSection);
    if (onRefreshAiStatus) onRefreshAiStatus();
    loadOverridesAndCalib();
    loadMachineLibrary();
  }, [isOpen, initialSection, onRefreshAiStatus, loadOverridesAndCalib, loadMachineLibrary]);
  // Note: active AI download/task polling is handled centrally by SpectraWorkspace.jsx

  useEffect(() => {
    if (!isPullPolling) return;
    if (!aiDownload?.active && ['COMPLETED', 'ERROR', 'CANCELLED'].includes(aiDownload?.status)) {
      setIsPullPolling(false);
      if (aiDownload.status === 'COMPLETED') {
        const pulledModel = aiDownload.model || pullModelInput;
        setPendingUnpulledModel(null);
        if (pulledModel && onSaveAiConfig) {
          onSaveAiConfig({ model: pulledModel, auto_unload: autoUnload });
        }
        setStatusBanner({
          msg: aiDownload.status_text || t('cfgMsgModelReady', { model: pulledModel }),
          error: false,
        });
      } else if (aiDownload.status === 'ERROR') {
        setStatusBanner({
          msg: aiDownload.error || aiDownload.status_text || t('cfgMsgInstallFailed'),
          error: true,
        });
      } else if (aiDownload.status === 'CANCELLED') {
        setStatusBanner({ msg: t('cfgMsgDlCancelled'), error: true });
      }
    }
  }, [aiDownload, isPullPolling, pullModelInput, autoUnload, onSaveAiConfig, t]);

  useEffect(() => {
    if (!isOpen) {
      setPendingUnpulledModel(null);
      if (setPatInput) setPatInput('');
    }
  }, [isOpen, setPatInput]);

  if (!isOpen) return null;

  const ollamaInfo = aiSystem?.ollama || {};
  const hardware = aiSystem?.hardware || {};
  const installedModels = Array.isArray(ollamaInfo.models) ? ollamaInfo.models : [];
  const loadedModels = Array.isArray(ollamaInfo.loaded_models) ? ollamaInfo.loaded_models : [];
  const catalog = Array.isArray(hardware.model_catalog) ? hardware.model_catalog : [];

  const isModelInstalled = (modelId) => {
    const target = (modelId || '').trim();
    if (!target) return false;
    return installedModels.some(
      (ins) => ins === target || ins === `${target}:latest` || ins.startsWith(`${target}:`) || ins.startsWith(target)
    );
  };

  // Combine installed models + catalog entries for the Default Model selector
  const selectableModels = Array.from(
    new Set([
      ...installedModels,
      ...catalog.map((c) => c.id),
      ...(aiModel ? [aiModel] : [])
    ])
  );

  const effectiveDefaultModel =
    pendingUnpulledModel || aiModel || hardware?.default_selected_model || selectableModels[0] || '';
  const promptUnpulledTarget =
    pendingUnpulledModel && !isModelInstalled(pendingUnpulledModel)
      ? pendingUnpulledModel
      : effectiveDefaultModel && !isModelInstalled(effectiveDefaultModel)
      ? effectiveDefaultModel
      : null;
  const promptUnpulledMeta = promptUnpulledTarget
    ? catalog.find((c) => c.id === promptUnpulledTarget)
    : null;

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
    if (!isModelInstalled(nextModel)) {
      setPendingUnpulledModel(nextModel);
      setPullModelInput(nextModel);
      return;
    }
    setPendingUnpulledModel(null);
    if (onSaveAiConfig) {
      await onSaveAiConfig({ model: nextModel, auto_unload: autoUnload });
      setStatusBanner({ msg: t('cfgMsgDefaultModelSet', { model: nextModel }), error: false });
    }
  };

  const handlePullAndUseSelectedModel = async (modelId) => {
    if (!modelId) return;
    setPendingUnpulledModel(null);
    setPullModelInput(modelId);
    if (onSaveAiConfig) {
      await onSaveAiConfig({ model: modelId, auto_unload: autoUnload });
    }
    await runOllamaAction('pull_async', modelId);
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
        setStatusBanner({ msg: t('cfgMsgRemovedOverride', { key }), error: false });
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
        setStatusBanner({ msg: t('cfgMsgSavedThreshold', { val: data.threshold }), error: false });
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
        setStatusBanner({ msg: t('cfgMsgResetThreshold', { val: data.threshold }), error: false });
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
              {t('configTitle')}
            </span>
          </div>
          <button
            onClick={onClose}
            className="text-zinc-400 hover:text-white p-1 rounded hover:bg-zinc-800 cursor-pointer"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Language / Jazyk + Quick Update Check Bar */}
        <div className="flex flex-wrap items-center justify-between gap-2 px-5 py-2 bg-black/50 border-b border-zinc-800/80 text-xs">
          <div className="flex flex-wrap items-center gap-2">
            <div className="flex items-center space-x-2 text-zinc-300 font-bold">
              <Globe className="w-3.5 h-3.5 text-[#00F0FF]" />
              <span>{t('langToggleLabel')}</span>
            </div>
            <div className="flex items-center gap-1.5">
              {SUPPORTED_LANGUAGES.map((l) => {
                const active = lang === l.id;
                return (
                  <button
                    key={l.id}
                    type="button"
                    onClick={() => onChangeLang(l.id)}
                    className={`px-2.5 py-1 rounded font-bold text-[11px] border transition-colors cursor-pointer ${
                      active
                        ? 'bg-[#00F0FF]/20 border-[#00F0FF] text-[#00F0FF]'
                        : 'bg-zinc-900 border-zinc-700 text-zinc-400 hover:text-white'
                    }`}
                  >
                    {l.label} ({l.short})
                  </button>
                );
              })}
            </div>
          </div>

          <div className="flex items-center gap-2">
            {updateInfo?.ok && (
              <span
                className={`text-[10px] px-2 py-0.5 rounded font-bold border ${
                  updateInfo.update_available
                    ? 'bg-emerald-950/70 border-emerald-600 text-emerald-300'
                    : 'bg-zinc-900 border-zinc-700 text-zinc-400'
                }`}
              >
                {updateInfo.update_available
                  ? t('cfgQuickUpdateAvailable', { build: updateInfo.latest_build })
                  : t('cfgQuickUpdateUpToDate')}
              </span>
            )}
            <button
              type="button"
              disabled={isCheckingUpdates || Boolean(updateProgress?.in_progress)}
              onClick={() => {
                setActiveSection('updates');
                if (onCheckUpdates) onCheckUpdates(true);
              }}
              className="flex items-center space-x-1 px-2.5 py-1 rounded font-bold text-[11px] bg-zinc-900 hover:bg-zinc-800 disabled:opacity-50 border border-zinc-700 text-cyan-300 cursor-pointer transition-colors"
            >
              <RefreshCw className={`w-3 h-3 ${isCheckingUpdates ? 'animate-spin' : ''}`} />
              <span>{isCheckingUpdates ? t('cfgUpdatesBtnChecking') : t('cfgQuickUpdateCheck')}</span>
            </button>
            {updateInfo?.update_available && !updateProgress?.in_progress && (
              <button
                type="button"
                onClick={() => {
                  setActiveSection('updates');
                  if (onStartUpdate) onStartUpdate();
                }}
                className="flex items-center space-x-1 px-2.5 py-1 rounded font-extrabold text-[11px] bg-emerald-600 hover:bg-emerald-500 text-black cursor-pointer transition-colors"
              >
                <Download className="w-3 h-3" />
                <span>{t('cfgUpdatesBtnInstall', { build: updateInfo.latest_build })}</span>
              </button>
            )}
          </div>
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
            <span>{t('cfgTabAi')}</span>
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
            <span>{t('cfgTabLibrary', { count: libraryStats.total_machines || machineCatalog.length })}</span>
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
            <span>{t('cfgTabGithub')}</span>
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
            <span>{t('cfgTabCalibration')}</span>
          </button>
          <button
            type="button"
            onClick={() => {
              setActiveSection('updates');
              if (!updateInfo && onCheckUpdates) onCheckUpdates(false);
            }}
            className={`px-3 py-1.5 rounded-t font-bold flex items-center space-x-1.5 border-b-2 transition-colors cursor-pointer ${
              activeSection === 'updates'
                ? 'border-[#00F0FF] text-[#00F0FF] bg-cyan-950/20'
                : 'border-transparent text-zinc-400 hover:text-zinc-200'
            }`}
          >
            <Download className="w-3.5 h-3.5" />
            <span>{t('cfgTabUpdates')}</span>
            {updateInfo?.update_available && (
              <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse" />
            )}
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
          {activeSection === 'ai' && (
            <LocalAiSection
              t={t}
              aiEnabled={aiEnabled}
              aiModel={aiModel}
              aiSystem={aiSystem}
              aiDownload={aiDownload}
              autoUnload={autoUnload}
              ollamaInfo={ollamaInfo}
              hardware={hardware}
              installedModels={installedModels}
              loadedModels={loadedModels}
              catalog={catalog}
              selectableModels={selectableModels}
              effectiveDefaultModel={effectiveDefaultModel}
              promptUnpulledTarget={promptUnpulledTarget}
              promptUnpulledMeta={promptUnpulledMeta}
              pendingUnpulledModel={pendingUnpulledModel}
              setPendingUnpulledModel={setPendingUnpulledModel}
              pullModelInput={pullModelInput}
              setPullModelInput={setPullModelInput}
              ollamaBusy={ollamaBusy}
              isModelInstalled={isModelInstalled}
              onToggleAi={onToggleAi}
              onSaveAiConfig={onSaveAiConfig}
              onRefreshAiStatus={onRefreshAiStatus}
              runOllamaAction={runOllamaAction}
              handleSelectDefaultModel={handleSelectDefaultModel}
              handlePullAndUseSelectedModel={handlePullAndUseSelectedModel}
            />
          )}

          {activeSection === 'library' && (
            <MachineLibrarySection
              t={t}
              libraryStats={libraryStats}
              connectedMatch={connectedMatch}
              librarySearch={librarySearch}
              setLibrarySearch={setLibrarySearch}
              machineCatalog={machineCatalog}
              expandedMachineId={expandedMachineId}
              setExpandedMachineId={setExpandedMachineId}
              isLoadingLibrary={isLoadingLibrary}
              loadMachineLibrary={loadMachineLibrary}
              handleImportPatchFile={handleImportPatchFile}
              handleExportMachinePatch={handleExportMachinePatch}
              offsetDbStatus={offsetDbStatus}
              offsetDbCheck={offsetDbCheck}
              isCheckingOffsetDb={isCheckingOffsetDb}
              isSyncingOffsetDb={isSyncingOffsetDb}
              offsetDbSyncNotice={offsetDbSyncNotice}
              onCheckOffsetDb={onCheckOffsetDb}
              onSyncOffsetDb={onSyncOffsetDb}
            />
          )}

          {activeSection === 'github' && (
            <GitHubAuthSection
              t={t}
              githubAuth={githubAuth}
              deviceFlow={deviceFlow}
              patInput={patInput}
              setPatInput={setPatInput}
              copiedCode={copiedCode}
              authStatusMsg={authStatusMsg}
              onStartDeviceFlow={onStartDeviceFlow}
              onSavePat={onSavePat}
              onLogout={onLogout}
              onCancelDeviceFlow={onCancelDeviceFlow}
              onCopyDeviceCode={onCopyDeviceCode}
            />
          )}

          {activeSection === 'calibration' && (
            <CalibrationSection
              t={t}
              overrideEntries={overrideEntries}
              loadOverridesAndCalib={loadOverridesAndCalib}
              handleDeleteOverride={handleDeleteOverride}
              beanCalib={beanCalib}
              thresholdInput={thresholdInput}
              setThresholdInput={setThresholdInput}
              handleSaveThreshold={handleSaveThreshold}
              handleResetThreshold={handleResetThreshold}
            />
          )}

          {activeSection === 'updates' && (
            <SoftwareUpdateSection
              t={t}
              updateInfo={updateInfo}
              updateProgress={updateProgress}
              isCheckingUpdates={isCheckingUpdates}
              isReconnectingAfterUpdate={isReconnectingAfterUpdate}
              onCheckUpdates={onCheckUpdates}
              onStartUpdate={onStartUpdate}
              onCancelUpdate={onCancelUpdate}
              offsetDbStatus={offsetDbStatus}
              offsetDbCheck={offsetDbCheck}
              isCheckingOffsetDb={isCheckingOffsetDb}
              isSyncingOffsetDb={isSyncingOffsetDb}
              offsetDbSyncNotice={offsetDbSyncNotice}
              onCheckOffsetDb={onCheckOffsetDb}
              onSyncOffsetDb={onSyncOffsetDb}
            />
          )}
        </div>

        {/* Interactive Guide Reminder Footer */}
        {onLaunchGuide && (
          <div className="px-5 py-3 bg-black/60 border-t border-zinc-800 flex flex-wrap items-center justify-between gap-3 text-xs">
            <div className="flex items-start gap-2.5 min-w-0 flex-1">
              <Compass className="w-4 h-4 text-[#FCEE09] shrink-0 mt-0.5" />
              <div className="min-w-0">
                <div className="font-bold text-white text-[11px]">{t('cfgGuideReminderTitle')}</div>
                <div className="text-[10px] text-zinc-400 leading-snug">{t('cfgGuideReminderDesc')}</div>
                {onToggleGuideOnStartup && (
                  <label className="flex items-center space-x-1.5 text-[10px] text-zinc-300 cursor-pointer mt-1.5">
                    <input
                      type="checkbox"
                      checked={Boolean(showGuideOnStartup)}
                      onChange={(e) => onToggleGuideOnStartup(e.target.checked)}
                      className="rounded bg-black border-zinc-700 text-[#00F0FF]"
                    />
                    <span>{t('cfgShowGuideOnStartup')}</span>
                  </label>
                )}
              </div>
            </div>
            <button
              type="button"
              onClick={() => {
                onClose();
                onLaunchGuide();
              }}
              className="px-3 py-1.5 bg-[#FCEE09] hover:bg-yellow-400 text-black font-extrabold rounded text-[11px] shrink-0 cursor-pointer transition-colors"
            >
              {t('cfgBtnLaunchGuide')}
            </button>
          </div>
        )}
      </div>
    </div>
  );
}

export default React.memo(ConfigModal);
