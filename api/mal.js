// /api/mal?user=<MyAnimeList username> -> {items: [{id: MAL id, score: 0-10, status}]}
// MAL's public list JSON has no CORS headers, so the browser can't fetch it directly.
// status: 1 watching, 2 completed, 3 on hold, 4 dropped, 6 plan to watch
module.exports = async (req, res) => {
  const user = String(req.query.user || '').trim();
  res.setHeader('Cache-Control', 'no-store');
  if (!/^[\w-]{2,16}$/.test(user)) return res.status(400).json({error: "That doesn't look like a MyAnimeList username."});
  const items = [];
  try {
    for (let offset = 0; offset < 6000; offset += 300) {
      const r = await fetch(`https://myanimelist.net/animelist/${user}/load.json?status=7&offset=${offset}`,
        {headers: {'User-Agent': 'Mozilla/5.0 (compatible; AniMatch; +https://animatch-pied.vercel.app)'}});
      if (r.status === 400 || r.status === 404)
        return res.status(404).json({error: 'List not found. Check the username and that the list is public.'});
      if (!r.ok) return res.status(502).json({error: `MyAnimeList answered ${r.status}. Try again in a minute.`});
      const page = await r.json();
      items.push(...page.map(a => ({id: a.anime_id, score: a.score, status: a.status})));
      if (page.length < 300) break;
    }
  } catch (e) {
    console.error('MAL fetch failed', e);
    return res.status(502).json({error: "Couldn't reach MyAnimeList. Try again in a minute."});
  }
  res.json({items});
};
