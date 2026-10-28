// Hands the browser the public Supabase URL and anon/publishable key.
// These are safe to expose: row-level security in schema.sql protects the data.
module.exports = (req, res) => {
  const env = process.env;
  res.setHeader('Cache-Control', 'public, max-age=300');
  res.json({
    url: env.SUPABASE_URL || env.NEXT_PUBLIC_SUPABASE_URL || null,
    key: env.SUPABASE_ANON_KEY || env.NEXT_PUBLIC_SUPABASE_ANON_KEY ||
         env.SUPABASE_PUBLISHABLE_KEY || env.NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY || null,
  });
};
