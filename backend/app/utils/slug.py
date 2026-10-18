import re
from nanoid import generate

ALPHABET = "abcdefghijklmnopqrstuvwxyz0123456789"


def slugify(text: str) -> str:
    """
    Convert arbitrary text into URL-safe base slug.
    'Murder Trial: Bail Application' → 'murder-trial-bail-application'
    """
    text = text.lower().strip()
    text = re.sub(r'\s+', '-', text)
    text = re.sub(r'[^\w\-]', '', text)
    text = re.sub(r'-+', '-', text)
    text = text.strip('-')
    return text[:50]


def make_slug(text: str) -> str:
    """Generate a single candidate slug. Not guaranteed unique."""
    base = slugify(text) or "chat"
    suffix = generate(ALPHABET, 5)
    return f"{base}-{suffix}"
