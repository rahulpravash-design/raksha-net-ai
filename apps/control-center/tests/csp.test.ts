import { describe, expect, it } from "vitest";

import { contentSecurityPolicy, newNonce } from "@raksha/ui/csp";

const base = { apiBaseUrl: "https://api.raksha.example/v1", dev: false };

function directives(policy: string): Record<string, string> {
  return Object.fromEntries(
    policy.split("; ").map((part) => {
      const [name, ...rest] = part.split(" ");
      return [name!, rest.join(" ")];
    }),
  );
}

describe("contentSecurityPolicy", () => {
  it("lets scripts run only with this request's nonce — no 'unsafe-inline'", () => {
    const policy = directives(contentSecurityPolicy({ ...base, nonce: "abc123==" }));
    expect(policy["script-src"]).toBe("'self' 'nonce-abc123==' 'strict-dynamic'");
    expect(policy["script-src"]).not.toContain("unsafe-inline");
    expect(policy["script-src"]).not.toContain("unsafe-eval");
  });

  it("adds 'unsafe-eval' in development only", () => {
    const dev = directives(contentSecurityPolicy({ ...base, nonce: "n", dev: true }));
    expect(dev["script-src"]).toContain("'unsafe-eval'");
  });

  it("talks only to itself and the API, and frames nothing", () => {
    const policy = directives(contentSecurityPolicy({ ...base, nonce: "n" }));
    expect(policy["connect-src"]).toBe("'self' https://api.raksha.example");
    expect(policy["default-src"]).toBe("'self'");
    expect(policy["object-src"]).toBe("'none'");
    expect(policy["frame-ancestors"]).toBe("'none'");
    expect(policy["base-uri"]).toBe("'self'");
  });

  it("allows no API origin when the API address is unusable, instead of throwing", () => {
    const policy = directives(
      contentSecurityPolicy({ apiBaseUrl: undefined, nonce: "n", dev: false }),
    );
    expect(policy["connect-src"]).toBe("'self'");
  });

  it("allows map tiles from the configured host, subdomains included", () => {
    const osm = directives(contentSecurityPolicy({ ...base, nonce: "n" }));
    expect(osm["img-src"]).toContain("https://*.tile.openstreetmap.org");
    const custom = directives(
      contentSecurityPolicy({ ...base, nonce: "n", tileUrl: "https://tiles.example.org/{z}/{x}/{y}.png" }),
    );
    expect(custom["img-src"]).toContain("https://tiles.example.org");
  });

  it("keeps 'unsafe-inline' for styles only — the documented remainder", () => {
    const policy = directives(contentSecurityPolicy({ ...base, nonce: "n" }));
    expect(policy["style-src"]).toBe("'self' 'unsafe-inline'");
  });
});

describe("newNonce", () => {
  it("is 128 random bits, base64, different every time", () => {
    const seen = new Set(Array.from({ length: 200 }, () => newNonce()));
    expect(seen.size).toBe(200);
    for (const nonce of seen) {
      expect(nonce).toMatch(/^[A-Za-z0-9+/]{22}==$/);
    }
  });
});
