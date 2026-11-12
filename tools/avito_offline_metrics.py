#!/usr/bin/env python3
"""Offline Avito daily metrics validation and funnel report. No network, no writes."""
from __future__ import annotations
import argparse
import csv
import json
from collections import defaultdict
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path

COLUMNS = ("date","ad_id","city","category","impressions","views","contacts","favorites",
           "ad_spend_rub","qualified_leads","proposals_sent","deals","revenue_rub","notes")
COUNTS = ("impressions","views","contacts","favorites","qualified_leads","proposals_sent","deals")
MONEY = ("ad_spend_rub","revenue_rub")
NUMERIC = COUNTS + MONEY
KNOWN = {"8347570435":"Москва","8477159401":"Санкт-Петербург",
         "8531755111":"Сургут","8414224003":"Чита"}


def parse(rows):
    seen = set()
    clean = []
    errors = []
    for line, raw in enumerate(rows, start=2):
        if None in raw or set(raw) != set(COLUMNS):
            errors.append(f"line {line}: invalid columns")
            continue
        try:
            d = date.fromisoformat(raw["date"])
            if d.isoformat() != raw["date"]:
                raise ValueError("date not ISO YYYY-MM-DD")
            ident = raw["ad_id"].strip()
            if ident not in KNOWN or raw["city"].strip() != KNOWN[ident]:
                raise ValueError("unknown ad_id or city mismatch")
            key = (d.isoformat(), ident)
            if key in seen:
                raise ValueError("duplicate listing/day")
            seen.add(key)
            values = {}
            for name in COUNTS:
                s = raw[name].strip()
                if s and not s.isdecimal():
                    raise ValueError(f"{name} must be a nonnegative integer")
                values[name] = int(s) if s else None
            for name in MONEY:
                s = raw[name].strip()
                if s:
                    try:
                        val = Decimal(s)
                    except InvalidOperation:
                        raise ValueError(f"{name} is not a decimal")
                    if not val.is_finite() or val < 0:
                        raise ValueError(f"{name} must be finite and nonnegative")
                    values[name] = val
                else:
                    values[name] = None
            clean.append({"date":d.isoformat(),"ad_id":ident,"city":KNOWN[ident],
                          "category":raw["category"].strip(),**values})
        except ValueError as e:
            errors.append(f"line {line}: {e}")
    return clean, errors


def ratio(num, den):
    return float(num / den) if num is not None and den is not None and den > 0 else None


def summarize(records):
    grouped = defaultdict(list)
    for r in records:
        grouped[r["ad_id"]].append(r)
    result = []
    for ident in sorted(grouped):
        rows = grouped[ident]
        totals = {}
        coverage = {}
        for field in NUMERIC:
            values = [r[field] for r in rows if r[field] is not None]
            coverage[field] = len(values)
            totals[field] = sum(values) if len(values) == len(rows) else None
        result.append({
            "ad_id":ident,"city":KNOWN[ident],"days":len(rows),
            "coverage_days":coverage,
            "totals":{k:str(v) if isinstance(v,Decimal) else v for k,v in totals.items()},
            "ctr":ratio(totals["views"],totals["impressions"]),
            "view_to_contact":ratio(totals["contacts"],totals["views"]),
            "qualification_rate":ratio(totals["qualified_leads"],totals["contacts"]),
            "lead_to_deal":ratio(totals["deals"],totals["qualified_leads"]),
            "cost_per_contact_rub":ratio(totals["ad_spend_rub"],totals["contacts"]),
            "roas":ratio(totals["revenue_rub"],totals["ad_spend_rub"]),
        })
    return {"schema":"avito.offline-metrics.v1","listing_summaries":result,
            "input_rows":len(records),"no_data":len(records)==0}


def main():
    p = argparse.ArgumentParser()
    p.add_argument("csv_path",type=Path)
    args = p.parse_args()
    with args.csv_path.open(encoding="utf-8-sig",newline="") as f:
        reader = csv.DictReader(f)
        if reader.fieldnames != list(COLUMNS):
            p.error("CSV header does not match template")
        rows,errors = parse(reader)
    if errors:
        print(json.dumps({"errors":errors},ensure_ascii=False,indent=2))
        return 1
    print(json.dumps(summarize(rows),ensure_ascii=False,indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
