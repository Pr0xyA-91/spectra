import React from 'react';
import { Database, Upload, RefreshCw, Search, ShieldCheck, Download } from 'lucide-react';

export default function MachineLibrarySection({
  t,
  libraryStats,
  connectedMatch,
  librarySearch,
  setLibrarySearch,
  machineCatalog,
  expandedMachineId,
  setExpandedMachineId,
  isLoadingLibrary,
  loadMachineLibrary,
  handleImportPatchFile,
  handleExportMachinePatch,
  offsetDbStatus = null,
  offsetDbCheck = null,
  isCheckingOffsetDb = false,
  isSyncingOffsetDb = false,
  offsetDbSyncNotice = null,
  onCheckOffsetDb = null,
  onSyncOffsetDb = null,
}) {
  const addedMachines = offsetDbCheck?.added_machines || [];
  const updatedMachines = offsetDbCheck?.updated_machines || [];

  return (
    <div className="space-y-3">
      {/* Ed25519 Signed Machine Offset DB Card */}
      <div className="p-3 bg-purple-950/20 border border-purple-700/50 rounded space-y-2">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div>
            <div className="font-bold text-white flex items-center gap-1.5 text-xs">
              <ShieldCheck className="w-4 h-4 text-emerald-400" />
              <span>{t('offsetDbTitle')}</span>
              <span
                className={`text-[9px] px-1.5 py-0.5 rounded font-bold border ${
                  offsetDbCheck?.update_available
                    ? 'bg-emerald-950/80 text-emerald-300 border-emerald-500'
                    : offsetDbStatus?.source === 'synced_verified_db'
                    ? 'bg-purple-950 text-purple-200 border-purple-500'
                    : 'bg-zinc-900 text-zinc-300 border-zinc-700'
                }`}
              >
                {offsetDbCheck?.update_available
                  ? t('offsetDbAvailableBadge')
                  : offsetDbStatus?.source === 'synced_verified_db'
                  ? t('offsetDbVerifiedBadge')
                  : t('offsetDbBundledBadge')}
              </span>
            </div>
            <div className="text-[10px] text-zinc-400 mt-0.5">
              {t('offsetDbCurrentVersion')}:{' '}
              <strong className="text-cyan-300 font-mono">
                {offsetDbStatus?.offset_db_version || libraryStats.offset_db_version || 'bundled'}
              </strong>
              {offsetDbCheck?.latest_version && (
                <>
                  {' '}• {t('offsetDbRemoteVersion')}:{' '}
                  <strong className="text-emerald-300 font-mono">{offsetDbCheck.latest_version}</strong>
                </>
              )}
            </div>
          </div>
          <div className="flex items-center gap-1.5">
            {onCheckOffsetDb && (
              <button
                type="button"
                disabled={isCheckingOffsetDb || isSyncingOffsetDb}
                onClick={() => onCheckOffsetDb(true)}
                className="px-2.5 py-1 bg-zinc-800 hover:bg-zinc-700 disabled:opacity-50 border border-zinc-600 text-zinc-200 rounded text-[11px] font-bold flex items-center gap-1 cursor-pointer"
              >
                <RefreshCw className={`w-3 h-3 ${isCheckingOffsetDb ? 'animate-spin' : ''}`} />
                <span>{isCheckingOffsetDb ? t('offsetDbBtnChecking') : t('offsetDbBtnCheck')}</span>
              </button>
            )}
            {onSyncOffsetDb && offsetDbCheck?.update_available && (
              <button
                type="button"
                disabled={isSyncingOffsetDb}
                onClick={async () => {
                  await onSyncOffsetDb();
                  if (loadMachineLibrary) loadMachineLibrary();
                }}
                className="px-3 py-1 bg-emerald-600 hover:bg-emerald-500 disabled:opacity-50 text-black font-extrabold rounded text-[11px] flex items-center gap-1 cursor-pointer shadow-[0_0_10px_rgba(16,185,129,0.4)]"
              >
                <Download className="w-3 h-3" />
                <span>{isSyncingOffsetDb ? t('offsetDbBtnSyncing') : t('offsetDbBtnSync')}</span>
              </button>
            )}
          </div>
        </div>

        {(addedMachines.length > 0 || updatedMachines.length > 0) && offsetDbCheck?.update_available && (
          <div className="p-2 bg-black/50 border border-emerald-700/50 rounded space-y-1 text-[10px] font-mono">
            {addedMachines.length > 0 && (
              <div className="text-emerald-300">
                <strong>+ {t('offsetDbAddedLabel')}:</strong>{' '}
                {addedMachines.map((m) => `${m.model_family}${m.ef_code ? ` [${m.ef_code}]` : ''}`).join(', ')}
              </div>
            )}
            {updatedMachines.length > 0 && (
              <div className="text-cyan-300">
                <strong>↻ {t('offsetDbUpdatedLabel')}:</strong>{' '}
                {updatedMachines.map((m) => `${m.model_family}${m.ef_code ? ` [${m.ef_code}]` : ''}`).join(', ')}
              </div>
            )}
          </div>
        )}

        {offsetDbSyncNotice?.msg && (
          <div
            className={`px-2.5 py-1.5 rounded text-[10px] border ${
              offsetDbSyncNotice.error
                ? 'bg-red-950/50 border-red-800 text-red-300'
                : 'bg-emerald-950/40 border-emerald-700 text-emerald-300'
            }`}
          >
            {offsetDbSyncNotice.msg}
          </div>
        )}

        <div className="text-[10px] text-zinc-400">
          {t('offsetDbPrecedenceNote')}
        </div>
      </div>

      <div className="p-3 bg-black/40 border border-zinc-800 rounded flex flex-wrap items-center justify-between gap-2">
        <div>
          <div className="font-bold text-white flex items-center gap-2">
            <Database className="w-4 h-4 text-purple-400" />
            <span>{t('cfgLibraryTitle')}</span>
          </div>
          <div className="text-[10px] text-zinc-400 mt-0.5">
            {t('cfgLibraryStats', {
              total: libraryStats.total_machines,
              verified: libraryStats.verified_specs_count,
              local: libraryStats.local_overrides_count,
            })}
          </div>
        </div>
        <div className="flex items-center gap-2">
          <label className="px-2.5 py-1 bg-purple-900/60 hover:bg-purple-800 border border-purple-500/60 text-purple-200 rounded text-[11px] font-bold flex items-center gap-1 cursor-pointer">
            <Upload className="w-3.5 h-3.5" />
            <span>{t('cfgBtnImportPatch')}</span>
            <input type="file" accept=".json,application/json" onChange={handleImportPatchFile} className="hidden" />
          </label>
          <button
            type="button"
            onClick={loadMachineLibrary}
            disabled={isLoadingLibrary}
            className="px-2 py-1 bg-zinc-900 hover:bg-zinc-800 border border-zinc-700 text-zinc-300 rounded text-[11px] flex items-center gap-1 cursor-pointer"
          >
            <RefreshCw className={`w-3 h-3 ${isLoadingLibrary ? 'animate-spin' : ''}`} />
          </button>
        </div>
      </div>

      {connectedMatch && (
        <div className="p-3 bg-emerald-950/30 border border-emerald-500/60 rounded space-y-1.5">
          <div className="flex items-center justify-between text-[11px]">
            <span className="font-bold text-emerald-300">
              {t('cfgConnectedMatch', { model: connectedMatch.model_family, ef: connectedMatch.ef_code || t('cfgNoEf') })}
            </span>
            <span className="px-2 py-0.5 bg-emerald-950 border border-emerald-600 text-emerald-300 rounded text-[10px] font-bold">
              {connectedMatch.active_source}
            </span>
          </div>
          <div className="text-[10px] text-zinc-300">
            {t('cfgMatchSummary', { products: connectedMatch.product_count, maintenance: connectedMatch.maintenance_count })}
            {connectedMatch.article_numbers?.length > 0 && ` • ${t('cfgArticles')} ${connectedMatch.article_numbers.slice(0, 6).join(', ')}`}
          </div>
        </div>
      )}

      <div className="relative">
        <Search className="w-3.5 h-3.5 text-zinc-500 absolute left-2.5 top-2.5" />
        <input
          type="text"
          value={librarySearch}
          onChange={(e) => setLibrarySearch(e.target.value)}
          placeholder={t('cfgLibrarySearchPlaceholder')}
          className="w-full bg-zinc-950 border border-zinc-700 rounded pl-8 pr-3 py-1.5 text-xs text-white outline-none focus:border-purple-400"
        />
      </div>

      <div className="max-h-72 overflow-y-auto space-y-1.5 pr-1">
        {machineCatalog
          .filter((m) => {
            const q = librarySearch.trim().toLowerCase();
            if (!q) return true;
            return (
              (m.ef_code || '').toLowerCase().includes(q) ||
              (m.model_family || '').toLowerCase().includes(q) ||
              (m.active_source || '').toLowerCase().includes(q) ||
              (m.article_numbers || []).some((a) => String(a).toLowerCase().includes(q))
            );
          })
          .slice(0, 80)
          .map((m) => {
            const isOpenRow = expandedMachineId === m.id;
            const hasOffsets = (m.offsets?.products?.length || 0) + (m.offsets?.maintenance?.length || 0) > 0;
            return (
              <div key={m.id} className="bg-zinc-950 border border-zinc-800 rounded p-2.5 space-y-2 text-[11px]">
                <div className="flex items-center justify-between gap-2">
                  <button
                    type="button"
                    onClick={() => setExpandedMachineId(isOpenRow ? '' : m.id)}
                    className="text-left flex-1 min-w-0 cursor-pointer"
                  >
                    <div className="flex items-center gap-2 flex-wrap">
                      <span className="font-bold text-white">{m.model_family}</span>
                      {m.ef_code && (
                        <span className="px-1.5 py-0.5 bg-zinc-900 border border-zinc-700 rounded text-[10px] text-cyan-300">
                          {m.ef_code}
                        </span>
                      )}
                      <span
                        className={`px-1.5 py-0.5 rounded text-[9px] font-bold border ${
                          m.has_local_override
                            ? 'bg-emerald-950 text-emerald-300 border-emerald-700'
                            : m.has_verified_spec
                            ? 'bg-purple-950 text-purple-300 border-purple-700'
                            : 'bg-zinc-900 text-zinc-400 border-zinc-700'
                        }`}
                      >
                        {m.active_source}
                      </span>
                      {m.is_connected_match && (
                        <span className="px-1.5 py-0.5 bg-sky-950 border border-sky-600 text-sky-300 rounded text-[9px] font-bold">
                          {t('cfgBadgeActive')}
                        </span>
                      )}
                    </div>
                    <div className="text-[10px] text-zinc-400 mt-0.5">
                      {t('cfgRowSummary', { products: m.product_count, maintenance: m.maintenance_count })}
                      {m.article_numbers?.length > 0 ? ` • Art: ${m.article_numbers.slice(0, 4).join(', ')}` : ''}
                    </div>
                  </button>
                  {hasOffsets && (
                    <button
                      type="button"
                      onClick={() => handleExportMachinePatch(m)}
                      className="px-2 py-1 bg-zinc-800 hover:bg-zinc-700 border border-zinc-700 text-zinc-200 rounded text-[10px] font-bold shrink-0 cursor-pointer"
                    >
                      {t('cfgBtnExportJson')}
                    </button>
                  )}
                </div>

                {isOpenRow && (
                  <div className="pt-2 border-t border-zinc-800 space-y-1.5 text-[10px]">
                    {m.notes && <div className="text-zinc-300 italic">{m.notes}</div>}
                    {hasOffsets ? (
                      <div className="grid grid-cols-1 sm:grid-cols-2 gap-1.5">
                        {(m.offsets?.products || []).slice(0, 12).map((p, i) => (
                          <div key={`p-${i}`} className="flex justify-between px-2 py-0.5 bg-black/50 rounded border border-zinc-800/80">
                            <span className="text-zinc-300 truncate">{p.name}</span>
                            <span className="text-cyan-300 font-bold">{p.addr_hex}</span>
                          </div>
                        ))}
                        {(m.offsets?.maintenance || []).slice(0, 12).map((mt, i) => (
                          <div key={`m-${i}`} className="flex justify-between px-2 py-0.5 bg-black/50 rounded border border-zinc-800/80">
                            <span className="text-amber-300 truncate">{mt.name}</span>
                            <span className="text-amber-400 font-bold">{mt.addr_hex}</span>
                          </div>
                        ))}
                      </div>
                    ) : (
                      <div className="text-zinc-500">
                        {t('cfgStandardMapNote', { labels: (m.product_labels || []).slice(0, 8).join(', ') })}
                      </div>
                    )}
                  </div>
                )}
              </div>
            );
          })}
      </div>
    </div>
  );
}
