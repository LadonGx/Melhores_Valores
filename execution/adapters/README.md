# execution/adapters/ — Store HTML Parsers

## Objective
Parse raw HTML from each e-commerce store into a normalized product dict. Each adapter is fully isolated — one file per store.

## Responsibilities
- Extract `name`, `price`, `image_url` from raw HTML
- Return `None` on parse failure (never raise to caller)
- Handle store-specific HTML structure variations

## Files

| File | Store | Notes |
|---|---|---|
| `amazon.py` | Amazon BR | Handles JS-rendered and static HTML variants |
| `mercadolivre.py` | Mercado Livre | Always receives Playwright-rendered HTML |

## Interface Contract

Every adapter exposes a single public function:

```python
def parse_product(html: str) -> dict | None:
    """
    Returns:
        {
            "name": str,
            "price": float | None,   # None if out of stock
            "image_url": str | None
        }
    or None if parsing fails entirely.
    """
```

## Who Calls Adapters

Only `scraping_orchestrator.py`. Never call adapters directly from tasks or web_server.

```python
# In scraping_orchestrator.py:
from execution.adapters import amazon, mercadolivre

result = amazon.parse_product(html)
```

## Conventions

- CSS selectors or BeautifulSoup — no assumptions about JS state (html is already rendered by caller)
- `price` is always a Python `float`, never a formatted string
- `name` is stripped of whitespace
- Return `None` for the whole dict if the page is a CAPTCHA/block page or structure is unrecognizable
- Do NOT check for garbage names here — `db_client.py` handles that

## Amazon: where the price comes from (`offer_type`)

`amazon.py` only reads prices from the product's own price areas — never from the whole page, because
carousels / sponsored cards (`#sp_detail*`, `sims-*`, `CardInstance*`, `#similarities*`) also use `span.a-price`
and, on listings without a main offer, they were being saved as the product price.

Order of trust (first hit wins):

1. `priceToPay` / `apexPriceToPay` with a filled `a-offscreen`, then any non-struck `span.a-price` `a-offscreen`,
   only inside `#corePrice_feature_div`, `#corePriceDisplay_desktop_feature_div`, `#apex_desktop*`, `#mediaTab_heading_0`;
2. legacy ids (`#priceblock_*`, `#price_inside_buybox`);
3. the SELECTED format button in `#tmmSwatches` when it shows a direct price (also covers Kindle). It runs before the
   whole/fraction split because on some listings the visible block has an empty `a-offscreen` and a different
   whole/fraction (e.g. 67,45) while the selected button (and `#tp_price_block_total_price_ww`) say the real 71,00;
4. whole + fraction split, same containers as (1);
5. "a partir de" price of the selected format button (no main offer, only other sellers).

`#buybox` is not read on its own: it also exists on listings without a main offer and its content is only the
same price blocks above.

New optional key `offer_type` in the returned dict (Mercado Livre never sets it):

| `offer_type` | Meaning | `price` | `confidence_score` |
|---|---|---|---|
| `main` | Main offer price (steps 1–4) | set | as before (≥ 0.72) |
| `third_party_from` | No main offer; "a partir de" of other sellers (step 5) | set | 0.6 |
| `none` | Product page read fine, Amazon only shows "Ver todas as opções de compra" (`#buybox-see-all-buying-choices` / `#all-offers-display`), no "a partir de" | `None`, `in_stock: True` | 0.6 |

`none` is never used for a confirmed out-of-stock page (that keeps `in_stock: False` and no `offer_type`). A page
without a price and without that positive "no main offer" sign (or without a product title) still returns `None`,
so the cascade escalates as before — the price block may simply be missing from that HTML.

### Seller of the offer (`seller_type`, `seller_name`)

When a price is found, `amazon.py` also says who sells that offer, read from the "Enviado / Vendido"
block (`#merchantInfoFeature_feature_div`, or the older `#merchant-info`):

| `seller_type` | When | `seller_name` |
|---|---|---|
| `amazon` | Seller is exactly "Amazon.com.br" (a store whose name only *contains* "amazon" is a third party), or a Kindle e-book without a seller block | `None` |
| `third_party` | Another seller holds the buy box (e.g. Amazon ran out) | seller name |
| `third_party_from` | `offer_type: "third_party_from"` — no buy box, only "a partir de" | `None` |
| `None` | No seller information on the page | `None` |

Third-party prices are **kept** in `PriceHistory` (`sellerType` / `sellerName`) because they show the market,
but price stats, group stats and promotions ignore them while the listing has its own (Amazon / unknown) prices.
A seller change with the same price is a new history row (deduplication compares the seller too). Regression tests use real
pages in `execution/tests/fixtures/amazon/`. Old wrong history rows: `docs/revisao-precos-amazon.md`.

### Format of the listing (`format`)

New key in every product dict returned by `extract_from_html` (including out-of-stock, `offer_type: "none"` and
blocked pages, where it is `None`): `"format": "ebook_kindle" | "physical" | None`. The pipeline saves it with
`db_client.set_product_format` on every successful check. It does not depend on there being a price, and reading it
never changes price, `offer_type`, `seller_type` or confidence.

| `format` | Means | Typical page |
|---|---|---|
| `"ebook_kindle"` | The listing is the eBook Kindle edition | "Formato: eBook Kindle", trail "Loja Kindle › eBooks Kindle", selected button "Kindle R$ …" |
| `"physical"` | Physical edition (Capa comum/dura, Brochura) | "Formato: Capa comum/dura", selected button "Capa Comum R$ …" |
| `None` | Unknown / not applicable | Electronics, consoles, no book signals at all |

Sources, in order of trust — the first source that yields a format wins, so contradictions between sources are
always settled by the strongest one (e.g. selected button "Capa Comum" beats a `<title>` that mentions eBooks Kindle):

1. SELECTED button in `#tmmSwatches` (`.a-button-selected`) — the format actually on offer; its text starts with the
   format name, so the standalone word "kindle" counts here;
2. format line "Formato: …" in `#productSubtitle` or `#bylineInfo` (e.g. "Formato: Capa comum");
3. store trail "Loja Kindle › eBooks Kindle" in `#wayfinding-breadcrumbs_feature_div` — Kindle only: the "Livros" trail
   of physical books is not a signal;
4. `<title>` (Kindle pages start with "Amazon.com.br eBooks Kindle: …").

Within the same source, Kindle signals are checked before physical ones ("eBook Kindle" is more specific and never
coexists with "Capa comum/dura" in a format line). Outside the selected button, only the full phrases
"eBook Kindle"/"eBooks Kindle"/"Loja Kindle" identify Kindle — a physical book whose title merely mentions Kindle is
not misread. Mercado Livre never returns the key.

## What NOT to Change Without Confirmation

- Do not change the return dict keys (`name`, `price`, `image_url`) — used throughout the system
- Do not add network calls — adapters are pure HTML parsers
- Do not import `db_client` or `cache_manager`

## Risks

- Store HTML structure changes break parsers silently (returns None)
- Adding a new key to the return dict requires updating callers
- Duplicate adapters for the same store create confusion — one file per store, always

## Adding a New Store Adapter

1. Create `execution/adapters/<store>.py`
2. Implement `parse_product(html: str) -> dict | None`
3. Add store detection in `execution/store_detection.py`
4. Add scraping logic in `execution/scraping_orchestrator.py`
5. Update `packages/types/src/index.ts` `Store` type
