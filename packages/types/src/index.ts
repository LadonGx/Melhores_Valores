// ─── API Responses ───────────────────────────────────────────────────────────

export interface HealthResponse {
  status: string;
  message: string;
}

export interface AddProductResponse {
  message: string;
  task_id: string;
  status: 'queued' | 'processing';
  url: string;
  store: string;
}

export interface SearchResponse {
  status: 'processing';
  task_id: string;
  query: string;
  message: string;
}

export interface SearchResultsResponse {
  search_id: string;
  total: number;
  results: SearchResult[];
}

// ─── Domain Models ────────────────────────────────────────────────────────────

export type Store = 'amazon' | 'mercadolivre' | 'aliexpress' | string;

export interface Product {
  id: string;
  url: string;
  name: string | null;
  store: Store;
  image_url: string | null;
  created_at: string;
  updated_at: string;
}

export interface PriceHistoryEntry {
  id: string;
  price: number;
  created_at: string;
}

export interface ProductWithHistory {
  product: Product;
  current_price: number | null;
  lowest_price: number | null;
  average_price: number | null;
  history: PriceHistoryEntry[];
}

export interface SearchResult {
  id: string;
  search_id: string;
  store: Store;
  title: string;
  price: number;
  currency: string;
  image_url: string | null;
  product_url: string;
  rating: number | null;
  review_count: number | null;
}

// ─── UI ───────────────────────────────────────────────────────────────────────

export type TaskStatus = 'queued' | 'processing' | 'completed' | 'failed';
