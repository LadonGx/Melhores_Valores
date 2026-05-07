import axios from 'axios';

export const api = axios.create({
  // Em dev, usa o proxy do Vite (/api → http://localhost:8000).
  // Em produção, define VITE_API_URL com a URL completa do backend.
  baseURL: import.meta.env.VITE_API_URL ?? '/api',
  headers: { 'Content-Type': 'application/json' },
  timeout: 30_000,
});

api.interceptors.response.use(
  (response) => response,
  (error) => {
    const message = error.response?.data?.detail ?? error.message;
    return Promise.reject(new Error(message));
  }
);
