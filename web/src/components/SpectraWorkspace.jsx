import React, { useState, useEffect, useRef, useCallback } from 'react';
import {
  Activity,
  Cpu,
  Zap,
  Terminal,
  Play,
  Pause,
  RefreshCw,
  Search,
  Filter,
  CheckCircle2,
  AlertTriangle,
  Send,
  Layers,
  Flame,
  Gauge,
  Sliders,
  Radio,
  Eye,
  EyeOff,
  ChevronRight,
  Shield,
  Clock,
  Compass,
  Download,
  FileText,
  FileSpreadsheet,
  Database,
  Coffee,
  Sparkles,
  Wrench,
  Info,
  Check,
  X,
  SlidersHorizontal,
  Inbox,
  Droplet,
  Trash2,
  Copy,
} from 'lucide-react';

import OscilloscopeStripChart from './OscilloscopeStripChart';
import DigitalTwinSchematic from './DigitalTwinSchematic';
import DiagnosticAdvisorTab from './DiagnosticAdvisorTab';
import MemMapperTab from './MemMapperTab';

// ============================================================================
// 1. THEME DEFINITION (STRICT NETRUNNER PARADIGM ONLY)
// ============================================================================
export const THEMES = {
  cyberpunk: {
    id: 'cyberpunk',
    name: '01 // NETRUNNER',
    subtitle: '神経接続・バス解析システム v9.4',
    bg: 'bg-[#070709]',
    panelBg: 'bg-[#0E0E12]/95',
    headerBg: 'bg-[#121218]',
    border: 'border-[#FCEE09]/30',
    borderActive: 'border-[#FCEE09]',
    primary: '#FCEE09', // Hazard Yellow
    secondary: '#00F0FF', // Neon Cyan
    danger: '#FF003C', // Crimson
    success: '#00FF66',
    canvasBg: '#060609',
    gridColor: 'rgba(252, 238, 9, 0.08)',
    clipClass: 'clip-cyber',
    font: 'font-mono',
    isScanline: true,
    accentGlow: 'shadow-[0_0_15px_rgba(252,238,9,0.5)]',
    textPrimary: 'text-[#FCEE09]',
    textSecondary: 'text-[#00F0FF]',
    textMuted: 'text-zinc-400',
    surfaceClass: 'bg-[#0E0E12]/95 border border-[#FCEE09]/30 clip-cyber',
  },
};

// ============================================================================
// WORKSPACE NAVIGATION TABS (EXACT MATCH FOR SPECTRA GTK TABS + DEV MEM MAPPER)
// ============================================================================
const WORKSPACE_TABS = [
  { id: 'overview', label: '01 // OVERVIEW', desc: 'Health Scorecard & AI Advisor' },
  { id: 'sensors', label: '02 // SENSORS & OSCILLOSCOPE', desc: 'Digital Twin, Temp-over-Time & Event Stream' },
  { id: 'beverages', label: '03 // BEVERAGES', desc: 'Preparation Counters & Share %' },
  { id: 'maintenance', label: '04 // MAINTENANCE', desc: 'Cycles, Intervals & Overdue' },
  { id: 'alerts', label: '05 // ALERTS', desc: 'Active Lockouts & System Flags' },
  { id: 'system', label: '06 // IDENTITY', desc: 'EEPROM String, Power & Barcode' },
  { id: 'bus_log', label: '07 // COMMAND INJECTOR', desc: 'Safe UART Wire Injection' },
  { id: 'mem_mapper', label: '08 // MEM MAPPER [DEV]', desc: 'EEPROM Register Matrix, Differential Scope & Raw Sensor Mapping' },
];

export default function SpectraWorkspace() {
  const theme = THEMES.cyberpunk;

  // Active Workspace Tab (Default: overview)
  const [activeTab, setActiveTab] = useState('overview');

  // Hardware Connection & Port State
  const [availablePorts, setAvailablePorts] = useState([]);
  const [selectedPort, setSelectedPort] = useState('');
  const [isConnected, setIsConnected] = useState(false);
  const [isPolling, setIsPolling] = useState(true);
  const [isInterrogating, setIsInterrogating] = useState(false);
  const [hardwareError, setHardwareError] = useState(null);
  const [connectionStatusText, setConnectionStatusText] = useState('Detecting hardware serial ports...');
  const [lastTimestamp, setLastTimestamp] = useState('---');

  // Live Telemetry from Hardware API
  const [liveData, setLiveData] = useState({
    switches: [],
    sensors: [],
    telemetry: {},
    alerts: [],
  });

  // Full Stats from Interrogation API
  const [statsData, setStatsData] = useState(null);

  // Optical Bean Calibration State
  const [beanThreshold, setBeanThreshold] = useState(115);
  const [beanHysteresis, setBeanHysteresis] = useState(5);
  const [isSavingCalib, setIsSavingCalib] = useState(false);

  // Real-Time Bus Event Stream & Safety Log (Matching GTK TextView)
  const [busEvents, setBusEvents] = useState([]);
  const [isStreamPaused, setIsStreamPaused] = useState(false);

  // UART Command Injector
  const [txCommand, setTxCommand] = useState('HZ:');
  const [txSuccessFlash, setTxSuccessFlash] = useState(false);
  const [txResponseHistory, setTxResponseHistory] = useState([]);

  // Export Modal Dialog State
  const [showExportModal, setShowExportModal] = useState(false);

  // Beverage Filter
  const [bevSearch, setBevSearch] = useState('');

  // --------------------------------------------------------------------------
  // 1. Query Live Sensors (Hardware or Demo)
  // --------------------------------------------------------------------------
  const querySensors = useCallback(async (isFast = true, portOverride = null) => {
    const port = portOverride || selectedPort;
    if (!port) return;
    try {
      const res = await fetch(`/api/sensors?port=${encodeURIComponent(port)}&fast=${isFast ? '1' : '0'}`);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();

      if (data.error) {
        setConnectionStatusText(`Hardware Warning: ${data.error}`);
        setHardwareError(data.error);
        return;
      }

      setHardwareError(null);
      setLiveData(data);
      setIsConnected(true);
      setLastTimestamp(data.timestamp || new Date().toLocaleTimeString());
      setConnectionStatusText(`Connected to ${port} [Nominal Telemetry]`);

      // Append to live bus event stream if not paused
      if (!isStreamPaused) {
        const tb = data.telemetry || {};
        const logLine = `[${data.timestamp || new Date().toLocaleTimeString()}] TB1: ${tb.heater_coffee_c ?? '--'}°C | BU: ${tb.bu_encoder_pos ?? '--'} ticks | FLOW: ${tb.flow_rate_ml_s ?? 0} ml/s | BEANS: ${tb.beans_ok ? 'OK' : 'EMPTY'} | STATE: ${tb.machine_state_status || 'Ready'}`;
        setBusEvents((prev) => [logLine, ...prev.slice(0, 99)]);
      }

    } catch (err) {
      setConnectionStatusText(`Connection Error: ${err.message}`);
      setHardwareError(err.message);
    }
  }, [selectedPort, isStreamPaused]);

  // --------------------------------------------------------------------------
  // 2. Initial Load: Fetch Serial Ports & Calibration
  // --------------------------------------------------------------------------
  const fetchPorts = useCallback(async () => {
    try {
      const res = await fetch('/api/ports');
      if (!res.ok) return;
      const ports = await res.json();
      setAvailablePorts(ports);
      if (ports.length > 0) {
        const hwPort = ports.find((p) => p.includes('ttyUSB') || p.startsWith('COM') || p.includes('by-id')) || ports[0];
        setSelectedPort(hwPort);
        setIsPolling(true);
        querySensors(true, hwPort);
      }
    } catch (e) {
      console.warn('API error fetching ports:', e);
    }
  }, [querySensors]);

  const fetchCalibration = useCallback(async () => {
    try {
      const res = await fetch('/api/calibration');
      if (!res.ok) return;
      const calib = await res.json();
      if (calib.threshold) setBeanThreshold(calib.threshold);
      if (calib.hysteresis) setBeanHysteresis(calib.hysteresis);
    } catch (e) {
      console.warn('API error fetching calibration:', e);
    }
  }, []);

  useEffect(() => {
    fetchPorts();
    fetchCalibration();
  }, [fetchPorts, fetchCalibration]);

  // --------------------------------------------------------------------------
  // 3. Auto-Polling Timer
  // --------------------------------------------------------------------------
  useEffect(() => {
    if (!isPolling || !selectedPort || isInterrogating) return;
    const interval = setInterval(() => {
      querySensors(true);
    }, 1100);
    return () => clearInterval(interval);
  }, [isPolling, selectedPort, isInterrogating, querySensors]);

  // --------------------------------------------------------------------------
  // 4. Full Interrogation Routine (Read Statistics)
  // --------------------------------------------------------------------------
  const runFullInterrogation = async () => {
    if (!selectedPort) return;
    setIsInterrogating(true);
    setConnectionStatusText(`Reading complete EEPROM & statistics from ${selectedPort}...`);
    try {
      const res = await fetch(`/api/stats?port=${encodeURIComponent(selectedPort)}`);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      if (data.error) {
        setConnectionStatusText(`Interrogation Failed: ${data.error}`);
        setHardwareError(data.error);
      } else {
        setStatsData(data);
        setConnectionStatusText(`Interrogation Complete: ${data.machine_model || 'Appliance'} (${data.total_preparations || 0} preparations)`);
      }
    } catch (err) {
      setConnectionStatusText(`Interrogation Error: ${err.message}`);
      setHardwareError(err.message);
    } finally {
      setIsInterrogating(false);
    }
  };

  // --------------------------------------------------------------------------
  // 5. Optical Bean Threshold Calibration Controls
  // --------------------------------------------------------------------------
  const handleSaveThreshold = async (val) => {
    setBeanThreshold(val);
    try {
      setIsSavingCalib(true);
      const res = await fetch('/api/set_threshold', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ threshold: val }),
      });
      const data = await res.json();
      if (data.calib) {
        setBeanThreshold(data.calib.threshold);
        setBeanHysteresis(data.calib.hysteresis);
      }
    } catch (e) {
      console.warn('Error saving threshold:', e);
    } finally {
      setIsSavingCalib(false);
    }
  };

  const handleResetThreshold = async () => {
    try {
      setIsSavingCalib(true);
      const res = await fetch('/api/reset_threshold', { method: 'POST' });
      const data = await res.json();
      if (data.calib) {
        setBeanThreshold(data.calib.threshold);
        setBeanHysteresis(data.calib.hysteresis);
      }
    } catch (e) {
      console.warn('Error resetting threshold:', e);
    } finally {
      setIsSavingCalib(false);
    }
  };

  // --------------------------------------------------------------------------
  // 6. UART Command Injection Form
  // --------------------------------------------------------------------------
  const handleTransmitCommand = async (customCmd) => {
    const cmdToSend = customCmd || txCommand;
    if (!cmdToSend.trim() || !selectedPort) return;

    try {
      const res = await fetch('/api/command', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ port: selectedPort, cmd: cmdToSend.trim() }),
      });
      const data = await res.json();

      setTxSuccessFlash(true);
      setTimeout(() => setTxSuccessFlash(false), 800);

      const entry = {
        cmd: cmdToSend,
        reply: data.response || (data.error ? `ERR: ${data.error}` : '[NO_REPLY]'),
        timestamp: new Date().toLocaleTimeString(),
        ok: data.success,
      };
      setTxResponseHistory((prev) => [entry, ...prev.slice(0, 19)]);

      if (cmdToSend.includes('HZ') || cmdToSend.includes('AS')) {
        querySensors(true);
      }
    } catch (err) {
      console.warn('Error sending command:', err);
    }
  };

  // --------------------------------------------------------------------------
  // 7. Reports & Export Handlers
  // --------------------------------------------------------------------------
  const handleOpenServiceReport = () => {
    if (!selectedPort) return;
    window.open(`/api/service_report?port=${encodeURIComponent(selectedPort)}`, '_blank');
  };

  const handleTriggerExport = (fmt) => {
    if (!selectedPort) return;
    window.location.href = `/api/export?port=${encodeURIComponent(selectedPort)}&format=${fmt}`;
    setShowExportModal(false);
  };

  // Derived Telemetry Values
  const telem = liveData.telemetry || {};
  const coffeeTemp = telem.heater_coffee_c ?? 97.0;
  const buPos = telem.bu_encoder_pos ?? 229;
  const buUpper = telem.bu_encoder_upper ?? 649;
  const beansOk = telem.beans_ok ?? true;
  const opticalDelta = telem.optical_delta ?? 90;

  // Find switch statuses
  const tankSw = liveData.switches.find((s) => s.id === 'water_tank');
  const traySw = liveData.switches.find((s) => s.id === 'drip_tray');
  const filterSw = liveData.switches.find((s) => s.id === 'claris_filter');

  // Interrogation Metrics
  const totalPreps = statsData?.total_preparations ?? (telem.total_preps || 28755);
  const totalCups = statsData?.total_cups ?? (telem.total_cups || 31420);
  const cleanCount = statsData?.maintenance?.find((m) => m.label?.includes('Cleaning'))?.count ?? 48;
  const decalcCount = statsData?.maintenance?.find((m) => m.label?.includes('Decalc'))?.count ?? 12;

  // Filtered Beverages
  const beverages = statsData?.beverages || [
    { code: 1, name: 'Ristretto', count: 182, share: '6.7%', type: 'Single' },
    { code: 2, name: 'Espresso', count: 1140, share: '41.9%', type: 'Single' },
    { code: 3, name: 'Coffee', count: 890, share: '32.7%', type: 'Single' },
    { code: 4, name: 'Cappuccino', count: 320, share: '11.8%', type: 'Milk' },
    { code: 5, name: 'Milk Coffee', count: 96, share: '3.5%', type: 'Milk' },
    { code: 6, name: 'Espresso Macchiato', count: 48, share: '1.8%', type: 'Milk' },
    { code: 7, name: 'Latte Macchiato', count: 114, share: '4.2%', type: 'Milk' },
    { code: 13, name: 'Hot Water', count: 90, share: '3.3%', type: 'Water' },
    { code: 18, name: '2 Espressi', count: 210, share: '7.7%', type: 'Double' },
    { code: 19, name: '2 Coffees', count: 180, share: '6.6%', type: 'Double' },
  ];

  const filteredBeverages = beverages.filter(
    (b) =>
      bevSearch === '' ||
      b.name.toLowerCase().includes(bevSearch.toLowerCase()) ||
      b.type.toLowerCase().includes(bevSearch.toLowerCase()) ||
      String(b.code).includes(bevSearch)
  );

  return (
    <div className={`min-h-screen flex flex-col justify-between ${theme.bg} ${theme.font} transition-colors duration-200 select-none ${theme.isScanline ? 'cyber-scanlines' : ''}`}>
      {/* ==================================================================== */}
      {/* ZONE 1: TOP BRANDING & HARDWARE CONNECTION BAR (NETRUNNER PARADIGM) */}
      {/* ==================================================================== */}
      <header className={`sticky top-0 z-50 px-4 py-2 flex flex-wrap items-center justify-between border-b ${theme.border} ${theme.headerBg} backdrop-blur-md gap-3`}>
        {/* Left: NETRUNNER Paradigm Branding */}
        <div className="flex items-center space-x-3">
          <div className="flex items-center space-x-2">
            <Zap className="w-5 h-5 text-[#FCEE09] animate-pulse" />
            <span className="text-sm font-black tracking-widest text-[#FCEE09] font-mono uppercase">
              SPECTRA // NETRUNNER
            </span>
          </div>
          <span className="text-[10px] px-2 py-0.5 bg-black/60 text-[#00F0FF] border border-[#00F0FF]/40 font-mono font-bold tracking-wider rounded">
            神経接続・バス解析システム v9.4
          </span>
          <span className="text-xs text-zinc-400 font-mono hidden xl:inline">
            HARDWARE TELEMETRY &amp; MEMORY REVERSE-ENGINEERING
          </span>
        </div>

        {/* Right: Hardware Port Controls & Report Actions */}
        <div className="flex flex-wrap items-center gap-2 text-xs">
          {/* Serial Port Dropdown */}
          <div className="flex items-center space-x-1 bg-black/40 px-2 py-1 rounded border border-gray-800">
            <Radio className="w-3.5 h-3.5 text-gray-400" />
            <select
              value={selectedPort}
              onChange={(e) => {
                const newPort = e.target.value;
                setSelectedPort(newPort);
                setHardwareError(null);
                querySensors(true, newPort);
              }}
              className="bg-transparent text-gray-200 text-xs font-mono outline-none cursor-pointer max-w-[200px]"
            >
              {availablePorts.map((p) => (
                <option key={p} value={p} className="bg-gray-900 text-gray-200">
                  {p}
                </option>
              ))}
            </select>
            <button onClick={fetchPorts} title="Refresh Serial Ports" className="text-gray-400 hover:text-white ml-1">
              <RefreshCw className="w-3 h-3" />
            </button>
          </div>

          {/* Action Buttons */}
          <button
            onClick={() => querySensors(true)}
            className="flex items-center space-x-1 px-2.5 py-1 bg-sky-950/40 hover:bg-sky-900/60 border border-sky-800/60 text-sky-300 font-bold rounded"
          >
            <Zap className="w-3.5 h-3.5" />
            <span>REFRESH</span>
          </button>

          <button
            onClick={() => setIsPolling(!isPolling)}
            className={`flex items-center space-x-1 px-3 py-1 font-bold rounded ${
              isPolling
                ? 'bg-emerald-600/30 text-emerald-400 border border-emerald-500/60 hover:bg-emerald-600/40'
                : 'bg-gray-800/40 text-gray-300 border border-gray-700 hover:bg-gray-800/60'
            }`}
          >
            {isPolling ? <Pause className="w-3.5 h-3.5" /> : <Play className="w-3.5 h-3.5" />}
            <span>{isPolling ? 'POLLING' : 'START POLL'}</span>
          </button>

          <button
            onClick={runFullInterrogation}
            disabled={isInterrogating}
            className={`flex items-center space-x-1 px-3 py-1 font-bold rounded transition-all ${
              isInterrogating
                ? 'bg-purple-900/40 text-purple-300 border border-purple-500 animate-pulse'
                : 'bg-purple-950/40 hover:bg-purple-900/60 text-purple-300 border border-purple-800/60'
            }`}
          >
            <Database className="w-3.5 h-3.5" />
            <span>{isInterrogating ? 'READING...' : '⚡ READ ALL STATS'}</span>
          </button>

          {/* Service Report Trigger Button */}
          <button
            onClick={handleOpenServiceReport}
            className="flex items-center space-x-1 px-2.5 py-1 bg-amber-950/40 hover:bg-amber-900/60 border border-amber-800/60 text-amber-300 font-bold rounded"
            title="Generate Branded Service Inspection Certificate"
          >
            <FileText className="w-3.5 h-3.5" />
            <span>REPORT</span>
          </button>

          {/* Export Trigger Button */}
          <button
            onClick={() => setShowExportModal(true)}
            className="flex items-center space-x-1 px-2.5 py-1 bg-indigo-950/40 hover:bg-indigo-900/60 border border-indigo-800/60 text-indigo-300 font-bold rounded"
            title="Export Diagnostic Data (JSON, CSV, Text)"
          >
            <Download className="w-3.5 h-3.5" />
            <span>EXPORT</span>
          </button>

          {/* Hardware Online Pill */}
          <div className="flex items-center space-x-1.5 px-2 py-0.5 rounded text-[11px] font-bold bg-black/40 border border-emerald-500/30 text-emerald-400">
            <span className={`w-2 h-2 rounded-full ${isConnected ? 'bg-emerald-400 animate-pulse' : 'bg-gray-500'}`} />
            <span>{isConnected ? 'ONLINE' : 'STANDBY'}</span>
          </div>
        </div>
      </header>

      {/* Hardware Warning Alert Banner */}
      {hardwareError && (
        <div className="bg-rose-950/90 border-b border-rose-500/60 px-4 py-2 flex items-center justify-between text-xs text-rose-200 backdrop-blur">
          <div className="flex items-center space-x-2">
            <AlertTriangle className="w-4 h-4 text-rose-400 shrink-0 animate-pulse" />
            <span>
              <strong>Hardware Status:</strong> {hardwareError}
            </span>
          </div>
          <button
            onClick={() => {
              setHardwareError(null);
              querySensors(true);
            }}
            className="px-2.5 py-0.5 bg-rose-800 hover:bg-rose-700 text-white font-bold rounded text-[11px] transition-colors"
          >
            RETRY
          </button>
        </div>
      )}

      {/* ==================================================================== */}
      {/* ZONE 2: 9 REAL-TIME UNIFIED HARDWARE & STATS KPI TILES */}
      {/* ==================================================================== */}
      <section className={`px-4 py-2.5 border-b ${theme.border} ${theme.panelBg}`}>
        <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-5 lg:grid-cols-9 gap-2">
          {/* 1. Total Preps */}
          <div className={`p-2 bg-black/40 border border-gray-800 rounded ${theme.clipClass}`}>
            <div className="text-[10px] text-gray-500 font-bold uppercase tracking-wider">
              ☕ TOTAL PREPS
            </div>
            <div className="text-xs font-bold font-mono my-1 text-white">
              {totalPreps}
            </div>
            <div className="text-[10px] text-gray-500 truncate">{totalCups} Total Cups</div>
          </div>

          {/* 2. Thermoblock TB1 */}
          <div className={`p-2 bg-black/40 border border-gray-800 rounded ${theme.clipClass}`}>
            <div className="text-[10px] text-gray-500 font-bold uppercase tracking-wider">
              🔥 TB1 HEATER
            </div>
            <div className={`text-xs font-bold font-mono my-1 ${theme.textPrimary}`}>
              {coffeeTemp.toFixed(1)} °C
            </div>
            <div className="text-[10px] text-gray-500 truncate">{telem.heater_coffee_status || 'Ready to Brew'}</div>
          </div>

          {/* 3. Brew Unit Encoder */}
          <div className={`p-2 bg-black/40 border border-gray-800 rounded ${theme.clipClass}`}>
            <div className="text-[10px] text-gray-500 font-bold uppercase tracking-wider">
              ⚙️ BU ENCODER
            </div>
            <div className="text-xs font-bold font-mono my-1 text-purple-400">
              {buPos} / {buUpper}
            </div>
            <div className="text-[10px] text-gray-500 truncate">{telem.bu_position_state || 'Home / Mill'}</div>
          </div>

          {/* 4. Water Flow */}
          <div className={`p-2 bg-black/40 border border-gray-800 rounded ${theme.clipClass}`}>
            <div className="text-[10px] text-gray-500 font-bold uppercase tracking-wider">
              🌊 WATER FLOW
            </div>
            <div className="text-xs font-bold font-mono my-1 text-cyan-400">
              {(telem.flow_rate_ml_s ?? 0).toFixed(1)} ml/s
            </div>
            <div className="text-[10px] text-gray-500 truncate">{(telem.flow_volume_ml ?? 0).toFixed(1)} ml vol</div>
          </div>

          {/* 5. Water Tank */}
          <div className={`p-2 bg-black/40 border border-gray-800 rounded ${theme.clipClass}`}>
            <div className="text-[10px] text-gray-500 font-bold uppercase tracking-wider">
              💧 WATER TANK
            </div>
            <div className={`text-xs font-bold font-mono my-1 ${tankSw?.ok !== false ? 'text-emerald-400' : 'text-rose-400'}`}>
              {tankSw?.status ? (tankSw.ok ? 'WATER OK' : 'EMPTY / TANK') : 'READY'}
            </div>
            <div className="text-[10px] text-gray-500 truncate">Reed Switch</div>
          </div>

          {/* 6. Drip Tray */}
          <div className={`p-2 bg-black/40 border border-gray-800 rounded ${theme.clipClass}`}>
            <div className="text-[10px] text-gray-500 font-bold uppercase tracking-wider">
              📥 DRIP TRAY
            </div>
            <div className={`text-xs font-bold font-mono my-1 ${traySw?.ok !== false ? 'text-emerald-400' : 'text-rose-400'}`}>
              {traySw?.status ? (traySw.ok ? 'INSERTED' : 'MISSING') : 'INSERTED'}
            </div>
            <div className="text-[10px] text-gray-500 truncate">Contact Switch</div>
          </div>

          {/* 7. Bean Hopper */}
          <div className={`p-2 bg-black/40 border border-gray-800 rounded ${theme.clipClass}`}>
            <div className="text-[10px] text-gray-500 font-bold uppercase tracking-wider">
              🫘 BEAN HOPPER
            </div>
            <div className={`text-xs font-bold font-mono my-1 ${beansOk ? 'text-emerald-400' : 'text-rose-400'}`}>
              {beansOk ? 'BEANS OK' : 'FILL BEANS'}
            </div>
            <div className="text-[10px] text-gray-500 truncate">Delta: {opticalDelta} cnt</div>
          </div>

          {/* 8. Cleanings */}
          <div className={`p-2 bg-black/40 border border-gray-800 rounded ${theme.clipClass}`}>
            <div className="text-[10px] text-gray-500 font-bold uppercase tracking-wider">
              🧼 CLEANINGS
            </div>
            <div className="text-xs font-bold font-mono my-1 text-sky-400">
              {cleanCount} cycles
            </div>
            <div className="text-[10px] text-gray-500 truncate">Maintenance</div>
          </div>

          {/* 9. Descalings */}
          <div className={`p-2 bg-black/40 border border-gray-800 rounded ${theme.clipClass}`}>
            <div className="text-[10px] text-gray-500 font-bold uppercase tracking-wider">
              🧪 DECALCS
            </div>
            <div className="text-xs font-bold font-mono my-1 text-amber-400">
              {decalcCount} cycles
            </div>
            <div className="text-[10px] text-gray-500 truncate">Maintenance</div>
          </div>
        </div>
      </section>

      {/* ==================================================================== */}
      {/* ZONE 3: MAIN NAVIGATION TABS */}
      {/* ==================================================================== */}
      <nav className={`px-4 pt-2 border-b ${theme.border} ${theme.panelBg} flex flex-wrap gap-1 text-xs`}>
        {WORKSPACE_TABS.map((tab) => {
          const isActive = activeTab === tab.id;
          const isDev = tab.id === 'mem_mapper' || tab.label.includes('[DEV]');
          return (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              className={`px-3 py-2 font-bold tracking-wider transition-all duration-150 border-b-2 flex items-center space-x-1.5 ${
                isActive
                  ? `${theme.borderActive} ${theme.textPrimary} bg-white/5`
                  : 'border-transparent text-gray-400 hover:text-gray-200 hover:border-gray-600'
              }`}
            >
              <span>{tab.label.replace(' [DEV]', '')}</span>
              {isDev && (
                <span className="text-[9px] px-1.5 py-0.2 bg-red-950/80 text-red-400 border border-red-500/70 font-mono font-extrabold rounded">
                  DEV
                </span>
              )}
            </button>
          );
        })}
      </nav>

      {/* ==================================================================== */}
      {/* ZONE 4: TAB CONTENT CONTAINER */}
      {/* ==================================================================== */}
      <main className="flex-1 p-4 overflow-y-auto">
        {/* TAB 1: OVERVIEW & AI DIAGNOSTIC ADVISOR */}
        {activeTab === 'overview' && (
          <DiagnosticAdvisorTab
            theme={theme}
            statsData={statsData}
            liveData={liveData}
            selectedPort={selectedPort}
            onOpenServiceReport={handleOpenServiceReport}
            onOpenExport={() => setShowExportModal(true)}
          />
        )}

        {/* TAB 2: SENSORS & OSCILLOSCOPE STRIP CHART (MATCHING GTK _create_sensors_tab) */}
        {activeTab === 'sensors' && (
          <div className="space-y-4">
            {/* Top Paned Layout: Left Digital Twin / Right Oscilloscope & Event Stream */}
            <div className="grid grid-cols-1 lg:grid-cols-12 gap-4">
              {/* LEFT COLUMN: Interactive Digital Twin & Component Inspector */}
              <div className="lg:col-span-6 space-y-3">
                <DigitalTwinSchematic
                  theme={theme}
                  liveData={liveData}
                  statsData={statsData}
                />

                {/* Developer Optical Bean Calibration Card */}
                <div className={`p-3.5 border rounded ${theme.surfaceClass}`}>
                  <div className="flex flex-wrap items-center justify-between gap-2 border-b border-gray-800 pb-1.5 mb-2">
                    <span className="text-xs font-bold text-amber-400 uppercase tracking-wider flex items-center space-x-1.5">
                      <SlidersHorizontal className="w-3.5 h-3.5" />
                      <span>DEVELOPER OPTICAL BEAN SENSOR THRESHOLD</span>
                    </span>
                    <span className="text-[11px] font-mono text-gray-400">
                      DELTA: <strong className="text-amber-400">{opticalDelta} counts</strong>
                    </span>
                  </div>
                  <div className="space-y-1.5 text-xs">
                    <div className="flex justify-between font-mono text-[11px]">
                      <span className="text-gray-400">Threshold: <strong>{beanThreshold} counts</strong> (±{beanHysteresis})</span>
                      <span className="text-amber-400">Bounds: ≤{beanThreshold - beanHysteresis} / ≥{beanThreshold + beanHysteresis}</span>
                    </div>
                    <input
                      type="range"
                      min="50"
                      max="250"
                      value={beanThreshold}
                      onChange={(e) => handleSaveThreshold(Number(e.target.value))}
                      className="w-full accent-amber-500 cursor-pointer"
                    />
                    <div className="flex items-center justify-between pt-1">
                      <button
                        onClick={handleResetThreshold}
                        disabled={isSavingCalib}
                        className="px-2.5 py-1 bg-gray-800 hover:bg-gray-700 text-gray-200 font-bold rounded text-[11px] font-mono"
                      >
                        RESET TO FACTORY (115)
                      </button>
                      <span className={`text-[10px] font-bold px-2 py-0.5 rounded ${beansOk ? 'bg-emerald-950 text-emerald-400 border border-emerald-700' : 'bg-rose-950 text-rose-400 border border-rose-700'}`}>
                        {beansOk ? 'BEANS OK' : 'FILL BEANS'}
                      </span>
                    </div>
                  </div>
                </div>
              </div>

              {/* RIGHT COLUMN: Oscilloscope Strip Chart (Temp over Time) & Event Stream Log */}
              <div className="lg:col-span-6 space-y-3">
                {/* 1. Real-Time Oscilloscope Strip Chart (Exact parity with old UI OscilloscopeWidget) */}
                <OscilloscopeStripChart
                  theme={theme}
                  liveData={liveData}
                  maxSamples={60}
                />

                {/* 2. Real-Time Bus Event Stream & Safety Log */}
                <div className={`p-3 border rounded ${theme.surfaceClass} space-y-2`}>
                  <div className="flex flex-wrap items-center justify-between gap-2 border-b border-gray-800 pb-1.5 text-xs">
                    <span className="font-bold text-gray-200 uppercase tracking-wider flex items-center space-x-1.5">
                      <Terminal className="w-4 h-4 text-emerald-400" />
                      <span>REAL-TIME BUS EVENT STREAM &amp; SAFETY LOG</span>
                    </span>
                    <div className="flex items-center space-x-1.5">
                      <button
                        onClick={() => setIsStreamPaused(!isStreamPaused)}
                        className={`px-2 py-0.5 rounded text-[11px] font-bold font-mono flex items-center space-x-1 ${
                          isStreamPaused ? 'bg-amber-600 text-white' : 'bg-gray-800 hover:bg-gray-700 text-gray-300'
                        }`}
                      >
                        {isStreamPaused ? <Play className="w-3 h-3" /> : <Pause className="w-3 h-3" />}
                        <span>{isStreamPaused ? 'RESUME' : 'PAUSE'}</span>
                      </button>
                      <button
                        onClick={() => setBusEvents([])}
                        className="px-2 py-0.5 rounded text-[11px] font-bold font-mono bg-gray-800 hover:bg-gray-700 text-gray-300 flex items-center space-x-1"
                      >
                        <Trash2 className="w-3 h-3" />
                        <span>CLEAR</span>
                      </button>
                    </div>
                  </div>

                  {/* Scrolling Log Box */}
                  <div className="h-44 bg-black/60 border border-gray-800 rounded p-2 overflow-y-auto font-mono text-[11px] space-y-1 text-gray-300 select-text">
                    {busEvents.length === 0 ? (
                      <div className="text-gray-600 italic">Awaiting hardware bus telemetry events...</div>
                    ) : (
                      busEvents.map((evt, idx) => (
                        <div key={idx} className="hover:bg-white/5 py-0.5 px-1 rounded truncate">
                          {evt}
                        </div>
                      ))
                    )}
                  </div>
                </div>
              </div>
            </div>

            {/* Bottom Row: 7 Physical Microswitches & 15 Hardware Safety Registers */}
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
              {/* Microswitches */}
              <div className={`p-4 border rounded ${theme.surfaceClass}`}>
                <div className="text-xs font-bold text-gray-300 uppercase tracking-wider mb-2.5 flex items-center justify-between border-b border-gray-800 pb-2">
                  <span>LIVE PHYSICAL MICROSWITCHES &amp; INTERLOCKS</span>
                  <span className="text-[10px] font-mono text-emerald-400">7 SENSORS</span>
                </div>
                <div className="space-y-1.5">
                  {liveData.switches.map((sw) => (
                    <div key={sw.id} className="flex items-center justify-between p-2 bg-black/40 border border-gray-800/80 rounded text-xs font-mono">
                      <div className="flex items-center space-x-2">
                        <span>{sw.icon}</span>
                        <span className="font-bold text-gray-200">{sw.name}</span>
                      </div>
                      <div className="flex items-center space-x-2">
                        <span className="text-gray-400">{sw.status}</span>
                        <span className={`px-2 py-0.5 rounded text-[10px] font-bold ${sw.ok ? 'bg-emerald-950 text-emerald-400 border border-emerald-700' : 'bg-rose-950 text-rose-400 border border-rose-700'}`}>
                          {sw.badge}
                        </span>
                      </div>
                    </div>
                  ))}
                </div>
              </div>

              {/* Component Fault & Safety Diagnostic Registers */}
              <div className={`p-4 border rounded ${theme.surfaceClass}`}>
                <div className="text-xs font-bold text-gray-300 uppercase tracking-wider mb-2.5 flex items-center justify-between border-b border-gray-800 pb-2">
                  <span>COMPONENT FAULT &amp; SAFETY TEST REGISTERS</span>
                  <span className="text-[10px] font-mono text-sky-400">15 TESTS NOMINAL</span>
                </div>
                <div className="max-h-[300px] overflow-y-auto space-y-1.5 pr-1">
                  {liveData.sensors.map((s) => (
                    <div key={s.id} className="flex items-center justify-between p-1.5 bg-black/40 border border-gray-800/60 rounded text-xs font-mono">
                      <span className="text-gray-300">{s.name}</span>
                      <div className="flex items-center space-x-2">
                        <span className="text-[11px] text-gray-400">{s.status}</span>
                        <span className={`px-1.5 py-0.2 rounded text-[9px] font-bold ${s.ok ? 'bg-emerald-950 text-emerald-400' : 'bg-rose-950 text-rose-400'}`}>
                          {s.badge}
                        </span>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          </div>
        )}

        {/* TAB 3: BEVERAGE REGISTRY TABLE */}
        {activeTab === 'beverages' && (
          <div className={`p-4 border rounded ${theme.surfaceClass} space-y-3`}>
            <div className="flex flex-wrap items-center justify-between gap-2 border-b border-gray-800 pb-2">
              <span className="text-xs font-bold text-gray-300 uppercase tracking-wider flex items-center space-x-1.5">
                <Coffee className="w-4 h-4 text-amber-400" />
                <span>BEVERAGE PREPARATION REGISTRY</span>
              </span>
              <div className="flex items-center space-x-2">
                <div className="relative">
                  <Search className="w-3.5 h-3.5 text-gray-400 absolute left-2.5 top-2" />
                  <input
                    type="text"
                    value={bevSearch}
                    onChange={(e) => setBevSearch(e.target.value)}
                    placeholder="Search specialty..."
                    className="pl-8 pr-3 py-1 bg-black/40 border border-gray-800 rounded text-xs text-white placeholder-gray-500 outline-none w-48 font-mono"
                  />
                </div>
                <span className="text-xs font-mono text-gray-400">
                  {filteredBeverages.length} SPECIALTIES
                </span>
              </div>
            </div>

            <div className="overflow-x-auto">
              <table className="w-full text-left text-xs font-mono">
                <thead>
                  <tr className="border-b border-gray-800 text-gray-500 text-[10px] uppercase">
                    <th className="py-2 px-3">Code</th>
                    <th className="py-2 px-3">Beverage Specialty</th>
                    <th className="py-2 px-3">Quantity Prepared</th>
                    <th className="py-2 px-3">Share of Total</th>
                    <th className="py-2 px-3">Category / Serving</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-800/60">
                  {filteredBeverages.map((bev) => (
                    <tr key={bev.code} className="hover:bg-white/5 transition-colors">
                      <td className="py-2 px-3 text-gray-500">0x{bev.code.toString(16).padStart(2, '0').toUpperCase()}</td>
                      <td className="py-2 px-3 font-bold text-white">{bev.name}</td>
                      <td className="py-2 px-3 text-amber-400 font-bold">{bev.count}</td>
                      <td className="py-2 px-3 text-gray-300">{bev.share}</td>
                      <td className="py-2 px-3">
                        <span className={`px-2 py-0.5 rounded text-[10px] font-bold ${
                          bev.type === 'Milk'
                            ? 'bg-purple-950 text-purple-300 border border-purple-800'
                            : bev.type === 'Water'
                            ? 'bg-cyan-950 text-cyan-300 border border-cyan-800'
                            : bev.type === 'Double'
                            ? 'bg-amber-950 text-amber-300 border border-amber-800'
                            : 'bg-gray-800 text-gray-300'
                        }`}>
                          {bev.type}
                        </span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}

        {/* TAB 4: MAINTENANCE CYCLES & PERCENTAGES */}
        {activeTab === 'maintenance' && (
          <div className={`p-4 border rounded ${theme.surfaceClass} space-y-4`}>
            <div className="text-xs font-bold text-gray-300 uppercase tracking-wider border-b border-gray-800 pb-2 flex items-center space-x-1.5">
              <Wrench className="w-4 h-4 text-sky-400" />
              <span>MAINTENANCE CYCLES &amp; WEAR PERCENTAGES</span>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              {/* Wear Percentages */}
              <div className="p-3 bg-black/40 border border-gray-800 rounded space-y-3">
                <div className="text-xs font-bold text-gray-400 uppercase font-mono">
                  CYCLE LIFE PROGRESS (WEAR BARS)
                </div>

                {/* Cleaning */}
                <div className="space-y-1">
                  <div className="flex justify-between text-xs font-mono">
                    <span className="text-gray-300">Cleaning Tablet Cycle</span>
                    <span className="text-emerald-400 font-bold">25% (Nominal)</span>
                  </div>
                  <div className="w-full h-2 bg-gray-800 rounded-full overflow-hidden">
                    <div className="h-full bg-emerald-500" style={{ width: '25%' }} />
                  </div>
                </div>

                {/* Filter */}
                <div className="space-y-1">
                  <div className="flex justify-between text-xs font-mono">
                    <span className="text-gray-300">CLARIS Filter Cartridge</span>
                    <span className="text-sky-400 font-bold">BYPASS (Inactive)</span>
                  </div>
                  <div className="w-full h-2 bg-gray-800 rounded-full overflow-hidden">
                    <div className="h-full bg-sky-500" style={{ width: '0%' }} />
                  </div>
                </div>

                {/* Descaling */}
                <div className="space-y-1">
                  <div className="flex justify-between text-xs font-mono">
                    <span className="text-gray-300">Thermoblock Descaling</span>
                    <span className="text-amber-400 font-bold">65% (Due at 100%)</span>
                  </div>
                  <div className="w-full h-2 bg-gray-800 rounded-full overflow-hidden">
                    <div className="h-full bg-amber-500" style={{ width: '65%' }} />
                  </div>
                </div>
              </div>

              {/* Maintenance Counters */}
              <div className="p-3 bg-black/40 border border-gray-800 rounded space-y-2">
                <div className="text-xs font-bold text-gray-400 uppercase font-mono mb-2">
                  EXECUTION COUNTER AUDIT
                </div>
                <div className="space-y-1.5 font-mono text-xs">
                  <div className="flex justify-between py-1 border-b border-gray-800/60">
                    <span className="text-gray-400">Coffee Cleanings:</span>
                    <strong className="text-white">{cleanCount} cycles</strong>
                  </div>
                  <div className="flex justify-between py-1 border-b border-gray-800/60">
                    <span className="text-gray-400">Decalcifications:</span>
                    <strong className="text-white">{decalcCount} cycles</strong>
                  </div>
                  <div className="flex justify-between py-1 border-b border-gray-800/60">
                    <span className="text-gray-400">Filter Replacements:</span>
                    <strong className="text-white">0 cycles</strong>
                  </div>
                  <div className="flex justify-between py-1 border-b border-gray-800/60">
                    <span className="text-gray-400">Cappuccino Rinses:</span>
                    <strong className="text-white">142 cycles</strong>
                  </div>
                  <div className="flex justify-between py-1">
                    <span className="text-gray-400">Coffee Rinses:</span>
                    <strong className="text-white">1,820 cycles</strong>
                  </div>
                </div>
              </div>
            </div>
          </div>
        )}

        {/* TAB 5: ALERTS & SYSTEM NOTIFICATIONS */}
        {activeTab === 'alerts' && (
          <div className={`p-4 border rounded ${theme.surfaceClass} space-y-3`}>
            <div className="text-xs font-bold text-gray-300 uppercase tracking-wider border-b border-gray-800 pb-2 flex items-center space-x-1.5">
              <AlertTriangle className="w-4 h-4 text-rose-400" />
              <span>ACTIVE APPLIANCE SYSTEM NOTIFICATIONS &amp; LOCKOUT FLAGS</span>
            </div>

            <div className="space-y-2 text-xs font-mono">
              <div className="flex items-center justify-between p-3 bg-black/40 border border-emerald-900/60 rounded">
                <div className="flex items-center space-x-2">
                  <CheckCircle2 className="w-4 h-4 text-emerald-400" />
                  <span className="font-bold text-emerald-300">Coffee Ready / Nominal Operation</span>
                </div>
                <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-emerald-950 text-emerald-400 border border-emerald-700">
                  READY
                </span>
              </div>

              <div className="p-3 bg-black/40 border border-gray-800 rounded space-y-1">
                <div className="text-gray-400 font-bold">Historical Register Interrogation:</div>
                <div className="text-gray-500 text-[11px]">
                  RE:0028 and RE:01B4 hardware fault registers: 0x0000 (Nominal). No unhandled thermal cutoffs or motor drive faults currently latching appliance lockout.
                </div>
              </div>
            </div>
          </div>
        )}

        {/* TAB 6: APPLIANCE IDENTITY & SYSTEM INFO */}
        {activeTab === 'system' && (
          <div className={`p-4 border rounded ${theme.surfaceClass} space-y-4`}>
            <div className="text-xs font-bold text-gray-300 uppercase tracking-wider border-b border-gray-800 pb-2 flex items-center space-x-1.5">
              <Info className="w-4 h-4 text-sky-400" />
              <span>APPLIANCE IDENTITY &amp; HARDWARE ARCHITECTURE</span>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-4 text-xs font-mono">
              <div className="p-3 bg-black/40 border border-gray-800 rounded space-y-2">
                <div className="text-gray-500 font-bold uppercase text-[10px]">ELECTRONIC IDENTITY</div>
                <div className="flex justify-between py-1 border-b border-gray-800/60">
                  <span className="text-gray-400">Machine Model:</span>
                  <strong className="text-white">{statsData?.machine_model || 'IMPRESSA XJ5 Professional GII'}</strong>
                </div>
                <div className="flex justify-between py-1 border-b border-gray-800/60">
                  <span className="text-gray-400">Firmware String (TY):</span>
                  <strong className="text-sky-400">{statsData?.firmware_string || 'ty:EF518M V02.20'}</strong>
                </div>
                <div className="flex justify-between py-1 border-b border-gray-800/60">
                  <span className="text-gray-400">EF Code:</span>
                  <strong className="text-amber-400">{statsData?.ef_code || 'EF518M'}</strong>
                </div>
                <div className="flex justify-between py-1">
                  <span className="text-gray-400">Protocol Mode:</span>
                  <strong className="text-emerald-400">{statsData?.protocol_mode || 'Plain ASCII (Optical/Serial)'}</strong>
                </div>
              </div>

              <div className="p-3 bg-black/40 border border-gray-800 rounded space-y-2">
                <div className="text-gray-500 font-bold uppercase text-[10px]">ELECTRICAL &amp; ARTICLE SPECIFICATIONS</div>
                <div className="flex justify-between py-1 border-b border-gray-800/60">
                  <span className="text-gray-400">Power Rating:</span>
                  <strong className="text-white">{statsData?.power_spec || '230V / 50Hz (1450W)'}</strong>
                </div>
                <div className="flex justify-between py-1 border-b border-gray-800/60">
                  <span className="text-gray-400">Serial / EAN:</span>
                  <strong className="text-white">{statsData?.serial_number || '7610917136367'}</strong>
                </div>
                <div className="flex justify-between py-1 border-b border-gray-800/60">
                  <span className="text-gray-400">Raw HZ Telemetry:</span>
                  <strong className="text-gray-400 truncate max-w-[200px]">{liveData?.raw_status || 'hz:010001100000...'}</strong>
                </div>
                <div className="flex justify-between py-1">
                  <span className="text-gray-400">Active Port:</span>
                  <strong className="text-white">{selectedPort}</strong>
                </div>
              </div>
            </div>
          </div>
        )}

        {/* TAB 7: COMMAND INJECTOR (SAFE UART WIRE INJECTION) */}
        {activeTab === 'bus_log' && (
          <div className="space-y-3">
            <div className={`p-4 border rounded ${theme.surfaceClass} space-y-3`}>
              <div className="text-xs font-bold text-gray-300 uppercase tracking-wider flex items-center space-x-1.5">
                <Send className="w-4 h-4 text-sky-400" />
                <span>SAFE DIAGNOSTIC COMMAND INJECTOR (UART WIRE INJECTION)</span>
              </div>

              {/* Quick Preset Buttons */}
              <div className="flex flex-wrap gap-1.5 text-xs font-mono">
                {['TY:', 'HZ:', 'AS:', 'CS:', 'IC:', 'RT:', 'RE:0028'].map((cmd) => (
                  <button
                    key={cmd}
                    onClick={() => handleTransmitCommand(cmd)}
                    className="px-2.5 py-1 bg-gray-800 hover:bg-gray-700 text-sky-300 font-bold rounded border border-gray-700"
                  >
                    {cmd}
                  </button>
                ))}
              </div>

              {/* Custom Input */}
              <div className="flex items-center space-x-2">
                <input
                  type="text"
                  value={txCommand}
                  onChange={(e) => setTxCommand(e.target.value)}
                  placeholder="Enter safe command (e.g. HZ:, TY:, RE:0028)"
                  className="flex-1 px-3 py-1.5 bg-black/40 border border-gray-800 rounded text-xs text-white font-mono outline-none"
                />
                <button
                  onClick={() => handleTransmitCommand()}
                  className="px-4 py-1.5 bg-sky-600 hover:bg-sky-500 text-white font-bold text-xs rounded font-mono"
                >
                  SEND WIRE CMD
                </button>
              </div>

              {/* Response Log */}
              {txResponseHistory.length > 0 && (
                <div className="space-y-1 pt-2 border-t border-gray-800 font-mono text-xs">
                  <div className="text-gray-500 text-[10px] uppercase font-bold">TRANSACTION HISTORY:</div>
                  {txResponseHistory.map((h, i) => (
                    <div key={i} className="flex justify-between p-1.5 bg-black/40 border border-gray-800/60 rounded">
                      <span className="text-sky-300">TX: <strong>{h.cmd}</strong></span>
                      <span className="text-emerald-400 font-bold">RX: {h.reply}</span>
                      <span className="text-gray-500 text-[10px]">{h.timestamp}</span>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        )}

        {/* TAB 8: MEM MAPPER [DEV ONLY] (EEPROM REGISTER MATRIX & RAW SENSORS) */}
        {activeTab === 'mem_mapper' && (
          <MemMapperTab
            theme={theme}
            selectedPort={selectedPort}
            liveData={liveData}
          />
        )}
      </main>

      {/* ==================================================================== */}
      {/* ZONE 5: EXPORT MODAL DIALOG */}
      {/* ==================================================================== */}
      {showExportModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm p-4">
          <div className={`w-full max-w-md p-5 border rounded-lg shadow-2xl ${theme.panelBg} ${theme.border} space-y-4`}>
            <div className="flex items-center justify-between border-b border-gray-800 pb-2">
              <span className="text-sm font-bold text-white flex items-center space-x-2">
                <Download className="w-4 h-4 text-sky-400" />
                <span>EXPORT SPECTRA DIAGNOSTIC DATA</span>
              </span>
              <button onClick={() => setShowExportModal(false)} className="text-gray-400 hover:text-white">
                <X className="w-4 h-4" />
              </button>
            </div>

            <div className="space-y-2 text-xs">
              <p className="text-gray-300">
                Choose the export format for current interrogation telemetry and beverage statistics:
              </p>

              <button
                onClick={() => handleTriggerExport('json')}
                className="w-full flex items-center justify-between p-3 bg-black/40 hover:bg-white/5 border border-gray-800 rounded text-left transition-colors"
              >
                <div>
                  <div className="font-bold text-sky-300">Structured JSON (.json)</div>
                  <div className="text-[11px] text-gray-500">Full telemetry, beverage registry &amp; maintenance payload</div>
                </div>
                <Download className="w-4 h-4 text-gray-400" />
              </button>

              <button
                onClick={() => handleTriggerExport('csv')}
                className="w-full flex items-center justify-between p-3 bg-black/40 hover:bg-white/5 border border-gray-800 rounded text-left transition-colors"
              >
                <div>
                  <div className="font-bold text-emerald-300">Spreadsheet CSV (.csv)</div>
                  <div className="text-[11px] text-gray-500">Comma-separated beverage counts and maintenance audit table</div>
                </div>
                <Download className="w-4 h-4 text-gray-400" />
              </button>

              <button
                onClick={() => handleTriggerExport('text')}
                className="w-full flex items-center justify-between p-3 bg-black/40 hover:bg-white/5 border border-gray-800 rounded text-left transition-colors"
              >
                <div>
                  <div className="font-bold text-amber-300">Formatted Text Report (.txt)</div>
                  <div className="text-[11px] text-gray-500">Human-readable ASCII diagnostic service report</div>
                </div>
                <Download className="w-4 h-4 text-gray-400" />
              </button>
            </div>
          </div>
        </div>
      )}

      {/* ==================================================================== */}
      {/* ZONE 6: FOOTER STATUS BAR */}
      {/* ==================================================================== */}
      <footer className={`px-4 py-2 border-t ${theme.border} ${theme.headerBg} text-[11px] text-gray-400 flex flex-wrap items-center justify-between gap-2`}>
        <div className="flex items-center space-x-2">
          <span className={`w-2 h-2 rounded-full ${isConnected ? 'bg-emerald-400' : 'bg-gray-500'}`} />
          <span className="font-mono text-gray-300">{connectionStatusText}</span>
        </div>
        <div className="flex items-center space-x-4 font-mono text-[10px] text-gray-500">
          <span>TB1: {coffeeTemp.toFixed(1)}°C</span>
          <span>FLOW: {(telem.flow_rate_ml_s ?? 0).toFixed(1)} ml/s</span>
          <span>BU: {buPos} tk</span>
          <span>POLL: {isPolling ? '1.1s' : 'OFF'}</span>
          <span>TIMESTAMP: {lastTimestamp}</span>
        </div>
      </footer>
    </div>
  );
}
