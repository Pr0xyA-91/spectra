import React from 'react';
import {
  Zap,
  Search,
  Filter,
  Play,
  Pause,
  X,
  Layers
} from 'lucide-react';

function EepromMatrixView({
  theme,
  summary,
  registers,
  filteredRegisters,
  selectedAddr,
  setSelectedAddr,
  isSweeping,
  sweepProgress,
  isLiveDiff,
  setIsLiveDiff,
  filterType,
  setFilterType,
  searchQuery,
  setSearchQuery,
  onFullSweep,
  onCaptureBaseline,
  inspectorPanel
}) {
  return (
    <div className="space-y-4">
      {/* Quick Metrics Bar & Actions Toolbar */}
      <div className={`p-3 border ${theme.border} ${theme.panelBg} ${theme.clipClass} flex flex-wrap items-center justify-between gap-3 text-xs font-mono`}>
        {/* Metric Status Badges */}
        <div className="flex flex-wrap items-center gap-2">
          <span className="px-2 py-0.5 bg-emerald-950/80 text-emerald-400 border border-emerald-500/60 font-bold rounded">
            🟢 {summary.mapped} Mapped
          </span>
          <span className="px-2 py-0.5 bg-amber-950/80 text-amber-400 border border-amber-500/60 font-bold rounded">
            🟠 {summary.theoretical} Theor.
          </span>
          <span className="px-2 py-0.5 bg-red-950/80 text-red-400 border border-red-500/60 font-bold rounded">
            🔴 {summary.unknown} Unknown
          </span>
          <span className="px-2 py-0.5 bg-zinc-900 text-zinc-400 border border-zinc-700 font-bold rounded">
            ⚪ {summary.blank} Blank
          </span>
          <span className="px-2 py-0.5 bg-cyan-950/80 text-cyan-400 border border-cyan-500/60 font-bold rounded">
            ⚡ {summary.changed} Changed
          </span>
          <span className="px-2 py-0.5 bg-purple-950/80 text-purple-300 border border-purple-500/60 font-bold rounded">
            Coverage: {summary.coverage_pct}%
          </span>
        </div>

        {/* Sweep & Diff Action Buttons */}
        <div className="flex items-center space-x-2">
          <button
            onClick={() => onFullSweep()}
            disabled={isSweeping}
            className={`flex items-center space-x-1.5 px-3 py-1 font-bold rounded transition-all ${
              isSweeping
                ? 'bg-yellow-600/40 text-yellow-300 border border-yellow-500 animate-pulse'
                : 'bg-[#FCEE09] hover:bg-yellow-400 text-black font-extrabold shadow-[0_0_10px_rgba(252,238,9,0.4)]'
            }`}
          >
            <Zap className="w-3.5 h-3.5" />
            <span>{isSweeping ? `SWEEPING (${sweepProgress.current}/${sweepProgress.total})...` : '⚡ FULL SWEEP'}</span>
          </button>

          <button
            onClick={onCaptureBaseline}
            className="flex items-center space-x-1 px-2.5 py-1 bg-zinc-800 hover:bg-zinc-700 text-zinc-200 border border-zinc-600 rounded font-bold"
            title="Capture snapshot as baseline reference for delta tracking"
          >
            <Layers className="w-3.5 h-3.5 text-cyan-400" />
            <span>📸 BASELINE</span>
          </button>

          <button
            onClick={() => setIsLiveDiff(!isLiveDiff)}
            className={`flex items-center space-x-1 px-2.5 py-1 font-bold rounded ${
              isLiveDiff
                ? 'bg-cyan-950 text-cyan-400 border border-cyan-500 animate-pulse'
                : 'bg-zinc-800 hover:bg-zinc-700 text-zinc-400 border border-zinc-700'
            }`}
            title="Continuous differential comparison against captured baseline"
          >
            {isLiveDiff ? <Pause className="w-3.5 h-3.5" /> : <Play className="w-3.5 h-3.5" />}
            <span>{isLiveDiff ? 'DIFF ACTIVE' : '⏱️ LIVE DIFF'}</span>
          </button>
        </div>
      </div>

      {isSweeping && (
        <div className="w-full bg-zinc-900/90 border border-yellow-500/40 rounded overflow-hidden">
          <div
            className="h-1.5 bg-[#FCEE09] transition-all duration-150"
            style={{
              width: `${Math.min(100, Math.round((sweepProgress.current / Math.max(1, sweepProgress.total)) * 100))}%`
            }}
          />
        </div>
      )}

      {/* Filter & Search Bar */}
      <div className="flex flex-wrap items-center justify-between gap-2 text-xs font-mono">
        <div className="flex flex-wrap items-center gap-1.5">
          <span className="text-zinc-500 uppercase tracking-wider flex items-center space-x-1 mr-1">
            <Filter className="w-3.5 h-3.5" />
            <span>Filter:</span>
          </span>
          {[
            { id: 'all', label: `All (${registers.length || 512})` },
            { id: 'mapped', label: '🟢 Mapped' },
            { id: 'theoretical', label: '🟠 Theor.' },
            { id: 'unknown', label: '🔴 Unknown' },
            { id: 'blank', label: '⚪ Blank' },
            { id: 'changed', label: '⚡ Changed' }
          ].map((f) => (
            <button
              key={f.id}
              onClick={() => setFilterType(f.id)}
              className={`px-2.5 py-0.5 rounded border transition-all ${
                filterType === f.id
                  ? 'bg-zinc-200 text-black border-white font-bold'
                  : 'bg-zinc-900/80 text-zinc-400 border-zinc-800 hover:border-zinc-600'
              }`}
            >
              {f.label}
            </button>
          ))}
        </div>

        {/* Search Box */}
        <div className="flex items-center space-x-1 bg-black/60 px-2 py-1 rounded border border-zinc-800 min-w-[220px]">
          <Search className="w-3.5 h-3.5 text-zinc-400" />
          <input
            type="text"
            placeholder="Search Hex (e.g. 0040) or Name..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="bg-transparent text-zinc-200 text-xs font-mono outline-none w-full"
          />
          {searchQuery && (
            <button onClick={() => setSearchQuery('')} className="text-zinc-500 hover:text-white">
              <X className="w-3 h-3" />
            </button>
          )}
        </div>
      </div>

      {/* Main Paned Layout: Left Register Table | Right Bitfield Inspector & Mapping Editor */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-4">
        {/* Left Column: 512-Word Register Matrix Table */}
        <div className="lg:col-span-7 space-y-2">
          <div className={`border ${theme.border} ${theme.panelBg} ${theme.clipClass} overflow-hidden shadow-inner`}>
            <div className="max-h-[580px] overflow-y-auto font-mono text-xs">
              <table className="w-full border-collapse">
                <thead className="sticky top-0 bg-[#121218] border-b border-zinc-800 text-zinc-400 text-[11px] uppercase tracking-wider select-none z-10">
                  <tr>
                    <th className="py-2 px-2 text-left w-20">Status</th>
                    <th className="py-2 px-2 text-left w-16">Addr</th>
                    <th className="py-2 px-2 text-left w-16">Hex</th>
                    <th className="py-2 px-2 text-left w-16">Dec</th>
                    <th className="py-2 px-2 text-left w-20">Base/Delta</th>
                    <th className="py-2 px-2 text-left">Register Name</th>
                    <th className="py-2 px-2 text-left w-20">Category</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-zinc-800/60">
                  {filteredRegisters.length === 0 ? (
                    <tr>
                      <td colSpan={7} className="py-8 text-center text-zinc-500">
                        {isSweeping ? 'Reading EEPROM words over serial port...' : 'No registers match current filter.'}
                      </td>
                    </tr>
                  ) : (
                    filteredRegisters.map((r) => {
                      const isSelected = r.addr === selectedAddr;
                      return (
                        <tr
                          key={r.addr}
                          onClick={() => setSelectedAddr(r.addr)}
                          className={`cursor-pointer transition-colors ${
                            isSelected
                              ? 'bg-[#FCEE09]/15 text-white font-bold border-l-4 border-l-[#FCEE09]'
                              : r.is_changed
                              ? 'bg-amber-950/30 text-amber-300 hover:bg-zinc-800/80'
                              : 'hover:bg-zinc-800/50 text-zinc-300'
                          }`}
                        >
                          <td className="py-1.5 px-2">
                            {r.status === 'mapped' && (
                              <span className="text-emerald-400 font-bold">🟢 Mapped</span>
                            )}
                            {r.status === 'theoretical' && (
                              <span className="text-amber-400 font-bold">🟠 Theor.</span>
                            )}
                            {r.status === 'unknown' && (
                              <span className="text-red-400 font-bold">🔴 Unknown</span>
                            )}
                            {r.status === 'blank' && (
                              <span className="text-zinc-500">⚪ Blank</span>
                            )}
                          </td>
                          <td className="py-1.5 px-2 text-cyan-400 font-mono font-bold">
                            0x{r.hex_addr}
                          </td>
                          <td className="py-1.5 px-2 font-mono text-[#FCEE09]">
                            {r.val_hex}
                          </td>
                          <td className="py-1.5 px-2 font-mono text-zinc-200">
                            {r.val}
                          </td>
                          <td className="py-1.5 px-2 font-mono">
                            {r.is_changed ? (
                              <span className="text-amber-400 font-bold animate-pulse">
                                Δ {r.delta > 0 ? `+${r.delta}` : r.delta}
                              </span>
                            ) : (
                              <span className="text-zinc-500">{r.baseline_hex}</span>
                            )}
                          </td>
                          <td className="py-1.5 px-2 truncate max-w-[180px]" title={r.desc}>
                            <span className={isSelected ? 'text-[#FCEE09]' : 'text-zinc-200'}>
                              {r.name}
                            </span>
                          </td>
                          <td className="py-1.5 px-2 text-[10px] text-zinc-400 uppercase">
                            {r.category}
                          </td>
                        </tr>
                      );
                    })
                  )}
                </tbody>
              </table>
            </div>
          </div>
        </div>

        {/* Right Column Slot */}
        <div className="lg:col-span-5 space-y-4">
          {inspectorPanel}
        </div>
      </div>
    </div>
  );
}

export default React.memo(EepromMatrixView);
