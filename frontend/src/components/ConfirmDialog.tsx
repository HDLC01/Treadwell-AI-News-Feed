import { useEffect, useRef } from "react";
import { AlertTriangle, X } from "lucide-react";

interface Props {
  open: boolean;
  title: string;
  message?: string;
  confirmLabel?: string;
  cancelLabel?: string;
  /** When true, the confirm button uses the destructive color (dismiss/remove/merge). */
  destructive?: boolean;
  busy?: boolean;
  onConfirm: () => void;
  onCancel: () => void;
}

// Required for all destructive actions (dismiss / remove / merge) per SPEC §5.
// Focus-traps lightly, closes on Escape, click-outside cancels.
export default function ConfirmDialog({
  open,
  title,
  message,
  confirmLabel = "Confirm",
  cancelLabel = "Cancel",
  destructive = false,
  busy = false,
  onConfirm,
  onCancel,
}: Props) {
  const confirmRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    if (!open) return;
    confirmRef.current?.focus();
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape" && !busy) onCancel();
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [open, busy, onCancel]);

  if (!open) return null;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4"
      role="dialog"
      aria-modal="true"
      aria-labelledby="confirm-dialog-title"
    >
      <div
        className="absolute inset-0 bg-black/50 transition-opacity duration-200"
        onClick={() => !busy && onCancel()}
        aria-hidden="true"
      />
      <div className="relative z-10 w-full max-w-md rounded-xl border border-border bg-surface p-5 shadow-xl transition-all duration-200">
        <div className="flex items-start gap-3">
          <span
            className={`inline-flex h-10 w-10 shrink-0 items-center justify-center rounded-full ${
              destructive ? "bg-destructive/10 text-destructive" : "bg-primary/10 text-primary"
            }`}
          >
            <AlertTriangle className="h-5 w-5" aria-hidden="true" />
          </span>
          <div className="min-w-0 flex-1">
            <h2
              id="confirm-dialog-title"
              className="text-base font-semibold text-fg"
            >
              {title}
            </h2>
            {message && <p className="mt-1 text-sm text-cold">{message}</p>}
          </div>
          <button
            type="button"
            onClick={() => !busy && onCancel()}
            aria-label="Close"
            className="inline-flex h-8 w-8 cursor-pointer items-center justify-center rounded-md text-cold transition-colors duration-200 hover:bg-muted"
          >
            <X className="h-4 w-4" aria-hidden="true" />
          </button>
        </div>

        <div className="mt-5 flex justify-end gap-2">
          <button
            type="button"
            onClick={onCancel}
            disabled={busy}
            className="inline-flex h-10 cursor-pointer items-center justify-center rounded-md border border-border bg-surface px-4 text-sm font-medium text-fg transition-colors duration-200 hover:bg-muted disabled:opacity-50"
          >
            {cancelLabel}
          </button>
          <button
            ref={confirmRef}
            type="button"
            onClick={onConfirm}
            disabled={busy}
            className={[
              "inline-flex h-10 cursor-pointer items-center justify-center rounded-md px-4 text-sm font-semibold transition-colors duration-200 disabled:opacity-50",
              destructive
                ? "bg-destructive text-destructive-fg hover:opacity-90"
                : "bg-primary text-primary-fg hover:opacity-90",
            ].join(" ")}
          >
            {busy ? "Working…" : confirmLabel}
          </button>
        </div>
      </div>
    </div>
  );
}
