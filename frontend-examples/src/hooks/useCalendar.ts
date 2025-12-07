/**
 * React Hook for Calendar Data
 * Example hook for fetching and managing calendar data
 */

import { useState, useEffect } from 'react';
import { getCalendarDays } from '../api/calendar';

interface UseCalendarReturn {
  days: Record<string, any>;
  loading: boolean;
  error: Error | null;
  refetch: () => Promise<void>;
}

/**
 * Hook to fetch all calendar days
 *
 * Usage:
 * ```tsx
 * function Calendar() {
 *   const { days, loading, error } = useCalendar();
 *
 *   if (loading) return <div>Loading...</div>;
 *   if (error) return <div>Error: {error.message}</div>;
 *
 *   return (
 *     <div>
 *       {Object.entries(days).map(([dayNum, dayData]) => (
 *         <Day key={dayNum} data={dayData} />
 *       ))}
 *     </div>
 *   );
 * }
 * ```
 */
export function useCalendar(): UseCalendarReturn {
  const [days, setDays] = useState<Record<string, any>>({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<Error | null>(null);

  const fetchDays = async () => {
    try {
      setLoading(true);
      const data = await getCalendarDays();
      setDays(data);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err : new Error('Unknown error'));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchDays();
  }, []);

  return {
    days,
    loading,
    error,
    refetch: fetchDays,
  };
}
