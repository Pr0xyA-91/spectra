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
import { txVal } from '../i18n/translations';

/**
 * Interactive Hydraulic & Mechanical Digital Twin Schematic
 * Visualizes the physical fluid path and electromechanical actuators.
 * Clicking any node focuses deep inspection telemetry and hardware engineering specs.
 */
export default function DigitalTwinSchematic({
  theme,
  lang = 'en',
  liveData,
  statsData,
}) {
  const isCs = lang === 'cs';
  const [selectedNodeId, setSelectedNodeId] = useState('tb1'); // Default select coffee heater

  const telem = liveData?.telemetry || {};
  const hasTelem = Boolean(telem && Object.keys(telem).length > 0);
  const switches = liveData?.switches || [];

  const tankSw = hasTelem ? switches.find((s) => s.id === 'water_tank') : null;
  const traySw = hasTelem ? switches.find((s) => s.id === 'drip_tray') : null;
  const filterSw = hasTelem ? switches.find((s) => s.id === 'claris_filter') : null;
  const beansSw = hasTelem ? switches.find((s) => s.id === 'bean_hopper') : null;

  const tb1Temp = hasTelem && telem.heater_coffee_c != null ? telem.heater_coffee_c : null;
  const tb2Temp = hasTelem && telem.heater_steam_c != null ? telem.heater_steam_c : null;
  const isDualHeater = telem.is_dual_heater ?? false;
  const buPos = hasTelem && telem.bu_encoder_pos != null ? telem.bu_encoder_pos : null;
  const buUpper = hasTelem && telem.bu_encoder_upper != null ? telem.bu_encoder_upper : null;
  const buZone = hasTelem && telem.bu_position_state ? telem.bu_position_state : (isCs ? 'Pohotovost / Nenačteno' : 'Standby / Unread');
  const flowRate = hasTelem && telem.flow_rate_ml_s != null ? telem.flow_rate_ml_s : null;
  const flowVolume = hasTelem && telem.flow_volume_ml != null ? telem.flow_volume_ml : null;
  const flowPulses = hasTelem && telem.flow_pulses != null ? telem.flow_pulses : null;
  const beansOk = hasTelem && telem.beans_ok != null ? telem.beans_ok : null;
  const opticalDelta = hasTelem && telem.optical_delta != null ? telem.optical_delta : null;
  const isLocalBeanDisplay = Boolean(beansSw?.details?.includes('Monitored Locally'));

  // Node specifications and dynamic state
  const NODES = {
    tank: {
      id: 'tank',
      label: isCs ? 'NÁDRŽKA VODY' : 'WATER TANK',
      icon: '💧',
      status: tankSw ? (tankSw.ok ? (isCs ? 'V NORMĚ' : 'NOMINAL') : (isCs ? 'PRÁZDNÁ' : 'EMPTY / TANK')) : (isCs ? 'POHOTOVOST' : 'STANDBY'),
      primary: tankSw ? (tankSw.ok ? (isCs ? 'Voda OK' : 'Water Level OK') : (isCs ? 'Nutno doplnit' : 'Refill Required')) : '---',
      details: isCs ? 'Jazýčkový senzor spínaný magnetickým plovákem v nádržce na vodu.' : 'Chassis reed sensor actuated by magnetic float in water tank reservoir.',
      hardware: isCs ? 'Jazýčkový kontakt: NO (normálně rozpojený) | Blokace: Úroveň 1' : 'Reed switch contact: NO (Normally Open) | Safety Lockout: Level 1 (Hard Block)',
      badge: tankSw ? (tankSw.ok ? (isCs ? 'V NORMĚ' : 'NORMAL') : (isCs ? 'PRÁZDNÁ' : 'EMPTY')) : (isCs ? 'POHOT.' : 'STANDBY'),
      ok: tankSw ? tankSw.ok !== false : true,
      x: 60,
      y: 70,
    },
    flowmeter: {
      id: 'flowmeter',
      label: isCs ? 'PRŮTOKOMĚR' : 'FLOWMETER',
      icon: '🌊',
      status: flowRate != null ? (flowRate > 0 ? (isCs ? 'ČERPÁNÍ' : 'PUMPING') : (isCs ? 'NEČINNÝ' : 'IDLE')) : (isCs ? 'POHOTOVOST' : 'STANDBY'),
      primary: flowRate != null ? `${flowRate.toFixed(1)} ml/s (${flowPulses ?? 0} ${isCs ? 'imp.' : 'pulses'})` : '--- ml/s',
      details: flowRate != null
        ? (isCs ? `Průtok turbínkou: ${flowRate.toFixed(2)} ml/s | Objem dávky: ${(flowVolume ?? 0).toFixed(1)} ml.` : `Turbine impulse rate: ${flowRate.toFixed(2)} ml/s | Cycle volume: ${(flowVolume ?? 0).toFixed(1)} ml.`)
        : (isCs ? 'Impulzní průtokoměr Digmesa v pohotovosti.' : 'Digmesa impulse flowmeter standby.'),
      hardware: isCs ? 'Digmesa Nano tryska 1,2 mm | Hallův senzor: ~2,37 ml / 100 impulzů' : 'Digmesa Nano 1.2mm nozzle | Hall effect impulse sensor: ~2.37 ml / 100 pulses',
      badge: flowRate != null ? (flowRate > 0 ? (isCs ? 'AKTIVNÍ' : 'ACTIVE') : (isCs ? 'KLID' : 'IDLE')) : (isCs ? 'POHOT.' : 'STANDBY'),
      ok: true,
      x: 180,
      y: 70,
    },
    pump: {
      id: 'pump',
      label: isCs ? 'ČERPADLO' : 'VIBRATION PUMP',
      icon: '⚡',
      status: flowRate != null ? (flowRate > 0 ? (isCs ? 'POD NAPĚTÍM' : 'ENERGIZED') : (isCs ? 'POHOTOVOST' : 'STANDBY')) : (isCs ? 'POHOTOVOST' : 'STANDBY'),
      primary: flowRate != null ? (flowRate > 0 ? (isCs ? '15 BAR AKTIVNÍ' : '15 BAR ACTIVE') : (isCs ? '0,0 BAR (KLID)' : '0.0 BAR (STANDBY)')) : '--- BAR',
      details: isCs ? 'Vibrační čerpadlo řízené triakem s pracovním tlakem až 15 bar.' : 'Triac-controlled vibration pump delivering 15 bar peak extraction pressure.',
      hardware: isCs ? 'Ulka EP5 230V / 50Hz, 48W | Řízení půlvlnou a fázové spínání triakem' : 'Ulka EP5 230V / 50Hz, 48W | Half-wave diode & Triac phase angle switching',
      badge: flowRate != null ? (flowRate > 0 ? (isCs ? 'ČERPÁ' : 'PUMPING') : (isCs ? 'PŘIPRAV.' : 'READY')) : (isCs ? 'POHOT.' : 'STANDBY'),
      ok: true,
      x: 300,
      y: 70,
    },
    tb1: {
      id: 'tb1',
      label: isCs ? 'TOPNÝ BLOK' : 'COFFEE THERMOBLOCK',
      icon: '☕',
      status: tb1Temp != null
        ? (tb1Temp >= 80 && tb1Temp <= 115
            ? (isCs ? 'PŘIPRAVEN' : 'READY')
            : (tb1Temp > 115 ? (isCs ? 'PŘEHŘÁTÍ' : 'OVERHEAT') : (isCs ? 'NAHŘÍVÁ SE' : 'HEATING')))
        : (isCs ? 'POHOTOVOST' : 'STANDBY'),
      primary: tb1Temp != null ? `${tb1Temp.toFixed(1)} °C` : '--- °C',
      details: tb1Temp != null
        ? (isCs ? 'Hlavní kávový termoblok řízený PID regulací. Pracovní rozsah: 80 °C–115 °C.' : 'Primary coffee thermoblock PID controlled temperature. Target brew zone: 80°C–115°C.')
        : (isCs ? 'Čekám na načtení teploty termobloku.' : 'Thermoblock temperature awaiting sensor read.'),
      hardware: isCs ? 'Hliníkový ohřívač 1400W @ 230V | NTC odpor: ~10kΩ @ 25°C' : 'Aluminum cast heater 1400W @ 230V | NTC Resistance: ~10kΩ @ 25°C (NTC raw: 970)',
      badge: tb1Temp != null
        ? (tb1Temp >= 80 && tb1Temp <= 115
            ? (isCs ? 'PŘIPRAV.' : 'READY')
            : (tb1Temp > 115 ? (isCs ? 'PŘEHŘÁTÍ' : 'OVERHEAT') : (isCs ? 'OHŘEV' : 'HEATING')))
        : (isCs ? 'POHOT.' : 'STANDBY'),
      ok: tb1Temp != null ? tb1Temp <= 115 : true,
      x: 430,
      y: 70,
    },
    valve: {
      id: 'valve',
      label: isCs ? 'VENTIL' : 'MULTIWAY VALVE',
      icon: '🔀',
      status: telem.mv_busy ? (isCs ? 'POLOHOVÁNÍ' : 'POSITIONING') : (isCs ? 'VÝCHOZÍ / PŘIPRAVEN' : 'HOMED / READY'),
      primary: telem.mv_busy ? (isCs ? 'Ventil se otáčí' : 'Valve Moving') : (isCs ? 'Výdejní poloha' : 'Dispensing Channel'),
      details: isCs ? 'Keramický vícecestný rozdělovač vody (káva, proplach, pára/bypass).' : 'Ceramic multiway distributor valve for fluid routing (Coffee, Rinse, Bypass).',
      hardware: isCs ? 'DC motorek / mikrospínače zpětné vazby polohy' : 'DC Stepper / Microswitch position feedback | Low-voltage motor drive',
      badge: telem.mv_busy ? (isCs ? 'PRACUJE' : 'BUSY') : (isCs ? 'PŘIPRAV.' : 'READY'),
      ok: telem.mv_init_ok !== false,
      x: 560,
      y: 70,
    },
    bu: {
      id: 'bu',
      label: isCs ? 'SPAŘ. JEDN.' : 'BREW UNIT & ENCODER',
      icon: '⚙️',
      status: buPos != null ? (buPos === 0 ? (isCs ? 'INICIALIZACE' : 'INITIALIZING') : (isCs ? 'SYNCHRONIZOVÁNA' : 'SYNCHRONIZED')) : (isCs ? 'POHOTOVOST' : 'STANDBY'),
      primary: buPos != null ? `${buPos} / ${buUpper ?? '---'} ${isCs ? 'tiků' : 'ticks'}` : (isCs ? '--- / --- tiků' : '--- / --- ticks'),
      details: isCs ? `Mechanický zdvih: ${buZone} (${telem.bu_stroke_pct ?? 0} % dráhy).` : `Mechanical stroke: ${buZone} (${telem.bu_stroke_pct ?? 0}% travel).`,
      hardware: isCs ? 'Buhler 12V DC motor | Optický enkodér s clonkou' : 'Buhler 12V DC motor | Quadrature optical encoder disk with slotted optocoupler',
      badge: buPos != null ? `${buPos} tk` : '--- tk',
      ok: telem.bu_init_ok !== false,
      x: 430,
      y: 190,
    },
    beans: {
      id: 'beans',
      label: isCs ? 'ZÁSOBNÍK ZRN' : 'BEAN HOPPER SENSOR',
      icon: '🫘',
      status: isLocalBeanDisplay
        ? (isCs ? 'Hlídáno lokálně displejem (EF518D)' : 'Monitored Locally by Display MCU (EF518D)')
        : (beansSw?.status ? txVal(lang, beansSw.status) : (beansOk != null ? (beansOk ? (isCs ? 'ZRNA OK' : 'BEANS OK') : (isCs ? 'DOPLNIT ZRNA' : 'FILL BEANS')) : (isCs ? 'POHOTOVOST' : 'STANDBY'))),
      primary: isLocalBeanDisplay
        ? (isCs ? 'LOKÁLNĚ (EF518D)' : 'LOCAL (EF518D)')
        : (beansOk != null ? (beansOk ? (isCs ? 'PLNÝ' : 'CHARGED') : (isCs ? 'PRÁZDNÝ' : 'EMPTY')) : '---'),
      details: beansSw?.details ? txVal(lang, beansSw.details) : (isCs ? 'Stav zrn dle bitu HZ[0][3], displeje nebo snímače.' : 'Live bean presence via HZ[0][3] status bit, local display MCU, or optical sensor.'),
      hardware: isLocalBeanDisplay
        ? (isCs ? 'Čelní displej (EF518D / Renesas R8C) — lokální fototranzistor' : 'Front Display MCU (EF518D / Renesas R8C) Local Phototransistor')
        : (isCs ? 'Detektor zrn v MCU Renesas | Bit 3 rámce HZ' : 'Renesas MCU digital bean charge detector | Bit 3 of HZ telemetry frame'),
      badge: isLocalBeanDisplay
        ? (isCs ? 'LOKÁLNĚ' : 'LOCAL (EF518D)')
        : (beansSw?.badge ? txVal(lang, beansSw.badge) : (beansOk != null ? (beansOk ? (isCs ? 'PLNÝ' : 'CHARGED') : (isCs ? 'PRÁZDNÝ' : 'EMPTY')) : (isCs ? 'POHOT.' : 'STANDBY'))),
      ok: beansSw ? beansSw.ok : (beansOk !== false),
      x: 300,
      y: 190,
    },
    tray: {
      id: 'tray',
      label: isCs ? 'ODKAPNÍ MISKA' : 'DRIP TRAY & DRAWER',
      icon: '📥',
      status: traySw ? (traySw.ok ? (isCs ? 'VLOŽENA' : 'INSERTED') : (isCs ? 'CHYBÍ' : 'MISSING')) : (isCs ? 'POHOTOVOST' : 'STANDBY'),
      primary: traySw ? (traySw.ok ? (isCs ? 'Miska vložena' : 'Tray Present') : (isCs ? 'Miska vyjmuta' : 'Tray Removed')) : '---',
      details: isCs ? 'Dvojité kontaktní pružinky v zadní části šachty snímající zasunutí misky.' : 'Dual contact leaf springs on rear chassis detecting drawer insertion.',
      hardware: isCs ? 'Mechanický mikrospínač | Bezpečnostní blokace pohonu' : 'Mechanical leaf microswitch contacts | Safety Interlock: Immediate motor shutdown',
      badge: traySw ? (traySw.ok ? (isCs ? 'VLOŽENA' : 'INSERTED') : (isCs ? 'CHYBÍ' : 'MISSING')) : (isCs ? 'POHOT.' : 'STANDBY'),
      ok: traySw ? traySw.ok !== false : true,
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
              <span>{isCs ? 'HYDRAULICKÉ A MECHANICKÉ SCHÉMA (DIGITÁLNÍ DVOJČE)' : 'HYDRAULIC & ELECTROMECHANICAL DIGITAL TWIN'}</span>
            </span>
            <span className="text-[10px] text-gray-500 font-mono">{isCs ? '(KLIKNUTÍM NA SOUČÁSTKU ZOBRAZÍTE DETAIL)' : '(CLICK ANY COMPONENT TO INSPECT)'}</span>
          </div>
          <span className="text-xs font-mono text-gray-400">
            {isCs ? 'PORTY:' : 'PORTS:'} <span className="text-emerald-400 font-bold">ONLINE</span>
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
                {isCs ? 'DETAILNÍ INSPEKTOR KOMPONENTY' : 'DEEP COMPONENT INSPECTOR'}
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
              {isCs ? 'HLAVNÍ TELEMETRIE' : 'PRIMARY TELEMETRY'}
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
              {isCs ? 'PROVOZNÍ STAV' : 'OPERATING STATUS'}
            </div>
            <div className={`text-sm font-bold font-mono ${selectedNode.ok ? 'text-emerald-400' : 'text-rose-400'}`}>
              {selectedNode.status}
            </div>
            <div className="text-[11px] text-gray-400 mt-1">
              {isCs ? 'Bezpečnostní blokace ověřeny. Odezva registrů bez chybových stavů.' : 'Safety interlocking verified. Register feedback nominal without fault trips.'}
            </div>
          </div>

          {/* Box 3: Hardware Specifications */}
          <div className="p-3 bg-black/40 border border-gray-800 rounded">
            <div className="text-[10px] text-gray-500 font-bold uppercase tracking-wider mb-1">
              {isCs ? 'HARDWAROVÉ PARAMETRY' : 'HARDWARE SPECIFICATIONS'}
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
