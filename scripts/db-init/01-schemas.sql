-- =============================================================================
-- Colab Dev DB Bootstrap
-- Runs on first Postgres start via Docker volume mount
-- =============================================================================

-- Extensions (pgvector image ships these; citext/pg_trgm are contrib)
CREATE EXTENSION IF NOT EXISTS postgis;
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS citext;
CREATE EXTENSION IF NOT EXISTS pg_trgm;
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Per-service schemas (all in shared colab_dev DB for demo convenience)
CREATE SCHEMA IF NOT EXISTS auth;
CREATE SCHEMA IF NOT EXISTS profile;
CREATE SCHEMA IF NOT EXISTS discovery;
CREATE SCHEMA IF NOT EXISTS chat;
CREATE SCHEMA IF NOT EXISTS gateway;

-- Grant the app user full access to all schemas
DO $$
BEGIN
  IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = 'colab') THEN
    CREATE ROLE colab WITH LOGIN PASSWORD 'colab';
  END IF;
END
$$;

GRANT ALL PRIVILEGES ON DATABASE colab_dev TO colab;
GRANT ALL ON SCHEMA auth, profile, discovery, chat, gateway TO colab;
ALTER DEFAULT PRIVILEGES IN SCHEMA auth, profile, discovery, chat, gateway
  GRANT ALL ON TABLES TO colab;
ALTER DEFAULT PRIVILEGES IN SCHEMA auth, profile, discovery, chat, gateway
  GRANT ALL ON SEQUENCES TO colab;
