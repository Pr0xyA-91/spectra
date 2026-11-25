import { useState, useEffect, useRef, useCallback } from 'react';
import { createTranslator } from '../../i18n/translations';
import { parseJsonResponse } from '../../utils/fetchSafe';

export function useHardwareTelemetry({ lang, langRef }) {
  const [availablePorts, setAvailablePorts] = useState([]);
  const [selectedPort, setSelectedPort] = useState('');
  const [isConnected, setIsConnected] = useState(false);
  const [isPolling, setIsPolling] = useState(true);
  const [isInterrogating, setIsInterrogating] = useState(false);
  const [hardwareError, setHardwareError] = useState(null);
  const [connectionStatusText, setConnectionStatusText] = useState(() => createTranslator(lang)('detectingPorts'));
  const [lastTimestamp, setLastTimestamp] = useState('---');

  const [liveData, setLiveData] = useState({
    switches: [],
    sensors: [],
    telemetry: {},
    alerts: [],
  });

  const [statsData, setStatsData] = useState(null);
  const [interrogationProgress, setInterrogationProgress] = useState(0);
  const [interrogationStage, setInterrogationStage] = useState('');

  // Optical Bean Calibration State
  const [, setBeanThreshold] = useState(115);
  const [, setBeanHysteresis] = useState(5);

  // Real-Time Bus Event Stream & Safety Log
  const [busEvents, setBusEvents] = useState([]);
  const [isStreamPaused, setIsStreamPaused] = useState(false);

  // UART Command Injector
  const [txCommand, setTxCommand] = useState('HZ:');
  const [, setTxSuccessFlash] = useState(false);
  const [txResponseHistory, setTxResponseHistory] = useState([]);

  // In-flight guard, active-port guard, stream-pause ref, and abort/timeout refs
  const inFlightPollRef = useRef(false);
  const activePollIdRef = useRef(0);
  const interrogatingRef = useRef(false);
  const pollFailCountRef = useRef(0);
  const activePortRef = useRef(selectedPort);
  useEffect(() => {
    activePortRef.current = selectedPort;
  }, [selectedPort]);
  const isStreamPausedRef = useRef(isStreamPaused);
  useEffect(() => {
    isStreamPausedRef.current = isStreamPaused;
  }, [isStreamPaused]);
  const didInitPortsRef = useRef(false);
  const sensorAbortRef = useRef(null);
  const interrogationTimersRef = useRef([]);

  const clearInterrogationTimers = useCallback(() => {
    interrogationTimersRef.current.forEach((id) => clearTimeout(id));
    interrogationTimersRef.current = [];
  }, []);

  useEffect(() => {
    return () => {
      clearInterrogationTimers();
      if (sensorAbortRef.current) {
        try { sensorAbortRef.current.abort(); } catch {}
      }
    };
  }, [clearInterrogationTimers]);

  // 1. Query Live Sensors (Hardware or Demo) — stable deps ([]) to prevent port snap-back
  const querySensors = useCallback(async (isFast = true, portOverride = null, silent = false) => {
    const port = portOverride || activePortRef.current;
    if (!port) return;

    if (silent && inFlightPollRef.current) {
      return;
    }
    if (!silent && sensorAbortRef.current) {
      try { sensorAbortRef.current.abort(); } catch {}
    }
    const controller = new AbortController();
    sensorAbortRef.current = controller;
    const myPollId = activePollIdRef.current + 1;
    activePollIdRef.current = myPollId;
    inFlightPollRef.current = true;

    try {
      const res = await fetch(
        `/api/sensors?port=${encodeURIComponent(port)}&fast=${isFast ? '1' : '0'}`,
        { signal: controller.signal }
      );
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      if (activePortRef.current && port !== activePortRef.current) return;

      if (data.error) {
        pollFailCountRef.current += 1;
        if (!silent || pollFailCountRef.current >= 3) {
          setConnectionStatusText(createTranslator(langRef.current)('connWarning', { err: data.error }));
          setHardwareError(data.error);
        }
        return;
      }

      pollFailCountRef.current = 0;
      setHardwareError(null);
      setLiveData(data);
      setIsConnected(true);
      setLastTimestamp(data.timestamp || new Date().toLocaleTimeString());
      setConnectionStatusText(createTranslator(langRef.current)('connConnected', { port }));

      // Append to live bus event stream if not paused
      if (!isStreamPausedRef.current) {
        const tb = data.telemetry || {};
        const cap = data.capabilities || {};
        const ts = data.timestamp || new Date().toLocaleTimeString();
        const segs = [];
        if (cap.topology === 'jura_smart_connect') {
          segs.push(`@TF: ALERTS=${tb.active_alert_count ?? 0}`);
        } else {
          if (tb.heater_coffee_c != null) segs.push(`TB1: ${Number(tb.heater_coffee_c).toFixed(1)}°C`);
          if (tb.heater_steam_c != null) segs.push(`TB2: ${Number(tb.heater_steam_c).toFixed(1)}°C`);
          if (tb.pump_pressure_bar != null) segs.push(`P: ${Number(tb.pump_pressure_bar).toFixed(1)} bar`);
          if (cap.has_bu_encoder && tb.bu_encoder_pos != null) segs.push(`BU: ${tb.bu_encoder_pos} tk`);
          if (cap.has_flowmeter !== false && tb.flow_rate_ml_s != null) segs.push(`FLOW: ${tb.flow_rate_ml_s} ml/s`);
        }
        if (tb.beans_ok === true) segs.push('BEANS: OK');
        else if (tb.beans_ok === false) segs.push('BEANS: EMPTY');
        segs.push(`STATE: ${tb.machine_state_status || data.readiness || (cap.has_live_frame === false ? 'No Frame' : 'Ready')}`);
        const logLine = `[${ts}] ${segs.join(' | ')}`;
        setBusEvents((prev) => [logLine, ...prev.slice(0, 99)]);
      }
    } catch (err) {
      if (err?.name === 'AbortError') return;
      if (activePortRef.current && port !== activePortRef.current) return;
      pollFailCountRef.current += 1;
      if (!silent || pollFailCountRef.current >= 3) {
        setConnectionStatusText(createTranslator(langRef.current)('connError', { err: err.message }));
        setHardwareError(err.message);
      }
    } finally {
      if (activePollIdRef.current === myPollId) {
        inFlightPollRef.current = false;
      }
    }
  }, [langRef]);

  // 2. Initial Load: Fetch Serial Ports & Calibration
  const fetchPorts = useCallback(async (forceSelect = false) => {
    try {
      const res = await fetch('/api/ports');
      if (!res.ok) return;
      const ports = await res.json();
      setAvailablePorts(ports);
      if (ports.length > 0 && (forceSelect || !didInitPortsRef.current || !ports.includes(activePortRef.current))) {
        didInitPortsRef.current = true;
        const hwPort =
          ports.find((p) => p.includes('ttyUSB') || p.includes('ttyACM') || p.includes('USB') || p.includes('by-id') || p.toUpperCase().startsWith('COM')) ||
          ports.find((p) => p.includes('DEMO')) ||
          ports[0];
        activePortRef.current = hwPort;
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
    if (!didInitPortsRef.current) {
      fetchPorts(false);
    }
    fetchCalibration();
  }, [fetchPorts, fetchCalibration]);

  // 3. Full Interrogation Routine (Read Statistics & EEPROM with Progress)
  const runFullInterrogation = useCallback(async () => {
    const port = activePortRef.current;
    if (!port || interrogatingRef.current) return;
    interrogatingRef.current = true;
    const tr = createTranslator(langRef.current);
    clearInterrogationTimers();
    setIsInterrogating(true);
    setInterrogationProgress(8);
    setInterrogationStage(tr('stageProbeIdentity'));
    setConnectionStatusText(tr('connInterrogating', { port }));

    const t1 = setTimeout(() => {
      setInterrogationProgress(28);
      setInterrogationStage(createTranslator(langRef.current)('stageReadGateways'));
    }, 600);

    const t2 = setTimeout(() => {
      setInterrogationProgress(55);
      setInterrogationStage(createTranslator(langRef.current)('stageSweepBeverages'));
    }, 1400);

    const t3 = setTimeout(() => {
      setInterrogationProgress(78);
      setInterrogationStage(createTranslator(langRef.current)('stageReadMaintenance'));
    }, 2400);

    const t4 = setTimeout(() => {
      setInterrogationProgress(92);
      setInterrogationStage(createTranslator(langRef.current)('stageEvalHealth'));
    }, 3400);

    interrogationTimersRef.current = [t1, t2, t3, t4];

    try {
      const res = await fetch(`/api/stats?port=${encodeURIComponent(port)}`);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      if (port !== activePortRef.current) return;
      if (data.error) {
        setConnectionStatusText(createTranslator(langRef.current)('connInterrogateFailed', { err: data.error }));
        setHardwareError(data.error);
        setInterrogationStage(createTranslator(langRef.current)('stageError', { err: data.error }));
      } else {
        setInterrogationProgress(100);
        setInterrogationStage(createTranslator(langRef.current)('stageComplete'));
        setStatsData(data);
        setConnectionStatusText(createTranslator(langRef.current)('connInterrogateComplete', { model: data.machine_model || 'Appliance', preps: data.total_preparations || 0 }));
      }
    } catch (err) {
      if (port !== activePortRef.current) return;
      setConnectionStatusText(createTranslator(langRef.current)('connInterrogateError', { err: err.message }));
      setHardwareError(err.message);
      setInterrogationStage(createTranslator(langRef.current)('stageError', { err: err.message }));
    } finally {
      clearTimeout(t1);
      clearTimeout(t2);
      clearTimeout(t3);
      clearTimeout(t4);
      const tEnd = setTimeout(() => {
        interrogatingRef.current = false;
        setIsInterrogating(false);
        setInterrogationProgress(0);
        setInterrogationStage('');
      }, 900);
      interrogationTimersRef.current = [tEnd];
    }
  }, [clearInterrogationTimers, langRef]);

  // 4. UART Command Injection Form
  const handleTransmitCommand = useCallback(async (customCmd) => {
    const cmdToSend = customCmd || txCommand;
    if (!cmdToSend.trim() || !selectedPort) return;

    try {
      const res = await fetch('/api/command', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ port: selectedPort, cmd: cmdToSend.trim() }),
      });
      const data = await parseJsonResponse(res);

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
  }, [txCommand, selectedPort, querySensors]);

  return {
    availablePorts,
    selectedPort,
    setSelectedPort,
    activePortRef,
    pollFailCountRef,
    isConnected,
    isPolling,
    setIsPolling,
    isInterrogating,
    hardwareError,
    setHardwareError,
    connectionStatusText,
    lastTimestamp,
    liveData,
    setLiveData,
    statsData,
    setStatsData,
    interrogationProgress,
    interrogationStage,
    busEvents,
    setBusEvents,
    isStreamPaused,
    setIsStreamPaused,
    txCommand,
    setTxCommand,
    txResponseHistory,
    querySensors,
    fetchPorts,
    runFullInterrogation,
    handleTransmitCommand,
  };
}
