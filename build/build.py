#!/usr/bin/env python3
"""Build index.html from the weekly exports in data/<week>/.

Per week folder:
  channel_<start>_<end>.csv       Shopify "Performance by marketing channel" (weekly totals, last non-direct click)
  campaign_<start>_<end>.csv      Shopify "Performance by marketing campaign"
  product_sales_<start>_<end>.csv daily product sales lines (date x SKU x size x province)

Usage: python3 build/build.py   (needs pandas)
"""
import glob, json, os, re
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SALES = "Total sales (last non-direct click)"
ORDERS = "Orders (last non-direct click)"


def clean_campaign(name):
    """Strip Klaviyo ids/clone suffixes so clones of one send merge."""
    n = re.sub(r"\s*\(clone\)", "", name)
    n = re.sub(r"\s*\([A-Za-z0-9]{6,30}\)\s*$", "", n)
    return n.strip()


def span(path):
    m = re.search(r"(\d{4}-\d{2}-\d{2})_(\d{4}-\d{2}-\d{2})", path)
    return m.group(1), m.group(2)


weeks = []
for wd in sorted(glob.glob(os.path.join(ROOT, "data", "*"))):
    if not os.path.isdir(wd):
        continue
    ch = glob.glob(os.path.join(wd, "channel_*.csv"))
    ca = glob.glob(os.path.join(wd, "campaign_*.csv"))
    pr = glob.glob(os.path.join(wd, "product_sales_*.csv"))
    if not (ch and ca and pr):
        continue
    start, end = span(ch[0])

    # ---- channels
    c = pd.read_csv(ch[0])
    c.columns = ["channel", "traffic", "sales", "sessions", "orders", "cvr", "spend", "roas", "cpa", "cac",
                 "impr", "clicks", "ctr", "aov", "new_cust", "ret_cust"]
    adjustments = c[c.sales < 0]
    c = c[c.sales >= 0]
    active = c[(c.sales > 0) | (c.orders > 0)]
    tail = c.drop(active.index)
    chan = active[["channel", "traffic", "sales", "sessions", "orders", "new_cust", "ret_cust"]].to_dict("records")
    tail_row = {"channel": f"{len(tail)} other sources (no sales)", "traffic": "mixed", "sales": 0.0,
                "sessions": int(tail.sessions.sum()), "orders": 0, "new_cust": 0, "ret_cust": 0}

    # ---- campaigns
    k = pd.read_csv(ca[0])
    k.columns = ["campaign", "channel", "traffic", "sales", "sessions", "orders", "cvr", "spend", "roas", "cpa",
                 "cac", "impr", "clicks", "ctr", "aov", "new_cust", "ret_cust"]
    k["campaign_clean"] = k.campaign.map(clean_campaign)
    kn = k[k.sales >= 0]
    kg = (kn.groupby(["campaign_clean", "channel", "traffic"], as_index=False)
            [["sales", "sessions", "orders", "new_cust", "ret_cust"]].sum())
    kg = kg[(kg.sales > 0) | (kg.orders > 0)].sort_values("sales", ascending=False)

    # ---- products
    p = pd.read_csv(pr[0], dtype={"SKU": str}, parse_dates=["Date"])
    p["day"] = p.Date.dt.strftime("%Y-%m-%d")
    daily = (p.groupby("day").agg(sales=("Net Sales", "sum"), units=("Net Quantity", "sum"),
                                  release_sales=("Net Sales", lambda s: s[p.loc[s.index, "Release"] == "Release"].sum()),
                                  md_sales=("Net Sales", lambda s: s[p.loc[s.index, "Status"] == "Markdowns"].sum()))
               .reset_index().to_dict("records"))
    sku = (p.groupby(["SKU", "Product Title", "Product Vendor", "Department", "Release"], as_index=False)
             .agg(sales=("Net Sales", "sum"), units=("Net Quantity", "sum")).sort_values("sales", ascending=False))
    top = sku.head(15)
    sku_day = (p[p.SKU.isin(top.SKU)].groupby(["SKU", "day"], as_index=False)
                 .agg(sales=("Net Sales", "sum"), units=("Net Quantity", "sum")))
    vendor = (p.groupby("Product Vendor", as_index=False).agg(sales=("Net Sales", "sum"), units=("Net Quantity", "sum"))
                .sort_values("sales", ascending=False).head(10))

    in_window = p[p.day <= end]
    weeks.append({
        "start": start, "end": end,
        "channels": chan, "channel_tail": tail_row,
        "adjustments": adjustments[["channel", "sales"]].to_dict("records"),
        "campaigns": kg.head(25).rename(columns={"campaign_clean": "campaign"}).to_dict("records"),
        "campaign_adjustments": k[k.sales < 0][["campaign_clean", "channel", "sales"]]
            .rename(columns={"campaign_clean": "campaign"}).to_dict("records"),
        "attributed_total": round(float(c.sales.sum()), 2),
        "attributed_net_of_adj": round(float(c.sales.sum() + adjustments.sales.sum()), 2),
        "paid_spend_filled": bool(c.spend.notna().any()),
        "product_daily": daily,
        "product_total_in_window": round(float(in_window["Net Sales"].sum()), 2),
        "product_total_all": round(float(p["Net Sales"].sum()), 2),
        "product_units_in_window": int(in_window["Net Quantity"].sum()),
        "product_rows": int(len(p)),
        "product_exact_dupe_rows": int(p.duplicated().sum()),
        "top_products": top.to_dict("records"),
        "top_product_daily": sku_day.to_dict("records"),
        "vendors": vendor.to_dict("records"),
        "markdown_share": round(float(p[p.Status == "Markdowns"]["Net Sales"].sum() / p["Net Sales"].sum()), 4),
        "release_share": round(float(p[p.Release == "Release"]["Net Sales"].sum() / p["Net Sales"].sum()), 4),
    })

data = {"banner": "Livestock", "tz": "America/Vancouver", "week_start": "Sunday", "weeks": weeks}
with open(os.path.join(ROOT, "build", "template.html")) as f:
    tpl = f.read()
html = tpl.replace("/*__DATA__*/null", json.dumps(data, default=float))
with open(os.path.join(ROOT, "index.html"), "w") as f:
    f.write(html)
print(f"built index.html with {len(weeks)} week(s)")
