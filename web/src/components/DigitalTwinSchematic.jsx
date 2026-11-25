import React, { useState, useEffect, useMemo } from 'react';
import { txVal } from '../i18n/translations';

/**
 * Device-Aware Interactive Hydraulic & Electromechanical Digital Twin Schematic
 * Dynamically adapts topology, nodes, hydraulic paths, and hardware specs based on
 * backend `liveData.capabilities` (Jura Single / Dual / Smart Connect, Nivona, Kalerm, Jetinno).
 */
function DigitalTwinSchematic({
  theme,
  lang = 'en',
  liveData,
  statsData,
}) {
  const isCs = lang === 'cs';
  const [selectedNodeId, setSelectedNodeId] = useState('tb1');

  const telem = liveData?.telemetry || {};
  const caps = liveData?.capabilities || {};
  const hasTelem = Boolean(telem && Object.keys(telem).length > 0);
  const switches = liveData?.switches || [];
  const protocol = liveData?.protocol || caps.protocol || '';
  const hasLiveFrame =
    caps.has_live_frame !== undefined ? Boolean(caps.has_live_frame) : hasTelem;

  // Determine active device topology
  const topologyConfig = useMemo(() => {
    let topology = 'jura_single';
    if (caps.topology) topology = caps.topology;
    else if (protocol.toLowerCase().includes('smart connect')) topology = 'jura_smart_connect';
    else if (protocol.toLowerCase().includes('jetinno')) topology = 'jetinno_vending';
    else if (protocol.toLowerCase().includes('kalerm') || protocol.toLowerCase().includes('modbus')) topology = 'kalerm_dual';
    else if (protocol.toLowerCase().includes('eugster')) topology = 'nivona_single';
    else if (telem.is_dual_heater) topology = 'jura_dual';

    return {
      inferredTopology: topology,
      isDual: topology === 'jura_dual' || topology === 'kalerm_dual' || topology === 'jetinno_vending',
      isSmartConnect: topology === 'jura_smart_connect',
      isJetinno: topology === 'jetinno_vending',
      isKalerm: topology === 'kalerm_dual',
      isNivona: topology === 'nivona_single',
    };
  }, [caps.topology, protocol, telem.is_dual_heater]);

  const {
    inferredTopology,
    isDual,
    isSmartConnect,
    isJetinno,
    isKalerm,
    isNivona,
  } = topologyConfig;

  const findSw = (id) => (hasTelem ? switches.find((s) => s.id === id) : null);
  const tankSw = findSw('water_inlet') || findSw('water_tank');
  const traySw = findSw('drip_tray');
  const beansSw = findSw('bean_hopper');
  const groundsSw = findSw('grounds_container');
  const brewGroupSw = findSw('brew_group');
  const doorSw = findSw('door_switch') || findSw('cabinet_door');
  const cupSw = findSw('cup_detector');
  const readySw = findSw('machine_ready');

  const tankHas = Boolean(tankSw);
  const tankOk = tankSw ? tankSw.ok !== false : true;
  const tankStatus = tankSw?.status ?? '';
  const tankBadge = tankSw?.badge ?? '';
  const tankDetails = tankSw?.details ?? '';

  const trayHas = Boolean(traySw);
  const trayOk = traySw ? traySw.ok !== false : true;
  const trayStatus = traySw?.status ?? '';
  const trayBadge = traySw?.badge ?? '';

  const beansHas = Boolean(beansSw);
  const beansOkSw = beansSw ? beansSw.ok !== false : null;
  const beansStatus = beansSw?.status ?? '';
  const beansBadge = beansSw?.badge ?? '';
  const beansDetails = beansSw?.details ?? '';

  const groundsHas = Boolean(groundsSw);
  const groundsOk = groundsSw ? groundsSw.ok !== false : true;
  const groundsStatus = groundsSw?.status ?? '';
  const groundsBadge = groundsSw?.badge ?? '';
  const groundsDetails = groundsSw?.details ?? '';

  const brewGroupHas = Boolean(brewGroupSw);
  const brewGroupOk = brewGroupSw ? brewGroupSw.ok !== false : true;
  const brewGroupStatus = brewGroupSw?.status ?? '';
  const brewGroupBadge = brewGroupSw?.badge ?? '';
  const brewGroupDetails = brewGroupSw?.details ?? '';

  const doorHas = Boolean(doorSw);
  const doorOk = doorSw ? doorSw.ok !== false : true;
  const doorStatus = doorSw?.status ?? '';
  const doorBadge = doorSw?.badge ?? '';
  const doorDetails = doorSw?.details ?? '';

  const cupHas = Boolean(cupSw);
  const cupOk = cupSw ? cupSw.ok !== false : true;
  const cupStatus = cupSw?.status ?? '';
  const cupBadge = cupSw?.badge ?? '';
  const cupDetails = cupSw?.details ?? '';

  const readyHas = Boolean(readySw);
  const readyOk = readySw ? readySw.ok !== false : true;
  const readyStatus = readySw?.status ?? '';
  const readyBadge = readySw?.badge ?? '';
  const readyDetails = readySw?.details ?? '';

  const tb1Temp = hasTelem && telem.heater_coffee_c != null ? Number(telem.heater_coffee_c) : null;
  const tb2Temp = hasTelem && telem.heater_steam_c != null ? Number(telem.heater_steam_c) : null;
  const buPos = hasTelem && telem.bu_encoder_pos != null ? telem.bu_encoder_pos : null;
  const buUpper = hasTelem && telem.bu_encoder_upper != null ? telem.bu_encoder_upper : null;
  const buZone = hasTelem && telem.bu_position_state ? telem.bu_position_state : (isCs ? 'Pohotovost / Nenačteno' : 'Standby / Unread');
  const flowRate = hasTelem && telem.flow_rate_ml_s != null ? Number(telem.flow_rate_ml_s) : null;
  const flowVolume = hasTelem && telem.flow_volume_ml != null ? Number(telem.flow_volume_ml) : null;
  const flowPulses = hasTelem && telem.flow_pulses != null ? telem.flow_pulses : null;
  const pressureBar = hasTelem && telem.pump_pressure_bar != null ? Number(telem.pump_pressure_bar) : null;
  const beansOk = hasTelem && telem.beans_ok != null ? telem.beans_ok : null;
  const isLocalBeanDisplay = Boolean(beansSw?.details?.includes('Monitored Locally'));

  const supportsCoffeeTemp = caps.has_coffee_temp !== undefined ? Boolean(caps.has_coffee_temp) : tb1Temp != null;
  const supportsSteamTemp = caps.has_steam_temp !== undefined ? Boolean(caps.has_steam_temp) : tb2Temp != null;
  const supportsFlow = caps.has_flowmeter !== undefined ? Boolean(caps.has_flowmeter) : (!isSmartConnect && hasLiveFrame);
  const supportsBuEncoder = caps.has_bu_encoder !== undefined ? Boolean(caps.has_bu_encoder) : (!isSmartConnect && buPos != null);
  const supportsValve = caps.has_valve_state !== undefined ? Boolean(caps.has_valve_state) : (!isSmartConnect && !isNivona && !isKalerm && !isJetinno && hasLiveFrame);

  const naBadge = isSmartConnect ? 'N/A (@-PROTO)' : (isCs ? 'NEPODPOR.' : 'N/A');
  const noFrameBadge = isCs ? 'BEZ RÁMCE' : 'NO FRAME';

  const NODES = useMemo(() => {
    const makeSwitchNode = (id, label, icon, x, y, hasData, okVal, statusVal, badgeVal, detailsVal, hardware, fallbackDesc) => {
      return {
        id,
        label,
        icon,
        supported: true,
        status: hasData ? txVal(lang, statusVal) : (isCs ? 'POHOTOVOST' : 'STANDBY'),
        primary: hasData ? txVal(lang, badgeVal) : '---',
        details: detailsVal ? txVal(lang, detailsVal) : fallbackDesc,
        hardware,
        badge: hasData ? txVal(lang, badgeVal) : (isCs ? 'POHOT.' : 'STANDBY'),
        ok: hasData ? okVal : true,
        x,
        y,
      };
    };

    const nodes = {};

  nodes.tank = {
    id: 'tank',
    label: isJetinno ? (isCs ? 'PŘÍVOD VODY' : 'MAINS INLET') : (isCs ? 'NÁDRŽKA VODY' : 'WATER TANK'),
    icon: '💧',
    supported: true,
    status: tankHas
      ? (tankOk ? (isCs ? 'V NORMĚ' : 'NOMINAL') : txVal(lang, tankStatus))
      : (isCs ? 'POHOTOVOST' : 'STANDBY'),
    primary: tankHas
      ? (tankOk ? (isJetinno ? (isCs ? 'Tlak OK' : 'Pressure OK') : (isCs ? 'Voda OK' : 'Water OK')) : txVal(lang, tankBadge))
      : '---',
    details: tankDetails
      ? txVal(lang, tankDetails)
      : (isJetinno
          ? (isCs ? 'Tlakový snímač přívodu vody z řadu.' : 'Mains water inlet pressure switch / transducer.')
          : (isCs ? 'Jazýčkový senzor spínaný magnetickým plovákem v nádržce.' : 'Chassis reed sensor actuated by magnetic float in water tank.')),
    hardware: isJetinno
      ? (isCs ? 'Přívod vody z řadu | Tlakový spínač vstupu' : 'Direct mains water line | Inlet pressure safety interlock')
      : (isCs ? 'Jazýčkový kontakt: NO | Blokace: Úroveň 1' : 'Reed switch contact: NO | Safety Lockout: Level 1'),
    badge: tankHas ? txVal(lang, tankBadge) : (isCs ? 'POHOT.' : 'STANDBY'),
    ok: tankHas ? tankOk : true,
    x: 60,
    y: 70,
  };

  if (!isJetinno) {
    nodes.flowmeter = {
      id: 'flowmeter',
      label: isCs ? 'PRŮTOKOMĚR' : 'FLOWMETER',
      icon: '🌊',
      supported: !isSmartConnect,
      status: isSmartConnect
        ? (isCs ? 'NEEXPONOVÁNO (@TF:)' : 'NOT EXPOSED (@TF:)')
        : !hasLiveFrame && hasTelem
        ? (isCs ? 'BEZ ODEZVY' : 'NO FRAME')
        : flowRate != null
        ? (flowRate > 0 ? (isCs ? 'ČERPÁNÍ' : 'PUMPING') : (isCs ? 'NEČINNÝ' : 'IDLE'))
        : (isCs ? 'POHOTOVOST' : 'STANDBY'),
      primary: isSmartConnect
        ? '---'
        : supportsFlow && flowRate != null
        ? `${flowRate.toFixed(1)} ml/s`
        : '--- ml/s',
      details: isSmartConnect
        ? (isCs ? 'Protokol Smart Connect @TF: neposkytuje živé impulzy průtokoměru.' : 'Smart Connect @TF: alert frame does not expose live flowmeter pulses.')
        : flowRate != null
        ? (isCs ? `Průtok turbínkou: ${flowRate.toFixed(2)} ml/s | Objem dávky: ${(flowVolume ?? 0).toFixed(1)} ml (${flowPulses ?? 0} imp.).` : `Turbine flow: ${flowRate.toFixed(2)} ml/s | Cycle volume: ${(flowVolume ?? 0).toFixed(1)} ml (${flowPulses ?? 0} pulses).`)
        : (isCs ? 'Impulzní průtokoměr v pohotovosti.' : 'Impulse turbine flowmeter standby.'),
      hardware: isKalerm
        ? (isCs ? 'Kalerm turbínový průtokoměr (~2,2 imp/ml) | Modbus registr 0x0003' : 'Kalerm impulse turbine (~2.2 pulses/ml) | Modbus input reg 0x0003')
        : (isCs ? 'Digmesa Hallův průtokoměr (~2,37 imp/ml)' : 'Digmesa Hall-effect impulse flowmeter (~2.37 pulses/ml)'),
      badge: isSmartConnect
        ? naBadge
        : !hasLiveFrame && hasTelem
        ? noFrameBadge
        : flowRate != null
        ? (flowRate > 0 ? (isCs ? 'AKTIVNÍ' : 'ACTIVE') : (isCs ? 'KLID' : 'IDLE'))
        : (isCs ? 'POHOT.' : 'STANDBY'),
      ok: isSmartConnect ? true : (hasLiveFrame || !hasTelem),
      x: 185,
      y: 70,
    };
  }

  nodes.pump = {
    id: 'pump',
    label: isJetinno ? (isCs ? 'ČERPADLO / TLAK' : 'BREW PUMP') : (isCs ? 'ČERPADLO' : 'PUMP'),
    icon: '⚡',
    supported: isJetinno ? (pressureBar != null || !hasTelem) : !isSmartConnect,
    status: isSmartConnect
      ? (isCs ? 'NEEXPONOVÁNO (@TF:)' : 'NOT EXPOSED (@TF:)')
      : isJetinno
      ? (pressureBar != null ? (isCs ? 'TLAK MĚŘEN' : 'MONITORED') : (hasTelem ? (isCs ? 'BEZ ODEZVY' : 'NO FRAME') : (isCs ? 'POHOTOVOST' : 'STANDBY')))
      : !hasLiveFrame && hasTelem
      ? (isCs ? 'BEZ ODEZVY' : 'NO FRAME')
      : flowRate != null
      ? (flowRate > 0 ? (isCs ? 'POD NAPĚTÍM' : 'ENERGIZED') : (isCs ? 'POHOTOVOST' : 'STANDBY'))
      : (isCs ? 'POHOTOVOST' : 'STANDBY'),
    primary: isSmartConnect
      ? '---'
      : isJetinno
      ? (pressureBar != null ? `${pressureBar.toFixed(1)} bar` : '--- bar')
      : flowRate != null
      ? (flowRate > 0 ? (isCs ? 'AKTIVNÍ' : 'ACTIVE') : (isCs ? 'KLID' : 'IDLE'))
      : '---',
    details: isSmartConnect
      ? (isCs ? 'Stav čerpadla není dostupný v rámci @TF:.' : 'Pump actuation state is not exposed in @TF: status frames.')
      : isJetinno
      ? (isCs ? 'Piezoelektrický převodník tlaku výdeje espressa.' : 'Piezoelectric brew pressure transducer on high-pressure pump circuit.')
      : (isCs ? 'Vibrační / rotační čerpadlo řízené triakem z hlavní desky.' : 'Triac-switched brew pump driven by main logic board.'),
    hardware: isJetinno
      ? (isCs ? 'Tlakový převodník 0–15 bar | Jetinno IO' : '0–15 bar piezoelectric pressure transducer | Jetinno IO')
      : (isCs ? '230V AC čerpadlo | Fázové řízení triakem' : '230V AC pump | Triac phase-angle drive'),
    badge: isSmartConnect
      ? naBadge
      : isJetinno
      ? (pressureBar != null ? `${pressureBar.toFixed(1)} BAR` : (hasTelem ? noFrameBadge : (isCs ? 'POHOT.' : 'STANDBY')))
      : !hasLiveFrame && hasTelem
      ? noFrameBadge
      : flowRate != null
      ? (flowRate > 0 ? (isCs ? 'ČERPÁ' : 'PUMPING') : (isCs ? 'KLID' : 'IDLE'))
      : (isCs ? 'POHOT.' : 'STANDBY'),
    ok: isSmartConnect ? true : (hasLiveFrame || !hasTelem),
    x: isJetinno ? 185 : 310,
    y: 70,
  };

  nodes.tb1 = {
    id: 'tb1',
    label: isJetinno ? (isCs ? 'ESPRESSO BOJLER' : 'ESPRESSO BOILER') : (isCs ? 'TOPNÝ BLOK TB1' : 'COFFEE HEATER TB1'),
    icon: '☕',
    supported: !isSmartConnect,
    status: isSmartConnect
      ? (isCs ? 'NEEXPONOVÁNO (@TF:)' : 'NOT EXPOSED (@TF:)')
      : tb1Temp != null
      ? (tb1Temp >= 80 && tb1Temp <= 115
          ? (isCs ? 'PŘIPRAVEN' : 'READY')
          : (tb1Temp > 115 ? (isCs ? 'PŘEHŘÁTÍ' : 'OVERHEAT') : (isCs ? 'NAHŘÍVÁ SE' : 'HEATING')))
      : hasTelem
      ? (isCs ? 'BEZ ODEZVY' : 'NO FRAME')
      : (isCs ? 'POHOTOVOST' : 'STANDBY'),
    primary: isSmartConnect
      ? '--- °C'
      : tb1Temp != null
      ? `${tb1Temp.toFixed(1)} °C`
      : '--- °C',
    details: isSmartConnect
      ? (isCs ? 'Smart Connect @TF: hlásí pouze výstrahy, nikoliv přesnou teplotu NTC.' : 'Smart Connect @TF: exposes alerts only; numeric NTC temperature is not reported.')
      : tb1Temp != null
      ? (isCs ? 'Hlavní kávový ohřívač s PID regulací (pracovní pásmo 80–115 °C).' : 'Primary coffee thermoblock/boiler under PID control (ready band 80–115°C).')
      : (isCs ? 'Čekám na teplotu hlavního ohřívače.' : 'Awaiting primary heater temperature sample.'),
    hardware: telem.heater_ntc_raw
      ? `NTC ADC raw: 0x${Number(telem.heater_ntc_raw).toString(16).toUpperCase().padStart(4, '0')} (${telem.heater_ntc_raw}) | PID`
      : (isJetinno
          ? (isCs ? 'Mosazný vysokotlaký bojler + NTC' : 'High-pressure brass espresso boiler + NTC')
          : (isCs ? 'Kávový termoblok + NTC senzor' : 'Primary coffee thermoblock + NTC thermistor')),
    badge: isSmartConnect
      ? naBadge
      : tb1Temp != null
      ? (tb1Temp >= 80 && tb1Temp <= 115
          ? (isCs ? 'PŘIPRAV.' : 'READY')
          : (tb1Temp > 115 ? (isCs ? 'PŘEHŘÁTÍ' : 'OVERHEAT') : (isCs ? 'OHŘEV' : 'HEATING')))
      : hasTelem
      ? noFrameBadge
      : (isCs ? 'POHOT.' : 'STANDBY'),
    ok: isSmartConnect ? true : (tb1Temp != null ? tb1Temp <= 115 : !hasTelem),
    x: isJetinno ? 320 : 435,
    y: 70,
  };

  if (isDual) {
    nodes.tb2 = {
      id: 'tb2',
      label: isJetinno ? (isCs ? 'INSTANT BOJLER' : 'INSTANT BOILER') : (isCs ? 'PARNÍ BLOK TB2' : 'STEAM HEATER TB2'),
      icon: '♨️',
      supported: supportsSteamTemp || !hasTelem,
      status: tb2Temp != null
        ? (isJetinno
            ? (tb2Temp >= 75 && tb2Temp <= 102 ? (isCs ? 'PŘIPRAVEN' : 'READY') : (tb2Temp > 102 ? (isCs ? 'PŘEHŘÁTÍ' : 'OVERHEAT') : (isCs ? 'NAHŘÍVÁ SE' : 'HEATING')))
            : (tb2Temp >= 105 && tb2Temp <= 155 ? (isCs ? 'PŘIPRAVEN' : 'READY') : (tb2Temp > 155 ? (isCs ? 'PŘEHŘÁTÍ' : 'OVERHEAT') : (isCs ? 'NAHŘÍVÁ SE' : 'HEATING'))))
        : hasTelem
        ? (isCs ? 'BEZ ODEZVY' : 'NO FRAME')
        : (isCs ? 'POHOTOVOST' : 'STANDBY'),
      primary: tb2Temp != null ? `${tb2Temp.toFixed(1)} °C` : '--- °C',
      details: isJetinno
        ? (isCs ? 'Atmosférický bojler pro instantní / rozpustné nápoje.' : 'Atmospheric hot-water boiler serving instant/soluble beverage mixers.')
        : (isCs ? 'Dedikovaný druhý termoblok / parní generátor pro páru a mléčnou pěnu.' : 'Dedicated secondary thermoblock / steam boiler for milk & steam circuits.'),
      hardware: telem.heater_steam_raw
        ? `Steam NTC ADC raw: 0x${Number(telem.heater_steam_raw).toString(16).toUpperCase().padStart(4, '0')} (${telem.heater_steam_raw})`
        : (isCs ? 'Sekundární parní/horkovodní ohřívač + NTC' : 'Secondary steam/hot-water heater + NTC sensor'),
      badge: tb2Temp != null
        ? (tb2Temp > 155 ? (isCs ? 'PŘEHŘÁTÍ' : 'OVERHEAT') : (tb2Temp >= (isJetinno ? 75 : 105) ? (isCs ? 'PŘIPRAV.' : 'READY') : (isCs ? 'OHŘEV' : 'HEATING')))
        : hasTelem
        ? noFrameBadge
        : (isCs ? 'POHOT.' : 'STANDBY'),
      ok: tb2Temp != null ? tb2Temp <= 155 : !hasTelem,
      x: isJetinno ? 455 : 565,
      y: 70,
    };
  } else if (!isNivona) {
    // Single-heater Jura / Smart Connect shows Multiway Valve on top-right
    nodes.valve = {
      id: 'valve',
      label: isCs ? 'VENTIL' : 'MULTIWAY VALVE',
      icon: '🔀',
      supported: supportsValve || (!isSmartConnect && !hasTelem),
      status: isSmartConnect
        ? (isCs ? 'NEEXPONOVÁNO (@TF:)' : 'NOT EXPOSED (@TF:)')
        : !hasLiveFrame && hasTelem
        ? (isCs ? 'BEZ ODEZVY' : 'NO FRAME')
        : telem.mv_busy
        ? (isCs ? 'POLOHOVÁNÍ' : 'POSITIONING')
        : (hasTelem ? (isCs ? 'VÝCHOZÍ / PŘIPRAVEN' : 'HOMED / READY') : (isCs ? 'POHOTOVOST' : 'STANDBY')),
      primary: isSmartConnect
        ? '---'
        : !hasLiveFrame && hasTelem
        ? '---'
        : hasTelem
        ? (telem.mv_busy ? (isCs ? 'Otáčí se' : 'Moving') : (isCs ? 'Výchozí' : 'Homed'))
        : '---',
      details: isSmartConnect
        ? (isCs ? 'Poloha keramického ventilu není dostupná v rámci @TF:.' : 'Ceramic multiway valve position is not reported in @TF: frames.')
        : (isCs ? 'Keramický vícecestný rozdělovač vody (káva, proplach, pára).' : 'Ceramic multiway distributor valve (Coffee, Rinse, Steam/Bypass).'),
      hardware: isCs ? 'DC motorek + mikrospínače zpětné vazby (HZ[0][2,6])' : 'DC motor + position microswitch feedback (HZ[0][2,6])',
      badge: isSmartConnect
        ? naBadge
        : !hasLiveFrame && hasTelem
        ? noFrameBadge
        : hasTelem
        ? (telem.mv_busy ? (isCs ? 'PRACUJE' : 'BUSY') : (isCs ? 'PŘIPRAV.' : 'READY'))
        : (isCs ? 'POHOT.' : 'STANDBY'),
      ok: isSmartConnect ? true : (hasLiveFrame ? telem.mv_init_ok !== false : !hasTelem),
      x: 565,
      y: 70,
    };
  }

  // Bottom Row Nodes — adapted per device topology
  if (isJetinno) {
    nodes.door = makeSwitchNode(
      'door',
      isCs ? 'DVEŘE SKŘÍNĚ' : 'CABINET DOOR',
      '🚪',
      60,
      195,
      doorHas,
      doorOk,
      doorStatus,
      doorBadge,
      doorDetails,
      isCs ? 'Bezpečnostní mikrospínač dveří (STUM IO)' : 'Chassis safety interlock switch (STUM IO)',
      isCs ? 'Snímač zavření servisních dveří automatu.' : 'Service cabinet door interlock monitor.'
    );
    nodes.cup = makeSwitchNode(
      'cup',
      isCs ? 'SENZOR KELÍMKU' : 'CUP SENSOR',
      '🥤',
      185,
      195,
      cupHas,
      cupOk,
      cupStatus,
      cupBadge,
      cupDetails,
      isCs ? 'Optická závora výdejní zóny' : 'Optical IR beam in dispense bay',
      isCs ? 'Detekce přítomnosti kelímku ve výdejním prostoru.' : 'Infrared cup presence detection in dispense area.'
    );
    nodes.grounds = makeSwitchNode(
      'grounds',
      isCs ? 'ODPAD KÁVY' : 'PUCK BIN',
      '🗑️',
      320,
      195,
      groundsHas,
      groundsOk,
      groundsStatus,
      groundsBadge,
      groundsDetails,
      isCs ? 'Počitadlo + optická kontrola odpadního koše' : 'Grounds capacity counter & optical switch',
      isCs ? 'Kontrola zaplnění zásobníku na kávovou sedlinu.' : 'Spent coffee puck bin level monitor.'
    );
    nodes.tray = makeSwitchNode(
      'tray',
      isCs ? 'ODPADNÍ MISKA' : 'WASTE TRAY',
      '📥',
      455,
      195,
      trayHas,
      trayOk,
      trayStatus,
      trayBadge,
      '',
      isCs ? 'Hladinová elektroda odpadní vody' : 'Liquid level electrode probe',
      isCs ? 'Kontrola hladiny odpadní vody v odkapní misce.' : 'Wastewater tray overflow probe.'
    );
    nodes.state = makeSwitchNode(
      'state',
      isCs ? 'STAV STROJE' : 'MACHINE STATE',
      '✅',
      585,
      195,
      readyHas,
      readyOk,
      readyStatus,
      readyBadge,
      readyDetails,
      isCs ? 'Celkové vyhodnocení IO kontroléru Jetinno' : 'Jetinno IO controller readiness synthesis',
      isCs ? 'Souhrnný provozní stav automatu.' : 'Overall vending controller readiness.'
    );
  } else if (isKalerm) {
    nodes.door = makeSwitchNode(
      'door',
      isCs ? 'SERVISNÍ DVEŘE' : 'SERVICE DOOR',
      '🚪',
      60,
      195,
      doorHas,
      doorOk,
      doorStatus,
      doorBadge,
      doorDetails,
      isCs ? 'Přední bezpečnostní mikrospínač (Modbus bit 7)' : 'Front chassis interlock (Modbus bit 7)',
      isCs ? 'Snímač zavření předních servisních dveří.' : 'Maintenance door interlock switch.'
    );
    nodes.beans = makeSwitchNode(
      'beans',
      isCs ? 'ZÁSOBNÍK ZRN' : 'BEAN HOPPER',
      '🫘',
      185,
      195,
      beansHas,
      beansOkSw !== false,
      beansStatus,
      beansBadge,
      beansDetails,
      isCs ? 'Optický IR senzor v násypce (Modbus bit 5)' : 'Infrared optical beam in bean hopper (Modbus bit 5)',
      isCs ? 'Detekce přítomnosti kávových zrn.' : 'Optical bean hopper level detection.'
    );
    nodes.bu = makeSwitchNode(
      'bu',
      isCs ? 'SPAŘ. JEDN.' : 'BREW GROUP',
      '⚙️',
      310,
      195,
      brewGroupHas,
      brewGroupOk,
      brewGroupStatus,
      brewGroupBadge,
      brewGroupDetails,
      isCs ? 'Optický enkodér + vačkový mikrospínač (Modbus bit 3)' : 'Optical encoder + cam home switch (Modbus bit 3)',
      isCs ? 'Poloha spařovací jednotky Kalerm.' : 'Kalerm brew group home/active position.'
    );
    nodes.grounds = makeSwitchNode(
      'grounds',
      isCs ? 'ODPAD KÁVY' : 'GROUNDS BOX',
      '🗑️',
      435,
      195,
      groundsHas,
      groundsOk,
      groundsStatus,
      groundsBadge,
      groundsDetails,
      isCs ? 'Mikrospínač zásobníku sedliny (Modbus bit 2)' : 'Used puck container microswitch (Modbus bit 2)',
      isCs ? 'Kontrola vložení a naplnění zásobníku sedliny.' : 'Grounds box presence & fill state.'
    );
    nodes.tray = makeSwitchNode(
      'tray',
      isCs ? 'ODKAPNÍ MISKA' : 'DRIP TRAY',
      '📥',
      565,
      195,
      trayHas,
      trayOk,
      trayStatus,
      trayBadge,
      '',
      isCs ? 'Kontaktní spínač odkapní misky (Modbus bit 1)' : 'Waste basin contact switch (Modbus bit 1)',
      isCs ? 'Kontrola zasunutí odkapní misky.' : 'Drip tray insertion switch.'
    );
  } else if (isNivona) {
    nodes.bu = makeSwitchNode(
      'bu',
      isCs ? 'SPAŘ. JEDN.' : 'BREW GROUP',
      '⚙️',
      185,
      195,
      brewGroupHas,
      brewGroupOk,
      brewGroupStatus,
      brewGroupBadge,
      brewGroupDetails,
      isCs ? 'Mikrospínač vyjímatelné spařovací jednotky' : 'Removable brew unit presence interlock',
      isCs ? 'Kontrola usazení a zamčení spařovací jednotky.' : 'Removable brew group lock switch.'
    );
    nodes.grounds = makeSwitchNode(
      'grounds',
      isCs ? 'ODPAD KÁVY' : 'GROUNDS DRAWER',
      '🗑️',
      310,
      195,
      groundsHas,
      groundsOk,
      groundsStatus,
      groundsBadge,
      groundsDetails,
      isCs ? 'Mikrospínač nádobky na sedlinu' : 'Used puck drawer microswitch',
      isCs ? 'Kontrola vložení nádobky na kávovou sedlinu.' : 'Coffee grounds drawer switch.'
    );
    nodes.tray = makeSwitchNode(
      'tray',
      isCs ? 'ODKAPNÍ MISKA' : 'DRIP TRAY',
      '📥',
      435,
      195,
      trayHas,
      trayOk,
      trayStatus,
      trayBadge,
      '',
      isCs ? 'Vodivostní kontakty misky' : 'Conductive drip tray contacts',
      isCs ? 'Kontrola přítomnosti odkapní misky.' : 'Drip tray contact sensor.'
    );
  } else {
    // Jura Single, Jura Dual, and Jura Smart Connect
    nodes.beans = {
      id: 'beans',
      label: isCs ? 'ZÁSOBNÍK ZRN' : 'BEAN HOPPER',
      icon: '🫘',
      supported: true,
      status: isLocalBeanDisplay
        ? (isCs ? 'Hlídáno lokálně displejem (EF518D)' : 'Monitored Locally by Display MCU (EF518D)')
        : beansStatus
        ? txVal(lang, beansStatus)
        : beansOk != null
        ? (beansOk ? (isCs ? 'ZRNA OK' : 'BEANS OK') : (isCs ? 'DOPLNIT ZRNA' : 'FILL BEANS'))
        : (isCs ? 'POHOTOVOST' : 'STANDBY'),
      primary: isLocalBeanDisplay
        ? (isCs ? 'LOKÁLNĚ' : 'LOCAL (EF518D)')
        : beansBadge
        ? txVal(lang, beansBadge)
        : beansOk != null
        ? (beansOk ? (isCs ? 'PLNÝ' : 'CHARGED') : (isCs ? 'PRÁZDNÝ' : 'EMPTY'))
        : '---',
      details: beansDetails
        ? txVal(lang, beansDetails)
        : (isCs ? 'Stav zrn dle telemetrie kávovaru nebo lokálního displeje.' : 'Bean presence via telemetry status, puck thickness fallback, or local display MCU.'),
      hardware: isLocalBeanDisplay
        ? (isCs ? 'Čelní displej (EF518D / Renesas R8C) — lokální fototranzistor' : 'Front Display MCU (EF518D / Renesas R8C) Local Phototransistor')
        : isSmartConnect
        ? (isCs ? 'Stavový bit Smart Connect @TF:' : 'Smart Connect @TF: alert bitmask')
        : (isCs ? 'Detektor zrn / kontrola tloušťky puku (HZ[8])' : 'Bean charge status / puck compression check (HZ[8])'),
      badge: isLocalBeanDisplay
        ? (isCs ? 'LOKÁLNĚ' : 'LOCAL')
        : beansBadge
        ? txVal(lang, beansBadge)
        : beansOk != null
        ? (beansOk ? (isCs ? 'PLNÝ' : 'CHARGED') : (isCs ? 'PRÁZDNÝ' : 'EMPTY'))
        : (isCs ? 'POHOT.' : 'STANDBY'),
      ok: beansHas ? beansOkSw : (beansOk !== false),
      x: 185,
      y: 195,
    };

    nodes.bu = {
      id: 'bu',
      label: isCs ? 'SPAŘ. JEDN.' : 'BREW UNIT',
      icon: '⚙️',
      supported: !isSmartConnect,
      status: isSmartConnect
        ? (isCs ? 'NEEXPONOVÁNO (@TF:)' : 'NOT EXPOSED (@TF:)')
        : !hasLiveFrame && hasTelem
        ? (isCs ? 'BEZ ODEZVY' : 'NO FRAME')
        : buPos != null
        ? (buPos === 0 ? (isCs ? 'INICIALIZACE' : 'INITIALIZING') : (isCs ? 'SYNCHRONIZOVÁNA' : 'SYNCHRONIZED'))
        : (isCs ? 'POHOTOVOST' : 'STANDBY'),
      primary: isSmartConnect
        ? '---'
        : supportsBuEncoder && buPos != null
        ? `${buPos} / ${buUpper ?? '---'}`
        : '--- / ---',
      details: isSmartConnect
        ? (isCs ? 'Smart Connect @TF: neposkytuje polohu enkodéru spařovací jednotky.' : 'Smart Connect @TF: does not expose brew unit encoder ticks.')
        : (isCs ? `Mechanický zdvih: ${buZone} (${telem.bu_stroke_pct ?? 0} % dráhy).` : `Mechanical stroke: ${buZone} (${telem.bu_stroke_pct ?? 0}% travel).`),
      hardware: telem.bu_mill_target
        ? `Optical encoder | Mill Target (RE:0041): ${telem.bu_mill_target} ticks`
        : (isCs ? '12V DC motor + optický enkodér s clonkou' : '12V DC drive motor + quadrature optical encoder'),
      badge: isSmartConnect
        ? naBadge
        : !hasLiveFrame && hasTelem
        ? noFrameBadge
        : buPos != null
        ? `${buPos} tk`
        : '--- tk',
      ok: isSmartConnect ? true : (hasLiveFrame ? telem.bu_init_ok !== false : !hasTelem),
      x: 310,
      y: 195,
    };

    nodes.tray = {
      id: 'tray',
      label: isCs ? 'ODKAPNÍ MISKA' : 'DRIP TRAY',
      icon: '📥',
      supported: true,
      status: trayHas ? txVal(lang, trayStatus) : (isCs ? 'POHOTOVOST' : 'STANDBY'),
      primary: trayHas ? (trayOk ? (isCs ? 'Vložena' : 'Present') : (isCs ? 'Chybí' : 'Missing')) : '---',
      details: isCs ? 'Kontaktní pružinky snímající zasunutí odkapní misky / zásobníku sedliny.' : 'Rear chassis leaf contacts detecting drip tray & grounds drawer insertion.',
      hardware: isCs ? 'Mechanický mikrospínač | Bezpečnostní blokace pohonu' : 'Mechanical leaf contacts | Safety Interlock: immediate drive inhibit',
      badge: trayHas ? txVal(lang, trayBadge) : (isCs ? 'POHOT.' : 'STANDBY'),
      ok: trayHas ? trayOk : true,
      x: 435,
      y: 195,
    };

    nodes.state = makeSwitchNode(
      'state',
      isCs ? 'STAV STROJE' : 'MACHINE STATE',
      '☕',
      565,
      195,
      readyHas,
      readyOk,
      readyStatus,
      readyBadge,
      readyDetails,
      isSmartConnect
        ? (isCs ? 'Vyhodnocení z aktivních výstrah @TF:' : 'Synthesized from Smart Connect @TF: active alerts')
        : (isCs ? 'Vyhodnocení z 5 fyzických vstupů HZ:' : 'Synthesized from 5 live physical HZ: inputs'),
      isCs ? 'Souhrnný stav připravenosti kávovaru k výdeji.' : 'Overall live machine readiness status.'
    );
  }

    return nodes;
  }, [
    lang,
    isCs,
    isJetinno,
    isKalerm,
    isNivona,
    isDual,
    isSmartConnect,
    hasTelem,
    hasLiveFrame,
    tankHas,
    tankOk,
    tankStatus,
    tankBadge,
    tankDetails,
    trayHas,
    trayOk,
    trayStatus,
    trayBadge,
    beansHas,
    beansOkSw,
    beansStatus,
    beansBadge,
    beansDetails,
    groundsHas,
    groundsOk,
    groundsStatus,
    groundsBadge,
    groundsDetails,
    brewGroupHas,
    brewGroupOk,
    brewGroupStatus,
    brewGroupBadge,
    brewGroupDetails,
    doorHas,
    doorOk,
    doorStatus,
    doorBadge,
    doorDetails,
    cupHas,
    cupOk,
    cupStatus,
    cupBadge,
    cupDetails,
    readyHas,
    readyOk,
    readyStatus,
    readyBadge,
    readyDetails,
    flowRate,
    flowVolume,
    flowPulses,
    pressureBar,
    tb1Temp,
    tb2Temp,
    buPos,
    buUpper,
    buZone,
    beansOk,
    isLocalBeanDisplay,
    supportsFlow,
    supportsSteamTemp,
    supportsValve,
    supportsBuEncoder,
    naBadge,
    noFrameBadge,
    telem.heater_ntc_raw,
    telem.heater_steam_raw,
    telem.mv_busy,
    telem.mv_init_ok,
    telem.bu_stroke_pct,
    telem.bu_mill_target,
    telem.bu_init_ok,
  ]);

  // Keep selectedNodeId valid when switching between different machine topologies
  useEffect(() => {
    if (!NODES[selectedNodeId]) {
      setSelectedNodeId(NODES.tb1 ? 'tb1' : Object.keys(NODES)[0]);
    }
  }, [inferredTopology, selectedNodeId, NODES]);

  const selectedNode = NODES[selectedNodeId] || NODES.tb1 || Object.values(NODES)[0];

  const topologyLabel = (() => {
    switch (inferredTopology) {
      case 'jura_dual':
        return isCs ? 'JURA DUAL-HEATER' : 'JURA DUAL-HEATER';
      case 'jura_smart_connect':
        return 'JURA SMART CONNECT (@TF:)';
      case 'nivona_single':
        return 'NIVONA ASCII';
      case 'kalerm_dual':
        return 'KALERM MODBUS DUAL';
      case 'jetinno_vending':
        return 'JETINNO VENDING IO';
      default:
        return 'JURA SINGLE-HEATER';
    }
  })();

  const headerStatus = !hasTelem
    ? { label: isCs ? 'POHOTOVOST' : 'STANDBY', cls: 'text-zinc-400' }
    : hasLiveFrame
    ? { label: `LIVE · ${topologyLabel}`, cls: 'text-emerald-400' }
    : { label: `${isCs ? 'BEZ ŽIVÉHO RÁMCE' : 'NO LIVE FRAME'} · ${topologyLabel}`, cls: 'text-amber-400' };

  const operatingNote = (() => {
    if (!selectedNode) return '';
    if (selectedNode.supported === false) {
      return isCs
        ? 'Tato komponenta není reportována aktivním protokolem tohoto zařízení.'
        : 'This component is not exposed by the active machine protocol.';
    }
    if (!hasTelem) {
      return isCs
        ? 'Čekám na první živý telemetrický rámec z připojeného kávovaru.'
        : 'Awaiting live telemetry frame from connected appliance.';
    }
    if (!hasLiveFrame) {
      return isCs
        ? 'Zařízení neodpovědělo na dotaz živých senzorů — hodnoty nelze ověřit.'
        : 'Appliance did not reply to live sensor poll — state cannot be verified.';
    }
    if (selectedNode.ok === false) {
      return isCs
        ? 'Detekována výstraha nebo rozpojená blokace — zkontrolujte komponentu či registr.'
        : 'Warning or safety interlock active — inspect component or fault register.';
    }
    return isCs
      ? 'Živá telemetrie komponenty je v normálním rozsahu.'
      : 'Live component telemetry is within nominal operating bounds.';
  })();

  return (
    <div className="space-y-3">
      {/* 1. INTERACTIVE DIGITAL TWIN SCHEMATIC CANVAS */}
      <div className={`p-4 border rounded ${theme.surfaceClass}`}>
        <div className="flex flex-wrap items-center justify-between gap-2 mb-2">
          <div className="flex items-center space-x-2">
            <span className="text-base font-bold text-gray-300 flex items-center space-x-1.5">
              <span>{isCs ? 'HYDRAULICKÉ A MECHANICKÉ SCHÉMA (DIGITÁLNÍ DVOJČE)' : 'HYDRAULIC & ELECTROMECHANICAL DIGITAL TWIN'}</span>
            </span>
            <span className="text-[10px] text-gray-500 font-mono">
              {isCs ? '(KLIKNUTÍM NA SOUČÁSTKU ZOBRAZÍTE DETAIL)' : '(CLICK ANY COMPONENT TO INSPECT)'}
            </span>
          </div>
          <span className={`text-[11px] font-mono font-bold ${headerStatus.cls}`}>
            {headerStatus.label}
          </span>
        </div>

        {/* Schematic Flow Container */}
        <div className="relative w-full h-[270px] bg-black/40 border border-gray-800/80 rounded-lg p-2 overflow-x-auto select-none">
          <svg className="w-[660px] h-full mx-auto" viewBox="0 0 660 265">
            {/* Upper hydraulic path lines adapted to active topology */}
            {!isJetinno ? (
              <>
                <path
                  d="M 110 85 L 140 85"
                  stroke="#38BDF8"
                  strokeWidth="2.5"
                  strokeDasharray={flowRate > 0 ? '4,4' : 'none'}
                  className={flowRate > 0 ? 'animate-pulse' : ''}
                />
                <path
                  d="M 235 85 L 265 85"
                  stroke="#38BDF8"
                  strokeWidth="2.5"
                  strokeDasharray={flowRate > 0 ? '4,4' : 'none'}
                />
                <path d="M 360 85 L 390 85" stroke="#F43F5E" strokeWidth="2.5" />
                {(NODES.valve || NODES.tb2) && (
                  <path
                    d="M 485 85 L 520 85"
                    stroke={NODES.tb2 ? '#FB923C' : '#F43F5E'}
                    strokeWidth="2.5"
                    strokeDasharray={NODES.tb2 ? '4,2' : 'none'}
                  />
                )}
              </>
            ) : (
              <>
                <path d="M 110 85 L 140 85" stroke="#38BDF8" strokeWidth="2.5" />
                <path d="M 235 85 L 275 85" stroke="#F43F5E" strokeWidth="2.5" />
                <path d="M 370 85 L 410 85" stroke="#FB923C" strokeWidth="2.5" strokeDasharray="4,2" />
              </>
            )}

            {/* Downward brew/waste connection */}
            {NODES.bu && NODES.tb1 && (
              <path
                d={`M ${NODES.tb1.x} 116 L ${NODES.tb1.x} 142 L ${NODES.bu.x} 142 L ${NODES.bu.x} 165`}
                stroke="#A855F7"
                strokeWidth="2"
                fill="none"
                strokeDasharray="3,3"
              />
            )}

            {/* Grinder -> Brew Unit */}
            {NODES.beans && NODES.bu && (
              <path
                d={`M ${NODES.beans.x + 50} 195 L ${NODES.bu.x - 45} 195`}
                stroke="#F59E0B"
                strokeWidth="2"
                strokeDasharray="3,3"
              />
            )}

            {/* Brew Unit -> Grounds / Tray */}
            {NODES.bu && NODES.tray && (
              <path
                d={`M ${NODES.bu.x + 50} 195 L ${NODES.tray.x - 45} 195`}
                stroke="#64748B"
                strokeWidth="2"
                strokeDasharray="4,4"
              />
            )}

            {/* Render Nodes */}
            {Object.values(NODES).map((node) => {
              const isSelected = node.id === selectedNode?.id;
              const isUnsupported = node.supported === false;
              const badgeBg = isUnsupported
                ? 'rgba(113, 113, 122, 0.2)'
                : node.ok
                ? 'rgba(16, 185, 129, 0.15)'
                : 'rgba(239, 68, 68, 0.22)';
              const badgeFg = isUnsupported
                ? '#A1A1AA'
                : node.ok
                ? '#34D399'
                : '#F87171';
              return (
                <g
                  key={node.id}
                  onClick={() => setSelectedNodeId(node.id)}
                  className="cursor-pointer group"
                  transform={`translate(${node.x - 47}, ${node.y - 30})`}
                  opacity={isUnsupported ? 0.65 : 1}
                >
                  <rect
                    width="96"
                    height="62"
                    rx="6"
                    strokeDasharray={isUnsupported ? '3,3' : 'none'}
                    className={`transition-all duration-150 ${
                      isSelected
                        ? 'fill-slate-900 stroke-2'
                        : 'fill-black/80 stroke hover:fill-slate-900/80'
                    }`}
                    stroke={
                      isSelected
                        ? theme.primary
                        : isUnsupported
                        ? '#52525B'
                        : node.ok
                        ? '#334155'
                        : '#EF4444'
                    }
                  />

                  <text x="7" y="18" fontSize="13">
                    {node.icon}
                  </text>
                  <text
                    x="25"
                    y="17"
                    fontSize="7.5"
                    fontWeight="bold"
                    fontFamily="monospace"
                    fill={isSelected ? (theme.primary || '#FF4F00') : '#CBD5E1'}
                  >
                    {node.label.length > 12 ? node.label.slice(0, 11) + '..' : node.label}
                  </text>

                  <text
                    x="8"
                    y="36"
                    fontSize="10.5"
                    fontWeight="bold"
                    fontFamily="monospace"
                    fill={isUnsupported ? '#94A3B8' : node.ok ? '#F8FAFC' : '#F87171'}
                  >
                    {String(node.primary).length > 12 ? String(node.primary).slice(0, 11) + '..' : node.primary}
                  </text>

                  <rect
                    x="7"
                    y="43"
                    width="82"
                    height="13"
                    rx="3"
                    fill={badgeBg}
                  />
                  <text
                    x="48"
                    y="52"
                    fontSize="7"
                    fontWeight="bold"
                    fontFamily="monospace"
                    textAnchor="middle"
                    fill={badgeFg}
                  >
                    {String(node.badge).length > 13 ? String(node.badge).slice(0, 12) + '..' : node.badge}
                  </text>
                </g>
              );
            })}
          </svg>
        </div>
      </div>

      {/* 2. SELECTED COMPONENT DEEP TELEMETRY INSPECTOR */}
      {selectedNode && (
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
            <span
              className={`text-xs px-2.5 py-1 rounded font-bold font-mono ${
                selectedNode.supported === false
                  ? 'bg-zinc-900 text-zinc-400 border border-zinc-700'
                  : selectedNode.ok
                  ? 'bg-emerald-950 text-emerald-300 border border-emerald-600'
                  : 'bg-rose-950 text-rose-300 border border-rose-600'
              }`}
            >
              {selectedNode.status}
            </span>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-3 text-xs">
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

            <div className="p-3 bg-black/40 border border-gray-800 rounded">
              <div className="text-[10px] text-gray-500 font-bold uppercase tracking-wider mb-1">
                {isCs ? 'PROVOZNÍ STAV' : 'OPERATING STATUS'}
              </div>
              <div
                className={`text-sm font-bold font-mono ${
                  selectedNode.supported === false
                    ? 'text-zinc-400'
                    : selectedNode.ok
                    ? 'text-emerald-400'
                    : 'text-rose-400'
                }`}
              >
                {selectedNode.status}
              </div>
              <div className="text-[11px] text-gray-400 mt-1">
                {operatingNote}
              </div>
            </div>

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
      )}
    </div>
  );
}

export default React.memo(DigitalTwinSchematic);
