#!/usr/bin/env python3
"""Build index.html from the daily exports in data/.

data/channels/*.csv   Shopify "Top performing marketing channels by day"  (Day, Traffic type, Marketing channel, ...)
data/campaigns/*.csv  Shopify "Top performing marketing campaigns by day" (Day, Marketing campaign, Marketing channel, ...)
data/product/*.csv    product sales lines (Date, SKU, Product Title, ... Net Sales, Net Quantity)
data/sku_images.csv   SKU -> image URL (optional)

Files in a folder may overlap. Files are applied oldest first by the end date in the filename,
and a newer file replaces every date it contains, so a weekly export can simply be dropped in.
Usage: python3 build/build.py   (needs pandas)
"""
import glob, json, os, re
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

EMAIL = {"klaviyo", "spently", "mailchimp", "shopify_email", "gmail", "outlook.com"}
SEARCH = {"google", "bing", "duckduckgo", "ecosia", "yahoo!", "brave", "startpage", "baidu", "naver", "msn"}
SOCIAL = {"instagram", "facebook", "meta", "linktr", "pinterest", "reddit", "x", "youtube", "substack"}
AI = {"chatgpt", "perplexity", "gemini"}
PARTNER = {"couponbirds", "valuecom", "wethrift", "partnerize", "sovrn", "afterpay", "klarna", "sezzle", "zephr"}


def group(channel, traffic):
    """Roll raw source + traffic type up to a marketing channel group."""
    if channel == "(unattributed)":
        return "Unattributed"
    if channel == "direct":
        return "Direct"
    if channel in EMAIL:
        return "Email"
    if channel == "google_ads" or (channel in SEARCH and traffic == "paid"):
        return "Paid Search"
    if channel == "meta_ads" or (channel in SOCIAL and traffic == "paid"):
        return "Paid Social"
    if channel in SEARCH:
        return "Organic Search"
    if channel in SOCIAL:
        return "Organic Social"
    if channel in AI:
        return "AI Assistants"
    if channel in PARTNER:
        return "Affiliates & Partners"
    return "Other / Unclassified"


def clean_campaign(name):
    """Strip Klaviyo ids/clone suffixes so clones of one send merge."""
    n = re.sub(r"\s*\(clone\)", "", str(name))
    n = re.sub(r"\s*\([A-Za-z0-9]{6,30}\)\s*$", "", n)
    return n.strip()


def message_id(name):
    """Klaviyo message id Shopify appends to campaign names, e.g. "... (01M5MXQECX3TF78FJF2J7YMN9F)"."""
    m = re.search(r"\(([A-Za-z0-9]{20,30})\)\s*$", str(name))
    return m.group(1) if m else ""


def end_of(path):
    m = re.findall(r"\d{4}-\d{2}-\d{2}", os.path.basename(path))
    return m[-1] if m else ""


def load_folder(folder, datecol, **kw):
    """Read every CSV in data/<folder>; a newer file replaces the dates it contains."""
    out = None
    for f in sorted(glob.glob(os.path.join(ROOT, "data", folder, "*.csv")), key=end_of):
        df = pd.read_csv(f, **kw)
        df[datecol] = pd.to_datetime(df[datecol]).dt.strftime("%Y-%m-%d")
        out = df if out is None else pd.concat([out[~out[datecol].isin(set(df[datecol]))], df], ignore_index=True)
    if out is None:
        raise SystemExit(f"no CSV files in data/{folder}")
    return out


def table(values):
    vals = sorted(set(values))
    return vals, {v: i for i, v in enumerate(vals)}


# ---------------------------------------------------------------- channels (daily)
c = load_folder("channels", "Day")
c.columns = ["day", "traffic", "channel", "sales", "sessions", "orders", "cvr", "aov", "newc", "retc"]
c["channel"] = c.channel.fillna("(unattributed)")
c["traffic"] = c.traffic.fillna("(none)")
c = c[(c.sales != 0) | (c.sessions != 0) | (c.orders != 0)]
c["group"] = [group(a, t) for a, t in zip(c.channel, c.traffic)]
c = c.groupby(["day", "channel", "traffic", "group"], as_index=False)[["sales", "sessions", "orders", "newc", "retc"]].sum()
c_days, c_dix = table(c.day)
pairs = c[["channel", "traffic", "group"]].drop_duplicates().sort_values(["group", "channel", "traffic"]).reset_index(drop=True)
p_ix = {(r.channel, r.traffic): i for i, r in pairs.iterrows()}
c_rows = [[c_dix[r.day], p_ix[(r.channel, r.traffic)], round(r.sales, 2), int(r.sessions), int(r.orders), int(r.newc), int(r.retc)]
          for r in c.sort_values("day").itertuples()]
channels = {"days": c_days, "pairs": pairs.to_dict("records"), "rows": c_rows,
            "fields": ["d", "pair", "sales", "sessions", "orders", "new", "ret"],
            "attribution": "last click (includes direct)"}

# ---------------------------------------------------------------- campaigns (daily)
k = load_folder("campaigns", "Day")
k.columns = ["day", "campaign", "channel", "traffic", "sales", "sessions", "orders", "cvr", "aov", "newc", "retc"]
k["mid"] = k.campaign.map(message_id)
k["campaign"] = k.campaign.map(clean_campaign)
k = k[(k.sales != 0) | (k.sessions != 0) | (k.orders != 0)]
k["group"] = [group(a, t) for a, t in zip(k.channel, k.traffic)]
k = k.groupby(["day", "campaign", "mid", "channel", "traffic", "group"], as_index=False)[["sales", "sessions", "orders", "newc", "retc"]].sum()
k_days, k_dix = table(k.day)
camps = k[["campaign", "mid", "channel", "traffic", "group"]].drop_duplicates().sort_values(["campaign", "channel", "mid"]).reset_index(drop=True)
cp_ix = {(r.campaign, r.mid, r.channel, r.traffic): i for i, r in camps.iterrows()}
k_rows = [[k_dix[r.day], cp_ix[(r.campaign, r.mid, r.channel, r.traffic)], round(r.sales, 2), int(r.sessions), int(r.orders), int(r.newc), int(r.retc)]
          for r in k.sort_values("day").itertuples()]
campaigns = {"days": k_days, "camps": camps.to_dict("records"), "rows": k_rows,
             "fields": ["d", "camp", "sales", "sessions", "orders", "new", "ret"],
             "attribution": "last non-direct click"}

# ---------------------------------------------------------------- Klaviyo exports
def pct(v):
    return float(str(v).rstrip("%")) / 100 if pd.notna(v) else None


kl_campaigns, seen = [], {}
for f in sorted(glob.glob(os.path.join(ROOT, "data", "klaviyo", "campaignListReport_*.csv")), key=end_of):
    for r in pd.read_csv(f).itertuples(index=False):
        seen[r[1]] = {
            "id": r[0], "mid": r[1], "name": str(r[2]), "date": str(r[6])[:10], "time": str(r[6])[11:16], "dow": r[7],
            "subject": "" if pd.isna(r[8]) else str(r[8]), "audience": "" if pd.isna(r[5]) else str(r[5]),
            "recipients": int(r[10] or 0), "conv": 0, "convValue": 0.0, "uopens": int(r[16] or 0), "uclicks": int(r[19] or 0),
            "clicks": int(r[21] or 0), "unsub": int(r[22] or 0), "spam": int(r[24] or 0), "delivered": int(r[26] or 0),
            "bounced": int(r[27] or 0), "hasRev": False}
# campaign report from the Klaviyo API (Placed Order conversion metric): adds real revenue and orders
for f in sorted(glob.glob(os.path.join(ROOT, "data", "klaviyo", "campaign_report_*.csv")), key=end_of):
    for r in pd.read_csv(f).itertuples(index=False):
        if len(r) > 12 and r[12] != "email":
            continue  # push / SMS are not part of the email view
        d = seen.setdefault(r[0], {"id": r[0], "mid": r[0], "name": str(r[1]), "date": str(r[2]), "time": str(r[3]), "dow": "",
                                   "subject": "", "audience": "", "clicks": 0, "spam": 0, "bounced": 0})
        d.update({"audience": d.get("audience") or ("" if pd.isna(r[4]) else str(r[4])), "recipients": int(r[5] or 0), "delivered": int(r[6] or 0),
                  "uopens": int(r[7] or 0), "uclicks": int(r[8] or 0), "unsub": int(r[9] or 0), "conv": int(r[10] or 0),
                  "convValue": round(float(r[11] or 0), 2), "hasRev": True})
kl_campaigns = sorted(seen.values(), key=lambda x: x["date"])

# daily flow performance: deliveries (Received Email) and Placed Order revenue/orders attributed to each flow
fd_days, fd_flows, fd_rows = [], [], []
fdf = sorted(glob.glob(os.path.join(ROOT, "data", "klaviyo", "flow_daily_*.csv")), key=end_of)
if fdf:
    fdd = pd.read_csv(fdf[-1])
    fd_days, d_ix2 = table(fdd.Day)
    fd_flows, f_ix2 = table(fdd.Flow)
    cols = list(fdd.columns)   # Day, Flow ID, Flow, Deliveries, Revenue, Orders, Opens, Unique opens, Clicks, Unique clicks
    fd_rows = [[d_ix2[r[0]], f_ix2[r[2]], int(r[3]), round(float(r[4]), 2), int(r[5]),
                int(r[7]) if len(r) > 7 else 0, int(r[9]) if len(r) > 9 else 0] for r in fdd.itertuples(index=False)]
cd_days, cd_rows = [], []
cdf = sorted(glob.glob(os.path.join(ROOT, "data", "klaviyo", "campaign_daily_*.csv")), key=end_of)
if cdf:
    cdd = pd.read_csv(cdf[-1])
    cd_days = list(cdd.Day)
    # Day, Deliveries, Revenue, Orders, Opens, Unique opens, Clicks, Unique clicks
    cd_rows = [[i, int(r[1]), round(float(r[2]), 2), int(r[3]), int(r[5]), int(r[7])] for i, r in enumerate(cdd.itertuples(index=False))]
kl_flows, flow_file = [], ""
ff = sorted(glob.glob(os.path.join(ROOT, "data", "klaviyo", "flow-analytics_*.csv")), key=end_of)
if ff:
    flow_file = end_of(ff[-1])
    for r in pd.read_csv(ff[-1]).itertuples(index=False):
        kl_flows.append({"flow": str(r[1]), "revenue": float(r[2] or 0), "conv": int(r[3] or 0), "convRate": pct(r[4]),
                         "deliveries": int(r[5] or 0), "recipients": int(r[6] or 0)})
klaviyo = {"campaigns": kl_campaigns, "flows": kl_flows, "flow_file": flow_file,
           "flow_daily": {"days": fd_days, "flows": fd_flows, "rows": fd_rows, "fields": ["d", "flow", "deliveries", "revenue", "orders", "uopens", "uclicks"]},
           "campaign_daily": {"days": cd_days, "rows": cd_rows, "fields": ["d", "deliveries", "revenue", "orders", "uopens", "uclicks"]}}

# ---------------------------------------------------------------- products (daily lines)
P = load_folder("product", "Date", dtype={"SKU": str, "Size": str})
raw_lines = len(P)
P = P[(P["Net Sales"] != 0) | (P["Net Quantity"] != 0)]
for col in ["SKU", "Product Title", "Product Vendor", "Product Type", "Province", "Size", "Status", "Release", "Season", "Department", "Class", "Sub Class"]:
    P[col] = P[col].astype(str).replace({"nan": "(blank)", "False": "(blank)", "0": "(blank)"})
keys = ["Date", "SKU", "Status", "Release", "Size", "Province", "Product Vendor", "Product Type", "Department", "Class", "Sub Class", "Season"]
sale_lines = len(P)
P = P.groupby(keys, as_index=False).agg(net=("Net Sales", "sum"), units=("Net Quantity", "sum"))

p_days, p_dix = table(P.Date)
skus, s_ix = table(P.SKU)
title = pd.read_csv(sorted(glob.glob(os.path.join(ROOT, "data", "product", "*.csv")), key=end_of)[-1], dtype={"SKU": str},
                    usecols=["SKU", "Product Title"]).dropna().groupby("SKU")["Product Title"].agg(lambda s: s.mode().iat[0])
imgs = {}
ip = os.path.join(ROOT, "data", "sku_images.csv")
if os.path.exists(ip):
    imgs = dict(pd.read_csv(ip, dtype=str).fillna("").values)

dims, enc = {}, {}
for col, key in [("Status", "status"), ("Release", "release"), ("Size", "size"), ("Province", "province"), ("Product Vendor", "vendor"),
                 ("Product Type", "type"), ("Department", "dept"), ("Class", "cls"), ("Sub Class", "sub"), ("Season", "season")]:
    dims[key], enc[col] = table(P[col])
P = P.sort_values(["Date", "SKU"])
p_rows = [[p_dix[r.Date], s_ix[r.SKU], enc["Status"][r.Status], enc["Release"][r.Release], enc["Size"][r.Size], enc["Province"][r.Province],
           enc["Product Vendor"][r._7], enc["Product Type"][r._8], enc["Department"][r.Department], enc["Class"][r.Class],
           enc["Sub Class"][r._11], enc["Season"][r.Season], round(r.net, 2), int(r.units)] for r in P.itertuples()]
product = {"days": p_days, "skus": [{"sku": s, "title": title.get(s, s), "img": imgs.get(s, "")} for s in skus],
           "dims": {k2: v[0] if isinstance(v, tuple) else v for k2, v in dims.items()},
           "rows": p_rows,
           "fields": ["d", "s", "status", "release", "size", "province", "vendor", "type", "dept", "cls", "sub", "season", "net", "units"],
           "raw_lines": raw_lines, "sale_lines": sale_lines}

data = {"banner": "Livestock", "tz": "America/Vancouver", "week_start": "Sunday",
        "channels": channels, "campaigns": campaigns, "product": product, "klaviyo": klaviyo}
with open(os.path.join(ROOT, "build", "template.html")) as f:
    tpl = f.read()
html = tpl.replace("/*__DATA__*/null", json.dumps(data, separators=(",", ":"), default=float))
with open(os.path.join(ROOT, "index.html"), "w") as f:
    f.write(html)
print(f"built index.html {len(html)/1e6:.1f} MB | channels {len(c_rows):,} rows {c_days[0]}..{c_days[-1]} | "
      f"campaigns {len(k_rows):,} rows {k_days[0]}..{k_days[-1]} | product {len(p_rows):,} rows {p_days[0]}..{p_days[-1]} | "
      f"klaviyo {len(kl_campaigns)} campaigns, {len(fd_rows)} daily flow rows")
