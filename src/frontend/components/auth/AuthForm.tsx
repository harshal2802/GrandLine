"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { useState } from "react";
import Link from "next/link";
import { useAuthStore } from "@/stores/auth";

export function AuthForm({ mode }: { mode: "login" | "register" }) {
  const router = useRouter();
  const params = useSearchParams();
  const [email, setEmail] = useState("");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setBusy(true);
    try {
      if (mode === "login") {
        await useAuthStore.getState().login(email, password);
      } else {
        await useAuthStore.getState().register(email, username, password);
      }
      const redirect = params.get("redirect") || "/app/sea-chart";
      router.push(redirect);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Something went wrong");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="flex min-h-screen items-center justify-center bg-ocean-950 px-4">
      <form
        onSubmit={submit}
        className="w-full max-w-sm space-y-4 rounded-xl border border-ocean-800 bg-ocean-900/60 p-8"
      >
        <h1 className="text-2xl font-semibold text-ocean-50">
          {mode === "login" ? "Board the ship" : "Join the crew"}
        </h1>
        <p className="text-sm text-ocean-400">
          {mode === "login"
            ? "Sign in to reach the Observation Deck."
            : "Create an account to chart your first voyage."}
        </p>

        <label className="block text-sm">
          <span className="text-ocean-300">Email</span>
          <input
            type="email"
            required
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            className="mt-1 w-full rounded-md border border-ocean-700 bg-ocean-950 px-3 py-2 text-ocean-100 outline-none focus:border-ocean-400"
          />
        </label>

        {mode === "register" && (
          <label className="block text-sm">
            <span className="text-ocean-300">Username</span>
            <input
              type="text"
              required
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              className="mt-1 w-full rounded-md border border-ocean-700 bg-ocean-950 px-3 py-2 text-ocean-100 outline-none focus:border-ocean-400"
            />
          </label>
        )}

        <label className="block text-sm">
          <span className="text-ocean-300">Password</span>
          <input
            type="password"
            required
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            className="mt-1 w-full rounded-md border border-ocean-700 bg-ocean-950 px-3 py-2 text-ocean-100 outline-none focus:border-ocean-400"
          />
        </label>

        {error && <p className="text-sm text-rose-400">{error}</p>}

        <button
          type="submit"
          disabled={busy}
          className="w-full rounded-md bg-ocean-500 px-4 py-2 font-medium text-ocean-950 hover:bg-ocean-400 disabled:opacity-50"
        >
          {busy ? "…" : mode === "login" ? "Sign in" : "Create account"}
        </button>

        <p className="text-center text-sm text-ocean-400">
          {mode === "login" ? (
            <>
              New here?{" "}
              <Link href="/register" className="text-ocean-300 underline">
                Join the crew
              </Link>
            </>
          ) : (
            <>
              Already aboard?{" "}
              <Link href="/login" className="text-ocean-300 underline">
                Sign in
              </Link>
            </>
          )}
        </p>
      </form>
    </div>
  );
}
