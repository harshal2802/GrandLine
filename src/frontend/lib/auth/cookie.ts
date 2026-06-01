// Read-only cookie helper. The backend sets a non-HttpOnly `access_token`
// cookie so the WS handshake (which can't send Authorization headers) can read
// it (Decision 4 / P4).

export function readCookie(name: string): string | null {
  if (typeof document === "undefined") return null;
  const match = document.cookie
    .split("; ")
    .find((row) => row.startsWith(`${name}=`));
  return match ? decodeURIComponent(match.slice(name.length + 1)) : null;
}
