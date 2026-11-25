import React from 'react';
import {
  AlertTriangle,
  RefreshCw,
  Box,
  Sparkles,
  ArrowDownCircle,
  Maximize2
} from 'lucide-react';
import HmiHardwareControlPanel from './HmiHardwareControlPanel';
import { HmiAiResultsView } from './HmiAiResultsView';

export default function HmiSemanticAuditView({
  auditLocale,
  setAuditLocale,
  effectiveLanguages,
  useOllama,
  setUseOllama,
  aiEnabled,
  onToggleAi,
  ollamaModel,
  setOllamaModel,
  onGlobalModelChange,
  effectiveModelCatalog,
  autoUnload,
  setAutoUnload,
  aiStatus,
  isLoadingAiStatus,
  onRefreshAiStatus,
  isOperatingOllama,
  onControlOllama,
  pullProgress,
  setPullProgress,
  semanticReport,
  isLoadingSemantic,
  semanticProgress,
  onRunSemanticAudit,
  aiReviews,
  aiDefectsCount,
  aiVerifiedCount,
  aiResultFilter,
  setAiResultFilter,
  filteredAiReviews,
  onOpenAiModal,
  anomalyFilter,
  setAnomalyFilter,
  flaggedAllCount,
  flaggedScannedCount,
  flaggedDefectsCount,
  flaggedSuggestedCount,
  filteredFlaggedPhrases
}) {
  return (
    <div className="space-y-4">
      {/* Header & Offline Engine Status Badges */}
      <div className="p-3 bg-zinc-900/60 rounded border border-zinc-800 space-y-2">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div className="flex items-center space-x-2">
            <Sparkles className="w-4 h-4 text-purple-400" />
            <span className="text-xs font-bold text-purple-300 uppercase tracking-wider">
              3-Tier Offline Semantic Hybrid Auditor
            </span>
            <span className="px-2 py-0.5 text-[10px] font-bold rounded bg-emerald-950 text-emerald-400 border border-emerald-800">
              100% OFFLINE ENGINE
            </span>
          </div>

          <div className="flex flex-wrap items-center gap-1.5 text-[10px] font-mono">
            <span className="px-2 py-0.5 rounded bg-cyan-950/80 border border-cyan-800 text-cyan-300">
              Tier 1: Auto-Learned Glossary
            </span>
            <span className="px-2 py-0.5 rounded bg-blue-950/80 border border-blue-800 text-blue-300">
              Tier 2: Vector Consensus
            </span>
            <span
              className={`px-2 py-0.5 rounded border transition-all ${
                isLoadingSemantic && useOllama
                  ? 'bg-purple-950/80 border-purple-500 text-purple-300 animate-pulse'
                  : semanticReport?.tier3_ollama?.available
                  ? 'bg-emerald-950/80 border-emerald-700 text-emerald-300'
                  : aiStatus?.ollama?.available
                  ? 'bg-cyan-950/80 border-cyan-700 text-cyan-300'
                  : 'bg-zinc-900 border-zinc-700 text-gray-500'
              }`}
            >
              Tier 3: Local AI 127.0.0.1 (
              {isLoadingSemantic && useOllama
                ? 'Active — Scanning...'
                : semanticReport?.tier3_ollama?.available
                ? `Active — ${semanticReport.tier3_ollama.active_model || 'Model Loaded'}`
                : aiStatus?.ollama?.available
                ? `Online — Ready [${aiStatus.ollama.loaded_models?.[0]?.name || aiStatus.ollama.loaded_models?.[0] || ollamaModel || 'Ready'}]`
                : 'Offline / Inactive'}
              )
            </span>
          </div>
        </div>

        {/* Controls Bar */}
        <div className="flex flex-wrap items-center justify-between gap-3 pt-2 border-t border-zinc-800/80">
          <div className="flex items-center space-x-3">
            <span className="text-gray-400 font-bold text-xs">Target Locale:</span>
            <select
              value={auditLocale}
              onChange={(e) => {
                setAuditLocale(e.target.value);
                onRunSemanticAudit(null, e.target.value);
              }}
              className="bg-black/60 border border-zinc-700 rounded px-2.5 py-1 text-gray-200 font-mono text-xs focus:outline-none focus:border-purple-500"
            >
              {effectiveLanguages.map((l) => (
                <option key={l.locale} value={l.locale}>
                  {l.locale} ({l.phrase_count} phrases)
                </option>
              ))}
            </select>

            <label className="flex items-center space-x-1.5 text-xs text-gray-300 cursor-pointer">
              <input
                type="checkbox"
                checked={useOllama && aiEnabled}
                onChange={(e) => {
                  const next = e.target.checked;
                  setUseOllama(next);
                  if (onToggleAi) onToggleAi(next, ollamaModel);
                }}
                className="rounded bg-black/60 border-zinc-700 text-purple-500 focus:ring-purple-500"
              />
              <span>Query Local AI (127.0.0.1:11434 — default OFF)</span>
            </label>
          </div>

          <button
            onClick={() => onRunSemanticAudit()}
            disabled={isLoadingSemantic}
            className="flex items-center space-x-1.5 px-3 py-1.5 font-bold rounded bg-gradient-to-r from-purple-600 to-indigo-600 hover:from-purple-500 hover:to-indigo-500 text-white shadow-[0_0_12px_rgba(168,85,247,0.3)] transition-all text-xs"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${isLoadingSemantic ? 'animate-spin' : ''}`} />
            <span>{isLoadingSemantic ? 'ANALYZING SEMANTICS...' : '🧠 RUN DEEP SEMANTIC AUDIT'}</span>
          </button>
        </div>

        {/* Deep AI Semantic Scan Progress Bar */}
        {(isLoadingSemantic || (semanticProgress && semanticProgress.active)) && (
          <div className="pt-2 border-t border-purple-900/40 space-y-1.5">
            <div className="flex items-center justify-between text-[11px] font-mono">
              <span className="text-purple-300 font-bold flex items-center gap-1.5">
                <span className="inline-block w-2 h-2 rounded-full bg-purple-400 animate-ping" />
                {semanticProgress?.step || 'SEMANTIC_AUDIT'}: {semanticProgress?.detail || 'Scanning translations...'}
              </span>
              <div className="flex items-center space-x-2 text-gray-400">
                {semanticProgress?.total > 0 && (
                  <span>
                    [{semanticProgress.current || 0} / {semanticProgress.total}]
                  </span>
                )}
                <span className="text-purple-300 font-bold">{semanticProgress?.percent || 0}%</span>
                {semanticProgress?.eta_seconds !== null && semanticProgress?.eta_seconds !== undefined && semanticProgress.eta_seconds > 0 && (
                  <span className="text-xs text-amber-400 font-mono">
                    ~{Math.ceil(semanticProgress.eta_seconds)}s remaining
                  </span>
                )}
              </div>
            </div>
            <div className="w-full bg-black/60 rounded-full h-2 overflow-hidden border border-purple-900/60 p-[1px]">
              <div
                className="h-full rounded-full bg-gradient-to-r from-purple-600 via-indigo-500 to-cyan-400 transition-all duration-300 shadow-[0_0_8px_rgba(168,85,247,0.5)]"
                style={{ width: `${Math.min(100, Math.max(2, semanticProgress?.percent || 0))}%` }}
              />
            </div>
          </div>
        )}
      </div>

      {/* Warning Banner when useOllama is checked but no models installed */}
      {useOllama && (semanticReport?.tier3_ollama?.status_message || (aiStatus?.ollama?.available && (!aiStatus.ollama.models || aiStatus.ollama.models.length === 0))) && (
        <div className="p-3 bg-amber-950/60 border border-amber-600/80 rounded flex flex-wrap items-center justify-between gap-2 text-amber-200">
          <div className="flex items-center space-x-2">
            <AlertTriangle className="w-5 h-5 text-amber-400 shrink-0" />
            <span className="text-xs font-mono font-bold">
              {semanticReport?.tier3_ollama?.status_message ||
                "Local AI runtime is ready, but no models are installed yet. Click 'Pull Selected Model' below to download."}
            </span>
          </div>
          <button
            onClick={() => onControlOllama('pull')}
            disabled={isOperatingOllama}
            className="px-3 py-1 bg-amber-500 hover:bg-amber-400 text-black font-bold text-xs rounded transition-all shrink-0 flex items-center space-x-1"
          >
            <ArrowDownCircle className="w-3.5 h-3.5" />
            <span>Pull Selected Model</span>
          </button>
        </div>
      )}

      {/* Host Hardware Self-Check & Adaptive Model Selector Panel */}
      <HmiHardwareControlPanel
        aiStatus={aiStatus}
        isLoadingAiStatus={isLoadingAiStatus}
        onRefreshAiStatus={onRefreshAiStatus}
        ollamaModel={ollamaModel}
        setOllamaModel={setOllamaModel}
        onGlobalModelChange={onGlobalModelChange}
        effectiveModelCatalog={effectiveModelCatalog}
        autoUnload={autoUnload}
        setAutoUnload={setAutoUnload}
        isOperatingOllama={isOperatingOllama}
        onControlOllama={onControlOllama}
        pullProgress={pullProgress}
        setPullProgress={setPullProgress}
      />

      {/* Metrics Summary Cards */}
      {semanticReport?.summary && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          <div className="p-2.5 bg-black/40 border border-zinc-800 rounded">
            <div className="text-[10px] text-gray-500 font-bold uppercase">TOTAL ANALYZED</div>
            <div className="text-sm font-bold text-gray-200 mt-0.5">
              {semanticReport.summary.total_phrases} Phrases
            </div>
            <div className="text-[10px] text-gray-500">Cross-referenced against en-GB</div>
          </div>

          <div className="p-2.5 bg-black/40 border border-zinc-800 rounded">
            <div className="text-[10px] text-gray-500 font-bold uppercase">LEARNED GLOSSARY</div>
            <div className="text-sm font-bold text-cyan-300 mt-0.5">
              {semanticReport.summary.glossary_terms_count} Domain Terms
            </div>
            <div className="text-[10px] text-gray-500">Mined from binary co-occurrence</div>
          </div>

          <div className="p-2.5 bg-black/40 border border-zinc-800 rounded">
            <div className="text-[10px] text-gray-500 font-bold uppercase">AVG ALIGNMENT SCORE</div>
            <div className="text-sm font-bold text-emerald-300 mt-0.5">
              {(semanticReport.summary.average_alignment * 100).toFixed(1)}%
            </div>
            <div className="text-[10px] text-gray-500">Consensus & length consistency</div>
          </div>

          <div className="p-2.5 bg-black/40 border border-zinc-800 rounded">
            <div className="text-[10px] text-gray-500 font-bold uppercase">FLAGGED ANOMALIES</div>
            <div
              className={`text-sm font-bold mt-0.5 ${
                semanticReport.summary.flagged_count > 0 ? 'text-amber-400' : 'text-emerald-400'
              }`}
            >
              {semanticReport.summary.flagged_count} Outliers
            </div>
            <div className="text-[10px] text-gray-500">Low alignment or contradictions</div>
          </div>
        </div>
      )}

      {/* Prominent Local Ollama AI Scan Results Panel */}
      {semanticReport?.tier3_ollama?.reviews?.length > 0 && (
        <div className="p-3.5 bg-[#121218] border border-purple-800/70 rounded-lg space-y-3 shadow-[0_0_20px_rgba(168,85,247,0.15)]">
          <div className="flex flex-wrap items-center justify-between gap-2 border-b border-zinc-800/80 pb-2.5">
            <div className="flex items-center space-x-2">
              <Sparkles className="w-4 h-4 text-purple-400" />
              <span className="text-xs font-bold text-purple-200 uppercase tracking-wider font-mono">
                🤖 LOCAL AI SCAN RESULTS
              </span>
              <span className="px-2 py-0.5 text-[10px] font-bold rounded bg-purple-950 text-purple-300 border border-purple-800 font-mono">
                TIER 3 NEURAL AUDIT
              </span>
            </div>
            <button
              onClick={onOpenAiModal}
              className="flex items-center space-x-1.5 px-3 py-1 text-xs font-bold rounded bg-purple-900/60 hover:bg-purple-800 text-purple-200 border border-purple-600 transition-all shadow-sm"
              title="Open AI Scan Results in full-size window"
            >
              <Maximize2 className="w-3.5 h-3.5" />
              <span>🗖 Open AI Results Window</span>
            </button>
          </div>
          <HmiAiResultsView
            isModal={false}
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
      )}

      {/* Tables Grid: 1. Learned Glossary, 2. Flagged Anomalies */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {/* Table 1: Self-Learned Domain Glossary */}
        <div className="bg-[#121218] border border-zinc-800 rounded overflow-hidden">
          <div className="p-2.5 bg-zinc-900/60 border-b border-zinc-800 flex items-center justify-between">
            <span className="text-xs font-bold text-cyan-400 flex items-center space-x-1.5">
              <Box className="w-3.5 h-3.5" />
              <span>Self-Learned Domain Glossary ({semanticReport?.tier1_glossary?.length || 0})</span>
            </span>
            <span className="text-[10px] text-gray-500 font-mono">
              Dice Similarity &gt;= 0.45 • Support &gt;= 2
            </span>
          </div>
          <div className="overflow-x-auto max-h-[360px] overflow-y-auto">
            <table className="w-full text-left border-collapse text-[11px] font-mono">
              <thead className="sticky top-0 bg-zinc-900 border-b border-zinc-800 text-gray-400 text-[10px] uppercase">
                <tr>
                  <th className="p-2">English Concept</th>
                  <th className="p-2">Target Translation ({auditLocale})</th>
                  <th className="p-2 text-center">Support</th>
                  <th className="p-2 text-center">Confidence</th>
                  <th className="p-2 text-center">Dice</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-zinc-800/60 text-gray-300">
                {semanticReport?.tier1_glossary?.map((g, idx) => (
                  <tr key={idx} className="hover:bg-zinc-800/40">
                    <td className="p-2">
                      <span className="font-bold text-gray-200">{g.en_term}</span>{' '}
                      <span className="text-gray-500 font-sans text-[10px]">({g.en_word})</span>
                    </td>
                    <td className="p-2">
                      <span className="font-bold text-cyan-300">{g.target_term}</span>{' '}
                      <span className="text-gray-400 font-sans text-[10px]">({g.target_word})</span>
                    </td>
                    <td className="p-2 text-center text-gray-400">{g.support}</td>
                    <td className="p-2 text-center text-emerald-400 font-bold">
                      {(g.confidence * 100).toFixed(0)}%
                    </td>
                    <td className="p-2 text-center text-blue-400">{g.dice.toFixed(2)}</td>
                  </tr>
                ))}
                {(!semanticReport || !semanticReport.tier1_glossary?.length) && (
                  <tr>
                    <td colSpan={5} className="p-4 text-center text-gray-500">
                      {isLoadingSemantic
                        ? 'Extracting domain glossary from binary...'
                        : 'No glossary loaded. Click "Run Deep Semantic Audit" above.'}
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </div>

        {/* Table 2: Flagged Anomalies & Substitutions */}
        <div className="bg-[#121218] border border-zinc-800 rounded overflow-hidden">
          <div className="p-2.5 bg-zinc-900/60 border-b border-zinc-800 flex items-center justify-between">
            <span className="text-xs font-bold text-amber-400 flex items-center space-x-1.5">
              <AlertTriangle className="w-3.5 h-3.5" />
              <span>Flagged Anomalies & Low Alignment ({flaggedAllCount})</span>
            </span>
            <span className="text-[10px] text-gray-500 font-mono">
              Score &lt; 0.65 or Glossary Contradiction
            </span>
          </div>

          {/* Filter bar for Flagged Anomalies */}
          <div className="px-2.5 py-1.5 bg-black/40 border-b border-zinc-800/80 flex flex-wrap items-center gap-1.5 text-[10px]">
            <button
              onClick={() => setAnomalyFilter('ALL')}
              className={`px-2 py-0.5 rounded font-bold transition-all ${
                anomalyFilter === 'ALL'
                  ? 'bg-zinc-700 text-white'
                  : 'bg-zinc-900 hover:bg-zinc-800 text-zinc-400'
              }`}
            >
              ALL ({flaggedAllCount})
            </button>
            <button
              onClick={() => setAnomalyFilter('OLLAMA_SCANNED')}
              className={`px-2 py-0.5 rounded font-bold transition-all ${
                anomalyFilter === 'OLLAMA_SCANNED'
                  ? 'bg-purple-900/80 text-purple-200 border border-purple-600'
                  : 'bg-zinc-900 hover:bg-zinc-800 text-zinc-400'
              }`}
            >
              🤖 AI SCANNED ({flaggedScannedCount})
            </button>
            <button
              onClick={() => setAnomalyFilter('AI_DEFECTS')}
              className={`px-2 py-0.5 rounded font-bold transition-all ${
                anomalyFilter === 'AI_DEFECTS'
                  ? 'bg-rose-900/80 text-rose-200 border border-rose-600'
                  : 'bg-zinc-900 hover:bg-zinc-800 text-zinc-400'
              }`}
            >
              🚨 AI CONFIRMED DEFECTS ({flaggedDefectsCount})
            </button>
            <button
              onClick={() => setAnomalyFilter('GLOSSARY')}
              className={`px-2 py-0.5 rounded font-bold transition-all ${
                anomalyFilter === 'GLOSSARY'
                  ? 'bg-emerald-900/80 text-emerald-200 border border-emerald-600'
                  : 'bg-zinc-900 hover:bg-zinc-800 text-zinc-400'
              }`}
            >
              📚 WITH SUGGESTED FIX ({flaggedSuggestedCount})
            </button>
          </div>

          <div className="overflow-x-auto max-h-[360px] overflow-y-auto">
            <table className="w-full text-left border-collapse text-[11px]">
              <thead className="sticky top-0 bg-zinc-900 border-b border-zinc-800 text-gray-400 text-[10px] uppercase font-mono">
                <tr>
                  <th className="p-2 w-16 text-center">Score</th>
                  <th className="p-2">Key & Values</th>
                  <th className="p-2">Anomaly Diagnostics</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-zinc-800/60 text-gray-300">
                {filteredFlaggedPhrases.map((fl, idx) => (
                  <tr key={idx} className="hover:bg-zinc-800/40">
                    <td className="p-2 text-center align-top">
                      <span
                        className={`px-1.5 py-0.5 rounded font-mono font-bold text-[10px] ${
                          fl.alignment_score < 0.45
                            ? 'bg-rose-950 text-rose-300 border border-rose-800'
                            : 'bg-amber-950 text-amber-300 border border-amber-800'
                        }`}
                      >
                        {(fl.alignment_score * 100).toFixed(0)}%
                      </span>
                    </td>
                    <td className="p-2 align-top">
                      <div className="flex items-center space-x-1.5">
                        <span className="font-mono font-bold text-gray-200">{fl.key}</span>
                        {fl.ollama_review && (
                          fl.ollama_review.is_correct ? (
                            <span className="px-1 py-0.2 text-[9px] font-bold rounded bg-emerald-950 text-emerald-400 border border-emerald-800">
                              AI OK
                            </span>
                          ) : (
                            <span className="px-1 py-0.2 text-[9px] font-bold rounded bg-rose-950 text-rose-400 border border-rose-800">
                              AI DEFECT
                            </span>
                          )
                        )}
                      </div>
                      <div className="text-gray-400 text-[10px] font-sans truncate max-w-[220px]" title={fl.en_val}>
                        EN: {fl.en_val}
                      </div>
                      <div className="text-amber-300 text-[10px] font-sans truncate max-w-[220px]" title={fl.target_val}>
                        {auditLocale}: {fl.target_val}
                      </div>
                    </td>
                    <td className="p-2 align-top">
                      <div className="text-[10px] text-gray-300 font-sans">{fl.reason}</div>
                      {fl.suggested_val && (
                        <div className="mt-1 text-[10px] text-emerald-400 font-mono flex items-center justify-between">
                          <span className="truncate max-w-[160px]" title={fl.suggested_val}>
                            Fix: {fl.suggested_val}
                          </span>
                        </div>
                      )}
                    </td>
                  </tr>
                ))}
                {(!filteredFlaggedPhrases || !filteredFlaggedPhrases.length) && (
                  <tr>
                    <td colSpan={3} className="p-4 text-center text-gray-500">
                      {isLoadingSemantic
                        ? 'Scoring cross-locale consensus...'
                        : 'No semantic anomalies match the current filter.'}
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </div>
  );
}
