// Watch parties: everyone swipes the same deck; anime that every member liked is a match.
// GET  /api/party?code=ABCDE                      -> party state
// POST /api/party {op:'create', member, name, deck}  -> state (new code)
// POST /api/party {op:'join',   code, member, name}  -> state
// POST /api/party {op:'swipe',  code, member, anime, action}
// POST /api/party {op:'leave',  code, member}
// Members are random per-browser ids, so guests can join without an account.
const crypto = require('crypto');

const BASE = (process.env.SUPABASE_URL || process.env.NEXT_PUBLIC_SUPABASE_URL) + '/rest/v1/';
const KEY = process.env.SUPABASE_SERVICE_ROLE_KEY || process.env.SUPABASE_SECRET_KEY;
const ALPHABET = 'ABCDEFGHJKLMNPQRSTUVWXYZ23456789'; // no 0/O or 1/I

async function db(path, {method = 'GET', body, prefer} = {}) {
  const headers = {apikey: KEY, 'Content-Type': 'application/json'};
  if (KEY.startsWith('eyJ')) headers.Authorization = `Bearer ${KEY}`; // legacy JWT keys
  if (prefer) headers.Prefer = prefer;
  const r = await fetch(BASE + path, {method, headers, body: body && JSON.stringify(body)});
  const text = await r.text();
  if (!r.ok) throw Object.assign(new Error(text), {status: r.status});
  return text ? JSON.parse(text) : null;
}

async function state(code) {
  const [party] = await db(`parties?code=eq.${code}&select=code,deck`);
  if (!party) return null;
  const [members, swipes] = await Promise.all([
    db(`party_members?code=eq.${code}&select=member,name&order=joined_at`),
    db(`party_swipes?code=eq.${code}&select=member,anime_id,action`),
  ]);
  return {code, deck: party.deck, members, swipes};
}

const fail = (res, status, error) => res.status(status).json({error});
const isUuid = s => /^[0-9a-f-]{36}$/i.test(s || '');
const cleanName = s => String(s || '').trim().slice(0, 24);

module.exports = async (req, res) => {
  res.setHeader('Cache-Control', 'no-store');
  try {
    if (req.method === 'GET') {
      const code = String(req.query.code || '').toUpperCase();
      if (!/^[A-Z0-9]{5}$/.test(code)) return fail(res, 400, 'Party codes are 5 characters.');
      const s = await state(code);
      return s ? res.json(s) : fail(res, 404, 'No party with that code.');
    }
    if (req.method !== 'POST') return fail(res, 405, 'Use GET or POST.');

    let b;
    try { b = req.body || {}; } catch { return fail(res, 400, 'Request body must be JSON.'); }
    const code = String(b.code || '').toUpperCase();
    if (!isUuid(b.member)) return fail(res, 400, 'Missing member id.');

    if (b.op === 'create') {
      const name = cleanName(b.name);
      const deck = Array.isArray(b.deck) ? b.deck.filter(Number.isInteger).slice(0, 100) : [];
      if (!name) return fail(res, 400, 'Enter your name.');
      if (deck.length < 5) return fail(res, 400, 'Not enough anime loaded yet. Try again in a second.');
      for (let tries = 0; tries < 5; tries++) {
        const newCode = Array.from(crypto.randomBytes(5), x => ALPHABET[x % ALPHABET.length]).join('');
        try { await db('parties', {method: 'POST', body: {code: newCode, deck}}); }
        catch (e) { if (e.status === 409) continue; throw e; }
        await db('party_members', {method: 'POST', body: {code: newCode, member: b.member, name}});
        return res.json(await state(newCode));
      }
      return fail(res, 500, 'Could not create a party code. Try again.');
    }

    if (!/^[A-Z0-9]{5}$/.test(code)) return fail(res, 400, 'Party codes are 5 characters.');

    if (b.op === 'join') {
      const name = cleanName(b.name);
      if (!name) return fail(res, 400, 'Enter your name.');
      const [party] = await db(`parties?code=eq.${code}&select=code`);
      if (!party) return fail(res, 404, 'No party with that code.');
      await db('party_members?on_conflict=code,member', {method: 'POST', body: {code, member: b.member, name},
        prefer: 'resolution=merge-duplicates'});
      return res.json(await state(code));
    }
    if (b.op === 'swipe') {
      if (!Number.isInteger(b.anime) || !['like', 'super', 'nope'].includes(b.action)) return fail(res, 400, 'Bad swipe.');
      await db('party_swipes?on_conflict=code,member,anime_id', {method: 'POST',
        body: {code, member: b.member, anime_id: b.anime, action: b.action}, prefer: 'resolution=merge-duplicates'});
      return res.json({ok: true});
    }
    if (b.op === 'leave') {
      await db(`party_members?code=eq.${code}&member=eq.${b.member}`, {method: 'DELETE'});
      return res.json({ok: true});
    }
    return fail(res, 400, 'Unknown op.');
  } catch (e) {
    console.error('party error', e.status, e.message);
    // a swipe from someone who isn't (or is no longer) a member breaks the foreign key
    if (e.status === 409 || e.status === 400) return fail(res, 409, 'You are not in this party any more. Join again.');
    return fail(res, 500, 'Party server error. Try again.');
  }
};
