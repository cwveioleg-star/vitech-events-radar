#!/usr/bin/env python3
"""Count a supplied research ledger; no web access, writes or proof of actual reading."""

import argparse
import json
from calendar import monthrange
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

KINDS = {"aggregator", "calendar", "event", "registration", "cfp", "community"}
REGISTRY = Path(__file__).resolve().parents[1] / "references/tech-brands.json"
ROUTES = {"calendar", "cfp"}
OPTIONAL_ROUTES = {"timepad", "telegram"}
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
    try:
        checked = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return checked.tzinfo is not None and checked.utcoffset() is not None and timedelta(0) <= now - checked <= timedelta(hours=24)
    except (ValueError, TypeError, AttributeError):
        return False


def traced(value):
    return isinstance(value, dict) and all(isinstance(value.get(k), str) and value[k].strip()
                                           for k in ("tool_ref", "evidence"))


def brand_ids(brands):
    if not isinstance(brands, list) or not brands:
        raise ValueError("Expected a nonempty brand registry")
    if any(not isinstance(b, dict) or not isinstance(b.get("id"), str) or not b["id"].strip()
           or not isinstance(b.get("name"), str) or not b["name"].strip() for b in brands):
        raise ValueError("Invalid brand registry")
    ids = {b["id"] for b in brands}
    if len(ids) != len(brands) or len({b["name"].strip().casefold() for b in brands}) != len(brands):
        raise ValueError("Duplicate brand identities")
    return ids


def working_registry(bundle, now):
    snapshot = json.loads(REGISTRY.read_text(encoding="utf-8"))
    supplied = bundle.get("registry")
    if supplied is None:
        return brand_ids(snapshot["brands"]), {"registry_source": snapshot["source_url"],
                "registry_fresh": False, "registry_snapshot_on": snapshot["refreshed_on"]}
    if not isinstance(supplied, dict) or not traced(supplied) or not fresh(supplied.get("checked_at", ""), now):
        raise ValueError("A current registry needs a fresh read trace")
    source = canonical(supplied.get("source_url"))
    ids = brand_ids(supplied.get("brands"))
    if len(ids) * 2 < len(snapshot['brands']):
        raise ValueError('Registry shrank by more than half; use selected_brand_ids for a subset')
    return ids, {"registry_source": source, "registry_fresh": True, "registry_snapshot_on": None}


def coverage(bundle, records, counted, now):
    """Check the declared plan, never infer an exhaustive market search."""
    ids, registry_info = working_registry(bundle, now)
    extras = bundle.get("extra_brands", [])
    if extras:
        new_ids = brand_ids(extras)
        if ids.intersection(new_ids):
            raise ValueError("Additional brand IDs must be new")
        ids.update(new_ids)
    elif not isinstance(extras, list):
        raise ValueError("Expected additional brands")
    mode = bundle.get("mode", "targeted")
    if mode not in {"targeted", "full"}:
        raise ValueError("Unknown research mode")
    selected = bundle.get("selected_brand_ids", [])
    if not isinstance(selected, list) or any(not isinstance(i, str) or i not in ids for i in selected):
        raise ValueError("Selected brands must belong to the working registry")
    required = ids if mode == "full" else set(selected)
    scope = bundle.get("cfp_search", {})
    if not isinstance(scope, dict):
        raise ValueError("Expected CFP search scope")
    horizon = False
    starts = ends = None
    try:
        starts = datetime.fromisoformat(scope["from"]).date()
        ends = datetime.fromisoformat(scope["through"]).date()
        months = scope.get("months", 6)
        horizon = type(months) is int and 1 <= months <= 24 and starts == now.date() and ends >= add_months(starts, months)
    except (KeyError, TypeError, ValueError, AttributeError):
        pass
    checks = bundle.get("brand_checks", [])
    if not isinstance(checks, list):
        raise ValueError("Expected brand checks")
    checked_ids, cfp_ids, seen, optional_gaps = set(), set(), set(), []
    for check in checks:
        try:
            identity = check["brand_id"]
            if identity not in required or identity in seen:
                continue
            seen.add(identity)
            if not fresh(check["checked_at"], now):
                continue
            routes = check["routes"]
            if not isinstance(routes, list) or any(not isinstance(r, dict) for r in routes):
                continue
            kinds = [r.get("kind") for r in routes]
            if len(kinds) != len(set(kinds)) or not ROUTES.issubset(kinds):
                continue
            for route in routes:
                if route["kind"] in OPTIONAL_ROUTES:
                    if route.get("status") in {"blocked", "snippet_only", "error"}:
                        optional_gaps.append(identity + ":" + route["kind"])
                    continue
                if route["kind"] not in ROUTES or not traced(route) or route.get("status") not in {"read", "not_found"}:
                    raise ValueError("Unresolved core route")
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
    discovery = bundle.get("discovery_searches", [])
    if not isinstance(discovery, list):
        raise ValueError("Expected discovery searches")
    channels, traces = set(), set()
    for search in discovery:
        try:
            if traced(search) and fresh(search.get("checked_at", ""), now) and search.get("kind") in {"aggregator", "web", "community", "calendar"}:
                channels.add(search["kind"])
                traces.add(search["tool_ref"])
        except (TypeError, ValueError, AttributeError):
            continue
    discovery_ok = len(channels) >= 2 and len(traces) >= 2
    community = scope.get("community_searches", [])
    community_ok = isinstance(community, list) and bool(community) and all(traced(c) for c in community)
    complete = horizon and cfp_ids == required and community_ok and scope.get("unresolved") == []
    return {"mode": mode, **registry_info, "brands_total": len(ids), "brands_selected": len(required),
            "brands_checked": len(checked_ids), "missing_brands": sorted(required - checked_ids),
            "brand_coverage_complete": checked_ids == required, "discovery_complete": discovery_ok,
            "optional_route_gaps": sorted(set(optional_gaps)),
            "cfp_from": starts.isoformat() if starts else None,
            "cfp_through": ends.isoformat() if ends else None,
            "cfp_horizon_complete": bool(complete), "cfp_missing_brands": sorted(required - cfp_ids),
            "scoped_no_cfp_claim_allowed": bool(complete and discovery_ok and type(scope.get("verified_suitable_count")) is int and scope["verified_suitable_count"] == 0),
            "no_cfp_claim_allowed": False}


def audit(data, now, minimum=None):
    bundle = data if isinstance(data, dict) else {}
    records = bundle.get("reads") if isinstance(data, dict) else data
    if not isinstance(records, list) or now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("Expected ledger and timezone-aware current time")
    if minimum is None:
        minimum = bundle.get("minimum_reads")
    if minimum is not None and (type(minimum) is not int or minimum < 1):
        raise ValueError("Explicit read target must be a positive integer")
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
    reads_complete = bool(counted) and (minimum is None or len(counted) >= minimum)
    breadth["scoped_no_cfp_claim_allowed"] = reads_complete and breadth["scoped_no_cfp_claim_allowed"]
    return {"complete": reads_complete and breadth["discovery_complete"] and breadth["brand_coverage_complete"] and breadth["cfp_horizon_complete"],
            "reads_complete": reads_complete, **breadth,
            "minimum": minimum, "read_unique": len(counted), "domains": len(domains),
            "counted_indices": counted, "excluded_indices": rejected,
            "note": "Declared search plan only, not exhaustive market coverage or proof of web reading."}


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
