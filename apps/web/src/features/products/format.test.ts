import { describe, it, expect } from 'vitest';
import type { Product } from '@mv/types';
import {
  hasMixedFormats,
  isKindle,
  kindleBadge,
  mixedFormatsWarning,
  MIXED_FORMATS_WARNING,
} from './format';

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

describe('isKindle / kindleBadge', () => {
  it('marks only ebook_kindle as Kindle', () => {
    expect(isKindle(product('ebook_kindle'))).toBe(true);
    expect(isKindle(product('physical'))).toBe(false);
    expect(isKindle(product(null))).toBe(false);
    expect(isKindle(product(undefined))).toBe(false);
  });

  it('shows the Kindle badge only for ebook_kindle', () => {
    expect(kindleBadge(product('ebook_kindle'))).toBe('Kindle');
    expect(kindleBadge(product('physical'))).toBeNull();
    expect(kindleBadge(product(null))).toBeNull();
    expect(kindleBadge(product(undefined))).toBeNull();
  });
});

describe('hasMixedFormats', () => {
  it('is true with at least one kindle and one physical listing', () => {
    expect(hasMixedFormats([product('ebook_kindle'), product('physical')])).toBe(true);
    expect(hasMixedFormats([product('physical'), product('ebook_kindle')])).toBe(true);
    expect(
      hasMixedFormats([product(null), product('ebook_kindle'), product('physical')]),
    ).toBe(true);
  });

  it('is false when every listing has the same known format', () => {
    expect(hasMixedFormats([product('ebook_kindle'), product('ebook_kindle')])).toBe(false);
    expect(hasMixedFormats([product('physical'), product('physical')])).toBe(false);
  });

  it('is false when there is no known format', () => {
    expect(hasMixedFormats([product(null), product(undefined)])).toBe(false);
    expect(hasMixedFormats([])).toBe(false);
  });

  it('never counts the unknown format as one of the two', () => {
    expect(hasMixedFormats([product('ebook_kindle'), product(null)])).toBe(false);
    expect(hasMixedFormats([product('physical'), product(undefined)])).toBe(false);
  });
});

describe('mixedFormatsWarning', () => {
  it('returns the warning text for mixed formats', () => {
    const message = mixedFormatsWarning([product('ebook_kindle'), product('physical')]);
    expect(message).toBe(MIXED_FORMATS_WARNING);
  });

  it('returns null for compatible or unknown formats', () => {
    expect(mixedFormatsWarning([product('ebook_kindle'), product('ebook_kindle')])).toBeNull();
    expect(mixedFormatsWarning([product('physical'), product(null)])).toBeNull();
    expect(mixedFormatsWarning([])).toBeNull();
  });
});
