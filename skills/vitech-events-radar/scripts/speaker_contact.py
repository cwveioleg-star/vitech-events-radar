#!/usr/bin/env python3
"""Build a personal conference survey or copyable handoff. Never sends messages."""

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

# Only bundled code, resolved relative to this script; no third-party dependency.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from check_candidates import reasons

CONTACT_FILE = Path(__file__).resolve().parents[1] / "references/devrel-contact.md"
STATES = {"has_idea", "no_idea"}


def clean(value, limit=500):
    if not isinstance(value, str) or not value.strip() or len(value) > limit:
        raise ValueError("Expected short public text")
    if any(ord(c) < 32 for c in value):
        raise ValueError("Control characters are not allowed")
    return value.strip()


def https(value):
    value = clean(value, 2000)
    parsed = urlsplit(value)
    if parsed.scheme != "https" or not parsed.netloc or parsed.username or parsed.password:
        raise ValueError("Expected a public HTTPS link")
    return value


def load_contact():
    match = re.search(r"```json\s*(.*?)\s*```", CONTACT_FILE.read_text(), re.S)
    data = json.loads(match.group(1)) if match else None
    if not isinstance(data, dict) or set(data) != {"greeting", "loop_label", "loop_url", "telegram_url"}:
        raise ValueError("Invalid contact configuration")
    clean(data["greeting"])
    clean(data["loop_label"])
    https(data["loop_url"])
    https(data["telegram_url"])
    return data


def eligible(conferences, now):
    if not isinstance(conferences, list):
        raise ValueError("Expected the current verified conference cards")
    ids = set()
    result = []
    for card in conferences:
        if not isinstance(card, dict):
            raise ValueError("Invalid conference card")
        identity = clean(card.get("id"), 80)
        if identity in ids or identity == "skip":
            raise ValueError("Conference IDs must be unique")
        ids.add(identity)
        if card.get("kind") in {"event", "cfp"} and not reasons(card, now):
            result.append(card)
    return result


def survey(conferences, now=None):
    cards = eligible(conferences, now or datetime.now(timezone.utc))
    if not cards:
        return {"status": "no_verified_options", "questions": []}
    choices = [f"{i}. {c['id']} · {c['name']} · " +
               ("CFP открыт" if c['kind'] == 'cfp' else "возможность выступления нужно уточнить")
               for i, c in enumerate(cards[:9], 1)] + ["skip · Пока не выбираю"]
    return {"status": "ready", "questions": [
        {"question": "Какое из этих событий тебе интересно для участия как спикеру?",
         "options": choices, "type": "single_select",
         "free_text_placeholder": "Можно написать номер события; новую конференцию сначала проверим"},
        {"question": "У тебя уже есть идея темы?",
         "options": ["has_idea · Есть идея", "no_idea · Пока нет идеи"],
         "type": "single_select", "free_text_placeholder": "Можно сразу написать идею темы"},
    ]}


def compose(data, contact=None, now=None):
    if not isinstance(data, dict) or set(data) - {"conferences", "selection"}:
        raise ValueError("Expected verified cards and a selection only")
    choice = data.get("selection")
    if not isinstance(choice, dict) or set(choice) - {"conference_id", "topic_state", "topic"}:
        raise ValueError("Invalid selection")
    identity = clean(choice.get("conference_id"), 80)
    if identity == "skip":
        return {"status": "skipped", "message": None, "links": {}}
    cards = eligible(data.get("conferences"), now or datetime.now(timezone.utc))
    card = next((c for c in cards if c["id"] == identity), None)
    if card is None:
        raise ValueError("Selected event needs a fresh verified card")
    state = choice.get("topic_state")
    if state not in STATES:
        raise ValueError("Choose whether a topic idea exists")
    topic = choice.get("topic")
    if topic is not None:
        topic = clean(topic)
    if state == "no_idea" and topic:
        raise ValueError("Conflicting topic answers")
    contact = contact or load_contact()
    topic_line = (f"У меня есть идея темы: «{topic}»." if topic else "У меня уже есть идея темы.") if state == "has_idea" else "Пока нет идеи темы."
    open_cfp = card["kind"] == "cfp"
    status = card.get("cfp_status", "unknown")
    if status not in {"open", "closed", "unknown", "not_announced"}:
        raise ValueError("Invalid CFP status")
    lines = [
        clean(contact["greeting"]),
        (f"Хочу выступить на конференции «{clean(card['name'])}»." if open_cfp else
         f"Мне интересно выступить на событии «{clean(card['name'])}»."),
        topic_line,
    ]
    if open_cfp:
        lines.append("Помоги, пожалуйста, собрать фактуру и подготовиться к подаче.")
    else:
        lines.append("Опубликованный CFP уже закрыт." if status == "closed" else
                     "Открытый приём докладов пока не подтверждён.")
        lines.append("Помоги, пожалуйста, выяснить, возможно ли участие как спикера, и, если возможно, собрать фактуру.")
    lines += [
        f"Конференция: {https(card['primary_url'])}",
    ]
    if open_cfp:
        lines.append(f"CFP: {https(card['url'])}")
    message = "\n".join(lines)
    return {"status": "ready", "message": message,
            "loop_label": clean(contact["loop_label"]),
            "links": {"loop": https(contact["loop_url"]), "telegram": https(contact["telegram_url"])}}


def markdown(result):
    if result["status"] != "ready":
        return "Пока ничего не выбрано."
    longest = max((len(m.group()) for m in re.finditer(r"`+", result["message"])), default=0)
    fence = "`" * max(3, longest + 1)
    return (f"{fence}text\n{result['message']}\n{fence}\n\n"
            f"**[{result['loop_label']}]({result['links']['loop']})** · "
            f"[Telegram]({result['links']['telegram']})\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--action", choices=("survey", "message"), default="message")
    parser.add_argument("--format", choices=("json", "markdown"), default="markdown")
    parser.add_argument("--now", help="Timezone-aware ISO8601 time, for reproducible checks")
    args = parser.parse_args()
    try:
        now = datetime.fromisoformat(args.now.replace("Z", "+00:00")) if args.now else datetime.now(timezone.utc)
        if now.tzinfo is None or now.utcoffset() is None:
            raise ValueError("Timezone required")
        data = json.load(sys.stdin)
        result = survey(data["conferences"], now) if args.action == "survey" else compose(data, now=now)
        if args.action == "survey" or args.format == "json":
            print(json.dumps(result, ensure_ascii=False, indent=2))
        else:
            print(markdown(result))
    except (ValueError, TypeError, KeyError, OverflowError, RecursionError):
        print("Invalid public selection; no message was sent.", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
