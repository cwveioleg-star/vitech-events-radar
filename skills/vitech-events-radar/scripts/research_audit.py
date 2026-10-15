#!/usr/bin/env python3
"""Count a supplied research ledger; no web access, writes or proof of actual reading."""

import argparse
import json
from datetime import datetime, timedelta
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

KINDS = {"calendar", "event", "registration", "cfp", "community"}
REQUIRED_BRANDS = {"avitotech", "alfa digital"}
NOISE = {"page", "p", "offset", "limit", "sort", "order", "from", "ref", "fbclid", "gclid", "yclid"}


def canonical(value):
    if not isinstance(value, str):
        raise ValueError("Expected URL")
    u = urlsplit(value)
    if u.scheme != "https" or not u.hostname or u.username or u.password:
        raise ValueError("Expected public HTTPS URL")
    query = [(k, v) for k, v in parse_qsl(u.query, keep_blank_values=True)
             if not k.lower().startswith("utm_") and k.lower() not in NOISE]
    return urlunsplit(("https", u.netloc.lower(), u.path.rstrip("/") or "/", urlencode(sorted(query)), ""))


def audit(records, now, minimum=100):
    if not isinstance(records, list) or now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("Expected ledger and timezone-aware current time")
    if type(minimum) is not int or minimum < 100:
        raise ValueError("Minimum coverage is 100")
    seen_urls, seen_ids, domains, brands = set(), set(), set(), set()
    rejected, counted = [], []
    for index, entry in enumerate(records):
        try:
            if not isinstance(entry, dict):
                raise ValueError("not an object")
            url = canonical(entry.get("canonical_url") or entry["url"])
            canonical(entry["url"])
            checked = datetime.fromisoformat(entry["checked_at"].replace("Z", "+00:00"))
            if checked.tzinfo is None or checked.utcoffset() is None or checked > now or now - checked > timedelta(hours=24):
                raise ValueError("stale/future check")
            if entry.get("status") != "read" or entry.get("relevant") is not True or entry.get("kind") not in KINDS:
                raise ValueError("not a relevant completed read")
            for field in ("tool_ref", "evidence"):
                if not isinstance(entry.get(field), str) or not entry[field].strip():
                    raise ValueError("missing read trace/evidence")
            identity = entry.get("source_id") or url
            if not isinstance(identity, str):
                raise ValueError("invalid document ID")
            duplicate = url in seen_urls or identity in seen_ids
            # Remember both sides even on duplicate, so alias chains cannot pad coverage.
            seen_urls.add(url)
            seen_ids.add(identity)
            if duplicate:
                raise ValueError("duplicate document")
            domains.add(urlsplit(url).hostname)
            brand = entry.get("brand", "")
            if not isinstance(brand, str):
                raise ValueError("invalid brand")
            brand = brand.strip().casefold()
            if brand in REQUIRED_BRANDS:
                brands.add(brand)
            counted.append(index)
        except (ValueError, TypeError, KeyError, AttributeError):
            rejected.append(index)
    missing = sorted(REQUIRED_BRANDS - brands)
    return {"complete": len(counted) >= minimum and not missing,
            "minimum": minimum, "read_unique": len(counted), "domains": len(domains),
            "missing_brands": missing, "counted_indices": counted, "excluded_indices": rejected,
            "note": "Ledger validation only; the agent must actually read the sources."}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("file")
    p.add_argument("--now", required=True)
    args = p.parse_args()
    try:
        with open(args.file, encoding="utf-8") as source:
            records = json.load(source)
        now = datetime.fromisoformat(args.now.replace("Z", "+00:00"))
        print(json.dumps(audit(records, now), ensure_ascii=False, indent=2))
    except (ValueError, TypeError, OSError, OverflowError, RecursionError):
        p.exit(2, "Invalid research ledger.\n")


if __name__ == "__main__":
    main()
