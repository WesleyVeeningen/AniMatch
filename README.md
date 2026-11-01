# AniMatch

Swipe through anime like a dating app and get recommendations that learn from every swipe. Like, super-like or pass on a title, and AniMatch ranks the rest of the catalogue by how well it fits your taste, with a short "why" for each pick. You can also start a watch party: everyone swipes the same deck, and anything the whole group likes becomes a match.

**Live:** [animatch-pied.vercel.app](https://animatch-pied.vercel.app)

## Features

- **Swipe deck** of up to 1,500 popular titles from AniList, with sequels filtered out so you only see where a series starts
- **Hybrid recommendations**: collaborative filtering learned from 26M ratings, with a genre and tag profile for titles too new for that data. Picks explain themselves ("Because you liked Bleach"), and part of the deck keeps exploring popular titles. [How it was built and measured](ml/README.md)
- **Import your list** from AniList or MyAnimeList, so shows you already watched count as swipes
- **Undo** and a **matches** view of everything you liked
- **Accounts are optional.** Guests keep their swipes in the browser; sign in and they're saved to your account (and carried over from guest mode)
- **Watch parties** with a short join code. Guests can join without an account

## Stack

- Plain HTML, CSS and JavaScript (single page in `public/index.html`), no framework or build step
- [AniList GraphQL API](https://anilist.co/graphiql) for anime data
- [Supabase](https://supabase.com) for auth and Postgres, with row-level security so users only see their own swipes
- Vercel serverless functions in `api/`
- Python (NumPy, SciPy, pandas) for training and offline evaluation in `ml/`

## Project layout

```
public/index.html   the whole app: UI and swipe deck
public/recommender.js   hybrid scoring, runs in the browser
public/cf-model.json    trained item-item links (built by ml/export.py)
ml/                 training, offline evaluation and results
api/config.js       hands the browser the public Supabase URL and key
api/mal.js          proxies MyAnimeList lists (MAL has no CORS headers)
api/party.js        watch parties: create, join, swipe, leave
schema.sql          tables and row-level security policies
scripts/migrate.js  applies schema.sql during the Vercel build
```

## Running it

The easiest way is to deploy it to Vercel with a Supabase project connected. These environment variables are used:

| Variable | Used by |
| --- | --- |
| `SUPABASE_URL` | browser (via `/api/config`) and `/api/party` |
| `SUPABASE_ANON_KEY` or `SUPABASE_PUBLISHABLE_KEY` | browser sign-in and swipe sync |
| `SUPABASE_SERVICE_ROLE_KEY` or `SUPABASE_SECRET_KEY` | `/api/party` (server only) |
| `POSTGRES_URL_NON_POOLING` | `npm run build`, which applies `schema.sql` |

The Vercel Supabase integration sets these for you (the `NEXT_PUBLIC_` variants work too). Every deploy runs `npm run build`, which applies `schema.sql`. It's safe to run more than once.

To run locally with the API routes:

```bash
npm install
vercel dev
```

Or serve `public/` with any static server (for example `npx serve public`). Without the API it runs in guest mode only: swiping and recommendations work, accounts, MAL import and watch parties don't.
