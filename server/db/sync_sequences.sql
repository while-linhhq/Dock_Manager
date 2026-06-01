-- Sync all public.*_id_seq counters after SQL dump restore (Navicat omits setval).
-- Usage: docker compose exec -T db psql -U postgres -d demo_db -f - < db/sync_sequences.sql
-- Or from server/: psql "$DATABASE_URL" -f db/sync_sequences.sql

DO $$
DECLARE
  r RECORD;
  seq_name text;
  max_id bigint;
BEGIN
  FOR r IN
    SELECT c.table_name
    FROM information_schema.columns c
    WHERE c.table_schema = 'public'
      AND c.column_name = 'id'
    ORDER BY c.table_name
  LOOP
    seq_name := r.table_name || '_id_seq';

    IF to_regclass('public.' || quote_ident(seq_name)) IS NULL THEN
      RAISE NOTICE 'skip %: sequence % not found', r.table_name, seq_name;
      CONTINUE;
    END IF;

    EXECUTE format('SELECT COALESCE(MAX(id), 0) FROM %I.%I', 'public', r.table_name) INTO max_id;

    IF max_id > 0 THEN
      EXECUTE format('SELECT setval(%L::regclass, %s)', 'public.' || seq_name, max_id);
      RAISE NOTICE '%: setval(%) -> next id %', r.table_name, max_id, max_id + 1;
    ELSE
      EXECUTE format('SELECT setval(%L::regclass, 1, false)', 'public.' || seq_name);
      RAISE NOTICE '%: empty table, next id 1', r.table_name;
    END IF;

    EXECUTE format(
      'ALTER SEQUENCE %I.%I OWNED BY %I.%I.id',
      'public', seq_name, 'public', r.table_name
    );
  END LOOP;
END $$;
