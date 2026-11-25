import React from 'react';
import {
  Terminal,
  Play,
  Pause,
  SlidersHorizontal,
  Trash2,
} from 'lucide-react';
import OscilloscopeStripChart from '../OscilloscopeStripChart';
import DigitalTwinSchematic from '../DigitalTwinSchematic';
import RawFrameInspector from '../RawFrameInspector';
import { txVal } from '../../i18n/translations';

export default function SensorsTabView({
  theme,
  lang,
  t,
  liveData,
  statsData,
  selectedPort,
  effectiveBuild,
  telem,
  beansOk,
  opticalDelta,
  busEvents,
  setBusEvents,
  isStreamPaused,
  setIsStreamPaused,
}) {
  const liveCaps = liveData?.capabilities || {};
  const showAsShuntCard = Boolean(
    liveCaps.has_as_shunt ||
    telem.bean_adcs ||
    telem.heater_ntc_shunt_ratio != null
  );
  const switchesList = Array.isArray(liveData?.switches) ? liveData.switches : [];
  const sensorsList = Array.isArray(liveData?.sensors) ? liveData.sensors : [];
  const okSensorsCount = sensorsList.filter((s) => s.ok !== false).length;

  return (
    <div className="space-y-4">
      {/* Top Paned Layout: Left Digital Twin / Right Oscilloscope & Event Stream */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-4">
        {/* LEFT COLUMN: Interactive Digital Twin & Component Inspector */}
        <div className="lg:col-span-6 space-y-3">
          <DigitalTwinSchematic
            theme={theme}
            lang={lang}
            liveData={liveData}
            statsData={statsData}
          />

          {/* Coffee Heater NTC Diagnostic Sensor Card (AS: Check Sensor — shown only when supported) */}
          {showAsShuntCard && (
            <div className={`p-3.5 border rounded ${theme.surfaceClass}`}>
              <div className="flex flex-wrap items-center justify-between gap-2 border-b border-gray-800 pb-1.5 mb-2">
                <span className="text-xs font-bold text-amber-400 uppercase tracking-wider flex items-center space-x-1.5">
                  <SlidersHorizontal className="w-3.5 h-3.5" />
                  <span>{t('ntcSensorCardTitle')}</span>
                </span>
                <span className="text-[11px] font-mono text-gray-400">
                  {t('shuntLabel')}{' '}
                  <strong className="text-amber-400">
                    {telem.heater_ntc_shunt_ratio
                      ? `${telem.heater_ntc_shunt_ratio} (+${telem.heater_ntc_shunt_gain_pct}%)`
                      : opticalDelta != null
                      ? `Delta: ${opticalDelta}`
                      : t('kpiStandby')}
                  </strong>
                </span>
              </div>
              <div className="space-y-1.5 text-xs">
                <div className="flex justify-between font-mono text-[11px]">
                  <span className="text-gray-400">
                    {t('selfTestLabel')}{' '}
                    <strong className={telem.heater_ntc_self_test_ok ? 'text-emerald-400' : 'text-amber-400'}>
                      {telem.heater_ntc_self_test_ok
                        ? t('nominalShuntOk')
                        : telem.heater_ntc_self_test_ok === false
                        ? t('outOfRange')
                        : t('kpiStandby')}
                    </strong>
                  </span>
                  <span className="text-amber-400">{t('p518ValidRange')}</span>
                </div>
                <div className="flex items-center justify-between pt-1">
                  <span className="text-[11px] font-mono text-gray-400">
                    {t('ambientOffOn', { off: telem.bean_adcs?.[0] ?? '--', on: telem.bean_adcs?.[1] ?? '--' })}
                  </span>
                  <span
                    className={`text-[10px] font-bold px-2 py-0.5 rounded border ${
                      beansOk === true
                        ? 'bg-emerald-950 text-emerald-400 border-emerald-700'
                        : beansOk === false
                        ? 'bg-rose-950 text-rose-400 border-rose-700'
                        : 'bg-zinc-900 text-zinc-400 border-zinc-700'
                    }`}
                  >
                    {beansOk === true ? t('kpiBeansOk') : beansOk === false ? t('kpiFillBeans') : t('kpiStandby')}
                  </span>
                </div>
              </div>
            </div>
          )}
        </div>

        {/* RIGHT COLUMN: Oscilloscope Strip Chart (Temp over Time) & Event Stream Log */}
        <div className="lg:col-span-6 space-y-3">
          {/* 1. Real-Time Oscilloscope Strip Chart */}
          <OscilloscopeStripChart
            theme={theme}
            lang={lang}
            liveData={liveData}
            selectedPort={selectedPort}
            maxSamples={60}
          />

          {/* 2. Real-Time Bus Event Stream & Safety Log */}
          <div className={`p-3 border rounded ${theme.surfaceClass} space-y-2`}>
            <div className="flex flex-wrap items-center justify-between gap-2 border-b border-gray-800 pb-1.5 text-xs">
              <span className="font-bold text-gray-200 uppercase tracking-wider flex items-center space-x-1.5">
                <Terminal className="w-4 h-4 text-emerald-400" />
                <span>{t('busStreamTitle')}</span>
              </span>
              <div className="flex items-center space-x-1.5">
                <button
                  onClick={() => setIsStreamPaused(!isStreamPaused)}
                  className={`px-2 py-0.5 rounded text-[11px] font-bold font-mono flex items-center space-x-1 ${
                    isStreamPaused ? 'bg-amber-600 text-white' : 'bg-gray-800 hover:bg-gray-700 text-gray-300'
                  }`}
                >
                  {isStreamPaused ? <Play className="w-3 h-3" /> : <Pause className="w-3 h-3" />}
                  <span>{isStreamPaused ? t('btnResume') : t('btnPause')}</span>
                </button>
                <button
                  onClick={() => setBusEvents([])}
                  className="px-2 py-0.5 rounded text-[11px] font-bold font-mono bg-gray-800 hover:bg-gray-700 text-gray-300 flex items-center space-x-1"
                >
                  <Trash2 className="w-3 h-3" />
                  <span>{t('btnClear')}</span>
                </button>
              </div>
            </div>

            {/* Scrolling Log Box */}
            <div className="h-44 bg-black/60 border border-gray-800 rounded p-2 overflow-y-auto font-mono text-[11px] space-y-1 text-gray-300 select-text">
              {busEvents.length === 0 ? (
                <div className="text-gray-600 italic">{t('busStreamEmpty')}</div>
              ) : (
                busEvents.map((evt, idx) => (
                  <div key={idx} className="hover:bg-white/5 py-0.5 px-1 rounded truncate">
                    {evt}
                  </div>
                ))
              )}
            </div>
          </div>
        </div>
      </div>

      {/* Live Raw Telemetry Frame Inspector (Collapsible Multi-Device Engineering Strip) */}
      <RawFrameInspector
        theme={theme}
        lang={lang}
        liveData={liveData}
        statsData={statsData}
        selectedPort={selectedPort}
        liveBuild={effectiveBuild}
      />

      {/* Bottom Row: Dynamic Physical Microswitches & Component Fault / Safety Registers */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {/* Microswitches */}
        <div className={`p-4 border rounded ${theme.surfaceClass}`}>
          <div className="text-xs font-bold text-gray-300 uppercase tracking-wider mb-2.5 flex items-center justify-between border-b border-gray-800 pb-2">
            <span>{t('microswitchesTitle')}</span>
            <span className="text-[10px] font-mono text-emerald-400">
              {t('microswitchesDynamicCount', { count: switchesList.length })}
            </span>
          </div>
          <div className="space-y-1.5">
            {switchesList.length === 0 ? (
              <div className="p-4 text-center text-xs font-mono text-gray-500 italic">
                {t('microswitchesEmpty')}
              </div>
            ) : (
              switchesList.map((sw) => (
                <div key={sw.id} className="flex items-center justify-between p-2 bg-black/40 border border-gray-800/80 rounded text-xs font-mono">
                  <div className="flex items-center space-x-2">
                    <span>{sw.icon}</span>
                    <span className="font-bold text-gray-200">{txVal(lang, sw.name)}</span>
                  </div>
                  <div className="flex items-center space-x-2">
                    <span className="text-gray-400">{txVal(lang, sw.status)}</span>
                    <span className={`px-2 py-0.5 rounded text-[10px] font-bold ${sw.ok ? 'bg-emerald-950 text-emerald-400 border border-emerald-700' : 'bg-rose-950 text-rose-400 border border-rose-700'}`}>
                      {txVal(lang, sw.badge)}
                    </span>
                  </div>
                </div>
              ))
            )}
          </div>
        </div>

        {/* Component Fault & Safety Diagnostic Registers */}
        <div className={`p-4 border rounded ${theme.surfaceClass}`}>
          <div className="text-xs font-bold text-gray-300 uppercase tracking-wider mb-2.5 flex items-center justify-between border-b border-gray-800 pb-2">
            <span>{t('faultRegistersTitle')}</span>
            <span className="text-[10px] font-mono text-sky-400">
              {t('faultRegistersDynamicCount', { ok: okSensorsCount, total: sensorsList.length })}
            </span>
          </div>
          <div className="max-h-[300px] overflow-y-auto space-y-1.5 pr-1">
            {sensorsList.length === 0 ? (
              <div className="p-4 text-center text-xs font-mono text-gray-500 italic">
                {t('faultRegistersEmpty')}
              </div>
            ) : (
              sensorsList.map((s) => (
                <div key={s.id} className="flex items-center justify-between p-1.5 bg-black/40 border border-gray-800/60 rounded text-xs font-mono">
                  <span className="text-gray-300">{txVal(lang, s.name)}</span>
                  <div className="flex items-center space-x-2">
                    <span className="text-[11px] text-gray-400">{txVal(lang, s.status)}</span>
                    <span className={`px-1.5 py-0.2 rounded text-[9px] font-bold ${s.ok ? 'bg-emerald-950 text-emerald-400' : 'bg-rose-950 text-rose-400'}`}>
                      {txVal(lang, s.badge)}
                    </span>
                  </div>
                </div>
              ))
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
