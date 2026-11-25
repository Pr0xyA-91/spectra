/**
 * Frontend URL safety helpers to prevent unsafe schemes (e.g. javascript:, data:)
 * from reaching <a href> or window.open() sinks.
 */

export function safeExternalUrl(raw) {
  if (!raw || typeof raw !== 'string') return null;
  const trimmed = raw.trim();
  if (!trimmed) return null;
  try {
    const parsed = new URL(trimmed);
    if (parsed.protocol === 'https:' || parsed.protocol === 'http:') {
      return parsed.href;
    }
    return null;
  } catch {
    return null;
  }
}

export function openSafeExternalUrl(raw) {
  const safeHref = safeExternalUrl(raw);
  if (!safeHref) return false;
  window.open(safeHref, '_blank', 'noopener,noreferrer');
  return true;
}
