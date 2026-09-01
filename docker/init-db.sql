-- Enable PostgreSQL extensions required by the CRM platform.
-- Runs automatically on first container start (docker-entrypoint-initdb.d).
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS pg_trgm;
CREATE EXTENSION IF NOT EXISTS unaccent;
CREATE EXTENSION IF NOT EXISTS vector;  -- pgvector, for future AI features
