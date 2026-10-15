#!/usr/bin/env python3
"""Count a supplied research ledger; no web access, writes or proof of actual reading."""

import argparse
import json
from calendar import monthrange
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

KINDS = {"calendar", "event", "registration", "cfp", "community"}
REGISTRY = Path(__file__).resolve().parents[1] / "references/tech-brands.json"
ROUTES = {"calendar", "timepad", "telegram", "cfp"}
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


def add_months(day, months):
    total = day.year * 12 + day.month - 1 + months
    year, month = divmod(total, 12)
    return day.replace(year=year, month=month + 1,
                       day=min(day.day, monthrange(year, month + 1)[1]))


def fresh(value, now):
    checked = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return checked.tzinfo is not None and checked.utcoffset() is not None and timedelta(0) <= now - checked <= timedelta(hours=24)


def traced(value):
    return isinstance(value, dict) and all(isinstance(value.get(k), str) and value[k].strip()
                                           for k in ("tool_ref", "evidence"))


def coverage(bundle, records, counted, now):
    """Validate breadth separately from page count. This cannot prove web facts."""
    registry = json.loads(REGISTRY.read_text(encoding="utf-8"))["brands"]
    ids = {b["id"] for b in registry}
    extras = bundle.get("extra_brands", [])
    if not isinstance(extras, list) or any(not isinstance(b, dict) or not b.get("id") or not b.get("name") for b in extras):
        raise ValueError("Invalid additional brands")
    extra_ids = [b["id"] for b in extras]
    if any(not isinstance(identity, str) for identity in extra_ids) or len(set(extra_ids)) != len(extra_ids) or ids.intersection(extra_ids):
        raise ValueError("Additional brand IDs must be new and unique")
    ids.update(extra_ids)
    scope = bundle.get("cfp_search", {})
    if not isinstance(scope, dict):
        raise ValueError("Expected CFP search scope")
    horizon = False
    starts = ends = None
    try:
        starts = datetime.fromisoformat(scope["from"]).date()
        ends = datetime.fromisoformat(scope["through"]).date()
        months = scope.get("months", 6)
        horizon = type(months) is int and months >= 4 and starts == now.date() and ends >= add_months(starts, months)
    except (KeyError, TypeError, ValueError, AttributeError):
        pass
    checks = bundle.get("brand_checks", [])
    if not isinstance(checks, list):
        raise ValueError("Expected brand checks")
    checked_ids, cfp_ids, seen = set(), set(), set()
    for check in checks:
        try:
            identity = check["brand_id"]
            if identity not in ids or identity in seen:
                raise ValueError("Unknown or duplicate brand")
            seen.add(identity)
            if not fresh(check["checked_at"], now):
                continue
            routes = check["routes"]
            if not isinstance(routes, list) or len(routes) != len(ROUTES) or {r["kind"] for r in routes} != ROUTES:
                continue
            for route in routes:
                if not traced(route) or route.get("status") not in {"read", "not_found"}:
                    raise ValueError("Unresolved route")
                indices = route.get("read_indices", [])
                if route["status"] == "read":
                    if not isinstance(indices, list) or not indices:
                        raise ValueError("Missing supporting reads")
                    if any(type(i) is not int or i not in counted or identity not in records[i].get("brand_ids", []) for i in indices):
                        raise ValueError("Read does not support this brand")
                elif indices:
                    raise ValueError("Not-found searches are not document reads")
            checked_ids.add(identity)
            if horizon and check.get("cfp_from") == scope["from"] and check.get("cfp_through") == scope["through"]:
                cfp_ids.add(identity)
        except (KeyError, TypeError, ValueError, AttributeError):
            continue
    community = scope.get("community_searches", [])
    community_ok = isinstance(community, list) and bool(community) and all(traced(c) for c in community)
    complete = horizon and cfp_ids == ids and community_ok and scope.get("unresolved") == []
    return {"brands_total": len(ids), "brands_checked": len(checked_ids),
            "missing_brands": sorted(ids - checked_ids),
            "brand_coverage_complete": checked_ids == ids,
            "cfp_from": starts.isoformat() if starts else None,
            "cfp_through": ends.isoformat() if ends else None,
            "cfp_horizon_complete": bool(complete),
            "cfp_missing_brands": sorted(ids - cfp_ids),
            "no_cfp_claim_allowed": bool(complete and type(scope.get("verified_suitable_count")) is int and scope["verified_suitable_count"] == 0)}


def audit(data, now, minimum=100):
    bundle = data if isinstance(data, dict) else {}
    records = bundle.get("reads") if isinstance(data, dict) else data
    if not isinstance(records, list) or now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("Expected ledger and timezone-aware current time")
    if type(minimum) is not int or minimum < 100:
        raise ValueError("Minimum coverage is 100")
    seen_urls, seen_ids, domains = set(), set(), set()
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
            if "brand_ids" in entry and (not isinstance(entry["brand_ids"], list) or
                                         any(not isinstance(b, str) for b in entry["brand_ids"])):
                raise ValueError("invalid brand IDs")
            counted.append(index)
        except (ValueError, TypeError, KeyError, AttributeError):
            rejected.append(index)
    breadth = coverage(bundle, records, set(counted), now)
    reads_complete = len(counted) >= minimum
    breadth["no_cfp_claim_allowed"] = reads_complete and breadth["no_cfp_claim_allowed"]
    return {"complete": reads_complete and breadth["brand_coverage_complete"] and breadth["cfp_horizon_complete"],
            "reads_complete": reads_complete, **breadth,
            "minimum": minimum, "read_unique": len(counted), "domains": len(domains),
            "counted_indices": counted, "excluded_indices": rejected,
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
