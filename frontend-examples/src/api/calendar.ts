/**
 * Calendar API Client
 * Handles all HTTP requests to the calendar service
 */

import type { HealthResponse } from './types';

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL;

/**
 * Health check endpoint
 * @returns Service health status
 */
export async function getHealth(): Promise<HealthResponse> {
  const response = await fetch(`${API_BASE_URL}/calendar/health`, {
    method: 'GET',
    headers: {
      'Content-Type': 'application/json',
    },
  });

  if (!response.ok) {
    throw new Error(`Health check failed: ${response.statusText}`);
  }

  return response.json();
}

// Future calendar endpoints will be added here
// Example structure (DO NOT IMPLEMENT YET):
//
// export async function getEvents(): Promise<Event[]> {
//   const response = await fetch(`${API_BASE_URL}/calendar/events`, {
//     method: 'GET',
//     headers: {
//       'Content-Type': 'application/json',
//     },
//   });
//
//   if (!response.ok) {
//     throw new Error(`Failed to fetch events: ${response.statusText}`);
//   }
//
//   return response.json();
// }
