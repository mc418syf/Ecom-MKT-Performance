# Ecom-MKT-Performance

Livestock weekly marketing + product performance dashboard (weeks start Sunday, America/Vancouver).

## Weekly refresh
1. Create `data/<week>/` (e.g. `data/wk39/`) with three files, keeping the date range in each name:
   - `channel_<start>_<end>.csv` – Shopify "Performance by marketing channel"
   - `campaign_<start>_<end>.csv` – Shopify "Performance by marketing campaign"
   - `product_sales_<start>_<end>.csv` – daily product sales lines (date x SKU)
2. `python3 build/build.py` (needs pandas) rewrites `index.html`.
3. Open `index.html`. A week selector and week-over-week deltas appear once two weeks are loaded.

## Known limits
Channel/campaign exports are weekly totals with no spend, so the product-vs-channel correlation is timeline-only until a daily
export, a product x channel file and a campaign log are added.
