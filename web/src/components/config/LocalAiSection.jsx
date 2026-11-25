import React from 'react';
import { Power, Play, Square, RefreshCw, Download, Trash2 } from 'lucide-react';

export default function LocalAiSection({
  t,
  aiEnabled,
  aiModel,
  aiSystem,
  aiDownload,
  autoUnload,
  ollamaInfo,
  hardware,
  installedModels,
  loadedModels,
  catalog,
  selectableModels,
  effectiveDefaultModel,
  promptUnpulledTarget,
  promptUnpulledMeta,
  pendingUnpulledModel,
  setPendingUnpulledModel,
  pullModelInput,
  setPullModelInput,
  ollamaBusy,
  isModelInstalled,
  onToggleAi,
  onSaveAiConfig,
  onRefreshAiStatus,
  runOllamaAction,
  handleSelectDefaultModel,
  handlePullAndUseSelectedModel,
}) {
  return (
    <div className="space-y-4">
      {/* Master AI Power Card */}
      <div className="p-3.5 bg-black/40 border border-zinc-800 rounded space-y-3">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div>
            <div className="font-bold text-white flex items-center gap-2">
              <span>{t('cfgGlobalAiTitle')}</span>
              <span
                className={`text-[10px] px-1.5 py-0.5 rounded font-bold ${
                  aiEnabled
                    ? 'bg-emerald-950 text-emerald-400 border border-emerald-700'
                    : 'bg-zinc-900 text-zinc-400 border border-zinc-700'
                }`}
              >
                {aiEnabled ? t('cfgAiActiveBadge') : t('cfgAiOffBadge')}
              </span>
            </div>
            <div className="text-[11px] text-zinc-400 mt-0.5">
              {t('cfgRuntimeLabel')}{' '}
              <strong className={ollamaInfo.available ? 'text-emerald-400' : 'text-zinc-400'}>
                {ollamaInfo.available ? t('cfgRuntimeOnline') : aiSystem?.binary_installed ? t('cfgRuntimeStopped') : t('cfgRuntimeNotInstalled')}
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
            <span>{aiEnabled ? t('btnTurnAiOff') : t('cfgBtnEnableAi')}</span>
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
            <span>{t('cfgBtnStartEngine')}</span>
          </button>
          <button
            type="button"
            disabled={ollamaBusy}
            onClick={() => runOllamaAction('unload')}
            className="px-2.5 py-1 bg-zinc-800 hover:bg-zinc-700 disabled:opacity-40 border border-zinc-700 text-amber-300 rounded text-[11px] font-bold cursor-pointer"
          >
            {t('cfgBtnUnloadRam')}
          </button>
          <button
            type="button"
            disabled={ollamaBusy}
            onClick={() => runOllamaAction('stop')}
            className="px-2.5 py-1 bg-zinc-800 hover:bg-zinc-700 disabled:opacity-40 border border-zinc-700 text-rose-300 rounded text-[11px] font-bold flex items-center gap-1 cursor-pointer"
          >
            <Square className="w-3 h-3" />
            <span>{t('cfgBtnStopEngine')}</span>
          </button>
          <button
            type="button"
            disabled={ollamaBusy}
            onClick={() => onRefreshAiStatus && onRefreshAiStatus()}
            className="ml-auto px-2.5 py-1 bg-zinc-900 hover:bg-zinc-800 border border-zinc-700 text-zinc-300 rounded text-[11px] flex items-center gap-1 cursor-pointer"
          >
            <RefreshCw className={`w-3 h-3 ${ollamaBusy ? 'animate-spin' : ''}`} />
            <span>{t('cfgBtnRefresh')}</span>
          </button>
        </div>
      </div>

      {/* Global Default Model Selector */}
      <div className="p-3.5 bg-black/40 border border-zinc-800 rounded space-y-2.5">
        <div className="flex items-center justify-between">
          <label className="font-bold text-white uppercase text-[11px]">
            {t('cfgDefaultModelLabel')}
          </label>
          {hardware?.recommended_model && (
            <span className="text-[10px] text-cyan-400">
              {t('cfgRecommended', { model: hardware.recommended_model })}
            </span>
          )}
        </div>

        <select
          value={effectiveDefaultModel}
          onChange={(e) => handleSelectDefaultModel(e.target.value)}
          className="w-full bg-zinc-950 border border-zinc-700 rounded px-2.5 py-2 text-xs text-white outline-none focus:border-[#00F0FF]"
        >
          {selectableModels.map((mId) => {
            const cat = catalog.find((c) => c.id === mId);
            const isInstalled = isModelInstalled(mId);
            const tagParts = [
              isInstalled ? t('cfgInstalledTag') : t('cfgNotPulledTag'),
              cat?.is_recommended ? t('cfgRecommendedTag') : cat?.compatibility || ''
            ].filter(Boolean);
            return (
              <option key={mId} value={mId}>
                {cat ? `${cat.name} [${mId}]` : mId} — {tagParts.join(' • ')}
              </option>
            );
          })}
        </select>

        {promptUnpulledTarget && !aiDownload?.active && (
          <div className="p-2.5 bg-amber-950/35 border border-amber-500/60 rounded space-y-2">
            <div className="flex flex-wrap items-start justify-between gap-2">
              <div>
                <div className="font-bold text-amber-200 text-[11px]">
                  {t('cfgUnpulledPromptTitle', { model: promptUnpulledTarget })}
                </div>
                <div className="text-[10px] text-amber-200/80 mt-0.5">
                  {t('cfgUnpulledPromptDesc', {
                    size: promptUnpulledMeta?.disk_mb ? ` (~${promptUnpulledMeta.disk_mb} MB)` : '',
                  })}
                </div>
              </div>
              <div className="flex items-center gap-1.5 shrink-0">
                <button
                  type="button"
                  disabled={ollamaBusy}
                  onClick={() => handlePullAndUseSelectedModel(promptUnpulledTarget)}
                  className="px-2.5 py-1 bg-[#FCEE09] hover:bg-yellow-300 disabled:opacity-40 text-black font-extrabold rounded text-[11px] flex items-center gap-1 cursor-pointer"
                >
                  <Download className="w-3.5 h-3.5" />
                  <span>{t('cfgBtnPullSelectedNow', { model: promptUnpulledTarget })}</span>
                </button>
                {pendingUnpulledModel && (
                  <button
                    type="button"
                    onClick={() => setPendingUnpulledModel(null)}
                    className="px-2 py-1 bg-zinc-900 hover:bg-zinc-800 border border-zinc-700 text-zinc-300 rounded text-[11px] cursor-pointer"
                  >
                    {t('cfgBtnKeepCurrentModel')}
                  </button>
                )}
              </div>
            </div>
          </div>
        )}

        <label className="flex items-center space-x-2 text-[11px] text-zinc-300 cursor-pointer pt-1">
          <input
            type="checkbox"
            checked={Boolean(autoUnload)}
            onChange={(e) =>
              onSaveAiConfig && onSaveAiConfig({ model: aiModel, auto_unload: e.target.checked })
            }
            className="rounded bg-black border-zinc-700 text-cyan-500"
          />
          <span>{t('cfgAutoUnloadLabel')}</span>
        </label>
      </div>

      {/* Manage Installed Local Models + Pull New */}
      <div className="p-3.5 bg-black/40 border border-zinc-800 rounded space-y-3">
        <div className="font-bold text-white uppercase text-[11px]">
          {t('cfgLocalModelsTitle', { count: installedModels.length })}
        </div>

        {installedModels.length === 0 ? (
          <div className="p-2.5 bg-zinc-950/70 border border-zinc-800 rounded text-[11px] text-zinc-400">
            {t('cfgNoModelsInstalled')}
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
                        {t('cfgBadgeDefault')}
                      </span>
                    )}
                    {isLoaded && (
                      <span className="px-1.5 py-0.5 bg-emerald-950 text-emerald-300 border border-emerald-700 rounded text-[9px] font-bold animate-pulse">
                        {t('cfgBadgeInRam')}
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
                        {t('cfgBtnUse')}
                      </button>
                    )}
                    {isLoaded && (
                      <button
                        type="button"
                        disabled={ollamaBusy}
                        onClick={() => runOllamaAction('unload', m)}
                        className="px-2 py-0.5 bg-amber-950/60 hover:bg-amber-900/70 border border-amber-700 text-amber-300 rounded text-[10px] font-bold cursor-pointer"
                      >
                        {t('cfgBtnUnload')}
                      </button>
                    )}
                    <button
                      type="button"
                      disabled={ollamaBusy}
                      onClick={() => runOllamaAction('delete', m)}
                      className="p-1 text-rose-400 hover:text-rose-300 hover:bg-rose-950/40 rounded cursor-pointer"
                      title={t('cfgDeleteModelTitle', { model: m })}
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
          <div className="text-[11px] text-zinc-400 font-bold uppercase">{t('cfgPullTitle')}</div>
          <div className="flex gap-2">
            <input
              type="text"
              value={pullModelInput}
              onChange={(e) => setPullModelInput(e.target.value)}
              placeholder={t('cfgPullPlaceholder')}
              className="flex-1 bg-zinc-950 border border-zinc-700 rounded px-2.5 py-1.5 text-xs text-white outline-none focus:border-[#00F0FF]"
            />
            {aiDownload?.active ? (
              <button
                type="button"
                onClick={() => runOllamaAction('cancel_pull')}
                className="px-3 py-1.5 bg-red-700 hover:bg-red-600 text-white font-bold rounded text-xs cursor-pointer"
              >
                {t('cfgBtnCancelPull')}
              </button>
            ) : (
              <button
                type="button"
                disabled={ollamaBusy || !pullModelInput.trim()}
                onClick={() => runOllamaAction('pull_async', pullModelInput.trim())}
                className="px-3 py-1.5 bg-cyan-700 hover:bg-cyan-600 disabled:opacity-40 text-white font-bold rounded text-xs flex items-center gap-1.5 cursor-pointer"
              >
                <Download className="w-3.5 h-3.5" />
                <span>{t('cfgBtnPullModel')}</span>
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
                  {aiDownload.phase_label || t('cfgInstallingAi')}
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
                  {aiDownload.error || aiDownload.status_text || t('cfgWorking')}
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
  );
}
