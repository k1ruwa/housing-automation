# Housing Automation — Project Context

This file is loaded automatically by Claude Code at the start of every session. It describes the project, the stack, and the conventions to follow. Keep it up to date as the project evolves.

## What this project does

A personal housing-search automation for the Dutch rental market (starting with Amsterdam). The goal is to be alerted to new listings within minutes of them being posted, and to speed up the application process with pre-drafted personalized messages.

**Core loop**:
1. A Python scraper polls configured sources every 3 hours, finds new listings, stores them in Postgres.
2. On insert of a new listing, a Telegram alert is sent with listing details and a link.
3. The Next.js dashboard shows all listings, lets the user draft a personalized message (Claude API), and track application status.
4. Messaging is copy-paste assisted for walled-garden sites (Pararius, Funda) and optionally auto-send for sites that expose real contact info.

**Explicitly out of scope for MVP**: auto-messaging on Pararius/Funda (contact forms block it, account risk), map view, preferred-area filtering. These are Phase 3.

## Architecture

Monorepo with two independently deployed services.

```
housing-automation/
├── frontend/          # Next.js 14 App Router, TypeScript, Tailwind — deploys to Vercel
├── scraper/           # Python 3.11, Playwright, APScheduler — deploys to Railway
├── shared/            # JSON schemas, shared types (generated), SQL migrations
├── .claude/           # Claude Code config (system prompt, settings)
├── CLAUDE.md          # This file
└── README.md          # Setup and deployment instructions
```

The two services never import each other. They communicate only through the Supabase database.

## Stack

**Frontend** (`/frontend`)
- Next.js 14 (App Router) + TypeScript
- Tailwind CSS + shadcn/ui components
- `@supabase/supabase-js` for DB reads
- `@anthropic-ai/sdk` for drafting messages (server-side API route only — never expose key client-side)
- Deployed: Vercel, watches `/frontend` only

**Scraper** (`/scraper`)
- Python 3.11
- Playwright for JS-heavy sites, `httpx` + `selectolax` for static HTML
- APScheduler for the 3-hour cadence (in-process, no separate cron service)
- `supabase-py` for DB writes
- `python-telegram-bot` for alerts
- Deployed: Railway as an always-on worker (no HTTP server needed)

**Data** (Supabase — free tier is plenty)
- Postgres + REST API + auth (auth not used yet, single-user app)
- Migrations live in `/shared/migrations/` as plain `.sql` files, applied via Supabase CLI

## Database schema

See `/shared/migrations/` for canonical definitions. High-level:

- `listings` — one row per unique listing found. Deduped by `(source, external_id)`. Fields: source, external_id, url, title, address, neighborhood, price_eur, size_m2, bedrooms, available_from, description, latitude, longitude, raw_html, first_seen_at, last_seen_at, is_active.
- `applications` — one row per application the user has made. FK to listings. Fields: listing_id, status (enum: drafted, sent, viewing_scheduled, rejected, accepted, withdrawn), message_sent, channel, sent_at, notes, updated_at.
- `profile` — single-row table with the user's intro info used for message drafting. Fields: full_name, age, occupation, income_eur, move_in_date, intro_text, preferences_json.
- `sources` — config table listing which sites are enabled, their URLs, scraping strategy, rate limits.

## Scraping rules

- **Never** scrape more often than configured per source. Default 3h. Respect `robots.txt` where it applies.
- Always set a realistic User-Agent, and randomize delays between requests within a run.
- Dedupe on `(source, external_id)` — extract external_id from the listing URL, never generate one client-side.
- If a site layout changes and selectors break, fail loudly (Telegram error alert), don't silently insert bad data.
- Store `raw_html` for the listing detail page on first scrape, so we can re-parse later without re-fetching.

## Messaging rules

- The user's profile info and intro text are in the `profile` table. Never hardcode them.
- Drafts are generated via a Next.js API route (`/api/draft-message`) that calls Claude. The key lives in Vercel env vars.
- For Pararius/Funda/Kamernet/HousingAnywhere: show the draft + a "Copy to clipboard" button only. Do NOT attempt auto-send.
- For sources where a real email address is extracted: show both "Copy" and "Send via email" (via Resend). Default UI choice is still Copy; auto-send is opt-in per listing.

## Environment variables

Each service has its own `.env.example`. Never commit real secrets.

Frontend needs:
- `NEXT_PUBLIC_SUPABASE_URL`, `NEXT_PUBLIC_SUPABASE_ANON_KEY`
- `ANTHROPIC_API_KEY` (server-side only)
- `RESEND_API_KEY` (when Phase 3 arrives)

Scraper needs:
- `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY` (service role — scraper writes)
- `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`
- `SCRAPE_INTERVAL_HOURS` (default 3)

## Conventions

- **Commits**: Conventional Commits (`feat:`, `fix:`, `chore:`, `docs:`). One logical change per commit.
- **Branches**: `main` is always deployable. Feature work on `feat/short-name` branches, PR into main.
- **Python**: `ruff` for lint + format, `mypy --strict` where feasible. Type hints everywhere.
- **TypeScript**: `strict: true` in tsconfig, no `any` unless justified in a comment. ESLint + Prettier.
- **Secrets**: Never commit. `.env` is gitignored, `.env.example` is committed with dummy values.

## Deployment

- Push to `main` → Vercel auto-deploys `/frontend`, Railway auto-deploys `/scraper`.
- Supabase migrations are applied manually via `supabase db push` after merging — never auto-applied on deploy.

## Current phase

**Phase 1 (MVP)**: Pararius-only scraper, Telegram alerts, dashboard showing listings, manual status tracking. No message drafting yet.

**Phase 2**: Add Kamernet + Funda. Add Claude-powered message drafting with copy button. Add Gmail-inbox hybrid scraping for sites that offer email alerts.

**Phase 3**: Map view (Leaflet + OpenStreetMap, not Google Maps). Preferred-area filtering with drawable polygons. Optional auto-send for listings with exposed emails.
