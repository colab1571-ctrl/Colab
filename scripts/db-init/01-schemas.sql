-- =============================================================================
-- Colab Stage 2 — PostgreSQL init script
-- Creates per-service databases + required extensions
-- Runs once on first postgres container start (docker-entrypoint-initdb.d)
-- Image: pgvector/pgvector:pg16 (has pgvector, no PostGIS)
-- =============================================================================

-- Extensions in the default colab database
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pgcrypto";
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pg_trgm;
CREATE EXTENSION IF NOT EXISTS citext;
CREATE EXTENSION IF NOT EXISTS btree_gist;

-- ---------------------------------------------------------------------------
-- auth-svc database
-- ---------------------------------------------------------------------------
CREATE DATABASE auth_svc;
GRANT ALL PRIVILEGES ON DATABASE auth_svc TO colab;

\connect auth_svc
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- ---------------------------------------------------------------------------
-- profile-svc database (needs pgvector for embeddings + geo)
-- ---------------------------------------------------------------------------
\connect colab
CREATE DATABASE profile_svc;
GRANT ALL PRIVILEGES ON DATABASE profile_svc TO colab;

\connect profile_svc
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pgcrypto";
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pg_trgm;
CREATE EXTENSION IF NOT EXISTS citext;
CREATE EXTENSION IF NOT EXISTS btree_gist;

-- ---------------------------------------------------------------------------
-- discovery-svc database (needs pgvector for similarity search)
-- ---------------------------------------------------------------------------
\connect colab
CREATE DATABASE discovery_svc;
GRANT ALL PRIVILEGES ON DATABASE discovery_svc TO colab;

\connect discovery_svc
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pgcrypto";
CREATE EXTENSION IF NOT EXISTS vector;

-- ---------------------------------------------------------------------------
-- gateway-svc database (waitlist table only)
-- ---------------------------------------------------------------------------
\connect colab
CREATE DATABASE gateway_svc;
GRANT ALL PRIVILEGES ON DATABASE gateway_svc TO colab;

\connect gateway_svc
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Return to default db
\connect colab
SELECT 'Stage 2 DB init complete' AS status;
