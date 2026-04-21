# Housing Automation

Personal automation for the Dutch rental market. Scrapes listings, alerts via Telegram, helps draft personalized applications.

See [`CLAUDE.md`](./CLAUDE.md) for architecture and conventions.

## First-time setup

### 1. Accounts to create (all free tier)
- [GitHub](https://github.com) — new empty repo `housing-automation`
- [Supabase](https://supabase.com) — new project, copy the URL + anon key + service role key
- [Vercel](https://vercel.com) — link to the GitHub repo, set root directory to `frontend`
- [Railway](https://railway.app) — link to the GitHub repo, set root directory to `scraper`
- [Telegram BotFather](https://t.me/botfather) — `/newbot`, copy the token
- [Anthropic Console](https://console.anthropic.com) — create API key (Phase 2)

### 2. Local dev

```bash
# Frontend
cd frontend
npm install
cp .env.example .env.local   # fill in Supabase + Anthropic keys
npm run dev

# Scraper (in a separate terminal)
cd scraper
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
playwright install chromium
cp .env.example .env         # fill in Supabase + Telegram keys
python -m scraper.main --once   # single run for testing
```

### 3. Database migrations

```bash
supabase link --project-ref <your-project-ref>
supabase db push   # applies everything in /shared/migrations
```

## Deployment

Push to `main`. Vercel redeploys the frontend, Railway redeploys the scraper. Supabase migrations are applied manually (see step 3 above).
