-- 006_broaden_sources.sql
-- Broaden beyond data centers to Treadwell's full commercial-flooring customer base.
-- Idempotent on sources.url (unique constraint added in 005).

insert into sources (name, source_type, url, fetch_method, parser_key, region_scope, tier, enabled)
values
  ('Google News - commercial construction KC', 'news', 'https://news.google.com/rss/search?q=%22commercial%20construction%22%20%22Kansas%20City%22&hl=en-US&gl=US&ceid=US:en', 'rss', 'rss_generic', 'kc_metro', 1, true),
  ('Google News - groundbreaking KC', 'news', 'https://news.google.com/rss/search?q=groundbreaking%20%22Kansas%20City%22&hl=en-US&gl=US&ceid=US:en', 'rss', 'rss_generic', 'kc_metro', 1, true),
  ('Google News - new development KC', 'news', 'https://news.google.com/rss/search?q=%22new%20development%22%20%22Kansas%20City%22&hl=en-US&gl=US&ceid=US:en', 'rss', 'rss_generic', 'kc_metro', 1, true),
  ('Google News - industrial development KC', 'news', 'https://news.google.com/rss/search?q=%22industrial%20development%22%20%22Kansas%20City%22&hl=en-US&gl=US&ceid=US:en', 'rss', 'rss_generic', 'kc_metro', 1, true),
  ('Google News - warehouse or distribution KC', 'news', 'https://news.google.com/rss/search?q=%28%22warehouse%22%20OR%20%22distribution%20center%22%29%20%22Kansas%20City%22&hl=en-US&gl=US&ceid=US:en', 'rss', 'rss_generic', 'kc_metro', 1, true),
  ('Google News - fulfillment or logistics center KC', 'news', 'https://news.google.com/rss/search?q=%28%22fulfillment%20center%22%20OR%20%22logistics%20center%22%29%20%22Kansas%20City%22&hl=en-US&gl=US&ceid=US:en', 'rss', 'rss_generic', 'kc_metro', 1, true),
  ('Google News - manufacturing facility KC', 'news', 'https://news.google.com/rss/search?q=%22manufacturing%20facility%22%20%22Kansas%20City%22&hl=en-US&gl=US&ceid=US:en', 'rss', 'rss_generic', 'kc_metro', 1, true),
  ('Google News - food processing plant KC', 'news', 'https://news.google.com/rss/search?q=%28%22food%20processing%22%20OR%20%22processing%20plant%22%29%20%22Kansas%20City%22&hl=en-US&gl=US&ceid=US:en', 'rss', 'rss_generic', 'kc_metro', 1, true),
  ('Google News - cold storage KC', 'news', 'https://news.google.com/rss/search?q=%22cold%20storage%22%20%22Kansas%20City%22&hl=en-US&gl=US&ceid=US:en', 'rss', 'rss_generic', 'kc_metro', 1, true),
  ('Google News - battery or EV plant KS/MO', 'news', 'https://news.google.com/rss/search?q=%28%22battery%20plant%22%20OR%20%22EV%20plant%22%20OR%20%22gigafactory%22%29%20%28Kansas%20OR%20Missouri%29&hl=en-US&gl=US&ceid=US:en', 'rss', 'rss_generic', 'regional', 1, true),
  ('Google News - hospital or medical center KC', 'news', 'https://news.google.com/rss/search?q=%28%22hospital%22%20OR%20%22medical%20center%22%29%20%28construction%20OR%20expansion%29%20%22Kansas%20City%22&hl=en-US&gl=US&ceid=US:en', 'rss', 'rss_generic', 'kc_metro', 1, true),
  ('Google News - university or college construction KC', 'news', 'https://news.google.com/rss/search?q=%28%22university%22%20OR%20%22college%22%29%20construction%20%22Kansas%20City%22&hl=en-US&gl=US&ceid=US:en', 'rss', 'rss_generic', 'kc_metro', 1, true),
  ('Google News - new school Johnson County KS', 'news', 'https://news.google.com/rss/search?q=%22new%20school%22%20%28construction%20OR%20bond%29%20%22Johnson%20County%22&hl=en-US&gl=US&ceid=US:en', 'rss', 'rss_generic', 'kc_metro', 1, true),
  ('Google News - auto dealership KC', 'news', 'https://news.google.com/rss/search?q=%28%22auto%20dealership%22%20OR%20%22car%20dealership%22%29%20%22Kansas%20City%22&hl=en-US&gl=US&ceid=US:en', 'rss', 'rss_generic', 'kc_metro', 1, true),
  ('Google News - grocery or supermarket KC', 'news', 'https://news.google.com/rss/search?q=%28%22grocery%20store%22%20OR%20%22supermarket%22%29%20%22Kansas%20City%22&hl=en-US&gl=US&ceid=US:en', 'rss', 'rss_generic', 'kc_metro', 1, true),
  ('Google News - brewery or distillery KC', 'news', 'https://news.google.com/rss/search?q=%28%22brewery%22%20OR%20%22distillery%22%29%20%22Kansas%20City%22&hl=en-US&gl=US&ceid=US:en', 'rss', 'rss_generic', 'kc_metro', 1, true),
  ('Google News - aviation or hangar KC', 'news', 'https://news.google.com/rss/search?q=%28%22hangar%22%20OR%20%22aviation%20facility%22%29%20%22Kansas%20City%22&hl=en-US&gl=US&ceid=US:en', 'rss', 'rss_generic', 'kc_metro', 1, true),
  ('Google News - mixed-use development KC', 'news', 'https://news.google.com/rss/search?q=%22mixed-use%22%20development%20%22Kansas%20City%22&hl=en-US&gl=US&ceid=US:en', 'rss', 'rss_generic', 'kc_metro', 1, true)
on conflict (url) do nothing;
