import { NextRequest, NextResponse } from "next/server";

const PUBLIC_PATHS = new Set(["/", "/login", "/register"]);

export function middleware(request: NextRequest) {
  const { pathname } = request.nextUrl;

  // Allow public pages and static assets
  if (
    PUBLIC_PATHS.has(pathname) ||
    pathname.startsWith("/_next/") ||
    pathname.startsWith("/api/") ||
    pathname.includes(".")
  ) {
    return NextResponse.next();
  }

  // Protected routes: /app/* (Observation Deck)
  const token = request.cookies.get("access_token")?.value;

  if (!token) {
    const loginUrl = new URL("/login", request.url);
    loginUrl.searchParams.set("redirect", pathname);
    return NextResponse.redirect(loginUrl);
  }

  return NextResponse.next();
}

export const config = {
  matcher: ["/((?!_next/static|_next/image|favicon.ico).*)"],
};
