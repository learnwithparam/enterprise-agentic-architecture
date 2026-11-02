-- Documents, one row per case, content block, HCP or touch, owned by one tenant.
-- Row-level security is the isolation boundary: the app role sees only the tenant named in
-- app.tenant_id, and sees nothing when it is unset. FORCE applies it to the table owner too.

CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE tenants (
    id   text PRIMARY KEY,
    name text NOT NULL
);

CREATE TABLE docs (
    tenant_id  text        NOT NULL REFERENCES tenants (id),
    kind       text        NOT NULL,
    id         text        NOT NULL,
    doc        jsonb       NOT NULL,
    updated_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (tenant_id, kind, id)
);

ALTER TABLE docs ENABLE ROW LEVEL SECURITY;
ALTER TABLE docs FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON docs
    USING (tenant_id = current_setting('app.tenant_id', true))
    WITH CHECK (tenant_id = current_setting('app.tenant_id', true));

ALTER TABLE tenants ENABLE ROW LEVEL SECURITY;
ALTER TABLE tenants FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON tenants
    USING (id = current_setting('app.tenant_id', true));

DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'hcp_app') THEN
        CREATE ROLE hcp_app LOGIN NOSUPERUSER NOBYPASSRLS;
    END IF;
END $$;
GRANT SELECT ON tenants TO hcp_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON docs TO hcp_app;
