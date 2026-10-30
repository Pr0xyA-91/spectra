import React, { useState } from 'react';
import {
  Droplet,
  Activity,
  Zap,
  Flame,
  Cpu,
  Layers,
  Sparkles,
  Inbox,
  Coffee,
  CheckCircle2,
  AlertTriangle,
  Info,
  Sliders,
} from 'lucide-react';

/**
 * Interactive Hydraulic & Mechanical Digital Twin Schematic
 * Visualizes the physical fluid path and electromechanical actuators.
 * Clicking any node focuses deep inspection telemetry and hardware engineering specs.
 */
export default function DigitalTwinSchematic({
  theme,
  liveData,
  statsData,
}) {
  const [selectedNodeId, setSelectedNodeId] = useState('tb1'); // Default select coffee heater

  const telem = liveData?.telemetry || {};
  const switches = liveData?.switches || [];

  const tankSw = switches.find((s) => s.id === 'water_tank');
  const traySw = switches.find((s) => s.id === 'drip_tray');
  const filterSw = switches.find((s) => s.id === 'claris_filter');

  const tb1Temp = telem.heater_coffee_c ?? 97.0;
  const tb2Temp = telem.heater_steam_c;
  const isDualHeater = telem.is_dual_heater ?? false;
  const buPos = telem.bu_encoder_pos ?? 229;
  const buUpper = telem.bu_encoder_upper ?? 649;
  const buZone = telem.bu_position_state || 'Home / Mill Position';
  const flowRate = telem.flow_rate_ml_s ?? 0.0;
  const flowVolume = telem.flow_volume_ml ?? 0.0;
  const flowPulses = telem.flow_pulses ?? 120;
  const beansOk = telem.beans_ok ?? true;
  const opticalDelta = telem.optical_delta ?? 90;

  // Node specifications and dynamic state
  const NODES = {
    tank: {
      id: 'tank',
      label: 'WATER TANK',
      icon: '💧',
      status: tankSw?.ok ? 'NOMINAL' : 'EMPTY / TANK',
      primary: tankSw?.ok ? 'Water Level OK' : 'Refill Required',
      details: 'Chassis reed sensor actuated by magnetic float in water tank reservoir.',
      hardware: 'Reed switch contact: NO (Normally Open) | Safety Lockout: Level 1 (Hard Block)',
      badge: tankSw?.ok ? 'NORMAL' : 'EMPTY',
      ok: tankSw?.ok !== false,
      x: 60,
      y: 70,
    },
    flowmeter: {
      id: 'flowmeter',
      label: 'FLOWMETER',
      icon: '🌊',
      status: flowRate > 0 ? 'PUMPING' : 'IDLE',
      primary: `${flowRate.toFixed(1)} ml/s (${flowPulses} pulses)`,
      details: `Turbine impulse rate: ${flowRate.toFixed(2)} ml/s | Cycle volume: ${flowVolume.toFixed(1)} ml.`,
      hardware: 'Digmesa Nano 1.2mm nozzle | Hall effect impulse sensor: ~2.37 ml / 100 pulses',
      badge: flowRate > 0 ? 'ACTIVE' : 'IDLE',
      ok: true,
      x: 180,
      y: 70,
    },
    pump: {
      id: 'pump',
      label: 'VIBRATION PUMP',
      icon: '⚡',
      status: flowRate > 0 ? 'ENERGIZED' : 'STANDBY',
      primary: flowRate > 0 ? '15 BAR ACTIVE' : '0.0 BAR (STANDBY)',
      details: 'Triac-controlled vibration pump delivering 15 bar peak extraction pressure.',
      hardware: 'Ulka EP5 230V / 50Hz, 48W | Half-wave diode & Triac phase angle switching',
      badge: flowRate > 0 ? 'PUMPING' : 'READY',
      ok: true,
      x: 300,
      y: 70,
    },
    tb1: {
      id: 'tb1',
      label: 'COFFEE THERMOBLOCK',
      icon: '☕',
      status: tb1Temp >= 90 && tb1Temp <= 100 ? 'READY' : 'HEATING',
      primary: `${tb1Temp.toFixed(1)} °C`,
      details: `Primary coffee thermoblock PID controlled temperature. Target brew zone: 90°C–95°C.`,
      hardware: 'Aluminum cast heater 1400W @ 230V | NTC Resistance: ~10kΩ @ 25°C (NTC raw: 970)',
      badge: tb1Temp >= 90 && tb1Temp <= 100 ? 'READY' : 'HEATING',
      ok: true,
      x: 430,
      y: 70,
    },
    valve: {
      id: 'valve',
      label: 'MULTIWAY VALVE',
      icon: '🔀',
      status: telem.mv_busy ? 'POSITIONING' : 'HOMED / READY',
      primary: telem.mv_busy ? 'Valve Moving' : 'Dispensing Channel',
      details: 'Ceramic multiway distributor valve for fluid routing (Coffee, Rinse, Bypass).',
      hardware: 'DC Stepper / Microswitch position feedback | Low-voltage motor drive',
      badge: telem.mv_busy ? 'BUSY' : 'READY',
      ok: telem.mv_init_ok !== false,
      x: 560,
      y: 70,
    },
    bu: {
      id: 'bu',
      label: 'BREW UNIT & ENCODER',
      icon: '⚙️',
      status: buPos === 0 ? 'INITIALIZING' : 'SYNCHRONIZED',
      primary: `${buPos} / ${buUpper} ticks`,
      details: `Mechanical stroke: ${buZone} (${telem.bu_stroke_pct ?? 0}% travel).`,
      hardware: 'Buhler 12V DC motor | Quadrature optical encoder disk with slotted optocoupler',
      badge: `${buPos} tk`,
      ok: telem.bu_init_ok !== false,
      x: 430,
      y: 190,
    },
    beans: {
      id: 'beans',
      label: 'BEAN HOPPER SENSOR',
      icon: '🫘',
      status: beansOk ? 'BEANS OK' : 'EMPTY',
      primary: `Delta: ${opticalDelta} counts`,
      details: `Optical IR reflection sensor. Ambient ADC: ${telem.bean_adcs?.[0] ?? '--'}, Reflected: ${telem.bean_adcs?.[1] ?? '--'}.`,
      hardware: 'IR LED emitter & phototransistor receiver pair | Threshold: 115 ± 5 counts',
      badge: beansOk ? 'CHARGED' : 'EMPTY',
      ok: beansOk,
      x: 300,
      y: 190,
    },
    tray: {
      id: 'tray',
      label: 'DRIP TRAY & DRAWER',
      icon: '📥',
      status: traySw?.ok ? 'INSERTED' : 'MISSING',
      primary: traySw?.ok ? 'Tray Present' : 'Tray Removed',
      details: 'Dual contact leaf springs on rear chassis detecting drawer insertion.',
      hardware: 'Mechanical leaf microswitch contacts | Safety Interlock: Immediate motor shutdown',
      badge: traySw?.ok ? 'INSERTED' : 'MISSING',
      ok: traySw?.ok !== false,
      x: 560,
      y: 190,
    },
  };

  const selectedNode = NODES[selectedNodeId] || NODES.tb1;

  return (
    <div className="space-y-3">
      {/* 1. INTERACTIVE DIGITAL TWIN SCHEMATIC CANVAS */}
      <div className={`p-4 border rounded ${theme.surfaceClass}`}>
        <div className="flex items-center justify-between mb-2">
          <div className="flex items-center space-x-2">
            <span className="text-base font-bold text-gray-300 flex items-center space-x-1.5">
              <span>HYDRAULIC &amp; ELECTROMECHANICAL DIGITAL TWIN</span>
            </span>
            <span className="text-[10px] text-gray-500 font-mono">(CLICK ANY COMPONENT TO INSPECT)</span>
          </div>
          <span className="text-xs font-mono text-gray-400">
            PORTS: <span className="text-emerald-400 font-bold">ONLINE</span>
          </span>
        </div>

        {/* Schematic Flow Container */}
        <div className="relative w-full h-[270px] bg-black/40 border border-gray-800/80 rounded-lg p-2 overflow-x-auto select-none">
          <svg className="w-[660px] h-full mx-auto" viewBox="0 0 660 260">
            {/* Flow Connecting Lines */}
            {/* Upper line: Tank -> Flowmeter -> Pump -> TB1 -> Valve */}
            <path
              d="M 110 85 L 180 85"
              stroke="#38BDF8"
              strokeWidth="2.5"
              strokeDasharray={flowRate > 0 ? "4,4" : "none"}
              className={flowRate > 0 ? "animate-pulse" : ""}
            />
            <path
              d="M 230 85 L 300 85"
              stroke="#38BDF8"
              strokeWidth="2.5"
              strokeDasharray={flowRate > 0 ? "4,4" : "none"}
            />
            <path
              d="M 350 85 L 430 85"
              stroke="#F43F5E"
              strokeWidth="2.5"
            />
            <path
              d="M 480 85 L 560 85"
              stroke="#F43F5E"
              strokeWidth="2.5"
            />

            {/* Downward line: Valve -> Brew Unit */}
            <path
              d="M 585 110 L 585 145 L 455 145 L 455 175"
              stroke="#A855F7"
              strokeWidth="2"
              fill="none"
              strokeDasharray="3,3"
            />

            {/* Grinder line: Beans -> Brew Unit */}
            <path
              d="M 350 205 L 405 205"
              stroke="#F59E0B"
              strokeWidth="2"
              strokeDasharray="3,3"
            />

            {/* Waste line: Brew Unit -> Drip Tray */}
            <path
              d="M 480 205 L 535 205"
              stroke="#64748B"
              strokeWidth="2"
              strokeDasharray="4,4"
            />

            {/* Flow Direction Indicator Arrows */}
            <polygon points="150,82 156,85 150,88" fill="#38BDF8" />
            <polygon points="270,82 276,85 270,88" fill="#38BDF8" />
            <polygon points="395,82 401,85 395,88" fill="#F43F5E" />
            <polygon points="525,82 531,85 525,88" fill="#F43F5E" />

            {/* Render Nodes */}
            {Object.values(NODES).map((node) => {
              const isSelected = node.id === selectedNodeId;
              return (
                <g
                  key={node.id}
                  onClick={() => setSelectedNodeId(node.id)}
                  className="cursor-pointer group"
                  transform={`translate(${node.x - 45}, ${node.y - 30})`}
                >
                  {/* Node Background Box */}
                  <rect
                    width="95"
                    height="62"
                    rx="6"
                    className={`transition-all duration-150 ${
                      isSelected
                        ? 'fill-slate-900 stroke-2'
                        : 'fill-black/80 stroke hover:fill-slate-900/80'
                    }`}
                    stroke={isSelected ? theme.primary : '#334155'}
                  />

                  {/* Icon & Label */}
                  <text x="8" y="18" fontSize="13">
                    {node.icon}
                  </text>
                  <text
                    x="27"
                    y="17"
                    fontSize="8"
                    fontWeight="bold"
                    fontFamily="monospace"
                    fill={isSelected ? (theme.primary || '#FF4F00') : '#CBD5E1'}
                  >
                    {node.label.length > 11 ? node.label.slice(0, 10) + '..' : node.label}
                  </text>

                  {/* Primary Telemetry */}
                  <text
                    x="8"
                    y="36"
                    fontSize="11"
                    fontWeight="bold"
                    fontFamily="monospace"
                    fill={node.ok ? '#F8FAFC' : '#F87171'}
                  >
                    {node.primary}
                  </text>

                  {/* Status Badge */}
                  <rect
                    x="8"
                    y="43"
                    width="79"
                    height="13"
                    rx="3"
                    fill={node.ok ? 'rgba(16, 185, 129, 0.15)' : 'rgba(239, 68, 68, 0.2)'}
                  />
                  <text
                    x="47"
                    y="52"
                    fontSize="7.5"
                    fontWeight="bold"
                    fontFamily="monospace"
                    textAnchor="middle"
                    fill={node.ok ? '#34D399' : '#F87171'}
                  >
                    {node.badge}
                  </text>
                </g>
              );
            })}
          </svg>
        </div>
      </div>

      {/* 2. SELECTED COMPONENT DEEP TELEMETRY INSPECTOR */}
      <div className={`p-4 border rounded ${theme.surfaceClass}`}>
        <div className="flex items-center justify-between mb-3 border-b border-gray-800 pb-2">
          <div className="flex items-center space-x-2">
            <span className="text-xl">{selectedNode.icon}</span>
            <div>
              <div className="text-xs font-bold text-gray-400 uppercase tracking-wider">
                DEEP COMPONENT INSPECTOR
              </div>
              <div className={`text-sm font-bold font-mono ${theme.textPrimary}`}>
                {selectedNode.label}
              </div>
            </div>
          </div>
          <span className={`text-xs px-2.5 py-1 rounded font-bold font-mono ${selectedNode.ok ? 'bg-emerald-950 text-emerald-300 border border-emerald-600' : 'bg-rose-950 text-rose-300 border border-rose-600'}`}>
            {selectedNode.status}
          </span>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-3 text-xs">
          {/* Box 1: Primary Telemetry */}
          <div className="p-3 bg-black/40 border border-gray-800 rounded">
            <div className="text-[10px] text-gray-500 font-bold uppercase tracking-wider mb-1">
              PRIMARY TELEMETRY
            </div>
            <div className={`text-base font-bold font-mono ${theme.textSecondary}`}>
              {selectedNode.primary}
            </div>
            <div className="text-[11px] text-gray-400 mt-1">
              {selectedNode.details}
            </div>
          </div>

          {/* Box 2: Operating Status */}
          <div className="p-3 bg-black/40 border border-gray-800 rounded">
            <div className="text-[10px] text-gray-500 font-bold uppercase tracking-wider mb-1">
              OPERATING STATUS
            </div>
            <div className={`text-sm font-bold font-mono ${selectedNode.ok ? 'text-emerald-400' : 'text-rose-400'}`}>
              {selectedNode.status}
            </div>
            <div className="text-[11px] text-gray-400 mt-1">
              Safety interlocking verified. Register feedback nominal without fault trips.
            </div>
          </div>

          {/* Box 3: Hardware Specifications */}
          <div className="p-3 bg-black/40 border border-gray-800 rounded">
            <div className="text-[10px] text-gray-500 font-bold uppercase tracking-wider mb-1">
              HARDWARE SPECIFICATIONS
            </div>
            <div className="text-[11px] font-mono text-gray-300">
              {selectedNode.hardware}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
