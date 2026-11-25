import React from 'react';
import {
  RefreshCw,
  Play,
  Pause,
  Sliders,
  Check,
  Copy,
  Terminal,
  Database
} from 'lucide-react';

export default function RawSensorTelemetryView({
  theme,
  rawSensorData,
  selectedFieldKey,
  setSelectedFieldKey,
  selectedSensorField,
  isRawPolling,
  setIsRawPolling,
  onQueryRawSensors,
  copiedFrame,
  onCopyText,
  sensorMapForm,
  setSensorMapForm,
  isSavingSensorMap,
  onSaveSensorMapping,
  onResetSensorMappings
}) {
  return (
    <div className="space-y-4">
      {/* Wire Frames Terminal Box */}
      <div className={`p-4 border ${theme.border} ${theme.panelBg} ${theme.clipClass} space-y-3 font-mono shadow-md`}>
        <div className="flex items-center justify-between border-b border-zinc-800 pb-2">
          <div className="flex items-center space-x-2">
            <Terminal className="w-4 h-4 text-cyan-400" />
            <span className="font-bold text-xs text-white uppercase tracking-wider">
              RAW UART WIRE FRAMES [DIRECT MICROCONTROLLER BUS RESPONSES]
            </span>
          </div>
          <div className="flex items-center space-x-2 text-xs">
            <button
              onClick={() => setIsRawPolling(!isRawPolling)}
              className={`flex items-center space-x-1 px-2.5 py-0.5 rounded font-bold ${
                isRawPolling
                  ? 'bg-emerald-950 text-emerald-400 border border-emerald-500'
                  : 'bg-zinc-800 text-zinc-400 border border-zinc-700'
              }`}
            >
              {isRawPolling ? <Pause className="w-3 h-3" /> : <Play className="w-3 h-3" />}
              <span>{isRawPolling ? 'AUTO POLL (1.2s)' : 'PAUSED'}</span>
            </button>
            <button
              onClick={onQueryRawSensors}
              className="p-1 bg-zinc-800 hover:bg-zinc-700 text-zinc-200 border border-zinc-700 rounded"
              title="Manual Wire Interrogation"
            >
              <RefreshCw className="w-3.5 h-3.5" />
            </button>
          </div>
        </div>

        {/* Wire Raw Frame Strings with Copy Buttons */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-2 text-xs">
          {[
            { label: 'HZ: (Operational State)', val: rawSensorData.frames?.HZ || '---' },
            { label: 'AS: (Coffee Heater NTC Diagnostic)', val: rawSensorData.frames?.AS || '---' },
            { label: 'CS: (Component Triacs)', val: rawSensorData.frames?.CS || '---' },
            { label: 'RE:0028 (Fault Latch)', val: rawSensorData.frames?.RE_0028 || '---' },
          ].map((f) => (
            <div key={f.label} className="bg-black/60 p-2 rounded border border-zinc-800 flex items-center justify-between gap-2">
              <div className="truncate">
                <span className="text-[10px] text-zinc-400 uppercase block">{f.label}</span>
                <span className="text-cyan-300 font-mono font-bold">{f.val}</span>
              </div>
              <button
                onClick={() => onCopyText(f.val, f.label)}
                className="p-1 text-zinc-400 hover:text-white"
                title="Copy Raw Wire String"
              >
                {copiedFrame === f.label ? <Check className="w-3.5 h-3.5 text-emerald-400" /> : <Copy className="w-3.5 h-3.5" />}
              </button>
            </div>
          ))}
        </div>
      </div>

      {/* Raw Sensor Field Breakdown Table & Value Mapper Layout */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-4">
        {/* Left: Decoded Sensor Fields Table */}
        <div className="lg:col-span-7 space-y-2">
          <div className={`border ${theme.border} ${theme.panelBg} ${theme.clipClass} overflow-hidden shadow-inner`}>
            <div className="p-2 bg-[#121218] border-b border-zinc-800 flex items-center justify-between text-xs font-mono">
              <span className="font-bold text-white uppercase tracking-wider">
                FIELD-BY-FIELD TELEMETRY TRANSLATION
              </span>
              <span className="text-[11px] text-zinc-400">
                Click field to map engineering unit & formula
              </span>
            </div>

            <div className="max-h-[560px] overflow-y-auto font-mono text-xs">
              <table className="w-full border-collapse">
                <thead className="sticky top-0 bg-[#121218] border-b border-zinc-800 text-zinc-400 text-[11px] uppercase tracking-wider select-none z-10">
                  <tr>
                    <th className="py-2 px-2 text-left w-16">Key</th>
                    <th className="py-2 px-2 text-left">Parameter Name</th>
                    <th className="py-2 px-2 text-left w-16">Raw Hex</th>
                    <th className="py-2 px-2 text-left w-16">Decimal</th>
                    <th className="py-2 px-2 text-left w-24">Scaled Value</th>
                    <th className="py-2 px-2 text-left w-16">Status</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-zinc-800/60">
                  {rawSensorData.fields?.map((f) => {
                    const isSelected = f.key === selectedFieldKey;
                    return (
                      <tr
                        key={f.key}
                        onClick={() => setSelectedFieldKey(f.key)}
                        className={`cursor-pointer transition-colors ${
                          isSelected
                            ? 'bg-cyan-950/40 text-white font-bold border-l-4 border-l-[#00F0FF]'
                            : 'hover:bg-zinc-800/50 text-zinc-300'
                        }`}
                      >
                        <td className="py-2 px-2 font-mono font-bold text-cyan-400">
                          {f.key}
                        </td>
                        <td className="py-2 px-2 truncate max-w-[170px]" title={f.notes}>
                          <span className={isSelected ? 'text-[#00F0FF]' : 'text-zinc-200'}>
                            {f.name}
                          </span>
                        </td>
                        <td className="py-2 px-2 font-mono text-[#FCEE09]">
                          0x{f.raw_hex}
                        </td>
                        <td className="py-2 px-2 font-mono text-zinc-200">
                          {f.raw_dec ?? '---'}
                        </td>
                        <td className="py-2 px-2 font-mono text-emerald-400 font-bold">
                          {f.formatted || `${f.scaled_val ?? '---'} ${f.unit}`}
                        </td>
                        <td className="py-2 px-2">
                          {f.is_custom ? (
                            <span className="text-[10px] px-1.5 py-0.5 bg-cyan-950 text-cyan-300 border border-cyan-500 rounded font-bold">
                              CUSTOM
                            </span>
                          ) : (
                            <span className="text-[10px] px-1.5 py-0.5 bg-zinc-800 text-zinc-400 rounded">
                              DEFAULT
                            </span>
                          )}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </div>
        </div>

        {/* Right: Field Inspector & Value Mapper Form */}
        <div className="lg:col-span-5 space-y-4">
          {/* Field Deep Inspector */}
          <div className={`p-4 border ${theme.border} ${theme.panelBg} ${theme.clipClass} space-y-3 font-mono shadow-md`}>
            <div className="flex items-center justify-between border-b border-zinc-800 pb-2">
              <div className="flex items-center space-x-2">
                <Sliders className="w-4 h-4 text-cyan-400" />
                <span className="font-bold text-xs text-white uppercase tracking-wider">
                  SENSOR FIELD TRANSLATION: {selectedSensorField.key}
                </span>
              </div>
              <span className="text-[10px] px-2 py-0.5 bg-black/60 border border-zinc-700 text-cyan-300 font-bold rounded">
                {selectedSensorField.category}
              </span>
            </div>

            {/* 4 Translation Metric Cards */}
            <div className="grid grid-cols-2 gap-2 text-xs">
              <div className="bg-black/50 p-2.5 rounded border border-zinc-800">
                <span className="text-[10px] text-zinc-400 uppercase block">RAW HEX VALUE:</span>
                <span className="text-lg font-mono font-bold text-[#FCEE09]">
                  0x{selectedSensorField.raw_hex}
                </span>
              </div>
              <div className="bg-black/50 p-2.5 rounded border border-zinc-800">
                <span className="text-[10px] text-zinc-400 uppercase block">DECIMAL VALUE:</span>
                <span className="text-lg font-mono font-bold text-zinc-200">
                  {selectedSensorField.raw_dec ?? '---'}
                </span>
              </div>
              <div className="bg-black/50 p-2.5 rounded border border-zinc-800">
                <span className="text-[10px] text-zinc-400 uppercase block">ENGINEERING SCALED:</span>
                <span className="text-base font-mono font-bold text-emerald-400">
                  {selectedSensorField.formatted}
                </span>
              </div>
              <div className="bg-black/50 p-2.5 rounded border border-zinc-800">
                <span className="text-[10px] text-zinc-400 uppercase block">SCALE FORMULA:</span>
                <span className="text-xs font-mono font-bold text-cyan-300">
                  {selectedSensorField.scale === 1.0 ? 'x 1.0' : `x ${selectedSensorField.scale}`} ({selectedSensorField.unit || 'raw'})
                </span>
              </div>
            </div>

            {/* Binary Bitfield string */}
            {selectedSensorField.raw_bin && (
              <div className="bg-black/40 p-2 rounded border border-zinc-800">
                <span className="text-[10px] text-zinc-400 uppercase block mb-1">BINARY REPRESENTATION:</span>
                <span className="text-xs font-mono text-cyan-400 font-bold tracking-widest break-all">
                  {selectedSensorField.raw_bin}
                </span>
              </div>
            )}

            {/* Live Interpretation / Notes */}
            <div className="p-2.5 bg-zinc-900/80 rounded border border-zinc-800 text-xs text-zinc-300">
              <span className="text-[10px] text-zinc-500 uppercase block font-bold mb-0.5">
                FIRMWARE & PHYSICAL INTERPRETATION:
              </span>
              <span>{selectedSensorField.notes || selectedSensorField.desc}</span>
            </div>
          </div>

          {/* Sensor Value Mapping Form */}
          <div className={`p-4 border ${theme.border} ${theme.panelBg} ${theme.clipClass} space-y-3 font-mono shadow-md`}>
            <div className="flex items-center justify-between border-b border-zinc-800 pb-2">
              <div className="flex items-center space-x-2">
                <Database className="w-4 h-4 text-[#00F0FF]" />
                <span className="font-bold text-xs text-white uppercase tracking-wider">
                  MAP SENSOR VALUE [{selectedSensorField.key}]
                </span>
              </div>
              <span className="text-[10px] text-zinc-500">
                custom_sensor_mappings.json
              </span>
            </div>

            <form onSubmit={onSaveSensorMapping} className="space-y-2.5 text-xs">
              <div>
                <label className="block text-[11px] text-zinc-400 mb-1">FIELD LABEL / NAME:</label>
                <input
                  type="text"
                  value={sensorMapForm.name}
                  onChange={(e) => setSensorMapForm({ ...sensorMapForm, name: e.target.value })}
                  placeholder="e.g. Coffee Thermoblock NTC"
                  className="w-full bg-black/60 border border-zinc-700 px-2.5 py-1.5 rounded text-zinc-200 font-mono outline-none focus:border-[#00F0FF]"
                />
              </div>

              <div className="grid grid-cols-2 gap-2">
                <div>
                  <label className="block text-[11px] text-zinc-400 mb-1">CATEGORY:</label>
                  <select
                    value={sensorMapForm.category}
                    onChange={(e) => setSensorMapForm({ ...sensorMapForm, category: e.target.value })}
                    className="w-full bg-black/60 border border-zinc-700 px-2 py-1.5 rounded text-zinc-200 font-mono outline-none focus:border-[#00F0FF]"
                  >
                    <option value="Thermal">Thermal</option>
                    <option value="Hydraulics">Hydraulics</option>
                    <option value="Brew Unit">Brew Unit</option>
                    <option value="Optical Hopper">Optical Hopper</option>
                    <option value="Status">Status</option>
                    <option value="Safety">Safety</option>
                    <option value="Actuators">Actuators</option>
                    <option value="User Interface">User Interface</option>
                    <option value="Chassis">Chassis</option>
                    <option value="General">General</option>
                  </select>
                </div>

                <div>
                  <label className="block text-[11px] text-zinc-400 mb-1">ENGINEERING UNIT:</label>
                  <input
                    type="text"
                    value={sensorMapForm.unit}
                    onChange={(e) => setSensorMapForm({ ...sensorMapForm, unit: e.target.value })}
                    placeholder="e.g. °C, ticks, pulses"
                    className="w-full bg-black/60 border border-zinc-700 px-2.5 py-1.5 rounded text-zinc-200 font-mono outline-none focus:border-[#00F0FF]"
                  />
                </div>
              </div>

              <div className="grid grid-cols-2 gap-2">
                <div>
                  <label className="block text-[11px] text-zinc-400 mb-1">SCALE MULTIPLIER:</label>
                  <input
                    type="number"
                    step="any"
                    value={sensorMapForm.scale}
                    onChange={(e) => setSensorMapForm({ ...sensorMapForm, scale: parseFloat(e.target.value) || 1.0 })}
                    placeholder="e.g. 0.1 for 10x ADC"
                    className="w-full bg-black/60 border border-zinc-700 px-2.5 py-1.5 rounded text-zinc-200 font-mono outline-none focus:border-[#00F0FF]"
                  />
                </div>

                <div className="flex items-end">
                  <span className="text-[10px] text-zinc-500 pb-2">
                    Formula: <code>val * scale {sensorMapForm.unit}</code>
                  </span>
                </div>
              </div>

              <div>
                <label className="block text-[11px] text-zinc-400 mb-1">FIELD DOCUMENTATION / NOTES:</label>
                <textarea
                  rows={2}
                  value={sensorMapForm.desc}
                  onChange={(e) => setSensorMapForm({ ...sensorMapForm, desc: e.target.value })}
                  placeholder="Calibration details or physical sensor notes..."
                  className="w-full bg-black/60 border border-zinc-700 px-2.5 py-1.5 rounded text-zinc-200 font-mono outline-none focus:border-[#00F0FF] resize-none"
                />
              </div>

              <div className="pt-2 flex items-center justify-between">
                <button
                  type="button"
                  onClick={onResetSensorMappings}
                  className="text-[11px] text-zinc-400 hover:text-red-400 underline font-mono"
                >
                  Reset Defaults
                </button>

                <button
                  type="submit"
                  disabled={isSavingSensorMap || !sensorMapForm.name.trim()}
                  className="px-3 py-1.5 bg-[#00F0FF] hover:bg-cyan-300 text-black font-extrabold rounded font-mono text-xs flex items-center space-x-1 shadow-[0_0_10px_rgba(0,240,255,0.4)] disabled:opacity-50"
                >
                  <Check className="w-3.5 h-3.5" />
                  <span>{isSavingSensorMap ? 'SAVING...' : '💾 SAVE SENSOR MAPPING'}</span>
                </button>
              </div>
            </form>
          </div>
        </div>
      </div>
    </div>
  );
}
