import { Navigate, useLocation } from "react-router-dom";
import { Radar, AlertCircle } from "lucide-react";
import { useAuth } from "../lib/auth";

export default function LoginPage() {
  const { login, devLogin, status, authError, configured, devEnabled } = useAuth();
  const loc = useLocation() as { state?: { from?: { pathname?: string } } };

  if (status === "loading") {
    return (
      <div className="flex min-h-dvh items-center justify-center bg-bg">
        <div className="h-8 w-8 animate-spin rounded-full border-2 border-border border-t-accent" />
      </div>
    );
  }
  if (status === "authed") return <Navigate to={loc.state?.from?.pathname || "/"} replace />;

  return (
    <div className="flex min-h-dvh items-center justify-center bg-bg px-4">
      <div className="w-full max-w-sm">
        <div className="mb-6 flex flex-col items-center text-center">
          <div className="grid h-12 w-12 place-items-center rounded-xl bg-primary text-primary-fg">
            <Radar className="h-6 w-6" />
          </div>
          <h1 className="mt-3 text-xl font-bold text-fg">Treadwell Radar</h1>
          <p className="mt-1 text-sm text-cold">
            Sign in with your Treadwell Google account.
          </p>
        </div>

        <div className="rounded-xl border border-border bg-surface p-6 shadow-sm">
          {authError && (
            <p role="alert" className="mb-4 flex items-center gap-2 rounded-lg bg-destructive/10 px-3 py-2 text-sm text-destructive">
              <AlertCircle className="h-4 w-4 shrink-0" /> {authError}
            </p>
          )}
          <button
            type="button"
            onClick={login}
            disabled={!configured}
            className="inline-flex h-11 w-full cursor-pointer items-center justify-center gap-3 rounded-lg border border-border bg-surface font-semibold text-fg transition-colors hover:bg-muted disabled:cursor-not-allowed disabled:opacity-60"
          >
            <GoogleMark /> Continue with Google
          </button>
          {!configured && !devEnabled && (
            <p className="mt-3 text-center text-xs text-cold">
              Sign-in isn't configured on the server yet (Supabase keys missing).
            </p>
          )}
          {devEnabled && (
            <>
              <div className="my-4 flex items-center gap-2 text-[11px] uppercase tracking-wide text-cold">
                <span className="h-px flex-1 bg-border" /> dev <span className="h-px flex-1 bg-border" />
              </div>
              <button
                type="button"
                onClick={devLogin}
                className="inline-flex h-11 w-full cursor-pointer items-center justify-center rounded-lg border border-dashed border-accent/60 bg-accent/5 text-sm font-semibold text-accent hover:bg-accent/10"
              >
                Preview as admin (dev only)
              </button>
            </>
          )}
          <p className="mt-4 text-center text-xs text-cold">
            Only <strong>@wetreadwell.com</strong> accounts can access this radar.
          </p>
        </div>
      </div>
    </div>
  );
}

function GoogleMark() {
  return (
    <svg className="h-5 w-5" viewBox="0 0 24 24" aria-hidden="true">
      <path fill="#4285F4" d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92a5.06 5.06 0 0 1-2.2 3.32v2.77h3.57c2.08-1.92 3.27-4.74 3.27-8.1z" />
      <path fill="#34A853" d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.99.66-2.26 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84A11 11 0 0 0 12 23z" />
      <path fill="#FBBC05" d="M5.84 14.1a6.6 6.6 0 0 1 0-4.2V7.06H2.18a11 11 0 0 0 0 9.88l3.66-2.84z" />
      <path fill="#EA4335" d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1A11 11 0 0 0 2.18 7.06l3.66 2.84C6.71 7.31 9.14 5.38 12 5.38z" />
    </svg>
  );
}
