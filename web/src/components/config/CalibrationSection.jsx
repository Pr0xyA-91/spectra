import React from 'react';
import { Database, Trash2, Sliders } from 'lucide-react';

export default function CalibrationSection({
  t,
  overrideEntries,
  loadOverridesAndCalib,
  handleDeleteOverride,
  beanCalib,
  thresholdInput,
  setThresholdInput,
  handleSaveThreshold,
  handleResetThreshold,
}) {
  return (
    <div className="space-y-4">
      {/* Saved Local EEPROM Offset Overrides */}
      <div className="p-3.5 bg-black/40 border border-zinc-800 rounded space-y-2.5">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2 font-bold text-white">
            <Database className="w-4 h-4 text-emerald-400" />
            <span>{t('cfgOverridesTitle', { count: overrideEntries.length })}</span>
          </div>
          <button
            type="button"
            onClick={loadOverridesAndCalib}
            className="text-[10px] text-zinc-400 hover:text-white underline cursor-pointer"
          >
            {t('cfgBtnRefresh')}
          </button>
        </div>

        {overrideEntries.length === 0 ? (
          <div className="p-2.5 bg-zinc-950 border border-zinc-800 rounded text-[11px] text-zinc-400">
            {t('cfgOverridesEmpty')}
          </div>
        ) : (
          <div className="space-y-1.5 max-h-44 overflow-y-auto">
            {overrideEntries.map(([key, ov]) => (
              <div
                key={key}
                className="flex items-center justify-between p-2.5 bg-zinc-950 border border-zinc-800 rounded text-[11px]"
              >
                <div>
                  <div className="text-emerald-300 font-bold">
                    {ov.model_name || key}{' '}
                    <span className="text-zinc-500">({key})</span>
                  </div>
                  <div className="text-[10px] text-zinc-400">
                    {t('cfgOverrideMeta', {
                      products: (ov.products || []).length,
                      maintenance: (ov.maintenance || []).length,
                      updated: ov.updated_at || t('cfgUpdatedRecently'),
                    })}
                  </div>
                </div>
                <button
                  type="button"
                  onClick={() => handleDeleteOverride(key)}
                  className="px-2 py-1 bg-rose-950/60 hover:bg-rose-900/70 border border-rose-700 text-rose-300 rounded text-[10px] font-bold flex items-center gap-1 cursor-pointer"
                >
                  <Trash2 className="w-3 h-3" />
                  <span>{t('cfgBtnRevert')}</span>
                </button>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Optical Bean Sensor Threshold */}
      <div className="p-3.5 bg-black/40 border border-zinc-800 rounded space-y-2.5">
        <div className="font-bold text-white flex items-center gap-2">
          <Sliders className="w-4 h-4 text-[#FCEE09]" />
          <span>{t('cfgBeanThresholdTitle')}</span>
        </div>
        <p className="text-[11px] text-zinc-400">
          {t('cfgBeanThresholdDesc', { min: beanCalib.min_threshold ?? 30, max: beanCalib.max_threshold ?? 250 })}
        </p>
        <div className="flex items-center gap-3">
          <input
            type="range"
            min={beanCalib.min_threshold ?? 30}
            max={beanCalib.max_threshold ?? 250}
            value={thresholdInput}
            onChange={(e) => setThresholdInput(Number(e.target.value))}
            className="flex-1 accent-[#FCEE09]"
          />
          <span className="w-12 text-center font-bold text-[#FCEE09] bg-zinc-950 border border-zinc-700 rounded py-1">
            {thresholdInput}
          </span>
          <button
            type="button"
            onClick={handleSaveThreshold}
            className="px-3 py-1.5 bg-[#FCEE09] hover:bg-yellow-400 text-black font-extrabold rounded text-xs cursor-pointer"
          >
            {t('cfgBtnSave')}
          </button>
          <button
            type="button"
            onClick={handleResetThreshold}
            className="px-2.5 py-1.5 bg-zinc-800 hover:bg-zinc-700 text-zinc-300 border border-zinc-700 rounded text-xs cursor-pointer"
          >
            {t('cfgBtnReset')}
          </button>
        </div>
      </div>
    </div>
  );
}
