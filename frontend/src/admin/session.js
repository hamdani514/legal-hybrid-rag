/** The admin saved at sign-in (localStorage "currentAdmin"), or null when there
 * is none or it cannot be read. Read once when a page first renders, so the
 * page knows its admin without an extra render; the server still checks the
 * token on every request. */
export const readStoredAdmin = () => {
  try {
    return JSON.parse(localStorage.getItem('currentAdmin') || 'null');
  } catch {
    return null;
  }
};
