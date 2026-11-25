/**
 * Safe JSON response parsing and clipboard helpers for SPECTRA frontend.
 */

export async function parseJsonResponse(res) {
  if (!res) {
    return { success: false, error: 'No response from server.' };
  }
  const contentType = res.headers?.get?.('content-type') || '';
  if (contentType.includes('application/json')) {
    try {
      const data = await res.json();
      if (data && typeof data === 'object') {
        return data;
      }
      return { success: Boolean(res.ok), data };
    } catch {
      return {
        success: false,
        error: `Invalid JSON response (HTTP ${res.status ?? 'unknown'})`,
      };
    }
  }

  let text = '';
  try {
    text = await res.text();
  } catch {
    text = '';
  }
  const snippet = text.trim().slice(0, 200);
  return {
    success: false,
    error: !res.ok
      ? `Server error (${res.status}): ${snippet || 'Non-JSON response'}`
      : snippet || 'Unexpected non-JSON response from server.',
  };
}

export function copyTextSafe(text) {
  try {
    const str = String(text ?? '');
    if (navigator?.clipboard?.writeText) {
      return navigator.clipboard.writeText(str).then(
        () => true,
        () => false
      );
    }
    return Promise.resolve(false);
  } catch {
    return Promise.resolve(false);
  }
}
