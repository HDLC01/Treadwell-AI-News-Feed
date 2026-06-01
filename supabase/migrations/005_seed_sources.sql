-- 005_seed_sources.sql
-- Seed the v1 Tier-1 + light-scrape sources (config-as-data). Idempotent on url.
-- First add a unique constraint on sources.url so re-running this file is a no-op.

do $$ begin
    if not exists (select 1 from pg_constraint where conname = 'sources_url_key') then
        alter table sources add constraint sources_url_key unique (url);
    end if;
end $$;

-- ─── Google News RSS queries (tier 1, rss_generic) ───────────────────────
insert into sources (name, source_type, url, fetch_method, parser_key, region_scope, tier, enabled)
values
  ('Google News - data center Kansas City', 'news',
   'https://news.google.com/rss/search?q=%22data%20center%22%20%22Kansas%20City%22&hl=en-US&gl=US&ceid=US:en',
   'rss', 'rss_generic', 'kc_metro', 1, true),
  ('Google News - data center Missouri', 'news',
   'https://news.google.com/rss/search?q=%22data%20center%22%20Missouri&hl=en-US&gl=US&ceid=US:en',
   'rss', 'rss_generic', '350mi_ring', 1, true),
  ('Google News - data center Kansas', 'news',
   'https://news.google.com/rss/search?q=%22data%20center%22%20Kansas&hl=en-US&gl=US&ceid=US:en',
   'rss', 'rss_generic', '350mi_ring', 1, true),
  ('Google News - data center Omaha', 'news',
   'https://news.google.com/rss/search?q=%22data%20center%22%20Omaha&hl=en-US&gl=US&ceid=US:en',
   'rss', 'rss_generic', '350mi_ring', 1, true),
  ('Google News - data center Des Moines', 'news',
   'https://news.google.com/rss/search?q=%22data%20center%22%20%22Des%20Moines%22&hl=en-US&gl=US&ceid=US:en',
   'rss', 'rss_generic', '350mi_ring', 1, true),
  ('Google News - data center St. Louis', 'news',
   'https://news.google.com/rss/search?q=%22data%20center%22%20%22St.%20Louis%22&hl=en-US&gl=US&ceid=US:en',
   'rss', 'rss_generic', '350mi_ring', 1, true),
  ('Google News - data center Nebraska', 'news',
   'https://news.google.com/rss/search?q=%22data%20center%22%20Nebraska&hl=en-US&gl=US&ceid=US:en',
   'rss', 'rss_generic', '350mi_ring', 1, true),
  ('Google News - data center Iowa', 'news',
   'https://news.google.com/rss/search?q=%22data%20center%22%20Iowa&hl=en-US&gl=US&ceid=US:en',
   'rss', 'rss_generic', '350mi_ring', 1, true),
  ('Google News - hyperscale data center Midwest', 'news',
   'https://news.google.com/rss/search?q=%22hyperscale%22%20%22data%20center%22%20Midwest&hl=en-US&gl=US&ceid=US:en',
   'rss', 'rss_generic', '350mi_ring', 1, true),
  ('Google News - distribution center Kansas City', 'news',
   'https://news.google.com/rss/search?q=%22distribution%20center%22%20%22Kansas%20City%22&hl=en-US&gl=US&ceid=US:en',
   'rss', 'rss_generic', 'kc_metro', 1, true),
  ('Google News - manufacturing plant Kansas City', 'news',
   'https://news.google.com/rss/search?q=%22manufacturing%20plant%22%20%22Kansas%20City%22&hl=en-US&gl=US&ceid=US:en',
   'rss', 'rss_generic', 'kc_metro', 1, true),
  ('Google News - hospital construction Kansas City', 'news',
   'https://news.google.com/rss/search?q=%22hospital%22%20construction%20%22Kansas%20City%22&hl=en-US&gl=US&ceid=US:en',
   'rss', 'rss_generic', 'kc_metro', 1, true),
  ('Google News - warehouse construction Kansas City', 'news',
   'https://news.google.com/rss/search?q=%22warehouse%22%20construction%20%22Kansas%20City%22&hl=en-US&gl=US&ceid=US:en',
   'rss', 'rss_generic', 'kc_metro', 1, true)
on conflict (url) do nothing;

-- ─── Industry / trade RSS (tier 1, rss_generic) ──────────────────────────
insert into sources (name, source_type, url, fetch_method, parser_key, region_scope, tier, enabled)
values
  ('Data Center Dynamics', 'news',
   'https://www.datacenterdynamics.com/en/rss/',
   'rss', 'rss_generic', '350mi_ring', 1, true),
  ('Data Center Frontier', 'news',
   'https://www.datacenterfrontier.com/rss',
   'rss', 'rss_generic', '350mi_ring', 1, true),
  ('Kansas City Business Journal', 'news',
   'https://www.bizjournals.com/kansascity/news/rss.xml',
   'rss', 'rss_generic', 'kc_metro', 1, true)
on conflict (url) do nothing;

-- ─── Light HTML scrape targets (tier 2, html_generic, best-effort) ───────
-- KC-metro economic-development news/press index pages. The html_generic parser
-- pulls article links + visible text; if a page changes layout it simply yields
-- nothing for that run (one dead source never kills the pipeline). No fabricated
-- permit-portal URLs are seeded here.
insert into sources (name, source_type, url, fetch_method, parser_key, region_scope, tier, enabled)
values
  ('KCADC News (Kansas City Area Development Council)', 'press_release',
   'https://www.thinkkc.com/news/',
   'html', 'html_generic', 'kc_metro', 2, true),
  ('Olathe Economic Development News', 'press_release',
   'https://www.olatheks.org/business/economic-development',
   'html', 'html_generic', 'kc_metro', 2, true)
on conflict (url) do nothing;
