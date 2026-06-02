import { useEffect, useState, useCallback } from "react";
import type { FormEvent } from "react";
import {
  X,
  Mail,
  Phone,
  User,
  Inbox,
  Building2,
  Lock,
  Link as LinkIcon,
  Linkedin,
  ShieldCheck,
  Ban,
  Loader2,
  AlertTriangle,
} from "lucide-react";
import type { Contact } from "../lib/types";

/**
 * Slide-over drawer that lists a project's contacts grouped by company.
 * - Distinguishes named_person from general_inbox / main_line.
 * - mailto:/tel: links for email/phone.
 * - Shows source provenance (source + source_url).
 * - If the contacts endpoint returns 401 (gated by CONTACTS_GATE_PASSWORD), shows
 *   a password field that re-requests with the X-Contacts-Key header.
 *
 * Talks to the documented endpoint GET /api/projects/{id}/contacts directly so the
 * 401 / gate flow is fully under this component's control (matches SPEC §4).
 */

const KIND_LABELS: Record<string, string> = {
  named_person: "Named Person",
  general_inbox: "General Inbox",
  main_line: "Main Line",
};

const SOURCE_LABELS: Record<string, string> = {
  company_website: "Company Website",
  press_release: "Press Release",
  public_filing: "Public Filing",
  enrichment_api: "Enrichment API",
  manual: "Manual",
};

function kindLabel(k: string): string {
  return KIND_LABELS[k] ?? k.replace(/_/g, " ");
}

function sourceLabel(s: string | null | undefined): string | null {
  if (!s) return null;
  return SOURCE_LABELS[s] ?? s.replace(/_/g, " ");
}

interface CompanyGroup {
  companyId: string | null;
  companyName: string;
  contacts: Contact[];
}

function groupByCompany(contacts: Contact[]): CompanyGroup[] {
  const map = new Map<string, CompanyGroup>();
  for (const c of contacts) {
    const key = c.company_id ?? c.company_name ?? "__unknown__";
    let g = map.get(key);
    if (!g) {
      g = {
        companyId: c.company_id ?? null,
        companyName: c.company_name || "Unknown company",
        contacts: [],
      };
      map.set(key, g);
    }
    g.contacts.push(c);
  }
  // named persons first within each company
  for (const g of map.values()) {
    g.contacts.sort((a, b) => {
      const an = a.contact_kind === "named_person" ? 0 : 1;
      const bn = b.contact_kind === "named_person" ? 0 : 1;
      return an - bn;
    });
  }
  return Array.from(map.values()).sort((a, b) => a.companyName.localeCompare(b.companyName));
}

function ContactRow({ contact }: { contact: Contact }) {
  const isPerson = contact.contact_kind === "named_person";
  const src = sourceLabel(contact.source);
  return (
    <li className="rounded-md border border-border bg-bg p-3">
      <div className="flex items-start gap-2">
        <span className="mt-0.5 text-secondary">
          {isPerson ? (
            <User className="h-4 w-4 shrink-0" aria-hidden="true" />
          ) : (
            <Inbox className="h-4 w-4 shrink-0" aria-hidden="true" />
          )}
        </span>
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
            <span className="truncate text-sm font-semibold text-fg">
              {contact.full_name || kindLabel(contact.contact_kind)}
            </span>
            <span className="rounded-full border border-border px-1.5 py-0.5 text-[10px] font-medium uppercase tracking-wide text-fg/60">
              {kindLabel(contact.contact_kind)}
            </span>
            {contact.verified ? (
              <span
                className="inline-flex items-center gap-1 text-[10px] font-medium text-hot"
                title="Verified"
              >
                <ShieldCheck className="h-3 w-3" aria-hidden="true" />
                Verified
              </span>
            ) : null}
            {contact.do_not_contact ? (
              <span
                className="inline-flex items-center gap-1 text-[10px] font-semibold text-destructive"
                title="Do not contact"
              >
                <Ban className="h-3 w-3" aria-hidden="true" />
                Do not contact
              </span>
            ) : null}
          </div>
          {contact.title ? (
            <p className="truncate text-xs text-fg/70">{contact.title}</p>
          ) : null}

          <div className="mt-1.5 flex flex-col gap-1">
            {contact.email ? (
              <a
                href={`mailto:${contact.email}`}
                className="num inline-flex w-fit cursor-pointer items-center gap-1.5 text-xs font-medium text-primary hover:underline"
              >
                <Mail className="h-3.5 w-3.5" aria-hidden="true" />
                {contact.email}
              </a>
            ) : null}
            {contact.phone ? (
              <a
                href={`tel:${contact.phone.replace(/[^+\d]/g, "")}`}
                className="num inline-flex w-fit cursor-pointer items-center gap-1.5 text-xs font-medium text-primary hover:underline"
              >
                <Phone className="h-3.5 w-3.5" aria-hidden="true" />
                {contact.phone}
              </a>
            ) : null}
            {contact.linkedin_url ? (
              <a
                href={contact.linkedin_url}
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex w-fit cursor-pointer items-center gap-1.5 text-xs font-medium text-primary hover:underline"
              >
                <Linkedin className="h-3.5 w-3.5" aria-hidden="true" />
                LinkedIn profile
              </a>
            ) : contact.full_name ? (
              <a
                href={`https://www.linkedin.com/search/results/people/?keywords=${encodeURIComponent(
                  [contact.full_name, contact.company_name].filter(Boolean).join(" "),
                )}`}
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex w-fit cursor-pointer items-center gap-1.5 text-xs font-medium text-fg/60 hover:text-primary hover:underline"
              >
                <Linkedin className="h-3.5 w-3.5" aria-hidden="true" />
                Find on LinkedIn
              </a>
            ) : null}
          </div>

          {src ? (
            <div className="mt-1.5 flex items-center gap-1 text-[10px] text-fg/70">
              <LinkIcon className="h-3 w-3" aria-hidden="true" />
              <span>Source: {src}</span>
              {contact.source_url ? (
                <a
                  href={contact.source_url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="cursor-pointer truncate text-secondary hover:underline"
                  title={contact.source_url}
                >
                  view
                </a>
              ) : null}
            </div>
          ) : null}
        </div>
      </div>
    </li>
  );
}

export function ContactsDrawer({
  projectId,
  projectTitle,
  open,
  onClose,
}: {
  projectId: string;
  projectTitle?: string;
  open: boolean;
  onClose: () => void;
}) {
  const [contacts, setContacts] = useState<Contact[] | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [gated, setGated] = useState(false);
  const [keyInput, setKeyInput] = useState("");
  const [submitting, setSubmitting] = useState(false);

  const load = useCallback(
    async (key?: string) => {
      setLoading(true);
      setError(null);
      try {
        const headers: Record<string, string> = { Accept: "application/json" };
        if (key) headers["X-Contacts-Key"] = key;
        const res = await fetch(`/api/projects/${encodeURIComponent(projectId)}/contacts`, {
          headers,
        });
        if (res.status === 401) {
          setGated(true);
          setContacts(null);
          if (key) setError("That password was not accepted. Try again.");
          return;
        }
        if (!res.ok) {
          throw new Error(`Request failed (${res.status})`);
        }
        const data = (await res.json()) as Contact[];
        setContacts(Array.isArray(data) ? data : []);
        setGated(false);
      } catch (e) {
        setError(e instanceof Error ? e.message : "Failed to load contacts.");
        setContacts(null);
      } finally {
        setLoading(false);
      }
    },
    [projectId]
  );

  // Load on open; reset on close.
  useEffect(() => {
    if (open) {
      setKeyInput("");
      void load();
    } else {
      setContacts(null);
      setGated(false);
      setError(null);
    }
  }, [open, load]);

  // Close on Escape.
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  const submitKey = async (e: FormEvent) => {
    e.preventDefault();
    if (!keyInput.trim()) return;
    setSubmitting(true);
    await load(keyInput.trim());
    setSubmitting(false);
  };

  if (!open) return null;

  const groups = contacts ? groupByCompany(contacts) : [];
  const totalContacts = contacts?.length ?? 0;

  return (
    <div className="fixed inset-0 z-50 flex justify-end" role="dialog" aria-modal="true" aria-label="Project contacts">
      {/* Backdrop */}
      <button
        type="button"
        aria-label="Close contacts"
        onClick={onClose}
        className="absolute inset-0 cursor-pointer bg-black/50 transition-opacity duration-200 motion-reduce:transition-none"
      />

      {/* Panel */}
      <aside className="relative flex h-full w-full max-w-md flex-col border-l border-border bg-surface shadow-xl">
        <header className="flex items-center justify-between gap-2 border-b border-border px-4 py-3">
          <div className="min-w-0">
            <h2 className="text-sm font-semibold text-fg">Contacts</h2>
            {projectTitle ? (
              <p className="truncate text-xs text-fg/60" title={projectTitle}>
                {projectTitle}
              </p>
            ) : null}
          </div>
          <button
            type="button"
            onClick={onClose}
            className="inline-flex h-9 w-9 cursor-pointer items-center justify-center rounded-md border border-border text-fg transition-colors duration-150 hover:bg-muted"
            aria-label="Close"
          >
            <X className="h-4 w-4" aria-hidden="true" />
          </button>
        </header>

        <div className="flex-1 overflow-y-auto px-4 py-3">
          {loading ? (
            <div className="flex items-center justify-center gap-2 py-12 text-sm text-fg/60">
              <Loader2 className="h-4 w-4 animate-spin motion-reduce:animate-none" aria-hidden="true" />
              Loading contacts…
            </div>
          ) : gated ? (
            <div className="rounded-lg border border-border bg-bg p-4">
              <div className="mb-2 flex items-center gap-2 text-sm font-semibold text-fg">
                <Lock className="h-4 w-4" aria-hidden="true" />
                Contacts are protected
              </div>
              <p className="mb-3 text-xs text-fg/70">
                Enter the access password to view contact details for this project.
              </p>
              <form onSubmit={submitKey} className="flex flex-col gap-2">
                <label htmlFor="contacts-key" className="sr-only">
                  Contacts password
                </label>
                <input
                  id="contacts-key"
                  type="password"
                  value={keyInput}
                  onChange={(e) => setKeyInput(e.target.value)}
                  autoFocus
                  placeholder="Password"
                  className="w-full rounded-md border border-border bg-surface px-3 py-2 text-sm text-fg outline-none focus:ring-2 focus:ring-ring"
                />
                {error ? (
                  <p className="flex items-center gap-1 text-xs text-destructive">
                    <AlertTriangle className="h-3.5 w-3.5" aria-hidden="true" />
                    {error}
                  </p>
                ) : null}
                <button
                  type="submit"
                  disabled={submitting || !keyInput.trim()}
                  className="inline-flex h-10 cursor-pointer items-center justify-center gap-2 rounded-md bg-primary px-4 text-sm font-semibold text-primary-fg transition-opacity duration-150 hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-50"
                >
                  {submitting ? (
                    <Loader2 className="h-4 w-4 animate-spin motion-reduce:animate-none" aria-hidden="true" />
                  ) : (
                    <Lock className="h-4 w-4" aria-hidden="true" />
                  )}
                  Unlock contacts
                </button>
              </form>
            </div>
          ) : error ? (
            <div className="flex flex-col items-center justify-center gap-2 py-12 text-center">
              <AlertTriangle className="h-6 w-6 text-destructive" aria-hidden="true" />
              <p className="text-sm font-medium text-fg">Could not load contacts</p>
              <p className="text-xs text-fg/60">{error}</p>
              <button
                type="button"
                onClick={() => void load()}
                className="mt-1 inline-flex h-9 cursor-pointer items-center justify-center rounded-md border border-border px-3 text-sm font-medium text-fg transition-colors duration-150 hover:bg-muted"
              >
                Retry
              </button>
            </div>
          ) : totalContacts === 0 ? (
            <div className="flex flex-col items-center justify-center gap-1 py-12 text-center">
              <Inbox className="h-6 w-6 text-fg/40" aria-hidden="true" />
              <p className="text-sm font-medium text-fg">No contacts yet</p>
              <p className="text-xs text-fg/60">
                Contacts will appear here once a team company has been identified and enriched.
              </p>
            </div>
          ) : (
            <div className="flex flex-col gap-4">
              {groups.map((g) => (
                <section key={g.companyId ?? g.companyName}>
                  <h3 className="mb-2 flex items-center gap-2 text-xs font-semibold uppercase tracking-wide text-fg/70">
                    <Building2 className="h-3.5 w-3.5" aria-hidden="true" />
                    {g.companyName}
                  </h3>
                  <ul className="flex flex-col gap-2">
                    {g.contacts.map((c) => (
                      <ContactRow key={c.id} contact={c} />
                    ))}
                  </ul>
                </section>
              ))}
            </div>
          )}
        </div>

        {!loading && !gated && totalContacts > 0 ? (
          <footer className="border-t border-border px-4 py-2 text-[11px] text-fg/70">
            AI drafts, humans decide. Always verify a contact before reaching out; do-not-contact flags
            are honored across the system.
          </footer>
        ) : null}
      </aside>
    </div>
  );
}

export default ContactsDrawer;
