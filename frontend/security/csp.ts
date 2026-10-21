/**
 * Production-only Content Security Policy for the privileged desktop WebView.
 *
 * Requirements:
 * - Vite emits same-origin JS/CSS assets into ./assets.
 * - pywebview uses eval-based bridge helpers on supported native engines.
 * - React sets inline style properties for canvas/layout.
 * - JPEG previews come from the session-token protected 127.0.0.1 HTTP server,
 *   whose ephemeral port is not known until runtime.
 * - The desktop bridge may use a loopback HTTP/WebSocket transport depending
 *   on the host engine; development HMR does not use this policy.
 *
 * Unsafe inline SCRIPT is deliberately not allowed. Keep any future
 * relaxation backed by real packaged Windows/macOS/Linux tests.
 */
export const PRODUCTION_CSP = [
  "default-src 'none'",
  "base-uri 'none'",
  "form-action 'none'",
  "object-src 'none'",
  "frame-src 'none'",
  "worker-src 'none'",
  "script-src 'self' 'unsafe-eval'",
  "style-src 'self' 'unsafe-inline'",
  "img-src 'self' data: blob: http://127.0.0.1:*",
  "font-src 'self' data:",
  "connect-src 'self' http://127.0.0.1:* http://localhost:* ws://127.0.0.1:* ws://localhost:*",
  "media-src 'none'",
].join("; ");

const MARKER = 'data-previewgen-csp="production"';

/**
 * Inject immediately after charset, before any external script or stylesheet.
 * Fails the build rather than silently emitting an unprotected privileged UI.
 * Only Vite's build mode invokes this helper; dev HMR remains unaffected.
 */
export function injectProductionCsp(html: string): string {
  if (html.includes(MARKER)) return html;
  const charset = /<meta\s+charset=["']?utf-8["']?\s*\/?>/i;
  const match = charset.exec(html);
  if (!match) throw new Error("PreviewGen production CSP: missing UTF-8 charset meta tag");
  if (!html.includes("</head>")) {
    throw new Error("PreviewGen production CSP: missing head element");
  }
  const tag = `<meta http-equiv="Content-Security-Policy" ${MARKER} content="${PRODUCTION_CSP}" />`;
  return html.replace(match[0], `${match[0]}\n    ${tag}`);
}
