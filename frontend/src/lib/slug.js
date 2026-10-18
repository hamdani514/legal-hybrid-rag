/**
 * URL slugs, mirroring backend/app/utils/slug.py.
 *
 * The server is still the authority — it resolves collisions by appending -2,
 * -3 and returns the slug it actually used. This exists so the admin editor
 * can show the author what their title will become as they type, rather than
 * leaving the field blank until the first save.
 *
 * Keep the two in step: lowercase, spaces to hyphens, drop anything that is
 * not a word character or hyphen, collapse runs, trim, cap at 50 characters.
 */
export const slugify = (text) =>
  String(text ?? '')
    .toLowerCase()
    .trim()
    .replace(/\s+/g, '-')
    .replace(/[^\w-]/g, '')
    .replace(/-+/g, '-')
    .replace(/^-+|-+$/g, '')
    .slice(0, 50)
    // A title ending in punctuation can leave a trailing hyphen after the cut.
    .replace(/-+$/, '');

export default slugify;
