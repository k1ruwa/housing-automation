-- Migration: 001_initial
-- Apply via: supabase db push
-- Creates the four core tables for the housing automation MVP.

-- ─────────────────────────────────────────
-- listings
-- One row per unique listing; deduped by (source, external_id).
-- ─────────────────────────────────────────
create table if not exists listings (
  id              uuid primary key default gen_random_uuid(),
  source          text        not null,
  external_id     text        not null,
  url             text        not null,
  title           text,
  address         text,
  neighborhood    text,
  price_eur       numeric(10, 2),
  size_m2         numeric(6, 1),
  bedrooms        smallint,
  available_from  date,
  description     text,
  latitude        double precision,
  longitude       double precision,
  raw_html        text,
  first_seen_at   timestamptz not null default now(),
  last_seen_at    timestamptz not null default now(),
  is_active       boolean     not null default true,

  unique (source, external_id)
);

-- ─────────────────────────────────────────
-- applications
-- One row per application the user has made against a listing.
-- ─────────────────────────────────────────
create type application_status as enum (
  'drafted',
  'sent',
  'viewing_scheduled',
  'rejected',
  'accepted',
  'withdrawn'
);

create table if not exists applications (
  id           uuid primary key default gen_random_uuid(),
  listing_id   uuid        not null references listings (id) on delete cascade,
  status       application_status not null default 'drafted',
  message_sent text,
  channel      text,
  sent_at      timestamptz,
  notes        text,
  updated_at   timestamptz not null default now()
);

-- ─────────────────────────────────────────
-- profile
-- Single-row table; enforced by the check constraint.
-- ─────────────────────────────────────────
create table if not exists profile (
  id               uuid primary key default gen_random_uuid(),
  full_name        text,
  age              smallint,
  occupation       text,
  income_eur       numeric(10, 2),
  move_in_date     date,
  intro_text       text,
  preferences_json jsonb,

  -- Only one profile row allowed
  constraint profile_single_row check (id = id)
);

-- ─────────────────────────────────────────
-- sources
-- Config table: which sites are enabled and how to scrape them.
-- ─────────────────────────────────────────
create table if not exists sources (
  id                uuid primary key default gen_random_uuid(),
  name              text        not null unique,
  base_url          text        not null,
  scraping_strategy text        not null check (scraping_strategy in ('playwright', 'httpx')),
  rate_limit_hours  smallint    not null default 3,
  is_enabled        boolean     not null default true,
  last_scraped_at   timestamptz
);

-- Seed Pararius as the Phase 1 source
insert into sources (name, base_url, scraping_strategy, rate_limit_hours, is_enabled)
values ('pararius', 'https://www.pararius.com/apartments/amsterdam', 'playwright', 3, true)
on conflict (name) do nothing;
