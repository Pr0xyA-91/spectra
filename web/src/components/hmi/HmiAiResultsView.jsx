import React from 'react';
import { Sparkles, X } from 'lucide-react';

export function HmiAiResultsView({
  isModal = false,
  semanticReport,
  ollamaModel,
  auditLocale,
  aiReviews,
  aiDefectsCount,
  aiVerifiedCount,
  aiResultFilter,
  setAiResultFilter,
  filteredAiReviews
}) {
  const tier3 = semanticReport?.tier3_ollama;
  if (!tier3 || !aiReviews.length) return null;

  return (
    <div className="space-y-3">
      {/* KPI Summary Badges */}
      <div className="flex flex-wrap items-center gap-2 text-xs font-mono">
        <span className="px-2.5 py-1 rounded bg-purple-950/80 border border-purple-700 text-purple-300 font-bold">
          Model: {tier3.active_model || ollamaModel || 'qwen2.5:1.5b'}
        </span>
        <span className="px-2.5 py-1 rounded bg-zinc-900 border border-zinc-700 text-gray-200">
          Scanned: <span className="font-bold text-white">{aiReviews.length}</span> phrases
        </span>
        <span className="px-2.5 py-1 rounded bg-rose-950/80 border border-rose-700 text-rose-300 font-bold">
          🚨 AI Confirmed Defects: {aiDefectsCount}
        </span>
        <span className="px-2.5 py-1 rounded bg-emerald-950/80 border border-emerald-700 text-emerald-300 font-bold">
          ✅ AI Verified OK: {aiVerifiedCount}
        </span>
        <span className="px-2.5 py-1 rounded bg-blue-950/80 border border-blue-700 text-blue-300">
          ⏱️ Scan Time: <span className="font-bold">{tier3.total_elapsed_ms || 0}</span> ms
        </span>
        {tier3.ram_unloaded && (
          <span className="px-2.5 py-1 rounded bg-cyan-950/80 border border-cyan-700 text-cyan-300 font-bold">
            🧹 RAM Unloaded
          </span>
        )}
      </div>

      {/* Filter Bar inside AI Scan Results */}
      <div className="flex flex-wrap items-center gap-1.5 pt-1 text-xs">
        <button
          onClick={() => setAiResultFilter('ALL')}
          className={`px-2.5 py-1 rounded font-bold transition-all ${
            aiResultFilter === 'ALL'
              ? 'bg-purple-600 text-white shadow-sm'
              : 'bg-zinc-900 hover:bg-zinc-800 text-zinc-300 border border-zinc-700'
          }`}
        >
          ALL SCANNED ({aiReviews.length})
        </button>
        <button
          onClick={() => setAiResultFilter('DEFECTS')}
          className={`px-2.5 py-1 rounded font-bold transition-all ${
            aiResultFilter === 'DEFECTS'
              ? 'bg-rose-600 text-white shadow-sm'
              : 'bg-zinc-900 hover:bg-zinc-800 text-rose-300 border border-zinc-700'
          }`}
        >
          🚨 AI CONFIRMED DEFECTS ({aiDefectsCount})
        </button>
        <button
          onClick={() => setAiResultFilter('VERIFIED')}
          className={`px-2.5 py-1 rounded font-bold transition-all ${
            aiResultFilter === 'VERIFIED'
              ? 'bg-emerald-600 text-white shadow-sm'
              : 'bg-zinc-900 hover:bg-zinc-800 text-emerald-300 border border-zinc-700'
          }`}
        >
          ✅ AI VERIFIED OK ({aiVerifiedCount})
        </button>
      </div>

      {/* AI Results Table */}
      <div className={`overflow-x-auto overflow-y-auto border border-zinc-800 rounded bg-black/40 ${isModal ? 'max-h-[55vh]' : 'max-h-[360px]'}`}>
        <table className="w-full text-left border-collapse text-[11px]">
          <thead className="sticky top-0 bg-zinc-900 border-b border-zinc-800 text-gray-400 text-[10px] uppercase font-mono z-10">
            <tr>
              <th className="p-2.5 w-40">AI Verdict</th>
              <th className="p-2.5">Key & English Baseline (en-GB)</th>
              <th className="p-2.5">Current Firmware ({auditLocale})</th>
              <th className="p-2.5">🤖 AI Suggested Fix</th>
              <th className="p-2.5">Diagnostic Reasoning</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-zinc-800/60 text-gray-200">
            {filteredAiReviews.map((r, idx) => {
              const isDiff = r.suggested_translation && r.suggested_translation !== r.target_val;
              return (
                <tr key={idx} className="hover:bg-zinc-800/40">
                  <td className="p-2.5 align-top">
                    <div className="flex flex-col space-y-1">
                      {r.is_correct ? (
                        <span className="inline-flex items-center space-x-1 px-2 py-0.5 rounded text-[10px] font-bold bg-emerald-950 text-emerald-300 border border-emerald-700 w-fit">
                          <span>✅ VERIFIED OK</span>
                        </span>
                      ) : (
                        <span className="inline-flex items-center space-x-1 px-2 py-0.5 rounded text-[10px] font-bold bg-rose-950 text-rose-300 border border-rose-700 w-fit">
                          <span>🚨 DEFECT CONFIRMED</span>
                        </span>
                      )}
                      <span className="text-[10px] text-gray-500 font-mono">
                        {r.elapsed_ms ? `${r.elapsed_ms} ms` : ''}
                      </span>
                    </div>
                  </td>
                  <td className="p-2.5 align-top max-w-[220px]">
                    <div className="font-mono font-bold text-gray-200 truncate" title={r.key}>
                      {r.key}
                    </div>
                    <div className="text-gray-400 text-xs font-sans mt-0.5" title={r.en_val}>
                      {r.en_val}
                    </div>
                  </td>
                  <td className="p-2.5 align-top max-w-[200px]">
                    <div className="text-amber-300 font-mono text-xs break-words" title={r.target_val}>
                      {r.target_val}
                    </div>
                  </td>
                  <td className="p-2.5 align-top max-w-[220px]">
                    {isDiff ? (
                      <div className="text-emerald-300 font-mono font-bold text-xs bg-emerald-950/60 p-1.5 rounded border border-emerald-700/60 break-words shadow-sm">
                        {r.suggested_translation}
                      </div>
                    ) : (
                      <div className="text-gray-500 font-mono text-xs italic">
                        Matches current ({r.target_val})
                      </div>
                    )}
                  </td>
                  <td className="p-2.5 align-top">
                    <div className="text-xs text-gray-300 font-sans leading-relaxed">
                      {r.reason}
                    </div>
                  </td>
                </tr>
              );
            })}
            {filteredAiReviews.length === 0 && (
              <tr>
                <td colSpan={5} className="p-6 text-center text-gray-500 font-mono text-xs">
                  No phrases matching the current filter.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}

export function HmiAiResultsModal({
  show,
  onClose,
  semanticReport,
  ollamaModel,
  auditLocale,
  aiReviews,
  aiDefectsCount,
  aiVerifiedCount,
  aiResultFilter,
  setAiResultFilter,
  filteredAiReviews
}) {
  if (!show || !semanticReport?.tier3_ollama?.reviews?.length) return null;

  return (
    <div className="fixed inset-0 z-50 bg-black/80 backdrop-blur-sm flex items-center justify-center p-3 sm:p-6">
      <div className="bg-[#121218] border border-cyan-800/80 rounded-lg shadow-2xl flex flex-col w-full max-w-6xl max-h-[90vh] overflow-hidden">
        {/* Modal Header */}
        <div className="p-3 bg-zinc-900/90 border-b border-zinc-800 flex items-center justify-between">
          <div className="flex items-center space-x-2">
            <Sparkles className="w-4 h-4 text-cyan-400" />
            <span className="text-sm font-bold text-gray-100 uppercase tracking-wider font-mono">
              🤖 SPECTRA — LOCAL AI SCAN RESULTS
            </span>
            <span className="px-2 py-0.5 text-[10px] font-bold rounded bg-purple-950 text-purple-300 border border-purple-800 font-mono">
              {semanticReport?.tier3_ollama?.active_model || 'Local LLM'}
            </span>
          </div>
          <button
            onClick={onClose}
            className="p-1 rounded hover:bg-zinc-800 text-gray-400 hover:text-gray-200 transition-all"
            title="Close Window"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Modal Body */}
        <div className="p-4 overflow-y-auto space-y-4 flex-1">
          <HmiAiResultsView
            isModal={true}
            semanticReport={semanticReport}
            ollamaModel={ollamaModel}
            auditLocale={auditLocale}
            aiReviews={aiReviews}
            aiDefectsCount={aiDefectsCount}
            aiVerifiedCount={aiVerifiedCount}
            aiResultFilter={aiResultFilter}
            setAiResultFilter={setAiResultFilter}
            filteredAiReviews={filteredAiReviews}
          />
        </div>

        {/* Modal Footer */}
        <div className="p-3 bg-zinc-900/80 border-t border-zinc-800 flex items-center justify-between text-xs text-gray-400 font-mono">
          <div>
            Target Audit Locale: <span className="text-cyan-300 font-bold">{auditLocale}</span>
          </div>
          <button
            onClick={onClose}
            className="px-4 py-1.5 rounded bg-zinc-800 hover:bg-zinc-700 text-gray-200 font-bold text-xs"
          >
            Close
          </button>
        </div>
      </div>
    </div>
  );
}
