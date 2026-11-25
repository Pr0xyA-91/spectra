import React from 'react';
import {
  Play,
  Pause,
  Check,
  Terminal,
  Database,
  SlidersHorizontal,
  Trash2,
  Sparkles,
  Power
} from 'lucide-react';

function RegisterInspectorPanel({
  theme,
  selectedRegister,
  mapForm,
  setMapForm,
  isSavingReg,
  onSaveRegisterMapping,
  diffEvents,
  setDiffEvents,
  isDiffPaused,
  setIsDiffPaused,
  aiEnabled,
  aiModel,
  onToggleAi,
  registersCount,
  isSuggestingAi,
  aiSuggestError,
  aiSuggestions,
  onSuggestAiRegisters,
  onApplyAiSuggestion
}) {
  return (
    <>
      {/* Card 1: 16-Bit Register Bitfield Breakdown */}
      <div className={`p-4 border ${theme.border} ${theme.panelBg} ${theme.clipClass} space-y-3 font-mono shadow-md`}>
        <div className="flex items-center justify-between border-b border-zinc-800 pb-2">
          <div className="flex items-center space-x-2">
            <SlidersHorizontal className="w-4 h-4 text-cyan-400" />
            <span className="font-bold text-xs text-white uppercase tracking-wider">
              16-BIT REGISTER INSPECTOR: 0x{selectedRegister.hex_addr}
            </span>
          </div>
          <span className="text-[11px] px-2 py-0.5 bg-black/60 border border-zinc-700 text-[#FCEE09] font-bold rounded">
            {selectedRegister.val_hex} ({selectedRegister.val})
          </span>
        </div>

        {/* 16-Bit Binary Matrix Grid (b15 down to b0) */}
        <div>
          <div className="grid grid-cols-8 gap-1.5 text-center">
            {Array.from({ length: 16 }, (_, i) => 15 - i).map((b) => {
              const bitVal = (selectedRegister.val >> b) & 1;
              const isFlipped = selectedRegister.bits_flipped?.includes(b);
              return (
                <div
                  key={b}
                  className={`p-1 rounded border text-[11px] font-mono transition-all ${
                    isFlipped
                      ? 'bg-amber-950 border-amber-400 text-amber-200 font-extrabold shadow-[0_0_8px_rgba(251,191,36,0.6)] animate-pulse'
                      : bitVal === 1
                      ? 'bg-emerald-950/80 border-emerald-500 text-emerald-300 font-bold shadow-[0_0_6px_rgba(16,185,129,0.3)]'
                      : 'bg-black/50 border-zinc-800 text-zinc-500'
                  }`}
                >
                  <div className="text-[9px] text-zinc-400">b{b}</div>
                  <div className="text-sm font-bold">{bitVal}</div>
                </div>
              );
            })}
          </div>
        </div>

        {/* Data Format Breakdown */}
        <div className="grid grid-cols-2 gap-2 text-xs pt-1 border-t border-zinc-800/80">
          <div className="bg-black/40 p-2 rounded border border-zinc-800">
            <span className="text-zinc-500 text-[10px] uppercase block">Bytes (High / Low):</span>
            <span className="text-cyan-300 font-bold">
              0x{Number(selectedRegister?.high_byte ?? 0).toString(16).toUpperCase().padStart(2, '0')} ({selectedRegister?.high_byte ?? 0}) / 0x{Number(selectedRegister?.low_byte ?? 0).toString(16).toUpperCase().padStart(2, '0')} ({selectedRegister?.low_byte ?? 0})
            </span>
          </div>
          <div className="bg-black/40 p-2 rounded border border-zinc-800">
            <span className="text-zinc-500 text-[10px] uppercase block">Signed Dec / ASCII:</span>
            <span className="text-zinc-200 font-bold">
              {selectedRegister.signed_val} | '{selectedRegister.ascii_repr}'
            </span>
          </div>
        </div>

        <div className="text-xs text-zinc-400 italic">
          {selectedRegister.desc || 'No description entered for this register.'}
        </div>
      </div>

      {/* Card 2: Inline Register Mapping Form */}
      <div className={`p-4 border ${theme.border} ${theme.panelBg} ${theme.clipClass} space-y-3 font-mono shadow-md`}>
        <div className="flex items-center justify-between border-b border-zinc-800 pb-2">
          <div className="flex items-center space-x-2">
            <Database className="w-4 h-4 text-[#FCEE09]" />
            <span className="font-bold text-xs text-white uppercase tracking-wider">
              MAP REGISTER SPECIFICATION [0x{selectedRegister.hex_addr}]
            </span>
          </div>
          <span className="text-[10px] text-zinc-500">
            Persists to docs/models/
          </span>
        </div>

        <form onSubmit={onSaveRegisterMapping} className="space-y-2.5 text-xs">
          <div>
            <label className="block text-[11px] text-zinc-400 mb-1">REGISTER NAME:</label>
            <input
              type="text"
              value={mapForm.name}
              onChange={(e) => setMapForm({ ...mapForm, name: e.target.value })}
              placeholder="e.g. BU_Upper_Limit"
              className="w-full bg-black/60 border border-zinc-700 px-2.5 py-1.5 rounded text-zinc-200 font-mono outline-none focus:border-[#FCEE09]"
            />
          </div>

          <div className="grid grid-cols-2 gap-2">
            <div>
              <label className="block text-[11px] text-zinc-400 mb-1">CATEGORY:</label>
              <select
                value={mapForm.category}
                onChange={(e) => setMapForm({ ...mapForm, category: e.target.value })}
                className="w-full bg-black/60 border border-zinc-700 px-2 py-1.5 rounded text-zinc-200 font-mono outline-none focus:border-[#FCEE09]"
              >
                <option value="counters">counters</option>
                <option value="maintenance">maintenance</option>
                <option value="calibration">calibration</option>
                <option value="settings">settings</option>
                <option value="faults">faults</option>
                <option value="hardware">hardware</option>
                <option value="recipe">recipe</option>
                <option value="spdl">spdl</option>
                <option value="custom">custom</option>
              </select>
            </div>

            <div>
              <label className="block text-[11px] text-zinc-400 mb-1">UNIT:</label>
              <input
                type="text"
                value={mapForm.unit}
                onChange={(e) => setMapForm({ ...mapForm, unit: e.target.value })}
                placeholder="e.g. ticks, cups, °C"
                className="w-full bg-black/60 border border-zinc-700 px-2.5 py-1.5 rounded text-zinc-200 font-mono outline-none focus:border-[#FCEE09]"
              />
            </div>
          </div>

          <div>
            <label className="block text-[11px] text-zinc-400 mb-1">DESCRIPTION / FUNCTION:</label>
            <textarea
              rows={2}
              value={mapForm.desc}
              onChange={(e) => setMapForm({ ...mapForm, desc: e.target.value })}
              placeholder="Functional purpose and decoding logic..."
              className="w-full bg-black/60 border border-zinc-700 px-2.5 py-1.5 rounded text-zinc-200 font-mono outline-none focus:border-[#FCEE09] resize-none"
            />
          </div>

          <div className="pt-1 flex items-center justify-between">
            <div className="flex items-center space-x-2">
              <label className="text-[11px] text-zinc-400">STATUS:</label>
              <select
                value={mapForm.status}
                onChange={(e) => setMapForm({ ...mapForm, status: e.target.value })}
                className="bg-black/60 border border-zinc-700 px-2 py-1 rounded text-zinc-200 text-xs font-mono outline-none"
              >
                <option value="mapped">🟢 Mapped</option>
                <option value="theoretical">🟠 Theoretical</option>
                <option value="unknown">🔴 Unknown</option>
              </select>
            </div>

            <button
              type="submit"
              disabled={isSavingReg || !mapForm.name.trim()}
              className="px-3 py-1.5 bg-[#FCEE09] hover:bg-yellow-400 text-black font-extrabold rounded font-mono text-xs flex items-center space-x-1 shadow-[0_0_10px_rgba(252,238,9,0.4)] disabled:opacity-50"
            >
              <Check className="w-3.5 h-3.5" />
              <span>{isSavingReg ? 'SAVING...' : '💾 SAVE TO MODEL'}</span>
            </button>
          </div>
        </form>
      </div>

      {/* Card 3: Differential Logic Scope Event Stream */}
      <div className={`p-4 border ${theme.border} ${theme.panelBg} ${theme.clipClass} space-y-2 font-mono shadow-md`}>
        <div className="flex items-center justify-between border-b border-zinc-800 pb-2 text-xs">
          <div className="flex items-center space-x-2">
            <Terminal className="w-4 h-4 text-amber-400" />
            <span className="font-bold text-white uppercase tracking-wider">
              DIFFERENTIAL LOGIC SCOPE STREAM
            </span>
          </div>
          <div className="flex items-center space-x-2">
            <button
              onClick={() => setIsDiffPaused(!isDiffPaused)}
              className="text-zinc-400 hover:text-white"
              title={isDiffPaused ? 'Resume Scope' : 'Pause Scope'}
            >
              {isDiffPaused ? <Play className="w-3.5 h-3.5 text-emerald-400" /> : <Pause className="w-3.5 h-3.5" />}
            </button>
            <button
              onClick={() => setDiffEvents([])}
              className="text-zinc-400 hover:text-white"
              title="Clear Events"
            >
              <Trash2 className="w-3.5 h-3.5" />
            </button>
          </div>
        </div>

        <div className="h-32 overflow-y-auto bg-black/60 p-2 rounded border border-zinc-800 text-[11px] text-zinc-300 space-y-1">
          {diffEvents.length === 0 ? (
            <div className="text-zinc-500 italic py-6 text-center">
              No differential memory bit-flips recorded. Baseline active.
            </div>
          ) : (
            diffEvents.map((ev, i) => (
              <div key={i} className="flex items-center space-x-2 font-mono">
                <span className="text-zinc-500">[{ev.timestamp}]</span>
                <span className="text-cyan-400 font-bold">0x{ev.addrHex}</span>
                <span className="text-zinc-400">({ev.name}):</span>
                <span className="text-zinc-500 line-through">{ev.oldVal}</span>
                <span className="text-amber-400 font-bold">→ {ev.newVal}</span>
                <span className="text-zinc-500 text-[10px]">
                  bits: [{ev.flips?.join(', ')}]
                </span>
              </div>
            ))
          )}
        </div>
      </div>

      {/* Card 4: Local Ollama Register Labeling (Opt-in, Default OFF) */}
      <div className={`p-4 border ${aiEnabled ? 'border-cyan-800/80' : theme.border} ${theme.panelBg} ${theme.clipClass} space-y-3 font-mono shadow-md`}>
        <div className="flex items-center justify-between border-b border-zinc-800 pb-2 text-xs">
          <div className="flex items-center space-x-2">
            <Sparkles className={`w-4 h-4 ${aiEnabled ? 'text-cyan-400' : 'text-zinc-500'}`} />
            <span className="font-bold text-white uppercase tracking-wider">
              LOCAL AI REGISTER LABELING
            </span>
          </div>
          {onToggleAi && (
            <button
              type="button"
              onClick={() => onToggleAi(!aiEnabled)}
              className={`px-2 py-0.5 rounded text-[10px] font-bold flex items-center space-x-1 border ${
                aiEnabled
                  ? 'bg-red-950/60 hover:bg-red-900/70 text-red-300 border-red-700'
                  : 'bg-zinc-800 hover:bg-zinc-700 text-zinc-300 border-zinc-600'
              }`}
            >
              <Power className="w-3 h-3" />
              <span>{aiEnabled ? 'TURN AI OFF' : 'ENABLE AI (OFF)'}</span>
            </button>
          )}
        </div>

        <div className="flex items-center justify-between gap-2 text-[11px]">
          <span className="text-zinc-400">
            {aiEnabled
              ? `Local AI ready${aiModel ? ` (${aiModel})` : ''}. Infers purpose from deltas & neighbors.`
              : 'AI is OFF by default so your device keeps zero RAM/CPU overhead.'}
          </span>
          <button
            type="button"
            onClick={onSuggestAiRegisters}
            disabled={!aiEnabled || isSuggestingAi || registersCount === 0}
            className="shrink-0 px-2.5 py-1.5 bg-cyan-950/80 hover:bg-cyan-900/80 border border-cyan-500/70 text-cyan-300 font-bold rounded text-[11px] disabled:opacity-40"
          >
            {isSuggestingAi ? 'ANALYZING...' : '🧠 SUGGEST UNKNOWN / CHANGED'}
          </button>
        </div>

        {aiSuggestError && (
          <div className="p-2 bg-red-950/40 border border-red-800 rounded text-[11px] text-red-300">
            {aiSuggestError}
          </div>
        )}

        {aiSuggestions.length > 0 && (
          <div className="max-h-52 overflow-y-auto space-y-2 pr-1">
            {aiSuggestions.map((sug, idx) => (
              <div
                key={`${sug.addr}-${idx}`}
                className="p-2.5 bg-black/50 border border-zinc-800 rounded space-y-1 text-[11px]"
              >
                <div className="flex items-center justify-between gap-2">
                  <div className="flex items-center space-x-2 min-w-0">
                    <span className="text-cyan-400 font-bold">
                      0x{sug.addr_hex || Number(sug?.addr ?? 0).toString(16).toUpperCase().padStart(4, '0')}
                    </span>
                    <span className="text-[#FCEE09] font-bold truncate">{sug.suggested_name}</span>
                    <span className="px-1.5 py-0.5 bg-zinc-900 border border-zinc-700 rounded text-[9px] text-zinc-400 uppercase">
                      {sug.category || 'custom'}
                    </span>
                    {sug.unit && (
                      <span className="text-[10px] text-emerald-400">[{sug.unit}]</span>
                    )}
                  </div>
                  <button
                    type="button"
                    onClick={() => onApplyAiSuggestion(sug)}
                    className="shrink-0 px-2 py-0.5 bg-[#FCEE09] hover:bg-yellow-400 text-black font-bold rounded text-[10px]"
                  >
                    Apply to Editor
                  </button>
                </div>
                {sug.reasoning && (
                  <p className="text-zinc-400 text-[10px] leading-snug">{sug.reasoning}</p>
                )}
              </div>
            ))}
          </div>
        )}
      </div>
    </>
  );
}

export default React.memo(RegisterInspectorPanel);
