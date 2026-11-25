import React from 'react';
import {
  CheckCircle2,
  AlertTriangle,
  Copy,
  Check,
  RefreshCw,
  FolderOpen,
  Box,
  FileText,
  Sparkles
} from 'lucide-react';

export default function HmiHeaderBar({
  theme,
  lang,
  t,
  hmiInfo,
  findings,
  targetPath,
  setTargetPath,
  autoScanDownloads,
  discoveredTargets,
  isDiscovering,
  isLoading,
  isPatching,
  isExporting,
  copiedSha,
  statusMessage,
  setStatusMessage,
  exportNotice,
  setExportNotice,
  onRescan,
  onApplyPatches,
  onExportReport,
  onBrowseTarget,
  onDiscoverTargets,
  onToggleAutoScan,
  onSelectTarget,
  onCopySha
}) {
  return (
    <div className={`p-4 rounded border ${theme.border} ${theme.panelBg} space-y-3`}>
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center space-x-2.5">
          <div className="p-2 bg-cyan-950/60 border border-cyan-500/40 rounded text-cyan-400">
            <Box className="w-5 h-5" />
          </div>
          <div>
            <div className="flex items-center space-x-2">
              <h2 className="text-sm font-extrabold tracking-wider text-cyan-400">
                {t('hmiTitle')}
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
            onClick={() => onRescan()}
            disabled={isLoading}
            className="flex items-center space-x-1.5 px-3 py-1.5 font-bold rounded bg-zinc-800 hover:bg-zinc-700 text-zinc-200 border border-zinc-700 transition-all"
            title="Re-run static audit"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${isLoading ? 'animate-spin text-cyan-400' : ''}`} />
            <span>{t('hmiBtnRescan')}</span>
          </button>

          <button
            onClick={onApplyPatches}
            disabled={isPatching || isLoading || !hmiInfo}
            className="flex items-center space-x-1.5 px-3 py-1.5 font-bold rounded bg-gradient-to-r from-cyan-600 to-blue-600 hover:from-cyan-500 hover:to-blue-500 text-black shadow-[0_0_12px_rgba(6,182,212,0.4)] transition-all font-mono"
            title="Create a patched laboratory copy of the binary fixing all detected defects"
          >
            <Sparkles className="w-3.5 h-3.5 text-black" />
            <span>{isPatching ? t('hmiBtnPatching') : t('hmiBtnPatch')}</span>
          </button>

          <div className="flex items-center rounded border border-zinc-700 bg-zinc-900/60 overflow-hidden">
            <button
              onClick={() => onExportReport('md')}
              disabled={isExporting || !hmiInfo}
              className="px-2.5 py-1.5 font-bold text-gray-300 hover:text-white hover:bg-zinc-800 transition-colors flex items-center space-x-1"
              title="Export report as Markdown"
            >
              <FileText className="w-3.5 h-3.5 text-cyan-400" />
              <span>MD</span>
            </button>
            <button
              onClick={() => onExportReport('html')}
              disabled={isExporting || !hmiInfo}
              className="px-2.5 py-1.5 font-bold text-gray-300 hover:text-white hover:bg-zinc-800 transition-colors border-l border-zinc-700"
              title="Export report as HTML"
            >
              HTML
            </button>
            <button
              onClick={() => onExportReport('pdf')}
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
          <span className="text-gray-400 font-bold shrink-0">{lang === 'cs' ? 'Cílový firmware / složka:' : 'Target Binary / Update Dir:'}</span>
          <input
            type="text"
            value={targetPath}
            onChange={(e) => setTargetPath(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && onRescan()}
            className="flex-1 bg-black/60 border border-zinc-700 rounded px-2.5 py-1 text-gray-200 font-mono text-[11px] focus:outline-none focus:border-cyan-500"
            placeholder={t('hmiPathPlaceholder')}
          />
          <button
            onClick={() => onRescan()}
            className="px-3 py-1 font-bold rounded bg-cyan-950 border border-cyan-800 text-cyan-300 hover:bg-cyan-900 transition-colors shrink-0"
          >
            {lang === 'cs' ? 'NAČÍST' : 'LOAD'}
          </button>
          <button
            onClick={onBrowseTarget}
            className="px-2.5 py-1 font-bold rounded bg-zinc-800 border border-zinc-600 text-zinc-200 hover:bg-zinc-700 hover:text-white transition-colors text-[11px] flex items-center space-x-1 shrink-0"
            title="Open file chooser dialog"
          >
            <FolderOpen className="w-3.5 h-3.5 text-cyan-400" />
            <span>{t('hmiBtnBrowse')}</span>
          </button>
          <button
            onClick={() => onDiscoverTargets(false)}
            disabled={isDiscovering}
            className="p-1 rounded bg-zinc-800 border border-zinc-700 text-zinc-400 hover:text-cyan-300 transition-colors text-[10px] shrink-0"
            title="Re-scan ~/Downloads for firmware targets"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${isDiscovering ? 'animate-spin text-cyan-400' : ''}`} />
          </button>
          <button
            onClick={onToggleAutoScan}
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
              {discoveredTargets.slice(0, 6).map((item, idx) => {
                const isSelected = targetPath === item.path;
                const isApk = item.container_type === 'ANDROID_APK';
                const isBin = item.container_type === 'MCU_CTR_BIN';
                const activeClass = isSelected
                  ? 'bg-cyan-900 border-cyan-400 text-cyan-200 ring-1 ring-cyan-400/50'
                  : isApk
                  ? 'bg-cyan-950/60 border-cyan-800/80 text-cyan-300 hover:bg-cyan-900/60'
                  : isBin
                  ? 'bg-amber-950/40 border-amber-800/80 text-amber-300 hover:bg-amber-900/60'
                  : 'bg-zinc-800 border-zinc-700 text-zinc-300 hover:bg-zinc-700 hover:text-white';

                return (
                  <button
                    key={item.path || idx}
                    onClick={() => onSelectTarget(item.path)}
                    className={`px-2 py-1 font-bold rounded border transition-colors text-[10px] truncate max-w-[160px] ${activeClass}`}
                    title={`${item.label}\nPath: ${item.path}\nSize: ${(item.size / 1024).toFixed(0)} KB`}
                  >
                    {item.label || item.name}
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
                onClick={() => onCopySha(hmiInfo.sha256)}
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
  );
}
