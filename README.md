# Ecom-MKT-Performance

Livestock marketing + product performance dashboard (weeks start Sunday, America/Vancouver). Open `index.html`.

Tabs: Summary · Channels · Campaigns · Product Performance · Product × Channel · Method.
Date range, presets, comparison (previous period / same weeks last year / custom) and Day/Week/Month grain apply across the dashboard.

## Data (`data/`)
| Folder | Shopify export | Notes |
|---|---|---|
| `channels/` | Top performing marketing channels by day | last click, includes direct |
| `campaigns/` | Top performing marketing campaigns by day | last non-direct click |
| `product/` | Product sales lines (date x SKU x size x province) | zero-sales lines can be left in; they are dropped |
| `sku_images.csv` | SKU -> image URL | optional |

## Weekly refresh
1. Put the new daily exports in the folders above, with the date range in each file name (`..._2026-10-25_2026-10-31.csv`).
   A newer file replaces any dates it repeats, so overlapping exports are fine.
2. `python3 build/build.py` (needs pandas) rewrites `index.html`.

## Known limits
No ad spend, impressions or clicks in the exports, so no ROAS/CPA/CAC. Campaign data starts 2026-09-21.
