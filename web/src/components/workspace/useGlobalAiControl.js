import { useState, useEffect, useRef, useCallback } from 'react';

export function useGlobalAiControl({ onDisableAi, onOpenAiConfig }) {
  const [aiEnabled, setAiEnabled] = useState(false);
  const [aiModel, setAiModel] = useState(() => {
    try {
      return localStorage.getItem('spectra_ollama_model') || '';
    } catch {
      return '';
    }
  });
  const [aiTask, setAiTask] = useState({ active: false });
  const [aiDownload, setAiDownload] = useState({ active: false });
  const [aiSystem, setAiSystem] = useState(null);
  const [aiAutoUnload, setAiAutoUnload] = useState(true);
  const [aiBusyCount, setAiBusyCount] = useState(0);
  const [showNoModelPromptModal, setShowNoModelPromptModal] = useState(false);
  const [noModelPromptChoice, setNoModelPromptChoice] = useState('');
  const [autoEnableAiAfterPull, setAutoEnableAiAfterPull] = useState(false);

  const aiModelRef = useRef(aiModel);
  useEffect(() => {
    aiModelRef.current = aiModel;
  }, [aiModel]);

  const statusInFlightRef = useRef(false);
  const statusAbortRef = useRef(null);

  useEffect(() => {
    return () => {
      if (statusAbortRef.current) {
        try { statusAbortRef.current.abort(); } catch {}
        statusAbortRef.current = null;
      }
    };
  }, []);

  const fetchAiGlobalStatus = useCallback(async () => {
    if (statusInFlightRef.current) return;
    statusInFlightRef.current = true;
    const controller = new AbortController();
    statusAbortRef.current = controller;
    try {
      const res = await fetch('/api/ai/status', { signal: controller.signal });
      if (!res.ok) return;
      const data = await res.json();
      if (data && data.success) {
        setAiEnabled(Boolean(data.ai_enabled));
        if (data.preferred_model && !aiModelRef.current) {
          setAiModel(data.preferred_model);
        }
        if (typeof data.auto_unload === 'boolean') {
          setAiAutoUnload(data.auto_unload);
        }
        setAiTask(data.task || { active: false });
        setAiDownload(data.download || { active: false });
        if (data.system) {
          setAiSystem(data.system);
        }
      }
    } catch (err) {
      if (err?.name === 'AbortError') return;
    } finally {
      if (statusAbortRef.current === controller) {
        statusInFlightRef.current = false;
      }
    }
  }, []);

  const handleSaveAiConfig = useCallback(async ({ model, auto_unload }) => {
    if (model !== undefined) {
      setAiModel(model);
      try {
        localStorage.setItem('spectra_ollama_model', model || '');
      } catch {}
    }
    if (auto_unload !== undefined) {
      setAiAutoUnload(Boolean(auto_unload));
    }
    try {
      const res = await fetch('/api/ai/config', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ model, auto_unload }),
      });
      if (res.ok) {
        const data = await res.json();
        if (data.preferred_model) setAiModel(data.preferred_model);
        if (typeof data.auto_unload === 'boolean') setAiAutoUnload(data.auto_unload);
        if (data.system) setAiSystem(data.system);
      }
    } catch {}
  }, []);

  useEffect(() => {
    fetchAiGlobalStatus();
  }, [fetchAiGlobalStatus]);

  useEffect(() => {
    if (!aiTask?.active && !aiDownload?.active && aiBusyCount === 0) return;
    const iv = setInterval(() => {
      if (document.visibilityState === 'hidden') return;
      fetchAiGlobalStatus();
    }, 650);
    const handleVisibility = () => {
      if (document.visibilityState === 'visible') {
        fetchAiGlobalStatus();
      }
    };
    document.addEventListener('visibilitychange', handleVisibility);
    return () => {
      clearInterval(iv);
      document.removeEventListener('visibilitychange', handleVisibility);
      if (statusAbortRef.current) {
        try { statusAbortRef.current.abort(); } catch {}
        statusAbortRef.current = null;
      }
      statusInFlightRef.current = false;
    };
  }, [aiTask?.active, aiDownload?.active, aiBusyCount, fetchAiGlobalStatus]);

  const handleToggleAi = useCallback(async (nextEnabled, modelOverride = null) => {
    const targetEnabled = Boolean(nextEnabled);
    if (!targetEnabled) {
      setAiEnabled(false);
      onDisableAi?.();
    } else {
      let currentSystem = aiSystem;
      if (!currentSystem) {
        try {
          const stRes = await fetch('/api/ai/status');
          if (stRes.ok) {
            const stData = await stRes.json();
            if (stData?.system) {
              currentSystem = stData.system;
              setAiSystem(stData.system);
            }
          }
        } catch {}
      }
      const installedNow = Array.isArray(currentSystem?.ollama?.models)
        ? currentSystem.ollama.models
        : [];
      if (installedNow.length === 0) {
        setAiEnabled(false);
        setNoModelPromptChoice(
          modelOverride || currentSystem?.hardware?.recommended_model || 'qwen2.5:0.5b'
        );
        setShowNoModelPromptModal(true);
        return false;
      }
    }

    try {
      const res = await fetch('/api/ai/toggle', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          enabled: targetEnabled,
          model: modelOverride || aiModel || undefined,
        }),
      });
      if (res.ok) {
        const data = await res.json();
        if (targetEnabled && (data?.requires_model_install || !data?.success)) {
          setAiEnabled(false);
          if (data?.status?.system) setAiSystem(data.status.system);
          setNoModelPromptChoice(
            modelOverride || data?.status?.system?.hardware?.recommended_model || 'qwen2.5:0.5b'
          );
          setShowNoModelPromptModal(true);
          return false;
        }
        const finalEnabled = Boolean(data?.status?.ai_enabled ?? data?.ai_enabled ?? targetEnabled);
        setAiEnabled(finalEnabled);
        if (data?.preferred_model) setAiModel(data.preferred_model);
        if (data?.status) {
          setAiTask(data.status.task || { active: false });
          setAiDownload(data.status.download || { active: false });
          if (data.status.system) setAiSystem(data.status.system);
        }
        return finalEnabled;
      }
    } catch {}
    if (targetEnabled) setAiEnabled(false);
    return false;
  }, [aiModel, aiSystem, onDisableAi]);

  const handleStartPullFromNoModelPrompt = useCallback(async (chosenModel) => {
    const modelTag = (chosenModel || aiSystem?.hardware?.recommended_model || 'qwen2.5:0.5b').trim();
    setShowNoModelPromptModal(false);
    setAutoEnableAiAfterPull(true);
    onOpenAiConfig?.();
    await handleSaveAiConfig({ model: modelTag, auto_unload: aiAutoUnload });
    try {
      await fetch('/api/hmi/ai/control', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ action: 'pull_async', model: modelTag }),
      });
      fetchAiGlobalStatus();
    } catch {}
  }, [aiSystem, aiAutoUnload, handleSaveAiConfig, fetchAiGlobalStatus, onOpenAiConfig]);

  useEffect(() => {
    if (!autoEnableAiAfterPull) return;
    if (!aiDownload?.active && aiDownload?.status === 'COMPLETED') {
      setAutoEnableAiAfterPull(false);
      (async () => {
        await fetchAiGlobalStatus();
        await handleToggleAi(true, aiDownload.model || noModelPromptChoice);
      })();
    } else if (!aiDownload?.active && ['ERROR', 'CANCELLED'].includes(aiDownload?.status)) {
      setAutoEnableAiAfterPull(false);
    }
  }, [autoEnableAiAfterPull, aiDownload, noModelPromptChoice, fetchAiGlobalStatus, handleToggleAi]);

  const beginAiWork = useCallback(() => {
    setAiBusyCount((c) => c + 1);
    fetchAiGlobalStatus();
  }, [fetchAiGlobalStatus]);

  const endAiWork = useCallback(() => {
    setAiBusyCount((c) => Math.max(0, c - 1));
    fetchAiGlobalStatus();
  }, [fetchAiGlobalStatus]);

  return {
    aiEnabled,
    aiModel,
    setAiModel,
    aiTask,
    aiDownload,
    aiSystem,
    aiAutoUnload,
    aiBusyCount,
    showNoModelPromptModal,
    setShowNoModelPromptModal,
    noModelPromptChoice,
    setNoModelPromptChoice,
    fetchAiGlobalStatus,
    handleSaveAiConfig,
    handleToggleAi,
    handleStartPullFromNoModelPrompt,
    beginAiWork,
    endAiWork,
  };
}
