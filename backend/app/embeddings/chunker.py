"""
Token-exact, sentence-aware splitting for the embedding pipeline.

Why this module exists
----------------------
BGE models have a hard 512-token window, and sentence-transformers truncates
anything longer *silently* — no warning, no error, just a vector built from the
first part of the text. Ingestion previously wrote one vector per section with
no splitting, so on the 11-judgment corpus:

    33%   of section nodes exceeded the window
    49.4% of all section words never reached the index

and the worst-affected nodes were the ANALYSIS_RATIO sections — the Court's
reasoning, which is the most valuable text in a judgment and the thing a
researcher is actually searching for.

The measurement that matters
----------------------------
Budgets are measured with the embedding model's OWN tokenizer, not a
words-times-a-constant estimate. Legal English runs anywhere from 1.2 to 1.6
WordPiece tokens per whitespace word depending on how much Latin, Urdu
transliteration and citation formatting a passage carries, so a word heuristic
is either wasteful or wrong, and being wrong here is silent.

Splitting policy
----------------
Sentences are the unit. A chunk is grown one sentence at a time until the next
sentence would breach the budget, then closed. Consecutive chunks overlap by
`CHUNK_OVERLAP_SENTENCES`, so a holding that straddles a boundary is complete
in at least one chunk rather than halved in both.

A single sentence longer than the whole budget — rare, but Pakistani judgments
do contain page-long sentences with embedded citation strings — is hard-split
at token boundaries, because the alternative is dropping it.

Text short enough to fit returns exactly one chunk whose text is the input
unchanged, so short sections behave precisely as they did before chunking.
"""

import re
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.config import settings
from app.embeddings.embedding_generator import EmbeddingGenerator

# Sentence boundary: a full stop, question or exclamation mark followed by
# whitespace and something that starts a new sentence.
#
# The abbreviation exclusions matter for this corpus specifically. Judgments
# are dense with "No.", "Mr.", "Vs.", "Art." and "s. 9(1)", and splitting on
# those would shatter a paragraph into fragments too small to carry meaning.
_ABBREVIATIONS = (
    "no", "nos", "mr", "mrs", "ms", "dr", "vs", "v", "art", "arts", "s", "ss",
    "sec", "secs", "ch", "para", "paras", "pp", "p", "cf", "viz", "etc", "ibid",
    "hon", "j", "cj", "sc", "pld", "scmr", "ord", "r", "o", "cl", "sub",
)
_ABBREVIATION_SET = frozenset(_ABBREVIATIONS)

# A candidate sentence boundary. Python's `re` only allows fixed-width
# lookbehind, so the abbreviation rule cannot live in the pattern; candidates
# are matched loosely here and filtered by `_ends_abbreviation` below.
_SENTENCE_END = re.compile(
    r"[.!?]+[\"')\]]*"        # the terminator, plus any closing quote
    r"\s+"                     # the whitespace that follows it
    r"(?=[\"'(\[]*[A-Z0-9])"  # next sentence starts here
)

# The word immediately before a terminator, for the abbreviation check.
_TRAILING_WORD = re.compile(r"([A-Za-z]+)[.!?]+[\"')\]]*\s*$")


def _ends_abbreviation(text_before: str) -> bool:
    """True when `text_before` ends in a known abbreviation or an initial.

    Judgments are dense with "No.", "Mr.", "Vs.", "Art." and "s. 9(1)", and a
    single-letter initial as in "M. Akram". Treating any of those as a sentence
    end shatters a paragraph into fragments too small to carry meaning.
    """
    match = _TRAILING_WORD.search(text_before)
    if not match:
        return False

    word = match.group(1)
    # A lone capital is an initial, not a sentence: "Mr. M. Akram".
    if len(word) == 1 and word.isupper():
        return True
    return word.lower() in _ABBREVIATION_SET


# Paragraph breaks are a stronger signal than any sentence rule, so they are
# split on first and never merged across.
_PARAGRAPH_BREAK = re.compile(r"\n\s*\n+")

_generator = EmbeddingGenerator()


def _tokenizer():
    """The embedding model's own tokenizer — the only authority on length."""
    return _generator.model.tokenizer


def count_tokens(text: str) -> int:
    """Return the number of model tokens in `text`, excluding special tokens."""
    if not text:
        return 0
    return len(_tokenizer().encode(text, add_special_tokens=False))


def split_sentences(text: str) -> list[str]:
    """Split text into sentences, never merging across a paragraph break."""
    sentences: list[str] = []

    for paragraph in _PARAGRAPH_BREAK.split(text):
        paragraph = paragraph.strip()
        if not paragraph:
            continue

        start = 0
        for match in _SENTENCE_END.finditer(paragraph):
            if _ends_abbreviation(paragraph[start:match.end()]):
                continue
            piece = paragraph[start:match.end()].strip()
            if piece:
                sentences.append(piece)
            start = match.end()

        tail = paragraph[start:].strip()
        if tail:
            sentences.append(tail)

    return sentences


def _hard_split(sentence: str, budget: int) -> list[str]:
    """Split one over-long sentence at token boundaries.

    Only reached when a single sentence exceeds the whole chunk budget. The
    decode is lossy at the margins (WordPiece does not round-trip whitespace
    perfectly), which is acceptable because the alternative is losing the
    sentence altogether.
    """
    tokenizer = _tokenizer()
    ids = tokenizer.encode(sentence, add_special_tokens=False)

    pieces: list[str] = []
    for start in range(0, len(ids), budget):
        piece = tokenizer.decode(ids[start:start + budget], skip_special_tokens=True).strip()
        if piece:
            pieces.append(piece)

    return pieces


def chunk_text(
    text: str,
    max_tokens: int | None = None,
    overlap_sentences: int | None = None,
) -> list[dict]:
    """Split `text` into token-bounded, sentence-aligned chunks.

    Args:
        text: The section text to split.
        max_tokens: Token budget per chunk. Defaults to CHUNK_MAX_TOKENS.
        overlap_sentences: How many sentences each chunk repeats from the one
            before it. Defaults to CHUNK_OVERLAP_SENTENCES.

    Returns:
        A list of ``{"text", "chunk_index", "token_count"}`` dicts, in reading
        order. Empty input returns an empty list; text that already fits
        returns exactly one chunk holding the input unchanged.
    """
    max_tokens = max_tokens or settings.CHUNK_MAX_TOKENS
    overlap_sentences = (
        settings.CHUNK_OVERLAP_SENTENCES if overlap_sentences is None else overlap_sentences
    )

    text = (text or "").strip()
    if not text:
        return []

    # The common case: it already fits, so leave it exactly as it was.
    total = count_tokens(text)
    if total <= max_tokens:
        return [{"text": text, "chunk_index": 0, "token_count": total}]

    sentences = split_sentences(text) or [text]

    # Expand any sentence that cannot fit a chunk on its own.
    expanded: list[str] = []
    for sentence in sentences:
        if count_tokens(sentence) > max_tokens:
            expanded.extend(_hard_split(sentence, max_tokens))
        else:
            expanded.append(sentence)

    chunks: list[str] = []
    current: list[str] = []
    current_tokens = 0

    for sentence in expanded:
        sentence_tokens = count_tokens(sentence)

        if current and current_tokens + sentence_tokens > max_tokens:
            chunks.append(" ".join(current))

            # Carry the tail sentences forward so a holding that straddles the
            # boundary survives whole in the next chunk.
            carried = current[-overlap_sentences:] if overlap_sentences else []
            # Never let the overlap alone fill the budget, or the window stops
            # advancing and the loop cannot terminate.
            while carried and sum(count_tokens(s) for s in carried) + sentence_tokens > max_tokens:
                carried.pop(0)

            current = [*carried, sentence]
            current_tokens = sum(count_tokens(s) for s in current)
        else:
            current.append(sentence)
            current_tokens += sentence_tokens

    if current:
        chunks.append(" ".join(current))

    return [
        {"text": chunk, "chunk_index": index, "token_count": count_tokens(chunk)}
        for index, chunk in enumerate(chunks)
    ]


def chunk_node(title: str, text: str, **kwargs) -> list[dict]:
    """Chunk one node's text, repeating its heading on every chunk.

    The heading is prepended to every chunk rather than only the first, because
    a chunk is retrieved on its own: a passage from the middle of
    ANALYSIS_RATIO that does not say which section it belongs to embeds as
    unattributed prose, and matches correspondingly worse.

    Args:
        title: The node's heading.
        text: The node's body text.

    Returns:
        Chunks whose ``text`` is the embedding-ready string.
    """
    title = (title or "").strip()
    body = (text or "").strip()

    if not body:
        if not title:
            return []
        return [{"text": title, "chunk_index": 0, "token_count": count_tokens(title)}]

    # The heading costs tokens on every chunk, so the body budget shrinks by it.
    max_tokens = kwargs.pop("max_tokens", None) or settings.CHUNK_MAX_TOKENS
    title_cost = count_tokens(f"{title}\n\n") if title else 0
    body_budget = max(max_tokens - title_cost, 64)

    chunks = chunk_text(body, max_tokens=body_budget, **kwargs)

    if not title:
        return chunks

    return [
        {
            "text": f"{title}\n\n{chunk['text']}",
            "chunk_index": chunk["chunk_index"],
            "token_count": chunk["token_count"] + title_cost,
        }
        for chunk in chunks
    ]


if __name__ == "__main__":
    budget = settings.CHUNK_MAX_TOKENS
    print(f"model  : {settings.EMBEDDING_MODEL}")
    print(f"budget : {budget} tokens\n")

    # 1. Short text passes through untouched — the no-regression case.
    short = "The appeal is dismissed. No order as to costs."
    out = chunk_text(short)
    assert len(out) == 1 and out[0]["text"] == short, "short text was altered"
    print(f"short text         -> 1 chunk, {out[0]['token_count']} tokens  OK")

    # 2. Abbreviations must not create sentence boundaries.
    abbrev = "Civil Appeal No. 23-P of 2017 was heard by Mr. Justice Khan. It was dismissed."
    sents = split_sentences(abbrev)
    assert len(sents) == 2, f"abbreviation split wrongly into {len(sents)}: {sents}"
    print(f"abbreviations      -> {len(sents)} sentences from {abbrev.count('.')} full stops  OK")

    # 3. A long section must split, and NO chunk may exceed the budget.
    long_text = " ".join(
        f"The learned counsel for the appellant submitted that ground {i} was "
        f"not considered by the High Court in its impugned judgment dated {1990 + i}."
        for i in range(400)
    )
    out = chunk_text(long_text)
    over = [c for c in out if c["token_count"] > budget]
    print(f"long section       -> {count_tokens(long_text)} tokens into {len(out)} chunks")
    print(f"                      largest chunk = {max(c['token_count'] for c in out)} tokens")
    assert not over, f"{len(over)} chunks exceed the {budget}-token budget"

    # 4. Coverage: chunking must not lose text.
    rejoined = " ".join(c["text"] for c in out)
    assert "ground 0 " in rejoined and "ground 399 " in rejoined, "chunking lost content"
    print("coverage           -> first and last sentence both present  OK")

    # 5. Overlap must actually overlap, or a straddling holding is lost.
    assert len(out) > 1, "test fixture did not split"
    first = set(split_sentences(out[0]["text"]))
    second = set(split_sentences(out[1]["text"]))
    assert first & second, "consecutive chunks share no sentence"
    print(f"overlap            -> {len(first & second)} shared sentences across the boundary  OK")

    # 6. A single sentence longer than the budget must still be split.
    monster = "The Court held that " + "the said provision and " * 900 + "it is so ordered."
    out = chunk_text(monster)
    assert all(c["token_count"] <= budget for c in out), "hard split breached the budget"
    print(f"over-long sentence -> {count_tokens(monster)} tokens into {len(out)} chunks  OK")

    # 7. chunk_node repeats the heading on every chunk.
    out = chunk_node("Analysis / Ratio", long_text)
    assert all(c["text"].startswith("Analysis / Ratio") for c in out), "heading missing"
    assert all(c["token_count"] <= budget for c in out), "heading pushed a chunk over budget"
    print(f"chunk_node         -> heading on all {len(out)} chunks, all within budget  OK")

    print("\nOK: chunker verified.")
