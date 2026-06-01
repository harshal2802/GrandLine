import { describe, expect, it } from "vitest";
import { decodeJwt, expiresInMs } from "@/lib/auth/jwt";

function makeJwt(claims: Record<string, unknown>): string {
  const b64 = (o: unknown) =>
    Buffer.from(JSON.stringify(o)).toString("base64url");
  return `${b64({ alg: "HS256" })}.${b64(claims)}.sig`;
}

describe("decodeJwt", () => {
  it("decodes the payload", () => {
    const token = makeJwt({ sub: "u1", exp: 1234, type: "access" });
    expect(decodeJwt(token)).toMatchObject({ sub: "u1", exp: 1234 });
  });

  it("returns null on malformed tokens", () => {
    expect(decodeJwt("not-a-jwt")).toBeNull();
  });
});

describe("expiresInMs (P4)", () => {
  it("computes ms to exp", () => {
    const now = 1_000_000;
    const token = makeJwt({ exp: (now + 5_000) / 1000 });
    expect(expiresInMs(token, now)).toBe(5_000);
  });

  it("clamps expired tokens to 0", () => {
    const now = 1_000_000;
    const token = makeJwt({ exp: (now - 5_000) / 1000 });
    expect(expiresInMs(token, now)).toBe(0);
  });
});
