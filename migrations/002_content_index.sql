-- Search index over approved content: one vector per block per embedding model, and a full-text index.
-- The vector column has no fixed size because each row names its model and dimension, so a new
-- model is built beside the old one and the two never mix (queries filter on model_id).

CREATE TABLE content_index (
    tenant_id text   NOT NULL REFERENCES tenants (id),
    block_id  text   NOT NULL,
    model_id  text   NOT NULL,
    dim       int    NOT NULL,
    embedding vector NOT NULL,
    PRIMARY KEY (tenant_id, block_id, model_id)
);

ALTER TABLE content_index ENABLE ROW LEVEL SECURITY;
ALTER TABLE content_index FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON content_index
    USING (tenant_id = current_setting('app.tenant_id', true))
    WITH CHECK (tenant_id = current_setting('app.tenant_id', true));
GRANT SELECT, INSERT, UPDATE, DELETE ON content_index TO hcp_app;

CREATE INDEX docs_content_fts ON docs USING gin (to_tsvector('simple', doc ->> 'text')) WHERE kind = 'content';
