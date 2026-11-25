import React from 'react';
import { Search } from 'lucide-react';

export default function HmiPhraseExplorerView({
  selectedLocale,
  setSelectedLocale,
  languages,
  phrases,
  searchQuery,
  setSearchQuery
}) {
  return (
    <div className="space-y-3">
      {/* Controls Bar */}
      <div className="flex flex-wrap items-center justify-between gap-3 p-2.5 bg-[#121218] border border-zinc-800 rounded">
        <div className="flex items-center space-x-3">
          <span className="text-gray-400 font-bold">Select Locale:</span>
          <select
            value={selectedLocale}
            onChange={(e) => setSelectedLocale(e.target.value)}
            className="bg-black/60 border border-zinc-700 rounded px-2.5 py-1 text-gray-200 font-mono text-xs focus:outline-none focus:border-cyan-500"
          >
            {languages.map((l) => (
              <option key={l.locale} value={l.locale}>
                {l.locale} ({l.phrase_count} phrases)
              </option>
            ))}
          </select>

          <span className="text-gray-500 text-[11px] font-mono">
            {phrases.length} phrases loaded
          </span>
        </div>

        <div className="flex items-center space-x-2">
          <Search className="w-3.5 h-3.5 text-gray-400" />
          <input
            type="text"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="bg-black/60 border border-zinc-700 rounded px-2.5 py-1 text-gray-200 text-xs w-64 focus:outline-none focus:border-cyan-500"
            placeholder="Search key, translation, or VMA..."
          />
        </div>
      </div>

      {/* Phrases Table */}
      <div className="overflow-x-auto rounded border border-zinc-800 bg-[#121218]">
        <table className="w-full text-left border-collapse">
          <thead>
            <tr className="border-b border-zinc-800 bg-zinc-900/60 text-gray-400 font-bold uppercase text-[10px]">
              <th className="p-2 w-12 text-center">#</th>
              <th className="p-2 w-64">Key Identifier</th>
              <th className="p-2 w-24">Key VMA</th>
              <th className="p-2">Translation ({selectedLocale})</th>
              <th className="p-2 w-24">Val VMA</th>
              <th className="p-2 w-24">File Offset</th>
              <th className="p-2">English Reference (en-GB)</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-zinc-800/60 font-mono text-[11px]">
            {phrases.slice(0, 100).map((p) => (
              <tr key={p.key} className="hover:bg-zinc-800/40 text-gray-300">
                <td className="p-2 text-center text-gray-500">{p.index}</td>
                <td className="p-2 font-bold text-gray-200 truncate max-w-[240px]" title={p.key}>
                  {p.key}
                </td>
                <td className="p-2 text-gray-400">{p.key_vma}</td>
                <td className="p-2 font-sans text-cyan-300 truncate max-w-[300px]" title={p.val}>
                  {p.val}
                </td>
                <td className="p-2 text-gray-400">{p.val_vma}</td>
                <td className="p-2 text-gray-400">{p.slot_file_off}</td>
                <td className="p-2 font-sans text-gray-400 truncate max-w-[300px]" title={p.en_ref}>
                  {p.en_ref}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {phrases.length > 100 && (
          <div className="p-2 text-center text-gray-500 text-[10px] border-t border-zinc-800">
            Showing first 100 of {phrases.length} phrases. Use live search above to filter.
          </div>
        )}
      </div>
    </div>
  );
}
