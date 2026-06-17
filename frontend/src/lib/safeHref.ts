/**
 * Return `u` only if it is a safe http(s) URL, otherwise `undefined`.
 *
 * Project/contact/signal URLs originate from ingested web content + AI
 * extraction, so a poisoned record could carry a `javascript:` or `data:` URL
 * that becomes a stored-XSS click. Gate every such href through this helper and
 * fall back to plain text when it returns undefined.
 */
export function safeHref(u?: string | null): string | undefined {
  if (!u) return undefined;
  try {
    const parsed = new URL(u, window.location.origin);
    return parsed.protocol === "http:" || parsed.protocol === "https:" ? u : undefined;
  } catch {
    return undefined;
  }
}
