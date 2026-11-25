import React, { useState, useEffect, useRef, useCallback, Suspense } from 'react';
import SpectraWorkspace from './components/SpectraWorkspace';

const DebugConsoleModal = React.lazy(() => import('./components/DebugConsoleModal'));

export default function App() {
  const [lang, setLang] = useState(() => {
    try {
      const saved = localStorage.getItem('spectra_lang');
      return saved === 'cs' ? 'cs' : 'en';
    } catch {
      return 'en';
    }
  });
  const userSelectedLangRef = useRef(false);
  const [isDebugOpen, setIsDebugOpen] = useState(false);
  const [debugCounts, setDebugCounts] = useState({ errorCount: 0, warnCount: 0 });
  const [debugSummary, setDebugSummary] = useState(null);
  const [scaleMode, setScaleMode] = useState('auto'); // 'auto' | 0.85 | 1.0 | 1.15
  const [currentScale, setCurrentScale] = useState(1.0);

  const handleChangeLang = useCallback((nextLang) => {
    const normalized = nextLang === 'cs' ? 'cs' : 'en';
    userSelectedLangRef.current = true;
    setLang(normalized);
    document.documentElement.lang = normalized;
    try {
      localStorage.setItem('spectra_lang', normalized);
    } catch {}
    fetch('/api/ui_prefs', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ lang: normalized }),
    }).catch(() => {});
  }, []);

  useEffect(() => {
    let active = true;
    fetch('/api/ui_prefs')
      .then((r) => (r.ok ? r.json() : null))
      .then((d) => {
        if (!active || userSelectedLangRef.current) return;
        const diskLang = d?.prefs?.lang;
        if (diskLang === 'cs' || diskLang === 'en') {
          setLang(diskLang);
          document.documentElement.lang = diskLang;
          try {
            localStorage.setItem('spectra_lang', diskLang);
          } catch {}
        }
      })
      .catch(() => {});
    return () => {
      active = false;
    };
  }, []);

  useEffect(() => {
    document.documentElement.lang = lang;
  }, [lang]);

  // 1. Native Desktop App mode lifecycle: heartbeat & window_closed / close beacon
  useEffect(() => {
    const sendHeartbeat = () => {
      if (document.visibilityState === 'hidden') return;
      fetch('/api/app/heartbeat', { method: 'POST', keepalive: true }).catch(() => {});
    };

    const interval = setInterval(sendHeartbeat, 2000);
    const handleVisibility = () => {
      if (document.visibilityState === 'visible') {
        sendHeartbeat();
      }
    };
    document.addEventListener('visibilitychange', handleVisibility);

    const handleWindowClose = () => {
      try {
        const payload = JSON.stringify({ reason: 'window_closed' });
        if (navigator.sendBeacon) {
          navigator.sendBeacon('/api/app/close', payload);
          navigator.sendBeacon('/api/app/window_closed', payload);
        } else {
          fetch('/api/app/close', {
            method: 'POST',
            keepalive: true,
            headers: { 'Content-Type': 'application/json' },
            body: payload,
          }).catch(() => {});
        }
      } catch (e) {
        // Ignore during teardown
      }
    };

    window.addEventListener('pagehide', handleWindowClose);
    window.addEventListener('beforeunload', handleWindowClose);

    return () => {
      clearInterval(interval);
      document.removeEventListener('visibilitychange', handleVisibility);
      window.removeEventListener('pagehide', handleWindowClose);
      window.removeEventListener('beforeunload', handleWindowClose);
    };
  }, []);

  // 2. Global client-side runtime error reporting to backend ring buffer
  useEffect(() => {
    const handleGlobalError = (event) => {
      fetch('/api/debug/client_error', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          message: event.message || 'Client JavaScript Error',
          source: 'FRONTEND',
          details: event.error?.stack || `${event.filename}:${event.lineno}:${event.colno}`,
        }),
      }).catch(() => {});
    };

    const handleUnhandledRejection = (event) => {
      const reason = event.reason;
      fetch('/api/debug/client_error', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          message: `Unhandled Promise Rejection: ${reason?.message || reason || 'Unknown'}`,
          source: 'FRONTEND',
          details: reason?.stack || String(reason),
        }),
      }).catch(() => {});
    };

    window.addEventListener('error', handleGlobalError);
    window.addEventListener('unhandledrejection', handleUnhandledRejection);

    return () => {
      window.removeEventListener('error', handleGlobalError);
      window.removeEventListener('unhandledrejection', handleUnhandledRejection);
    };
  }, []);

  // 3. Debug hotkey triggers (Ctrl+Shift+D, F12, Ctrl+`, custom GTK event)
  useEffect(() => {
    const handleKeyDown = (e) => {
      const isF12 = e.key === 'F12';
      const isCtrlShiftD = (e.ctrlKey || e.metaKey) && e.shiftKey && (e.key === 'D' || e.key === 'd');
      const isCtrlBacktick = (e.ctrlKey || e.metaKey) && e.key === '`';

      if (isF12 || isCtrlShiftD || isCtrlBacktick) {
        e.preventDefault();
        setIsDebugOpen((prev) => !prev);
      }
    };

    const handleCustomToggle = () => {
      setIsDebugOpen((prev) => !prev);
    };

    window.addEventListener('keydown', handleKeyDown);
    window.addEventListener('spectra-toggle-debug', handleCustomToggle);

    return () => {
      window.removeEventListener('keydown', handleKeyDown);
      window.removeEventListener('spectra-toggle-debug', handleCustomToggle);
    };
  }, []);

  // 4. Viewport Dynamic Monitor Autoscaling
  useEffect(() => {
    const updateScale = () => {
      let scale = 1.0;
      if (scaleMode === 'auto') {
        const w = window.innerWidth;
        const h = window.innerHeight;
        // Baseline design canvas: 1480 x 880
        if (w < 1440 || h < 840) {
          scale = Math.max(0.78, Math.min(w / 1480, h / 880));
        } else if (w >= 2500) {
          scale = Math.min(1.30, w / 1920);
        } else {
          scale = 1.0;
        }
      } else if (typeof scaleMode === 'number') {
        scale = scaleMode;
      }
      scale = Math.round(scale * 100) / 100;
      setCurrentScale(scale);
      document.documentElement.style.fontSize = `${Math.round(16 * scale * 100) / 100}px`;
    };

    updateScale();
    window.addEventListener('resize', updateScale);
    return () => window.removeEventListener('resize', updateScale);
  }, [scaleMode]);

  // 5. Periodic status poll for top-bar debug error counter badge
  useEffect(() => {
    let active = true;
    let controller = null;
    let lastErrorCount = -1;
    let lastWarnCount = -1;
    let lastLogId = null;
    let lastBuild = null;

    const checkCounts = async () => {
      if (!active || document.visibilityState === 'hidden') return;
      if (controller) {
        try { controller.abort(); } catch {}
      }
      controller = new AbortController();
      try {
        const res = await fetch('/api/debug/status', { signal: controller.signal });
        const data = await res.json();
        if (!active || !data || !data.success) return;

        const nextErrorCount = data.error_count || 0;
        const nextWarnCount = data.warn_count || 0;
        const logsArr = Array.isArray(data.logs) ? data.logs : [];
        const latestLogId = logsArr.length > 0 ? (logsArr[logsArr.length - 1]?.id ?? null) : null;
        const nextBuild = data.build ?? null;

        const countsChanged = nextErrorCount !== lastErrorCount || nextWarnCount !== lastWarnCount;
        if (countsChanged) {
          lastErrorCount = nextErrorCount;
          lastWarnCount = nextWarnCount;
          setDebugCounts({
            errorCount: nextErrorCount,
            warnCount: nextWarnCount,
          });
        }

        if (
          lastBuild === null ||
          nextBuild !== lastBuild ||
          latestLogId !== lastLogId ||
          countsChanged
        ) {
          lastBuild = nextBuild;
          lastLogId = latestLogId;
          setDebugSummary(data);
        }
      } catch (e) {}
    };

    checkCounts();
    const interval = setInterval(checkCounts, 3500);
    const handleVisibility = () => {
      if (document.visibilityState === 'visible') {
        checkCounts();
      }
    };
    document.addEventListener('visibilitychange', handleVisibility);

    return () => {
      active = false;
      clearInterval(interval);
      document.removeEventListener('visibilitychange', handleVisibility);
      if (controller) {
        try { controller.abort(); } catch {}
      }
    };
  }, []);

  return (
    <>
      <SpectraWorkspace
        lang={lang}
        setLang={handleChangeLang}
        isDebugOpen={isDebugOpen}
        setIsDebugOpen={setIsDebugOpen}
        debugCounts={debugCounts}
        debugSummary={debugSummary}
        scaleMode={scaleMode}
        setScaleMode={setScaleMode}
        currentScale={currentScale}
      />
      {isDebugOpen && (
        <Suspense fallback={null}>
          <DebugConsoleModal isOpen={isDebugOpen} onClose={() => setIsDebugOpen(false)} lang={lang} />
        </Suspense>
      )}
    </>
  );
}
