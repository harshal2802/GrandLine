import { describe, it, expect, vi, beforeEach } from "vitest";
import { NextRequest, NextResponse } from "next/server";
import { middleware } from "./middleware";

// Mock NextResponse methods
vi.mock("next/server", async () => {
  const actual = await vi.importActual("next/server");
  return {
    ...actual,
    NextResponse: {
      next: vi.fn(() => ({ type: "next" })),
      redirect: vi.fn((url: URL) => ({ type: "redirect", url })),
    },
  };
});

function createRequest(pathname: string, cookie?: { name: string; value: string }) {
  const url = new URL(`http://localhost:3000${pathname}`);
  const req = new NextRequest(url);
  if (cookie) {
    req.cookies.set(cookie.name, cookie.value);
  }
  return req;
}

describe("Next.js Auth Middleware", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("allows public landing page", () => {
    const req = createRequest("/");
    middleware(req);
    expect(NextResponse.next).toHaveBeenCalled();
  });

  it("allows /login page", () => {
    const req = createRequest("/login");
    middleware(req);
    expect(NextResponse.next).toHaveBeenCalled();
  });

  it("allows /register page", () => {
    const req = createRequest("/register");
    middleware(req);
    expect(NextResponse.next).toHaveBeenCalled();
  });

  it("allows Next.js internal routes", () => {
    const req = createRequest("/_next/static/chunk.js");
    middleware(req);
    expect(NextResponse.next).toHaveBeenCalled();
  });

  it("redirects unauthenticated user from /app route", () => {
    const req = createRequest("/app");
    middleware(req);
    expect(NextResponse.redirect).toHaveBeenCalled();
    const redirectUrl = (NextResponse.redirect as unknown as ReturnType<typeof vi.fn>).mock
      .calls[0][0] as URL;
    expect(redirectUrl.pathname).toBe("/login");
    expect(redirectUrl.searchParams.get("redirect")).toBe("/app");
  });

  it("allows authenticated user to access /app route", () => {
    const req = createRequest("/app", { name: "access_token", value: "some-jwt" });
    middleware(req);
    expect(NextResponse.next).toHaveBeenCalled();
  });

  it("redirects unauthenticated user from nested /app route", () => {
    const req = createRequest("/app/sea-chart");
    middleware(req);
    expect(NextResponse.redirect).toHaveBeenCalled();
  });
});
