import React from 'react';
import { Cpu, Power, AlertTriangle } from 'lucide-react';

/**
 * Global AI Progress & Kill-Switch Status Bar.
 * Visible across all tabs whenever any Local AI task or model download is active.
 * Always gives the user a 1-click button to turn AI OFF immediately.
 */
export default function AiStatusBar({
  aiEnabled,
  aiTask,
  aiDownload,
  onTurnAiOff,
}) {
  const isTaskActive = Boolean(aiTask?.active);
  const isDlActive = Boolean(aiDownload?.active);

  if (!isTaskActive && !isDlActive) {
    return null;
  }

  const label = isTaskActive
    ? aiTask.task_label || 'Local AI Task'
    : aiDownload.phase_label || 'Downloading Local AI Model';

  const detail = isTaskActive
    ? aiTask.detail || aiTask.step || 'Processing...'
    : aiDownload.status_text || 'Downloading...';

  const model = isTaskActive ? aiTask.model : aiDownload.model;
  const percent = isTaskActive
    ? Math.min(100, Math.max(2, Number(aiTask.percent || 0)))
    : Math.min(100, Math.max(2, Number(aiDownload.percent || 0)));

  const current = isTaskActive ? aiTask.current : null;
  const total = isTaskActive ? aiTask.total : null;
  const eta = isTaskActive ? aiTask.eta_seconds : aiDownload.eta_sec;

  return (
    <div className="bg-[#0B0D14]/95 border-b border-purple-500/60 px-4 py-2 font-mono text-xs backdrop-blur shadow-[0_4px_20px_rgba(168,85,247,0.18)]">
      <div className="flex flex-wrap items-center justify-between gap-2 mb-1.5">
        <div className="flex items-center space-x-2 min-w-0">
          <span className="inline-block w-2 h-2 rounded-full bg-[#00F0FF] animate-ping shrink-0" />
          <Cpu className="w-3.5 h-3.5 text-[#FCEE09] shrink-0" />
          <span className="font-extrabold uppercase tracking-wider text-[#FCEE09] shrink-0">
            {label}
          </span>
          {model && (
            <span className="px-1.5 py-0.5 text-[10px] rounded bg-purple-950/90 border border-purple-600/60 text-purple-200 shrink-0">
              {model}
            </span>
          )}
          <span className="text-zinc-300 truncate">{detail}</span>
        </div>

        <div className="flex items-center space-x-3 shrink-0">
          {total > 0 && (
            <span className="text-[11px] text-zinc-400">
              [{current || 0}/{total}]
            </span>
          )}
          {eta > 0 && (
            <span className="text-[11px] text-amber-400">
              ~{Math.ceil(eta)}s ETA
            </span>
          )}
          <span className="font-extrabold text-[#00F0FF] text-xs">
            {Math.round(percent)}%
          </span>
          <button
            onClick={onTurnAiOff}
            className="flex items-center space-x-1 px-2.5 py-0.5 rounded bg-rose-950 hover:bg-rose-800 border border-rose-500 text-rose-200 font-bold text-[10px] uppercase tracking-wider transition-colors cursor-pointer"
            title="Stop active AI task, unload model, and turn Local AI OFF"
          >
            <Power className="w-3 h-3" />
            <span>TURN AI OFF</span>
          </button>
        </div>
      </div>

      <div className="w-full h-2 bg-black/75 rounded-full overflow-hidden border border-purple-900/70 p-[1px]">
        <div
          className="h-full rounded-full bg-gradient-to-r from-[#FCEE09] via-[#00F0FF] to-purple-500 transition-all duration-300 shadow-[0_0_10px_rgba(0,240,255,0.5)]"
          style={{ width: `${percent}%` }}
        />
      </div>

      {!aiEnabled && isTaskActive && (
        <div className="mt-1 flex items-center space-x-1 text-[10px] text-amber-300">
          <AlertTriangle className="w-3 h-3" />
          <span>Stopping AI task and unloading model...</span>
        </div>
      )}
    </div>
  );
}
