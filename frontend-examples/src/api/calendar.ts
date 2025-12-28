/**
 * Calendar API Client
 * Handles all HTTP requests to the calendar service
 */

import type { HealthResponse } from './types';

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL;
const API_KEY = import.meta.env.VITE_API_KEY;

/**
 * Get default headers for API requests
 * Includes API key if configured
 */
function getHeaders(): HeadersInit {
  const headers: HeadersInit = {
    'Content-Type': 'application/json',
  };

  if (API_KEY) {
    headers['X-API-Key'] = API_KEY;
  }

  return headers;
}

/**
 * Health check endpoint
 * @returns Service health status
 */
export async function getHealth(): Promise<HealthResponse> {
  const response = await fetch(`${API_BASE_URL}/calendar/health`, {
    method: 'GET',
    headers: getHeaders(),
  });

  if (!response.ok) {
    throw new Error(`Health check failed: ${response.statusText}`);
  }

  return response.json();
}

/**
 * Get all calendar days
 * @returns Dictionary with day numbers as keys
 */
export async function getCalendarDays(): Promise<Record<string, any>> {
  const response = await fetch(`${API_BASE_URL}/calendar/days`, {
    method: 'GET',
    headers: getHeaders(),
  });

  if (!response.ok) {
    throw new Error(`Failed to fetch calendar days: ${response.statusText}`);
  }

  return response.json();
}

/**
 * Get a specific calendar day
 * @param dayNumber Day number (1-24)
 * @returns Day data
 */
export async function getCalendarDay(dayNumber: number): Promise<any> {
  const response = await fetch(`${API_BASE_URL}/calendar/days/${dayNumber}`, {
    method: 'GET',
    headers: getHeaders(),
  });

  if (!response.ok) {
    throw new Error(`Failed to fetch day ${dayNumber}: ${response.statusText}`);
  }

  return response.json();
}
