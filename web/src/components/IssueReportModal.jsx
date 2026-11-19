import React, { useState, useEffect } from 'react';
import {
  Flag,
  X,
  Github,
  Send,
  ExternalLink,
  Check,
  AlertTriangle,
  RefreshCw,
  Shield,
  Terminal,
  Cpu,
} from 'lucide-react';
import { createTranslator } from '../i18n/translations';

const ISSUE_CATEGORIES = [
  { id: 'bug', labelKey: 'issueCatBug', color: 'rose' },
  { id: 'hardware', labelKey: 'issueCatHardware', color: 'amber' },
  { id: 'enhancement', labelKey: 'issueCatEnhancement', color: 'sky' },
  { id: 'ui', labelKey: 'issueCatUi', color: 'purple' },
];

export default function IssueReportModal({
  isOpen,
  onClose,
  theme,
  lang = 'en',
  githubAuth = { authenticated: false, login: null },
  statsData = null,
  liveData = null,
  selectedPort = '',
  liveBuild = '',
  onOpenGitHubConfig = () => {},
  onSubmittingChange = () => {},
}) {
  const t = createTranslator(lang);

  const [category, setCategory] = useState('bug');
  const [title, setTitle] = useState('');
  const [description, setDescription] = useState('');
  const [includeEnv, setIncludeEnv] = useState(true);
  const [includeLogs, setIncludeLogs] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [result, setResult] = useState(null);

  useEffect(() => {
    onSubmittingChange(isSubmitting);
  }, [isSubmitting, onSubmittingChange]);

  if (!isOpen) return null;

  const machineModel =
    statsData?.identity?.model_name ||
    statsData?.model_family ||
    '';
  const efCode = statsData?.identity?.ef_code || '';
  const protocol = liveData?.protocol || statsData?.protocol || '';
  const portType = selectedPort
    ? selectedPort.toUpperCase().startsWith('DEMO')
      ? 'Simulation / Demo'
      : selectedPort.toUpperCase().startsWith('COM')
      ? 'Windows COM Serial'
      : 'USB/Serial UART'
    : 'None';

  const buildPayload = (mode) => ({
    title: title.trim(),
    description: description.trim(),
    category,
    include_env: includeEnv,
    include_logs: includeLogs,
    mode,
    machine_context: {
      model: machineModel,
      ef_code: efCode,
      protocol,
      port_type: portType,
    },
  });

  const handleSubmit = async (mode = 'api') => {
    if (!title.trim() || !description.trim()) {
      setResult({
        success: false,
        error: t('issueValidationError'),
      });
      return;
    }

    setIsSubmitting(true);
    setResult(null);
    try {
      const res = await fetch('/api/github/report_issue', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(buildPayload(mode)),
      });
      const data = await res.json().catch(() => ({
        success: false,
        error: `HTTP ${res.status}`,
      }));

      if (mode === 'url_only') {
        if (data.web_url) {
          window.open(data.web_url, '_blank', 'noopener,noreferrer');
          setResult({
            success: true,
            openedBrowser: true,
            web_url: data.web_url,
            repo: data.repo,
          });
        } else {
          setResult({
            success: false,
            error: data.error || t('issueUnknownError'),
          });
        }
      } else {
        setResult(data);
      }
    } catch (err) {
      setResult({
        success: false,
        error: err.message || t('issueUnknownError'),
      });
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleReset = () => {
    setTitle('');
    setDescription('');
    setResult(null);
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/75 backdrop-blur-sm p-4">
      <div
        className={`w-full max-w-xl border rounded-lg shadow-2xl ${theme.panelBg} ${theme.border} overflow-hidden flex flex-col max-h-[90vh]`}
      >
        {/* Header */}
        <div className="flex items-center justify-between px-5 py-3.5 border-b border-gray-800 bg-black/40">
          <div className="flex items-center space-x-2.5">
            <Flag className="w-4 h-4 text-rose-400" />
            <div>
              <h2 className="text-sm font-bold text-white font-mono tracking-wider uppercase">
                {t('issueModalTitle')}
              </h2>
              <p className="text-[11px] text-gray-400">
                {t('issueModalSubtitle')}
              </p>
            </div>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="text-gray-400 hover:text-white p-1 rounded hover:bg-white/5 cursor-pointer"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Body */}
        <div className="p-5 space-y-4 overflow-y-auto text-xs">
          {/* GitHub Auth Status Strip */}
          <div className="flex flex-wrap items-center justify-between gap-2 p-2.5 rounded bg-black/40 border border-gray-800">
            <div className="flex items-center space-x-2 font-mono text-[11px]">
              <Github className="w-4 h-4 text-gray-300" />
              {githubAuth?.authenticated ? (
                <span className="text-emerald-400 font-bold">
                  {t('ghSignedInAs', { login: githubAuth.login || 'GitHub' })}
                </span>
              ) : (
                <span className="text-amber-300">
                  {t('issueNotSignedInHint')}
                </span>
              )}
            </div>
            {!githubAuth?.authenticated && (
              <button
                type="button"
                onClick={() => {
                  onClose();
                  onOpenGitHubConfig();
                }}
                className="px-2.5 py-1 rounded text-[11px] font-bold font-mono bg-zinc-800 hover:bg-zinc-700 text-zinc-200 border border-zinc-600 cursor-pointer transition-colors"
              >
                {t('issueSignInBtn')}
              </button>
            )}
          </div>

          {/* Category Selector */}
          <div>
            <label className="block text-[11px] font-bold uppercase tracking-wider text-gray-400 mb-1.5 font-mono">
              {t('issueCategoryLabel')}
            </label>
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
              {ISSUE_CATEGORIES.map((cat) => {
                const active = category === cat.id;
                return (
                  <button
                    key={cat.id}
                    type="button"
                    onClick={() => setCategory(cat.id)}
                    className={`px-2.5 py-1.5 rounded text-[11px] font-bold font-mono border transition-all cursor-pointer ${
                      active
                        ? 'bg-rose-950/70 border-rose-400 text-rose-200 shadow-[0_0_8px_rgba(244,63,94,0.3)]'
                        : 'bg-black/40 border-gray-800 text-gray-400 hover:text-gray-200 hover:border-gray-600'
                    }`}
                  >
                    {t(cat.labelKey)}
                  </button>
                );
              })}
            </div>
          </div>

          {/* Title */}
          <div>
            <label className="block text-[11px] font-bold uppercase tracking-wider text-gray-400 mb-1 font-mono">
              {t('issueTitleLabel')}
            </label>
            <input
              type="text"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              maxLength={200}
              placeholder={t('issueTitlePlaceholder')}
              className="w-full px-3 py-2 bg-black/50 border border-gray-700 focus:border-sky-500 rounded text-xs text-white placeholder-gray-500 outline-none font-mono"
            />
          </div>

          {/* Description */}
          <div>
            <label className="block text-[11px] font-bold uppercase tracking-wider text-gray-400 mb-1 font-mono">
              {t('issueDescLabel')}
            </label>
            <textarea
              rows={5}
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder={t('issueDescPlaceholder')}
              className="w-full px-3 py-2 bg-black/50 border border-gray-700 focus:border-sky-500 rounded text-xs text-white placeholder-gray-500 outline-none font-mono resize-y select-text"
            />
          </div>

          {/* Optional Sanitized Diagnostics Checkboxes */}
          <div className="p-3 rounded bg-black/40 border border-gray-800 space-y-2">
            <div className="flex items-center space-x-1.5 text-[11px] font-bold uppercase tracking-wider text-gray-400 font-mono">
              <Shield className="w-3.5 h-3.5 text-emerald-400" />
              <span>{t('issueAttachmentsTitle')}</span>
            </div>

            <label className="flex items-start space-x-2 cursor-pointer text-gray-300">
              <input
                type="checkbox"
                checked={includeEnv}
                onChange={(e) => setIncludeEnv(e.target.checked)}
                className="mt-0.5 accent-emerald-500"
              />
              <div>
                <div className="font-semibold flex items-center space-x-1.5">
                  <Cpu className="w-3 h-3 text-sky-400" />
                  <span>{t('issueIncludeEnv')}</span>
                </div>
                <div className="text-[10px] text-gray-500 font-mono mt-0.5">
                  Build {liveBuild || 'current'}
                  {machineModel ? ` · ${machineModel}` : ''}
                  {efCode ? ` (${efCode})` : ''}
                  {protocol ? ` · ${protocol}` : ''}
                </div>
              </div>
            </label>

            <label className="flex items-start space-x-2 cursor-pointer text-gray-300">
              <input
                type="checkbox"
                checked={includeLogs}
                onChange={(e) => setIncludeLogs(e.target.checked)}
                className="mt-0.5 accent-emerald-500"
              />
              <div>
                <div className="font-semibold flex items-center space-x-1.5">
                  <Terminal className="w-3 h-3 text-amber-400" />
                  <span>{t('issueIncludeLogs')}</span>
                </div>
                <div className="text-[10px] text-gray-500">
                  {t('issueSanitizedNote')}
                </div>
              </div>
            </label>
          </div>

          {/* Submission Result Banner */}
          {result && (
            <div
              className={`p-3 rounded border font-mono text-xs space-y-2 ${
                result.success
                  ? 'bg-emerald-950/50 border-emerald-700 text-emerald-200'
                  : 'bg-rose-950/50 border-rose-700 text-rose-200'
              }`}
            >
              <div className="flex items-start space-x-2">
                {result.success ? (
                  <Check className="w-4 h-4 text-emerald-400 shrink-0 mt-0.5" />
                ) : (
                  <AlertTriangle className="w-4 h-4 text-rose-400 shrink-0 mt-0.5" />
                )}
                <div className="space-y-1 flex-1 min-w-0">
                  {result.success && result.issue_url ? (
                    <>
                      <div className="font-bold">
                        {t('issueCreatedSuccess', {
                          num: result.issue_number ? `#${result.issue_number}` : '',
                        })}
                      </div>
                      <a
                        href={result.issue_url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="inline-flex items-center space-x-1 text-sky-300 hover:text-white underline break-all"
                      >
                        <span>{result.issue_url}</span>
                        <ExternalLink className="w-3 h-3 shrink-0" />
                      </a>
                    </>
                  ) : result.success && result.openedBrowser ? (
                    <div className="font-bold">{t('issueBrowserOpened')}</div>
                  ) : (
                    <>
                      <div>{result.error || t('issueUnknownError')}</div>
                      {result.web_url && (
                        <a
                          href={result.web_url}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="inline-flex items-center space-x-1 text-sky-300 hover:text-white underline"
                        >
                          <span>{t('issueOpenBrowserFallback')}</span>
                          <ExternalLink className="w-3 h-3 shrink-0" />
                        </a>
                      )}
                    </>
                  )}
                </div>
              </div>
            </div>
          )}
        </div>

        {/* Footer Actions */}
        <div className="flex flex-wrap items-center justify-between gap-2 px-5 py-3 border-t border-gray-800 bg-black/40 text-xs">
          <div className="text-[10px] font-mono text-gray-500">
            GitHub: Pr0xyA-91/spectra
          </div>
          <div className="flex items-center space-x-2">
            {result?.success && (
              <button
                type="button"
                onClick={handleReset}
                className="px-3 py-1.5 rounded font-mono font-bold bg-zinc-800 hover:bg-zinc-700 text-zinc-200 border border-zinc-700 cursor-pointer"
              >
                {t('issueReportAnother')}
              </button>
            )}
            <button
              type="button"
              onClick={() => handleSubmit('url_only')}
              disabled={isSubmitting || !title.trim() || !description.trim()}
              className="flex items-center space-x-1.5 px-3 py-1.5 rounded font-mono font-bold bg-zinc-900 hover:bg-zinc-800 text-zinc-200 border border-zinc-700 disabled:opacity-40 cursor-pointer transition-colors"
              title={t('issueOpenBrowserTitle')}
            >
              <ExternalLink className="w-3.5 h-3.5" />
              <span>{t('issueOpenInBrowserBtn')}</span>
            </button>
            {githubAuth?.authenticated && (
              <button
                type="button"
                onClick={() => handleSubmit('api')}
                disabled={isSubmitting || !title.trim() || !description.trim()}
                className="flex items-center space-x-1.5 px-3.5 py-1.5 rounded font-mono font-bold bg-rose-600 hover:bg-rose-500 text-white border border-rose-400 disabled:opacity-40 cursor-pointer transition-colors shadow-[0_0_10px_rgba(244,63,94,0.3)]"
              >
                {isSubmitting ? (
                  <RefreshCw className="w-3.5 h-3.5 animate-spin" />
                ) : (
                  <Send className="w-3.5 h-3.5" />
                )}
                <span>{isSubmitting ? t('issueSubmittingBtn') : t('issueSubmitGithubBtn')}</span>
              </button>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
