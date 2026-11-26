"""Pencocokan kata kunci: tidak peka huruf besar/kecil, mengabaikan tanda baca."""

import re
from datetime import time

NON_WORD = re.compile(r"[^\w\s]", re.UNICODE)


def normalize(text: str) -> str:
    return " ".join(NON_WORD.sub(" ", (text or "").lower()).split())


def keyword_matches(text: str, keyword: str, match_type: str) -> bool:
    message, word = normalize(text), normalize(keyword)
    if not message or not word:
        return False
    if match_type == "exact":
        return message == word
    if match_type == "starts_with":
        return message == word or message.startswith(word + " ")
    # contains: cocok sebagai kata/frasa utuh, bukan potongan kata ("harga" ≠ "hargai").
    return f" {word} " in f" {message} "


def within_hours(now: time, start: time | None, end: time | None) -> bool:
    if start is None or end is None or start == end:
        return True
    if start < end:
        return start <= now < end
    return now >= start or now < end  # melewati tengah malam, mis. 20.00–06.00


def find_rule(rules, text: str, now: time):
    """Aturan aktif pertama (urut prioritas) yang cocok dengan pesan."""
    for rule in rules:
        if not rule.is_active or not within_hours(now, rule.active_from, rule.active_until):
            continue
        if any(keyword_matches(text, kw, rule.match_type) for kw in rule.keyword_list):
            return rule
    return None
