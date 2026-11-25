import React from 'react';
import { AlertTriangle, RotateCcw, RefreshCw } from 'lucide-react';

/**
 * Tactical Dark React ErrorBoundary supporting:
 * - variant="app"   : full-viewport recovery screen around <App />
 * - variant="panel" : localized fallback around lazy tabs / modals
 */
export default class ErrorBoundary extends React.Component {
  constructor(props) {
    super(props);
    this.state = { hasError: false, error: null };
    this.handleReset = this.handleReset.bind(this);
    this.handleReload = this.handleReload.bind(this);
  }

  static getDerivedStateFromError(error) {
    return { hasError: true, error };
  }

  componentDidCatch(error, errorInfo) {
    try {
      const payload = {
        message: `React ErrorBoundary (${this.props.variant || 'panel'}): ${error?.message || String(error || 'Unknown render error')}`,
        source: 'FRONTEND',
        details: [error?.stack, errorInfo?.componentStack].filter(Boolean).join('\n\n'),
      };
      fetch('/api/debug/client_error', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      }).catch(() => {});
    } catch {
      // Never throw inside error boundary reporting
    }
  }

  handleReset() {
    this.setState({ hasError: false, error: null });
    if (typeof this.props.onReset === 'function') {
      try {
        this.props.onReset();
      } catch {
        // Ignore user reset hook error
      }
    }
  }

  handleReload() {
    try {
      window.location.reload();
    } catch {
      this.handleReset();
    }
  }

  render() {
    if (!this.state.hasError) {
      return this.props.children;
    }

    const isApp = this.props.variant === 'app';
    const message = this.state.error?.message || 'Unexpected UI rendering failure.';

    return (
      <div
        className={
          isApp
            ? 'min-h-screen w-full bg-[#070709] text-zinc-100 flex items-center justify-center p-6 font-mono'
            : 'w-full rounded-lg border border-rose-500/60 bg-[#0E0E12]/95 text-zinc-100 p-6 font-mono shadow-lg'
        }
      >
        <div className="max-w-lg w-full border border-rose-500/50 bg-[#121218] rounded-lg p-5 space-y-4 shadow-[0_0_24px_rgba(244,63,94,0.18)]">
          <div className="flex items-start gap-3">
            <div className="p-2 rounded bg-rose-950/70 border border-rose-500/60 text-rose-400 shrink-0">
              <AlertTriangle className="w-5 h-5" />
            </div>
            <div className="min-w-0 flex-1 space-y-1">
              <div className="text-[11px] font-bold uppercase tracking-widest text-rose-400">
                {isApp ? 'SPECTRA WORKSPACE RECOVERY' : 'PANEL RENDER FAULT'}
              </div>
              <h2 className="text-sm font-extrabold text-white">
                {this.props.title || (isApp ? 'Application UI encountered a runtime exception' : 'This module encountered a rendering error')}
              </h2>
              <p className="text-xs text-zinc-400 break-words bg-black/50 border border-zinc-800 rounded p-2.5">
                {message}
              </p>
            </div>
          </div>

          <div className="flex flex-wrap items-center justify-end gap-2 pt-1">
            <button
              type="button"
              onClick={this.handleReset}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded bg-[#FCEE09] hover:bg-yellow-300 text-black font-extrabold text-xs cursor-pointer transition-colors"
            >
              <RotateCcw className="w-3.5 h-3.5" />
              <span>Retry / Reset Panel</span>
            </button>
            <button
              type="button"
              onClick={this.handleReload}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded bg-zinc-800 hover:bg-zinc-700 border border-zinc-600 text-zinc-100 font-bold text-xs cursor-pointer transition-colors"
            >
              <RefreshCw className="w-3.5 h-3.5" />
              <span>Reload Workspace</span>
            </button>
          </div>
        </div>
      </div>
    );
  }
}
