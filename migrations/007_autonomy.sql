-- Which countries a tenant lets the platform send to without a reviewer, and on which topics (ADR 0026).
-- It was one SSM parameter per country, shared by every tenant. One tenant switching Germany off would have
-- switched it off for all of them, so it is a tenant row now, behind the same forced policy as every table.

CREATE TABLE autonomy (
    tenant_id  text        NOT NULL REFERENCES tenants (id),
    country    text        NOT NULL,
    enabled    boolean     NOT NULL,
    topics     jsonb       NOT NULL DEFAULT '[]',
    updated_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (tenant_id, country)
);

ALTER TABLE autonomy ENABLE ROW LEVEL SECURITY;
ALTER TABLE autonomy FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON autonomy
    USING (tenant_id = current_setting('app.tenant_id', true))
    WITH CHECK (tenant_id = current_setting('app.tenant_id', true));
GRANT SELECT, INSERT, UPDATE ON autonomy TO hcp_app;
