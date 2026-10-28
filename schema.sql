-- AniMatch: one row per (user, anime) swipe. Accounts live in Supabase Auth (auth.users).
create table if not exists public.swipes (
  user_id    uuid not null default auth.uid() references auth.users on delete cascade,
  anime_id   integer not null,
  action     text not null constraint swipes_action_check check (action in ('like', 'super', 'nope', 'seen')),
  feats      jsonb not null default '{}',
  title      text,
  cover      text,
  seq        bigint generated always as identity,
  created_at timestamptz not null default now(),
  primary key (user_id, anime_id)
);

-- 'seen' = imported from an AniList/MAL list as watched but rated middling
alter table public.swipes drop constraint if exists swipes_action_check;
alter table public.swipes add constraint swipes_action_check check (action in ('like', 'super', 'nope', 'seen'));

alter table public.swipes enable row level security;

-- Each user can only see and change their own swipes.
drop policy if exists "own swipes: select" on public.swipes;
drop policy if exists "own swipes: insert" on public.swipes;
drop policy if exists "own swipes: update" on public.swipes;
drop policy if exists "own swipes: delete" on public.swipes;
create policy "own swipes: select" on public.swipes for select to authenticated using (auth.uid() = user_id);
create policy "own swipes: insert" on public.swipes for insert to authenticated with check (auth.uid() = user_id);
create policy "own swipes: update" on public.swipes for update to authenticated using (auth.uid() = user_id) with check (auth.uid() = user_id);
create policy "own swipes: delete" on public.swipes for delete to authenticated using (auth.uid() = user_id);

grant select, insert, update, delete on public.swipes to authenticated;

-- Watch parties. Guests can join without an account, so these tables are only
-- reached through /api/party (service role); RLS with no policies blocks direct access.
create table if not exists public.parties (
  code       text primary key,
  deck       integer[] not null,
  created_at timestamptz not null default now()
);
create table if not exists public.party_members (
  code      text not null references public.parties on delete cascade,
  member    uuid not null,
  name      text not null,
  joined_at timestamptz not null default now(),
  primary key (code, member)
);
create table if not exists public.party_swipes (
  code     text not null,
  member   uuid not null,
  anime_id integer not null,
  action   text not null check (action in ('like', 'super', 'nope')),
  primary key (code, member, anime_id),
  foreign key (code, member) references public.party_members on delete cascade
);
alter table public.parties enable row level security;
alter table public.party_members enable row level security;
alter table public.party_swipes enable row level security;

notify pgrst, 'reload schema';
