import React, { useState, useEffect, useRef } from 'react';
import SpectraWorkspace from './components/SpectraWorkspace';
import DebugConsoleModal from './components/DebugConsoleModal';

export default function App() {
  const [lang, setLang] = useState(() => {
    try {
      const saved = localStorage.getItem('spectra_lang');
      return saved === 'cs' ? 'cs' : 'en';
    } catch {
      return 'en';
    }
  });
  const prefsLoadedRef = useRef(false);
  const [isDebugOpen, setIsDebugOpen] = useState(false);
  const [debugCounts, setDebugCounts] = useState({ errorCount: 0, warnCount: 0 });
  const [debugSummary, setDebugSummary] = useState(null);
  const [scaleMode, setScaleMode] = useState('auto'); // 'auto' | 0.85 | 1.0 | 1.15
  const [currentScale, setCurrentScale] = useState(1.0);

  useEffect(() => {
    let active = true;
    fetch('/api/ui_prefs')
      .then((r) => (r.ok ? r.json() : null))
      .then((d) => {
        if (!active) return;
        const diskLang = d?.prefs?.lang;
        let lsLang = null;
        try {
          lsLang = localStorage.getItem('spectra_lang');
        } catch {}
        if (!lsLang && (diskLang === 'cs' || diskLang === 'en')) {
          setLang(diskLang);
          try {
            localStorage.setItem('spectra_lang', diskLang);
          } catch {}
        }
        prefsLoadedRef.current = true;
      })
      .catch(() => {
        prefsLoadedRef.current = true;
      });
    return () => {
      active = false;
    };
  }, []);

  useEffect(() => {
    try {
      localStorage.setItem('spectra_lang', lang);
    } catch {}
    document.documentElement.lang = lang;
    if (prefsLoadedRef.current) {
      fetch('/api/ui_prefs', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ lang }),
      }).catch(() => {});
    }
  }, [lang]);

  // 1. Native Desktop App mode lifecycle: heartbeat & window_closed / close beacon
  useEffect(() => {
    const interval = setInterval(() => {
      fetch('/api/app/heartbeat', { method: 'POST', keepalive: true }).catch(() => {});
    }, 2000);

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
    const checkCounts = async () => {
      try {
        const res = await fetch('/api/debug/status');
        const data = await res.json();
        if (data && data.success) {
          setDebugSummary(data);
          setDebugCounts({
            errorCount: data.error_count || 0,
            warnCount: data.warn_count || 0,
          });
        }
      } catch (e) {}
    };

    checkCounts();
    const interval = setInterval(checkCounts, 3500);
    return () => clearInterval(interval);
  }, []);

  return (
    <>
      <SpectraWorkspace
        lang={lang}
        setLang={setLang}
        isDebugOpen={isDebugOpen}
        setIsDebugOpen={setIsDebugOpen}
        debugCounts={debugCounts}
        debugSummary={debugSummary}
        scaleMode={scaleMode}
        setScaleMode={setScaleMode}
        currentScale={currentScale}
      />
      <DebugConsoleModal isOpen={isDebugOpen} onClose={() => setIsDebugOpen(false)} lang={lang} />
    </>
  );
}
