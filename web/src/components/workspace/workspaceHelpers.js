// Shared theme, pure export prefix sanitization, browser download helper,
// and live activity pill computation for SpectraWorkspace.

export const WIN_RESERVED_PREFIXES = new Set([
  'CON', 'PRN', 'AUX', 'NUL',
  'COM1', 'COM2', 'COM3', 'COM4', 'COM5', 'COM6', 'COM7', 'COM8', 'COM9',
  'LPT1', 'LPT2', 'LPT3', 'LPT4', 'LPT5', 'LPT6', 'LPT7', 'LPT8', 'LPT9',
]);

export function sanitizeExportPrefix(raw, maxLen = 48) {
  if (!raw) return '';
  let normalized = String(raw)
    .trim()
    .normalize('NFKD')
    .replace(/[\u0300-\u036f]/g, '')
    .replace(/[^\x20-\x7E]/g, '');
  normalized = normalized
    .replace(/\.\./g, '_')
    .replace(/[\\/]/g, '_')
    .replace(/[^A-Za-z0-9._-]+/g, '_')
    .replace(/_{2,}/g, '_')
    .replace(/^[._-]+|[._-]+$/g, '');
  if (!normalized) return '';
  if (normalized.length > maxLen) {
    normalized = normalized.slice(0, maxLen).replace(/[._-]+$/g, '');
  }
  if (WIN_RESERVED_PREFIXES.has(normalized.toUpperCase())) {
    normalized = `tkt_${normalized}`;
  }
  return normalized;
}

export function triggerBrowserDownload(content, filename, mime = 'application/json') {
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
}

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

export function computeSpectraActivity({
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
}) {
  if (isReconnectingAfterUpdate) {
    return {
      label: t('activityReconnecting'),
      detail: updateProgress?.message || 'Reconnecting to updated SPECTRA server...',
      dot: 'bg-amber-400 animate-ping',
      cls: 'bg-amber-950/70 border-amber-500/70 text-amber-200',
    };
  }
  if (updateProgress?.in_progress) {
    const pct = Math.round(updateProgress.percent || 0);
    return {
      label: t('activityUpdating', { pct }),
      detail: updateProgress.message || `Downloading & installing update (${pct}%)`,
      dot: 'bg-cyan-400 animate-pulse',
      cls: 'bg-cyan-950/70 border-cyan-500/70 text-cyan-200',
    };
  }
  if (isInterrogating) {
    return {
      label: t('activityReading', { pct: interrogationProgress }),
      detail: interrogationStage || `Interrogating ${selectedPort}`,
      dot: 'bg-[#FCEE09] animate-pulse',
      cls: 'bg-purple-950/80 border-purple-400/80 text-purple-100',
    };
  }
  if (isDumping) {
    return {
      label: t('activityCapturing'),
      detail: `Capturing full EEPROM bundle from ${selectedPort}`,
      dot: 'bg-purple-400 animate-pulse',
      cls: 'bg-purple-950/70 border-purple-500/70 text-purple-200',
    };
  }
  if (isHardwareBusy) {
    return {
      label: t('activityMapping'),
      detail: 'Memory Mapper EEPROM sweep active',
      dot: 'bg-sky-400 animate-pulse',
      cls: 'bg-sky-950/70 border-sky-500/70 text-sky-200',
    };
  }
  if (aiDownload?.active) {
    return {
      label: t('activityPullingAi'),
      detail: aiDownload.model ? `Downloading ${aiDownload.model}` : 'Downloading Local AI model',
      dot: 'bg-fuchsia-400 animate-pulse',
      cls: 'bg-fuchsia-950/70 border-fuchsia-500/70 text-fuchsia-200',
    };
  }
  if (aiTask?.active || aiBusyCount > 0 || isCalibratingOffsets) {
    const pct = aiTask?.active && aiTask.percent != null ? Math.round(aiTask.percent) : null;
    return {
      label: pct != null ? t('activityAiWorkingPct', { pct }) : t('activityAiWorking'),
      detail: aiTask?.label || (isCalibratingOffsets ? 'Calibrating EEPROM offsets with Local AI' : 'Local AI inference running'),
      dot: 'bg-purple-400 animate-pulse',
      cls: 'bg-purple-950/70 border-purple-400/70 text-purple-200',
    };
  }
  if (isUploading || isReportingIssue) {
    return {
      label: t('activityGithubSync'),
      detail: isReportingIssue ? 'Submitting GitHub issue' : 'Uploading capture to GitHub',
      dot: 'bg-indigo-400 animate-pulse',
      cls: 'bg-indigo-950/70 border-indigo-400/70 text-indigo-200',
    };
  }
  if (exportStatus?.loading) {
    return {
      label: t('activityExporting'),
      detail: exportStatus.msg || 'Exporting diagnostic data',
      dot: 'bg-sky-400 animate-pulse',
      cls: 'bg-sky-950/70 border-sky-500/70 text-sky-200',
    };
  }
  if (isCheckingUpdates) {
    return {
      label: t('activityCheckingUpdates'),
      detail: 'Checking GitHub releases for SPECTRA updates',
      dot: 'bg-sky-400 animate-pulse',
      cls: 'bg-zinc-900/80 border-sky-700/70 text-sky-300',
    };
  }
  if (hardwareError) {
    return {
      label: t('activityCommError'),
      detail: hardwareError,
      dot: 'bg-rose-500',
      cls: 'bg-rose-950/70 border-rose-500/70 text-rose-200',
    };
  }
  if (isConnected && isPolling) {
    return {
      label: t('activityMonitoring'),
      detail: selectedPort ? `Live polling ${selectedPort}` : 'Live telemetry polling',
      dot: 'bg-emerald-400 animate-pulse',
      cls: 'bg-black/40 border-emerald-500/40 text-emerald-400',
    };
  }
  if (isConnected) {
    return {
      label: t('activityReady'),
      detail: selectedPort ? `Connected to ${selectedPort}` : 'Ready',
      dot: 'bg-emerald-400',
      cls: 'bg-black/40 border-emerald-600/35 text-emerald-300',
    };
  }
  return {
    label: t('activityIdle'),
    detail: connectionStatusText || 'Idle',
    dot: 'bg-zinc-500',
    cls: 'bg-black/40 border-zinc-700 text-zinc-400',
  };
}
