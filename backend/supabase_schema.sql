-- ChargeGrid schema. Run in the Supabase SQL Editor.
-- RLS is enabled on every table with NO policies: only the backend (secret key) can read or write.

create table if not exists vehicle_models (
  id text primary key, label text not null,
  battery_kwh numeric not null, max_ac_kw numeric not null, max_dc_kw numeric not null,
  ac_connector text not null, dc_connector text not null, wh_per_km numeric not null);

create table if not exists users (
  id uuid primary key, name text not null, pin_hash text not null,
  vehicle_model_id text not null references vehicle_models(id),
  soc numeric not null check (soc between 0 and 100),
  lat double precision not null, lng double precision not null,
  wallet_balance numeric not null default 1000,
  created_at timestamptz not null default now());
create unique index if not exists users_name_lower_key on users (lower(name));

create table if not exists stations (
  id text primary key, name text not null, lat double precision not null, lng double precision not null,
  power_cap_kw numeric not null);

create table if not exists chargers (
  id text primary key, station_id text not null references stations(id), number int not null,
  kind text not null check (kind in ('AC','DC')), connector text not null,
  max_kw numeric not null, price_per_kwh numeric not null);

create table if not exists reservations (
  id uuid primary key, user_id uuid not null references users(id), charger_id text not null references chargers(id),
  status text not null check (status in ('active','used','expired','cancelled')),
  created_at timestamptz not null default now(), expires_at timestamptz not null);

create table if not exists charging_sessions (
  id uuid primary key, user_id uuid not null references users(id), charger_id text not null references chargers(id),
  station_id text not null, vehicle_model_id text not null,
  start_soc numeric, end_soc numeric, target_soc numeric, spending_cap numeric,
  energy_kwh numeric not null default 0, energy_cost numeric not null default 0,
  idle_minutes numeric not null default 0, idle_fee numeric not null default 0,
  status text not null check (status in ('active','completed','aborted')), end_reason text,
  sim_started text, sim_ended text, started_at timestamptz not null default now(), ended_at timestamptz);

create table if not exists invoices (
  id uuid primary key, number text not null unique,
  session_id uuid not null unique references charging_sessions(id), user_id uuid not null references users(id),
  energy_kwh numeric not null, energy_amount numeric not null, idle_fee numeric not null default 0,
  tax_percent numeric not null, tax_amount numeric not null, total numeric not null,
  status text not null check (status in ('paid','unpaid')),
  created_at timestamptz not null default now(), paid_at timestamptz,
  lines jsonb not null default '[]'::jsonb);  -- itemised energy lines (added to the spec so old invoices re-render exactly)

create table if not exists wallet_transactions (
  id bigint generated always as identity primary key, user_id uuid not null references users(id),
  kind text not null check (kind in ('topup','payment')), amount numeric not null, balance_after numeric not null,
  invoice_id uuid null references invoices(id), created_at timestamptz not null default now());

create index if not exists idx_sessions_user on charging_sessions(user_id);
create index if not exists idx_invoices_user on invoices(user_id);
create index if not exists idx_txs_user on wallet_transactions(user_id);

alter table vehicle_models enable row level security;
alter table users enable row level security;
alter table stations enable row level security;
alter table chargers enable row level security;
alter table reservations enable row level security;
alter table charging_sessions enable row level security;
alter table invoices enable row level security;
alter table wallet_transactions enable row level security;
