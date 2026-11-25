import React, { useState, useMemo } from 'react';
import {
  ShieldCheck,
  AlertTriangle,
  CheckCircle2,
  Wrench,
  FileText,
  Download,
  Coffee,
  Sparkles,
  Layers,
  ChevronRight,
  Info,
  Power,
  RefreshCw,
  Upload,
  Check,
  Send,
  Sliders,
  X,
} from 'lucide-react';
import { createTranslator, txAdvisorCard, txBeverageName, txVal } from '../i18n/translations';
import { safeExternalUrl } from '../utils/urlSafety';

const MAX_REF_FILE_BYTES = 10 * 1024 * 1024; // 10 MiB client-side upload guard

/**
 * Overview Tab: AI Diagnostic Health Advisor & Beverage Recipe Analytics
 * Replicates 100% of the old UI Overview Tab:
 * - Diagnostic Health Scorecard (0-100%)
 * - Heuristic Maintenance Advisor Cards (Descaling, Switch bounce, BU mechanical health)
 * - Technician Field Service Inspection Checklist
 * - Beverage Specialty Recipe Analytics with proportional distribution bars
 * - 1-Click Customer Service Report & Multi-format Export triggers
 * - Inline Local AI Bench Triage, Customer Summary & CSV/Screenshot Offset Calibrator
 */
function DiagnosticAdvisorTab({
  theme,
  lang = 'en',
  statsData,
  liveData = null,
  liveDataRef = null,
  machineModel = '',
  selectedPort,
  onOpenServiceReport,
  onOpenExport,
  onInterrogate,
  isInterrogating,
  aiEnabled = false,
  aiModel = '',
  onToggleAi = null,
  beginAiWork = null,
  endAiWork = null,
  aiServiceSummary = null,
  setAiServiceSummary = null,
  onStatsUpdated = null,
  onOpenConfig = null,
}) {
  const t = useMemo(() => createTranslator(lang), [lang]);
  const [checklist, setChecklist] = useState({
    chk1: true, // Visual inspection of silicone pressure lines & brass fittings
    chk2: true, // Safety thermal cutoff continuity (TB1: 0.1Ω, TB2: 0.1Ω)
    chk3: false, // Descaling cycle execution & flowmeter verification
    chk4: true, // Clean microswitch contact leaves on rear chassis
  });
  const [aiTriage, setAiTriage] = useState(null);
  const [isRunningTriage, setIsRunningTriage] = useState(false);
  const [isGeneratingSummary, setIsGeneratingSummary] = useState(false);
  const [aiError, setAiError] = useState('');

  // Inline Offset Calibrator (.csv, .txt notes, or J.O.E./Legacy Screenshot + US/EU Identity)
  const [refFileName, setRefFileName] = useState('');
  const [refCsvText, setRefCsvText] = useState('');
  const [refImageB64, setRefImageB64] = useState('');
  const [refIsImage, setRefIsImage] = useState(false);
  const [refNotesText, setRefNotesText] = useState('');
  const [manualModelName, setManualModelName] = useState('');
  const [manualArticleNumber, setManualArticleNumber] = useState('');
  const [manualSerialNumber, setManualSerialNumber] = useState('');
  const [manualMarketRegion, setManualMarketRegion] = useState('');
  const [isCalibrating, setIsCalibrating] = useState(false);
  const [calResult, setCalResult] = useState(null);
  const [calNotice, setCalNotice] = useState({ msg: '', error: false, url: '' });
  const [appliedLocal, setAppliedLocal] = useState(false);
  const [showUploadPromptModal, setShowUploadPromptModal] = useState(false);
  const [isUploadingContrib, setIsUploadingContrib] = useState(false);

  const handleRunAiTriage = async () => {
    if (!aiEnabled) return;
    setIsRunningTriage(true);
    setAiError('');
    if (beginAiWork) beginAiWork();
    try {
      const currentLive = liveDataRef?.current ?? liveData;
      const telemetryPayload = currentLive
        ? currentLive
        : machineModel
        ? { machine_model: machineModel }
        : {};
      const res = await fetch('/api/advisor/ai_triage', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          telemetry: telemetryPayload,
          stats: statsData || {},
          model: aiModel || undefined,
          lang,
        }),
      });
      const contentType = res.headers.get('content-type') || '';
      const data = contentType.includes('application/json')
        ? await res.json()
        : { success: false, error: `HTTP ${res.status}` };
      if (data.success && data.triage) {
        setAiTriage({ ...data.triage, model: data.model });
      } else {
        setAiError(data.error || 'Failed to generate AI fault triage.');
      }
    } catch (err) {
      setAiError(err.message);
    } finally {
      setIsRunningTriage(false);
      if (endAiWork) endAiWork();
    }
  };

  const handleGenerateServiceSummary = async () => {
    if (!aiEnabled) return;
    setIsGeneratingSummary(true);
    setAiError('');
    if (beginAiWork) beginAiWork();
    try {
      const res = await fetch('/api/service_report/ai_summary', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          stats: statsData || {},
          model: aiModel || undefined,
          lang,
        }),
      });
      const contentType = res.headers.get('content-type') || '';
      const data = contentType.includes('application/json')
        ? await res.json()
        : { success: false, error: `HTTP ${res.status}` };
      if (data.success && data.customer_summary) {
        if (setAiServiceSummary) setAiServiceSummary(data);
      } else {
        setAiError(data.error || 'Failed to generate customer summary.');
      }
    } catch (err) {
      setAiError(err.message);
    } finally {
      setIsGeneratingSummary(false);
      if (endAiWork) endAiWork();
    }
  };

  const handleReferenceUpload = (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setCalResult(null);
    setCalNotice({ msg: '', error: false, url: '' });
    setAppliedLocal(false);

    if (file.size > MAX_REF_FILE_BYTES) {
      const mb = (file.size / (1024 * 1024)).toFixed(1);
      setRefFileName('');
      setRefCsvText('');
      setRefImageB64('');
      setRefIsImage(false);
      setCalNotice({
        msg: `File "${file.name}" (${mb} MiB) exceeds the 10 MiB client upload limit.`,
        error: true,
        url: '',
      });
      e.target.value = '';
      return;
    }

    setRefFileName(file.name);

    const lower = file.name.toLowerCase();
    const isImg = file.type.startsWith('image/') || /\.(png|jpe?g|webp|bmp)$/i.test(lower);
    setRefIsImage(isImg);

    const reader = new FileReader();
    reader.onload = (evt) => {
      const val = String(evt.target?.result || '');
      if (isImg) {
        setRefImageB64(val);
        setRefCsvText('');
      } else {
        setRefCsvText(val);
        setRefImageB64('');
      }
    };
    if (isImg) reader.readAsDataURL(file);
    else reader.readAsText(file);
  };

  const hasAnyCalibInput = Boolean(
    refCsvText ||
      refImageB64 ||
      refNotesText.trim() ||
      manualModelName.trim() ||
      manualArticleNumber.trim() ||
      manualSerialNumber.trim() ||
      manualMarketRegion.trim()
  );

  const handleCalibrateUploadedRef = async () => {
    if (!aiEnabled) return;
    if (!hasAnyCalibInput) {
      setCalNotice({ msg: t('msgSelectRefFirst'), error: true, url: '' });
      return;
    }
    setIsCalibrating(true);
    setCalNotice({ msg: '', error: false, url: '' });
    setAppliedLocal(false);
    if (beginAiWork) beginAiWork();
    try {
      const res = await fetch('/api/offsets/calibrate_upload', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          file_name: refFileName || (refNotesText.trim() ? 'manual_notes.txt' : 'reference.csv'),
          csv_text: refCsvText || undefined,
          image_b64: refImageB64 || undefined,
          user_notes: refNotesText.trim() || undefined,
          user_model_name: manualModelName.trim() || undefined,
          user_article_number: manualArticleNumber.trim() || undefined,
          user_serial_number: manualSerialNumber.trim() || undefined,
          user_market_region: manualMarketRegion.trim() || undefined,
          port: selectedPort,
          model: aiModel || undefined,
        }),
      });
      const data = await res.json();
      if (!res.ok || !data.success) {
        setCalNotice({ msg: data.error || 'Calibration failed.', error: true, url: '' });
      } else {
        setCalResult(data);
        const det = data.detected_identity || data.override || {};
        if (det.model_name && det.model_name !== 'Unknown' && !manualModelName.trim()) {
          setManualModelName(det.model_name);
        }
        if (det.article_number && det.article_number !== 'unknown' && !manualArticleNumber.trim()) {
          setManualArticleNumber(det.article_number);
        }
        if (det.serial_number && det.serial_number !== 'N/A' && !manualSerialNumber.trim()) {
          setManualSerialNumber(det.serial_number);
        }
        if (det.market_region && det.market_region !== 'N/A' && !manualMarketRegion.trim()) {
          setManualMarketRegion(det.market_region);
        }
        setCalNotice({
          msg: t('msgMatchedOffsets', { products: data.matched_products, maintenance: data.matched_maintenance }),
          error: false,
          url: '',
        });
      }
    } catch (err) {
      setCalNotice({ msg: `Calibration error: ${err.message}`, error: true, url: '' });
    } finally {
      setIsCalibrating(false);
      if (endAiWork) endAiWork();
    }
  };

  const handleApplyCalibrationLocally = async () => {
    if (!calResult?.override) return;
    const mergedOverride = {
      ...calResult.override,
      ...(manualModelName.trim() ? { model_name: manualModelName.trim() } : {}),
      ...(manualArticleNumber.trim() ? { article_number: manualArticleNumber.trim() } : {}),
      ...(manualSerialNumber.trim() ? { serial_number: manualSerialNumber.trim() } : {}),
      ...(manualMarketRegion.trim() ? { market_region: manualMarketRegion.trim() } : {}),
    };
    try {
      const res = await fetch('/api/offsets/apply_local', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          capture_id: calResult.capture_id || undefined,
          override: mergedOverride,
          model_name: manualModelName.trim() || undefined,
          article_number: manualArticleNumber.trim() || undefined,
          serial_number: manualSerialNumber.trim() || undefined,
          market_region: manualMarketRegion.trim() || undefined,
          port: selectedPort,
        }),
      });
      const data = await res.json();
      if (data.success) {
        setAppliedLocal(true);
        setCalResult((prev) => (prev ? { ...prev, override: data.override || mergedOverride } : prev));
        if (data.updated_stats && onStatsUpdated) onStatsUpdated(data.updated_stats);
        setCalNotice({
          msg: t('msgAppliedSaved', { key: data.saved_key }),
          error: false,
          url: '',
        });
        setShowUploadPromptModal(true);
      } else {
        setCalNotice({ msg: data.error || 'Failed to save local override.', error: true, url: '' });
      }
    } catch (err) {
      setCalNotice({ msg: err.message, error: true, url: '' });
    }
  };

  const handleContributeOffsetFix = async () => {
    if (!calResult?.override) return;
    setIsUploadingContrib(true);
    setCalNotice({ msg: t('msgSubmittingFix'), error: false, url: '' });
    const mergedOverride = {
      ...calResult.override,
      ...(manualModelName.trim() ? { model_name: manualModelName.trim() } : {}),
      ...(manualArticleNumber.trim() ? { article_number: manualArticleNumber.trim() } : {}),
      ...(manualSerialNumber.trim() ? { serial_number: manualSerialNumber.trim() } : {}),
      ...(manualMarketRegion.trim() ? { market_region: manualMarketRegion.trim() } : {}),
    };
    try {
      const res = await fetch('/api/offsets/contribute', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          capture_id: calResult.capture_id || undefined,
          override: mergedOverride,
        }),
      });
      const data = await res.json();
      if (data.success) {
        setCalNotice({
          msg: data.message || t('msgContributedSuccess'),
          error: false,
          url: data.url || '',
        });
      } else {
        setCalNotice({
          msg: data.error || t('msgGithubUnavailable'),
          error: true,
          url: data.url || '',
        });
      }
    } catch (err) {
      setCalNotice({ msg: `Contribute error: ${err.message}`, error: true, url: '' });
    } finally {
      setIsUploadingContrib(false);
    }
  };

  const handleExportPatchFile = async () => {
    if (!calResult?.override) return;
    try {
      const res = await fetch('/api/offsets/export_patch', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          capture_id: calResult.capture_id || undefined,
          override: calResult.override,
          save_dialog: true,
        }),
      });
      const data = await res.json();
      if (data.dialog_unavailable && data.patch_json) {
        const blob = new Blob([data.patch_json], { type: 'application/json' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = data.filename || 'spectra_offset_patch.json';
        document.body.appendChild(a);
        a.click();
        a.remove();
        URL.revokeObjectURL(url);
        setCalNotice({ msg: `Downloaded ${data.filename}`, error: false, url: '' });
      } else if (data.success) {
        setCalNotice({ msg: `Saved patch file: ${data.saved_path || data.filename}`, error: false, url: '' });
      } else if (!data.cancelled) {
        setCalNotice({ msg: data.error || 'Export failed.', error: true, url: '' });
      }
    } catch (err) {
      setCalNotice({ msg: `Export error: ${err.message}`, error: true, url: '' });
    }
  };

  // Empty State: Machine has not been read yet
  if (!statsData) {
    return (
      <div className={`p-8 border rounded ${theme.surfaceClass} text-center space-y-4 font-mono shadow-lg`}>
        <div className="w-16 h-16 rounded-full bg-black/40 border border-[#FCEE09]/40 flex items-center justify-center mx-auto text-[#FCEE09]">
          <ShieldCheck className="w-8 h-8 animate-pulse" />
        </div>
        <div className="space-y-1">
          <h3 className="text-base font-black text-white uppercase tracking-wider">
            {t('machineNotReadTitle')}
          </h3>
          <p className="text-xs text-zinc-400 max-w-lg mx-auto">
            {t('machineNotReadDesc', { port: selectedPort || t('serialPortFallback') })}
          </p>
        </div>
        <div className="pt-2">
          <button
            onClick={onInterrogate}
            disabled={isInterrogating || !selectedPort}
            className="px-4 py-2 bg-[#FCEE09] hover:bg-yellow-400 text-black font-extrabold text-xs rounded tracking-wider shadow-[0_0_12px_rgba(252,238,9,0.4)] transition-all font-mono disabled:opacity-50"
          >
            {isInterrogating ? t('btnReadingData') : t('btnInterrogateFull')}
          </button>
        </div>
      </div>
    );
  }

  // Calculate health score & cards from real interrogated statsData
  const healthScore = statsData.health_score ?? 95;
  const advisorCards = statsData.advisor_cards || [];
  const beverages = statsData.beverages || [];
  const totalPreps = statsData.total_preparations || 0;
  const totalCups = statsData.total_cups ?? totalPreps;

  // Health Score Color
  const getScoreColor = (sc) => {
    if (sc >= 90) return 'text-emerald-400 border-emerald-500';
    if (sc >= 75) return 'text-amber-400 border-amber-500';
    return 'text-rose-400 border-rose-500';
  };

  return (
    <div className="grid grid-cols-1 lg:grid-cols-12 gap-3">
      {/* ==================================================================== */}
      {/* LEFT COLUMN: AI DIAGNOSTIC HEALTH ADVISOR (7 COLS) */}
      {/* ==================================================================== */}
      <div className="lg:col-span-7 space-y-3">
        {/* Top: Executive Health Scorecard */}
        <div className={`p-4 border rounded ${theme.surfaceClass}`}>
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div>
              <div className="text-[10px] font-bold text-gray-500 uppercase tracking-wider">
                {t('scorecardTitle')}
              </div>
              <div className="text-lg font-black font-mono text-gray-200">
                {statsData?.machine_model || 'Jura IMPRESSA XJ5 Pro'}
              </div>
              <div className="text-xs text-gray-400">
                {t('protocolLabel')} <span className="font-mono text-sky-400">{statsData?.protocol_mode || 'Plain ASCII'}</span> | {t('powerLabel')} <span className="font-mono text-gray-300">{statsData?.power_spec || '230V / 50Hz'}</span>
              </div>
            </div>

            {/* Circular / Pill Health Score Badge */}
            <div className="flex items-center space-x-3">
              <div className={`w-16 h-16 rounded-full border-4 flex flex-col items-center justify-center font-mono ${getScoreColor(healthScore)} bg-black/40`}>
                <span className="text-xl font-black leading-none">{healthScore}</span>
                <span className="text-[9px] font-bold uppercase text-gray-400">/ 100</span>
              </div>
              <div>
                <div className={`text-xs font-bold uppercase ${healthScore >= 90 ? 'text-emerald-400' : (healthScore >= 75 ? 'text-amber-400' : 'text-rose-400')}`}>
                  {healthScore >= 90 ? t('healthExcellent') : (healthScore >= 75 ? t('healthAttention') : t('healthCritical'))}
                </div>
                <div className="text-[10px] text-gray-500">
                  {healthScore >= 90 ? t('healthExcellentDesc') : t('healthAttentionDesc')}
                </div>
              </div>
            </div>
          </div>

          {/* Quick Action Buttons for Reports */}
          <div className="flex flex-wrap items-center gap-2 mt-4 pt-3 border-t border-gray-800">
            <button
              onClick={() => onOpenServiceReport(false)}
              className="flex items-center space-x-1.5 px-3 py-1.5 bg-sky-950/60 hover:bg-sky-900 border border-sky-600/60 text-sky-200 font-bold text-xs rounded transition-colors cursor-pointer"
            >
              <FileText className="w-3.5 h-3.5" />
              <span>{t('btnViewCertificate')}</span>
            </button>

            {aiEnabled && aiServiceSummary?.customer_summary && (
              <button
                onClick={() => onOpenServiceReport(true)}
                className="flex items-center space-x-1.5 px-3 py-1.5 bg-emerald-950/70 hover:bg-emerald-900 border border-emerald-500/70 text-emerald-200 font-bold text-xs rounded transition-colors cursor-pointer"
              >
                <Sparkles className="w-3.5 h-3.5" />
                <span>{t('btnCertificateWithAi')}</span>
              </button>
            )}

            <button
              onClick={onOpenExport}
              className="flex items-center space-x-1.5 px-3 py-1.5 bg-purple-950/60 hover:bg-purple-900 border border-purple-600/60 text-purple-200 font-bold text-xs rounded transition-colors cursor-pointer"
            >
              <Download className="w-3.5 h-3.5" />
              <span>{t('btnExportData')}</span>
            </button>
          </div>
        </div>

        {/* Advisor Recommendation Cards */}
        <div className={`p-4 border rounded ${theme.surfaceClass}`}>
          <div className="flex items-center justify-between mb-3 border-b border-gray-800 pb-2">
            <span className="text-xs font-bold text-gray-300 uppercase tracking-wider flex items-center space-x-1.5">
              <ShieldCheck className="w-4 h-4 text-sky-400" />
              <span>{t('advisorTitle')}</span>
            </span>
            <span className="text-[10px] font-mono text-gray-400">
              {t('advisorChecksCount', { count: advisorCards.length })}
            </span>
          </div>

          <div className="space-y-2.5">
            {advisorCards.map((rawCard, idx) => {
              const card = txAdvisorCard(lang, rawCard);
              const borderCol =
                card.severity === 'ok'
                  ? 'border-emerald-900/60 bg-emerald-950/20'
                  : card.severity === 'warn'
                  ? 'border-amber-900/60 bg-amber-950/20'
                  : card.severity === 'error'
                  ? 'border-rose-900/60 bg-rose-950/20'
                  : 'border-sky-900/60 bg-sky-950/20';

              const titleCol =
                card.severity === 'ok'
                  ? 'text-emerald-400'
                  : card.severity === 'warn'
                  ? 'text-amber-400'
                  : card.severity === 'error'
                  ? 'text-rose-400'
                  : 'text-sky-400';

              return (
                <div key={idx} className={`p-3 border rounded text-xs ${borderCol}`}>
                  <div className="flex items-center space-x-2 font-bold mb-1">
                    <span>{card.icon}</span>
                    <span className={titleCol}>{card.title}</span>
                  </div>
                  <div className="text-gray-300 pl-5 mb-1 leading-relaxed">
                    {card.desc}
                  </div>
                  <div className="text-[11px] font-mono text-gray-400 pl-5">
                    {card.action}
                  </div>
                </div>
              );
            })}
          </div>
        </div>

        {/* Technician Field Service Inspection Checklist */}
        <div className={`p-4 border rounded ${theme.surfaceClass}`}>
          <div className="text-xs font-bold text-gray-300 uppercase tracking-wider mb-2 flex items-center space-x-1.5 border-b border-gray-800 pb-2">
            <Wrench className="w-4 h-4 text-purple-400" />
            <span>{t('checklistTitle')}</span>
          </div>
          <div className="space-y-2 text-xs">
            <label className="flex items-start space-x-2.5 cursor-pointer text-gray-300 hover:text-white">
              <input
                type="checkbox"
                checked={checklist.chk1}
                onChange={(e) => setChecklist({ ...checklist, chk1: e.target.checked })}
                className="mt-0.5 rounded accent-sky-500"
              />
              <span>{t('chk1')}</span>
            </label>
            <label className="flex items-start space-x-2.5 cursor-pointer text-gray-300 hover:text-white">
              <input
                type="checkbox"
                checked={checklist.chk2}
                onChange={(e) => setChecklist({ ...checklist, chk2: e.target.checked })}
                className="mt-0.5 rounded accent-sky-500"
              />
              <span>{t('chk2')}</span>
            </label>
            <label className="flex items-start space-x-2.5 cursor-pointer text-gray-300 hover:text-white">
              <input
                type="checkbox"
                checked={checklist.chk3}
                onChange={(e) => setChecklist({ ...checklist, chk3: e.target.checked })}
                className="mt-0.5 rounded accent-sky-500"
              />
              <span>{t('chk3')}</span>
            </label>
            <label className="flex items-start space-x-2.5 cursor-pointer text-gray-300 hover:text-white">
              <input
                type="checkbox"
                checked={checklist.chk4}
                onChange={(e) => setChecklist({ ...checklist, chk4: e.target.checked })}
                className="mt-0.5 rounded accent-sky-500"
              />
              <span>{t('chk4')}</span>
            </label>
          </div>
        </div>

        {/* Opt-In Local AI Bench Triage & Customer Service Summary (Default: OFF) */}
        <div className={`p-4 border rounded ${theme.surfaceClass} space-y-3`}>
          <div className="flex flex-wrap items-center justify-between gap-2 border-b border-gray-800 pb-2">
            <div className="flex items-center space-x-1.5 text-xs font-bold text-purple-300 uppercase tracking-wider">
              <Sparkles className="w-4 h-4 text-purple-400" />
              <span>{t('aiPanelTitle')}</span>
            </div>
            {onToggleAi && (
              <button
                onClick={() => onToggleAi(!aiEnabled)}
                className={`flex items-center space-x-1 px-2 py-0.5 rounded text-[10px] font-mono font-bold border cursor-pointer transition-colors ${
                  aiEnabled
                    ? 'bg-purple-950/80 border-purple-500 text-purple-200 hover:bg-rose-950/80 hover:border-rose-500 hover:text-rose-200'
                    : 'bg-zinc-900 border-zinc-700 text-zinc-400 hover:text-white'
                }`}
              >
                <Power className="w-3 h-3" />
                <span>{aiEnabled ? t('btnTurnAiOff') : t('btnEnableAiDefaultOff')}</span>
              </button>
            )}
          </div>

          {!aiEnabled ? (
            <p className="text-[11px] text-zinc-400 font-mono">
              {t('aiOffNotice')}
            </p>
          ) : (
            <div className="space-y-2.5">
              <div className="flex flex-wrap gap-2">
                <button
                  onClick={handleRunAiTriage}
                  disabled={isRunningTriage}
                  className="flex items-center space-x-1.5 px-3 py-1.5 bg-purple-700 hover:bg-purple-600 disabled:opacity-50 text-white font-bold text-xs rounded cursor-pointer"
                >
                  <RefreshCw className={`w-3.5 h-3.5 ${isRunningTriage ? 'animate-spin' : ''}`} />
                  <span>{isRunningTriage ? t('btnRunningTriage') : t('btnRunTriage')}</span>
                </button>
                <button
                  onClick={handleGenerateServiceSummary}
                  disabled={isGeneratingSummary}
                  className="flex items-center space-x-1.5 px-3 py-1.5 bg-cyan-800 hover:bg-cyan-700 disabled:opacity-50 text-white font-bold text-xs rounded cursor-pointer"
                >
                  <FileText className="w-3.5 h-3.5" />
                  <span>{isGeneratingSummary ? t('btnGeneratingSummary') : t('btnGenerateSummary')}</span>
                </button>
              </div>

              {aiError && (
                <div className="p-2 rounded bg-rose-950/60 border border-rose-700 text-rose-200 text-[11px] font-mono">
                  {aiError}
                </div>
              )}

              {aiTriage && (
                <div className="p-3 bg-black/50 border border-purple-800/60 rounded space-y-2 text-xs">
                  <div className="flex items-center justify-between">
                    <span className="font-bold text-purple-300">{t('benchDiagnosisTitle', { model: aiTriage.model })}</span>
                    <span className={`px-2 py-0.5 rounded text-[10px] font-mono font-bold ${
                      aiTriage.urgency === 'HIGH'
                        ? 'bg-rose-950 text-rose-300 border border-rose-600'
                        : aiTriage.urgency === 'MEDIUM'
                        ? 'bg-amber-950 text-amber-300 border border-amber-600'
                        : 'bg-emerald-950 text-emerald-300 border border-emerald-600'
                    }`}>
                      {t('urgencyLabel', { urgency: aiTriage.urgency })}
                    </span>
                  </div>
                  <p className="text-gray-200 leading-relaxed">{aiTriage.summary}</p>
                  {aiTriage.probable_causes?.length > 0 && (
                    <div>
                      <div className="text-[10px] font-bold text-zinc-400 uppercase">{t('probableCauses')}</div>
                      <ul className="list-disc list-inside text-zinc-300 text-[11px]">
                        {aiTriage.probable_causes.map((c, i) => <li key={i}>{c}</li>)}
                      </ul>
                    </div>
                  )}
                  {aiTriage.bench_checks?.length > 0 && (
                    <div>
                      <div className="text-[10px] font-bold text-zinc-400 uppercase">{t('benchChecks')}</div>
                      <ul className="list-disc list-inside text-cyan-300 text-[11px]">
                        {aiTriage.bench_checks.map((c, i) => <li key={i}>{c}</li>)}
                      </ul>
                    </div>
                  )}
                </div>
              )}

              {aiServiceSummary?.customer_summary && (
                <div className="p-3 bg-black/50 border border-cyan-800/60 rounded space-y-1.5 text-xs">
                  <div className="font-bold text-cyan-300 text-[11px] uppercase">{t('customerSummaryPreview')}</div>
                  <p className="text-gray-200 leading-relaxed">{aiServiceSummary.customer_summary}</p>
                  {aiServiceSummary.recommended_next_service && (
                    <p className="text-[11px] text-amber-300 font-mono">{t('nextServiceLabel')} {aiServiceSummary.recommended_next_service}</p>
                  )}
                </div>
              )}

              {/* Wrong Counters? Fix Machine Offsets via J.O.E. CSV or Legacy Screenshot */}
              <div className="pt-3 border-t border-gray-800/90 space-y-2.5">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <div className="flex items-center space-x-1.5 text-[11px] font-bold text-amber-300 uppercase">
                    <Sliders className="w-3.5 h-3.5 text-amber-400" />
                    <span>{t('offsetPanelTitle')}</span>
                  </div>
                  {onOpenConfig && (
                    <button
                      type="button"
                      onClick={onOpenConfig}
                      className="text-[10px] font-mono text-cyan-400 hover:underline cursor-pointer"
                    >
                      {t('btnModelsLibrary')}
                    </button>
                  )}
                </div>

                <div className="flex flex-wrap items-center gap-2">
                  <label className="flex items-center space-x-1.5 px-3 py-1.5 bg-zinc-900 hover:bg-zinc-800 border border-zinc-700 text-zinc-200 rounded text-xs font-mono cursor-pointer">
                    <Upload className="w-3.5 h-3.5 text-amber-400" />
                    <span>{refFileName ? refFileName : t('uploadRefLabel')}</span>
                    <input
                      type="file"
                      accept=".csv,.txt,.png,.jpg,.jpeg,.webp,image/*"
                      onChange={handleReferenceUpload}
                      className="hidden"
                    />
                  </label>

                  <button
                    type="button"
                    disabled={isCalibrating || !hasAnyCalibInput}
                    onClick={handleCalibrateUploadedRef}
                    className="flex items-center space-x-1.5 px-3 py-1.5 bg-amber-600 hover:bg-amber-500 disabled:opacity-40 text-black font-bold text-xs rounded cursor-pointer"
                  >
                    <RefreshCw className={`w-3.5 h-3.5 ${isCalibrating ? 'animate-spin' : ''}`} />
                    <span>{isCalibrating ? t('btnCalibrating') : t('btnCalibrateOffsets')}</span>
                  </button>
                </div>

                {/* Machine Identity Correction (US/EU Variants) & Freeform Text Window */}
                <div className="p-2.5 bg-zinc-950/70 border border-zinc-800/90 rounded space-y-2 text-[11px] font-mono">
                  <div className="text-[10px] text-zinc-400 font-bold uppercase tracking-wider">
                    {t('identityOverrideTitle')}
                  </div>
                  <div className="grid grid-cols-1 sm:grid-cols-4 gap-2">
                    <input
                      type="text"
                      value={manualModelName}
                      onChange={(e) => setManualModelName(e.target.value)}
                      placeholder={t('lblModelName')}
                      className="px-2 py-1 bg-black/70 border border-zinc-700 rounded text-zinc-100 placeholder-zinc-500 outline-none focus:border-amber-500"
                    />
                    <input
                      type="text"
                      value={manualArticleNumber}
                      onChange={(e) => setManualArticleNumber(e.target.value)}
                      placeholder={t('lblArticleNumber')}
                      className="px-2 py-1 bg-black/70 border border-zinc-700 rounded text-zinc-100 placeholder-zinc-500 outline-none focus:border-amber-500"
                    />
                    <input
                      type="text"
                      value={manualSerialNumber}
                      onChange={(e) => setManualSerialNumber(e.target.value)}
                      placeholder={t('lblSerialNumber')}
                      className="px-2 py-1 bg-black/70 border border-zinc-700 rounded text-zinc-100 placeholder-zinc-500 outline-none focus:border-amber-500"
                    />
                    <input
                      type="text"
                      value={manualMarketRegion}
                      onChange={(e) => setManualMarketRegion(e.target.value)}
                      placeholder={t('lblMarketRegion')}
                      className="px-2 py-1 bg-black/70 border border-zinc-700 rounded text-zinc-100 placeholder-zinc-500 outline-none focus:border-amber-500"
                    />
                  </div>
                  <textarea
                    rows={3}
                    value={refNotesText}
                    onChange={(e) => setRefNotesText(e.target.value)}
                    placeholder={t('refNotesPlaceholder')}
                    className="w-full px-2 py-1.5 bg-black/70 border border-zinc-700 rounded text-zinc-100 placeholder-zinc-500 outline-none focus:border-amber-500 resize-y"
                  />
                </div>

                {refIsImage && (
                  <p className="text-[10px] font-mono text-zinc-400">
                    {t('screenshotDetectedTip')}
                  </p>
                )}

                {calNotice.msg && (
                  <div
                    className={`p-2 rounded text-[11px] font-mono border flex flex-wrap items-center justify-between gap-2 ${
                      calNotice.error
                        ? 'bg-rose-950/50 border-rose-700 text-rose-200'
                        : 'bg-emerald-950/40 border-emerald-700 text-emerald-200'
                    }`}
                  >
                    <span>{calNotice.msg}</span>
                    {safeExternalUrl(calNotice.url) && (
                      <a
                        href={safeExternalUrl(calNotice.url)}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="underline text-cyan-300 font-bold"
                      >
                        {t('viewSubmission')}
                      </a>
                    )}
                  </div>
                )}

                {calResult?.override && (
                  <div className="p-3 bg-black/60 border border-amber-700/60 rounded space-y-2.5 text-xs font-mono">
                    <div className="flex flex-wrap items-center justify-between gap-2 text-[11px]">
                      <span className="text-amber-300 font-bold">
                        {t('calibratedSummary', {
                          products: calResult.matched_products,
                          maintenance: calResult.matched_maintenance,
                          source: calResult.extraction_source,
                        })}
                      </span>
                      <span className="text-zinc-400">
                        {t('totalPrepsPreview')} <strong className="text-rose-400">{calResult.preview_before?.total_preps ?? '—'}</strong> →{' '}
                        <strong className="text-emerald-400">{calResult.preview_after?.total_preps ?? '—'}</strong>
                      </span>
                    </div>

                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-1.5 max-h-48 overflow-y-auto text-[10px]">
                      {(calResult.override.products || []).map((p, idx) => (
                        <div key={`p-${idx}`} className="flex justify-between px-2 py-1 bg-zinc-950 border border-zinc-800 rounded">
                          <span className="text-zinc-300 truncate">{p.name}</span>
                          <span className="text-cyan-300">{p.addr_hex} ({p.joe_count})</span>
                        </div>
                      ))}
                      {(calResult.override.maintenance || []).map((m, idx) => (
                        <div key={`m-${idx}`} className="flex justify-between px-2 py-1 bg-zinc-950 border border-zinc-800 rounded">
                          <span className="text-amber-200 truncate">{m.name}</span>
                          <span className="text-amber-400">{m.addr_hex} ({m.joe_count})</span>
                        </div>
                      ))}
                    </div>

                    {(calResult.detected_identity?.model_name || calResult.override?.model_name) && (
                      <div className="text-[10px] text-cyan-300 bg-cyan-950/30 border border-cyan-800/50 rounded px-2 py-1">
                        {t('detectedIdentitySummary', {
                          model: manualModelName || calResult.override.model_name || '—',
                          article: manualArticleNumber || calResult.override.article_number || '—',
                          serial: manualSerialNumber || calResult.override.serial_number || '—',
                        })}
                      </div>
                    )}

                    <div className="flex flex-wrap gap-2 pt-1">
                      <button
                        type="button"
                        onClick={handleApplyCalibrationLocally}
                        className="flex items-center space-x-1 px-2.5 py-1 bg-emerald-700 hover:bg-emerald-600 text-white font-bold rounded text-[11px] cursor-pointer"
                      >
                        <Check className="w-3.5 h-3.5" />
                        <span>{appliedLocal ? t('btnAppliedLocally') : t('btnApplyLocallyNow')}</span>
                      </button>
                      <button
                        type="button"
                        onClick={handleContributeOffsetFix}
                        className="flex items-center space-x-1 px-2.5 py-1 bg-sky-700 hover:bg-sky-600 text-white font-bold rounded text-[11px] cursor-pointer"
                      >
                        <Send className="w-3.5 h-3.5" />
                        <span>{t('btnContributeRepo')}</span>
                      </button>
                      <button
                        type="button"
                        onClick={handleExportPatchFile}
                        className="flex items-center space-x-1 px-2.5 py-1 bg-zinc-800 hover:bg-zinc-700 border border-zinc-600 text-zinc-200 font-bold rounded text-[11px] cursor-pointer"
                      >
                        <Download className="w-3.5 h-3.5" />
                        <span>{t('btnExportPatchJson')}</span>
                      </button>
                    </div>
                  </div>
                )}
              </div>
            </div>
          )}
        </div>
      </div>

      {/* ==================================================================== */}
      {/* RIGHT COLUMN: BEVERAGE PREPARATION RECIPE ANALYTICS (5 COLS) */}
      {/* ==================================================================== */}
      <div className="lg:col-span-5 space-y-3">
        <div className={`p-4 border rounded ${theme.surfaceClass}`}>
          <div className="flex items-center justify-between mb-3 border-b border-gray-800 pb-2">
            <span className="text-xs font-bold text-gray-300 uppercase tracking-wider flex items-center space-x-1.5">
              <Coffee className="w-4 h-4 text-amber-400" />
              <span>{t('bevAnalyticsTitle')}</span>
            </span>
            <span className="text-xs font-mono font-bold text-sky-400">
              {t('bevPrepsCups', { preps: totalPreps, cups: totalCups })}
            </span>
          </div>

          <div className="space-y-3">
            {beverages.map((bev) => {
              const count = bev.count || 0;
              const pct = totalPreps > 0 ? (count / totalPreps) * 100 : 0;
              return (
                <div key={bev.code} className="space-y-1">
                  <div className="flex items-center justify-between text-xs font-mono">
                    <span className="font-bold text-gray-200">{txBeverageName(lang, bev.name)}</span>
                    <span className="text-gray-400">
                      <strong className="text-white">{count}</strong> ({pct.toFixed(1)}%)
                    </span>
                  </div>

                  {/* Visual Proportion Bar */}
                  <div className="w-full h-2 bg-gray-800 rounded-full overflow-hidden">
                    <div
                      className={`h-full transition-all duration-300 ${
                        bev.type === 'Milk'
                          ? 'bg-purple-500'
                          : bev.type === 'Water'
                          ? 'bg-cyan-500'
                          : 'bg-amber-500'
                      }`}
                      style={{ width: `${Math.max(1, pct)}%` }}
                    />
                  </div>
                </div>
              );
            })}
          </div>

          {/* Beverage Categories Legend */}
          <div className="mt-4 pt-3 border-t border-gray-800 flex items-center justify-between text-[11px] font-mono text-gray-400">
            <span className="flex items-center space-x-1.5">
              <span className="w-2.5 h-2.5 rounded-full bg-amber-500 inline-block" />
              <span>{t('legendCoffee')}</span>
            </span>
            <span className="flex items-center space-x-1.5">
              <span className="w-2.5 h-2.5 rounded-full bg-purple-500 inline-block" />
              <span>{t('legendMilk')}</span>
            </span>
            <span className="flex items-center space-x-1.5">
              <span className="w-2.5 h-2.5 rounded-full bg-cyan-500 inline-block" />
              <span>{t('legendWater')}</span>
            </span>
          </div>
        </div>
      </div>
      {/* Community Calibration Upload Prompt Modal after Local Apply */}
      {showUploadPromptModal && calResult?.override && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 backdrop-blur-sm p-4">
          <div className="w-full max-w-md border-2 border-sky-500/70 bg-[#0d0d14] rounded-xl shadow-2xl overflow-hidden font-mono text-xs">
            <div className="flex items-center justify-between px-4 py-3 bg-[#14141f] border-b border-zinc-800">
              <div className="flex items-center space-x-2 text-sky-300 font-bold uppercase tracking-wider">
                <Send className="w-4 h-4" />
                <span>{t('calibUploadModalTitle')}</span>
              </div>
              <button
                type="button"
                onClick={() => setShowUploadPromptModal(false)}
                className="text-zinc-400 hover:text-white p-1 rounded hover:bg-zinc-800 cursor-pointer"
              >
                <X className="w-4 h-4" />
              </button>
            </div>
            <div className="p-4 space-y-3 text-zinc-200">
              <p className="text-[11px] leading-relaxed text-zinc-300">
                {t('calibUploadModalDesc')}
              </p>
              <div className="p-2.5 bg-black/60 border border-zinc-800 rounded space-y-1 text-[11px]">
                <div className="text-cyan-300 font-bold">
                  {t('detectedIdentitySummary', {
                    model: manualModelName || calResult.override.model_name || '—',
                    article: manualArticleNumber || calResult.override.article_number || '—',
                    serial: manualSerialNumber || calResult.override.serial_number || '—',
                  })}
                </div>
                <div className="text-zinc-400">
                  {t('calibratedSummary', {
                    products: calResult.matched_products ?? 0,
                    maintenance: calResult.matched_maintenance ?? 0,
                    source: calResult.extraction_source || calResult.override.extraction_source || 'calibration',
                  })}
                </div>
              </div>

              {calNotice.msg && (
                <div
                  className={`p-2 rounded text-[11px] border ${
                    calNotice.error
                      ? 'bg-rose-950/50 border-rose-700 text-rose-200'
                      : 'bg-emerald-950/50 border-emerald-700 text-emerald-200'
                  }`}
                >
                  <div>{calNotice.msg}</div>
                  {safeExternalUrl(calNotice.url) && (
                    <a
                      href={safeExternalUrl(calNotice.url)}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="inline-block mt-1 underline text-cyan-300 font-bold"
                    >
                      {t('viewSubmission')}
                    </a>
                  )}
                </div>
              )}

              <div className="flex flex-wrap justify-end gap-2 pt-1">
                <button
                  type="button"
                  onClick={handleExportPatchFile}
                  className="px-3 py-1.5 bg-zinc-900 hover:bg-zinc-800 border border-zinc-700 text-zinc-200 font-bold rounded text-[11px] cursor-pointer"
                >
                  {t('btnExportPatchJson')}
                </button>
                <button
                  type="button"
                  disabled={isUploadingContrib}
                  onClick={handleContributeOffsetFix}
                  className="flex items-center space-x-1.5 px-3 py-1.5 bg-sky-600 hover:bg-sky-500 disabled:opacity-50 text-white font-extrabold rounded text-[11px] cursor-pointer"
                >
                  <Send className="w-3.5 h-3.5" />
                  <span>{t('calibUploadBtnNow')}</span>
                </button>
                <button
                  type="button"
                  onClick={() => setShowUploadPromptModal(false)}
                  className="px-3 py-1.5 bg-zinc-800 hover:bg-zinc-700 text-zinc-300 font-bold rounded text-[11px] cursor-pointer"
                >
                  {calNotice.url ? t('calibUploadClose') : t('calibUploadBtnLater')}
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

export default React.memo(DiagnosticAdvisorTab);
