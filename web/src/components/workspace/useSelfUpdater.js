import { useState, useEffect, useRef, useCallback } from 'react';

export function useSelfUpdater({ t, serverBootIdRef }) {
  const [updateInfo, setUpdateInfo] = useState(null);
  const [updateProgress, setUpdateProgress] = useState({
    status: 'idle',
    percent: 0,
    in_progress: false,
    restart_required: false,
    message: '',
    error: '',
  });
  const [isCheckingUpdates, setIsCheckingUpdates] = useState(false);
  const [isReconnectingAfterUpdate, setIsReconnectingAfterUpdate] = useState(false);

  const updatePollTimerRef = useRef(null);
  const updateRestartDelayRef = useRef(null);
  const updateStatusTimerRef = useRef(null);
  const pollInFlightRef = useRef(false);
  const statusInFlightRef = useRef(false);
  const updateAbortRef = useRef(null);

  const checkForUpdates = useCallback(async (force = false) => {
    setIsCheckingUpdates(true);
    try {
      const res = await fetch(`/api/update/check?force=${force ? '1' : '0'}`);
      if (res.ok) {
        const data = await res.json();
        setUpdateInfo(data);
        return data;
      }
    } catch {}
    finally {
      setIsCheckingUpdates(false);
    }
    return null;
  }, []);

  // Silent non-blocking update check shortly after startup
  useEffect(() => {
    const timer = setTimeout(() => {
      checkForUpdates(false);
    }, 1500);
    return () => clearTimeout(timer);
  }, [checkForUpdates]);

  useEffect(() => {
    return () => {
      if (updateRestartDelayRef.current) clearTimeout(updateRestartDelayRef.current);
      if (updatePollTimerRef.current) clearInterval(updatePollTimerRef.current);
      if (updateStatusTimerRef.current) clearInterval(updateStatusTimerRef.current);
      if (updateAbortRef.current) {
        try { updateAbortRef.current.abort(); } catch {}
        updateAbortRef.current = null;
      }
    };
  }, []);

  const pollServerAfterRestart = useCallback((expectedTargetBuild = '') => {
    setIsReconnectingAfterUpdate(true);
    if (updateRestartDelayRef.current) {
      clearTimeout(updateRestartDelayRef.current);
      updateRestartDelayRef.current = null;
    }
    if (updatePollTimerRef.current) {
      clearInterval(updatePollTimerRef.current);
      updatePollTimerRef.current = null;
    }
    const prevBootId = serverBootIdRef.current || '';
    const targetBuild = String(expectedTargetBuild || updateInfo?.latest_build || '').trim();
    let attempts = 0;
    let sawDisconnect = false;

    updateRestartDelayRef.current = setTimeout(() => {
      updateRestartDelayRef.current = null;
      updatePollTimerRef.current = setInterval(async () => {
        if (document.visibilityState === 'hidden' || pollInFlightRef.current) return;
        pollInFlightRef.current = true;
        attempts += 1;
        if (updateAbortRef.current) {
          try { updateAbortRef.current.abort(); } catch {}
        }
        const controller = new AbortController();
        updateAbortRef.current = controller;
        try {
          const res = await fetch(`/api/version?ts=${Date.now()}`, {
            cache: 'no-store',
            signal: controller.signal,
          });
          if (res.ok) {
            const data = await res.json();
            const bootChanged = Boolean(prevBootId && data?.boot_id && data.boot_id !== prevBootId);
            const buildChanged = Boolean(targetBuild && data?.build && data.build === targetBuild);
            if (bootChanged || buildChanged || sawDisconnect) {
              clearInterval(updatePollTimerRef.current);
              updatePollTimerRef.current = null;
              window.location.replace(`${window.location.pathname}?v=${encodeURIComponent(data?.build || Date.now())}`);
              return;
            }
          } else {
            sawDisconnect = true;
          }
        } catch (err) {
          if (err?.name === 'AbortError') return;
          sawDisconnect = true;
        } finally {
          if (updateAbortRef.current === controller) {
            pollInFlightRef.current = false;
          }
        }
        if (attempts >= 60) {
          clearInterval(updatePollTimerRef.current);
          updatePollTimerRef.current = null;
          setIsReconnectingAfterUpdate(false);
          setUpdateProgress((prev) => ({
            ...prev,
            status: 'error',
            in_progress: false,
            restart_required: false,
            message: t('cfgUpdatesReconnectTimeout'),
            error: t('cfgUpdatesReconnectTimeout'),
          }));
        }
      }, 800);
    }, 900);
  }, [t, updateInfo?.latest_build, serverBootIdRef]);

  const startSelfUpdate = useCallback(async () => {
    const targetBuild = String(updateInfo?.latest_build || '').trim();
    try {
      const verRes = await fetch(`/api/version?ts=${Date.now()}`, { cache: 'no-store' }).catch(() => null);
      if (verRes && verRes.ok) {
        const verData = await verRes.json().catch(() => null);
        if (verData?.boot_id) serverBootIdRef.current = verData.boot_id;
      }

      const res = await fetch('/api/update/apply', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({}),
      });
      const rawText = await res.text();
      let data = {};
      try {
        data = rawText ? JSON.parse(rawText) : {};
      } catch {
        data = {};
      }
      if (!res.ok || !data?.ok) {
        const errMsg = data?.error || data?.state?.error || `HTTP ${res.status}: ${rawText.slice(0, 200) || 'Update request failed'}`;
        setUpdateProgress({
          ...(data?.state || {}),
          status: 'error',
          in_progress: false,
          percent: 0,
          restart_required: false,
          message: 'Update failed',
          error: errMsg,
        });
        return;
      }
      if (data?.state) {
        setUpdateProgress(data.state);
      }

      if (updateStatusTimerRef.current) clearInterval(updateStatusTimerRef.current);
      updateStatusTimerRef.current = setInterval(async () => {
        if (document.visibilityState === 'hidden' || statusInFlightRef.current) return;
        statusInFlightRef.current = true;
        if (updateAbortRef.current) {
          try { updateAbortRef.current.abort(); } catch {}
        }
        const controller = new AbortController();
        updateAbortRef.current = controller;
        try {
          const stRes = await fetch(`/api/update/status?ts=${Date.now()}`, {
            cache: 'no-store',
            signal: controller.signal,
          });
          if (!stRes.ok) throw new Error(`HTTP ${stRes.status}`);
          const st = await stRes.json();
          if (st?.boot_id && !serverBootIdRef.current) {
            serverBootIdRef.current = st.boot_id;
          }
          setUpdateProgress(st);
          if (st.restart_required || st.status === 'restarting') {
            clearInterval(updateStatusTimerRef.current);
            updateStatusTimerRef.current = null;
            pollServerAfterRestart(st.target_build || targetBuild);
          } else if (!st.in_progress && ['up_to_date', 'error', 'cancelled'].includes(st.status)) {
            clearInterval(updateStatusTimerRef.current);
            updateStatusTimerRef.current = null;
            if (st.status === 'up_to_date') {
              checkForUpdates(true);
            }
          }
        } catch (err) {
          if (err?.name === 'AbortError') return;
          clearInterval(updateStatusTimerRef.current);
          updateStatusTimerRef.current = null;
          pollServerAfterRestart(targetBuild);
        } finally {
          if (updateAbortRef.current === controller) {
            statusInFlightRef.current = false;
          }
        }
      }, 450);
    } catch (err) {
      const errMsg = err?.message || 'Network error starting self-update';
      setUpdateProgress({
        status: 'error',
        in_progress: false,
        percent: 0,
        restart_required: false,
        message: 'Update failed',
        error: errMsg,
      });
    }
  }, [checkForUpdates, pollServerAfterRestart, updateInfo?.latest_build, serverBootIdRef]);

  const cancelSelfUpdate = useCallback(async () => {
    try {
      const res = await fetch('/api/update/cancel', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({}),
      });
      if (res.ok) {
        const data = await res.json();
        if (data?.state) setUpdateProgress(data.state);
      }
    } catch {}
  }, []);

  return {
    updateInfo,
    updateProgress,
    isCheckingUpdates,
    isReconnectingAfterUpdate,
    checkForUpdates,
    startSelfUpdate,
    cancelSelfUpdate,
  };
}
