/** The server writes each route's Arabic title and description (src/qayem/seo.py). On the page a visitor
 * landed on, in Arabic, the app keeps them: search engines read the rendered page, and these are written
 * for search. Pages opened afterwards inside the app get the app's own titles. */
const landing = window.location.pathname;
export const serverTitle = document.title;
const serverHead = Boolean(document.querySelector('link[rel="canonical"]'));

export const keepsServerHead = (language: string) =>
  serverHead && language === "ar" && window.location.pathname === landing;
