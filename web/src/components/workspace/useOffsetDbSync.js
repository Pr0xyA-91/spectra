import { useState, useEffect, useCallback } from 'react';

export function useOffsetDbSync({ onStatsUpdated } = {}) {
  const [offsetDbStatus, setOffsetDbStatus] = useState(null);
  const [offsetDbCheck, setOffsetDbCheck] = useState(null);
  const [isCheckingOffsetDb, setIsCheckingOffsetDb] = useState(false);
  const [isSyncingOffsetDb, setIsSyncingOffsetDb] = useState(false);
  const [offsetDbSyncNotice, setOffsetDbSyncNotice] = useState(null);
  const [offsetDbBannerDismissed, setOffsetDbBannerDismissed] = useState(false);

  const fetchOffsetDbStatus = useCallback(async () => {
    try {
      const res = await fetch('/api/offsets_db/status', { cache: 'no-store' });
      if (res.ok) {
        const data = await res.json();
        if (data?.success) {
          setOffsetDbStatus(data);
          return data;
        }
      }
    } catch {}
    return null;
  }, []);

  const checkOffsetDbUpdates = useCallback(async (force = false) => {
    setIsCheckingOffsetDb(true);
    try {
      const res = await fetch(`/api/offsets_db/check?force=${force ? '1' : '0'}`, { cache: 'no-store' });
      if (res.ok) {
        const data = await res.json();
        setOffsetDbCheck(data);
        if (data?.update_available) {
          setOffsetDbBannerDismissed(false);
        }
        return data;
      }
    } catch {}
    finally {
      setIsCheckingOffsetDb(false);
    }
    return null;
  }, []);

  const syncOffsetDb = useCallback(async () => {
    setIsSyncingOffsetDb(true);
    setOffsetDbSyncNotice(null);
    try {
      const res = await fetch('/api/offsets_db/sync', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({}),
      });
      const data = await res.json().catch(() => ({ success: false, error: `HTTP ${res.status}` }));
      if (res.ok && data?.success) {
        if (data.status) {
          setOffsetDbStatus(data.status);
        } else {
          fetchOffsetDbStatus();
        }
        if (data.updated_stats && typeof onStatsUpdated === 'function') {
          onStatsUpdated(data.updated_stats);
        }
        setOffsetDbCheck((prev) => (prev ? { ...prev, update_available: false, current_version: data.offset_db_version || prev.latest_version } : prev));
        setOffsetDbSyncNotice({
          error: false,
          msg: data.message || `Synced Machine Offset DB ${data.offset_db_version || ''}`.trim(),
        });
        return data;
      }
      setOffsetDbSyncNotice({
        error: true,
        msg: data?.error || 'Machine Offset DB sync failed.',
      });
      return data;
    } catch (err) {
      setOffsetDbSyncNotice({
        error: true,
        msg: err?.message || 'Network error syncing Machine Offset DB.',
      });
      return { success: false, error: err?.message || 'Network error' };
    } finally {
      setIsSyncingOffsetDb(false);
    }
  }, [fetchOffsetDbStatus, onStatsUpdated]);

  // Initial read-only status + non-blocking check shortly after startup (NEVER silent overwrite)
  useEffect(() => {
    fetchOffsetDbStatus();
    const timer = setTimeout(() => {
      checkOffsetDbUpdates(false);
    }, 2400);
    return () => clearTimeout(timer);
  }, [fetchOffsetDbStatus, checkOffsetDbUpdates]);

  return {
    offsetDbStatus,
    offsetDbCheck,
    isCheckingOffsetDb,
    isSyncingOffsetDb,
    offsetDbSyncNotice,
    offsetDbBannerDismissed,
    setOffsetDbBannerDismissed,
    fetchOffsetDbStatus,
    checkOffsetDbUpdates,
    syncOffsetDb,
  };
}
