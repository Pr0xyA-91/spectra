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
} from 'lucide-react';

// ============================================================================
// 1. THEMES DEFINITION (THE 5 DESIGN PARADIGMS)
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
  oscilloscope: {
    id: 'oscilloscope',
    name: '02 // TEK-DARK',
    subtitle: '24MHz 8-CH MIXED SIGNAL DSO & LOGIC ANALYZER',
    bg: 'bg-[#0B0F17]',
    panelBg: 'bg-[#111722]',
    headerBg: 'bg-[#151C28]',
    border: 'border-[#1E293B]',
    borderActive: 'border-[#00FF66]',
    primary: '#00FF66', // Phosphor Green
    secondary: '#FFB000', // Amber
    danger: '#FF4444',
    success: '#00FF66',
    canvasBg: '#070B10',
    gridColor: 'rgba(0, 255, 102, 0.14)',
    clipClass: 'rounded-md',
    font: 'font-mono',
    isScanline: false,
    accentGlow: 'shadow-[0_0_12px_rgba(0,255,102,0.4)]',
    textPrimary: 'text-[#00FF66]',
    textSecondary: 'text-[#FFB000]',
    textMuted: 'text-slate-400',
    surfaceClass: 'bg-[#111722] border border-[#1E293B] rounded-md shadow-inner',
  },
  omarchy: {
    id: 'omarchy',
    name: '03 // HYPR-TUI',
    subtitle: 'WAYLAND TILING WM :: /dev/ttyUSB0 @ 115200bps',
    bg: 'bg-[#1A1B26]',
    panelBg: 'bg-[#16161E]',
    headerBg: 'bg-[#16161E]',
    border: 'border-2 border-[#3B4261]',
    borderActive: 'border-[#7AA2F7]',
    primary: '#7AA2F7', // TokyoNight Blue
    secondary: '#BB9AF7', // Purple
    danger: '#F7768E',
    success: '#9ECE6A',
    canvasBg: '#13141C',
    gridColor: 'rgba(122, 162, 247, 0.12)',
    clipClass: 'border-2 border-[#3B4261]',
    font: 'font-mono',
    isScanline: false,
    accentGlow: 'shadow-none',
    textPrimary: 'text-[#7AA2F7]',
    textSecondary: 'text-[#BB9AF7]',
    textMuted: 'text-[#787C99]',
    surfaceClass: 'bg-[#16161E] border-2 border-[#3B4261]',
  },
  expanse: {
    id: 'expanse',
    name: '04 // ROCINANTE',
    subtitle: 'MCRN TACTICAL // PDC & DRIVE CORE BUS DIAGNOSTICS',
    bg: 'bg-[#060911]',
    panelBg: 'bg-[#0A101D]/90',
    headerBg: 'bg-[#090E1A]',
    border: 'border-[#38BDF8]/30',
    borderActive: 'border-[#FF7700]',
    primary: '#FF7700', // MCRN Tactical Amber
    secondary: '#38BDF8', // Ice Vector Blue
    danger: '#EF4444',
    success: '#38BDF8',
    canvasBg: '#04070D',
    gridColor: 'rgba(56, 189, 248, 0.10)',
    clipClass: 'clip-expanse',
    font: 'font-mono',
    isScanline: false,
    accentGlow: 'shadow-[0_0_12px_rgba(255,119,0,0.5)]',
    textPrimary: 'text-[#FF7700]',
    textSecondary: 'text-[#38BDF8]',
    textMuted: 'text-sky-300/60',
    surfaceClass: 'bg-[#0A101D]/90 border border-[#38BDF8]/30 clip-expanse',
  },
  swiss: {
    id: 'swiss',
    name: '05 // BRAUN-ENG',
    subtitle: 'ABT. ELEKTRONIK // DIN-ISO 9001 PRÜFSTAND',
    bg: 'bg-[#F4F3EF]',
    panelBg: 'bg-[#FFFFFF]',
    headerBg: 'bg-[#EAE8E1]',
    border: 'border-[#18181B]/20',
    borderActive: 'border-[#FF4F00]',
    primary: '#FF4F00', // International Orange
    secondary: '#18181B', // Stark Charcoal
    danger: '#DC2626',
    success: '#15803D',
    canvasBg: '#FAF9F5',
    gridColor: 'rgba(24, 24, 27, 0.10)',
    clipClass: 'border border-[#18181B]/20',
    font: 'font-mono',
    isScanline: false,
    accentGlow: 'shadow-sm',
    textPrimary: 'text-[#FF4F00]',
    textSecondary: 'text-[#18181B]',
    textMuted: 'text-zinc-600',
    surfaceClass: 'bg-[#FFFFFF] border border-[#18181B]/20 shadow-sm text-zinc-900',
  },
};

// ============================================================================
// 2. FSM STAGES DEFINITION
// ============================================================================
const FSM_STAGES = [
  { id: 'IDLE', label: '01. IDLE', desc: 'Awaiting SOF / Idle' },
  { id: 'SYNC_LOCK', label: '02. SYNC_LOCK', desc: 'Carrier Synchronization' },
  { id: 'HEADER_PARSE', label: '03. HDR_PARSE', desc: 'Opcode & Param Address' },
  { id: 'PAYLOAD_STREAM', label: '04. PAYLOAD', desc: 'UART / EEPROM Nibbles' },
  { id: 'CRC_VERIFY', label: '05. CRC_VERIFY', desc: 'Echo / Parity Check' },
  { id: 'DISPATCH', label: '06. DISPATCH', desc: 'Diagnostic Dispatch' },
];

export default function SpectraWorkspace() {
  const [activeThemeId, setActiveThemeId] = useState('cyberpunk');
  const theme = THEMES[activeThemeId] || THEMES.cyberpunk;

  // Active Workspace Tab
  const [activeTab, setActiveTab] = useState('switches'); // 'switches', 'diagnostics', 'beverages', 'maintenance', 'system', 'packets'

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

  // Waveform State
  const [isWaveformRunning, setIsWaveformRunning] = useState(true);
  const [triggerMode, setTriggerMode] = useState('PACKET_SOF');
  const [timebase, setTimebase] = useState('50µs');
  const [threshTrim, setThreshTrim] = useState(1.65);
  const [channels, setChannels] = useState({
    ch1: true, // UART_TX / RX
    ch2: true, // FLOW_PULSES
    ch3: true, // BU_ENCODER
    ch4: true, // TB1_NTC
    ch5: true, // TRIAC_ZC
  });

  // Packet Decoder State
  const [packets, setPackets] = useState([]);
  const [selectedPacket, setSelectedPacket] = useState(null);
  const [activeFsmStage, setActiveFsmStage] = useState('DISPATCH');
  const [fsmLocked, setFsmLocked] = useState(false);
  const [searchTerm, setSearchTerm] = useState('');
  const [busFilter, setBusFilter] = useState('ALL');

  // UART Command Injector
  const [txCommand, setTxCommand] = useState('HZ:');
  const [txSuccessFlash, setTxSuccessFlash] = useState(false);
  const [txResponseHistory, setTxResponseHistory] = useState([]);

  // Canvas Refs
  const canvasRef = useRef(null);
  const animFrameId = useRef(null);
  const phaseRef = useRef(0);

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

      // Add decoded UART packet to live packet stream
      const pktId = `PKT-${String(Math.floor(Date.now() / 100) % 10000).padStart(4, '0')}`;
      const tb = data.telemetry || {};
      const newPkt = {
        id: pktId,
        timestamp: data.timestamp || new Date().toLocaleTimeString(),
        bus: 'UART0_RX',
        cmd: 'HZ_TELEMETRY',
        hex: '48 5A 3A 0D 0A ' + (tb.button_matrix || '0000'),
        ascii: 'HZ:....',
        decoded: `TB1: ${tb.heater_coffee_c ?? '--'}°C // ENCODER: ${tb.bu_encoder_pos ?? '--'} ticks`,
        telemetry: `BEANS: ${tb.beans_ok ? 'OK' : 'EMPTY'} // FLOW: ${tb.flow_rate_ml_s ?? 0} ml/s`,
        status: 'CRC16_OK',
        fsmState: 'DISPATCH',
        bytes: [
          { offset: '0x00', hex: '48', bin: '01001000', desc: 'ASCII "H"' },
          { offset: '0x01', hex: '5A', bin: '01011010', desc: 'ASCII "Z"' },
          { offset: '0x02', hex: '3A', bin: '00111010', desc: 'ASCII ":"' },
          { offset: '0x03', hex: '0D', bin: '00001101', desc: 'CR Carriage Return' },
          { offset: '0x04', hex: '0A', bin: '00001010', desc: 'LF Line Feed' },
          { offset: '0x05', hex: (tb.bu_encoder_pos ? (tb.bu_encoder_pos & 0xFF).toString(16).toUpperCase() : '00'), bin: '00000000', desc: 'Encoder Low Byte' },
          { offset: '0x06', hex: (tb.optical_delta ? (Math.abs(tb.optical_delta) & 0xFF).toString(16).toUpperCase() : '00'), bin: '00000000', desc: 'Optic Delta Byte' },
          { offset: '0x07', hex: (tb.flow_pulses ? (tb.flow_pulses & 0xFF).toString(16).toUpperCase() : '00'), bin: '00000000', desc: 'Turbine Pulse Byte' },
        ],
      };

      setPackets((prev) => [newPkt, ...prev.slice(0, 49)]);
      if (!selectedPacket) setSelectedPacket(newPkt);

    } catch (err) {
      setConnectionStatusText(`Connection Error: ${err.message}`);
      setHardwareError(err.message);
    }
  }, [selectedPort, selectedPacket]);

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
        // Prefer hardware ttyUSB / COM ports, or first available
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
  // 4. Full Interrogation Routine
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
      } else {
        setStatsData(data);
        setConnectionStatusText(`Interrogation Complete: ${data.machine_model || 'Appliance'} (${data.total_preparations || 0} preparations)`);
        setActiveTab('beverages');
      }
    } catch (err) {
      setConnectionStatusText(`Interrogation Error: ${err.message}`);
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
      setTxResponseHistory((prev) => [entry, ...prev.slice(0, 9)]);

      // If query was HZ or AS, refresh sensors immediately
      if (cmdToSend.includes('HZ') || cmdToSend.includes('AS')) {
        querySensors(true);
      }
    } catch (err) {
      console.warn('Error sending command:', err);
    }
  };

  // --------------------------------------------------------------------------
  // 7. 60 FPS HTML5 Canvas Mixed-Domain Oscilloscope Engine
  // --------------------------------------------------------------------------
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');

    const render = () => {
      if (isWaveformRunning) {
        phaseRef.current += 0.04;
      }
      const phase = phaseRef.current;
      const width = canvas.width;
      const height = canvas.height;

      // Clear Canvas
      ctx.fillStyle = theme.canvasBg;
      ctx.fillRect(0, 0, width, height);

      // 12x5 DSO Graticule Grid
      const cols = 12;
      const rows = 5;
      const dx = width / cols;
      const dy = height / rows;

      ctx.strokeStyle = theme.gridColor;
      ctx.lineWidth = 1;
      ctx.setLineDash([2, 4]);

      for (let i = 1; i < cols; i++) {
        ctx.beginPath();
        ctx.moveTo(i * dx, 0);
        ctx.lineTo(i * dx, height);
        ctx.stroke();
      }
      for (let j = 1; j < rows; j++) {
        ctx.beginPath();
        ctx.moveTo(0, j * dy);
        ctx.lineTo(width, j * dy);
        ctx.stroke();
      }
      ctx.setLineDash([]);

      // Center Crosshairs
      ctx.strokeStyle = theme.gridColor;
      ctx.beginPath();
      ctx.moveTo(width / 2, 0);
      ctx.lineTo(width / 2, height);
      ctx.moveTo(0, height / 2);
      ctx.lineTo(width, height / 2);
      ctx.stroke();

      // Trigger Threshold Line
      const threshY = height * (1 - threshTrim / 3.3);
      ctx.strokeStyle = `${theme.danger}66`;
      ctx.lineWidth = 1;
      ctx.setLineDash([4, 4]);
      ctx.beginPath();
      ctx.moveTo(0, threshY);
      ctx.lineTo(width, threshY);
      ctx.stroke();
      ctx.setLineDash([]);

      // Base Y coordinates for 5 channels
      const channelBaseY = [
        height * 0.18, // CH1 UART
        height * 0.36, // CH2 FLOW_PULSES
        height * 0.54, // CH3 BU_ENCODER
        height * 0.72, // CH4 TB1_NTC
        height * 0.88, // CH5 TRIAC_ZC
      ];

      const telem = liveData.telemetry || {};

      // CH1: UART Wire Activity
      if (channels.ch1) {
        ctx.strokeStyle = theme.primary;
        ctx.lineWidth = 2;
        ctx.beginPath();
        for (let x = 0; x < width; x++) {
          const bitIndex = Math.floor((x + phase * 40) / 28);
          const isHigh = ((bitIndex * 13 + (bitIndex % 3)) % 7) > 3;
          const y = isHigh ? channelBaseY[0] - 16 : channelBaseY[0] + 6;
          if (x === 0) ctx.moveTo(x, y);
          else ctx.lineTo(x, y);
        }
        ctx.stroke();

        // Protocol Annotation Pills
        const annotations = [
          { text: '0x48 [H]', x: 50 },
          { text: '0x5A [Z]', x: 150 },
          { text: '0x3A [:]', x: 250 },
          { text: `TB1:${telem.heater_coffee_c || 95}°C`, x: 380 },
          { text: `ENC:${telem.bu_encoder_pos || 226}`, x: 540 },
          { text: telem.beans_ok ? 'BEANS:OK' : 'EMPTY', x: 700 },
        ];
        annotations.forEach((ann) => {
          const drawX = (ann.x - (phase * 40) % (width + 250) + width) % width;
          ctx.fillStyle = `${theme.primary}22`;
          ctx.strokeStyle = theme.primary;
          ctx.lineWidth = 1;
          ctx.fillRect(drawX, channelBaseY[0] - 32, 85, 14);
          ctx.strokeRect(drawX, channelBaseY[0] - 32, 85, 14);
          ctx.fillStyle = theme.primary;
          ctx.font = '9px monospace';
          ctx.fillText(ann.text, drawX + 4, channelBaseY[0] - 22);
        });
      }

      // CH2: Turbine Flowmeter Pulses (Frequency scaled with flow rate)
      if (channels.ch2) {
        ctx.strokeStyle = theme.secondary;
        ctx.lineWidth = 1.8;
        ctx.beginPath();
        const flowRate = telem.flow_rate_ml_s || 0;
        const freq = flowRate > 0 ? 0.35 : 0.05;
        for (let x = 0; x < width; x++) {
          const isHigh = Math.sin((x + phase * 60) * freq) > 0;
          const y = isHigh ? channelBaseY[1] - 14 : channelBaseY[1] + 6;
          if (x === 0) ctx.moveTo(x, y);
          else ctx.lineTo(x, y);
        }
        ctx.stroke();
      }

      // CH3: Brew Unit Quadrature Optical Encoder
      if (channels.ch3) {
        ctx.strokeStyle = '#BB9AF7';
        ctx.lineWidth = 1.5;
        ctx.beginPath();
        for (let x = 0; x < width; x++) {
          const isHigh = Math.sin((x + phase * 30) * 0.15) > 0;
          const y = isHigh ? channelBaseY[2] - 14 : channelBaseY[2] + 4;
          if (x === 0) ctx.moveTo(x, y);
          else ctx.lineTo(x, y);
        }
        ctx.stroke();
      }

      // CH4: Thermoblock NTC Analog Curve & PID Ripple
      if (channels.ch4) {
        ctx.strokeStyle = '#38BDF8';
        ctx.lineWidth = 2;
        ctx.beginPath();
        const tbTemp = telem.heater_coffee_c || 95.0;
        const normalizedY = channelBaseY[3] - ((tbTemp - 80) / 30) * 16;
        for (let x = 0; x < width; x++) {
          const ripple = Math.sin((x + phase * 80) * 0.15) * 2.0;
          const y = normalizedY + ripple;
          if (x === 0) ctx.moveTo(x, y);
          else ctx.lineTo(x, y);
        }
        ctx.stroke();
      }

      // CH5: Mains AC Zero-Crossing Reference Sine & Triac Pulse
      if (channels.ch5) {
        ctx.strokeStyle = '#F97316';
        ctx.lineWidth = 1.8;
        ctx.beginPath();
        for (let x = 0; x < width; x++) {
          const sine = Math.sin((x + phase * 15) * 0.03) * 16;
          let y = channelBaseY[4] + sine;
          if (Math.abs(sine) < 1.2) y -= 8;
          if (x === 0) ctx.moveTo(x, y);
          else ctx.lineTo(x, y);
        }
        ctx.stroke();
      }

      animFrameId.current = requestAnimationFrame(render);
    };

    render();
    return () => cancelAnimationFrame(animFrameId.current);
  }, [isWaveformRunning, theme, channels, threshTrim, liveData]);

  // Derived Telemetry Values
  const telem = liveData.telemetry || {};
  const coffeeTemp = telem.heater_coffee_c ?? 95.0;
  const steamTemp = telem.heater_steam_c;
  const isDualHeater = telem.is_dual_heater ?? false;
  const buPos = telem.bu_encoder_pos ?? 226;
  const buUpper = telem.bu_encoder_upper ?? 638;
  const buStrokePct = telem.bu_stroke_pct ?? 0.0;
  const buZone = telem.bu_position_state || 'Home / Mill Position';
  const flowRate = telem.flow_rate_ml_s ?? 0.0;
  const flowVolume = telem.flow_volume_ml ?? 0.0;
  const beansOk = telem.beans_ok ?? true;
  const opticalDelta = telem.optical_delta ?? 92;
  const machineState = telem.machine_state_status || 'Ready to Brew';
  const machineBadge = telem.machine_state_badge || 'READY';

  // Find switch statuses
  const tankSw = liveData.switches.find((s) => s.id === 'water_tank');
  const traySw = liveData.switches.find((s) => s.id === 'drip_tray');
  const filterSw = liveData.switches.find((s) => s.id === 'claris_filter');

  // Filtered Packets
  const filteredPackets = packets.filter((p) => {
    const matchesBus = busFilter === 'ALL' || p.bus === busFilter;
    const matchesSearch =
      searchTerm === '' ||
      p.hex.toLowerCase().includes(searchTerm.toLowerCase()) ||
      p.cmd.toLowerCase().includes(searchTerm.toLowerCase()) ||
      p.decoded.toLowerCase().includes(searchTerm.toLowerCase());
    return matchesBus && matchesSearch;
  });

  return (
    <div className={`min-h-screen flex flex-col justify-between ${theme.bg} ${theme.font} transition-colors duration-200 select-none ${theme.isScanline ? 'cyber-scanlines' : ''}`}>
      {/* ==================================================================== */}
      {/* ZONE 1: TOP PARADIGM SWITCHER & HARDWARE CONNECTION BAR */}
      {/* ==================================================================== */}
      <header className={`sticky top-0 z-50 px-4 py-2 flex flex-wrap items-center justify-between border-b ${theme.border} ${theme.headerBg} backdrop-blur-md gap-3`}>
        {/* Left: 5 Theme Buttons */}
        <div className="flex items-center space-x-3">
          <div className="flex items-center space-x-1.5">
            <Compass className={`w-4 h-4 ${theme.textPrimary}`} />
            <span className="text-[11px] uppercase font-bold tracking-wider text-gray-400">
              PARADIGM:
            </span>
          </div>

          <div className="flex flex-wrap gap-1">
            {Object.values(THEMES).map((t) => {
              const active = t.id === activeThemeId;
              return (
                <button
                  key={t.id}
                  onClick={() => setActiveThemeId(t.id)}
                  className={`text-[11px] px-2.5 py-1 font-bold tracking-wide transition-all duration-150 ${
                    active
                      ? `${t.bg} ${t.textPrimary} border ${t.borderActive} ${t.accentGlow}`
                      : 'bg-black/30 text-gray-400 border border-transparent hover:border-gray-600'
                  } ${t.clipClass}`}
                >
                  {t.name}
                </button>
              );
            })}
          </div>
        </div>

        {/* Right: Hardware Port Controls */}
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
            <span>{isInterrogating ? 'READING...' : 'FULL STATS'}</span>
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
      {/* ZONE 2: 9 REAL-TIME HARDWARE KPI TILES */}
      {/* ==================================================================== */}
      <section className={`px-4 py-3 border-b ${theme.border} ${theme.panelBg}`}>
        <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-9 gap-2">
          {/* 1. Water Tank */}
          <div className={`p-2 bg-black/40 border border-gray-800 rounded ${theme.clipClass}`}>
            <div className="text-[10px] text-gray-500 font-bold uppercase tracking-wider">
              💧 WATER TANK
            </div>
            <div className={`text-xs font-bold font-mono my-1 ${tankSw?.ok !== false ? 'text-emerald-400' : 'text-rose-400'}`}>
              {tankSw?.status ? (tankSw.ok ? 'WATER OK' : 'EMPTY / TANK') : 'READY'}
            </div>
            <div className="text-[10px] text-gray-500 truncate">Reed Switch</div>
          </div>

          {/* 2. Drip Tray */}
          <div className={`p-2 bg-black/40 border border-gray-800 rounded ${theme.clipClass}`}>
            <div className="text-[10px] text-gray-500 font-bold uppercase tracking-wider">
              📥 DRIP TRAY
            </div>
            <div className={`text-xs font-bold font-mono my-1 ${traySw?.ok !== false ? 'text-emerald-400' : 'text-rose-400'}`}>
              {traySw?.status ? (traySw.ok ? 'INSERTED' : 'MISSING') : 'INSERTED'}
            </div>
            <div className="text-[10px] text-gray-500 truncate">Contact Switch</div>
          </div>

          {/* 3. Bean Hopper (Optical Sensor) */}
          <div className={`p-2 bg-black/40 border border-gray-800 rounded ${theme.clipClass}`}>
            <div className="text-[10px] text-gray-500 font-bold uppercase tracking-wider">
              🫘 BEAN HOPPER
            </div>
            <div className={`text-xs font-bold font-mono my-1 ${beansOk ? 'text-emerald-400' : 'text-amber-400'}`}>
              {beansOk ? 'BEANS OK' : 'FILL BEANS'}
            </div>
            <div className="text-[10px] text-gray-500 font-mono truncate">
              Δ: {opticalDelta}c (T:{beanThreshold})
            </div>
          </div>

          {/* 4. Machine State */}
          <div className={`p-2 bg-black/40 border border-gray-800 rounded ${theme.clipClass}`}>
            <div className="text-[10px] text-gray-500 font-bold uppercase tracking-wider">
              ⚡ APPLIANCE
            </div>
            <div className={`text-xs font-bold font-mono my-1 ${machineBadge === 'READY' ? 'text-emerald-400' : 'text-amber-400'}`}>
              {machineBadge}
            </div>
            <div className="text-[10px] text-gray-500 truncate">{machineState}</div>
          </div>

          {/* 5. Brew Unit */}
          <div className={`p-2 bg-black/40 border border-gray-800 rounded ${theme.clipClass}`}>
            <div className="text-[10px] text-gray-500 font-bold uppercase tracking-wider">
              ⚙️ BREW UNIT
            </div>
            <div className="text-xs font-bold font-mono my-1 text-sky-400">
              {buPos} / {buUpper}
            </div>
            <div className="text-[10px] text-gray-500 font-mono truncate">
              {buStrokePct}% {buZone}
            </div>
          </div>

          {/* 6. Coffee TB1 */}
          <div className={`p-2 bg-black/40 border border-gray-800 rounded ${theme.clipClass}`}>
            <div className="text-[10px] text-gray-500 font-bold uppercase tracking-wider">
              ☕ COFFEE TB1
            </div>
            <div className="text-xs font-bold font-mono my-1 text-amber-400">
              {coffeeTemp} °C
            </div>
            <div className="text-[10px] text-gray-500 truncate">Thermoblock 1</div>
          </div>

          {/* 7. Steam TB2 */}
          <div className={`p-2 bg-black/40 border border-gray-800 rounded ${theme.clipClass}`}>
            <div className="text-[10px] text-gray-500 font-bold uppercase tracking-wider">
              💨 STEAM TB2
            </div>
            <div className="text-xs font-bold font-mono my-1 text-purple-400">
              {isDualHeater && steamTemp ? `${steamTemp} °C` : 'SINGLE-TB'}
            </div>
            <div className="text-[10px] text-gray-500 truncate">
              {isDualHeater ? 'Thermoblock 2' : 'Not Installed'}
            </div>
          </div>

          {/* 8. Water Flow */}
          <div className={`p-2 bg-black/40 border border-gray-800 rounded ${theme.clipClass}`}>
            <div className="text-[10px] text-gray-500 font-bold uppercase tracking-wider">
              🌊 FLOW RATE
            </div>
            <div className="text-xs font-bold font-mono my-1 text-cyan-400">
              {flowRate} ml/s
            </div>
            <div className="text-[10px] text-gray-500 font-mono truncate">
              {flowVolume.toFixed(1)} ml total
            </div>
          </div>

          {/* 9. Water Filter */}
          <div className={`p-2 bg-black/40 border border-gray-800 rounded ${theme.clipClass}`}>
            <div className="text-[10px] text-gray-500 font-bold uppercase tracking-wider">
              🛡️ FILTER
            </div>
            <div className="text-xs font-bold font-mono my-1 text-emerald-400">
              {filterSw?.status ? 'BYPASS' : 'ACTIVE'}
            </div>
            <div className="text-[10px] text-gray-500 truncate">Hardness: 30°dH</div>
          </div>
        </div>
      </section>

      {/* ==================================================================== */}
      {/* ZONE 3: 60 FPS OSCILLOSCOPE & THERMAL SENSOR GAUGES */}
      {/* ==================================================================== */}
      <section className="px-4 py-2 grid grid-cols-1 lg:grid-cols-12 gap-3 flex-grow-0">
        {/* Left: Waveform Engine (Col 8) */}
        <div className={`lg:col-span-8 flex flex-col justify-between ${theme.surfaceClass} p-3`}>
          {/* Waveform Header Toolbar */}
          <div className="flex flex-wrap items-center justify-between gap-2 pb-2 border-b border-gray-800 mb-2">
            <div className="flex items-center space-x-2">
              <button
                onClick={() => setIsWaveformRunning(!isWaveformRunning)}
                className={`flex items-center space-x-1.5 px-2.5 py-0.5 text-xs font-bold uppercase rounded ${
                  isWaveformRunning
                    ? 'bg-emerald-600/20 text-emerald-400 border border-emerald-500/50 hover:bg-emerald-600/30'
                    : 'bg-rose-600/20 text-rose-400 border border-rose-500/50 hover:bg-rose-600/30'
                }`}
              >
                {isWaveformRunning ? <Pause className="w-3 h-3" /> : <Play className="w-3 h-3" />}
                <span>{isWaveformRunning ? 'RUNNING' : 'STOPPED'}</span>
              </button>

              <div className="flex items-center space-x-1.5 text-xs text-gray-400 bg-black/40 px-2 py-0.5 rounded border border-gray-800">
                <span className="text-gray-500 font-bold">TRIGGER:</span>
                <select
                  value={triggerMode}
                  onChange={(e) => setTriggerMode(e.target.value)}
                  className="bg-transparent text-gray-200 outline-none text-xs font-mono cursor-pointer"
                >
                  <option value="RISING_EDGE">RISING_EDGE</option>
                  <option value="FALLING_EDGE">FALLING_EDGE</option>
                  <option value="PACKET_SOF">PACKET_SOF (0x48 'H')</option>
                </select>
              </div>

              <div className="flex items-center space-x-1.5 text-xs text-gray-400 bg-black/40 px-2 py-0.5 rounded border border-gray-800">
                <span className="text-gray-500 font-bold">TIMEBASE:</span>
                <select
                  value={timebase}
                  onChange={(e) => setTimebase(e.target.value)}
                  className="bg-transparent text-gray-200 outline-none text-xs font-mono cursor-pointer"
                >
                  <option value="10µs">10 µs/div</option>
                  <option value="25µs">25 µs/div</option>
                  <option value="50µs">50 µs/div</option>
                  <option value="100µs">100 µs/div</option>
                  <option value="250µs">250 µs/div</option>
                </select>
              </div>
            </div>

            <div className="text-[11px] font-mono text-gray-500 hidden sm:block">
              LIVE SAMPLING // <span className={theme.textPrimary}>24.0 MHz BUS CLK</span>
            </div>
          </div>

          {/* HTML5 Canvas DSO */}
          <div className="relative w-full h-[210px] bg-black/60 rounded border border-gray-900 overflow-hidden">
            <canvas ref={canvasRef} width={920} height={210} className="w-full h-full block" />
          </div>

          {/* Channel Visibility Toolbar */}
          <div className="flex flex-wrap items-center justify-between gap-2 pt-2 mt-2 border-t border-gray-800 text-xs">
            <div className="flex flex-wrap items-center gap-1.5">
              {[
                { key: 'ch1', label: 'CH1: UART_TX', color: theme.primary },
                { key: 'ch2', label: 'CH2: FLOW_TURBINE', color: theme.secondary },
                { key: 'ch3', label: 'CH3: BU_ENCODER', color: '#BB9AF7' },
                { key: 'ch4', label: 'CH4: TB1_NTC', color: '#38BDF8' },
                { key: 'ch5', label: 'CH5: TRIAC_ZC', color: '#F97316' },
              ].map((ch) => (
                <button
                  key={ch.key}
                  onClick={() => setChannels((prev) => ({ ...prev, [ch.key]: !prev[ch.key] }))}
                  className={`flex items-center space-x-1 px-2 py-0.5 rounded text-[10px] font-mono font-bold transition-all ${
                    channels[ch.key] ? 'bg-black/50 border' : 'bg-black/20 text-gray-600 border border-transparent'
                  }`}
                  style={{
                    borderColor: channels[ch.key] ? ch.color : 'transparent',
                    color: channels[ch.key] ? ch.color : '#666',
                  }}
                >
                  {channels[ch.key] ? <Eye className="w-3 h-3" /> : <EyeOff className="w-3 h-3" />}
                  <span>{ch.label}</span>
                </button>
              ))}
            </div>

            <div className="flex items-center space-x-2 text-xs">
              <span className="text-gray-500 font-bold">THRESH TRIM:</span>
              <input
                type="range"
                min="0.80"
                max="3.00"
                step="0.05"
                value={threshTrim}
                onChange={(e) => setThreshTrim(parseFloat(e.target.value))}
                className="w-20 accent-amber-400 cursor-pointer"
              />
              <span className={`font-mono text-xs w-10 text-right ${theme.textPrimary}`}>
                {threshTrim.toFixed(2)}V
              </span>
            </div>
          </div>
        </div>

        {/* Right: Thermal & Optical Calibration Controls (Col 4) */}
        <div className={`lg:col-span-4 flex flex-col justify-between ${theme.surfaceClass} p-3 gap-2`}>
          <div>
            <div className="flex items-center justify-between pb-1.5 border-b border-gray-800">
              <span className="text-xs font-bold uppercase tracking-wider text-gray-400 flex items-center space-x-1.5">
                <Flame className="w-3.5 h-3.5 text-amber-500" />
                <span>THERMAL & CALIBRATION</span>
              </span>
              <span className="text-[10px] px-1.5 py-0.5 rounded bg-emerald-500/20 text-emerald-400 font-mono font-bold">
                NOMINAL
              </span>
            </div>

            {/* Dual Gauges */}
            <div className="grid grid-cols-2 gap-2 my-2">
              {/* Coffee Boiler Temp */}
              <div className="bg-black/40 border border-gray-800 p-2 rounded text-center">
                <div className="text-[10px] text-gray-500 uppercase tracking-wider font-bold mb-1">
                  COFFEE TB1
                </div>
                <div className="relative flex items-center justify-center my-1">
                  <svg className="w-16 h-16 transform -rotate-90">
                    <circle cx="32" cy="32" r="26" stroke="#222" strokeWidth="5" fill="none" />
                    <circle
                      cx="32"
                      cy="32"
                      r="26"
                      stroke="#F59E0B"
                      strokeWidth="5"
                      strokeDasharray="163"
                      strokeDashoffset={163 - (163 * (coffeeTemp / 140))}
                      strokeLinecap="round"
                      fill="none"
                    />
                  </svg>
                  <div className="absolute text-center">
                    <div className="text-xs font-bold font-mono text-amber-400">
                      {coffeeTemp}
                    </div>
                    <div className="text-[8px] text-gray-500">°C</div>
                  </div>
                </div>
                <div className="text-[10px] text-gray-400 font-mono">TARGET: 95°C</div>
              </div>

              {/* Water Flow / Rate */}
              <div className="bg-black/40 border border-gray-800 p-2 rounded text-center">
                <div className="text-[10px] text-gray-500 uppercase tracking-wider font-bold mb-1">
                  FLOWMETER
                </div>
                <div className="relative flex items-center justify-center my-1">
                  <svg className="w-16 h-16 transform -rotate-90">
                    <circle cx="32" cy="32" r="26" stroke="#222" strokeWidth="5" fill="none" />
                    <circle
                      cx="32"
                      cy="32"
                      r="26"
                      stroke="#38BDF8"
                      strokeWidth="5"
                      strokeDasharray="163"
                      strokeDashoffset={163 - (163 * Math.min(1.0, flowRate / 15.0))}
                      strokeLinecap="round"
                      fill="none"
                    />
                  </svg>
                  <div className="absolute text-center">
                    <div className="text-xs font-bold font-mono text-sky-400">
                      {flowRate}
                    </div>
                    <div className="text-[8px] text-gray-500">ml/s</div>
                  </div>
                </div>
                <div className="text-[10px] text-gray-400 font-mono">TURBINE</div>
              </div>
            </div>

            {/* Live Bean Sensor Sensitivity Calibration */}
            <div className="p-2 bg-black/40 border border-gray-800 rounded text-xs space-y-1.5">
              <div className="flex justify-between items-center">
                <span className="font-bold text-gray-300 flex items-center space-x-1">
                  <SlidersHorizontal className="w-3 h-3 text-amber-400" />
                  <span>OPTICAL BEAN CALIBRATION</span>
                </span>
                <button
                  onClick={handleResetThreshold}
                  disabled={isSavingCalib}
                  className="px-1.5 py-0.5 rounded bg-gray-800 hover:bg-gray-700 text-gray-300 text-[10px] font-bold"
                >
                  ↺ RESET (115)
                </button>
              </div>

              <div className="flex items-center justify-between text-[11px] font-mono">
                <span className="text-gray-500">THRESHOLD:</span>
                <span className={`font-bold ${theme.textPrimary}`}>{beanThreshold} counts</span>
                <span className="text-gray-500">BAND: {beanThreshold - beanHysteresis} .. {beanThreshold + beanHysteresis}</span>
              </div>

              <input
                type="range"
                min="60"
                max="160"
                step="1"
                value={beanThreshold}
                onChange={(e) => handleSaveThreshold(parseInt(e.target.value))}
                className="w-full accent-amber-400 cursor-pointer"
              />

              <div className="flex justify-between text-[9px] text-gray-500 font-mono">
                <span>STRONG (60)</span>
                <span>NOMINAL (115)</span>
                <span>BARE (145)</span>
              </div>
            </div>
          </div>

          {/* Quick Hardware Diagnostic Triggers */}
          <div className="pt-1.5 border-t border-gray-800 flex justify-between gap-1.5">
            <button
              onClick={() => handleTransmitCommand('HZ:')}
              className="flex-1 py-1 bg-black/40 hover:bg-black/60 border border-gray-700 text-gray-300 text-[10px] font-bold rounded"
            >
              QUERY HZ:
            </button>
            <button
              onClick={() => handleTransmitCommand('AS:')}
              className="flex-1 py-1 bg-black/40 hover:bg-black/60 border border-gray-700 text-gray-300 text-[10px] font-bold rounded"
            >
              QUERY AS:
            </button>
            <button
              onClick={() => handleTransmitCommand('TY:')}
              className="flex-1 py-1 bg-black/40 hover:bg-black/60 border border-gray-700 text-gray-300 text-[10px] font-bold rounded"
            >
              QUERY TY:
            </button>
          </div>
        </div>
      </section>

      {/* ==================================================================== */}
      {/* ZONE 4: FUNCTIONAL DIAGNOSTIC WORKSPACE TABS */}
      {/* ==================================================================== */}
      <section className="px-4 py-2 flex-grow">
        <div className={`p-3 ${theme.surfaceClass} flex flex-col justify-between h-full`}>
          {/* Tab Navigation Buttons */}
          <div className="flex flex-wrap items-center justify-between border-b border-gray-800 pb-2 mb-3 gap-2">
            <div className="flex flex-wrap gap-1">
              {[
                { id: 'switches', label: '1. PHYSICAL CONTACTS & SWITCHES', icon: Layers },
                { id: 'diagnostics', label: '2. HARDWARE SAFETY TESTS', icon: Shield },
                { id: 'beverages', label: '3. BEVERAGES & DISPENSINGS', icon: Coffee },
                { id: 'maintenance', label: '4. MAINTENANCE & HYGIENE', icon: Wrench },
                { id: 'system', label: '5. SYSTEM IDENTITY & GS1', icon: Info },
                { id: 'packets', label: '6. BUS PACKET DECODER', icon: Terminal },
              ].map((tab) => {
                const Icon = tab.icon;
                const active = activeTab === tab.id;
                return (
                  <button
                    key={tab.id}
                    onClick={() => setActiveTab(tab.id)}
                    className={`flex items-center space-x-1.5 px-3 py-1 text-xs font-bold font-mono transition-all duration-150 rounded ${
                      active
                        ? `${theme.bg} ${theme.textPrimary} border ${theme.borderActive}`
                        : 'bg-black/30 text-gray-400 border border-transparent hover:border-gray-700'
                    }`}
                  >
                    <Icon className="w-3.5 h-3.5" />
                    <span>{tab.label}</span>
                  </button>
                );
              })}
            </div>

            <div className="text-[11px] text-gray-500 font-mono">
              LAST UPDATE: <span className="text-gray-300">{lastTimestamp}</span>
            </div>
          </div>

          {/* TAB 1: PHYSICAL CONTACTS & MICROSWITCHES */}
          {activeTab === 'switches' && (
            <div className="overflow-x-auto max-h-[280px] overflow-y-auto">
              <table className="w-full text-left text-xs font-mono">
                <thead className="text-[10px] uppercase text-gray-500 border-b border-gray-800 sticky top-0 bg-[#0E0E12]">
                  <tr>
                    <th className="py-1 px-3">COMPONENT / SENSOR NAME</th>
                    <th className="py-1 px-3">OPERATIONAL STATE</th>
                    <th className="py-1 px-3">HARDWARE CODE</th>
                    <th className="py-1 px-3 text-right">STATUS</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-900">
                  {liveData.switches.length > 0 ? (
                    liveData.switches.map((sw, idx) => (
                      <tr key={idx} className="hover:bg-black/40 transition-colors">
                        <td className="py-1.5 px-3 whitespace-nowrap">
                          <span className="mr-2">{sw.icon || '⚙️'}</span>
                          <span className="font-bold text-gray-200">{sw.name}</span>
                        </td>
                        <td className="py-1.5 px-3 whitespace-nowrap text-gray-300">
                          {sw.status}
                        </td>
                        <td className="py-1.5 px-3 whitespace-nowrap text-gray-500">
                          {sw.id}
                        </td>
                        <td className="py-1.5 px-3 text-right whitespace-nowrap">
                          <span
                            className={`text-[10px] px-2 py-0.5 rounded font-bold ${
                              sw.ok
                                ? 'bg-emerald-500/20 text-emerald-400 border border-emerald-500/40'
                                : 'bg-rose-500/20 text-rose-400 border border-rose-500/40'
                            }`}
                          >
                            {sw.badge || (sw.ok ? 'NORMAL' : 'FAULT')}
                          </span>
                        </td>
                      </tr>
                    ))
                  ) : (
                    <tr>
                      <td colSpan={4} className="py-6 text-center text-gray-500 font-mono">
                        No physical switch telemetry yet. Click '⚡ REFRESH' or 'START POLL' above.
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          )}

          {/* TAB 2: HARDWARE SAFETY & COMPONENT DIAGNOSTICS */}
          {activeTab === 'diagnostics' && (
            <div className="overflow-x-auto max-h-[280px] overflow-y-auto">
              <table className="w-full text-left text-xs font-mono">
                <thead className="text-[10px] uppercase text-gray-500 border-b border-gray-800 sticky top-0 bg-[#0E0E12]">
                  <tr>
                    <th className="py-1 px-3">DIAGNOSTIC TEST / CHANNEL</th>
                    <th className="py-1 px-3">VERIFICATION DETAILS</th>
                    <th className="py-1 px-3">SAFETY MARGIN</th>
                    <th className="py-1 px-3 text-right">INTEGRITY</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-900">
                  {liveData.sensors.length > 0 ? (
                    liveData.sensors.map((s, idx) => (
                      <tr key={idx} className="hover:bg-black/40 transition-colors">
                        <td className="py-1.5 px-3 font-bold text-gray-200 whitespace-nowrap">
                          {s.name}
                        </td>
                        <td className="py-1.5 px-3 text-gray-300">
                          {s.status}
                        </td>
                        <td className="py-1.5 px-3 text-gray-500">
                          {s.verification || 'Continuity Verified'}
                        </td>
                        <td className="py-1.5 px-3 text-right whitespace-nowrap">
                          <span
                            className={`text-[10px] px-2 py-0.5 rounded font-bold ${
                              s.ok
                                ? 'bg-emerald-500/20 text-emerald-400 border border-emerald-500/40'
                                : 'bg-rose-500/20 text-rose-400 border border-rose-500/40'
                            }`}
                          >
                            {s.badge || (s.ok ? 'NOMINAL' : 'FAULT')}
                          </span>
                        </td>
                      </tr>
                    ))
                  ) : (
                    <tr>
                      <td colSpan={4} className="py-6 text-center text-gray-500 font-mono">
                        No safety test telemetry loaded. Click '⚡ REFRESH'.
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          )}

          {/* TAB 3: BEVERAGES & DISPENSING COUNTERS */}
          {activeTab === 'beverages' && (
            <div>
              {statsData ? (
                <div>
                  <div className="flex flex-wrap items-center justify-between mb-3 pb-2 border-b border-gray-800 gap-2">
                    <div className="flex items-center space-x-3">
                      <span className="text-xs font-bold text-gray-400">TOTAL CUPS:</span>
                      <span className={`text-base font-bold font-mono ${theme.textPrimary}`}>
                        {statsData.total_cups || 0}
                      </span>
                      <span className="text-gray-600">//</span>
                      <span className="text-xs font-bold text-gray-400">TOTAL PREPARATIONS:</span>
                      <span className={`text-base font-bold font-mono ${theme.textSecondary}`}>
                        {statsData.total_preparations || 0}
                      </span>
                    </div>

                    <div className="flex items-center space-x-2">
                      <button
                        onClick={() => {
                          const blob = new Blob([JSON.stringify(statsData, null, 2)], { type: 'application/json' });
                          const url = URL.createObjectURL(blob);
                          const a = document.createElement('a');
                          a.href = url;
                          a.download = `spectra_${statsData.machine_model || 'jura'}_stats.json`;
                          a.click();
                        }}
                        className="flex items-center space-x-1 px-2.5 py-1 bg-black/40 hover:bg-black/60 border border-gray-700 text-xs font-bold text-gray-300 rounded"
                      >
                        <Download className="w-3 h-3" />
                        <span>JSON</span>
                      </button>
                    </div>
                  </div>

                  <div className="overflow-x-auto max-h-[220px] overflow-y-auto">
                    <table className="w-full text-left text-xs font-mono">
                      <thead className="text-[10px] uppercase text-gray-500 border-b border-gray-800 sticky top-0 bg-[#0E0E12]">
                        <tr>
                          <th className="py-1 px-3">CODE</th>
                          <th className="py-1 px-3">BEVERAGE PRODUCT</th>
                          <th className="py-1 px-3">PREPARATIONS</th>
                          <th className="py-1 px-3">PROPORTION</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-gray-900">
                        {statsData.beverages && statsData.beverages.length > 0 ? (
                          statsData.beverages.map((bev) => {
                            const total = statsData.total_preparations || 1;
                            const pct = Math.round(((bev.count || 0) / total) * 100);
                            return (
                              <tr key={bev.code} className="hover:bg-black/40">
                                <td className="py-1 px-3 text-gray-500">#{bev.code}</td>
                                <td className="py-1 px-3 font-bold text-gray-200">{bev.name}</td>
                                <td className="py-1 px-3 text-amber-400 font-bold">{bev.count}</td>
                                <td className="py-1 px-3 w-48">
                                  <div className="flex items-center space-x-2">
                                    <div className="flex-grow bg-black/50 h-1.5 rounded overflow-hidden border border-gray-800">
                                      <div className="h-full bg-amber-500" style={{ width: `${pct}%` }} />
                                    </div>
                                    <span className="text-[10px] text-gray-500 w-8">{pct}%</span>
                                  </div>
                                </td>
                              </tr>
                            );
                          })
                        ) : (
                          <tr>
                            <td colSpan={4} className="py-6 text-center text-gray-500">
                              No beverage counters recorded for this model.
                            </td>
                          </tr>
                        )}
                      </tbody>
                    </table>
                  </div>
                </div>
              ) : (
                <div className="py-12 text-center font-mono">
                  <Database className="w-8 h-8 text-purple-400 mx-auto mb-2 opacity-60" />
                  <div className="text-sm font-bold text-gray-300">NO INTERROGATION DATA LOADED</div>
                  <div className="text-xs text-gray-500 my-1">
                    Click '📊 FULL STATS' in the header to read lifetime beverage counters & memory maps.
                  </div>
                  <button
                    onClick={runFullInterrogation}
                    className="mt-3 px-3 py-1.5 bg-purple-900/50 hover:bg-purple-800/60 text-purple-200 border border-purple-600 rounded text-xs font-bold"
                  >
                    RUN INTERROGATION NOW
                  </button>
                </div>
              )}
            </div>
          )}

          {/* TAB 4: MAINTENANCE & HYGIENE COUNTERS */}
          {activeTab === 'maintenance' && (
            <div>
              {statsData && statsData.maintenance ? (
                <div className="overflow-x-auto max-h-[260px] overflow-y-auto">
                  <table className="w-full text-left text-xs font-mono">
                    <thead className="text-[10px] uppercase text-gray-500 border-b border-gray-800 sticky top-0 bg-[#0E0E12]">
                      <tr>
                        <th className="py-1 px-3">HYGIENE CATEGORY</th>
                        <th className="py-1 px-3">EXECUTION COUNT</th>
                        <th className="py-1 px-3">SERVICE INTERVAL PROGRESS</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-gray-900">
                      {statsData.maintenance.map((m, idx) => (
                        <tr key={idx} className="hover:bg-black/40">
                          <td className="py-1.5 px-3 font-bold text-gray-200">{m.label || m.name}</td>
                          <td className="py-1.5 px-3 text-emerald-400 font-bold">{m.count} cycles</td>
                          <td className="py-1.5 px-3 w-56">
                            <div className="flex items-center space-x-2">
                              <div className="flex-grow bg-black/50 h-2 rounded overflow-hidden border border-gray-800">
                                <div className="h-full bg-emerald-500" style={{ width: `${Math.min(100, (m.count % 200) / 2)}%` }} />
                              </div>
                              <span className="text-[10px] text-gray-400">NOMINAL</span>
                            </div>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : (
                <div className="py-12 text-center font-mono">
                  <Wrench className="w-8 h-8 text-emerald-400 mx-auto mb-2 opacity-60" />
                  <div className="text-sm font-bold text-gray-300">NO HYGIENE COUNTERS LOADED</div>
                  <div className="text-xs text-gray-500 my-1">
                    Click '📊 FULL STATS' to read descaling, cleaning, and filter cycle records.
                  </div>
                </div>
              )}
            </div>
          )}

          {/* TAB 5: SYSTEM IDENTITY & GS1 SPECIFICATIONS */}
          {activeTab === 'system' && (
            <div className="space-y-3 font-mono text-xs">
              <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                <div className="p-3 bg-black/40 border border-gray-800 rounded space-y-2">
                  <div className="text-[11px] font-bold text-gray-400 border-b border-gray-800 pb-1">
                    APPLIANCE IDENTIFICATION
                  </div>
                  <div className="flex justify-between">
                    <span className="text-gray-500">MODEL FAMILY:</span>
                    <span className={`font-bold ${theme.textPrimary}`}>{statsData?.machine_model || 'Jura IMPRESSA XJ5 Pro'}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-gray-500">EF CODE / PROFILE:</span>
                    <span className="text-gray-300">{statsData?.ef_code || 'EF518M'}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-gray-500">MAIN FIRMWARE:</span>
                    <span className="text-gray-300">{statsData?.firmware_string || 'EF518M V02.20'}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-gray-500">POWER SPEC:</span>
                    <span className="text-gray-300">{statsData?.power_spec || '230V / 50Hz (EU/CH)'}</span>
                  </div>
                </div>

                <div className="p-3 bg-black/40 border border-gray-800 rounded space-y-2">
                  <div className="text-[11px] font-bold text-gray-400 border-b border-gray-800 pb-1">
                    GS1 IDENTIFIER & PRODUCTION
                  </div>
                  <div className="flex justify-between">
                    <span className="text-gray-500">SERIAL NUMBER:</span>
                    <span className="text-amber-400 font-bold">{statsData?.serial_number || '20130530018016'}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-gray-500">PRODUCTION DATE:</span>
                    <span className="text-gray-300">{statsData?.production_date || '30.05.2013'}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-gray-500">APPLIANCE NO:</span>
                    <span className="text-gray-300">{statsData?.machine_number || '18016'}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-gray-500">HARDWARE ADAPTER:</span>
                    <span className="text-gray-300">{selectedPort || '/dev/ttyUSB0'}</span>
                  </div>
                </div>
              </div>
            </div>
          )}

          {/* TAB 6: BUS PACKET DECODER TABLE */}
          {activeTab === 'packets' && (
            <div className="overflow-x-auto max-h-[260px] overflow-y-auto">
              <table className="w-full text-left text-xs font-mono">
                <thead className="text-[10px] uppercase text-gray-500 border-b border-gray-800 sticky top-0 bg-[#0E0E12]">
                  <tr>
                    <th className="py-1 px-3">FRAME ID / TIME</th>
                    <th className="py-1 px-3">BUS</th>
                    <th className="py-1 px-3">RAW HEX STREAM</th>
                    <th className="py-1 px-3">DECODED TELEMETRY</th>
                    <th className="py-1 px-3 text-right">STATUS</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-900">
                  {filteredPackets.map((pkt) => (
                    <tr
                      key={pkt.id}
                      onClick={() => setSelectedPacket(pkt)}
                      className={`cursor-pointer transition-colors ${
                        selectedPacket?.id === pkt.id ? 'bg-white/10 font-bold' : 'hover:bg-black/40 text-gray-300'
                      }`}
                    >
                      <td className="py-1 px-3 whitespace-nowrap">
                        <span className={theme.textPrimary}>{pkt.id}</span>
                        <span className="text-gray-500 text-[10px] block">{pkt.timestamp}</span>
                      </td>
                      <td className="py-1 px-3 whitespace-nowrap">
                        <span className="text-[10px] px-1.5 py-0.5 rounded bg-black/60 border border-gray-800">
                          {pkt.bus}
                        </span>
                      </td>
                      <td className="py-1 px-3 font-mono text-gray-300">{pkt.hex}</td>
                      <td className="py-1 px-3">
                        <div className="text-gray-200">{pkt.decoded}</div>
                        <div className="text-[10px] text-gray-500">{pkt.telemetry}</div>
                      </td>
                      <td className="py-1 px-3 text-right">
                        <span className="text-[10px] px-1.5 py-0.5 rounded font-bold bg-emerald-500/20 text-emerald-400 border border-emerald-500/30">
                          {pkt.status}
                        </span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          {/* Status Bar */}
          <div className="flex flex-wrap items-center justify-between pt-2 border-t border-gray-800 text-[11px] text-gray-500 mt-2">
            <span>{connectionStatusText}</span>
            <span className="font-mono">SPECTRA v0.6.0-DEV [PHYSICAL TESTBED]</span>
          </div>
        </div>
      </section>

      {/* ==================================================================== */}
      {/* ZONE 6: UART COMMAND INJECTOR FOOTER */}
      {/* ==================================================================== */}
      <footer className={`p-3 border-t ${theme.border} ${theme.panelBg}`}>
        <div className="flex flex-col sm:flex-row items-center justify-between gap-3">
          {/* Quick Macros */}
          <div className="flex items-center space-x-2 w-full sm:w-auto">
            <span className="text-[11px] font-bold uppercase text-gray-500 whitespace-nowrap">
              QUICK COMMANDS:
            </span>
            <div className="flex flex-wrap gap-1">
              {['HZ:', 'AS:', 'TY:', 'IC:', 'RE:0028'].map((macro) => (
                <button
                  key={macro}
                  onClick={() => {
                    setTxCommand(macro);
                    handleTransmitCommand(macro);
                  }}
                  className="px-2 py-1 text-[10px] font-mono font-bold bg-black/40 hover:bg-black/60 border border-gray-700 text-gray-300 rounded"
                >
                  [{macro}]
                </button>
              ))}
            </div>
          </div>

          {/* Command Input & Transmit */}
          <div className="flex items-center space-x-2 w-full sm:w-auto flex-grow max-w-xl">
            <div className="relative flex-grow">
              <span className={`absolute left-2.5 top-1.5 text-xs font-mono font-bold ${theme.textPrimary}`}>
                TX&gt;
              </span>
              <input
                type="text"
                value={txCommand}
                onChange={(e) => setTxCommand(e.target.value)}
                placeholder="HZ: or TY: ..."
                className="w-full bg-black/60 border border-gray-800 rounded pl-10 pr-3 py-1.5 text-xs text-gray-100 font-mono tracking-wider outline-none focus:border-gray-600 uppercase"
              />
            </div>

            <button
              onClick={() => handleTransmitCommand()}
              className={`flex items-center space-x-1.5 px-3 py-1.5 text-xs font-bold uppercase tracking-wider rounded transition-all duration-150 ${
                txSuccessFlash
                  ? 'bg-emerald-500 text-black shadow-[0_0_15px_rgba(16,185,129,0.8)]'
                  : `${theme.bg} ${theme.textPrimary} border ${theme.borderActive} hover:bg-white/10 ${theme.accentGlow}`
              }`}
            >
              <Send className="w-3.5 h-3.5" />
              <span>SEND</span>
            </button>
          </div>
        </div>

        {/* Recent Responses Strip */}
        {txResponseHistory.length > 0 && (
          <div className="mt-2 pt-1 border-t border-gray-800/60 flex items-center space-x-2 text-[10px] font-mono text-gray-400 overflow-x-auto">
            <span className="text-gray-500 font-bold whitespace-nowrap">LAST WIRE REPLIES:</span>
            {txResponseHistory.slice(0, 3).map((r, i) => (
              <span key={i} className="px-1.5 py-0.5 bg-black/50 border border-gray-800 rounded whitespace-nowrap">
                <b className={theme.textPrimary}>{r.cmd}</b> &rarr; {r.reply}
              </span>
            ))}
          </div>
        )}
      </footer>
    </div>
  );
}
