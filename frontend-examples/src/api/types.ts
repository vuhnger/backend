/**
 * API Response Types
 * These match the structure returned by the backend API
 */

export interface HealthResponse {
  status: string;
  service: string;
}

// Future types will be added here as endpoints are implemented
// Example:
// export interface Event {
//   id: string;
//   title: string;
//   start: string;
//   end: string;
// }
