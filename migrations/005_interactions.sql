-- Everything the four channels tell us lands here first, untouched (ADR 0021). The id is derived from the
-- channel and the sender's own event id, so a retried webhook or a re-sent batch file is the same row.
-- hcp_id stays empty until identity resolution links the source's id to a person.

CREATE TABLE interactions (
    tenant_id   text        NOT NULL REFERENCES tenants (id),
    id          text        NOT NULL,
    channel     text        NOT NULL,
    source_id   text        NOT NULL,
    kind        text        NOT NULL,
    body        text        NOT NULL,
    occurred_at timestamptz NOT NULL,
    received_at timestamptz NOT NULL DEFAULT now(),
    via         text        NOT NULL,
    hcp_id      text,
    PRIMARY KEY (tenant_id, id)
);

ALTER TABLE interactions ENABLE ROW LEVEL SECURITY;
ALTER TABLE interactions FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON interactions
    USING (tenant_id = current_setting('app.tenant_id', true))
    WITH CHECK (tenant_id = current_setting('app.tenant_id', true));
GRANT SELECT, INSERT, UPDATE ON interactions TO hcp_app;
