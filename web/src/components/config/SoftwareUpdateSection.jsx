import React from 'react';
import { Download, ExternalLink, RefreshCw, X, ShieldCheck } from 'lucide-react';
import { safeExternalUrl } from '../../utils/urlSafety';

export default function SoftwareUpdateSection({
  t,
  updateInfo,
  updateProgress,
  isCheckingUpdates,
  isReconnectingAfterUpdate,
  onCheckUpdates,
  onStartUpdate,
  onCancelUpdate,
  offsetDbStatus = null,
  offsetDbCheck = null,
  isCheckingOffsetDb = false,
  isSyncingOffsetDb = false,
  offsetDbSyncNotice = null,
  onCheckOffsetDb = null,
  onSyncOffsetDb = null,
}) {
  const addedMachines = offsetDbCheck?.added_machines || [];
  const updatedMachines = offsetDbCheck?.updated_machines || [];

  return (
    <div className="space-y-4">
      <div className="p-4 bg-black/40 border border-zinc-800 rounded space-y-3">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div>
            <div className="font-bold text-white flex items-center gap-2">
              <Download className="w-4 h-4 text-[#00F0FF]" />
              <span>{t('cfgUpdatesTitle')}</span>
            </div>
            <div className="text-[11px] text-zinc-400 mt-0.5">
              {t('cfgUpdatesSubtitle', { repo: 'Pr0xyA-91/spectra' })}
            </div>
          </div>
          <span
            className={`text-[10px] px-2 py-0.5 rounded font-bold border ${
              updateInfo?.update_available
                ? 'bg-emerald-950/70 text-emerald-300 border-emerald-600'
                : updateInfo?.ok
                ? 'bg-zinc-900 text-cyan-300 border-zinc-700'
                : 'bg-zinc-900 text-zinc-400 border-zinc-700'
            }`}
          >
            {updateInfo?.update_available
              ? t('cfgUpdatesAvailableBadge')
              : updateInfo?.ok
              ? t('cfgUpdatesUpToDateBadge')
              : t('cfgUpdatesOfflineBadge')}
          </span>
        </div>

        {/* Build Comparison Grid */}
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-2.5">
          <div className="p-2.5 bg-zinc-950/70 border border-zinc-800 rounded">
            <div className="text-[10px] text-zinc-500 uppercase">{t('cfgUpdatesCurrentBuild')}</div>
            <div className="text-sm font-extrabold text-white mt-0.5">
              Build {updateInfo?.current_build || updateProgress?.current_build || '—'}
            </div>
          </div>
          <div className="p-2.5 bg-zinc-950/70 border border-zinc-800 rounded">
            <div className="text-[10px] text-zinc-500 uppercase">{t('cfgUpdatesLatestBuild')}</div>
            <div
              className={`text-sm font-extrabold mt-0.5 ${
                updateInfo?.update_available ? 'text-emerald-400' : 'text-zinc-200'
              }`}
            >
              {updateInfo?.latest_build ? `Build ${updateInfo.latest_build}` : '—'}
            </div>
          </div>
          <div className="p-2.5 bg-zinc-950/70 border border-zinc-800 rounded">
            <div className="text-[10px] text-zinc-500 uppercase">{t('cfgUpdatesChannel')}</div>
            <div className="text-xs font-bold text-cyan-300 mt-1">
              {updateInfo?.install_mode === 'linux_git'
                ? t('cfgChannelLinuxGit')
                : updateInfo?.install_mode === 'linux_tarball'
                ? t('cfgChannelLinuxTarball')
                : updateInfo?.install_mode === 'windows_exe'
                ? t('cfgChannelWindowsExe')
                : updateInfo?.install_mode || updateInfo?.platform || 'auto'}
            </div>
          </div>
        </div>

        {/* Release Notes */}
        {updateInfo?.release_notes && (
          <div className="p-3 bg-zinc-950/80 border border-zinc-800 rounded space-y-1.5">
            <div className="flex items-center justify-between text-[11px] font-bold text-zinc-300">
              <span>{t('cfgUpdatesReleaseNotes')}</span>
              {safeExternalUrl(updateInfo?.release_url) && (
                <a
                  href={safeExternalUrl(updateInfo.release_url)}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-cyan-400 hover:underline flex items-center gap-1"
                >
                  <span>GitHub</span>
                  <ExternalLink className="w-3 h-3" />
                </a>
              )}
            </div>
            <pre className="text-[11px] text-zinc-400 whitespace-pre-wrap break-words font-mono max-h-40 overflow-y-auto">
              {updateInfo.release_notes}
            </pre>
          </div>
        )}

        {/* Progress Bar & Restart Status */}
        {(updateProgress?.in_progress ||
          updateProgress?.status === 'restarting' ||
          isReconnectingAfterUpdate) && (
          <div className="p-3 bg-cyan-950/30 border border-cyan-700/60 rounded space-y-2">
            <div className="flex items-center justify-between text-[11px] font-bold text-cyan-200">
              <span>
                {isReconnectingAfterUpdate
                  ? t('cfgUpdatesRestartBanner')
                  : updateProgress?.message || updateProgress?.status}
              </span>
              <span>{Math.min(100, Math.max(0, Math.round(updateProgress?.percent || 0)))}%</span>
            </div>
            <div className="w-full h-2 bg-zinc-900 rounded overflow-hidden border border-zinc-800">
              <div
                className="h-full bg-[#00F0FF] transition-all duration-300"
                style={{ width: `${Math.min(100, Math.max(4, Math.round(updateProgress?.percent || 0)))}%` }}
              />
            </div>
          </div>
        )}

        {/* Errors */}
        {(updateProgress?.error || (updateInfo && !updateInfo.ok && updateInfo.error)) && (
          <div className="px-3 py-2 bg-red-950/50 border border-red-800 text-red-300 rounded text-[11px]">
            {updateProgress?.error || updateInfo?.error}
          </div>
        )}

        {/* Platform Safety Note */}
        <p className="text-[11px] text-zinc-400 leading-relaxed">
          {updateInfo?.platform === 'windows' ? t('cfgUpdatesWinHint') : t('cfgUpdatesLinuxHint')}
        </p>

        {/* Controls */}
        <div className="flex flex-wrap items-center gap-2 pt-1">
          <button
            type="button"
            disabled={isCheckingUpdates || Boolean(updateProgress?.in_progress) || isReconnectingAfterUpdate}
            onClick={() => onCheckUpdates && onCheckUpdates(true)}
            className="flex items-center space-x-1.5 px-3 py-1.5 bg-zinc-800 hover:bg-zinc-700 disabled:opacity-50 text-zinc-200 border border-zinc-600 rounded font-bold text-xs cursor-pointer transition-colors"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${isCheckingUpdates ? 'animate-spin' : ''}`} />
            <span>{isCheckingUpdates ? t('cfgUpdatesBtnChecking') : t('cfgUpdatesBtnCheck')}</span>
          </button>

          {updateInfo?.update_available &&
            !updateProgress?.in_progress &&
            !isReconnectingAfterUpdate && (
              <button
                type="button"
                onClick={() => onStartUpdate && onStartUpdate()}
                className="flex items-center space-x-1.5 px-3.5 py-1.5 bg-emerald-600 hover:bg-emerald-500 text-black font-extrabold rounded text-xs cursor-pointer transition-colors shadow-[0_0_12px_rgba(16,185,129,0.4)]"
              >
                <Download className="w-3.5 h-3.5" />
                <span>{t('cfgUpdatesBtnInstall', { build: updateInfo.latest_build })}</span>
              </button>
            )}

          {updateProgress?.in_progress &&
            !['applying', 'restarting'].includes(updateProgress?.status) && (
              <button
                type="button"
                onClick={() => onCancelUpdate && onCancelUpdate()}
                className="flex items-center space-x-1.5 px-3 py-1.5 bg-red-950/70 hover:bg-red-900 text-red-200 border border-red-700 rounded font-bold text-xs cursor-pointer"
              >
                <X className="w-3.5 h-3.5" />
                <span>{t('cfgUpdatesBtnCancel')}</span>
              </button>
            )}
        </div>
      </div>

      {/* Independent Ed25519-Signed Machine Offset DB Sync Card */}
      <div className="p-4 bg-black/40 border border-purple-800/60 rounded space-y-3">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div>
            <div className="font-bold text-white flex items-center gap-2">
              <ShieldCheck className="w-4 h-4 text-purple-400" />
              <span>{t('offsetDbTitle')}</span>
            </div>
            <div className="text-[11px] text-zinc-400 mt-0.5">{t('offsetDbSubtitle')}</div>
          </div>
          <span
            className={`text-[10px] px-2 py-0.5 rounded font-bold border ${
              offsetDbCheck?.update_available
                ? 'bg-emerald-950/70 text-emerald-300 border-emerald-500'
                : 'bg-zinc-900 text-purple-300 border-purple-700/70'
            }`}
          >
            {offsetDbCheck?.update_available ? t('offsetDbAvailableBadge') : t('offsetDbUpToDateBadge')}
          </span>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 gap-2.5">
          <div className="p-2.5 bg-zinc-950/70 border border-zinc-800 rounded">
            <div className="text-[10px] text-zinc-500 uppercase">{t('offsetDbCurrentVersion')}</div>
            <div className="text-xs font-extrabold text-cyan-300 mt-0.5 font-mono">
              {offsetDbStatus?.offset_db_version || 'bundled'}
            </div>
          </div>
          <div className="p-2.5 bg-zinc-950/70 border border-zinc-800 rounded">
            <div className="text-[10px] text-zinc-500 uppercase">{t('offsetDbRemoteVersion')}</div>
            <div className="text-xs font-extrabold text-emerald-300 mt-0.5 font-mono">
              {offsetDbCheck?.latest_version || '—'}
            </div>
          </div>
        </div>

        {(addedMachines.length > 0 || updatedMachines.length > 0) && offsetDbCheck?.update_available && (
          <div className="p-2.5 bg-zinc-950/80 border border-emerald-700/60 rounded space-y-1 text-[11px] font-mono">
            {addedMachines.length > 0 && (
              <div className="text-emerald-300">
                <strong>+ {t('offsetDbAddedLabel')}:</strong>{' '}
                {addedMachines.map((m) => `${m.model_family}${m.ef_code ? ` [${m.ef_code}]` : ''}`).join(', ')}
              </div>
            )}
            {updatedMachines.length > 0 && (
              <div className="text-cyan-300">
                <strong>↻ {t('offsetDbUpdatedLabel')}:</strong>{' '}
                {updatedMachines.map((m) => `${m.model_family}${m.ef_code ? ` [${m.ef_code}]` : ''}`).join(', ')}
              </div>
            )}
          </div>
        )}

        {offsetDbSyncNotice?.msg && (
          <div
            className={`px-3 py-2 rounded text-[11px] border ${
              offsetDbSyncNotice.error
                ? 'bg-red-950/50 border-red-800 text-red-300'
                : 'bg-emerald-950/40 border-emerald-700 text-emerald-300'
            }`}
          >
            {offsetDbSyncNotice.msg}
          </div>
        )}

        <p className="text-[10px] text-zinc-400">{t('offsetDbPrecedenceNote')}</p>

        <div className="flex flex-wrap items-center gap-2">
          <button
            type="button"
            disabled={isCheckingOffsetDb || isSyncingOffsetDb}
            onClick={() => onCheckOffsetDb && onCheckOffsetDb(true)}
            className="flex items-center space-x-1.5 px-3 py-1.5 bg-zinc-800 hover:bg-zinc-700 disabled:opacity-50 text-zinc-200 border border-zinc-600 rounded font-bold text-xs cursor-pointer"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${isCheckingOffsetDb ? 'animate-spin' : ''}`} />
            <span>{isCheckingOffsetDb ? t('offsetDbBtnChecking') : t('offsetDbBtnCheck')}</span>
          </button>

          {offsetDbCheck?.update_available && (
            <button
              type="button"
              disabled={isSyncingOffsetDb}
              onClick={() => onSyncOffsetDb && onSyncOffsetDb()}
              className="flex items-center space-x-1.5 px-3.5 py-1.5 bg-emerald-600 hover:bg-emerald-500 disabled:opacity-50 text-black font-extrabold rounded text-xs cursor-pointer shadow-[0_0_12px_rgba(16,185,129,0.4)]"
            >
              <Download className="w-3.5 h-3.5" />
              <span>{isSyncingOffsetDb ? t('offsetDbBtnSyncing') : t('offsetDbBtnSync')}</span>
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
