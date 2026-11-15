import { render, screen } from '@testing-library/react';
import { describe, it, expect } from 'vitest';
import type { Product } from '@mv/types';
import { KindleBadge } from './KindleBadge';

function product(format: Product['format']): Product {
  return {
    id: `p-${format ?? 'unknown'}`,
    url: 'https://www.amazon.com.br/dp/x',
    name: 'Ritmo da Guerra',
    store: 'amazon',
    image_url: null,
    format,
    created_at: '2026-11-01T00:00:00.000Z',
    updated_at: '2026-11-01T00:00:00.000Z',
  };
}

describe('KindleBadge', () => {
  it('renders the Kindle badge only for ebook_kindle listings', () => {
    render(<KindleBadge product={product('ebook_kindle')} />);
    expect(screen.getByText('Kindle')).toBeInTheDocument();
  });

  it('renders nothing for physical or unknown formats', () => {
    const { rerender } = render(<KindleBadge product={product('physical')} />);
    expect(screen.queryByText('Kindle')).toBeNull();

    rerender(<KindleBadge product={product(null)} />);
    expect(screen.queryByText('Kindle')).toBeNull();

    rerender(<KindleBadge product={product(undefined)} />);
    expect(screen.queryByText('Kindle')).toBeNull();
  });
});
