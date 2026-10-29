-- One row per eval run, tagged with the release it measured (ADR 0025). A release is a hash of everything that
-- decides behaviour, so the same manifest is the same release. At most one run per tenant is the baseline:
-- the run a later release has to match or beat. Rows are never deleted, so the history shows every release.

CREATE TABLE eval_runs (
    tenant_id   text        NOT NULL REFERENCES tenants (id),
    id          bigserial,
    release     text        NOT NULL,
    manifest    jsonb       NOT NULL,
    metrics     jsonb       NOT NULL,
    passed      boolean     NOT NULL,
    regressions jsonb       NOT NULL DEFAULT '[]',
    baseline    boolean     NOT NULL DEFAULT false,
    at          timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (tenant_id, id)
);

ALTER TABLE eval_runs ENABLE ROW LEVEL SECURITY;
ALTER TABLE eval_runs FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON eval_runs
    USING (tenant_id = current_setting('app.tenant_id', true))
    WITH CHECK (tenant_id = current_setting('app.tenant_id', true));
GRANT SELECT, INSERT, UPDATE ON eval_runs TO hcp_app;
GRANT USAGE ON SEQUENCE eval_runs_id_seq TO hcp_app;
