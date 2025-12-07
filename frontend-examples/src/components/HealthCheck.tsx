/**
 * Example React Component - Health Check
 * Demonstrates how to use the API client to call backend endpoints
 */

import { useEffect, useState } from 'react';
import { getHealth } from '../api/calendar';
import type { HealthResponse } from '../api/types';

export function HealthCheck() {
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    async function checkHealth() {
      try {
        setLoading(true);
        const data = await getHealth();
        setHealth(data);
        setError(null);
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Unknown error');
        setHealth(null);
      } finally {
        setLoading(false);
      }
    }

    checkHealth();
  }, []);

  if (loading) {
    return <div>Checking API health...</div>;
  }

  if (error) {
    return <div>Error: {error}</div>;
  }

  return (
    <div>
      <h3>API Health Status</h3>
      <p>Status: {health?.status}</p>
      <p>Service: {health?.service}</p>
    </div>
  );
}
