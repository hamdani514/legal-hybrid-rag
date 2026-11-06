/*
 * The loading skeleton in index.html stays until the first page has really
 * drawn. Pages are loaded on demand (App.jsx), so "React has started" is not
 * enough: on a refresh of /welcome the page's own code may still be arriving.
 * <PageReady /> sits inside the same Suspense boundary as the routes, so its
 * effect runs only once the routed page has rendered.
 */
let markReady;
export const pageReady = new Promise((resolve) => {
  markReady = resolve;
});
export const markPageReady = () => markReady();
