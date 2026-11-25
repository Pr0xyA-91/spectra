import React from 'react';
import { txVal } from '../../i18n/translations';

function KpiRibbon({
  theme,
  lang,
  t,
  hasTelem,
  telem,
  statsData,
  totalPreps,
  totalCups,
  coffeeTemp,
  buPos,
  buUpper,
  flowRate,
  beansOk,
  tankSw,
  traySw,
  beansSw,
  cleanCount,
  decalcCount,
}) {
  return (
    <section className={`px-4 py-2.5 border-b ${theme.border} ${theme.panelBg}`}>
      <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-5 lg:grid-cols-9 gap-2">
        {/* 1. Total Preps */}
        <div className={`p-2 bg-black/40 border border-gray-800 rounded ${theme.clipClass}`}>
          <div className="text-[10px] text-gray-500 font-bold uppercase tracking-wider">
            {t('kpiTotalPreps')}
          </div>
          <div className="text-xs font-bold font-mono my-1 text-white">
            {totalPreps != null ? totalPreps : '---'}
          </div>
          <div className="text-[10px] text-gray-500 truncate">
            {totalCups != null ? t('kpiTotalCups', { cups: totalCups }) : t('kpiAwaitingRead')}
          </div>
        </div>

        {/* 2. Thermoblock TB1 */}
        <div className={`p-2 bg-black/40 border border-gray-800 rounded ${theme.clipClass}`}>
          <div className="text-[10px] text-gray-500 font-bold uppercase tracking-wider">
            {t('kpiTb1Heater')}
          </div>
          <div className={`text-xs font-bold font-mono my-1 ${theme.textPrimary}`}>
            {coffeeTemp != null ? `${coffeeTemp.toFixed(1)} °C` : '--- °C'}
          </div>
          <div className="text-[10px] text-gray-500 truncate">
            {hasTelem ? (telem.heater_coffee_status ? txVal(lang, telem.heater_coffee_status) : t('kpiReadyToBrew')) : t('kpiStandby')}
          </div>
        </div>

        {/* 3. Brew Unit Encoder */}
        <div className={`p-2 bg-black/40 border border-gray-800 rounded ${theme.clipClass}`}>
          <div className="text-[10px] text-gray-500 font-bold uppercase tracking-wider">
            {t('kpiBuEncoder')}
          </div>
          <div className="text-xs font-bold font-mono my-1 text-purple-400">
            {buPos != null ? `${buPos} / ${buUpper ?? '---'}` : '--- / ---'}
          </div>
          <div className="text-[10px] text-gray-500 truncate">
            {hasTelem ? (telem.bu_position_state || t('kpiOpticalQuad')) : t('kpiStandby')}
          </div>
        </div>

        {/* 4. Water Flow */}
        <div className={`p-2 bg-black/40 border border-gray-800 rounded ${theme.clipClass}`}>
          <div className="text-[10px] text-gray-500 font-bold uppercase tracking-wider">
            {t('kpiWaterFlow')}
          </div>
          <div className="text-xs font-bold font-mono my-1 text-cyan-400">
            {flowRate != null ? `${flowRate.toFixed(1)} ml/s` : '--- ml/s'}
          </div>
          <div className="text-[10px] text-gray-500 truncate">
            {hasTelem ? t('kpiFlowVol', { vol: (telem.flow_volume_ml ?? 0).toFixed(1) }) : t('kpiStandby')}
          </div>
        </div>

        {/* 5. Water Tank */}
        <div className={`p-2 bg-black/40 border border-gray-800 rounded ${theme.clipClass}`}>
          <div className="text-[10px] text-gray-500 font-bold uppercase tracking-wider">
            {t('kpiWaterTank')}
          </div>
          <div className={`text-xs font-bold font-mono my-1 ${tankSw ? (tankSw.ok ? 'text-emerald-400' : 'text-rose-400') : 'text-zinc-500'}`}>
            {tankSw ? (tankSw.ok ? t('kpiWaterOk') : t('kpiWaterEmpty')) : '---'}
          </div>
          <div className="text-[10px] text-gray-500 truncate">{hasTelem ? t('kpiFloatSwitch') : t('kpiStandby')}</div>
        </div>

        {/* 6. Drip Tray */}
        <div className={`p-2 bg-black/40 border border-gray-800 rounded ${theme.clipClass}`}>
          <div className="text-[10px] text-gray-500 font-bold uppercase tracking-wider">
            {t('kpiDripTray')}
          </div>
          <div className={`text-xs font-bold font-mono my-1 ${traySw ? (traySw.ok ? 'text-emerald-400' : 'text-rose-400') : 'text-zinc-500'}`}>
            {traySw ? (traySw.ok ? t('kpiInserted') : t('kpiMissing')) : '---'}
          </div>
          <div className="text-[10px] text-gray-500 truncate">{hasTelem ? t('kpiContactSwitch') : t('kpiStandby')}</div>
        </div>

        {/* 7. Bean Hopper */}
        <div className={`p-2 bg-black/40 border border-gray-800 rounded ${theme.clipClass}`} title={beansSw?.details || beansSw?.status || ''}>
          <div className="text-[10px] text-gray-500 font-bold uppercase tracking-wider">
            {t('kpiBeanHopper')}
          </div>
          <div className={`text-xs font-bold font-mono my-1 ${beansSw ? (beansSw.ok ? 'text-emerald-400' : 'text-rose-400') : (beansOk != null ? (beansOk ? 'text-emerald-400' : 'text-rose-400') : 'text-zinc-500')}`}>
            {beansSw?.details?.includes('Monitored Locally')
              ? t('kpiLocalEf518d')
              : (beansSw ? (beansSw.ok ? t('kpiBeansOk') : t('kpiFillBeans')) : (beansOk != null ? (beansOk ? t('kpiBeansOk') : t('kpiFillBeans')) : '---'))}
          </div>
          <div className="text-[10px] text-gray-500 truncate" title={beansSw?.details || beansSw?.status || ''}>
            {beansSw?.details ? txVal(lang, beansSw.details) : (beansOk != null ? (beansOk ? t('kpiHopperCharged') : t('kpiFillBeans')) : t('kpiStandby'))}
          </div>
        </div>

        {/* 8. Cleanings */}
        <div className={`p-2 bg-black/40 border border-gray-800 rounded ${theme.clipClass}`}>
          <div className="text-[10px] text-gray-500 font-bold uppercase tracking-wider">
            {t('kpiCleanings')}
          </div>
          <div className="text-xs font-bold font-mono my-1 text-sky-400">
            {cleanCount != null ? t('kpiCyclesCount', { count: cleanCount }) : '---'}
          </div>
          <div className="text-[10px] text-gray-500 truncate">
            {statsData ? t('kpiMaintRecord') : t('kpiAwaitingRead')}
          </div>
        </div>

        {/* 9. Descalings */}
        <div className={`p-2 bg-black/40 border border-gray-800 rounded ${theme.clipClass}`}>
          <div className="text-[10px] text-gray-500 font-bold uppercase tracking-wider">
            {t('kpiDecalcs')}
          </div>
          <div className="text-xs font-bold font-mono my-1 text-amber-400">
            {decalcCount != null ? t('kpiCyclesCount', { count: decalcCount }) : '---'}
          </div>
          <div className="text-[10px] text-gray-500 truncate">
            {statsData ? t('kpiMaintRecord') : t('kpiAwaitingRead')}
          </div>
        </div>
      </div>
    </section>
  );
}

export default React.memo(KpiRibbon);
