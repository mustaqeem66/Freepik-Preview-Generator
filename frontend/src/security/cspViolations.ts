/**
 * Report Content Security Policy violations to the native backend.
 *
 * Event coverage varies by WebView engine. These reports are diagnostics;
 * the native smoke test validates enforcement separately.
 */

/** One CSP violation as reported by the browser engine. */
export interface CspViolation {
  /** The policy directive that was violated, e.g. "script-src". */
  effectiveDirective: string;
  /** The URL the engine refused to load. */
  blockedURI: string;
  /** The policy source expression that blocked it. */
  violatedDirective: string;
  /** The resource type the engine refused, e.g. "script". */
  resourceType: string;
  /** The original policy text, when the engine supplies it. */
  sourceFile?: string;
  /** The line number in the source file, when the engine supplies it. */
  lineNumber?: number;
}

/** How a violation is delivered to the backend. */
export type CspViolationSink = (violations: CspViolation[]) => void | Promise<void>;

interface SecurityPolicyViolationEvent extends Event {
  effectiveDirective?: string;
  blockedURI?: string;
  violatedDirective?: string;
  resourceType?: string;
  sourceFile?: string;
  lineNumber?: number;
}

const MAX_REPORTED_VIOLATIONS = 50;

/**
 * Normalise a `SecurityPolicyViolationEvent` into a plain record.
 *
 * Engines differ in which fields they populate, so every field is optional
 * and the reader substitutes an empty string rather than dropping the event.
 * A violation without detail is still useful for diagnostics.
 */
export function normaliseViolation(event: SecurityPolicyViolationEvent): CspViolation {
  return {
    effectiveDirective: event.effectiveDirective ?? "",
    blockedURI: event.blockedURI ?? "",
    violatedDirective: event.violatedDirective ?? "",
    resourceType: event.resourceType ?? "",
    ...(event.sourceFile ? { sourceFile: event.sourceFile } : {}),
    ...(typeof event.lineNumber === "number" ? { lineNumber: event.lineNumber } : {}),
  };
}

/**
 * Listen for CSP violations and hand them to `sink`.
 *
 * Returns a function that removes the listener, so a test or a hot reload can
 * tear it down without leaking a listener into the next mount.
 */
export function watchCspViolations(sink: CspViolationSink): () => void {
  const pending: CspViolation[] = [];
  let flushing = false;

  const flush = async () => {
    if (flushing || pending.length === 0) return;
    flushing = true;
    try {
      while (pending.length > 0) {
        try {
          await sink(pending.splice(0));
        } catch {
          // Reporting must not interfere with the app or later diagnostics.
        }
      }
    } finally {
      flushing = false;
    }
  };

  const handler = (event: Event) => {
    if (pending.length < MAX_REPORTED_VIOLATIONS) {
      pending.push(normaliseViolation(event as SecurityPolicyViolationEvent));
    }
    void flush();
  };

  document.addEventListener("securitypolicyviolation", handler);
  return () => {
    document.removeEventListener("securitypolicyviolation", handler);
    pending.length = 0;
  };
}
