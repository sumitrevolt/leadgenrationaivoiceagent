import { useEffect, useState } from 'react';
import { dashboardApi, AdminDashboard } from '../services/api.ts';

/**
 * Fetch the real platform/admin dashboard payload from GET /api/admin/dashboard.
 * Backend returns real DB aggregates, or clearly-marked sample data
 * (is_sample_data=true) when the DB is empty/unavailable.
 *
 * @param pollMs  if > 0, re-fetch on this interval (live refresh). 0 = once.
 */
export function useDashboardData(pollMs = 0) {
  const [data, setData] = useState<AdminDashboard | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;

    const load = async () => {
      try {
        const d = await dashboardApi.getAdmin();
        if (alive) {
          setData(d);
          setError(null);
        }
      } catch (e) {
        if (alive) setError(e instanceof Error ? e.message : 'Failed to load dashboard');
      } finally {
        if (alive) setLoading(false);
      }
    };

    load();

    let timer: number | undefined;
    if (pollMs > 0) {
      timer = window.setInterval(load, pollMs);
    }
    return () => {
      alive = false;
      if (timer) window.clearInterval(timer);
    };
  }, [pollMs]);

  return { data, loading, error };
}

export default useDashboardData;
