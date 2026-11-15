import { render, screen } from '@testing-library/react';
import { describe, it, expect } from 'vitest';
import type { Product } from '@mv/types';
import { MIXED_FORMATS_WARNING } from '../format';
import { MixedFormatsWarning } from './MixedFormatsWarning';

function product(format: Product['format']): Product {
  return {
    id: `p-${format ?? 'unknown'}`,
    url: 'https://www.amazon.com.br/dp/x',
    name: 'Anúncio',
    store: 'amazon',
    image_url: null,
    format,
    created_at: '2026-11-01T00:00:00.000Z',
    updated_at: '2026-11-01T00:00:00.000Z',
  };
}

describe('MixedFormatsWarning', () => {
  it('shows the warning when the selection mixes kindle and physical', () => {
    render(<MixedFormatsWarning products={[product('ebook_kindle'), product('physical')]} />);
    expect(screen.getByRole('note')).toHaveTextContent(MIXED_FORMATS_WARNING);
  });

  it('does not render when formats are compatible or unknown', () => {
    const { rerender } = render(
      <MixedFormatsWarning products={[product('ebook_kindle'), product('ebook_kindle')]} />,
    );
    expect(screen.queryByRole('note')).toBeNull();

    rerender(<MixedFormatsWarning products={[product('physical'), product(null)]} />);
    expect(screen.queryByRole('note')).toBeNull();

    rerender(<MixedFormatsWarning products={[]} />);
    expect(screen.queryByRole('note')).toBeNull();
  });
});
