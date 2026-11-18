"""Small helpers that clean up messy form data before it is used.

* ``suggest_email`` spots typos in the domain (gmial.com, gmail.con, ...) and
  returns the corrected address, or None if the address looks fine.
* ``tidy_name`` fixes capitalisation and stray spaces/punctuation so a name
  looks right on a certificate or in a greeting.
"""

import difflib
import re
import unicodedata

# Domains that are real. An address on one of these is never "corrected".
KNOWN_DOMAINS = [
    "gmail.com", "googlemail.com", "yahoo.com", "yahoo.in", "yahoo.co.in", "yahoo.co.uk", "ymail.com",
    "hotmail.com", "hotmail.co.uk", "outlook.com", "outlook.in", "live.com", "live.in", "msn.com",
    "icloud.com", "me.com", "rediffmail.com", "protonmail.com", "proton.me", "pm.me", "aol.com",
    "mail.com", "email.com", "zoho.com", "yandex.com", "gmx.com", "hey.com", "tutanota.com",
]
# Domains we are willing to suggest (the popular ones only).
_SUGGEST_TARGETS = [
    "gmail.com", "yahoo.com", "yahoo.in", "hotmail.com", "outlook.com", "icloud.com", "rediffmail.com", "live.com",
]

# Typos seen in real form data that fuzzy matching alone might miss.
_FIXES = {
    "gmial.com": "gmail.com", "gamil.com": "gmail.com", "gmai.com": "gmail.com", "gmaill.com": "gmail.com",
    "gnail.com": "gmail.com", "gmal.com": "gmail.com", "gmeil.com": "gmail.com", "gemail.com": "gmail.com",
    "gmail.con": "gmail.com", "gmail.co": "gmail.com", "gmail.cm": "gmail.com", "gmail.om": "gmail.com",
    "gmail.comm": "gmail.com", "gmail.vom": "gmail.com", "gmail.cmo": "gmail.com", "gmail.c0m": "gmail.com",
    "gmail.in": "gmail.com", "gmail.org": "gmail.com", "gmail.net": "gmail.com", "gmail.coom": "gmail.com",
    "yaho.com": "yahoo.com", "yahooo.com": "yahoo.com", "yhoo.com": "yahoo.com", "yahoo.co": "yahoo.com",
    "yahoo.con": "yahoo.com", "yahoo.cm": "yahoo.com", "yahoo.om": "yahoo.com",
    "hotmial.com": "hotmail.com", "hotmal.com": "hotmail.com", "hotmail.con": "hotmail.com", "hotmai.com": "hotmail.com",
    "outlok.com": "outlook.com", "outlook.con": "outlook.com", "outloook.com": "outlook.com", "outlook.co": "outlook.com",
    "iclod.com": "icloud.com", "icloud.con": "icloud.com", "iclould.com": "icloud.com",
    "rediffmial.com": "rediffmail.com", "rediffmail.con": "rediffmail.com",
}


def suggest_email(email):
    """Return a corrected address if the domain looks like a typo, else None."""
    email = (email or "").strip()
    if email.count("@") != 1:
        return None
    local, domain = email.split("@")
    domain_l = domain.lower().rstrip(".,;")
    if not local or not domain_l or domain_l in KNOWN_DOMAINS:
        return None
    fixed = _FIXES.get(domain_l)
    if fixed is None:
        # Only fuzzy-match short single-site domains, never institution domains
        # such as sipnaengg.ac.in.
        if domain_l.count(".") > 1 and not domain_l.endswith((".co.in", ".co.uk")):
            return None
        match = difflib.get_close_matches(domain_l, _SUGGEST_TARGETS, n=1, cutoff=0.86)
        fixed = match[0] if match else None
    if not fixed or fixed == domain_l:
        return None
    return f"{local}@{fixed}"


_TITLES = {"dr.", "mr.", "mrs.", "ms.", "prof."}
_PARTICLES = {"de", "da", "van", "von", "bin", "al", "bin", "del", "di", "la", "le", "of"}


def _fix_word(word, first):
    if len(word) == 1:
        return word.upper() if word.isalpha() else word
    letters = [c for c in word if c.isalpha()]
    if not letters:
        return word
    if word.isupper() or word.islower():
        if not first and word.lower() in _PARTICLES:
            return word.lower()
        # capitalise each piece around - and '
        return re.sub(r"(^|[-'’])([a-z])", lambda m: m.group(1) + m.group(2).upper(), word.lower())
    # mixed case: only repair a lowercase first letter ("ashay"), keep McDonald etc.
    if word[0].islower() and word[1:].islower():
        return word.capitalize()
    return word


def tidy_name(name):
    """Capitalise and clean a person's name. Returns '' for empty input."""
    name = unicodedata.normalize("NFKC", name or "")
    name = re.sub(r"\s+", " ", name).strip(" \t\r\n\"'“”‘’,;:|-_")
    if not name:
        return ""
    words = []
    for i, w in enumerate(name.split(" ")):
        # drop trailing full stops after real words, keep initials like "A."
        if w.lower() in _TITLES:
            words.append(w.capitalize() if w.endswith(".") else w.capitalize() + ".")
            continue
        if len(w) > 2 and w.endswith("."):
            w = w.rstrip(".")
        if len(w) == 2 and w[1] == "." and w[0].isalpha():
            words.append(w[0].upper() + ".")
            continue
        words.append(_fix_word(w, i == 0))
    return " ".join(words)[:200]
