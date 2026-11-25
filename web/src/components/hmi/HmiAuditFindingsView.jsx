import React from 'react';
import { CheckCircle2, AlertTriangle, Info } from 'lucide-react';
import { AUDIT_FALLBACK_LOCALES } from './hmiConstants';

export default function HmiAuditFindingsView({
  severityFilter,
  setSeverityFilter,
  auditLocale,
  languages,
  filteredFindings,
  selectedFinding,
  setSelectedFinding,
  onChangeAuditLocale
}) {
  const localeOptions = languages.length > 0 ? languages.map((l) => l.locale) : AUDIT_FALLBACK_LOCALES;

  return (
    <div className="space-y-4">
      {/* Filters Bar */}
      <div className="flex flex-wrap items-center justify-between gap-3 bg-zinc-900/60 p-2.5 rounded border border-zinc-800">
        <div className="flex items-center space-x-2">
          <span className="text-gray-400 font-bold">Severity Filter:</span>
          {['ALL', 'CRITICAL', 'WARNING', 'FIXED'].map((sev) => (
            <button
              key={sev}
              onClick={() => setSeverityFilter(sev)}
              className={`px-2.5 py-0.5 rounded text-[11px] font-bold transition-all border ${
                severityFilter === sev
                  ? 'bg-cyan-950 border-cyan-500 text-cyan-300 shadow-[0_0_8px_rgba(6,182,212,0.3)]'
                  : 'bg-zinc-900 border-zinc-800 text-gray-400 hover:text-gray-200'
              }`}
            >
              {sev}
            </button>
          ))}
        </div>

        <div className="flex items-center space-x-2">
          <span className="text-gray-400 font-bold">Target Audit Locale:</span>
          <select
            value={auditLocale}
            onChange={(e) => onChangeAuditLocale(e.target.value)}
            className="bg-black/80 border border-zinc-700 rounded px-2.5 py-1 text-cyan-300 font-mono text-[11px] focus:outline-none focus:border-cyan-500"
          >
            {localeOptions.map((loc) => (
              <option key={loc} value={loc} className="bg-zinc-900 text-gray-200">
                {loc} {loc === 'cs-CZ' ? '(Czech Republic — Target)' : loc === 'en-GB' ? '(English UK — Base)' : ''}
              </option>
            ))}
          </select>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-12 gap-4">
        {/* Findings Table */}
        <div className="lg:col-span-8 overflow-x-auto rounded border border-zinc-800 bg-[#121218]">
          <table className="w-full text-left border-collapse">
            <thead>
              <tr className="border-b border-zinc-800 bg-zinc-900/60 text-gray-400 font-bold uppercase text-[10px]">
                <th className="p-2.5">Severity</th>
                <th className="p-2.5">Finding ID / Key</th>
                <th className="p-2.5">Locale</th>
                <th className="p-2.5">Current Value</th>
                <th className="p-2.5">Target Value</th>
                <th className="p-2.5">Status</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-zinc-800/60">
              {filteredFindings.map((f) => {
                const isSelected = selectedFinding?.id === f.id;
                return (
                  <tr
                    key={f.id}
                    onClick={() => setSelectedFinding(f)}
                    className={`cursor-pointer transition-colors ${
                      isSelected ? 'bg-cyan-950/40 text-cyan-200' : 'hover:bg-zinc-800/40 text-gray-300'
                    }`}
                  >
                    <td className="p-2.5">
                      {f.severity === 'CRITICAL' && (
                        <span className="px-2 py-0.5 rounded font-extrabold text-[10px] bg-rose-950 border border-rose-500 text-rose-300">
                          CRITICAL
                        </span>
                      )}
                      {f.severity === 'WARNING' && (
                        <span className="px-2 py-0.5 rounded font-extrabold text-[10px] bg-amber-950 border border-amber-500 text-amber-300">
                          WARNING
                        </span>
                      )}
                      {f.severity === 'INFO' && (
                        <span className="px-2 py-0.5 rounded font-extrabold text-[10px] bg-blue-950 border border-blue-500 text-blue-300">
                          INFO
                        </span>
                      )}
                    </td>
                    <td className="p-2.5 font-mono text-[11px] font-bold">
                      <div>{f.id}</div>
                      <div className="text-[10px] text-gray-400 font-normal">{f.key}</div>
                    </td>
                    <td className="p-2.5 font-mono">{f.locale}</td>
                    <td className="p-2.5 text-gray-200 truncate max-w-[160px]" title={f.current_val}>
                      {f.current_val}
                    </td>
                    <td className="p-2.5 text-cyan-300 truncate max-w-[160px]" title={f.expected_val}>
                      {f.expected_val}
                    </td>
                    <td className="p-2.5">
                      {f.status === 'FIXED' ? (
                        <span className="px-2 py-0.5 rounded font-bold text-[10px] bg-emerald-950 border border-emerald-500 text-emerald-300 flex items-center space-x-1 w-fit">
                          <CheckCircle2 className="w-3 h-3" />
                          <span>FIXED</span>
                        </span>
                      ) : (
                        <span className="px-2 py-0.5 rounded font-bold text-[10px] bg-rose-950/80 border border-rose-600 text-rose-300 flex items-center space-x-1 w-fit">
                          <AlertTriangle className="w-3 h-3" />
                          <span>DETECTED</span>
                        </span>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>

        {/* Finding Detail Card */}
        <div className="lg:col-span-4 rounded border border-zinc-800 bg-[#121218] p-4 space-y-3">
          <h3 className="text-xs font-bold uppercase tracking-wider text-cyan-400 flex items-center space-x-1.5 border-b border-zinc-800 pb-2">
            <Info className="w-4 h-4" />
            <span>Finding Root Cause & Remediation</span>
          </h3>

          {selectedFinding ? (
            <div className="space-y-3 text-gray-300">
              <div>
                <div className="text-[10px] text-gray-500 font-bold uppercase">DEFECT ID & CATEGORY</div>
                <div className="text-xs font-bold text-gray-100">{selectedFinding.id}</div>
                <div className="text-[11px] text-cyan-300">{selectedFinding.category}</div>
              </div>

              <div>
                <div className="text-[10px] text-gray-500 font-bold uppercase">DESCRIPTION</div>
                <div className="text-xs text-gray-300 leading-relaxed bg-black/40 p-2.5 rounded border border-zinc-800/80 mt-1">
                  {selectedFinding.description}
                </div>
              </div>

              <div className="grid grid-cols-2 gap-2 text-[11px]">
                <div>
                  <span className="text-gray-500">Locale:</span>{' '}
                  <span className="font-mono text-gray-200">{selectedFinding.locale}</span>
                </div>
                <div>
                  <span className="text-gray-500">Patchable:</span>{' '}
                  <span className="font-bold text-emerald-400">Yes (Pointer / Instruction)</span>
                </div>
              </div>

              <div className="space-y-1.5 p-2 bg-black/60 rounded border border-zinc-800 text-[11px] font-mono">
                <div>
                  <span className="text-gray-500">Current String:</span>{' '}
                  <span className="text-rose-300">"{selectedFinding.current_val}"</span>
                </div>
                <div>
                  <span className="text-gray-500">Target String:</span>{' '}
                  <span className="text-emerald-300">"{selectedFinding.expected_val}"</span>
                </div>
                <div>
                  <span className="text-gray-500">Virtual VMA:</span>{' '}
                  <span className="text-cyan-300">0x{Number(selectedFinding?.vma ?? 0).toString(16).padStart(8, '0')}</span>
                </div>
                <div>
                  <span className="text-gray-500">File Offset:</span>{' '}
                  <span className="text-cyan-300">0x{Number(selectedFinding?.file_offset ?? 0).toString(16).padStart(8, '0')}</span>
                </div>
              </div>
            </div>
          ) : (
            <div className="text-gray-500 text-center py-8">Select any audit finding to inspect technical details.</div>
          )}
        </div>
      </div>
    </div>
  );
}
