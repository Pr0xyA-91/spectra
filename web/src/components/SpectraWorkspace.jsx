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
  { id: 'IDLE', label: '01. IDLE', desc: 'Awaiting SOF' },
  { id: 'SYNC_LOCK', label: '02. SYNC_LOCK', desc: 'Preamble Match' },
  { id: 'HEADER_PARSE', label: '03. HDR_PARSE', desc: 'Opcode & Len' },
  { id: 'PAYLOAD_STREAM', label: '04. PAYLOAD', desc: 'DMA Stream' },
  { id: 'CRC_VERIFY', label: '05. CRC_VERIFY', desc: 'Polynomial 0x1021' },
  { id: 'DISPATCH', label: '06. DISPATCH', desc: 'Bus Execution' },
];

// ============================================================================
// 3. INITIAL MOCK TELEMETRY PACKETS
// ============================================================================
const INITIAL_PACKETS = [
  {
    id: 'PKT-0892',
    timestamp: '00:14.208450',
    bus: 'UART0_RX',
    cmd: 'NTC_BOILER_TEMP',
    hex: 'AA 55 14 04 03 A6 91 C0',
    ascii: '.U.....',
    decoded: 'NTC_BOILER_TEMP: 93.4°C',
    telemetry: 'PID_ERR: +0.2°C // SSR_DUTY: 64%',
    status: 'CRC16_OK',
    fsmState: 'DISPATCH',
    bytes: [
      { offset: '0x00', hex: 'AA', bin: '10101010', desc: 'SOF Preamble Byte 0' },
      { offset: '0x01', hex: '55', bin: '01010101', desc: 'SOF Preamble Byte 1' },
      { offset: '0x02', hex: '14', bin: '00010100', desc: 'Opcode: 0x14 (Read NTC)' },
      { offset: '0x03', hex: '04', bin: '00000100', desc: 'Payload Length: 4 bytes' },
      { offset: '0x04', hex: '03', bin: '00000011', desc: 'ADC High: 0x03' },
      { offset: '0x05', hex: 'A6', bin: '10100110', desc: 'ADC Low: 0xA6 (934 counts)' },
      { offset: '0x06', hex: '91', bin: '10010001', desc: 'CRC16-CCITT High' },
      { offset: '0x07', hex: 'C0', bin: '11000000', desc: 'CRC16-CCITT Low' },
    ],
  },
  {
    id: 'PKT-0893',
    timestamp: '00:14.225100',
    bus: 'I2C_SDA',
    cmd: 'OPTICAL_BEAN_ADC',
    hex: 'AA 55 22 04 06 18 06 7D',
    ascii: '.U."...}',
    decoded: 'BEAN_OPTIC: Delta +101 counts',
    telemetry: 'CHARGED (Thresh: 115 ± 5) // OK',
    status: 'CRC16_OK',
    fsmState: 'DISPATCH',
    bytes: [
      { offset: '0x00', hex: 'AA', bin: '10101010', desc: 'SOF Preamble Byte 0' },
      { offset: '0x01', hex: '55', bin: '01010101', desc: 'SOF Preamble Byte 1' },
      { offset: '0x02', hex: '22', bin: '00100010', desc: 'Opcode: 0x22 (Optic ADC)' },
      { offset: '0x03', hex: '04', bin: '00000100', desc: 'Payload Length: 4 bytes' },
      { offset: '0x04', hex: '06', bin: '00000110', desc: 'Ambient ADC High: 0x06' },
      { offset: '0x05', hex: '18', bin: '00011000', desc: 'Ambient ADC Low: 0x18 (1560)' },
      { offset: '0x06', hex: '06', bin: '00000110', desc: 'Pulsed ADC High: 0x06' },
      { offset: '0x07', hex: '7D', bin: '01111101', desc: 'Pulsed ADC Low: 0x7D (1661)' },
    ],
  },
  {
    id: 'PKT-0894',
    timestamp: '00:14.241850',
    bus: 'UART0_RX',
    cmd: 'BREW_ENCODER_POS',
    hex: 'AA 55 31 04 00 E2 02 7E',
    ascii: '.U.1...~',
    decoded: 'ENCODER: 226 / 638 ticks',
    telemetry: 'HOME / MILL POS // Stroke 0%',
    status: 'CRC16_OK',
    fsmState: 'DISPATCH',
    bytes: [
      { offset: '0x00', hex: 'AA', bin: '10101010', desc: 'SOF Preamble Byte 0' },
      { offset: '0x01', hex: '55', bin: '01010101', desc: 'SOF Preamble Byte 1' },
      { offset: '0x02', hex: '31', bin: '00110001', desc: 'Opcode: 0x31 (Encoder Pos)' },
      { offset: '0x03', hex: '04', bin: '00000100', desc: 'Payload Length: 4 bytes' },
      { offset: '0x04', hex: '00', bin: '00000000', desc: 'Current Pos High: 0x00' },
      { offset: '0x05', hex: 'E2', bin: '11100010', desc: 'Current Pos Low: 0xE2 (226)' },
      { offset: '0x06', hex: '02', bin: '00000010', desc: 'Upper Ref High: 0x02' },
      { offset: '0x07', hex: '7E', bin: '01111110', desc: 'Upper Ref Low: 0x7E (638)' },
    ],
  },
  {
    id: 'PKT-0895',
    timestamp: '00:14.258900',
    bus: 'SPI_MOSI',
    cmd: 'MICROSWITCH_HZ',
    hex: 'AA 55 40 04 01 00 00 1F',
    ascii: '.U.@....',
    decoded: 'SWITCHES: Tank OK, Tray OK',
    telemetry: 'BU_INIT: 1 // MACHINE_READY',
    status: 'CRC16_OK',
    fsmState: 'DISPATCH',
    bytes: [
      { offset: '0x00', hex: 'AA', bin: '10101010', desc: 'SOF Preamble Byte 0' },
      { offset: '0x01', hex: '55', bin: '01010101', desc: 'SOF Preamble Byte 1' },
      { offset: '0x02', hex: '40', bin: '01000000', desc: 'Opcode: 0x40 (Live Switches)' },
      { offset: '0x03', hex: '04', bin: '00000100', desc: 'Payload Length: 4 bytes' },
      { offset: '0x04', hex: '01', bin: '00000001', desc: 'HZ[0]: Tank Reed Present' },
      { offset: '0x05', hex: '00', bin: '00000000', desc: 'HZ[1]: Grinder Triac Off' },
      { offset: '0x06', hex: '00', bin: '00000000', desc: 'HZ[2]: Drip Tray Inserted' },
      { offset: '0x07', hex: '1F', bin: '00011111', desc: 'Status Flags: Nominal Ready' },
    ],
  },
  {
    id: 'PKT-0896',
    timestamp: '00:14.281300',
    bus: 'UART0_RX',
    cmd: 'EEPROM_WORD_SYNC',
    hex: 'AA 55 52 04 00 28 FF 00',
    ascii: '.U.R.(..',
    decoded: 'EEPROM: RE:0028 -> 0xFF00',
    telemetry: 'SERVICE_FLAG: HISTORICAL_OK',
    status: 'CRC16_OK',
    fsmState: 'DISPATCH',
    bytes: [
      { offset: '0x00', hex: 'AA', bin: '10101010', desc: 'SOF Preamble Byte 0' },
      { offset: '0x01', hex: '55', bin: '01010101', desc: 'SOF Preamble Byte 1' },
      { offset: '0x02', hex: '52', bin: '01010010', desc: 'Opcode: 0x52 (EEPROM Read)' },
      { offset: '0x03', hex: '04', bin: '00000100', desc: 'Payload Length: 4 bytes' },
      { offset: '0x04', hex: '00', bin: '00000000', desc: 'Addr High: 0x00' },
      { offset: '0x05', hex: '28', bin: '00101000', desc: 'Addr Low: 0x28 (Fault Reg)' },
      { offset: '0x06', hex: 'FF', bin: '11111111', desc: 'Data Word High: 0xFF' },
      { offset: '0x07', hex: '00', bin: '00000000', desc: 'Data Word Low: 0x00' },
    ],
  },
];

// ============================================================================
// 4. MAIN SPECTRA WORKSPACE COMPONENT
// ============================================================================
export default function SpectraWorkspace() {
  const [activeThemeId, setActiveThemeId] = useState('cyberpunk');
  const theme = THEMES[activeThemeId] || THEMES.cyberpunk;

  // Waveform State
  const [isRunning, setIsRunning] = useState(true);
  const [triggerMode, setTriggerMode] = useState('PACKET_SOF');
  const [timebase, setTimebase] = useState('50µs');
  const [threshTrim, setThreshTrim] = useState(1.65);
  const [channels, setChannels] = useState({
    ch1: true, // UART_TX
    ch2: true, // I2C_SDA
    ch3: true, // SPI_CLK
    ch4: true, // LDO_3V3
    ch5: true, // TRIAC_ZC
  });

  // FSM and Packet State
  const [packets, setPackets] = useState(INITIAL_PACKETS);
  const [selectedPacket, setSelectedPacket] = useState(INITIAL_PACKETS[0]);
  const [activeFsmStage, setActiveFsmStage] = useState('DISPATCH');
  const [fsmLocked, setFsmLocked] = useState(false);

  // Table Filters
  const [searchTerm, setSearchTerm] = useState('');
  const [busFilter, setBusFilter] = useState('ALL');

  // Telemetry Gauge States
  const [boilerTemp, setBoilerTemp] = useState(94.2);
  const [railVoltage, setRailVoltage] = useState(3.315);
  const [railRipple, setRailRipple] = useState(12.4);
  const [ringBufferPct, setRingBufferPct] = useState(48);
  const [ssrDuty, setSsrDuty] = useState(62);

  // Command Injector
  const [txCommand, setTxCommand] = useState('AA 55 14 00 00 00 E1 4B');
  const [txSuccessFlash, setTxSuccessFlash] = useState(false);

  // Canvas Ref
  const canvasRef = useRef(null);
  const animFrameId = useRef(null);
  const phaseRef = useRef(0);

  // --------------------------------------------------------------------------
  // Waveform Canvas Rendering Engine (60 FPS)
  // --------------------------------------------------------------------------
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');

    const render = () => {
      if (isRunning) {
        phaseRef.current += 0.04;
      }
      const phase = phaseRef.current;
      const width = canvas.width;
      const height = canvas.height;

      // Clear Canvas
      ctx.fillStyle = theme.canvasBg;
      ctx.fillRect(0, 0, width, height);

      // Draw 12x5 DSO Graticule Grid
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

      // Draw Channels
      const channelBaseY = [
        height * 0.18, // CH1 UART
        height * 0.36, // CH2 I2C
        height * 0.54, // CH3 SPI
        height * 0.72, // CH4 3.3V
        height * 0.88, // CH5 TRIAC
      ];

      // CH1: UART_TX (Digital Squarewave with Protocol Packets)
      if (channels.ch1) {
        ctx.strokeStyle = theme.primary;
        ctx.lineWidth = 2;
        ctx.beginPath();
        for (let x = 0; x < width; x++) {
          const bitIndex = Math.floor((x + phase * 40) / 28);
          // Pseudo-random but deterministic square wave pattern
          const isHigh = ((bitIndex * 13 + (bitIndex % 3)) % 7) > 3;
          const y = isHigh ? channelBaseY[0] - 18 : channelBaseY[0] + 6;
          if (x === 0) ctx.moveTo(x, y);
          else ctx.lineTo(x, y);
        }
        ctx.stroke();

        // Protocol Annotations (Pills)
        const annotations = [
          { text: '0xAA [SOF]', x: 40 },
          { text: '0x55 [SYNC]', x: 140 },
          { text: 'CMD:0x14', x: 260 },
          { text: 'DATA:0x03A6', x: 420 },
          { text: 'CRC16:OK', x: 580 },
        ];
        annotations.forEach((ann) => {
          const drawX = (ann.x - (phase * 40) % (width + 200) + width) % width;
          ctx.fillStyle = `${theme.primary}22`;
          ctx.strokeStyle = theme.primary;
          ctx.lineWidth = 1;
          ctx.fillRect(drawX, channelBaseY[0] - 34, 85, 14);
          ctx.strokeRect(drawX, channelBaseY[0] - 34, 85, 14);
          ctx.fillStyle = theme.primary;
          ctx.font = '9px monospace';
          ctx.fillText(ann.text, drawX + 4, channelBaseY[0] - 23);
        });
      }

      // CH2: I2C_SDA (Open drain transitions with clock stretching)
      if (channels.ch2) {
        ctx.strokeStyle = theme.secondary;
        ctx.lineWidth = 1.8;
        ctx.beginPath();
        for (let x = 0; x < width; x++) {
          const bit = Math.floor((x + phase * 25) / 20);
          const isHigh = ((bit * 7) % 5) > 1;
          const y = isHigh ? channelBaseY[1] - 16 : channelBaseY[1] + 6;
          if (x === 0) ctx.moveTo(x, y);
          else ctx.lineTo(x, y);
        }
        ctx.stroke();
      }

      // CH3: SPI_CLK (High-frequency clock bursts)
      if (channels.ch3) {
        ctx.strokeStyle = '#BB9AF7';
        ctx.lineWidth = 1.5;
        ctx.beginPath();
        for (let x = 0; x < width; x++) {
          const burstCycle = (x + phase * 60) % 200;
          let y = channelBaseY[2] + 4;
          if (burstCycle < 140) {
            // Active clock burst
            const clkState = Math.sin((x + phase * 60) * 0.4) > 0;
            y = clkState ? channelBaseY[2] - 14 : channelBaseY[2] + 4;
          }
          if (x === 0) ctx.moveTo(x, y);
          else ctx.lineTo(x, y);
        }
        ctx.stroke();
      }

      // CH4: LDO_3V3 (Analog voltage rail with subtle ripple)
      if (channels.ch4) {
        ctx.strokeStyle = '#38BDF8';
        ctx.lineWidth = 2;
        ctx.beginPath();
        for (let x = 0; x < width; x++) {
          const ripple = Math.sin((x + phase * 80) * 0.15) * 2.5 + Math.cos(x * 0.05) * 1.0;
          const y = channelBaseY[3] + ripple;
          if (x === 0) ctx.moveTo(x, y);
          else ctx.lineTo(x, y);
        }
        ctx.stroke();
      }

      // CH5: TRIAC_ZC (Sinusoidal AC zero-cross + Triac gate pulse)
      if (channels.ch5) {
        ctx.strokeStyle = '#F97316';
        ctx.lineWidth = 1.8;
        ctx.beginPath();
        for (let x = 0; x < width; x++) {
          const sine = Math.sin((x + phase * 15) * 0.03) * 16;
          let y = channelBaseY[4] + sine;
          // Pulse on zero crossing
          if (Math.abs(sine) < 1.2) {
            y -= 8;
          }
          if (x === 0) ctx.moveTo(x, y);
          else ctx.lineTo(x, y);
        }
        ctx.stroke();
      }

      animFrameId.current = requestAnimationFrame(render);
    };

    render();
    return () => cancelAnimationFrame(animFrameId.current);
  }, [isRunning, theme, channels, threshTrim]);

  // --------------------------------------------------------------------------
  // Live Telemetry Auto-Step / FSM Simulation
  // --------------------------------------------------------------------------
  useEffect(() => {
    if (!isRunning || fsmLocked) return;
    const interval = setInterval(() => {
      // Step through FSM stages during live capture
      setActiveFsmStage((prev) => {
        const idx = FSM_STAGES.findIndex((s) => s.id === prev);
        const nextIdx = (idx + 1) % FSM_STAGES.length;
        return FSM_STAGES[nextIdx].id;
      });

      // Subtle dynamic analog variations
      setBoilerTemp((t) => Number((93.0 + Math.sin(Date.now() / 3000) * 1.5).toFixed(1)));
      setRailVoltage((v) => Number((3.315 + (Math.random() - 0.5) * 0.006).toFixed(3)));
      setRailRipple((r) => Number((12.0 + Math.random() * 1.5).toFixed(1)));
      setRingBufferPct((p) => Math.min(95, Math.max(30, p + (Math.random() > 0.5 ? 2 : -2))));
    }, 1200);

    return () => clearInterval(interval);
  }, [isRunning, fsmLocked]);

  // --------------------------------------------------------------------------
  // User Actions & Command Transmission
  // --------------------------------------------------------------------------
  const handleSelectPacket = (pkt) => {
    setSelectedPacket(pkt);
    setActiveFsmStage(pkt.fsmState || 'DISPATCH');
    setFsmLocked(true);
  };

  const handleTransmitCommand = (cmdStr) => {
    const raw = cmdStr || txCommand;
    if (!raw.trim()) return;

    const newId = `PKT-0${900 + packets.length}`;
    const timestamp = `00:${(14.3 + packets.length * 0.02).toFixed(6)}`;
    const hexBytes = raw.trim().split(/\s+/);

    const byteBreakdown = hexBytes.slice(0, 8).map((b, idx) => ({
      offset: `0x0${idx}`,
      hex: b.toUpperCase(),
      bin: parseInt(b, 16).toString(2).padStart(8, '0'),
      desc: idx === 0 ? 'SOF Preamble' : idx === 1 ? 'SYNC Preamble' : idx === 2 ? 'Injected Opcode' : `Data Byte ${idx}`,
    }));

    // Pad to 8 bytes if shorter
    while (byteBreakdown.length < 8) {
      const idx = byteBreakdown.length;
      byteBreakdown.push({
        offset: `0x0${idx}`,
        hex: '00',
        bin: '00000000',
        desc: `Pad Byte ${idx}`,
      });
    }

    const newPkt = {
      id: newId,
      timestamp,
      bus: 'UART0_TX',
      cmd: raw.includes('14') ? 'POLL_BOILER_NTC' : raw.includes('FF') ? 'CRC_INJECT_ERR' : 'SYNC_PING',
      hex: raw.toUpperCase(),
      ascii: '.U.TX...',
      decoded: raw.includes('FF') ? 'MANUAL_CRC_FAULT_INJECT' : 'INJECTED_CMD_TX_ACK',
      telemetry: 'TRANSMITTED VIA CP2102 // ACK: 0x06',
      status: raw.includes('FF') ? 'ERR_FRAME_DESYNC' : 'CRC16_OK',
      fsmState: 'DISPATCH',
      bytes: byteBreakdown,
    };

    setPackets((prev) => [newPkt, ...prev]);
    setSelectedPacket(newPkt);
    setTxSuccessFlash(true);
    setTimeout(() => setTxSuccessFlash(false), 800);
  };

  // Filtered Packets List
  const filteredPackets = packets.filter((p) => {
    const matchesBus = busFilter === 'ALL' || p.bus === busFilter;
    const matchesSearch =
      searchTerm === '' ||
      p.hex.toLowerCase().includes(searchTerm.toLowerCase()) ||
      p.cmd.toLowerCase().includes(searchTerm.toLowerCase()) ||
      p.decoded.toLowerCase().includes(searchTerm.toLowerCase()) ||
      p.status.toLowerCase().includes(searchTerm.toLowerCase());
    return matchesBus && matchesSearch;
  });

  return (
    <div className={`min-h-screen flex flex-col justify-between ${theme.bg} ${theme.font} transition-colors duration-200 select-none ${theme.isScanline ? 'cyber-scanlines' : ''}`}>
      {/* ==================================================================== */}
      {/* ZONE 1: TOP PARADIGM SWITCHER BAR (Sticky) */}
      {/* ==================================================================== */}
      <header className={`sticky top-0 z-50 px-4 py-2 flex items-center justify-between border-b ${theme.border} ${theme.headerBg} backdrop-blur-md`}>
        <div className="flex items-center space-x-3">
          <div className="flex items-center space-x-2">
            <Compass className={`w-4 h-4 ${theme.textPrimary}`} />
            <span className="text-xs uppercase font-bold tracking-wider text-gray-400">
              PARADIGM MATRIX:
            </span>
          </div>

          <div className="flex flex-wrap gap-1.5">
            {Object.values(THEMES).map((t) => {
              const active = t.id === activeThemeId;
              return (
                <button
                  key={t.id}
                  onClick={() => setActiveThemeId(t.id)}
                  className={`text-xs px-2.5 py-1 font-bold tracking-wide transition-all duration-150 ${
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

        {/* Live Status Indicator */}
        <div className="flex items-center space-x-3">
          <div className="flex items-center space-x-1.5 px-2 py-0.5 rounded text-[11px] font-bold bg-black/40 border border-emerald-500/30 text-emerald-400">
            <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse"></span>
            <span>HARDWARE ONLINE</span>
          </div>
          <span className="text-[11px] text-gray-500 hidden md:inline">
            EF518M V02.20 [XJ5 PRO]
          </span>
        </div>
      </header>

      {/* ==================================================================== */}
      {/* ZONE 2: MASTER HARDWARE TELEMETRY HEADER */}
      {/* ==================================================================== */}
      <section className={`px-4 py-3 border-b ${theme.border} ${theme.panelBg} flex flex-col lg:flex-row lg:items-center justify-between gap-4`}>
        {/* Logo and Titles */}
        <div className="flex items-center space-x-3">
          <div className={`p-2 rounded ${theme.clipClass} border ${theme.borderActive} bg-black/40`}>
            {/* Hexagonal Shield + Dispersion Logo */}
            <svg className="w-8 h-8" viewBox="0 0 100 100" fill="none">
              <polygon points="50,5 90,25 90,75 50,95 10,75 10,25" stroke={theme.primary} strokeWidth="6" fill={`${theme.primary}15`} />
              <polygon points="50,22 75,36 75,64 50,78 25,64 25,36" stroke={theme.secondary} strokeWidth="4" fill="none" />
              <line x1="10" y1="50" x2="90" y2="50" stroke={theme.primary} strokeWidth="2" strokeDasharray="4 2" />
              <line x1="50" y1="5" x2="50" y2="95" stroke={theme.secondary} strokeWidth="2" strokeDasharray="4 2" />
            </svg>
          </div>
          <div>
            <div className="flex items-center space-x-2">
              <h1 className={`text-lg font-extrabold tracking-wider ${theme.textPrimary}`}>
                SPECTRA
              </h1>
              <span className="text-xs px-1.5 py-0.5 rounded bg-black/40 text-gray-400 border border-gray-700">
                v0.6.0-DEV
              </span>
            </div>
            <p className="text-xs text-gray-400 tracking-wide">
              {theme.subtitle}
            </p>
          </div>
        </div>

        {/* 6-Card Live Telemetry Strip */}
        <div className="grid grid-cols-2 sm:grid-cols-3 xl:grid-cols-6 gap-2">
          {[
            { label: 'SAMPLE RATE', val: '24.0 MHz', color: theme.textSecondary },
            { label: 'UART BUS', val: '9600 8N1', color: theme.textPrimary },
            { label: 'DMA BUFFER', val: `${ringBufferPct}%`, color: ringBufferPct > 80 ? 'text-rose-400' : 'text-emerald-400' },
            { label: 'NTC BOILER', val: `${boilerTemp} °C`, color: 'text-amber-400' },
            { label: '3.3V LDO RAIL', val: `${railVoltage} V`, color: 'text-sky-400' },
            { label: 'LOGIC THRESH', val: `${threshTrim.toFixed(2)} V`, color: theme.textPrimary },
          ].map((card, i) => (
            <div key={i} className={`px-2.5 py-1.5 bg-black/40 border border-gray-800 rounded text-left ${theme.clipClass}`}>
              <div className="text-[10px] uppercase tracking-wider text-gray-500 font-bold">
                {card.label}
              </div>
              <div className={`text-xs font-bold font-mono ${card.color}`}>
                {card.val}
              </div>
            </div>
          ))}
        </div>
      </section>

      {/* ==================================================================== */}
      {/* ZONE 3: TOP SPLIT GRID (WAVEFORM DSO + ANALOG RAILS) */}
      {/* ==================================================================== */}
      <section className="px-4 py-3 grid grid-cols-1 lg:grid-cols-12 gap-4 flex-grow-0">
        {/* Left: Waveform Engine (Col 9) */}
        <div className={`lg:col-span-9 flex flex-col justify-between ${theme.surfaceClass} p-3`}>
          {/* Waveform Controls Toolbar */}
          <div className="flex flex-wrap items-center justify-between gap-2 pb-2 border-b border-gray-800 mb-2">
            <div className="flex items-center space-x-2">
              <button
                onClick={() => setIsRunning(!isRunning)}
                className={`flex items-center space-x-1.5 px-3 py-1 text-xs font-bold uppercase rounded ${
                  isRunning
                    ? 'bg-emerald-600/20 text-emerald-400 border border-emerald-500/50 hover:bg-emerald-600/30'
                    : 'bg-rose-600/20 text-rose-400 border border-rose-500/50 hover:bg-rose-600/30'
                }`}
              >
                {isRunning ? <Pause className="w-3.5 h-3.5" /> : <Play className="w-3.5 h-3.5" />}
                <span>{isRunning ? 'RUNNING' : 'STOPPED'}</span>
              </button>

              <div className="flex items-center space-x-1.5 text-xs text-gray-400 bg-black/40 px-2 py-1 rounded border border-gray-800">
                <span className="text-gray-500 font-bold">TRIGGER:</span>
                <select
                  value={triggerMode}
                  onChange={(e) => setTriggerMode(e.target.value)}
                  className="bg-transparent text-gray-200 outline-none text-xs font-mono cursor-pointer"
                >
                  <option value="RISING_EDGE">RISING_EDGE</option>
                  <option value="FALLING_EDGE">FALLING_EDGE</option>
                  <option value="PACKET_SOF">PACKET_SOF (0xAA)</option>
                </select>
              </div>

              <div className="flex items-center space-x-1.5 text-xs text-gray-400 bg-black/40 px-2 py-1 rounded border border-gray-800">
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
              TRIGGER LEVEL: <span className={theme.textPrimary}>{threshTrim.toFixed(2)}V</span>
            </div>
          </div>

          {/* HTML5 Canvas DSO */}
          <div className="relative w-full h-[240px] sm:h-[260px] bg-black/60 rounded border border-gray-900 overflow-hidden">
            <canvas
              ref={canvasRef}
              width={960}
              height={260}
              className="w-full h-full block"
            />
          </div>

          {/* Channel Visibility & Thresh Slider Toolbar */}
          <div className="flex flex-wrap items-center justify-between gap-3 pt-2 mt-2 border-t border-gray-800 text-xs">
            <div className="flex flex-wrap items-center gap-2">
              {[
                { key: 'ch1', label: 'CH1: UART_TX', color: theme.primary },
                { key: 'ch2', label: 'CH2: I2C_SDA', color: theme.secondary },
                { key: 'ch3', label: 'CH3: SPI_CLK', color: '#BB9AF7' },
                { key: 'ch4', label: 'CH4: 3.3V_RAIL', color: '#38BDF8' },
                { key: 'ch5', label: 'CH5: TRIAC_ZC', color: '#F97316' },
              ].map((ch) => (
                <button
                  key={ch.key}
                  onClick={() => setChannels((prev) => ({ ...prev, [ch.key]: !prev[ch.key] }))}
                  className={`flex items-center space-x-1 px-2 py-0.5 rounded text-[11px] font-mono font-bold transition-all ${
                    channels[ch.key]
                      ? 'bg-black/50 border'
                      : 'bg-black/20 text-gray-600 border border-transparent'
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

            {/* Threshold Slider */}
            <div className="flex items-center space-x-2 text-xs">
              <span className="text-gray-500 font-bold">THRESH TRIM:</span>
              <input
                type="range"
                min="0.80"
                max="3.00"
                step="0.05"
                value={threshTrim}
                onChange={(e) => setThreshTrim(parseFloat(e.target.value))}
                className="w-24 accent-amber-400 cursor-pointer"
              />
              <span className={`font-mono text-xs w-10 text-right ${theme.textPrimary}`}>
                {threshTrim.toFixed(2)}V
              </span>
            </div>
          </div>
        </div>

        {/* Right: Analog & Thermal Rails Panel (Col 3) */}
        <div className={`lg:col-span-3 flex flex-col justify-between ${theme.surfaceClass} p-3 gap-3`}>
          <div>
            <div className="flex items-center justify-between pb-2 border-b border-gray-800">
              <span className="text-xs font-bold uppercase tracking-wider text-gray-400 flex items-center space-x-1.5">
                <Flame className="w-3.5 h-3.5 text-amber-500" />
                <span>THERMAL & POWER RAILS</span>
              </span>
              <span className="text-[10px] px-1.5 py-0.5 rounded bg-emerald-500/20 text-emerald-400 font-mono font-bold">
                REGULATED
              </span>
            </div>

            {/* Radial Gauges */}
            <div className="grid grid-cols-2 gap-2 my-3">
              {/* Boiler Temp Gauge */}
              <div className="bg-black/40 border border-gray-800 p-2.5 rounded text-center">
                <div className="text-[10px] text-gray-500 uppercase tracking-wider font-bold mb-1">
                  BOILER NTC
                </div>
                <div className="relative flex items-center justify-center my-1">
                  <svg className="w-20 h-20 transform -rotate-90">
                    <circle cx="40" cy="40" r="32" stroke="#222" strokeWidth="6" fill="none" />
                    <circle
                      cx="40"
                      cy="40"
                      r="32"
                      stroke="#F59E0B"
                      strokeWidth="6"
                      strokeDasharray="201"
                      strokeDashoffset={201 - (201 * (boilerTemp / 140))}
                      strokeLinecap="round"
                      fill="none"
                    />
                  </svg>
                  <div className="absolute text-center">
                    <div className="text-sm font-bold font-mono text-amber-400">
                      {boilerTemp}
                    </div>
                    <div className="text-[9px] text-gray-500">°C</div>
                  </div>
                </div>
                <div className="text-[10px] text-gray-400 font-mono">
                  TARGET: 95.0°C
                </div>
              </div>

              {/* 3.3V CMOS Rail Gauge */}
              <div className="bg-black/40 border border-gray-800 p-2.5 rounded text-center">
                <div className="text-[10px] text-gray-500 uppercase tracking-wider font-bold mb-1">
                  3.3V CMOS RAIL
                </div>
                <div className="relative flex items-center justify-center my-1">
                  <svg className="w-20 h-20 transform -rotate-90">
                    <circle cx="40" cy="40" r="32" stroke="#222" strokeWidth="6" fill="none" />
                    <circle
                      cx="40"
                      cy="40"
                      r="32"
                      stroke="#38BDF8"
                      strokeWidth="6"
                      strokeDasharray="201"
                      strokeDashoffset={201 - (201 * (railVoltage / 3.6))}
                      strokeLinecap="round"
                      fill="none"
                    />
                  </svg>
                  <div className="absolute text-center">
                    <div className="text-sm font-bold font-mono text-sky-400">
                      {railVoltage}
                    </div>
                    <div className="text-[9px] text-gray-500">VOLTS</div>
                  </div>
                </div>
                <div className="text-[10px] text-gray-400 font-mono">
                  RIPPLE: {railRipple} mV
                </div>
              </div>
            </div>

            {/* Linear Progress Bars */}
            <div className="space-y-2 text-xs">
              <div>
                <div className="flex justify-between text-[11px] mb-1">
                  <span className="text-gray-400">DMA RING BUFFER:</span>
                  <span className="font-mono text-gray-300">{ringBufferPct}%</span>
                </div>
                <div className="w-full bg-black/50 h-2 rounded overflow-hidden border border-gray-800">
                  <div
                    className={`h-full transition-all duration-300 ${
                      ringBufferPct > 80 ? 'bg-rose-500' : 'bg-emerald-500'
                    }`}
                    style={{ width: `${ringBufferPct}%` }}
                  />
                </div>
              </div>

              <div>
                <div className="flex justify-between text-[11px] mb-1">
                  <span className="text-gray-400">TRIAC SSR PHASE ANGLE:</span>
                  <span className="font-mono text-amber-400">{ssrDuty}%</span>
                </div>
                <div className="w-full bg-black/50 h-2 rounded overflow-hidden border border-gray-800">
                  <div
                    className="h-full bg-amber-500 transition-all duration-300"
                    style={{ width: `${ssrDuty}%` }}
                  />
                </div>
              </div>
            </div>
          </div>

          {/* Quick Simulation Presets */}
          <div className="pt-2 border-t border-gray-800 flex flex-col gap-1.5">
            <div className="text-[10px] text-gray-500 uppercase tracking-wider font-bold">
              HARDWARE TESTBENCH MACROS:
            </div>
            <div className="grid grid-cols-2 gap-1.5">
              <button
                onClick={() => {
                  setBoilerTemp(96.8);
                  setSsrDuty(88);
                  handleTransmitCommand('AA 55 14 02 03 C6 18 A2');
                }}
                className="px-2 py-1 bg-black/40 hover:bg-black/60 border border-gray-700 text-gray-300 text-[10px] font-bold rounded"
              >
                LOAD BREW_PWM
              </button>
              <button
                onClick={() => {
                  handleTransmitCommand('AA 55 FF 04 00 00 DE AD');
                }}
                className="px-2 py-1 bg-rose-950/40 hover:bg-rose-900/60 border border-rose-800/60 text-rose-300 text-[10px] font-bold rounded"
              >
                SIM DESYNC_ERR
              </button>
            </div>
          </div>
        </div>
      </section>

      {/* ==================================================================== */}
      {/* ZONE 4: PROTOCOL FINITE STATE MACHINE (FSM PIPELINE) */}
      {/* ==================================================================== */}
      <section className="px-4 py-2">
        <div className={`p-2.5 ${theme.surfaceClass}`}>
          <div className="flex items-center justify-between pb-2 mb-2 border-b border-gray-800 text-xs">
            <div className="flex items-center space-x-2">
              <Layers className={`w-3.5 h-3.5 ${theme.textPrimary}`} />
              <span className="font-bold tracking-wider uppercase text-gray-400">
                HARDWARE PROTOCOL FINITE STATE MACHINE (FSM PIPELINE)
              </span>
            </div>
            <div className="flex items-center space-x-2">
              {fsmLocked && (
                <button
                  onClick={() => setFsmLocked(false)}
                  className="text-[10px] px-2 py-0.5 rounded bg-amber-500/20 text-amber-400 border border-amber-500/40 font-bold"
                >
                  UNLOCK LIVE AUTO-STEP
                </button>
              )}
              <span className="text-[11px] text-gray-500 font-mono">
                STAGE: <b className={theme.textPrimary}>{activeFsmStage}</b>
              </span>
            </div>
          </div>

          {/* 6 Stage Cards */}
          <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-2">
            {FSM_STAGES.map((stage, idx) => {
              const isActive = activeFsmStage === stage.id;
              return (
                <div
                  key={stage.id}
                  onClick={() => {
                    setActiveFsmStage(stage.id);
                    setFsmLocked(true);
                  }}
                  className={`p-2 rounded cursor-pointer transition-all duration-150 border ${
                    isActive
                      ? `${theme.borderActive} bg-black/60 ${theme.accentGlow}`
                      : 'border-gray-800 bg-black/30 hover:border-gray-700'
                  }`}
                >
                  <div className="flex items-center justify-between mb-1">
                    <span className={`text-[11px] font-bold font-mono ${isActive ? theme.textPrimary : 'text-gray-400'}`}>
                      {stage.label}
                    </span>
                    {isActive && (
                      <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-ping"></span>
                    )}
                  </div>
                  <div className="text-[10px] text-gray-500">
                    {stage.desc}
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      </section>

      {/* ==================================================================== */}
      {/* ZONE 5: BOTTOM SPLIT GRID (PACKET DECODER + BYTE INSPECTOR) */}
      {/* ==================================================================== */}
      <section className="px-4 py-2 grid grid-cols-1 lg:grid-cols-12 gap-4 flex-grow">
        {/* Left: Real-Time Packet Decoder Table (Col 8) */}
        <div className={`lg:col-span-8 flex flex-col justify-between ${theme.surfaceClass} p-3`}>
          <div>
            {/* Filter Toolbar */}
            <div className="flex flex-wrap items-center justify-between gap-2 pb-2 mb-2 border-b border-gray-800">
              <div className="flex items-center space-x-2">
                <Terminal className={`w-3.5 h-3.5 ${theme.textPrimary}`} />
                <span className="text-xs font-bold uppercase tracking-wider text-gray-400">
                  REAL-TIME PACKET DECODER & BUS CAPTURE
                </span>
              </div>

              {/* Bus Tabs */}
              <div className="flex items-center gap-1">
                {['ALL', 'UART0_RX', 'I2C_SDA', 'SPI_MOSI', 'UART0_TX'].map((bus) => (
                  <button
                    key={bus}
                    onClick={() => setBusFilter(bus)}
                    className={`text-[10px] px-2 py-0.5 font-mono font-bold rounded ${
                      busFilter === bus
                        ? `${theme.bg} ${theme.textPrimary} border ${theme.borderActive}`
                        : 'bg-black/30 text-gray-400 border border-transparent hover:border-gray-700'
                    }`}
                  >
                    {bus}
                  </button>
                ))}
              </div>
            </div>

            {/* Search Input */}
            <div className="relative mb-2">
              <Search className="w-3.5 h-3.5 absolute left-2.5 top-2 text-gray-500" />
              <input
                type="text"
                placeholder="Filter HEX bytes, Opcode, CRC status..."
                value={searchTerm}
                onChange={(e) => setSearchTerm(e.target.value)}
                className="w-full bg-black/50 border border-gray-800 rounded pl-8 pr-3 py-1 text-xs text-gray-200 placeholder-gray-600 outline-none focus:border-gray-600 font-mono"
              />
            </div>

            {/* Table Stream */}
            <div className="overflow-x-auto max-h-[220px] overflow-y-auto">
              <table className="w-full text-left text-xs font-mono">
                <thead className="text-[10px] uppercase text-gray-500 border-b border-gray-800 sticky top-0 bg-[#0E0E12]">
                  <tr>
                    <th className="py-1 px-2">ID / TIME</th>
                    <th className="py-1 px-2">BUS</th>
                    <th className="py-1 px-2">RAW HEX STREAM</th>
                    <th className="py-1 px-2">DECODED TELEMETRY</th>
                    <th className="py-1 px-2 text-right">STATUS</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-900">
                  {filteredPackets.map((pkt) => {
                    const isSelected = selectedPacket?.id === pkt.id;
                    return (
                      <tr
                        key={pkt.id}
                        onClick={() => handleSelectPacket(pkt)}
                        className={`cursor-pointer transition-colors ${
                          isSelected
                            ? 'bg-white/10 font-bold'
                            : 'hover:bg-black/40 text-gray-300'
                        }`}
                      >
                        <td className="py-1 px-2 whitespace-nowrap">
                          <span className={theme.textPrimary}>{pkt.id}</span>
                          <span className="text-gray-500 text-[10px] block">{pkt.timestamp}</span>
                        </td>
                        <td className="py-1 px-2 whitespace-nowrap">
                          <span className="text-[10px] px-1.5 py-0.5 rounded bg-black/60 border border-gray-800 text-gray-300">
                            {pkt.bus}
                          </span>
                        </td>
                        <td className="py-1 px-2 font-mono text-gray-300 whitespace-nowrap">
                          {pkt.hex}
                        </td>
                        <td className="py-1 px-2 whitespace-nowrap">
                          <div className="text-gray-200">{pkt.decoded}</div>
                          <div className="text-[10px] text-gray-500">{pkt.telemetry}</div>
                        </td>
                        <td className="py-1 px-2 text-right whitespace-nowrap">
                          <span
                            className={`text-[10px] px-1.5 py-0.5 rounded font-bold ${
                              pkt.status === 'CRC16_OK'
                                ? 'bg-emerald-500/20 text-emerald-400 border border-emerald-500/30'
                                : 'bg-rose-500/20 text-rose-400 border border-rose-500/30'
                            }`}
                          >
                            {pkt.status}
                          </span>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </div>

          <div className="text-[10px] text-gray-500 pt-2 border-t border-gray-800 flex justify-between">
            <span>PACKET STREAM BUFFER: {filteredPackets.length} FRAMES</span>
            <span>POLYNOMIAL: CRC-16/CCITT-FALSE (0x1021)</span>
          </div>
        </div>

        {/* Right: Byte Inspector / Bitfield Drawer (Col 4) */}
        <div className={`lg:col-span-4 flex flex-col justify-between ${theme.surfaceClass} p-3`}>
          <div>
            <div className="flex items-center justify-between pb-2 mb-2 border-b border-gray-800">
              <span className="text-xs font-bold uppercase tracking-wider text-gray-400 flex items-center space-x-1.5">
                <Cpu className={`w-3.5 h-3.5 ${theme.textSecondary}`} />
                <span>BYTE-INSPECTOR & BITFIELDS</span>
              </span>
              <span className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-black/40 text-gray-300">
                FRAME: {selectedPacket?.id || 'NONE'}
              </span>
            </div>

            {/* Selected Packet Header Info */}
            {selectedPacket && (
              <div className="mb-2 p-2 bg-black/40 rounded border border-gray-800 text-xs">
                <div className="flex justify-between text-[11px] mb-1">
                  <span className="text-gray-500">OPCODE / SYMBOL:</span>
                  <span className={`font-mono font-bold ${theme.textPrimary}`}>
                    {selectedPacket.cmd}
                  </span>
                </div>
                <div className="flex justify-between text-[11px]">
                  <span className="text-gray-500">PAYLOAD SUMMARY:</span>
                  <span className="font-mono text-gray-300 truncate max-w-[200px]">
                    {selectedPacket.decoded}
                  </span>
                </div>
              </div>
            )}

            {/* 8-Byte Register Breakdown Table */}
            <div className="space-y-1 overflow-y-auto max-h-[190px]">
              {selectedPacket?.bytes?.map((b) => (
                <div
                  key={b.offset}
                  className="flex items-center justify-between px-2 py-1 bg-black/30 border border-gray-800/80 rounded text-[11px] font-mono hover:border-gray-700"
                >
                  <div className="flex items-center space-x-2">
                    <span className="text-gray-500 text-[10px]">{b.offset}</span>
                    <span className={`px-1.5 py-0.2 rounded bg-black/60 font-bold border border-gray-700 ${theme.textPrimary}`}>
                      0x{b.hex}
                    </span>
                    <span className="text-gray-400 text-[10px]">{b.bin}</span>
                  </div>
                  <div className="text-gray-400 text-[10px] truncate max-w-[140px] text-right">
                    {b.desc}
                  </div>
                </div>
              ))}
            </div>
          </div>

          <div className="text-[10px] text-gray-500 pt-2 border-t border-gray-800 text-right">
            LITTLE-ENDIAN // 8-BIT WORD PACKING
          </div>
        </div>
      </section>

      {/* ==================================================================== */}
      {/* ZONE 6: INTERACTIVE UART TX COMMAND INJECTOR FOOTER */}
      {/* ==================================================================== */}
      <footer className={`p-3 border-t ${theme.border} ${theme.panelBg}`}>
        <div className="flex flex-col sm:flex-row items-center justify-between gap-3">
          {/* Quick Macro Buttons */}
          <div className="flex items-center space-x-2 w-full sm:w-auto">
            <span className="text-[11px] font-bold uppercase text-gray-500 whitespace-nowrap">
              TX MACROS:
            </span>
            <div className="flex flex-wrap gap-1">
              <button
                onClick={() => setTxCommand('AA 55 10 00 00 00 44 21')}
                className="px-2 py-1 text-[10px] font-mono font-bold bg-black/40 hover:bg-black/60 border border-gray-700 text-gray-300 rounded"
              >
                [SYNC_PING]
              </button>
              <button
                onClick={() => setTxCommand('AA 55 14 02 00 00 8A 19')}
                className="px-2 py-1 text-[10px] font-mono font-bold bg-black/40 hover:bg-black/60 border border-gray-700 text-gray-300 rounded"
              >
                [POLL_NTC]
              </button>
              <button
                onClick={() => setTxCommand('AA 55 FF 04 DE AD BE EF')}
                className="px-2 py-1 text-[10px] font-mono font-bold bg-rose-950/40 hover:bg-rose-900/60 border border-rose-800/60 text-rose-300 rounded"
              >
                [CRC_FAULT]
              </button>
            </div>
          </div>

          {/* Hex Stream Injection Form */}
          <div className="flex items-center space-x-2 w-full sm:w-auto flex-grow max-w-2xl">
            <div className="relative flex-grow">
              <span className={`absolute left-2.5 top-1.5 text-xs font-mono font-bold ${theme.textPrimary}`}>
                TX&gt;
              </span>
              <input
                type="text"
                value={txCommand}
                onChange={(e) => setTxCommand(e.target.value)}
                placeholder="AA 55 ..."
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
              <span>TRANSMIT FRAME</span>
            </button>
          </div>
        </div>
      </footer>
    </div>
  );
}
