-- 009_contacts_source_news.sql
-- Allow 'news' as a contact source (contacts extracted from news articles).
-- Idempotent.
do $$ begin
    if exists (select 1 from pg_constraint where conname = 'contacts_source_check') then
        alter table contacts drop constraint contacts_source_check;
    end if;
    alter table contacts add constraint contacts_source_check
        check (source is null or source in
            ('company_website','press_release','public_filing','enrichment_api','manual','news'));
end $$;
