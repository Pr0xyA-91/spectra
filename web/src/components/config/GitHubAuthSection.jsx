import React from 'react';
import { Github, LogOut, Check, Copy, ExternalLink } from 'lucide-react';
import { safeExternalUrl } from '../../utils/urlSafety';

export default function GitHubAuthSection({
  t,
  githubAuth,
  deviceFlow,
  patInput,
  setPatInput,
  copiedCode,
  authStatusMsg,
  onStartDeviceFlow,
  onSavePat,
  onLogout,
  onCancelDeviceFlow,
  onCopyDeviceCode,
}) {
  return (
    <div className="p-4 bg-black/40 border border-zinc-800 rounded space-y-3">
      <div className="flex items-center justify-between border-b border-zinc-800 pb-2.5">
        <div className="flex items-center gap-2">
          <Github className="w-4 h-4 text-[#FCEE09]" />
          <div>
            <div className="font-bold text-white">{t('cfgGhTitle')}</div>
            <div className="text-[10px] text-zinc-400">
              {t('cfgGhDesc')}
            </div>
          </div>
        </div>
        {githubAuth?.authenticated ? (
          <span className="px-2 py-0.5 bg-emerald-950 border border-emerald-700 text-emerald-300 rounded text-[10px] font-bold">
            {t('cfgGhConnected', { login: githubAuth.login })}
          </span>
        ) : (
          <span className="px-2 py-0.5 bg-amber-950 border border-amber-700 text-amber-300 rounded text-[10px] font-bold">
            {t('cfgGhDisconnected')}
          </span>
        )}
      </div>

      {authStatusMsg?.msg && (
        <div
          className={`px-3 py-2 rounded text-[11px] border ${
            authStatusMsg.error
              ? 'bg-red-950/50 border-red-800 text-red-300'
              : 'bg-emerald-950/40 border-emerald-800 text-emerald-300'
          }`}
        >
          {authStatusMsg.msg}
        </div>
      )}

      {githubAuth?.authenticated ? (
        <div className="flex items-center justify-between p-3 bg-zinc-950 border border-zinc-800 rounded">
          <div className="text-xs text-zinc-300">
            {t('cfgGhSignedInAs', { login: githubAuth.login })}{' '}
            <span className="text-zinc-500">({githubAuth.method || 'token'})</span>
          </div>
          <button
            type="button"
            onClick={onLogout}
            className="px-3 py-1.5 bg-rose-950/70 hover:bg-rose-900/80 border border-rose-700 text-rose-200 rounded font-bold text-xs flex items-center gap-1.5 cursor-pointer"
          >
            <LogOut className="w-3.5 h-3.5" />
            <span>{t('cfgGhSignOut')}</span>
          </button>
        </div>
      ) : (
        <div className="space-y-3">
          {githubAuth?.device_flow_available && !deviceFlow && (
            <button
              type="button"
              onClick={onStartDeviceFlow}
              className="w-full py-2 px-3 bg-sky-700 hover:bg-sky-600 text-white font-bold rounded text-xs flex items-center justify-center gap-2 cursor-pointer"
            >
              <Github className="w-4 h-4" />
              <span>{t('cfgGhSignInBrowser')}</span>
            </button>
          )}

          {deviceFlow && (
            <div className="p-3 bg-sky-950/40 border border-sky-800 rounded space-y-2">
              <div className="text-[11px] text-sky-300 font-bold">{t('cfgGhAuthorize')}</div>
              <div className="flex items-center justify-between bg-black/70 p-2 rounded border border-sky-900">
                <span className="text-sm font-bold text-sky-200 tracking-widest">{deviceFlow.user_code}</span>
                <button
                  type="button"
                  onClick={() => onCopyDeviceCode(deviceFlow.user_code)}
                  className="px-2 py-1 bg-sky-800 hover:bg-sky-700 text-sky-100 rounded text-[10px] flex items-center gap-1 cursor-pointer"
                >
                  {copiedCode ? <Check className="w-3 h-3 text-emerald-400" /> : <Copy className="w-3 h-3" />}
                  <span>{copiedCode ? t('cfgGhCopied') : t('cfgGhCopyCode')}</span>
                </button>
              </div>
              <div className="flex items-center justify-between text-[11px]">
                {safeExternalUrl(deviceFlow.verification_uri) && (
                  <a
                    href={safeExternalUrl(deviceFlow.verification_uri)}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-sky-400 hover:text-sky-300 underline flex items-center gap-1"
                  >
                    <span>{t('cfgGhOpenDevice')}</span>
                    <ExternalLink className="w-3 h-3" />
                  </a>
                )}
                <button
                  type="button"
                  onClick={onCancelDeviceFlow}
                  className="text-zinc-400 hover:text-white cursor-pointer"
                >
                  {t('ghCancel')}
                </button>
              </div>
            </div>
          )}

          <div className="p-3 bg-zinc-950 border border-zinc-800 rounded space-y-2">
            <label className="block text-[11px] text-zinc-300 font-bold">
              {t('cfgGhPatLabel')}
            </label>
            <div className="flex gap-2">
              <input
                type="password"
                value={patInput}
                onChange={(e) => setPatInput(e.target.value)}
                autoComplete="off"
                spellCheck={false}
                placeholder="ghp_... or github_pat_..."
                className="flex-1 bg-black border border-zinc-700 rounded px-2.5 py-1.5 text-xs text-white outline-none focus:border-[#FCEE09]"
              />
              <button
                type="button"
                disabled={!patInput?.trim()}
                onClick={onSavePat}
                className="px-3 py-1.5 bg-[#FCEE09] hover:bg-yellow-400 disabled:opacity-40 text-black font-extrabold rounded text-xs cursor-pointer"
              >
                {t('ghConnect')}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
