// Supabase client — initialized at runtime from /api/auth/config so we don't
// need build-time env. Used ONLY for Google sign-in; all feed data goes through
// our own API. The anon key is public by design.

import { createClient, type SupabaseClient } from "@supabase/supabase-js";

let client: SupabaseClient | null = null;

// DEV-ONLY preview token (set by the "Preview as admin" button). Takes
// precedence over a Supabase session when present.
export const DEV_TOKEN_KEY = "nf-dev-token";

export function initSupabase(url: string, anonKey: string): SupabaseClient | null {
  if (!url || !anonKey) return null;
  if (!client) {
    client = createClient(url, anonKey, {
      auth: { persistSession: true, autoRefreshToken: true, detectSessionInUrl: true },
    });
  }
  return client;
}

export function getSupabase(): SupabaseClient | null {
  return client;
}

// Current Supabase access token, kept in sync by AuthProvider via
// onAuthStateChange. We deliberately do NOT call getSession() here: calling it
// inside the onAuthStateChange callback deadlocks supabase-js v2 during the
// fresh-login flow. Reading the token the event already gave us avoids it.
let _accessToken: string | null = null;
export function setAccessToken(t: string | null) {
  _accessToken = t;
}

export async function getAccessToken(): Promise<string | null> {
  const dev = localStorage.getItem(DEV_TOKEN_KEY);
  if (dev) return dev;
  return _accessToken;
}
