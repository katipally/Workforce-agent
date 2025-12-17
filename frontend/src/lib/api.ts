const explicitBase = import.meta.env.VITE_API_BASE_URL
  ? import.meta.env.VITE_API_BASE_URL.replace(/\/$/, '')
  : ''

// If VITE_API_BASE_URL is not set, fall back to same-origin /api
export const API_BASE_URL = explicitBase || '/api'
