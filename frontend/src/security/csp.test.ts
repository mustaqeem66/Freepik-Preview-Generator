import { describe, expect, it } from "vitest";
import { PRODUCTION_CSP, injectProductionCsp } from "../../security/csp";

const shell = `<!DOCTYPE html><html><head><meta charset="UTF-8" />
  <title>PreviewGen</title></head><body><div id="root"></div>
  <script type="module" src="/src/main.tsx"></script></body></html>`;

describe("production WebView Content Security Policy", () => {
  it("inserts a single policy early in the head before application scripts", () => {
    const output = injectProductionCsp(shell);
    expect(output).toContain('http-equiv="Content-Security-Policy"');
    expect(output).toContain('data-previewgen-csp="production"');
    expect(output.indexOf('http-equiv="Content-Security-Policy"'))
      .toBeLessThan(output.indexOf('<script'));
    expect(injectProductionCsp(output)).toBe(output);
  });

  it("limits scripts, blocks remote frames and preserves session preview images", () => {
    const directives = new Map(PRODUCTION_CSP.split("; ").map((part) => {
      const [name, ...values] = part.split(" ");
      return [name, values] as const;
    }));
    expect(directives.get("default-src")).toEqual(["'none'"]);
    expect(directives.get("script-src")).toEqual(["'self'", "'unsafe-eval'"]);
    expect(directives.get("script-src")).not.toContain("'unsafe-inline'");
    expect(directives.get("object-src")).toEqual(["'none'"]);
    expect(directives.get("frame-src")).toEqual(["'none'"]);
    expect(directives.get("img-src")).toContain("http://127.0.0.1:*");
    expect(directives.get("connect-src")).toContain("http://127.0.0.1:*");
    expect(directives.get("style-src")).toContain("'unsafe-inline'");
    expect(PRODUCTION_CSP).not.toContain("https:");
  });

  it("fails closed when the template has no reliable injection point", () => {
    expect(() => injectProductionCsp("<html><head></head><body></body></html>"))
      .toThrow(/charset/i);
    expect(() => injectProductionCsp('<meta charset="UTF-8" />'))
      .toThrow(/head/i);
  });
});
