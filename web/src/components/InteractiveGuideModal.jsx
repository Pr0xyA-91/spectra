import React, { useState, useEffect, useMemo } from 'react';
import {
  Compass,
  X,
  Globe,
  Radio,
  Sparkles,
  Layers,
  Cpu,
  Sliders,
  CheckCircle2,
  ShieldAlert,
  Play,
  Settings,
} from 'lucide-react';
import { createTranslator, SUPPORTED_LANGUAGES } from '../i18n/translations';

const TOTAL_STEPS = 7;

export default function InteractiveGuideModal({
  isOpen,
  onClose,
  theme,
  lang = 'en',
  onChangeLang = () => {},
  showOnStartup = false,
  onSetShowOnStartup = () => {},
  hasStats = false,
  isInterrogating = false,
  onSelectDemoPort = () => {},
  onRunInterrogate = () => {},
  onSwitchTab = () => {},
  onOpenConfig = () => {},
  onJumpToOffsetCalibrator = () => {},
}) {
  const t = useMemo(() => createTranslator(lang), [lang]);
  const [step, setStep] = useState(1);

  useEffect(() => {
    if (isOpen) {
      setStep(1);
    }
  }, [isOpen]);

  useEffect(() => {
    if (!isOpen) return;
    const onKey = (e) => {
      if (e.key === 'Escape') {
        onClose(false);
      } else if (e.key === 'ArrowRight' && step < TOTAL_STEPS) {
        setStep((s) => Math.min(TOTAL_STEPS, s + 1));
      } else if (e.key === 'ArrowLeft' && step > 1) {
        setStep((s) => Math.max(1, s - 1));
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [isOpen, step, onClose]);

  // Automatically navigate workspace tabs as the user steps through the tour
  useEffect(() => {
    if (!isOpen) return;
    if (step === 4) {
      onSwitchTab('overview');
    } else if (step === 6) {
      onSwitchTab('overview');
    }
  }, [isOpen, step, onSwitchTab]);

  if (!isOpen) return null;

  const isCentered = step === 1 || step === TOTAL_STEPS;
  const pct = Math.round((step / TOTAL_STEPS) * 100);

  const stepIcon = {
    1: <Compass className="w-5 h-5 text-[#FCEE09]" />,
    2: <Radio className="w-5 h-5 text-[#00F0FF]" />,
    3: <Sparkles className="w-5 h-5 text-purple-400" />,
    4: <Layers className="w-5 h-5 text-emerald-400" />,
    5: <Cpu className="w-5 h-5 text-purple-400" />,
    6: <Sliders className="w-5 h-5 text-amber-400" />,
    7: <CheckCircle2 className="w-5 h-5 text-emerald-400" />,
  }[step];

  return (
    <div
      className={
        isCentered
          ? 'fixed inset-0 z-50 flex items-center justify-center bg-black/75 backdrop-blur-sm p-4'
          : 'fixed bottom-5 right-5 z-50 w-[calc(100vw-2rem)] max-w-md pointer-events-auto'
      }
    >
      <div
        className={`w-full ${isCentered ? 'max-w-lg' : ''} border-2 border-[#FCEE09]/70 ${theme?.panelBg || 'bg-[#0E0E12]/95'} rounded-xl shadow-[0_0_35px_rgba(0,0,0,0.85)] overflow-hidden font-mono flex flex-col`}
      >
        {/* Top Header */}
        <div className="flex items-center justify-between px-4 py-3 bg-[#14141c] border-b border-zinc-800">
          <div className="flex items-center space-x-2">
            {stepIcon}
            <span className="text-xs font-extrabold tracking-wider text-[#FCEE09] uppercase">
              {t('guideHeaderBadge')}
            </span>
            <span className="text-[10px] px-2 py-0.5 rounded bg-zinc-900 border border-zinc-700 text-zinc-300 font-bold">
              {t('guideStepOf', { step, total: TOTAL_STEPS })}
            </span>
          </div>
          <button
            type="button"
            onClick={() => onClose(false)}
            className="text-zinc-400 hover:text-white p-1 rounded hover:bg-zinc-800 cursor-pointer"
            title={t('guideBtnSkip')}
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Step Progress Bar */}
        <div className="w-full h-1 bg-zinc-900">
          <div
            className="h-full bg-gradient-to-r from-[#FCEE09] via-[#00F0FF] to-purple-500 transition-all duration-300"
            style={{ width: `${pct}%` }}
          />
        </div>

        {/* Step Body */}
        <div className="p-5 space-y-4 text-xs">
          {step === 1 && (
            <div className="space-y-3.5">
              <h3 className="text-base font-black text-white">{t('guideStep1Title')}</h3>
              <p className="text-zinc-300 leading-relaxed font-sans text-sm">
                {t('guideStep1Body')}
              </p>

              {/* Language Quick-Pick */}
              <div className="p-3 bg-black/50 border border-zinc-800 rounded-lg space-y-2">
                <div className="flex items-center space-x-2 text-zinc-200 font-bold text-xs">
                  <Globe className="w-4 h-4 text-[#00F0FF]" />
                  <span>{t('guideStep1LangPrompt')}</span>
                </div>
                <div className="flex flex-wrap gap-2">
                  {SUPPORTED_LANGUAGES.map((l) => {
                    const active = lang === l.id;
                    return (
                      <button
                        key={l.id}
                        type="button"
                        onClick={() => onChangeLang(l.id)}
                        className={`flex-1 py-2 px-3 rounded font-bold text-xs border transition-all cursor-pointer ${
                          active
                            ? 'bg-[#00F0FF]/20 border-[#00F0FF] text-[#00F0FF] shadow-[0_0_12px_rgba(0,240,255,0.25)]'
                            : 'bg-zinc-900 border-zinc-700 text-zinc-300 hover:text-white hover:border-zinc-500'
                        }`}
                      >
                        {l.label} ({l.short})
                      </button>
                    );
                  })}
                </div>
              </div>

              <p className="text-[11px] text-zinc-400 font-sans">
                {t('guideStep1Note')}
              </p>
            </div>
          )}

          {step === 2 && (
            <div className="space-y-3">
              <h3 className="text-sm font-black text-[#00F0FF]">{t('guideStep2Title')}</h3>
              <p className="text-zinc-300 leading-relaxed font-sans text-[13px]">
                {t('guideStep2Body')}
              </p>
              <div className="p-2.5 bg-amber-950/30 border border-amber-700/50 rounded text-[11px] text-amber-200 flex items-start gap-2 font-sans">
                <ShieldAlert className="w-4 h-4 text-amber-400 shrink-0 mt-0.5" />
                <span>{t('guideStep2Safety')}</span>
              </div>
              <button
                type="button"
                onClick={onSelectDemoPort}
                className="w-full py-2 px-3 bg-sky-700 hover:bg-sky-600 text-white font-bold rounded text-xs flex items-center justify-center gap-2 cursor-pointer transition-colors"
              >
                <Play className="w-3.5 h-3.5" />
                <span>{t('guideStep2Action')}</span>
              </button>
            </div>
          )}

          {step === 3 && (
            <div className="space-y-3">
              <h3 className="text-sm font-black text-purple-300">{t('guideStep3Title')}</h3>
              <p className="text-zinc-300 leading-relaxed font-sans text-[13px]">
                {t('guideStep3Body')}
              </p>
              <button
                type="button"
                onClick={onRunInterrogate}
                disabled={isInterrogating}
                className="w-full py-2 px-3 bg-purple-700 hover:bg-purple-600 disabled:opacity-50 text-white font-bold rounded text-xs flex items-center justify-center gap-2 cursor-pointer transition-colors"
              >
                <Sparkles className="w-3.5 h-3.5" />
                <span>
                  {hasStats ? t('guideStep3ActionDone') : t('guideStep3Action')}
                </span>
              </button>
            </div>
          )}

          {step === 4 && (
            <div className="space-y-3">
              <h3 className="text-sm font-black text-emerald-300">{t('guideStep4Title')}</h3>
              <p className="text-zinc-300 leading-relaxed font-sans text-[13px]">
                {t('guideStep4Body')}
              </p>
              <div className="flex flex-wrap gap-2">
                <button
                  type="button"
                  onClick={() => onSwitchTab('overview')}
                  className="flex-1 py-1.5 px-2.5 bg-zinc-800 hover:bg-zinc-700 border border-zinc-600 text-zinc-200 font-bold rounded text-[11px] cursor-pointer"
                >
                  {t('guideStep4ActionOverview')}
                </button>
                <button
                  type="button"
                  onClick={() => onSwitchTab('sensors')}
                  className="flex-1 py-1.5 px-2.5 bg-zinc-800 hover:bg-zinc-700 border border-zinc-600 text-zinc-200 font-bold rounded text-[11px] cursor-pointer"
                >
                  {t('guideStep4ActionSensors')}
                </button>
              </div>
            </div>
          )}

          {step === 5 && (
            <div className="space-y-3">
              <h3 className="text-sm font-black text-purple-300">{t('guideStep5Title')}</h3>
              <p className="text-zinc-300 leading-relaxed font-sans text-[13px]">
                {t('guideStep5Body')}
              </p>
              <button
                type="button"
                onClick={() => onOpenConfig('ai')}
                className="w-full py-2 px-3 bg-zinc-800 hover:bg-zinc-700 border border-purple-500/60 text-purple-200 font-bold rounded text-xs flex items-center justify-center gap-2 cursor-pointer"
              >
                <Settings className="w-3.5 h-3.5 text-[#FCEE09]" />
                <span>{t('guideStep5Action')}</span>
              </button>
            </div>
          )}

          {step === 6 && (
            <div className="space-y-3">
              <h3 className="text-sm font-black text-amber-300">{t('guideStep6Title')}</h3>
              <p className="text-zinc-300 leading-relaxed font-sans text-[13px]">
                {t('guideStep6Body')}
              </p>
              <button
                type="button"
                onClick={onJumpToOffsetCalibrator}
                className="w-full py-2 px-3 bg-amber-600 hover:bg-amber-500 text-black font-extrabold rounded text-xs flex items-center justify-center gap-2 cursor-pointer"
              >
                <Sliders className="w-3.5 h-3.5" />
                <span>{t('guideStep6Action')}</span>
              </button>
            </div>
          )}

          {step === 7 && (
            <div className="space-y-3.5">
              <h3 className="text-base font-black text-emerald-400">{t('guideStep7Title')}</h3>
              <p className="text-zinc-300 leading-relaxed font-sans text-sm">
                {t('guideStep7Body')}
              </p>
              <label className="flex items-center space-x-2 text-xs text-zinc-300 cursor-pointer pt-1 font-sans">
                <input
                  type="checkbox"
                  checked={Boolean(showOnStartup)}
                  onChange={(e) => onSetShowOnStartup(e.target.checked)}
                  className="rounded bg-black border-zinc-700 text-[#00F0FF]"
                />
                <span>{t('guideStep7KeepStartup')}</span>
              </label>
            </div>
          )}
        </div>

        {/* Step Dots + Navigation Footer */}
        <div className="px-4 py-3 bg-black/50 border-t border-zinc-800 flex flex-wrap items-center justify-between gap-2">
          {/* Step Dots */}
          <div className="flex items-center space-x-1.5">
            {Array.from({ length: TOTAL_STEPS }, (_, idx) => {
              const sNum = idx + 1;
              const isCurr = sNum === step;
              return (
                <button
                  key={sNum}
                  type="button"
                  onClick={() => setStep(sNum)}
                  className={`h-2 rounded-full transition-all cursor-pointer ${
                    isCurr
                      ? 'w-5 bg-[#FCEE09]'
                      : sNum < step
                      ? 'w-2 bg-[#00F0FF]/70'
                      : 'w-2 bg-zinc-700 hover:bg-zinc-500'
                  }`}
                  title={t('guideStepOf', { step: sNum, total: TOTAL_STEPS })}
                />
              );
            })}
          </div>

          {/* Nav Buttons */}
          <div className="flex items-center space-x-2 text-xs">
            {step > 1 ? (
              <button
                type="button"
                onClick={() => setStep((s) => Math.max(1, s - 1))}
                className="px-3 py-1.5 rounded bg-zinc-800 hover:bg-zinc-700 border border-zinc-700 text-zinc-200 font-bold cursor-pointer"
              >
                {t('guideBtnBack')}
              </button>
            ) : (
              <button
                type="button"
                onClick={() => onClose(false)}
                className="px-3 py-1.5 rounded bg-zinc-900 hover:bg-zinc-800 border border-zinc-800 text-zinc-400 hover:text-zinc-200 cursor-pointer"
              >
                {t('guideBtnSkip')}
              </button>
            )}

            {step < TOTAL_STEPS ? (
              <button
                type="button"
                onClick={() => setStep((s) => Math.min(TOTAL_STEPS, s + 1))}
                className="px-3.5 py-1.5 rounded bg-[#FCEE09] hover:bg-yellow-400 text-black font-extrabold cursor-pointer"
              >
                {t('guideBtnNext')}
              </button>
            ) : (
              <button
                type="button"
                onClick={() => onClose(true)}
                className="px-3.5 py-1.5 rounded bg-emerald-600 hover:bg-emerald-500 text-white font-extrabold cursor-pointer"
              >
                {t('guideBtnFinish')}
              </button>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
