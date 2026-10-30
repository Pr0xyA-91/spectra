import React, { useState } from 'react';
import {
  ShieldCheck,
  AlertTriangle,
  CheckCircle2,
  Wrench,
  FileText,
  Download,
  Coffee,
  Sparkles,
  Layers,
  ChevronRight,
  Info,
} from 'lucide-react';

/**
 * Overview Tab: AI Diagnostic Health Advisor & Beverage Recipe Analytics
 * Replicates 100% of the old UI Overview Tab:
 * - Diagnostic Health Scorecard (0-100%)
 * - Heuristic Maintenance Advisor Cards (Descaling, Switch bounce, BU mechanical health)
 * - Technician Field Service Inspection Checklist
 * - Beverage Specialty Recipe Analytics with proportional distribution bars
 * - 1-Click Customer Service Report & Multi-format Export triggers
 */
export default function DiagnosticAdvisorTab({
  theme,
  statsData,
  liveData,
  selectedPort,
  onOpenServiceReport,
  onOpenExport,
  onInterrogate,
  isInterrogating,
}) {
  const [checklist, setChecklist] = useState({
    chk1: true, // Visual inspection of silicone pressure lines & brass fittings
    chk2: true, // Safety thermal cutoff continuity (TB1: 0.1Ω, TB2: 0.1Ω)
    chk3: false, // Descaling cycle execution & flowmeter verification
    chk4: true, // Clean microswitch contact leaves on rear chassis
  });

  // Empty State: Machine has not been read yet
  if (!statsData) {
    return (
      <div className={`p-8 border rounded ${theme.surfaceClass} text-center space-y-4 font-mono shadow-lg`}>
        <div className="w-16 h-16 rounded-full bg-black/40 border border-[#FCEE09]/40 flex items-center justify-center mx-auto text-[#FCEE09]">
          <ShieldCheck className="w-8 h-8 animate-pulse" />
        </div>
        <div className="space-y-1">
          <h3 className="text-base font-black text-white uppercase tracking-wider">
            MACHINE DATA NOT YET READ
          </h3>
          <p className="text-xs text-zinc-400 max-w-lg mx-auto">
            Diagnostic counters, maintenance cycles, and the automated AI health scorecard require interrogating the machine's EEPROM. Connect to <strong>{selectedPort || 'serial port'}</strong> and click below to read all parameters.
          </p>
        </div>
        <div className="pt-2">
          <button
            onClick={onInterrogate}
            disabled={isInterrogating || !selectedPort}
            className="px-4 py-2 bg-[#FCEE09] hover:bg-yellow-400 text-black font-extrabold text-xs rounded tracking-wider shadow-[0_0_12px_rgba(252,238,9,0.4)] transition-all font-mono disabled:opacity-50"
          >
            {isInterrogating ? 'READING MACHINE DATA...' : '⚡ INTERROGATE MACHINE & READ DATA'}
          </button>
        </div>
      </div>
    );
  }

  // Calculate health score & cards from real interrogated statsData
  const healthScore = statsData.health_score ?? 95;
  const advisorCards = statsData.advisor_cards || [];
  const beverages = statsData.beverages || [];
  const totalPreps = statsData.total_preparations || 0;
  const totalCups = statsData.total_cups || totalPreps;

  // Health Score Color
  const getScoreColor = (sc) => {
    if (sc >= 90) return 'text-emerald-400 border-emerald-500';
    if (sc >= 75) return 'text-amber-400 border-amber-500';
    return 'text-rose-400 border-rose-500';
  };

  return (
    <div className="grid grid-cols-1 lg:grid-cols-12 gap-3">
      {/* ==================================================================== */}
      {/* LEFT COLUMN: AI DIAGNOSTIC HEALTH ADVISOR (7 COLS) */}
      {/* ==================================================================== */}
      <div className="lg:col-span-7 space-y-3">
        {/* Top: Executive Health Scorecard */}
        <div className={`p-4 border rounded ${theme.surfaceClass}`}>
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div>
              <div className="text-[10px] font-bold text-gray-500 uppercase tracking-wider">
                EXECUTIVE APPLIANCE HEALTH SCORECARD
              </div>
              <div className="text-lg font-black font-mono text-gray-200">
                {statsData?.machine_model || 'Jura IMPRESSA XJ5 Pro'}
              </div>
              <div className="text-xs text-gray-400">
                Protocol: <span className="font-mono text-sky-400">{statsData?.protocol_mode || 'Plain ASCII'}</span> | Power: <span className="font-mono text-gray-300">{statsData?.power_spec || '230V / 50Hz'}</span>
              </div>
            </div>

            {/* Circular / Pill Health Score Badge */}
            <div className="flex items-center space-x-3">
              <div className={`w-16 h-16 rounded-full border-4 flex flex-col items-center justify-center font-mono ${getScoreColor(healthScore)} bg-black/40`}>
                <span className="text-xl font-black leading-none">{healthScore}</span>
                <span className="text-[9px] font-bold uppercase text-gray-400">/ 100</span>
              </div>
              <div>
                <div className={`text-xs font-bold uppercase ${healthScore >= 90 ? 'text-emerald-400' : (healthScore >= 75 ? 'text-amber-400' : 'text-rose-400')}`}>
                  {healthScore >= 90 ? 'EXCELLENT HEALTH' : (healthScore >= 75 ? 'ATTENTION REQUIRED' : 'CRITICAL SERVICE')}
                </div>
                <div className="text-[10px] text-gray-500">
                  {healthScore >= 90 ? 'All parameters within DIN-ISO tolerances.' : 'Review recommended maintenance actions below.'}
                </div>
              </div>
            </div>
          </div>

          {/* Quick Action Buttons for Reports */}
          <div className="flex flex-wrap items-center gap-2 mt-4 pt-3 border-t border-gray-800">
            <button
              onClick={onOpenServiceReport}
              className="flex items-center space-x-1.5 px-3 py-1.5 bg-sky-950/60 hover:bg-sky-900 border border-sky-600/60 text-sky-200 font-bold text-xs rounded transition-colors"
            >
              <FileText className="w-3.5 h-3.5" />
              <span>📄 VIEW / PRINT SERVICE CERTIFICATE</span>
            </button>

            <button
              onClick={onOpenExport}
              className="flex items-center space-x-1.5 px-3 py-1.5 bg-purple-950/60 hover:bg-purple-900 border border-purple-600/60 text-purple-200 font-bold text-xs rounded transition-colors"
            >
              <Download className="w-3.5 h-3.5" />
              <span>💾 EXPORT DIAGNOSTIC DATA</span>
            </button>
          </div>
        </div>

        {/* Advisor Recommendation Cards */}
        <div className={`p-4 border rounded ${theme.surfaceClass}`}>
          <div className="flex items-center justify-between mb-3 border-b border-gray-800 pb-2">
            <span className="text-xs font-bold text-gray-300 uppercase tracking-wider flex items-center space-x-1.5">
              <ShieldCheck className="w-4 h-4 text-sky-400" />
              <span>AUTOMATED DIAGNOSTIC HEALTH ADVISOR</span>
            </span>
            <span className="text-[10px] font-mono text-gray-400">
              {advisorCards.length} CHECKS EVALUATED
            </span>
          </div>

          <div className="space-y-2.5">
            {advisorCards.map((card, idx) => {
              const borderCol =
                card.severity === 'ok'
                  ? 'border-emerald-900/60 bg-emerald-950/20'
                  : card.severity === 'warn'
                  ? 'border-amber-900/60 bg-amber-950/20'
                  : card.severity === 'error'
                  ? 'border-rose-900/60 bg-rose-950/20'
                  : 'border-sky-900/60 bg-sky-950/20';

              const titleCol =
                card.severity === 'ok'
                  ? 'text-emerald-400'
                  : card.severity === 'warn'
                  ? 'text-amber-400'
                  : card.severity === 'error'
                  ? 'text-rose-400'
                  : 'text-sky-400';

              return (
                <div key={idx} className={`p-3 border rounded text-xs ${borderCol}`}>
                  <div className="flex items-center space-x-2 font-bold mb-1">
                    <span>{card.icon}</span>
                    <span className={titleCol}>{card.title}</span>
                  </div>
                  <div className="text-gray-300 pl-5 mb-1 leading-relaxed">
                    {card.desc}
                  </div>
                  <div className="text-[11px] font-mono text-gray-400 pl-5">
                    {card.action}
                  </div>
                </div>
              );
            })}
          </div>
        </div>

        {/* Technician Field Service Inspection Checklist */}
        <div className={`p-4 border rounded ${theme.surfaceClass}`}>
          <div className="text-xs font-bold text-gray-300 uppercase tracking-wider mb-2 flex items-center space-x-1.5 border-b border-gray-800 pb-2">
            <Wrench className="w-4 h-4 text-purple-400" />
            <span>TECHNICIAN FIELD SERVICE CHECKLIST</span>
          </div>
          <div className="space-y-2 text-xs">
            <label className="flex items-start space-x-2.5 cursor-pointer text-gray-300 hover:text-white">
              <input
                type="checkbox"
                checked={checklist.chk1}
                onChange={(e) => setChecklist({ ...checklist, chk1: e.target.checked })}
                className="mt-0.5 rounded accent-sky-500"
              />
              <span>Visual inspection of silicone pressure lines &amp; brass fittings</span>
            </label>
            <label className="flex items-start space-x-2.5 cursor-pointer text-gray-300 hover:text-white">
              <input
                type="checkbox"
                checked={checklist.chk2}
                onChange={(e) => setChecklist({ ...checklist, chk2: e.target.checked })}
                className="mt-0.5 rounded accent-sky-500"
              />
              <span>Safety thermal cutoff continuity (TB1: 0.1Ω, TB2: 0.1Ω)</span>
            </label>
            <label className="flex items-start space-x-2.5 cursor-pointer text-gray-300 hover:text-white">
              <input
                type="checkbox"
                checked={checklist.chk3}
                onChange={(e) => setChecklist({ ...checklist, chk3: e.target.checked })}
                className="mt-0.5 rounded accent-sky-500"
              />
              <span>Descaling cycle execution &amp; flowmeter impulse verification</span>
            </label>
            <label className="flex items-start space-x-2.5 cursor-pointer text-gray-300 hover:text-white">
              <input
                type="checkbox"
                checked={checklist.chk4}
                onChange={(e) => setChecklist({ ...checklist, chk4: e.target.checked })}
                className="mt-0.5 rounded accent-sky-500"
              />
              <span>Clean microswitch contact leaf springs on rear chassis with IPA</span>
            </label>
          </div>
        </div>
      </div>

      {/* ==================================================================== */}
      {/* RIGHT COLUMN: BEVERAGE PREPARATION RECIPE ANALYTICS (5 COLS) */}
      {/* ==================================================================== */}
      <div className="lg:col-span-5 space-y-3">
        <div className={`p-4 border rounded ${theme.surfaceClass}`}>
          <div className="flex items-center justify-between mb-3 border-b border-gray-800 pb-2">
            <span className="text-xs font-bold text-gray-300 uppercase tracking-wider flex items-center space-x-1.5">
              <Coffee className="w-4 h-4 text-amber-400" />
              <span>BEVERAGE RECIPE ANALYTICS</span>
            </span>
            <span className="text-xs font-mono font-bold text-sky-400">
              {totalPreps} PREPS ({totalCups} CUPS)
            </span>
          </div>

          <div className="space-y-3">
            {beverages.map((bev) => {
              const count = bev.count || 0;
              const pct = totalPreps > 0 ? (count / totalPreps) * 100 : 0;
              return (
                <div key={bev.code} className="space-y-1">
                  <div className="flex items-center justify-between text-xs font-mono">
                    <span className="font-bold text-gray-200">{bev.name}</span>
                    <span className="text-gray-400">
                      <strong className="text-white">{count}</strong> ({pct.toFixed(1)}%)
                    </span>
                  </div>

                  {/* Visual Proportion Bar */}
                  <div className="w-full h-2 bg-gray-800 rounded-full overflow-hidden">
                    <div
                      className={`h-full transition-all duration-300 ${
                        bev.type === 'Milk'
                          ? 'bg-purple-500'
                          : bev.type === 'Water'
                          ? 'bg-cyan-500'
                          : 'bg-amber-500'
                      }`}
                      style={{ width: `${Math.max(1, pct)}%` }}
                    />
                  </div>
                </div>
              );
            })}
          </div>

          {/* Beverage Categories Legend */}
          <div className="mt-4 pt-3 border-t border-gray-800 flex items-center justify-between text-[11px] font-mono text-gray-400">
            <span className="flex items-center space-x-1.5">
              <span className="w-2.5 h-2.5 rounded-full bg-amber-500 inline-block" />
              <span>Coffee / Espresso</span>
            </span>
            <span className="flex items-center space-x-1.5">
              <span className="w-2.5 h-2.5 rounded-full bg-purple-500 inline-block" />
              <span>Milk Specialties</span>
            </span>
            <span className="flex items-center space-x-1.5">
              <span className="w-2.5 h-2.5 rounded-full bg-cyan-500 inline-block" />
              <span>Hot Water</span>
            </span>
          </div>
        </div>
      </div>
    </div>
  );
}
