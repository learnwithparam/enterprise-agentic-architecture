-- What the event consumers remember (ADR 0020). processed_events makes delivery idempotent: SQS may hand
-- the same message over twice, and a publisher may send one event twice, but each handler sees an event id once.
-- dead_letters holds an event that failed every attempt, so an operator can read why and replay it.

CREATE TABLE processed_events (
    tenant_id text        NOT NULL REFERENCES tenants (id),
    event_id  text        NOT NULL,
    queue     text        NOT NULL,
    at        timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (tenant_id, event_id, queue)
);

ALTER TABLE processed_events ENABLE ROW LEVEL SECURITY;
ALTER TABLE processed_events FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON processed_events
    USING (tenant_id = current_setting('app.tenant_id', true))
    WITH CHECK (tenant_id = current_setting('app.tenant_id', true));
GRANT SELECT, INSERT ON processed_events TO hcp_app;

CREATE TABLE dead_letters (
    id          bigserial   PRIMARY KEY,
    tenant_id   text        NOT NULL REFERENCES tenants (id),
    queue       text        NOT NULL,
    event_id    text        NOT NULL,
    detail      jsonb       NOT NULL,
    error       text        NOT NULL,
    attempts    integer     NOT NULL,
    created_at  timestamptz NOT NULL DEFAULT now(),
    replayed_at timestamptz
);

ALTER TABLE dead_letters ENABLE ROW LEVEL SECURITY;
ALTER TABLE dead_letters FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON dead_letters
    USING (tenant_id = current_setting('app.tenant_id', true))
    WITH CHECK (tenant_id = current_setting('app.tenant_id', true));
GRANT SELECT, INSERT, UPDATE ON dead_letters TO hcp_app;
GRANT USAGE ON SEQUENCE dead_letters_id_seq TO hcp_app;
