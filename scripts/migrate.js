// Runs during the Vercel build: applies schema.sql (idempotent) to the Supabase database.
const fs = require('fs');
const path = require('path');
const {Client} = require('pg');

(async () => {
  const raw = process.env.POSTGRES_URL_NON_POOLING;
  if (!raw) { console.log('migrate: POSTGRES_URL_NON_POOLING not set, skipping'); return; }
  const url = new URL(raw);
  url.searchParams.delete('sslmode'); // Supabase's cert chain isn't in Node's store; TLS is still used below
  const db = new Client({connectionString: url.toString(), ssl: {rejectUnauthorized: false}});
  await db.connect();
  await db.query(fs.readFileSync(path.join(__dirname, '..', 'schema.sql'), 'utf8'));
  const {rows} = await db.query(`select count(*)::int as n from pg_policies where tablename = 'swipes'`);
  console.log(`migrate: schema applied, ${rows[0].n} row-level security policies on swipes`);
  await db.end();
})().catch(err => { console.error('migrate failed:', err.message); process.exit(1); });
