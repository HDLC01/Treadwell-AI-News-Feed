import {
  createContext, useContext, useEffect, useRef, useState, type ReactNode,
} from "react";
import { Navigate, useLocation } from "react-router-dom";
import { ApiError, getAuthConfig, getMe, devLogin as apiDevLogin } from "./api";
import { getSupabase, initSupabase, setAccessToken, DEV_TOKEN_KEY } from "./supabase";
import type { User } from "./types";

type AuthStatus = "loading" | "authed" | "anon";

interface AuthCtx {
  user: User | null;
  status: AuthStatus;
  isAdmin: boolean;
  authError: string | null;
  configured: boolean;
  devEnabled: boolean;
  login: () => Promise<void>;
  devLogin: () => Promise<void>;
  logout: () => Promise<void>;
}

const Ctx = createContext<AuthCtx | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [status, setStatus] = useState<AuthStatus>("loading");
  const [authError, setAuthError] = useState<string | null>(null);
  const [configured, setConfigured] = useState(false);
  const [devEnabled, setDevEnabled] = useState(false);
  const inited = useRef(false);

  // Verify the current Supabase session against our API (derives the role).
  const refresh = async () => {
    try {
      const me = await getMe();
      setUser(me);
      setStatus("authed");
      setAuthError(null);
    } catch (e) {
      setUser(null);
      setStatus("anon");
      if (e instanceof ApiError && e.status === 403) setAuthError(e.message);
    }
  };

  useEffect(() => {
    if (inited.current) return;
    inited.current = true;
    (async () => {
      try {
        const cfg = await getAuthConfig();
        setConfigured(cfg.configured);
        setDevEnabled(cfg.dev_login);
        // A dev preview token (if present) takes precedence over Supabase.
        if (localStorage.getItem(DEV_TOKEN_KEY)) { await refresh(); return; }
        const sb = initSupabase(cfg.supabase_url, cfg.supabase_anon_key);
        if (!sb) { setStatus("anon"); return; }
        // Subscribe for LATER changes (sign-out, token refresh). Read the token
        // from the event's session arg — NEVER call getSession() inside this
        // callback (it deadlocks supabase-js v2).
        sb.auth.onAuthStateChange((event, session) => {
          setAccessToken(session?.access_token ?? null);
          if (event === "SIGNED_OUT" || !session) { setUser(null); setStatus("anon"); }
          else if (event === "SIGNED_IN" || event === "TOKEN_REFRESHED") { refresh(); }
        });
        // Resolve the INITIAL session explicitly (also processes the OAuth
        // redirect URL), so a fresh Google login / reload lands authed.
        const { data } = await sb.auth.getSession();
        setAccessToken(data.session?.access_token ?? null);
        if (data.session) await refresh();
        else setStatus("anon");
      } catch {
        setStatus("anon");
      }
    })();
  }, []);

  const value: AuthCtx = {
    user,
    status,
    isAdmin: user?.role === "admin",
    authError,
    configured,
    devEnabled,
    login: async () => {
      const sb = getSupabase();
      if (!sb) return;
      await sb.auth.signInWithOAuth({
        provider: "google",
        options: {
          redirectTo: window.location.origin,
          queryParams: { hd: "wetreadwell.com", prompt: "select_account" },
        },
      });
    },
    devLogin: async () => {
      await apiDevLogin();
      await refresh();
    },
    logout: async () => {
      localStorage.removeItem(DEV_TOKEN_KEY);
      setAccessToken(null);
      const sb = getSupabase();
      await sb?.auth.signOut().catch(() => {});
      setUser(null);
      setStatus("anon");
    },
  };
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useAuth(): AuthCtx {
  const ctx = useContext(Ctx);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}

function FullPageSpinner() {
  return (
    <div className="flex min-h-dvh items-center justify-center bg-bg">
      <div className="h-8 w-8 animate-spin rounded-full border-2 border-border border-t-accent" />
    </div>
  );
}

export function RequireAuth({ children }: { children: ReactNode }) {
  const { status } = useAuth();
  const loc = useLocation();
  if (status === "loading") return <FullPageSpinner />;
  if (status === "anon") return <Navigate to="/login" replace state={{ from: loc }} />;
  return <>{children}</>;
}

export function RequireAdmin({ children }: { children: ReactNode }) {
  const { status, isAdmin } = useAuth();
  if (status === "loading") return <FullPageSpinner />;
  if (status === "anon") return <Navigate to="/login" replace />;
  if (!isAdmin) {
    return (
      <div className="mx-auto max-w-md p-10 text-center text-muted">
        <p className="text-lg font-semibold text-fg">Admins only</p>
        <p className="mt-1 text-sm">You're signed in, but this area needs admin access.</p>
      </div>
    );
  }
  return <>{children}</>;
}
