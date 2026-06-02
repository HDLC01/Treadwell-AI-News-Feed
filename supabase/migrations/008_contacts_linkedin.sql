-- 008_contacts_linkedin.sql
-- Contact enrichment: store a LinkedIn profile/company URL when one is found on a
-- company's own website (we never scrape LinkedIn itself). Idempotent.

alter table contacts add column if not exists linkedin_url text;

-- Helps the enricher dedupe contacts per project by email.
create index if not exists contacts_project_email_idx on contacts (project_id, email);
