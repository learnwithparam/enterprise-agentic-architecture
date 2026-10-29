-- The AI gateway's two tables (ADR 0019). A virtual key is what an agent holds instead of the provider
-- key: it names a tenant and an agent and carries a budget. Only the hash is stored. The spend log has
-- one row per model call, tagged so cost can be split by agent, release and prompt version.

CREATE TABLE virtual_keys (
    tenant_id  text        NOT NULL REFERENCES tenants (id),
    key_hash   text        NOT NULL,
    agent      text        NOT NULL,
    budget_usd numeric     NOT NULL,
    revoked    boolean     NOT NULL DEFAULT false,
    created_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (tenant_id, key_hash)
);

ALTER TABLE virtual_keys ENABLE ROW LEVEL SECURITY;
ALTER TABLE virtual_keys FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON virtual_keys
    USING (tenant_id = current_setting('app.tenant_id', true))
    WITH CHECK (tenant_id = current_setting('app.tenant_id', true));
GRANT SELECT, INSERT, UPDATE ON virtual_keys TO hcp_app;

CREATE TABLE spend_log (
    id             bigserial   PRIMARY KEY,
    tenant_id      text        NOT NULL REFERENCES tenants (id),
    key_hash       text        NOT NULL,
    agent          text        NOT NULL,
    release        text        NOT NULL,
    prompt_version text        NOT NULL,
    case_id        text        NOT NULL,
    model          text        NOT NULL,
    upstream       text        NOT NULL,
    status         int         NOT NULL,
    input_tokens   int         NOT NULL DEFAULT 0,
    output_tokens  int         NOT NULL DEFAULT 0,
    cache_read     int         NOT NULL DEFAULT 0,
    cache_write    int         NOT NULL DEFAULT 0,
    cost_usd       numeric     NOT NULL DEFAULT 0,
    latency_ms     int         NOT NULL DEFAULT 0,
    at             timestamptz NOT NULL DEFAULT now()
);

ALTER TABLE spend_log ENABLE ROW LEVEL SECURITY;
ALTER TABLE spend_log FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON spend_log
    USING (tenant_id = current_setting('app.tenant_id', true))
    WITH CHECK (tenant_id = current_setting('app.tenant_id', true));
GRANT SELECT, INSERT ON spend_log TO hcp_app;
GRANT USAGE ON SEQUENCE spend_log_id_seq TO hcp_app;
