create table if not exists public.brody_users (
  id uuid primary key default gen_random_uuid(),
  username text not null unique,
  password_hash text not null,
  cash numeric(14, 2) not null default 10000,
  is_admin boolean not null default false,
  banned boolean not null default false,
  created_at timestamptz not null default now()
);

create table if not exists public.brody_stocks (
  id bigint generated always as identity primary key,
  symbol text not null unique,
  name text not null,
  sector text not null default 'Business',
  price numeric(12, 2) not null,
  last_close numeric(12, 2) not null,
  updated_at timestamptz not null default now()
);

create table if not exists public.brody_holdings (
  user_id uuid not null references public.brody_users(id) on delete cascade,
  stock_id bigint not null references public.brody_stocks(id) on delete cascade,
  shares numeric(14, 2) not null,
  avg_cost numeric(12, 2) not null,
  primary key (user_id, stock_id)
);

create table if not exists public.brody_trades (
  id bigint generated always as identity primary key,
  user_id uuid not null references public.brody_users(id) on delete cascade,
  stock_id bigint not null references public.brody_stocks(id) on delete cascade,
  side text not null check (side in ('buy', 'sell')),
  shares numeric(14, 2) not null,
  price numeric(12, 2) not null,
  created_at timestamptz not null default now()
);

create table if not exists public.brody_announcements (
  id bigint generated always as identity primary key,
  message text not null,
  created_at timestamptz not null default now()
);

create table if not exists public.brody_settings (
  key text primary key,
  value jsonb not null
);

create table if not exists public.brody_history_points (
  id bigint generated always as identity primary key,
  user_id uuid not null references public.brody_users(id) on delete cascade,
  value numeric(14, 2) not null,
  created_at timestamptz not null default now()
);

create index if not exists brody_trades_user_created_idx
  on public.brody_trades (user_id, created_at desc);

create index if not exists brody_history_user_created_idx
  on public.brody_history_points (user_id, created_at desc);

insert into public.brody_users (username, password_hash, cash, is_admin)
values ('jagan', 'TEMP_REPLACE_WITH_HASH', 10000, true)
on conflict (username) do nothing;
