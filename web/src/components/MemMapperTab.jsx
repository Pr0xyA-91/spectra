import React, { useState, useEffect, useRef, useCallback } from 'react';
import {
  Cpu,
  Zap,
  RefreshCw,
  Search,
  Filter,
  CheckCircle2,
  AlertTriangle,
  Play,
  Pause,
  Sliders,
  Check,
  X,
  Copy,
  Layers,
  Terminal,
  Database,
  SlidersHorizontal,
  Flame,
  Gauge,
  Droplet,
  Shield,
  Eye,
  Trash2,
  Info
} from 'lucide-react';

export default function MemMapperTab({ theme, selectedPort, liveData }) {
  // Sub-tab: 'eeprom' or 'raw_sensors'
  const [subTab, setSubTab] = useState('eeprom');

  // Mapper info & EEPROM registers state
  const [mapperInfo, setMapperInfo] = useState(null);
  const [registers, setRegisters] = useState([]);
  const [selectedAddr, setSelectedAddr] = useState(0x0040); // Default to BU Upper Limit
  const [summary, setSummary] = useState({
    total_words: 512,
    mapped: 0,
    theoretical: 0,
    unknown: 0,
    blank: 0,
    changed: 0,
    coverage_pct: 0
  });

  // Loading & Action states
  const [isSweeping, setIsSweeping] = useState(false);
  const [sweepProgress, setSweepProgress] = useState({ current: 0, total: 32 });
  const [isLiveDiff, setIsLiveDiff] = useState(false);
  const [statusMessage, setStatusMessage] = useState(null);
  const [statusType, setStatusType] = useState('info'); // 'info' | 'success' | 'warn'

  // Filter & Search
  const [filterType, setFilterType] = useState('all'); // 'all', 'mapped', 'theoretical', 'unknown', 'blank', 'changed'
  const [searchQuery, setSearchQuery] = useState('');

  // Mapping Form State for Selected Register
  const [mapForm, setMapForm] = useState({
    name: '',
    desc: '',
    category: 'settings',
    unit: '',
    status: 'mapped'
  });
  const [isSavingReg, setIsSavingReg] = useState(false);

  // Differential Scope Event Stream Log
  const [diffEvents, setDiffEvents] = useState([]);
  const [isDiffPaused, setIsDiffPaused] = useState(false);

  // --------------------------------------------------------------------------
  // Sub-Tab 2: Raw Sensor Telemetry State
  // --------------------------------------------------------------------------
  const [rawSensorData, setRawSensorData] = useState({
    frames: {},
    fields: [],
    custom_mappings: {}
  });
  const [selectedFieldKey, setSelectedFieldKey] = useState('HZ_4'); // Default to TB1 Temp
  const [isRawPolling, setIsRawPolling] = useState(true);
  const [sensorMapForm, setSensorMapForm] = useState({
    key: 'HZ_4',
    name: '',
    category: 'Thermal',
    unit: '°C',
    scale: 0.1,
    desc: ''
  });
  const [isSavingSensorMap, setIsSavingSensorMap] = useState(false);
  const [copiedFrame, setCopiedFrame] = useState(null);

  // --------------------------------------------------------------------------
  // 1. Fetch Mapper Identity & Summary
  // --------------------------------------------------------------------------
  const fetchMapperInfo = useCallback(async () => {
    if (!selectedPort) return;
    try {
      const res = await fetch(`/api/mapper/info?port=${encodeURIComponent(selectedPort)}`);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      if (data.error) {
        setStatusMessage(data.error);
        setStatusType('warn');
        return;
      }
      setMapperInfo(data);
      if (data.summary) {
        setSummary(data.summary);
      }
    } catch (err) {
      console.warn('Failed to fetch mapper info:', err);
    }
  }, [selectedPort]);

  // --------------------------------------------------------------------------
  // 2. Full Memory Sweep
  // --------------------------------------------------------------------------
  const handleFullSweep = async () => {
    if (!selectedPort) return;
    setIsSweeping(true);
    setStatusMessage('Executing safe EEPROM sweep over UART...');
    setStatusType('info');

    try {
      const res = await fetch(`/api/mapper/sweep?port=${encodeURIComponent(selectedPort)}&block=all`);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();

      if (data.error) {
        setStatusMessage(`Sweep failed: ${data.error}`);
        setStatusType('warn');
      } else {
        setRegisters(data.registers || []);
        if (data.summary) setSummary(data.summary);
        setStatusMessage(`Sweep complete: ${data.registers?.length || 0} words verified.`);
        setStatusType('success');
      }
    } catch (err) {
      setStatusMessage(`Sweep error: ${err.message}`);
      setStatusType('warn');
    } finally {
      setIsSweeping(false);
    }
  };

  // --------------------------------------------------------------------------
  // 3. Baseline Capture
  // --------------------------------------------------------------------------
  const handleCaptureBaseline = async () => {
    if (!selectedPort) return;
    try {
      const res = await fetch('/api/mapper/baseline', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ port: selectedPort })
      });
      const data = await res.json();
      if (data.success) {
        setStatusMessage('Baseline snapshot captured. Differential scope initialized.');
        setStatusType('success');
        if (data.summary) setSummary(data.summary);
        // Refresh registers to recalculate deltas
        handleFullSweep();
      } else {
        setStatusMessage(`Baseline capture failed: ${data.error}`);
        setStatusType('warn');
      }
    } catch (err) {
      setStatusMessage(`Error: ${err.message}`);
      setStatusType('warn');
    }
  };

  // --------------------------------------------------------------------------
  // 4. Live Differential Polling
  // --------------------------------------------------------------------------
  const pollDiff = useCallback(async () => {
    if (!selectedPort || !isLiveDiff) return;
    try {
      const res = await fetch(`/api/mapper/diff?port=${encodeURIComponent(selectedPort)}`);
      if (!res.ok) return;
      const data = await res.json();

      if (data.summary) setSummary(data.summary);

      if (data.changed_registers && data.changed_registers.length > 0) {
        // Update local register entries with new values
        setRegisters((prev) => {
          const map = new Map(prev.map((r) => [r.addr, r]));
          for (const ch of data.changed_registers) {
            map.set(ch.addr, ch);
          }
          return Array.from(map.values()).sort((a, b) => a.addr - b.addr);
        });

        // Append to differential scope log
        if (!isDiffPaused) {
          const timestamp = new Date().toLocaleTimeString();
          const newEvents = data.changed_registers.map((r) => ({
            timestamp,
            addrHex: r.hex_addr,
            name: r.name,
            oldVal: r.baseline_hex,
            newVal: r.val_hex,
            flips: r.bits_flipped
          }));
          setDiffEvents((prev) => [...newEvents, ...prev.slice(0, 99)]);
        }
      }
    } catch (err) {
      console.warn('Diff poll failed:', err);
    }
  }, [selectedPort, isLiveDiff, isDiffPaused]);

  // Diff polling timer
  useEffect(() => {
    if (!isLiveDiff) return;
    const interval = setInterval(pollDiff, 1500);
    return () => clearInterval(interval);
  }, [isLiveDiff, pollDiff]);

  // --------------------------------------------------------------------------
  // 5. Register Selection & Form Population
  // --------------------------------------------------------------------------
  const selectedRegister = registers.find((r) => r.addr === selectedAddr) || {
    addr: selectedAddr,
    hex_addr: selectedAddr.toString(16).toUpperCase().padStart(4, '0'),
    val: 0,
    val_hex: '0x0000',
    val_dec: 0,
    status: 'blank',
    name: `Reg_0x${selectedAddr.toString(16).toUpperCase().padStart(4, '0')}`,
    desc: 'Unmapped register',
    category: 'settings',
    unit: '',
    baseline_val: 0,
    baseline_hex: '0x0000',
    delta: 0,
    bits_flipped: [],
    high_byte: 0,
    low_byte: 0,
    signed_val: 0,
    ascii_repr: '..'
  };

  useEffect(() => {
    if (selectedRegister) {
      setMapForm({
        name: selectedRegister.name || '',
        desc: selectedRegister.desc || '',
        category: selectedRegister.category || 'settings',
        unit: selectedRegister.unit || '',
        status: selectedRegister.status === 'blank' || selectedRegister.status === 'unknown' ? 'mapped' : selectedRegister.status
      });
    }
  }, [selectedAddr, registers]);

  // --------------------------------------------------------------------------
  // 6. Save Register Mapping into Model Spec
  // --------------------------------------------------------------------------
  const handleSaveRegisterMapping = async (e) => {
    if (e) e.preventDefault();
    if (!selectedPort || !mapForm.name.trim()) return;
    setIsSavingReg(true);

    try {
      const res = await fetch('/api/mapper/map_register', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          port: selectedPort,
          addr: selectedAddr,
          name: mapForm.name.trim(),
          desc: mapForm.desc.trim(),
          category: mapForm.category,
          unit: mapForm.unit.trim(),
          status: mapForm.status
        })
      });
      const data = await res.json();

      if (data.success) {
        setStatusMessage(data.message || 'Saved to model specification.');
        setStatusType('success');
        if (data.registers) setRegisters(data.registers);
        if (data.summary) setSummary(data.summary);
      } else {
        setStatusMessage(`Failed to save mapping: ${data.error}`);
        setStatusType('warn');
      }
    } catch (err) {
      setStatusMessage(`Error saving mapping: ${err.message}`);
      setStatusType('warn');
    } finally {
      setIsSavingReg(false);
    }
  };

  // --------------------------------------------------------------------------
  // 7. Sub-Tab 2: Query Raw Sensors Telemetry
  // --------------------------------------------------------------------------
  const queryRawSensors = useCallback(async () => {
    if (!selectedPort) return;
    try {
      const res = await fetch(`/api/mapper/raw_sensors?port=${encodeURIComponent(selectedPort)}`);
      if (!res.ok) return;
      const data = await res.json();
      if (!data.error) {
        setRawSensorData(data);
      }
    } catch (err) {
      console.warn('Raw sensors query failed:', err);
    }
  }, [selectedPort]);

  useEffect(() => {
    if (subTab === 'raw_sensors' && isRawPolling) {
      queryRawSensors();
      const interval = setInterval(queryRawSensors, 1200);
      return () => clearInterval(interval);
    }
  }, [subTab, isRawPolling, queryRawSensors]);

  // Populate Sensor Form when selected field changes
  const selectedSensorField = rawSensorData.fields?.find((f) => f.key === selectedFieldKey) || {
    key: selectedFieldKey,
    frame: 'HZ',
    index: 4,
    raw_hex: '03CA',
    raw_dec: 970,
    raw_bin: '0000 0011 1100 1010',
    name: 'Coffee Thermoblock NTC',
    category: 'Thermal',
    unit: '°C',
    scale: 0.1,
    scaled_val: 97.0,
    formatted: '97.0 °C',
    desc: 'Coffee Thermoblock temperature (0.1 °C resolution)',
    notes: 'Thermoblock nominal operating band (90-95°C)'
  };

  useEffect(() => {
    if (selectedSensorField) {
      setSensorMapForm({
        key: selectedSensorField.key,
        name: selectedSensorField.name || '',
        category: selectedSensorField.category || 'General',
        unit: selectedSensorField.unit || '',
        scale: selectedSensorField.scale ?? 1.0,
        desc: selectedSensorField.desc || ''
      });
    }
  }, [selectedFieldKey, rawSensorData]);

  // Save Sensor Mapping
  const handleSaveSensorMapping = async (e) => {
    if (e) e.preventDefault();
    if (!sensorMapForm.name.trim()) return;
    setIsSavingSensorMap(true);

    try {
      const res = await fetch('/api/mapper/map_sensor_field', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(sensorMapForm)
      });
      const data = await res.json();
      if (data.success) {
        setStatusMessage(`Saved sensor mapping for ${sensorMapForm.key}`);
        setStatusType('success');
        queryRawSensors();
      } else {
        setStatusMessage(`Error saving sensor mapping: ${data.error}`);
        setStatusType('warn');
      }
    } catch (err) {
      setStatusMessage(`Error: ${err.message}`);
      setStatusType('warn');
    } finally {
      setIsSavingSensorMap(false);
    }
  };

  const handleResetSensorMappings = async () => {
    if (!window.confirm('Reset all sensor field mappings to firmware defaults?')) return;
    try {
      const res = await fetch('/api/mapper/reset_sensor_mappings', { method: 'POST' });
      const data = await res.json();
      if (data.success) {
        setStatusMessage('Reset sensor mappings to factory defaults.');
        setStatusType('success');
        queryRawSensors();
      }
    } catch (err) {
      console.warn('Reset error:', err);
    }
  };

  // Initial load
  useEffect(() => {
    fetchMapperInfo();
    handleFullSweep();
  }, [selectedPort]);

  // Copy helper
  const handleCopyText = (txt, label) => {
    navigator.clipboard.writeText(txt);
    setCopiedFrame(label);
    setTimeout(() => setCopiedFrame(null), 1200);
  };

  // Filtered registers
  const filteredRegisters = registers.filter((r) => {
    if (filterType === 'mapped' && r.status !== 'mapped') return false;
    if (filterType === 'theoretical' && r.status !== 'theoretical') return false;
    if (filterType === 'unknown' && r.status !== 'unknown') return false;
    if (filterType === 'blank' && r.status !== 'blank') return false;
    if (filterType === 'changed' && !r.is_changed) return false;

    if (searchQuery.trim()) {
      const q = searchQuery.toLowerCase();
      const matchHex = r.hex_addr?.toLowerCase().includes(q);
      const matchName = r.name?.toLowerCase().includes(q);
      const matchDesc = r.desc?.toLowerCase().includes(q);
      const matchCat = r.category?.toLowerCase().includes(q);
      if (!matchHex && !matchName && !matchDesc && !matchCat) return false;
    }
    return true;
  });

  return (
    <div className="space-y-4">
      {/* ==================================================================== */}
      {/* 1. TOP HEADER & SUB-TAB NAVIGATION WITH DEV PRIVILEGE BADGE */}
      {/* ==================================================================== */}
      <div className={`p-3.5 border ${theme.border} ${theme.panelBg} ${theme.clipClass} flex flex-wrap items-center justify-between gap-3 shadow-lg`}>
        <div className="flex items-center space-x-3">
          <div className="flex items-center space-x-2">
            <Cpu className="w-5 h-5 text-[#FCEE09] animate-pulse" />
            <h2 className="text-base font-black tracking-widest text-[#FCEE09] uppercase">
              MEM MAPPER
            </h2>
          </div>
          <span className="text-[10px] px-2 py-0.5 bg-red-950/80 text-red-400 border border-red-500/70 font-mono font-bold tracking-wider rounded">
            ⚡ [DEV ONLY] REVERSE-ENGINEERING TOOL
          </span>
          <span className="text-xs text-zinc-400 font-mono hidden md:inline">
            {mapperInfo?.model_family || 'Jura Logic Board'} (EF: {mapperInfo?.ef_code || '---'}) | {mapperInfo?.max_words || 512} Words | {mapperInfo?.address_width || 4}-Digit Hex
          </span>
        </div>

        {/* Sub-Tab Navigation Toggle */}
        <div className="flex items-center space-x-1.5 bg-black/50 p-1 rounded border border-zinc-800">
          <button
            onClick={() => setSubTab('eeprom')}
            className={`px-3 py-1 text-xs font-mono font-bold transition-all ${
              subTab === 'eeprom'
                ? 'bg-[#FCEE09] text-black shadow-[0_0_10px_rgba(252,238,9,0.5)]'
                : 'text-zinc-400 hover:text-white'
            }`}
          >
            01 // EEPROM REGISTER MATRIX
          </button>
          <button
            onClick={() => setSubTab('raw_sensors')}
            className={`px-3 py-1 text-xs font-mono font-bold transition-all ${
              subTab === 'raw_sensors'
                ? 'bg-[#00F0FF] text-black shadow-[0_0_10px_rgba(0,240,255,0.5)]'
                : 'text-zinc-400 hover:text-white'
            }`}
          >
            02 // RAW SENSOR WIRE TELEMETRY & MAPPER
          </button>
        </div>
      </div>

      {/* Status Alert Notification Banner */}
      {statusMessage && (
        <div
          className={`px-3.5 py-2 text-xs font-mono flex items-center justify-between border ${
            statusType === 'success'
              ? 'bg-emerald-950/60 border-emerald-500/60 text-emerald-300'
              : statusType === 'warn'
              ? 'bg-amber-950/60 border-amber-500/60 text-amber-300'
              : 'bg-zinc-900 border-zinc-700 text-zinc-300'
          }`}
        >
          <div className="flex items-center space-x-2">
            <Info className="w-4 h-4 flex-shrink-0" />
            <span>{statusMessage}</span>
          </div>
          <button onClick={() => setStatusMessage(null)} className="text-zinc-400 hover:text-white ml-2">
            <X className="w-3.5 h-3.5" />
          </button>
        </div>
      )}

      {/* ==================================================================== */}
      {/* SUB-VIEW 1: EEPROM REGISTER MATRIX & LOGIC SCOPE */}
      {/* ==================================================================== */}
      {subTab === 'eeprom' && (
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
                onClick={handleFullSweep}
                disabled={isSweeping}
                className={`flex items-center space-x-1.5 px-3 py-1 font-bold rounded transition-all ${
                  isSweeping
                    ? 'bg-yellow-600/40 text-yellow-300 border border-yellow-500 animate-pulse'
                    : 'bg-[#FCEE09] hover:bg-yellow-400 text-black font-extrabold shadow-[0_0_10px_rgba(252,238,9,0.4)]'
                }`}
              >
                <Zap className="w-3.5 h-3.5" />
                <span>{isSweeping ? 'SWEEPING...' : '⚡ FULL SWEEP'}</span>
              </button>

              <button
                onClick={handleCaptureBaseline}
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

            {/* Right Column: Bitfield Inspector, Mapping Form, Diff Event Log */}
            <div className="lg:col-span-5 space-y-4">
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
                      0x{selectedRegister.high_byte.toString(16).toUpperCase().padStart(2, '0')} ({selectedRegister.high_byte}) / 0x{selectedRegister.low_byte.toString(16).toUpperCase().padStart(2, '0')} ({selectedRegister.low_byte})
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

                <form onSubmit={handleSaveRegisterMapping} className="space-y-2.5 text-xs">
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
            </div>
          </div>
        </div>
      )}

      {/* ==================================================================== */}
      {/* SUB-VIEW 2: RAW SENSOR WIRE TELEMETRY & VALUE MAPPER */}
      {/* ==================================================================== */}
      {subTab === 'raw_sensors' && (
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
                  onClick={queryRawSensors}
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
                    onClick={() => handleCopyText(f.val, f.label)}
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

                <form onSubmit={handleSaveSensorMapping} className="space-y-2.5 text-xs">
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
                      onClick={handleResetSensorMappings}
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
      )}
    </div>
  );
}
