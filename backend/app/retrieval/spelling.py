"""
Spelling normalisation for transliterated Urdu/Arabic legal terms.

Why
---
Users type these words the way they say them: "nikkah", "haq mahar",
"khulla", "talaaq", "heba". Judgments of the Supreme Court spell them one way
("Nikah", "Haq Mehr", "Khula", "Talaq", "Hiba"), and the keyword index matches
exact (stemmed) words. One extra letter was enough to lose the case: "nikah
case issue" found the dower judgment (C.A. 23-P/2017) while "nikkah case
issue" ranked a generic "case issue" match first and the search refused.

What
----
normalise() rewrites known variant spellings to the judgments' spelling. For
terms judgments mostly write in English, the English phrase is added next to
the Urdu one ("haq mahar" -> "haq mehr dower"), so both the keyword index and
the vectors see the word the judgment uses. Glosses avoid the category
trigger words in app.retrieval.categories ("marriage", "family", ...), so a
spelling fix never turns a search into a category browse by itself.

Curated on purpose: a fuzzy "closest word in the index" corrector would also
"correct" names and OCR noise, and at 3,000 judgments the index holds plenty
of both. Add a variant here when a real query shows one.
"""

from __future__ import annotations

import re

# (pattern over one word or phrase, replacement). Order matters: longer
# phrases first ("nikah nama" before "nikah", "haq shufa" before "shufa").
_RULES: list[tuple[str, str]] = [
    # marriage
    (r"n[ie]+k+a+h+[\s-]*nama+h?", "nikah nama"),
    (r"n[ie]+k+a+h+", "nikah"),
    (r"haq+[\s-]*(?:e[\s-]*)?m[ae]h[ae]?r", "haq mehr dower"),
    (r"kh[uo]l+a+h?", "khula"),
    (r"t[ae]l+a+[qk]", "talaq divorce"),
    (r"id+a+t|id+ah", "iddat"),
    (r"jah[ae]i?[zs]|jahiz", "jahez dowry"),
    (r"naf[a]?q+a+h?", "nafqa maintenance allowance"),
    (r"hi[zd]h?a+nat", "hizanat custody of minor"),
    # property
    (r"h[ie]+b+a+h?", "hiba gift"),
    (r"haq+[\s-]*(?:e[\s-]*)?sh[uo]+f+a+h?", "haq shufa pre-emption"),
    (r"sh[uo]+f+a+h?", "shufa pre-emption"),
    (r"pre[\s-]?emption", "pre-emption"),
    (r"[vw]ir+a*s[ae]t", "wirasat inheritance"),
    (r"int[ie]q+a+l", "intiqal mutation"),
    (r"pat[wv]a+ri", "patwari"),
    (r"wakf", "waqf"),
    # criminal
    (r"q[aie]s[ae]+s", "qisas"),
    (r"diy+a+t", "diyat"),
    (r"jir[gq]a+h?", "jirga"),
]

# One alternation, one pass: each span is rewritten once, by the first rule
# that matches there (a rule's output is never re-read by a later rule).
_PATTERN = re.compile(
    "|".join(rf"(?P<r{i}>(?<![A-Za-z])(?:{p})(?![A-Za-z]))" for i, (p, _) in enumerate(_RULES)),
    re.I,
)


def normalise(text: str) -> str:
    """The query with variant spellings replaced; unchanged if none occur."""
    if not text:
        return text or ""
    return _PATTERN.sub(lambda m: _RULES[int(m.lastgroup[1:])][1], text)


if __name__ == "__main__":
    cases = {
        "nikkah case issue": "nikah case issue",
        "Nikaah": "nikah",
        "nikahnama forged": "nikah nama forged",
        "nikkah-nama": "nikah nama",
        "haq mahar not paid": "haq mehr dower not paid",
        "haq-e-mehr": "haq mehr dower",
        "khulla decree": "khula decree",
        "talaaq notice": "talaq divorce notice",
        "heba of land": "hiba gift of land",
        "haq shufa suit": "haq shufa pre-emption suit",
        "preemption suit": "pre-emption suit",
        "virasat mutation": "wirasat inheritance mutation",
        "qasas and diyat": "qisas and diyat",
        # must NOT change
        "Mehr Ali v. State": "Mehr Ali v. State",
        "constable dismissed from service": "constable dismissed from service",
        "the hearing was adjourned": "the hearing was adjourned",
        "shuffle, tally, ideal, khaled, hibernate": "shuffle, tally, ideal, khaled, hibernate",
        "": "",
    }
    bad = [(q, normalise(q), want) for q, want in cases.items() if normalise(q) != want]
    for q, got, want in bad:
        print(f"FAIL {q!r}: got {got!r}, want {want!r}")
    print("spelling self-check:", "OK" if not bad else f"{len(bad)} failures")
