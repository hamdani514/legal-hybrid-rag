/**
 * Readable addresses for saved conversations: /chat/<title words>-<id>.
 *
 *   /chat/dispute-between-husband-and-wife-on-a1b2c3d4
 *
 * The last 8 characters are the start of the conversation's own id (a uuid4
 * from /api/chat/sessions), and only they are used to find the conversation.
 * The words are for people: renaming a conversation changes them, but an old
 * link still opens it, because its id part has not changed.
 */
const ID_CHARS = 8;
const MAX_WORDS = 8;
const MAX_CHARS = 50; // the words part; whole words only, never cut mid-word

const shortId = (sessionId) =>
  String(sessionId || '').replace(/-/g, '').slice(0, ID_CHARS).toLowerCase();

/** "Section 12(2) CPC: fraud!" gives "section-12-2-cpc-fraud". */
const titleWords = (title) => {
  const words = String(title || '')
    .toLowerCase()
    .replace(/[^a-z0-9\s_-]/g, ' ')
    .split(/[\s_-]+/)
    .filter(Boolean);
  const kept = [];
  for (const word of words) {
    if (kept.length >= MAX_WORDS || [...kept, word].join('-').length > MAX_CHARS) break;
    kept.push(word);
  }
  return kept.join('-');
};

/** The slug for one conversation. A title with no Latin letters or digits gives just the id. */
export const chatSlug = (sessionId, title) => {
  const words = titleWords(title);
  const id = shortId(sessionId);
  return words ? `${words}-${id}` : id;
};

export const chatPath = (sessionId, title) => `/chat/${chatSlug(sessionId, title)}`;

/** The id part of a slug ("...-a1b2c3d4" gives "a1b2c3d4"), or "" if it has none. */
export const slugId = (slug) => {
  const last = String(slug || '').toLowerCase().split('-').pop() || '';
  return new RegExp(`^[0-9a-f]{${ID_CHARS}}$`).test(last) ? last : '';
};

/** Does this address point at this conversation? */
export const slugMatches = (slug, sessionId) => {
  const id = slugId(slug);
  return Boolean(id && sessionId) && id === shortId(sessionId);
};
