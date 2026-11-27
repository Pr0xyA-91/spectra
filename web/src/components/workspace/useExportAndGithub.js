import { useState, useEffect, useCallback } from 'react';
import { triggerBrowserDownload } from './workspaceHelpers';
import { copyTextSafe } from '../../utils/fetchSafe';

export function useExportAndGithub({
  selectedPort,
  aiEnabled,
  aiModel,
  handleToggleAi,
  beginAiWork,
  endAiWork,
  setStatsData,
  showExportModal,
  setShowExportModal,
  showConfigModal,
  showIssueModal,
}) {
  const [exportPrefix, setExportPrefix] = useState('');
  const [joeCsvContent, setJoeCsvContent] = useState('');
  const [joeFileName, setJoeFileName] = useState('');
  const [isDumping, setIsDumping] = useState(false);
  const [exportStatus, setExportStatus] = useState({ loading: false, msg: '', error: false });
  const [capturedBundle, setCapturedBundle] = useState(null);
  const [capturedId, setCapturedId] = useState('');
  const [capturedFilename, setCapturedFilename] = useState('');
  const [browserDownloadAvailable, setBrowserDownloadAvailable] = useState(null);
  const [githubAuth, setGithubAuth] = useState({
    authenticated: false,
    login: null,
    method: null,
    device_flow_available: false,
  });
  const [deviceFlow, setDeviceFlow] = useState(null);
  const [showPatInput, setShowPatInput] = useState(false);
  const [patInput, setPatInput] = useState('');
  const [isUploading, setIsUploading] = useState(false);
  const [uploadResult, setUploadResult] = useState(null);
  const [copiedCode, setCopiedCode] = useState(false);

  const [useAiJoeMatch, setUseAiJoeMatch] = useState(false);
  const [isCalibratingOffsets, setIsCalibratingOffsets] = useState(false);
  const [offsetCalibration, setOffsetCalibration] = useState(null);
  const [offsetAppliedLocally, setOffsetAppliedLocally] = useState(false);

  useEffect(() => {
    if (!aiEnabled) {
      setUseAiJoeMatch(false);
    }
  }, [aiEnabled]);

  const fetchGithubStatus = useCallback(async () => {
    try {
      const res = await fetch('/api/github/auth/status');
      if (res.ok) {
        const data = await res.json();
        setGithubAuth(data);
      }
    } catch (e) {
      console.warn('Failed to fetch github status:', e);
    }
  }, []);

  // Hydrate persisted GitHub authentication immediately at app startup
  useEffect(() => {
    fetchGithubStatus();
  }, [fetchGithubStatus]);

  // Also refresh when opening Export, Config, or Report Issue modals
  useEffect(() => {
    if (showExportModal || showConfigModal || showIssueModal) {
      fetchGithubStatus();
    }
  }, [showExportModal, showConfigModal, showIssueModal, fetchGithubStatus]);

  // Clear sensitive PAT input whenever ExportCaptureModal and ConfigModal are closed
  useEffect(() => {
    if (!showExportModal && !showConfigModal) {
      setPatInput('');
      setShowPatInput(false);
    }
  }, [showExportModal, showConfigModal]);

  // GitHub Device Flow Polling Loop
  useEffect(() => {
    if (!deviceFlow?.device_code) return;
    let cancelled = false;
    let pollTimer = null;
    let consecutiveErrors = 0;

    const poll = async (intervalSec) => {
      if (cancelled) return;
      try {
        const res = await fetch('/api/github/auth/device/poll', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ device_code: deviceFlow.device_code, interval: intervalSec }),
        });
        if (!res.ok) {
          throw new Error(`HTTP ${res.status}`);
        }
        const data = await res.json();
        if (cancelled) return;
        consecutiveErrors = 0;

        if (data.status === 'complete' && data.login) {
          setGithubAuth({ authenticated: true, login: data.login, method: 'device_flow', device_flow_available: true });
          setDeviceFlow(null);
          setExportStatus({ loading: false, msg: `✓ Signed in as @${data.login}!`, error: false });
          return;
        }

        if (data.status === 'slow_down') {
          const nextInterval = data.interval || intervalSec + 5;
          pollTimer = setTimeout(() => poll(nextInterval), nextInterval * 1000);
          return;
        }

        if (data.status === 'pending') {
          pollTimer = setTimeout(() => poll(intervalSec), intervalSec * 1000);
          return;
        }

        // Error / expired / denied
        setDeviceFlow(null);
        setExportStatus({ loading: false, msg: data.error || 'Device authorization ended.', error: true });
      } catch (err) {
        if (!cancelled) {
          consecutiveErrors += 1;
          if (consecutiveErrors < 3) {
            const retrySec = Math.max(intervalSec, 5);
            pollTimer = setTimeout(() => poll(retrySec), retrySec * 1000);
            return;
          }
          setDeviceFlow(null);
          setExportStatus({ loading: false, msg: `Device poll error: ${err.message}`, error: true });
        }
      }
    };

    pollTimer = setTimeout(() => poll(deviceFlow.interval || 5), (deviceFlow.interval || 5) * 1000);
    return () => {
      cancelled = true;
      if (pollTimer) clearTimeout(pollTimer);
    };
  }, [deviceFlow]);

  const handleCancelDeviceFlow = useCallback(() => setDeviceFlow(null), []);

  const handleTriggerExport = async (fmt) => {
    if (!selectedPort) return;
    setExportStatus({ loading: true, msg: 'Prompting file save location...', error: false });
    try {
      const prefixParam = exportPrefix.trim() ? `&prefix=${encodeURIComponent(exportPrefix.trim())}` : '';
      const res = await fetch(`/api/export?port=${encodeURIComponent(selectedPort)}&format=${fmt}&save_dialog=1${prefixParam}`);
      let data;
      const contentType = res.headers.get('content-type') || '';
      if (contentType.includes('application/json')) {
        data = await res.json();
      } else {
        const text = await res.text();
        data = { success: false, error: !res.ok ? `Server error (${res.status}): ${text.slice(0, 200)}` : text };
      }

      if (data.success && data.saved_path) {
        setExportStatus({ loading: false, msg: `✓ Saved: ${data.saved_path}`, error: false });
        setTimeout(() => {
          setShowExportModal(false);
          setExportStatus({ loading: false, msg: '', error: false });
        }, 2200);
      } else if (data.cancelled) {
        setExportStatus({ loading: false, msg: 'Export cancelled.', error: false });
        if (data.content) {
          setBrowserDownloadAvailable({ content: data.content, filename: data.filename || `spectra_export.${fmt}`, mime: data.mime || 'text/plain' });
        }
      } else if (data.dialog_unavailable) {
        if (data.content) {
          triggerBrowserDownload(data.content, data.filename || `spectra_export.${fmt}`, data.mime || 'text/plain');
          setExportStatus({ loading: false, msg: `✓ Saved via browser download (${data.filename})`, error: false });
        } else {
          setExportStatus({ loading: false, msg: `Dialog unavailable: ${data.error}`, error: true });
        }
      } else {
        setExportStatus({ loading: false, msg: `Export failed: ${data.error || 'Unknown error'}`, error: true });
      }
    } catch (err) {
      setExportStatus({ loading: false, msg: `Export request error: ${err.message}`, error: true });
    }
  };

  const handleJoeFileUpload = (e) => {
    const file = e.target.files?.[0];
    if (!file) {
      setJoeCsvContent('');
      setJoeFileName('');
      return;
    }
    setJoeFileName(file.name);
    const reader = new FileReader();
    reader.onload = (event) => {
      setJoeCsvContent(event.target?.result || '');
    };
    reader.readAsText(file);
  };

  const handleTriggerDumpCapture = async () => {
    if (!selectedPort) return;
    setIsDumping(true);
    const usingAi = Boolean(aiEnabled && useAiJoeMatch && joeCsvContent);
    if (usingAi) beginAiWork();
    setExportStatus({ loading: true, msg: 'Sweeping EEPROM & capturing hardware dump...', error: false });
    try {
      const res = await fetch('/api/export_capture', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          port: selectedPort,
          joe_csv: joeCsvContent,
          prefix: exportPrefix.trim() || undefined,
          save_dialog: false,
          use_ollama: usingAi,
          model: aiModel || undefined,
        }),
      });
      let data;
      const contentType = res.headers.get('content-type') || '';
      if (contentType.includes('application/json')) {
        data = await res.json();
      } else {
        const text = await res.text();
        data = { success: false, error: !res.ok ? `Server error (${res.status}): ${text.slice(0, 200)}` : text };
      }

      if (data.success && data.bundle) {
        setCapturedBundle(data.bundle);
        setCapturedId(data.capture_id || '');
        setCapturedFilename(data.filename || 'spectra_capture.json');
        const words = Object.keys(data.bundle?.eeprom_words || {}).length;
        const model = data.bundle?.identity?.model_name || 'Machine';
        setExportStatus({
          loading: false,
          msg: `✓ Capture ready: ${model} (${words} words). Choose Save or Upload below.`,
          error: false,
        });
      } else {
        setExportStatus({ loading: false, msg: `Dump failed: ${data.error || 'Unknown error'}`, error: true });
      }
    } catch (err) {
      setExportStatus({ loading: false, msg: `Dump capture failed: ${err.message}`, error: true });
    } finally {
      setIsDumping(false);
      if (usingAi) endAiWork();
    }
  };

  const handleCalibrateOffsetsFromJoe = async (enableFirst = false) => {
    if (!aiEnabled && !enableFirst) {
      setExportStatus({ loading: false, msg: 'Local AI is OFF. Enable Local AI to run EEPROM offset calibration.', error: true });
      return;
    }
    if (enableFirst && !aiEnabled) {
      const enabledOk = await handleToggleAi(true);
      if (!enabledOk) return;
    }
    if (!joeCsvContent && !(capturedBundle?.joe_ground_truth?.raw_lines?.length)) {
      setExportStatus({ loading: false, msg: 'Attach a J.O.E. CSV export first so Local AI has ground-truth counts to match.', error: true });
      return;
    }
    setIsCalibratingOffsets(true);
    setOffsetAppliedLocally(false);
    beginAiWork();
    setExportStatus({ loading: true, msg: 'Local AI is matching J.O.E. counts against EEPROM offsets...', error: false });
    try {
      const res = await fetch('/api/ai/calibrate_offsets', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          capture_id: capturedId || undefined,
          bundle: capturedBundle || undefined,
          port: selectedPort,
          joe_csv: joeCsvContent || undefined,
          model: aiModel || undefined,
        }),
      });
      const data = await res.json();
      if (data.success && data.override) {
        if (data.bundle) setCapturedBundle(data.bundle);
        if (data.capture_id) setCapturedId(data.capture_id);
        setOffsetCalibration(data.override);
        setExportStatus({
          loading: false,
          msg: `✓ AI matched ${data.matched_products} product + ${data.matched_maintenance} maintenance offsets. Review and click Fix Locally or Report Upstream.`,
          error: false,
        });
      } else {
        setExportStatus({ loading: false, msg: `Offset calibration failed: ${data.error || 'Unknown error'}`, error: true });
      }
    } catch (err) {
      setExportStatus({ loading: false, msg: `Offset calibration error: ${err.message}`, error: true });
    } finally {
      setIsCalibratingOffsets(false);
      endAiWork();
    }
  };

  const handleApplyOffsetFixLocally = async () => {
    if (!offsetCalibration) return;
    setExportStatus({ loading: true, msg: 'Saving local EEPROM offset override & refreshing dashboard...', error: false });
    try {
      const res = await fetch('/api/offsets/apply_local', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          capture_id: capturedId || undefined,
          override: offsetCalibration,
          port: selectedPort,
        }),
      });
      const data = await res.json();
      if (data.success) {
        setOffsetAppliedLocally(true);
        if (data.bundle) setCapturedBundle(data.bundle);
        if (data.updated_stats) setStatsData(data.updated_stats);
        setExportStatus({
          loading: false,
          msg: `✓ Offset fix saved locally (${data.saved_key})! Machine readings are updated now. You can also upload below so this fix is included in the next SPECTRA update.`,
          error: false,
        });
      } else {
        setExportStatus({ loading: false, msg: `Failed to apply fix: ${data.error || 'Error'}`, error: true });
      }
    } catch (err) {
      setExportStatus({ loading: false, msg: `Apply local fix error: ${err.message}`, error: true });
    }
  };

  const handleSaveLocally = async () => {
    if (!capturedBundle && !selectedPort) return;
    setExportStatus({ loading: true, msg: 'Prompting file save location...', error: false });
    try {
      const res = await fetch('/api/export_capture', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          capture_id: capturedId,
          port: selectedPort,
          joe_csv: joeCsvContent,
          prefix: exportPrefix.trim() || undefined,
          save_dialog: true,
        }),
      });
      let data;
      const contentType = res.headers.get('content-type') || '';
      if (contentType.includes('application/json')) {
        data = await res.json();
      } else {
        const text = await res.text();
        data = { success: false, error: !res.ok ? `Server error (${res.status}): ${text.slice(0, 200)}` : text };
      }

      if (data.success && data.saved_path) {
        setExportStatus({ loading: false, msg: `✓ Saved locally: ${data.saved_path}`, error: false });
      } else if (data.cancelled) {
        setExportStatus({ loading: false, msg: 'Native save cancelled.', error: false });
        setBrowserDownloadAvailable({ bundle: data.bundle || capturedBundle, filename: data.filename || capturedFilename });
      } else if (data.dialog_unavailable) {
        triggerBrowserDownload(data.bundle || capturedBundle, data.filename || capturedFilename);
        setExportStatus({ loading: false, msg: `✓ Saved via browser download (${data.filename || capturedFilename})`, error: false });
      } else {
        setExportStatus({ loading: false, msg: `Save failed: ${data.error || 'Unknown error'}`, error: true });
      }
    } catch (err) {
      setExportStatus({ loading: false, msg: `Save error: ${err.message}`, error: true });
    }
  };

  const handleUploadToCommunity = async () => {
    if (!capturedBundle && !capturedId) return;
    setIsUploading(true);
    setExportStatus({ loading: true, msg: 'Uploading capture to community repository...', error: false });
    try {
      const res = await fetch('/api/upload-capture', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          capture_id: capturedId,
          capture_data: capturedBundle,
        }),
      });
      let data;
      const contentType = res.headers.get('content-type') || '';
      if (contentType.includes('application/json')) {
        data = await res.json();
      } else {
        const text = await res.text();
        data = { success: false, error: !res.ok ? `Server error (${res.status}): ${text.slice(0, 200)}` : text };
      }

      if (data.success) {
        setUploadResult({ success: true, url: data.url, msg: data.message });
        setExportStatus({ loading: false, msg: '✓ Uploaded to community repository!', error: false });
      } else {
        setUploadResult({ success: false, url: data.url, msg: data.message || data.error });
        setExportStatus({ loading: false, msg: `Upload failed: ${data.message || data.error || 'Error'}`, error: true });
      }
    } catch (err) {
      setExportStatus({ loading: false, msg: `Upload error: ${err.message}`, error: true });
    } finally {
      setIsUploading(false);
    }
  };

  const handleStartDeviceFlow = async () => {
    setExportStatus({ loading: true, msg: 'Requesting GitHub device authorization...', error: false });
    try {
      const res = await fetch('/api/github/auth/device/start', { method: 'POST' });
      const contentType = res.headers.get('content-type') || '';
      const data = contentType.includes('application/json')
        ? await res.json()
        : { success: false, error: `HTTP ${res.status}` };
      if (res.ok && data.success) {
        setDeviceFlow(data);
        setExportStatus({ loading: false, msg: `Enter code ${data.user_code} on GitHub`, error: false });
      } else {
        setExportStatus({ loading: false, msg: data.error || `Device flow failed (HTTP ${res.status})`, error: true });
      }
    } catch (err) {
      setExportStatus({ loading: false, msg: `Device auth error: ${err.message}`, error: true });
    }
  };

  const handleSavePat = async () => {
    if (!patInput.trim()) return;
    setExportStatus({ loading: true, msg: 'Validating GitHub personal access token...', error: false });
    try {
      const res = await fetch('/api/github/auth/token', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ token: patInput.trim() }),
      });
      const contentType = res.headers.get('content-type') || '';
      const data = contentType.includes('application/json')
        ? await res.json()
        : { success: false, error: `HTTP ${res.status}` };
      if (res.ok && data.success) {
        setGithubAuth({ authenticated: true, login: data.login, method: 'pat', device_flow_available: githubAuth.device_flow_available });
        setPatInput('');
        setShowPatInput(false);
        setExportStatus({ loading: false, msg: `✓ Connected as @${data.login}!`, error: false });
      } else {
        setExportStatus({ loading: false, msg: data.error || `Invalid personal access token (HTTP ${res.status})`, error: true });
      }
    } catch (err) {
      setExportStatus({ loading: false, msg: `Token auth error: ${err.message}`, error: true });
    }
  };

  const handleLogout = async () => {
    try {
      const res = await fetch('/api/github/auth/logout', { method: 'POST' });
      if (!res.ok) {
        throw new Error(`HTTP ${res.status}`);
      }
      await fetchGithubStatus();
      setDeviceFlow(null);
      setExportStatus({ loading: false, msg: 'Signed out from GitHub.', error: false });
    } catch (err) {
      setExportStatus({ loading: false, msg: `Logout error: ${err.message}`, error: true });
    }
  };

  const handleCopyDeviceCode = useCallback(async (code) => {
    if (!code) return;
    const ok = await copyTextSafe(code);
    if (ok) {
      setCopiedCode(true);
      setTimeout(() => setCopiedCode(false), 2000);
    }
  }, []);

  const handleResetCapture = () => {
    setCapturedBundle(null);
    setCapturedId('');
    setCapturedFilename('');
    setUploadResult(null);
    setBrowserDownloadAvailable(null);
    setOffsetCalibration(null);
    setOffsetAppliedLocally(false);
  };

  return {
    exportPrefix,
    setExportPrefix,
    joeCsvContent,
    joeFileName,
    isDumping,
    exportStatus,
    capturedBundle,
    capturedFilename,
    browserDownloadAvailable,
    githubAuth,
    deviceFlow,
    setDeviceFlow,
    showPatInput,
    setShowPatInput,
    patInput,
    setPatInput,
    isUploading,
    uploadResult,
    copiedCode,
    useAiJoeMatch,
    setUseAiJoeMatch,
    isCalibratingOffsets,
    offsetCalibration,
    offsetAppliedLocally,
    handleCancelDeviceFlow,
    handleTriggerExport,
    handleJoeFileUpload,
    handleTriggerDumpCapture,
    handleCalibrateOffsetsFromJoe,
    handleApplyOffsetFixLocally,
    handleSaveLocally,
    handleUploadToCommunity,
    handleStartDeviceFlow,
    handleSavePat,
    handleLogout,
    handleCopyDeviceCode,
    handleResetCapture,
  };
}
