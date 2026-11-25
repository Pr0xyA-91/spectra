import React from 'react';
import { Cpu, X, Settings, Download } from 'lucide-react';

const FALLBACK_AI_PROMPT_MODELS = [
  { id: 'qwen2.5:0.5b', name: 'Qwen 2.5 0.5B (Ultra-Light)', disk_mb: 398, is_recommended: true },
  { id: 'gemma3:1b', name: 'Gemma 3 1B (Google Ultra-Light)', disk_mb: 815 },
  { id: 'qwen2.5:1.5b', name: 'Qwen 2.5 1.5B (Balanced)', disk_mb: 986 },
  { id: 'gemma3:4b', name: 'Gemma 3 4B (Google Vision + Text)', disk_mb: 3400 },
];

export default function NoAiModelPromptModal({
  show,
  theme,
  t,
  aiSystem,
  noModelPromptChoice,
  setNoModelPromptChoice,
  onClose,
  onOpenConfig,
  onStartPull,
}) {
  if (!show) return null;

  const recommended = aiSystem?.hardware?.recommended_model || 'qwen2.5:0.5b';
  const chosenModel = noModelPromptChoice || recommended;
  const catalog =
    Array.isArray(aiSystem?.hardware?.model_catalog) && aiSystem.hardware.model_catalog.length > 0
      ? aiSystem.hardware.model_catalog
      : FALLBACK_AI_PROMPT_MODELS;

  return (
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
            onClick={onClose}
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
                {recommended}
              </span>
            </div>
            <select
              value={chosenModel}
              onChange={(e) => setNoModelPromptChoice(e.target.value)}
              className="w-full bg-zinc-950 border border-zinc-700 rounded px-2.5 py-2 text-xs text-white outline-none focus:border-[#00F0FF]"
            >
              {catalog.map((m) => (
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
              onClose();
              onOpenConfig();
            }}
            className="px-2.5 py-1.5 bg-zinc-900 hover:bg-zinc-800 border border-zinc-700 text-zinc-300 rounded font-bold cursor-pointer flex items-center gap-1"
          >
            <Settings className="w-3.5 h-3.5 text-[#FCEE09]" />
            <span>{t('aiNoModelBtnOpenConfig')}</span>
          </button>

          <div className="flex items-center gap-2 ml-auto">
            <button
              type="button"
              onClick={onClose}
              className="px-2.5 py-1.5 bg-zinc-900 hover:bg-zinc-800 border border-zinc-700 text-zinc-300 rounded cursor-pointer"
            >
              {t('cfgBtnKeepCurrentModel')}
            </button>
            <button
              type="button"
              onClick={() => onStartPull(chosenModel)}
              className="px-3 py-1.5 bg-[#00F0FF] hover:bg-cyan-300 text-black font-extrabold rounded flex items-center gap-1.5 cursor-pointer"
            >
              <Download className="w-3.5 h-3.5" />
              <span>
                {t('aiNoModelBtnDownloadAndEnable', { model: chosenModel })}
              </span>
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
