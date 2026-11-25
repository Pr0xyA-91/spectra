import React, { useState, useEffect, useRef, useCallback, useMemo } from 'react';
import { Cpu, X, Info } from 'lucide-react';
import {
  DEFAULT_SUMMARY,
  VALID_AI_CATEGORIES,
  buildFallbackRegister,
  buildFallbackSensorField,
  filterRegisters
} from './mem_mapper/mapperHelpers';
import EepromMatrixView from './mem_mapper/EepromMatrixView';
import RegisterInspectorPanel from './mem_mapper/RegisterInspectorPanel';
import RawSensorTelemetryView from './mem_mapper/RawSensorTelemetryView';
import { copyTextSafe } from '../utils/fetchSafe';

function MemMapperTab({
  theme,
  selectedPort,
  liveData = null,
  liveDataRef = null,
  machineModel = '',
  aiEnabled = false,
  aiModel = '',
  onToggleAi = null,
  beginAiWork = null,
  endAiWork = null,
  onSweepStateChange = null
}) {
  // Sub-tab: 'eeprom' or 'raw_sensors'
  const [subTab, setSubTab] = useState('eeprom');

  // Mapper info & EEPROM registers state
  const [mapperInfo, setMapperInfo] = useState(null);
  const [registers, setRegisters] = useState([]);
  const [selectedAddr, setSelectedAddr] = useState(0x0040); // Default to BU Upper Limit
  const [summary, setSummary] = useState(DEFAULT_SUMMARY);

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

  // Local AI Register Labeling state (opt-in, default OFF)
  const [aiSuggestions, setAiSuggestions] = useState([]);
  const [isSuggestingAi, setIsSuggestingAi] = useState(false);
  const [aiSuggestError, setAiSuggestError] = useState('');
  const pendingAiApplyRef = useRef(null);
  const sweepSeqRef = useRef(0);
  const diffInFlightRef = useRef(false);
  const diffAbortRef = useRef(null);
  const rawSensorsInFlightRef = useRef(false);
  const rawSensorsAbortRef = useRef(null);
  const activePortRef = useRef(selectedPort);
  const sweepAbortRef = useRef(null);

  useEffect(() => {
    activePortRef.current = selectedPort;
  }, [selectedPort]);

  // --------------------------------------------------------------------------
  // 1. Fetch Mapper Identity & Summary
  // --------------------------------------------------------------------------
  const fetchMapperInfo = useCallback(async (signal = null) => {
    const port = selectedPort;
    if (!port) return null;
    try {
      const res = await fetch(
        `/api/mapper/info?port=${encodeURIComponent(port)}`,
        signal ? { signal } : undefined
      );
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      if (port !== activePortRef.current) return null;
      if (data.error) {
        setStatusMessage(data.error);
        setStatusType('warn');
        return data;
      }
      setMapperInfo(data);
      if (data.summary) {
        setSummary(data.summary);
      }
      return data;
    } catch (err) {
      if (err?.name === 'AbortError') return null;
      console.warn('Failed to fetch mapper info:', err);
      return null;
    }
  }, [selectedPort]);

  // --------------------------------------------------------------------------
  // 2. Full Memory Sweep (Block-by-Block with Live Progress & Heartbeat Safety)
  // --------------------------------------------------------------------------
  const handleFullSweep = useCallback(async (infoOverride = null) => {
    const port = selectedPort;
    if (!port) return;
    if (isSweeping && !infoOverride) return;
    if (sweepAbortRef.current) {
      try { sweepAbortRef.current.abort(); } catch {}
    }
    const controller = new AbortController();
    sweepAbortRef.current = controller;
    const mySeq = sweepSeqRef.current + 1;
    sweepSeqRef.current = mySeq;
    setIsSweeping(true);
    onSweepStateChange?.(true);

    try {
      let info = infoOverride || mapperInfo;
      if (!info || !info.max_words) {
        info = await fetchMapperInfo(controller.signal);
      }
      if (sweepSeqRef.current !== mySeq || port !== activePortRef.current) return;
      if (!info || info.error) {
        if (info?.error) {
          setStatusMessage(`Sweep failed: ${info.error}`);
          setStatusType('warn');
        }
        return;
      }

      const maxWords = Number(info.max_words) || 512;
      const totalBlocks = Math.max(1, Math.floor(maxWords / 16));
      setSweepProgress({ current: 0, total: totalBlocks });
      setStatusMessage(`Executing safe EEPROM sweep (${totalBlocks} blocks / ${maxWords} words) over UART...`);
      setStatusType('info');

      let lastSummary = info.summary || null;
      const mergedMap = new Map();
      let completedBlocks = 0;

      for (let bIdx = 0; bIdx < totalBlocks; bIdx += 1) {
        if (sweepSeqRef.current !== mySeq || port !== activePortRef.current) return;

        setSweepProgress({ current: bIdx + 1, total: totalBlocks });
        setStatusMessage(`Reading EEPROM Block ${bIdx + 1}/${totalBlocks} (0x${(bIdx * 16).toString(16).toUpperCase().padStart(info.address_width || 4, '0')})...`);

        const res = await fetch('/api/mapper/sweep', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ port, block: bIdx }),
          signal: controller.signal,
        });
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const data = await res.json();
        if (sweepSeqRef.current !== mySeq || port !== activePortRef.current) return;

        if (data.error) {
          setStatusMessage(`Sweep stopped at block ${bIdx + 1}/${totalBlocks}: ${data.error}`);
          setStatusType('warn');
          return;
        }

        if (Array.isArray(data.registers) && data.registers.length > 0) {
          for (const reg of data.registers) {
            mergedMap.set(reg.addr, reg);
          }
          setRegisters((prev) => {
            const map = new Map(prev.map((r) => [r.addr, r]));
            for (const reg of data.registers) {
              map.set(reg.addr, reg);
            }
            return Array.from(map.values()).sort((a, b) => a.addr - b.addr);
          });
        }
        if (data.summary) {
          lastSummary = data.summary;
          setSummary(data.summary);
        }
        completedBlocks = bIdx + 1;

        if (data.abort_sweep) {
          setStatusMessage(
            data.abort_reason ||
            `Sweep stopped early at block ${bIdx + 1}/${totalBlocks}: No ASCII or Smart Connect response.`
          );
          setStatusType('warn');
          return;
        }
        if (data.end_of_table) {
          break;
        }
      }

      if (sweepSeqRef.current !== mySeq || port !== activePortRef.current) return;
      if (lastSummary) setSummary(lastSummary);
      setStatusMessage(`Sweep complete: ${mergedMap.size || maxWords} words verified across ${completedBlocks} blocks.`);
      setStatusType('success');
    } catch (err) {
      if (err?.name === 'AbortError') return;
      if (sweepSeqRef.current === mySeq) {
        setStatusMessage(`Sweep error: ${err.message}`);
        setStatusType('warn');
      }
    } finally {
      if (sweepSeqRef.current === mySeq) {
        setIsSweeping(false);
        onSweepStateChange?.(false);
      }
    }
  }, [selectedPort, isSweeping, mapperInfo, fetchMapperInfo, onSweepStateChange]);

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
    const port = selectedPort;
    if (!port || !isLiveDiff || isSweeping || diffInFlightRef.current || document.visibilityState === 'hidden') return;
    diffInFlightRef.current = true;
    const controller = new AbortController();
    diffAbortRef.current = controller;
    try {
      const res = await fetch(`/api/mapper/diff?port=${encodeURIComponent(port)}`, {
        signal: controller.signal,
      });
      if (!res.ok) return;
      const data = await res.json();
      if (port !== activePortRef.current) return;

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
      if (err?.name === 'AbortError') return;
      console.warn('Diff poll failed:', err);
    } finally {
      if (diffAbortRef.current === controller) {
        diffInFlightRef.current = false;
      }
    }
  }, [selectedPort, isLiveDiff, isSweeping, isDiffPaused]);

  // Diff polling timer (pause workspace sensor polling while active to prevent _session_lock contention)
  useEffect(() => {
    if (!isLiveDiff || isSweeping) return;
    onSweepStateChange?.(true);
    const interval = setInterval(() => {
      if (document.visibilityState === 'hidden') return;
      pollDiff();
    }, 1500);
    const handleVisibility = () => {
      if (document.visibilityState === 'visible') {
        pollDiff();
      }
    };
    document.addEventListener('visibilitychange', handleVisibility);
    return () => {
      clearInterval(interval);
      document.removeEventListener('visibilitychange', handleVisibility);
      if (diffAbortRef.current) {
        try { diffAbortRef.current.abort(); } catch {}
        diffAbortRef.current = null;
      }
      diffInFlightRef.current = false;
      onSweepStateChange?.(false);
    };
  }, [isLiveDiff, isSweeping, pollDiff, onSweepStateChange]);

  // --------------------------------------------------------------------------
  // 5. Register Selection & Form Population
  // --------------------------------------------------------------------------
  const selectedRegister =
    registers.find((r) => r.addr === selectedAddr) || buildFallbackRegister(selectedAddr);

  useEffect(() => {
    const pending = pendingAiApplyRef.current;
    if (pending && Number(pending.addr) === Number(selectedAddr)) {
      pendingAiApplyRef.current = null;
      setMapForm({
        name: pending.suggested_name || `Reg_0x${selectedAddr.toString(16).toUpperCase().padStart(4, '0')}`,
        desc: pending.reasoning ? `[AI ${pending.confidence || 'medium'}] ${pending.reasoning}` : 'AI-suggested register mapping',
        category: pending.category || 'custom',
        unit: pending.unit || '',
        status: 'theoretical'
      });
      return;
    }
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
  // 5b. Local Ollama Register Labeling (Opt-in)
  // --------------------------------------------------------------------------
  const handleSuggestAiRegisters = async () => {
    if (!aiEnabled) {
      setAiSuggestError('Local AI is OFF. Enable Local AI before running register analysis.');
      return;
    }
    setAiSuggestError('');
    setIsSuggestingAi(true);
    const taskId = 'mapper_ai_suggest';
    if (beginAiWork) beginAiWork(taskId, 'Memory Mapper: Analyzing unknown/changed registers...', 20);
    try {
      // Prioritize changed or unknown registers; fallback to selected register if needed
      let targetRegs = registers.filter((r) => r.is_changed || r.status === 'unknown' || r.status === 'theoretical');
      if (targetRegs.length === 0 && selectedRegister) {
        targetRegs = [selectedRegister];
      }
      const candidates = targetRegs.slice(0, 12).map((r) => ({
        addr: r.addr,
        addr_hex: r.hex_addr || r.addr.toString(16).toUpperCase().padStart(4, '0'),
        val: r.val,
        prev_val: r.baseline_val,
        flips: r.bits_flipped || [],
        status: r.status || 'unknown'
      }));
      const contextRegisters = registers
        .filter((r) => r.status === 'mapped')
        .slice(0, 20)
        .map((r) => ({
          addr: r.addr,
          val: r.val,
          name: r.name,
          category: r.category
        }));

      const currentLive = liveDataRef?.current ?? liveData;
      const res = await fetch('/api/mapper/ai_suggest', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          candidates,
          context_registers: contextRegisters,
          machine_model: machineModel || currentLive?.machine_model || 'Kalerm/Jura UART Machine',
          model: aiModel || ''
        })
      });
      const data = await res.json();
      if (!res.ok || !data.success) {
        throw new Error(data.error || `HTTP ${res.status}`);
      }
      setAiSuggestions(data.suggestions || []);
      if ((data.suggestions || []).length === 0) {
        setAiSuggestError('Local AI returned no high-confidence register suggestions for these candidates.');
      }
    } catch (err) {
      setAiSuggestError(err.message || 'AI register suggestion failed.');
    } finally {
      setIsSuggestingAi(false);
      if (endAiWork) endAiWork(taskId);
    }
  };

  const handleApplyAiSuggestion = (sug) => {
    const targetAddr = Number(sug.addr);
    const normalizedCategory = VALID_AI_CATEGORIES.includes(sug.category) ? sug.category : 'custom';
    const normalizedSug = { ...sug, category: normalizedCategory };
    pendingAiApplyRef.current = normalizedSug;
    setSelectedAddr(targetAddr);
    setMapForm({
      name: normalizedSug.suggested_name || `Reg_0x${targetAddr.toString(16).toUpperCase().padStart(4, '0')}`,
      desc: normalizedSug.reasoning ? `[AI ${normalizedSug.confidence || 'medium'}] ${normalizedSug.reasoning}` : 'AI-suggested register mapping',
      category: normalizedCategory,
      unit: normalizedSug.unit || '',
      status: 'theoretical'
    });
    setStatusMessage(`Applied AI suggestion for 0x${sug.addr_hex || targetAddr.toString(16).toUpperCase().padStart(4, '0')} into editor (status: theoretical). Save to persist.`);
    setStatusType('info');
  };

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
    const port = selectedPort;
    if (!port || isSweeping || rawSensorsInFlightRef.current || document.visibilityState === 'hidden') return;
    rawSensorsInFlightRef.current = true;
    const controller = new AbortController();
    rawSensorsAbortRef.current = controller;
    try {
      const res = await fetch(`/api/mapper/raw_sensors?port=${encodeURIComponent(port)}`, {
        signal: controller.signal,
      });
      if (!res.ok) return;
      const data = await res.json();
      if (port !== activePortRef.current) return;
      if (!data.error) {
        setRawSensorData(data);
      }
    } catch (err) {
      if (err?.name === 'AbortError') return;
      console.warn('Raw sensors query failed:', err);
    } finally {
      if (rawSensorsAbortRef.current === controller) {
        rawSensorsInFlightRef.current = false;
      }
    }
  }, [selectedPort, isSweeping]);

  useEffect(() => {
    if (subTab === 'raw_sensors' && isRawPolling && !isSweeping) {
      onSweepStateChange?.(true);
      if (document.visibilityState !== 'hidden') {
        queryRawSensors();
      }
      const interval = setInterval(() => {
        if (document.visibilityState === 'hidden') return;
        queryRawSensors();
      }, 1200);
      const handleVisibility = () => {
        if (document.visibilityState === 'visible') {
          queryRawSensors();
        }
      };
      document.addEventListener('visibilitychange', handleVisibility);
      return () => {
        clearInterval(interval);
        document.removeEventListener('visibilitychange', handleVisibility);
        if (rawSensorsAbortRef.current) {
          try { rawSensorsAbortRef.current.abort(); } catch {}
          rawSensorsAbortRef.current = null;
        }
        rawSensorsInFlightRef.current = false;
        onSweepStateChange?.(false);
      };
    }
  }, [subTab, isRawPolling, isSweeping, queryRawSensors, onSweepStateChange]);

  // Populate Sensor Form when selected field changes
  const selectedSensorField =
    rawSensorData.fields?.find((f) => f.key === selectedFieldKey) ||
    buildFallbackSensorField(selectedFieldKey);

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

  // Initial load: fetch metadata first, then sweep sequentially block-by-block
  useEffect(() => {
    let cancelled = false;
    const initController = new AbortController();
    (async () => {
      const info = await fetchMapperInfo(initController.signal);
      if (!cancelled && info && !info.error) {
        await handleFullSweep(info);
      }
    })();
    return () => {
      cancelled = true;
      initController.abort();
      if (sweepAbortRef.current) {
        try { sweepAbortRef.current.abort(); } catch {}
      }
      sweepSeqRef.current += 1;
      onSweepStateChange?.(false);
    };
  }, [selectedPort]);

  // Copy helper
  const handleCopyText = useCallback(async (txt, label) => {
    const ok = await copyTextSafe(txt);
    if (ok) {
      setCopiedFrame(label);
      setTimeout(() => setCopiedFrame(null), 1200);
    }
  }, []);

  const filteredRegisters = useMemo(
    () => filterRegisters(registers, filterType, searchQuery),
    [registers, filterType, searchQuery]
  );

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
          <span className="text-[10px] px-2 py-0.5 bg-cyan-950/80 text-cyan-300 border border-cyan-500/60 font-mono font-bold tracking-wider rounded">
            READ-ONLY DIFFERENTIAL SCOPE
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
        <EepromMatrixView
          theme={theme}
          summary={summary}
          registers={registers}
          filteredRegisters={filteredRegisters}
          selectedAddr={selectedAddr}
          setSelectedAddr={setSelectedAddr}
          isSweeping={isSweeping}
          sweepProgress={sweepProgress}
          isLiveDiff={isLiveDiff}
          setIsLiveDiff={setIsLiveDiff}
          filterType={filterType}
          setFilterType={setFilterType}
          searchQuery={searchQuery}
          setSearchQuery={setSearchQuery}
          onFullSweep={handleFullSweep}
          onCaptureBaseline={handleCaptureBaseline}
          inspectorPanel={
            <RegisterInspectorPanel
              theme={theme}
              selectedRegister={selectedRegister}
              mapForm={mapForm}
              setMapForm={setMapForm}
              isSavingReg={isSavingReg}
              onSaveRegisterMapping={handleSaveRegisterMapping}
              diffEvents={diffEvents}
              setDiffEvents={setDiffEvents}
              isDiffPaused={isDiffPaused}
              setIsDiffPaused={setIsDiffPaused}
              aiEnabled={aiEnabled}
              aiModel={aiModel}
              onToggleAi={onToggleAi}
              registersCount={registers.length}
              isSuggestingAi={isSuggestingAi}
              aiSuggestError={aiSuggestError}
              aiSuggestions={aiSuggestions}
              onSuggestAiRegisters={handleSuggestAiRegisters}
              onApplyAiSuggestion={handleApplyAiSuggestion}
            />
          }
        />
      )}

      {/* ==================================================================== */}
      {/* SUB-VIEW 2: RAW SENSOR WIRE TELEMETRY & VALUE MAPPER */}
      {/* ==================================================================== */}
      {subTab === 'raw_sensors' && (
        <RawSensorTelemetryView
          theme={theme}
          rawSensorData={rawSensorData}
          selectedFieldKey={selectedFieldKey}
          setSelectedFieldKey={setSelectedFieldKey}
          selectedSensorField={selectedSensorField}
          isRawPolling={isRawPolling}
          setIsRawPolling={setIsRawPolling}
          onQueryRawSensors={queryRawSensors}
          copiedFrame={copiedFrame}
          onCopyText={handleCopyText}
          sensorMapForm={sensorMapForm}
          setSensorMapForm={setSensorMapForm}
          isSavingSensorMap={isSavingSensorMap}
          onSaveSensorMapping={handleSaveSensorMapping}
          onResetSensorMappings={handleResetSensorMappings}
        />
      )}
    </div>
  );
}

export default React.memo(MemMapperTab);
