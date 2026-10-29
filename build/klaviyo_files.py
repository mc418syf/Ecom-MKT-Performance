#!/usr/bin/env python3
"""Turn saved Klaviyo API responses into the CSVs the dashboard reads (data/klaviyo/).

Usage: python3 build/klaviyo_files.py REVENUE.json DELIVERIES.json OPENS.json CLICKS.json CAMPAIGN_REPORT.json START END
(each input may be several comma-separated files covering different date windows)
  REVENUE     query_metric_aggregates, Placed Order, by [$attributed_flow,$attributed_message,$attributed_channel], sum_value+count
  DELIVERIES  query_metric_aggregates, Received Email, by [$flow,$message], count
  OPENS/CLICKS query_metric_aggregates, Opened/Clicked Email, by [$flow,$message], count+unique
  CAMPAIGN_REPORT  get_campaign_report with the Placed Order conversion metric
START/END are the YYYY-MM-DD window used in the queries (used in file names).
"""
import collections, csv, datetime, json, os, re, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "data", "klaviyo")
FLOW_NAMES = {
    "RW4bW3": "Delayed Fulfillment - Standard", "RcXBne": "Push - Back in Stock [Tapcart mobile app]", "RpUjzz": "Tap Cart Abandoned Cart",
    "S7VAD4": "WELCOME TO LIVESTOCK", "SD6FBt": "Sunset Unengaged Subscribers - Customer vs. Non-Customer (clone)", "TSJeSy": "CART ABANDONMENT",
    "ThUKTb": "Push - Abandoned Cart [Tapcart mobile app]", "UHB5rx": "[FR] WELCOME TO LIVESTOCK", "UKTQJr": "Wishlist Price Drop Alert - Standard",
    "ULGYQC": "ReturnZap - In-Transit", "VDGMs7": "Staff Work Anniversary 2025", "VY8GcK": "PRICE DROP", "VceMF3": "Apothecary Replen Flow",
    "WW4aVB": "BROWSE ABANDONMENT", "WtSWQy": "[FR] CART ABANDONMENT", "XMrQUB": "Push - Fulfilled Order [Tapcart mobile app]",
    "Xrys6z": "ReturnZap - Auto Approved", "Y7rJMX": "ReturnZap - Received", "Yakar9": "Cancelled Orders Discount"}


def load(path):
    d = json.load(open(path))
    return d["result"]["data"]["attributes"] if "result" in d else d["data"]["attributes"]


def local_days(dates):
    out = []
    for d in dates:
        dt = datetime.datetime.fromisoformat(d)
        out.append((dt - datetime.timedelta(hours=7 if dt.hour == 7 else 8)).strftime("%Y-%m-%d"))
    return out


def series(attrs, measure):
    """-> {(flow_id, message_id): {day: value}} merged over one or more saved responses"""
    out = collections.defaultdict(lambda: collections.defaultdict(float))
    for attr in attrs:
        days = local_days(attr["dates"])
        for s in attr["data"]:
            dims = s["dimensions"]
            vals = s["measurements"].get(measure)
            if vals is None:
                continue
            key = (dims[0], dims[1] if len(dims) > 1 else "")
            for i, v in enumerate(vals):
                if v:
                    out[key][days[i]] += v
    return out


def load_many(paths):
    attrs = []
    for p in paths.split(","):
        d = json.load(open(p))
        res = d["result"] if "result" in d else d
        nxt = (res.get("links") or {}).get("next")
        n = len(res["data"]["attributes"]["data"])
        if nxt:
            raise SystemExit(f"{p} has another page ({n} series); narrow the date window and re-run")
        attrs.append(res["data"]["attributes"])
    return attrs


def main(rev_f, del_f, opn_f, clk_f, rep_f, start, end):
    rev, dlv, opn, clk = load_many(rev_f), load_many(del_f), load_many(opn_f), load_many(clk_f)
    flow = collections.defaultdict(lambda: [0, 0, 0, 0, 0, 0.0, 0])   # deliveries, opens, uopens, clicks, uclicks, revenue, orders
    camp = collections.defaultdict(lambda: [0, 0, 0, 0, 0, 0.0, 0])
    sources = [(series(dlv, "count"), 0), (series(opn, "count"), 1), (series(opn, "unique"), 2), (series(clk, "count"), 3),
               (series(clk, "unique"), 4), (series(rev, "sum_value"), 5), (series(rev, "count"), 6)]
    for src, idx in sources:
        for (fl, msg), byday in src.items():
            tbl = camp if fl == "" else flow
            for d, v in byday.items():
                if start <= d <= end:
                    tbl[(d, fl)][idx] += v
    with open(os.path.join(OUT, f"flow_daily_{start}_{end}.csv"), "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["Day", "Flow ID", "Flow", "Deliveries (Received Email)", "Placed Order revenue (attributed)", "Placed Order count (attributed)",
                    "Opens", "Unique opens", "Clicks", "Unique clicks"])
        for (d, fl), v in sorted(flow.items()):
            w.writerow([d, fl, FLOW_NAMES.get(fl, fl), int(v[0]), round(v[5], 2), int(v[6]), int(v[1]), int(v[2]), int(v[3]), int(v[4])])
    with open(os.path.join(OUT, f"campaign_daily_{start}_{end}.csv"), "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["Day", "Deliveries (Received Email)", "Placed Order revenue (attributed)", "Placed Order count (attributed)", "Opens", "Unique opens", "Clicks", "Unique clicks"])
        for (d, _), v in sorted(camp.items()):
            w.writerow([d, int(v[0]), round(v[5], 2), int(v[6]), int(v[1]), int(v[2]), int(v[3]), int(v[4])])
    res = json.load(open(rep_f))["data"]["attributes"]["results"]
    rows = []
    for r in res:
        s = r["statistics"]; a = r["campaign_details"]["attributes"]; g = r["groupings"]
        m = re.match(r"(\w+) (\d+), (\d{4}), (\d+):(\d+)", a.get("send_time", "") or "")
        dt = datetime.datetime.strptime(f"{m.group(1)} {m.group(2)} {m.group(3)} {m.group(4)}:{m.group(5)}", "%B %d %Y %H:%M") if m else None
        aud = ", ".join(x["name"] for x in a.get("audiences", {}).get("included", []))
        rows.append([g["campaign_message_id"], a["name"], dt.strftime("%Y-%m-%d") if dt else "", dt.strftime("%H:%M") if dt else "", aud,
                     s.get("recipients"), s.get("delivered"), s.get("opens_unique"), s.get("clicks_unique"), s.get("unsubscribes"),
                     s.get("conversion_uniques"), round(s.get("conversion_value", 0) or 0, 2), g["send_channel"]])
    rows.sort(key=lambda x: x[2])
    with open(os.path.join(OUT, f"campaign_report_{start}_{end}.csv"), "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["Campaign message ID", "Campaign", "Send date", "Send time", "Audience", "Recipients", "Delivered", "Unique opens", "Unique clicks",
                    "Unsubscribes", "Placed Order conversions", "Placed Order revenue", "Channel"])
        w.writerows(rows)
    print(f"flow rows {len(flow)}, campaign days {len(camp)}, campaigns {len(rows)}")


if __name__ == "__main__":
    main(*sys.argv[1:8])
