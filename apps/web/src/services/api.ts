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
    // Mantém o status HTTP (undefined = sem resposta, ex.: rede fora) para quem precisar distinguir
    return Promise.reject(Object.assign(new Error(message), { status: error.response?.status }));
  }
);
