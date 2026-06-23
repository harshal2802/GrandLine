// Security headers for every route. The auth cookie is intentionally
// non-HttpOnly (WS handshake needs it — see backend auth.py), so CSP is the
// documented XSS mitigation; keep it in place.
//
// connect-src allows localhost:8000 for dev and https/wss for deployments
// where the API lives on another origin (NEXT_PUBLIC_API_BASE_URL).
const contentSecurityPolicy = [
  "default-src 'self'",
  // Next.js requires inline scripts for hydration; 'unsafe-eval' only in dev.
  process.env.NODE_ENV === "development"
    ? "script-src 'self' 'unsafe-inline' 'unsafe-eval'"
    : "script-src 'self' 'unsafe-inline'",
  "style-src 'self' 'unsafe-inline'",
  "img-src 'self' data: blob:",
  "font-src 'self' data:",
  "connect-src 'self' http://localhost:8000 ws://localhost:8000 https: wss:",
  // The embedded preview (Phase B2) iframes the crew's app, which the Cabin runs
  // on a localhost port. Allow that origin (and https for deployed previews).
  "frame-src 'self' http://localhost:* http://127.0.0.1:* https:",
  "object-src 'none'",
  "base-uri 'self'",
  "form-action 'self'",
  "frame-ancestors 'none'",
].join("; ");

const securityHeaders = [
  { key: "Content-Security-Policy", value: contentSecurityPolicy },
  { key: "X-Frame-Options", value: "DENY" },
  { key: "X-Content-Type-Options", value: "nosniff" },
  { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
  { key: "Permissions-Policy", value: "camera=(), microphone=(), geolocation=()" },
];

/** @type {import('next').NextConfig} */
const nextConfig = {
  output: "standalone",
  async headers() {
    return [
      {
        source: "/:path*",
        headers: securityHeaders,
      },
    ];
  },
};

export default nextConfig;
