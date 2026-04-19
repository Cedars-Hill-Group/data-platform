"""Name and identifier normalisation utilities for entity resolution.

These functions provide deterministic, rule-based normalisation that forms
Tier 2 of the entity-resolution pipeline (Tier 1 being exact matches on
stable identifiers such as email address or website domain).

All functions are pure (no I/O, no state) and can be tested in isolation.
"""

from __future__ import annotations

import re
import unicodedata
from urllib.parse import urlparse

# Legal entity suffixes to strip from company names.  Order matters – longer
# variants are listed first so that the alternation in the regex tries them
# before shorter substrings (e.g. "corporation" before "corp").
_LEGAL_SUFFIXES: tuple[str, ...] = (
    "corporation",
    "incorporated",
    "limited liability company",
    "limited partnership",
    "limited",
    "company",
    "corp",
    "inc",
    "llc",
    "llp",
    "lp",
    "ltd",
    "plc",
    "gmbh",
    "s.a.",
    "sas",
    "sa",
    "co",
)

# Matches one legal suffix at the very end of the string, optionally preceded
# by a comma and/or whitespace and optionally followed by a period.
_SUFFIX_RE = re.compile(
    r"[,\s]+(?:" + "|".join(re.escape(s) for s in _LEGAL_SUFFIXES) + r")\.?$",
    re.IGNORECASE,
)

# Non-word, non-space characters (punctuation) to collapse into spaces.
_PUNCT_RE = re.compile(r"[^\w\s]")


def _normalize_base(text: str) -> str:
    """Lowercase, strip accents, replace punctuation with spaces, collapse whitespace."""
    # Decompose unicode then drop combining (accent) characters.
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c))
    text = text.lower()
    text = _PUNCT_RE.sub(" ", text)
    return " ".join(text.split())


def normalize_company_name(name: str) -> str:
    """Return a normalized form of *name* suitable for exact-match lookups.

    Steps applied:

    1. Strip leading/trailing whitespace.
    2. Iteratively remove trailing legal entity suffixes (``Inc.``, ``LLC``,
       ``Corp``, ``Ltd``, ``GmbH``, …).
    3. Lowercase, strip punctuation, collapse whitespace.

    Examples
    --------
    >>> normalize_company_name("Acme Corp, Inc.")
    'acme'
    >>> normalize_company_name("BETA Technologies LLC")
    'beta technologies'
    >>> normalize_company_name("Widgets & Co.")
    'widgets'
    """
    name = name.strip()
    # Iteratively strip suffixes – handles "Corp, Inc.", "Limited Corp", etc.
    prev = None
    while prev != name:
        prev = name
        name = _SUFFIX_RE.sub("", name).strip()
    return _normalize_base(name)


def normalize_person_name(name: str) -> str:
    """Return a normalized form of a person name for exact-match lookups.

    Middle initials (single-character tokens, with or without a trailing
    period) are dropped only when the name has **three or more** tokens.
    This ensures that two-token names (e.g. ``"J. Smith"`` or ``"Bo Smith"``)
    are never reduced to a single token, which would produce misleadingly
    broad matches.

    Examples
    --------
    >>> normalize_person_name("John D. Smith")
    'john smith'
    >>> normalize_person_name("  Alice   JONES  ")
    'alice jones'
    >>> normalize_person_name("J. Smith")
    'j smith'
    """
    name = _normalize_base(name.strip())
    parts = name.split()
    if len(parts) > 2:
        parts = [p for p in parts if len(p) > 1]
    return " ".join(parts)


def normalize_website_domain(url: str) -> str:
    """Extract and normalize the registrable domain from *url*.

    Strips the scheme, ``www.`` prefix, paths, query strings, ports, and
    trailing slashes so that differently formatted URLs for the same site
    compare equal.

    Examples
    --------
    >>> normalize_website_domain("https://www.acme.com/about?ref=footer")
    'acme.com'
    >>> normalize_website_domain("acme.com")
    'acme.com'
    >>> normalize_website_domain("HTTP://Acme.COM/")
    'acme.com'
    """
    url = url.strip()
    if "://" not in url:
        url = "https://" + url
    parsed = urlparse(url)
    domain = (parsed.netloc or parsed.path).lower()
    # Strip port number if present
    domain = domain.split(":")[0]
    if domain.startswith("www."):
        domain = domain[4:]
    return domain.rstrip("/")
