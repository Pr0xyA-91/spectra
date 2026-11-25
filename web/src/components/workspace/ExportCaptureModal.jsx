import React from 'react';
import {
  RefreshCw,
  Download,
  Sparkles,
  Check,
  X,
  Copy,
  Upload,
  ExternalLink,
  LogOut,
  Github,
} from 'lucide-react';
import { safeExternalUrl } from '../../utils/urlSafety';
import { sanitizeExportPrefix, triggerBrowserDownload } from './workspaceHelpers';

export default function ExportCaptureModal({
  show,
  onClose,
  theme,
  t,
  statsData,
  selectedPort,
  exportPrefix,
  setExportPrefix,
  exportStatus,
  browserDownloadAvailable,
  isDumping,
  isCalibratingOffsets,
  onTriggerExport,
  capturedBundle,
  capturedFilename,
  onResetCapture,
  joeFileName,
  joeCsvContent,
  onJoeFileUpload,
  aiEnabled,
  useAiJoeMatch,
  setUseAiJoeMatch,
  onToggleAi,
  onTriggerDumpCapture,
  onCalibrateOffsetsFromJoe,
  offsetCalibration,
  offsetAppliedLocally,
  onApplyOffsetFixLocally,
  onSaveLocally,
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
  onStartDeviceFlow,
  onSavePat,
  onLogout,
  onCopyDeviceCode,
  onUploadToCommunity,
}) {
  if (!show) return null;

  const cleanPre = sanitizeExportPrefix(exportPrefix);
  const safeMod =
    String(statsData?.model_family || statsData?.identity?.model_name || 'appliance')
      .replace(/[^\w\-_]/g, '_')
      .replace(/^_+|_+$/g, '') || 'appliance';
  const previewName = `${cleanPre ? `${cleanPre}_` : ''}spectra_export_${safeMod}_YYYYMMDD_HHMMSS.json`;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm p-4">
      <div className={`w-full max-w-lg p-5 border rounded-lg shadow-2xl ${theme.panelBg} ${theme.border} space-y-4 max-h-[90vh] overflow-y-auto`}>
        <div className="flex items-center justify-between border-b border-gray-800 pb-2">
          <span className="text-sm font-bold text-white flex items-center space-x-2">
            <Download className="w-4 h-4 text-sky-400" />
            <span>{t('exportModalTitle')}</span>
          </span>
          <button onClick={onClose} className="text-gray-400 hover:text-white">
            <X className="w-4 h-4" />
          </button>
        </div>

        <div className="space-y-2 text-xs">
          <p className="text-gray-300">
            {t('exportModalDesc')}
          </p>

          {/* Ticket Number / Custom Filename Prefix */}
          <div className="p-2.5 rounded bg-black/40 border border-gray-800 space-y-1.5">
            <label className="block text-[11px] font-bold text-gray-300 font-mono">
              {t('exportPrefixLabel')}
            </label>
            <div className="flex items-center space-x-1.5">
              <input
                type="text"
                value={exportPrefix}
                onChange={(e) => setExportPrefix(e.target.value)}
                maxLength={48}
                placeholder={t('exportPrefixPlaceholder')}
                className="flex-1 px-2.5 py-1.5 bg-black/60 border border-gray-700 focus:border-sky-500 rounded text-xs text-white placeholder-gray-500 outline-none font-mono select-text"
              />
              {exportPrefix && (
                <button
                  type="button"
                  onClick={() => setExportPrefix('')}
                  className="p-1.5 rounded bg-zinc-900 hover:bg-zinc-800 border border-zinc-700 text-gray-400 hover:text-white cursor-pointer"
                  title={t('exportPrefixClear')}
                >
                  <X className="w-3.5 h-3.5" />
                </button>
              )}
            </div>
            <div className="text-[10px] font-mono text-gray-400 truncate">
              <span className="text-gray-500">{t('exportPrefixPreview')} </span>
              <span className={cleanPre ? 'text-sky-300 font-semibold' : 'text-gray-400'}>
                {previewName}
              </span>
            </div>
          </div>

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
            onClick={() => onTriggerExport('json')}
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
            onClick={() => onTriggerExport('csv')}
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
            onClick={() => onTriggerExport('text')}
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
                  onClick={onResetCapture}
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
                      onChange={onJoeFileUpload}
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
                                onToggleAi(true);
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
                    onClick={onTriggerDumpCapture}
                    disabled={isDumping || isCalibratingOffsets || exportStatus.loading || !selectedPort}
                    className="w-full mt-2 py-2.5 px-3 bg-purple-600 hover:bg-purple-500 disabled:opacity-50 text-white font-medium text-xs rounded flex items-center justify-center gap-2 transition-colors shadow-sm cursor-pointer"
                  >
                    <Sparkles className="w-4 h-4" />
                    <span>{isDumping ? t('btnSweepingBundle') : t('btnCaptureBundle')}</span>
                  </button>

                  {joeFileName && (
                    <button
                      onClick={() => onCalibrateOffsetsFromJoe(true)}
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
                          onClick={() => onToggleAi(!aiEnabled)}
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
                          onClick={() => onCalibrateOffsetsFromJoe(false)}
                          disabled={!aiEnabled || isCalibratingOffsets}
                          className="flex-1 py-1.5 px-2.5 bg-cyan-700 hover:bg-cyan-600 disabled:opacity-40 text-white font-bold text-[11px] rounded cursor-pointer"
                        >
                          {isCalibratingOffsets ? t('btnCalibrating') : offsetCalibration ? t('btnRerunAiCalib') : t('btnAiMatchJoe')}
                        </button>
                        {offsetCalibration && (
                          <button
                            type="button"
                            onClick={onApplyOffsetFixLocally}
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
                      onClick={onSaveLocally}
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
                          onClick={onLogout}
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
                              onClick={onStartDeviceFlow}
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
                            onClick={() => onCopyDeviceCode(deviceFlow.user_code)}
                            className="px-2 py-1 bg-sky-800/80 hover:bg-sky-700 text-sky-200 rounded text-[10px] flex items-center gap-1 cursor-pointer"
                          >
                            {copiedCode ? <Check className="w-3 h-3 text-emerald-400" /> : <Copy className="w-3 h-3" />}
                            <span>{copiedCode ? t('ghCopied') : t('ghCopy')}</span>
                          </button>
                        </div>
                        <div className="flex items-center justify-between text-[11px]">
                          {safeExternalUrl(deviceFlow.verification_uri) && (
                            <a
                              href={safeExternalUrl(deviceFlow.verification_uri)}
                              target="_blank"
                              rel="noopener noreferrer"
                              className="text-sky-400 hover:text-sky-300 underline flex items-center gap-1 font-medium"
                            >
                              <span>{t('ghOpenDeviceUrl')}</span>
                              <ExternalLink className="w-3 h-3" />
                            </a>
                          )}
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
                            autoComplete="off"
                            spellCheck={false}
                            placeholder="ghp_... or github_pat_..."
                            className="flex-1 bg-zinc-900 border border-zinc-700 rounded px-2 py-1 text-xs text-white font-mono placeholder:text-zinc-600 focus:outline-none focus:border-sky-500"
                          />
                          <button
                            onClick={onSavePat}
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
                      onClick={onUploadToCommunity}
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
                        {safeExternalUrl(uploadResult.url) && (
                          <a
                            href={safeExternalUrl(uploadResult.url)}
                            target="_blank"
                            rel="noopener noreferrer"
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
                        href={safeExternalUrl('https://github.com/Pr0xyA-91/spectra-captures/issues/new')}
                        target="_blank"
                        rel="noopener noreferrer"
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
  );
}
