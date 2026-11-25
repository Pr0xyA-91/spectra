import React from 'react';
import {
  Search,
  CheckCircle2,
  AlertTriangle,
  Send,
  Coffee,
  Wrench,
  Info,
} from 'lucide-react';
import {
  txVal,
  txBeverageName,
  txMaintenanceLabel,
} from '../../i18n/translations';

export const BeveragesTabView = React.memo(function BeveragesTabView({
  theme,
  lang,
  t,
  statsData,
  selectedPort,
  isInterrogating,
  onRunInterrogation,
  bevSearch,
  setBevSearch,
  filteredBeverages,
  totalPreps,
}) {
  return (
    <div className={`p-4 border rounded ${theme.surfaceClass} space-y-3`}>
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-gray-800 pb-2">
        <span className="text-xs font-bold text-gray-300 uppercase tracking-wider flex items-center space-x-1.5">
          <Coffee className="w-4 h-4 text-amber-400" />
          <span>{t('bevRegistryTitle')}</span>
        </span>
        <div className="flex items-center space-x-2">
          <div className="relative">
            <Search className="w-3.5 h-3.5 text-gray-400 absolute left-2.5 top-2" />
            <input
              type="text"
              value={bevSearch}
              onChange={(e) => setBevSearch(e.target.value)}
              placeholder={t('bevSearchPlaceholder')}
              disabled={!statsData}
              className="pl-8 pr-3 py-1 bg-black/40 border border-gray-800 rounded text-xs text-white placeholder-gray-500 outline-none w-48 font-mono disabled:opacity-40"
            />
          </div>
          <span className="text-xs font-mono text-gray-400">
            {statsData ? t('bevSpecialtiesCount', { count: filteredBeverages.length }) : t('bevAwaitingRead')}
          </span>
        </div>
      </div>

      {!statsData ? (
        <div className="p-8 text-center space-y-4 font-mono">
          <div className="w-14 h-14 rounded-full bg-black/40 border border-[#FCEE09]/30 flex items-center justify-center mx-auto text-[#FCEE09]">
            <Coffee className="w-7 h-7 animate-pulse" />
          </div>
          <div className="space-y-1">
            <h3 className="text-sm font-bold text-white uppercase tracking-wider">
              {t('bevEmptyTitle')}
            </h3>
            <p className="text-xs text-zinc-400 max-w-md mx-auto">
              {t('bevEmptyDesc', { port: selectedPort || t('serialPortFallback') })}
            </p>
          </div>
          <div className="pt-1">
            <button
              onClick={onRunInterrogation}
              disabled={isInterrogating || !selectedPort}
              className="px-5 py-2.5 bg-[#FCEE09] hover:bg-yellow-300 text-black font-mono font-bold text-xs uppercase tracking-wider rounded transition-colors disabled:opacity-50"
            >
              {isInterrogating ? t('btnReadingEeprom') : t('btnInterrogateShort')}
            </button>
          </div>
        </div>
      ) : filteredBeverages.length === 0 ? (
        <div className="p-8 text-center text-xs text-zinc-500 font-mono">
          {t('bevNoRecords')}
        </div>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs font-mono">
            <thead>
              <tr className="border-b border-gray-800 text-gray-500 text-[10px] uppercase">
                <th className="py-2 px-3">{t('colCode')}</th>
                <th className="py-2 px-3">{t('colSpecialty')}</th>
                <th className="py-2 px-3">{t('colQty')}</th>
                <th className="py-2 px-3">{t('colShare')}</th>
                <th className="py-2 px-3">{t('colCategory')}</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-800/60">
              {filteredBeverages.map((bev) => (
                <tr key={bev.code} className="hover:bg-white/5 transition-colors">
                  <td className="py-2 px-3 text-gray-500">0x{Number(bev?.code ?? 0).toString(16).padStart(2, '0').toUpperCase()}</td>
                  <td className="py-2 px-3 font-bold text-white">{txBeverageName(lang, bev.name)}</td>
                  <td className="py-2 px-3 text-amber-400 font-bold">{Number(bev?.count ?? 0).toLocaleString()}</td>
                  <td className="py-2 px-3 text-gray-300">
                    {bev.share || (totalPreps > 0 ? `${((bev.count / totalPreps) * 100).toFixed(1)}%` : '0.0%')}
                  </td>
                  <td className="py-2 px-3">
                    <span className={`px-2 py-0.5 rounded text-[10px] font-bold ${
                      bev.type === 'Milk'
                        ? 'bg-purple-950 text-purple-300 border border-purple-800'
                        : bev.type === 'Water'
                        ? 'bg-cyan-950 text-cyan-300 border border-cyan-800'
                        : bev.is_double || bev.type === 'Double'
                        ? 'bg-amber-950 text-amber-300 border border-amber-800'
                        : 'bg-zinc-800 text-zinc-300 border border-zinc-700'
                    }`}>
                      {txVal(lang, bev.type || (bev.is_double ? 'Double' : 'Single'))}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
});

export const MaintenanceTabView = React.memo(function MaintenanceTabView({
  theme,
  lang,
  t,
  statsData,
  selectedPort,
  isInterrogating,
  onRunInterrogation,
  cleanCount,
  decalcCount,
  totalPreps,
  filterSw,
}) {
  return (
    <div className={`p-4 border rounded ${theme.surfaceClass} space-y-4`}>
      <div className="text-xs font-bold text-gray-300 uppercase tracking-wider border-b border-gray-800 pb-2 flex items-center space-x-1.5">
        <Wrench className="w-4 h-4 text-sky-400" />
        <span>{t('maintTitle')}</span>
      </div>

      {!statsData ? (
        <div className="p-8 text-center space-y-4 font-mono">
          <div className="w-14 h-14 rounded-full bg-black/40 border border-[#FCEE09]/30 flex items-center justify-center mx-auto text-[#FCEE09]">
            <Wrench className="w-7 h-7 animate-pulse" />
          </div>
          <div className="space-y-1">
            <h3 className="text-sm font-bold text-white uppercase tracking-wider">
              {t('maintEmptyTitle')}
            </h3>
            <p className="text-xs text-zinc-400 max-w-md mx-auto">
              {t('maintEmptyDesc', { port: selectedPort || t('serialPortFallback') })}
            </p>
          </div>
          <div className="pt-1">
            <button
              onClick={onRunInterrogation}
              disabled={isInterrogating || !selectedPort}
              className="px-5 py-2.5 bg-[#FCEE09] hover:bg-yellow-300 text-black font-mono font-bold text-xs uppercase tracking-wider rounded transition-colors disabled:opacity-50"
            >
              {isInterrogating ? t('btnReadingEeprom') : t('btnInterrogateShort')}
            </button>
          </div>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {/* Wear Percentages */}
          <div className="p-3 bg-black/40 border border-gray-800 rounded space-y-3">
            <div className="text-xs font-bold text-gray-400 uppercase font-mono">
              {t('maintWearBarsTitle')}
            </div>

            {/* Cleaning */}
            <div className="space-y-1">
              <div className="flex justify-between text-xs font-mono">
                <span className="text-gray-300">{t('maintCoffeeClean')}</span>
                <span className="text-emerald-400 font-bold">
                  {cleanCount != null ? t('maintTotalCycles', { count: cleanCount }) : t('maintNominal')}
                </span>
              </div>
              <div className="w-full h-2 bg-gray-800 rounded-full overflow-hidden">
                <div
                  className="h-full bg-emerald-500"
                  style={{ width: `${Math.min(100, Math.max(15, totalPreps ? (totalPreps % 180) / 1.8 : 25))}%` }}
                />
              </div>
            </div>

            {/* Descaling */}
            <div className="space-y-1">
              <div className="flex justify-between text-xs font-mono">
                <span className="text-gray-300">{t('maintTbDescaling')}</span>
                <span className="text-amber-400 font-bold">
                  {decalcCount != null ? t('maintTotalCycles', { count: decalcCount }) : t('maintNominal')}
                </span>
              </div>
              <div className="w-full h-2 bg-gray-800 rounded-full overflow-hidden">
                <div
                  className="h-full bg-amber-500"
                  style={{ width: `${Math.min(100, Math.max(20, totalPreps ? (totalPreps % 350) / 3.5 : 40))}%` }}
                />
              </div>
            </div>

            {/* Filter */}
            <div className="space-y-1">
              <div className="flex justify-between text-xs font-mono">
                <span className="text-gray-300">{t('maintClarisFilter')}</span>
                <span className="text-sky-400 font-bold">
                  {filterSw?.ok ? t('maintFilterActive') : t('maintFilterBypass')}
                </span>
              </div>
              <div className="w-full h-2 bg-gray-800 rounded-full overflow-hidden">
                <div className="h-full bg-sky-500" style={{ width: filterSw?.ok ? '60%' : '0%' }} />
              </div>
            </div>
          </div>

          {/* Maintenance Counters */}
          <div className="p-3 bg-black/40 border border-gray-800 rounded space-y-2">
            <div className="text-xs font-bold text-gray-400 uppercase font-mono mb-2">
              {t('maintCounterAuditTitle')}
            </div>
            <div className="space-y-1.5 font-mono text-xs">
              {statsData.maintenance && statsData.maintenance.length > 0 ? (
                statsData.maintenance.map((m, idx) => (
                  <div key={idx} className="flex justify-between py-1 border-b border-gray-800/60 last:border-0">
                    <span className="text-gray-400">{txMaintenanceLabel(lang, m.label || m.name)}:</span>
                    <strong className="text-white">{m.count?.toLocaleString() ?? 0} {t('maintCyclesSuffix')}</strong>
                  </div>
                ))
              ) : (
                <div className="text-zinc-500 text-xs py-2">{t('maintNoRecords')}</div>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
});

export const AlertsTabView = React.memo(function AlertsTabView({
  theme,
  t,
  statsData,
  selectedPort,
  isInterrogating,
  onRunInterrogation,
}) {
  return (
    <div className={`p-4 border rounded ${theme.surfaceClass} space-y-3`}>
      <div className="text-xs font-bold text-gray-300 uppercase tracking-wider border-b border-gray-800 pb-2 flex items-center space-x-1.5">
        <AlertTriangle className="w-4 h-4 text-rose-400" />
        <span>{t('alertsTitle')}</span>
      </div>

      {!statsData ? (
        <div className="p-8 text-center space-y-4 font-mono">
          <div className="w-14 h-14 rounded-full bg-black/40 border border-[#FCEE09]/30 flex items-center justify-center mx-auto text-[#FCEE09]">
            <AlertTriangle className="w-7 h-7 animate-pulse" />
          </div>
          <div className="space-y-1">
            <h3 className="text-sm font-bold text-white uppercase tracking-wider">
              {t('alertsEmptyTitle')}
            </h3>
            <p className="text-xs text-zinc-400 max-w-md mx-auto">
              {t('alertsEmptyDesc', { port: selectedPort || t('serialPortFallback') })}
            </p>
          </div>
          <div className="pt-1">
            <button
              onClick={onRunInterrogation}
              disabled={isInterrogating || !selectedPort}
              className="px-5 py-2.5 bg-[#FCEE09] hover:bg-yellow-300 text-black font-mono font-bold text-xs uppercase tracking-wider rounded transition-colors disabled:opacity-50"
            >
              {isInterrogating ? t('btnReadingEeprom') : t('btnInterrogateShort')}
            </button>
          </div>
        </div>
      ) : (
        <div className="space-y-2 text-xs font-mono">
          {statsData.alerts && statsData.alerts.length > 0 ? (
            statsData.alerts.map((al, idx) => {
              const isBlocking = al && typeof al === 'object' ? al.blocking !== false : true;
              const alertText =
                typeof al === 'string'
                  ? al
                  : (al?.name || al?.message || al?.title || String(al));
              const badgeText =
                (al && typeof al === 'object' && al.severity) ||
                (isBlocking ? 'ALARM' : t('alertsReadyBadge'));
              return (
                <div
                  key={idx}
                  className={`flex items-center justify-between p-3 bg-black/40 border rounded ${
                    isBlocking ? 'border-rose-900/60' : 'border-emerald-900/60'
                  }`}
                >
                  <div className="flex items-center space-x-2">
                    {isBlocking ? (
                      <AlertTriangle className="w-4 h-4 text-rose-400" />
                    ) : (
                      <CheckCircle2 className="w-4 h-4 text-emerald-400" />
                    )}
                    <span className={`font-bold ${isBlocking ? 'text-rose-300' : 'text-emerald-300'}`}>
                      {alertText}
                    </span>
                  </div>
                  <span
                    className={`px-2 py-0.5 rounded text-[10px] font-bold border ${
                      isBlocking
                        ? 'bg-rose-950 text-rose-400 border-rose-700'
                        : 'bg-emerald-950 text-emerald-400 border-emerald-700'
                    }`}
                  >
                    {badgeText}
                  </span>
                </div>
              );
            })
          ) : (
            <div className="flex items-center justify-between p-3 bg-black/40 border border-emerald-900/60 rounded">
              <div className="flex items-center space-x-2">
                <CheckCircle2 className="w-4 h-4 text-emerald-400" />
                <span className="font-bold text-emerald-300">{t('alertsReadyNominal')}</span>
              </div>
              <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-emerald-950 text-emerald-400 border border-emerald-700">
                {t('alertsReadyBadge')}
              </span>
            </div>
          )}

          <div className="p-3 bg-black/40 border border-gray-800 rounded space-y-1">
            <div className="text-gray-400 font-bold">{t('alertsHistTitle')}</div>
            <div className="text-gray-500 text-[11px]">
              {t('alertsHistDesc', { model: statsData.machine_model || 'Appliance' })}
            </div>
          </div>
        </div>
      )}
    </div>
  );
});

export const SystemIdentityTabView = React.memo(function SystemIdentityTabView({
  theme,
  t,
  statsData,
  liveData,
  selectedPort,
  isInterrogating,
  onRunInterrogation,
}) {
  return (
    <div className={`p-4 border rounded ${theme.surfaceClass} space-y-4`}>
      <div className="text-xs font-bold text-gray-300 uppercase tracking-wider border-b border-gray-800 pb-2 flex items-center space-x-1.5">
        <Info className="w-4 h-4 text-sky-400" />
        <span>{t('identityTitle')}</span>
      </div>

      {!statsData ? (
        <div className="p-8 text-center space-y-4 font-mono">
          <div className="w-14 h-14 rounded-full bg-black/40 border border-[#FCEE09]/30 flex items-center justify-center mx-auto text-[#FCEE09]">
            <Info className="w-7 h-7 animate-pulse" />
          </div>
          <div className="space-y-1">
            <h3 className="text-sm font-bold text-white uppercase tracking-wider">
              {t('identityEmptyTitle')}
            </h3>
            <p className="text-xs text-zinc-400 max-w-md mx-auto">
              {t('identityEmptyDesc', { port: selectedPort || t('serialPortFallback') })}
            </p>
          </div>
          <div className="pt-1">
            <button
              onClick={onRunInterrogation}
              disabled={isInterrogating || !selectedPort}
              className="px-5 py-2.5 bg-[#FCEE09] hover:bg-yellow-300 text-black font-mono font-bold text-xs uppercase tracking-wider rounded transition-colors disabled:opacity-50"
            >
              {isInterrogating ? t('btnReadingEeprom') : t('btnInterrogateShort')}
            </button>
          </div>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4 text-xs font-mono">
          <div className="p-3 bg-black/40 border border-gray-800 rounded space-y-2">
            <div className="text-gray-500 font-bold uppercase text-[10px]">{t('electronicIdentity')}</div>
            <div className="flex justify-between py-1 border-b border-gray-800/60">
              <span className="text-gray-400">{t('lblMachineModel')}</span>
              <strong className="text-white">{statsData?.machine_model || '---'}</strong>
            </div>
            <div className="flex justify-between py-1 border-b border-gray-800/60">
              <span className="text-gray-400">{t('lblFirmwareString')}</span>
              <strong className="text-sky-400">{statsData?.firmware_string || '---'}</strong>
            </div>
            <div className="flex justify-between py-1 border-b border-gray-800/60">
              <span className="text-gray-400">{t('lblEfCode')}</span>
              <strong className="text-amber-400">{statsData?.ef_code || '---'}</strong>
            </div>
            <div className="flex justify-between py-1">
              <span className="text-gray-400">{t('lblProtocolMode')}</span>
              <strong className="text-emerald-400">{statsData?.protocol_mode || '---'}</strong>
            </div>
          </div>

          <div className="p-3 bg-black/40 border border-gray-800 rounded space-y-2">
            <div className="text-gray-500 font-bold uppercase text-[10px]">{t('electricalSpecs')}</div>
            <div className="flex justify-between py-1 border-b border-gray-800/60">
              <span className="text-gray-400">{t('lblPowerRating')}</span>
              <strong className="text-white">{statsData?.power_spec || '---'}</strong>
            </div>
            <div className="flex justify-between py-1 border-b border-gray-800/60">
              <span className="text-gray-400">{t('lblSerialEan')}</span>
              <strong className="text-white">{statsData?.serial_number || '---'}</strong>
            </div>
            <div className="flex justify-between py-1 border-b border-gray-800/60">
              <span className="text-gray-400">{t('lblRawHz')}</span>
              <strong className="text-gray-400 truncate max-w-[200px]">{liveData?.raw_status || '---'}</strong>
            </div>
            <div className="flex justify-between py-1">
              <span className="text-gray-400">{t('lblActivePort')}</span>
              <strong className="text-white">{selectedPort}</strong>
            </div>
          </div>
        </div>
      )}
    </div>
  );
});

export const CommandInjectorTabView = React.memo(function CommandInjectorTabView({
  theme,
  t,
  txCommand,
  setTxCommand,
  txResponseHistory,
  onTransmitCommand,
}) {
  return (
    <div className="space-y-3">
      <div className={`p-4 border rounded ${theme.surfaceClass} space-y-3`}>
        <div className="text-xs font-bold text-gray-300 uppercase tracking-wider flex items-center space-x-1.5">
          <Send className="w-4 h-4 text-sky-400" />
          <span>{t('injectorTitle')}</span>
        </div>

        {/* Quick Preset Buttons */}
        <div className="flex flex-wrap gap-1.5 text-xs font-mono">
          {['TY:', 'HZ:', 'AS:', 'CS:', 'IC:', 'RT:', 'RE:0028'].map((cmd) => (
            <button
              key={cmd}
              onClick={() => onTransmitCommand(cmd)}
              className="px-2.5 py-1 bg-gray-800 hover:bg-gray-700 text-sky-300 font-bold rounded border border-gray-700"
            >
              {cmd}
            </button>
          ))}
        </div>

        {/* Custom Input */}
        <div className="flex items-center space-x-2">
          <input
            type="text"
            value={txCommand}
            onChange={(e) => setTxCommand(e.target.value)}
            placeholder={t('injectorPlaceholder')}
            className="flex-1 px-3 py-1.5 bg-black/40 border border-gray-800 rounded text-xs text-white font-mono outline-none"
          />
          <button
            onClick={() => onTransmitCommand()}
            className="px-4 py-1.5 bg-sky-600 hover:bg-sky-500 text-white font-bold text-xs rounded font-mono"
          >
            {t('btnSendWireCmd')}
          </button>
        </div>

        {/* Response Log */}
        {txResponseHistory.length > 0 && (
          <div className="space-y-1 pt-2 border-t border-gray-800 font-mono text-xs">
            <div className="text-gray-500 text-[10px] uppercase font-bold">{t('txHistoryTitle')}</div>
            {txResponseHistory.map((h, i) => (
              <div key={i} className="flex justify-between p-1.5 bg-black/40 border border-gray-800/60 rounded">
                <span className="text-sky-300">TX: <strong>{h.cmd}</strong></span>
                <span className="text-emerald-400 font-bold">RX: {h.reply}</span>
                <span className="text-gray-500 text-[10px]">{h.timestamp}</span>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
});
