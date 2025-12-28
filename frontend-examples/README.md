# Frontend Integration Examples

This directory contains example TypeScript/React files for integrating with the backend API.

## 📁 Files Overview

```
frontend-examples/
├── .env.example              # Environment configuration
├── src/
│   ├── api/
│   │   ├── types.ts         # TypeScript interfaces for API responses
│   │   └── calendar.ts      # Calendar API client functions
│   └── components/
│       └── HealthCheck.tsx  # Example React component
```

## 🚀 How to Use

### 1. Copy Files to Your Frontend Project

Copy these files to your React/Vite frontend project:

```bash
# From your frontend project root
cp -r ../backend/frontend-examples/src/api ./src/
cp -r ../backend/frontend-examples/src/components ./src/
cp ../backend/frontend-examples/.env.example ./.env
```

### 2. Configure Environment Variables

Edit `.env` in your frontend project:

```env
# For local development
VITE_API_BASE_URL=http://localhost

# For production
VITE_API_BASE_URL=https://api.vuhnger.dev
```

### 3. Use in Your React App

```tsx
import { HealthCheck } from './components/HealthCheck';

function App() {
  return (
    <div>
      <h1>My App</h1>
      <HealthCheck />
    </div>
  );
}
```

## 📚 API Client Pattern

All API calls follow this pattern:

```typescript
// 1. Define the response type in types.ts
export interface SomeResponse {
  data: string;
}

// 2. Create the API function in calendar.ts
export async function getSomething(): Promise<SomeResponse> {
  const response = await fetch(`${API_BASE_URL}/calendar/something`);
  if (!response.ok) throw new Error('Failed');
  return response.json();
}

// 3. Use in React components
const [data, setData] = useState<SomeResponse | null>(null);
useEffect(() => {
  getSomething().then(setData);
}, []);
```

## 🔒 Adding Authentication (STEP 5)

When API key authentication is added in STEP 5, update the fetch calls:

```typescript
export async function getHealth(): Promise<HealthResponse> {
  const response = await fetch(`${API_BASE_URL}/calendar/health`, {
    headers: {
      'Content-Type': 'application/json',
      'X-API-Key': import.meta.env.VITE_API_KEY, // Add this
    },
  });
  // ...
}
```

## ⚠️ Important Notes

- These are **placeholder/boilerplate files only**
- No business logic implemented yet
- Only the health endpoint is functional
- Future endpoints are commented out as examples
- DO NOT implement calendar features until backend is ready
