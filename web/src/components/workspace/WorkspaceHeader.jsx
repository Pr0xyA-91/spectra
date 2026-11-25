import React from 'react';
import {
  Zap,
  Play,
  Pause,
  RefreshCw,
  Radio,
  Download,
  FileText,
  Sparkles,
  Box,
  Power,
  Settings,
  BookOpen,
  Flag,
  Database,
} from 'lucide-react';

function WorkspaceHeader({
  theme,
  t,
  effectiveBuild,
  spectraActivity,
  updateInfo,
  isCheckingUpdates,
  onOpenUpdates,
  offsetDbCheck,
  onOpenOffsetDb,
  selectedPort,
  availablePorts,
  onSelectPort,
  onRefreshPorts,
  onQuerySensors,
  isPolling,
  setIsPolling,
  isInterrogating,
  interrogationProgress,
  onRunInterrogation,
  statsData,
  onOpenServiceReport,
  onOpenExportModal,
  activeTab,
  onOpenFirmwareInspector,
  aiEnabled,
  aiModel,
  aiTask,
  onToggleAi,
  onOpenConfig,
  onOpenUserGuide,
  scaleMode,
  setScaleMode,
  currentScale,
  isDebugOpen,
  setIsDebugOpen,
  debugCounts,
  onOpenIssueModal,
}) {
  const offsetDbChangeCount =
    (offsetDbCheck?.added_machines?.length || 0) + (offsetDbCheck?.updated_machines?.length || 0);

  return (
    <header className={`sticky top-0 z-50 px-4 py-2 flex flex-wrap items-center justify-between border-b ${theme.border} ${theme.headerBg} backdrop-blur-md gap-3`}>
      {/* Left: Professional Brand Header + Live SPECTRA Activity Status */}
      <div className="flex items-center space-x-2.5">
        <div className="flex items-center space-x-2">
          <img
            src="/logo.svg"
            alt=""
            aria-hidden="true"
            className="w-7 h-7 shrink-0 drop-shadow-[0_0_8px_rgba(0,240,255,0.35)] select-none"
          />
          <Zap className="w-5 h-5 text-[#FCEE09] animate-pulse shrink-0" />
          <span className="text-sm font-black tracking-widest text-[#FCEE09] font-mono uppercase">
            SPECTRA
          </span>
        </div>
        <button
          type="button"
          onClick={() => onOpenUpdates(false)}
          className="text-[10px] px-2 py-0.5 bg-black/60 hover:bg-zinc-900 text-zinc-300 border border-zinc-700 hover:border-zinc-500 font-mono font-bold tracking-wider rounded transition-colors cursor-pointer"
          title={t('headerBuildCheckTitle', { build: effectiveBuild })}
        >
          BUILD {effectiveBuild}
        </button>
        <div
          className={`flex items-center space-x-1.5 px-2 py-0.5 rounded text-[10px] font-mono font-bold border transition-all ${spectraActivity.cls}`}
          title={`${t('activityTooltipPrefix')}: ${spectraActivity.detail}`}
        >
          <span className={`w-1.5 h-1.5 rounded-full shrink-0 ${spectraActivity.dot}`} />
          <span className="tracking-wider uppercase">{spectraActivity.label}</span>
        </div>
        {updateInfo?.update_available ? (
          <button
            type="button"
            onClick={() => onOpenUpdates(null)}
            className="flex items-center space-x-1 text-[10px] px-2 py-0.5 bg-emerald-950/80 hover:bg-emerald-900 text-emerald-300 border border-emerald-500/70 font-mono font-extrabold tracking-wider rounded animate-pulse cursor-pointer transition-colors"
            title={t('headerUpdateTitle', { build: updateInfo.latest_build })}
          >
            <Download className="w-3 h-3" />
            <span>{t('headerUpdateBtn', { build: updateInfo.latest_build })}</span>
          </button>
        ) : (
          <button
            type="button"
            onClick={() => onOpenUpdates(true)}
            className="flex items-center space-x-1 text-[10px] px-2 py-0.5 bg-cyan-950/50 hover:bg-cyan-900/70 text-cyan-300 border border-cyan-700/70 font-mono font-bold tracking-wider rounded cursor-pointer transition-colors"
            title={t('headerCheckUpdateTitle')}
          >
            {isCheckingUpdates ? (
              <RefreshCw className="w-3 h-3 animate-spin" />
            ) : (
              <Download className="w-3 h-3" />
            )}
            <span>{t('headerCheckUpdateBtn')}</span>
          </button>
        )}
        {offsetDbCheck?.update_available && onOpenOffsetDb && (
          <button
            type="button"
            onClick={onOpenOffsetDb}
            className="flex items-center space-x-1 text-[10px] px-2 py-0.5 bg-purple-950/85 hover:bg-purple-900 text-purple-200 border border-purple-400/80 font-mono font-extrabold tracking-wider rounded cursor-pointer transition-colors"
            title={t('offsetDbHeaderTitle')}
          >
            <Database className="w-3 h-3 text-purple-300" />
            <span>{t('offsetDbHeaderBadge', { count: Math.max(1, offsetDbChangeCount) })}</span>
          </button>
        )}
        <span className="text-xs text-zinc-400 font-mono hidden 2xl:inline">
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
            onChange={(e) => onSelectPort(e.target.value)}
            className="bg-transparent text-gray-200 text-xs font-mono outline-none cursor-pointer max-w-[200px]"
          >
            {availablePorts.map((p) => (
              <option key={p} value={p} className="bg-gray-900 text-gray-200">
                {p}
              </option>
            ))}
          </select>
          <button onClick={onRefreshPorts} title={t('refreshPortsTitle')} className="text-gray-400 hover:text-white ml-1">
            <RefreshCw className="w-3 h-3" />
          </button>
        </div>

        {/* Action Buttons */}
        <button
          onClick={onQuerySensors}
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
          onClick={onRunInterrogation}
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
          onClick={onOpenServiceReport}
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
            onOpenExportModal();
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
          onClick={onOpenFirmwareInspector}
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
          onClick={() => onToggleAi(!aiEnabled)}
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
          onClick={onOpenConfig}
          className="flex items-center space-x-1 px-2.5 py-1 font-mono font-bold rounded text-[11px] bg-black/40 hover:bg-zinc-800 border border-zinc-700 text-zinc-200 transition-colors cursor-pointer"
          title={t('btnConfigTitle')}
        >
          <Settings className="w-3.5 h-3.5 text-[#FCEE09]" />
          <span>{t('btnConfig')}</span>
        </button>

        {/* Built-In User Guide & Help Center */}
        <button
          type="button"
          onClick={onOpenUserGuide}
          className="flex items-center space-x-1 px-2.5 py-1 font-mono font-bold rounded text-[11px] bg-sky-950/40 hover:bg-sky-900/60 border border-sky-700/70 text-sky-300 hover:text-sky-100 transition-colors cursor-pointer"
          title={t('btnHelpTitle')}
        >
          <BookOpen className="w-3.5 h-3.5 text-sky-400" />
          <span>{t('btnHelp')}</span>
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

        {/* Report Issue to GitHub Button (End of Top Control Panel after Debug Toggle) */}
        <button
          type="button"
          onClick={onOpenIssueModal}
          className="flex items-center space-x-1 px-2.5 py-0.5 rounded text-[11px] font-mono font-bold bg-rose-950/40 hover:bg-rose-900/60 border border-rose-800/70 text-rose-300 hover:text-rose-100 transition-colors cursor-pointer"
          title={t('btnReportIssueTitle')}
        >
          <Flag className="w-3 h-3 text-rose-400" />
          <span>{t('btnReportIssue')}</span>
        </button>
      </div>
    </header>
  );
}

export default React.memo(WorkspaceHeader);
