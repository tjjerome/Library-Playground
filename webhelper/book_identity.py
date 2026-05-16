#!/usr/bin/env python3
"""Canonical book-identity layer.

ONE place that answers "are these the same book?".  Every resolution
call site — list resolution, pool/read exclusion, reconcile audit,
series-fit, cataloguer add — routes through `same_book` /
`title_keys` / `authors_match` here so tolerance can never drift per
call site again.  Before this module the same author/title-variant
bug was patched independently at six sites; new mismatch classes are
now a single golden-table row in tests/identity_contract.py, not a
new band-aid.

Tolerance is deliberately conservative: punctuation/case/article
folding, author name-order swap, co-author omission, multi-author
surname overlap, and a narrow British/American spelling fold.  There
is intentionally **no** general fuzzy-ratio match — over-matching
resolves the wrong book, and the contract test's negative cases
(same title, different author) are the guardrail.
"""

from __future__ import annotations

import re

_QUOTE_NORMALIZE = str.maketrans({
    "‘": "'", "’": "'", "‚": "'", "‛": "'",
    "“": '"', "”": '"', "„": '"', "‟": '"',
    "–": "-", "—": "-", "−": "-",
    "​": "", "‌": "", "‍": "", "﻿": "",
})
_LEAD_PUNCT = re.compile(r"^[^\w]+", flags=re.UNICODE)
_LEAD_ARTICLE = re.compile(r"^(the|a|an)\s+", flags=re.IGNORECASE)
_TRAILING_PAREN = re.compile(r"\s*\([^)]*\)\s*$")

# Two split regexes with genuinely different jobs (not duplicates):
#   _NAME_ORDER_GUARD — used ONLY inside _swap_lastfirst to refuse the
#     swap when a comma is part of a multi-author list rather than a
#     `Last, First` flip.  Broad on purpose (;, /, with).
#   AUTHOR_SPLIT — the canonical co-author splitter for identity
#     comparison and the log-side author-parts helper.
_NAME_ORDER_GUARD = re.compile(r"\s*(?:&|;|/|\band\b|\bwith\b)\s*",
                               flags=re.IGNORECASE)
AUTHOR_SPLIT = re.compile(r"\s*(?:&|;|/|,|\band\b|\bwith\b)\s*",
                          flags=re.IGNORECASE)


def _swap_lastfirst(s: str) -> str:
    """`Last, First` → `First Last`.  Conservative: a single comma,
    no multi-author delimiter, no role/parenthetical markup, and each
    side ≤2 word tokens — so genuine author lists and pen names with
    stylistic commas are left alone."""
    if s.count(",") != 1 or _NAME_ORDER_GUARD.search(s) or "(" in s:
        return s
    last, first = (p.strip() for p in s.split(","))
    if not (last and first):
        return s
    if len(last.split()) > 2 or len(first.split()) > 2:
        return s
    return f"{first} {last}"


def _collapse_initials(tokens: list[str]) -> list[str]:
    """Merge runs of single-character tokens so `k j parker`,
    `k.j. parker`, and `kj parker` all converge."""
    out: list[str] = []
    buf: list[str] = []
    for t in tokens:
        if len(t) == 1 and t.isalpha():
            buf.append(t)
            continue
        if buf:
            out.append("".join(buf))
            buf = []
        out.append(t)
    if buf:
        out.append("".join(buf))
    return out


def norm(s: str | None) -> str:
    if not s:
        return ""
    s = s.translate(_QUOTE_NORMALIZE)
    s = _swap_lastfirst(s)
    s = s.replace("&", " and ")
    s = _TRAILING_PAREN.sub("", s)
    s = _LEAD_PUNCT.sub("", s)
    s = s.lower()
    s = _LEAD_ARTICLE.sub("", s)
    # Drop subtitle drift: `Title: A Novel` ≡ `Title`.
    s = s.split(":", 1)[0]
    s = re.sub(r"\.", " ", s)
    return " ".join(_collapse_initials(s.split()))


def title_short(title: str | None) -> str:
    """Pre-colon prefix of the title, normalised. Empty if title has
    no colon."""
    if not title or ":" not in title:
        return ""
    return norm(title.split(":", 1)[0])


# British → American spelling fold, applied per word as an *additional*
# title-variant key, never as a general fuzzy match.  Length guards
# keep common non-variant words out (four/hour/tour, noise/raise,
# rise/wise).  -re→-er is intentionally omitted: it mangles
# nature/future/feature far more often than it folds centre/theatre.
_FOLD_WORD_RULES = [
    ("isations", "izations", 9),
    ("isation", "ization", 8),
    ("ising", "izing", 7),
    ("ised", "ized", 6),
    ("ise", "ize", 6),
    ("ours", "ors", 6),
    ("our", "or", 5),
]


def _fold_word(w: str) -> str:
    for suf, repl, minlen in _FOLD_WORD_RULES:
        if len(w) >= minlen and w.endswith(suf):
            return w[: -len(suf)] + repl
    return w


def title_fold(t: str) -> str:
    """Spelling-folded form of a norm()'d title.  Compare folded↔folded
    and only after an exact title key already failed."""
    if not t:
        return ""
    return " ".join(_fold_word(w) for w in t.split())


def title_keys(title: str | None) -> set[str]:
    """Every key a title can be matched on: full norm, pre-colon
    short, and the spelling-folded forms of each.  Bucket on these,
    then validate the author with `authors_match`."""
    keys: set[str] = set()
    tn = norm(title)
    if tn:
        keys.add(tn)
    ts = title_short(title)
    if ts:
        keys.add(ts)
    for k in list(keys):
        fk = title_fold(k)
        if fk:
            keys.add(fk)
    return keys


def author_parts(raw: str | None) -> set[str]:
    """Normalized author tokens for a (possibly multi-author) field:
    the whole normed field plus each split co-author, so a
    single-author query matches a co-authored row."""
    if not raw:
        return set()
    parts = {norm(raw)}
    for piece in AUTHOR_SPLIT.split(raw):
        pn = norm(piece)
        if pn:
            parts.add(pn)
    parts.discard("")
    return parts


def authors_match(a: str, b: str) -> bool:
    """True when two norm()'d author strings name the same author(s)
    under name-order swap, co-author omission, or — for genuine
    multi-author lists only — surname overlap.

      - exact equality; or
      - `_swap_lastfirst` on either side yields equality (name order;
        also covers bare two-token flips via the token-set rule since
        norm() only swaps on an explicit comma); or
      - one author's token set is a subset of the other
        (`{ben, r, rich}` ⊆ `{ben, r, rich, leo, janos}`, and the
        flip `{cixin, liu}` == `{liu, cixin}`); or
      - both sides are multi-author lists sharing a surname token
        (`Arkady & Boris Strugatsky` ≡ `Arkady Strugatsky & Boris
        Strugatsky`).  Restricted to multi/multi so two distinct
        single authors sharing a surname stay distinct.
    """
    if not a or not b:
        return a == b
    if a == b:
        return True
    if _swap_lastfirst(a) == b or a == _swap_lastfirst(b):
        return True
    ta, tb = set(a.split()), set(b.split())
    if ta and tb and (ta <= tb or tb <= ta):
        return True
    pa = [p for p in AUTHOR_SPLIT.split(a) if p.split()]
    pb = [p for p in AUTHOR_SPLIT.split(b) if p.split()]
    if len(pa) > 1 and len(pb) > 1:
        sa = {p.split()[-1] for p in pa}
        sb = {p.split()[-1] for p in pb}
        if sa & sb:
            return True
    return False


def same_book(title_a: str | None, author_a: str | None,
               title_b: str | None, author_b: str | None) -> bool:
    """THE identity predicate: titles share a key (exact, short, or
    spelling-folded) AND authors match tolerantly."""
    if not (title_keys(title_a) & title_keys(title_b)):
        return False
    return authors_match(norm(author_a), norm(author_b))


# Back-compat aliases — older call sites referenced the underscored
# names; keep them pointing at the canonical functions so nothing
# silently forks a second implementation.
_author_matches = authors_match
_title_fold = title_fold
