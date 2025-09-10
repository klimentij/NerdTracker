-- Compatibility for self-hosted PostgreSQL
DO $$
BEGIN
CREATE ROLE anon LOGIN NOINHERIT;
EXCEPTION WHEN duplicate_object THEN RAISE NOTICE '%, skipping', SQLERRM USING ERRCODE = SQLSTATE;
END
$$;
