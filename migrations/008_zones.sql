-- Three data zones inside a tenant (blueprint, "data firewall"). Each zone is its own schema with its own login role.
-- Medical holds cases and review work. Safety holds pharmacovigilance intakes and contact freezes.
-- Commercial holds doctors, touches and proposals. Everything else stays in public (shared).
-- The commercial role has no privilege on medical or safety. It learns only that a contact is on hold,
-- through shared.contact_hold, which has no case id and no text. Triggers keep that table in step.
-- Pre-launch, so existing rows are not moved: reset the dev database after this migration.

CREATE SCHEMA IF NOT EXISTS medical;
CREATE SCHEMA IF NOT EXISTS commercial;
CREATE SCHEMA IF NOT EXISTS safety;
CREATE SCHEMA IF NOT EXISTS shared;

DO $$
DECLARE r text;
BEGIN
    FOREACH r IN ARRAY ARRAY['hcp_medical', 'hcp_commercial', 'hcp_safety'] LOOP
        IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = r) THEN
            EXECUTE format('CREATE ROLE %I LOGIN NOSUPERUSER NOBYPASSRLS', r);
        END IF;
    END LOOP;
END $$;

-- The platform role keeps its tenant policy; the zone roles get their own narrower ones.
ALTER POLICY tenant_isolation ON docs TO hcp_app;

DO $$
DECLARE z text;
BEGIN
    FOREACH z IN ARRAY ARRAY['medical', 'commercial', 'safety'] LOOP
        EXECUTE format('CREATE TABLE %I.docs (LIKE public.docs INCLUDING ALL)', z);
        EXECUTE format('ALTER TABLE %I.docs ENABLE ROW LEVEL SECURITY', z);
        EXECUTE format('ALTER TABLE %I.docs FORCE ROW LEVEL SECURITY', z);
        EXECUTE format($p$CREATE POLICY tenant_isolation ON %I.docs TO hcp_app
            USING (tenant_id = current_setting('app.tenant_id', true))
            WITH CHECK (tenant_id = current_setting('app.tenant_id', true))$p$, z);
        EXECUTE format('GRANT USAGE ON SCHEMA %I TO hcp_app', z);
        EXECUTE format('GRANT SELECT, INSERT, UPDATE, DELETE ON %I.docs TO hcp_app', z);
    END LOOP;
END $$;

-- Each zone role reads and writes its own zone only.
GRANT USAGE ON SCHEMA commercial TO hcp_commercial;
GRANT SELECT, INSERT, UPDATE, DELETE ON commercial.docs TO hcp_commercial;
CREATE POLICY zone_role ON commercial.docs TO hcp_commercial
    USING (tenant_id = current_setting('app.tenant_id', true))
    WITH CHECK (tenant_id = current_setting('app.tenant_id', true));
GRANT USAGE ON SCHEMA medical TO hcp_medical;
GRANT SELECT, INSERT, UPDATE, DELETE ON medical.docs TO hcp_medical;
CREATE POLICY zone_role ON medical.docs TO hcp_medical
    USING (tenant_id = current_setting('app.tenant_id', true))
    WITH CHECK (tenant_id = current_setting('app.tenant_id', true));
GRANT USAGE ON SCHEMA safety TO hcp_safety;
GRANT SELECT, INSERT, UPDATE, DELETE ON safety.docs TO hcp_safety;
CREATE POLICY zone_role ON safety.docs TO hcp_safety
    USING (tenant_id = current_setting('app.tenant_id', true))
    WITH CHECK (tenant_id = current_setting('app.tenant_id', true));

-- Commercial may read approved content blocks and nothing else in the shared table.
GRANT SELECT ON public.docs TO hcp_commercial;
CREATE POLICY commercial_content ON public.docs FOR SELECT TO hcp_commercial
    USING (tenant_id = current_setting('app.tenant_id', true) AND kind = 'content');

-- The only thing that crosses between zones: a doctor, a product and why contact is on hold.
CREATE TABLE shared.contact_hold (
    tenant_id text NOT NULL REFERENCES public.tenants (id),
    hcp_id    text NOT NULL,
    product   text NOT NULL,
    reason    text NOT NULL CHECK (reason IN ('safety_freeze', 'open_medical_case')),
    PRIMARY KEY (tenant_id, hcp_id, product, reason)
);
ALTER TABLE shared.contact_hold ENABLE ROW LEVEL SECURITY;
ALTER TABLE shared.contact_hold FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON shared.contact_hold TO hcp_app, hcp_commercial, hcp_medical, hcp_safety
    USING (tenant_id = current_setting('app.tenant_id', true));
GRANT USAGE ON SCHEMA shared TO hcp_app, hcp_commercial, hcp_medical, hcp_safety;
GRANT SELECT ON shared.contact_hold TO hcp_app, hcp_commercial, hcp_medical, hcp_safety;
-- No role writes the hold table. Only the definer functions below do, so no case id can be put in it.

CREATE FUNCTION shared.sync_case_hold() RETURNS trigger LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog AS $$
DECLARE r record := CASE WHEN TG_OP = 'DELETE' THEN OLD ELSE NEW END;
        hcp text := r.doc -> 'hcp' ->> 'id'; prod text := r.doc ->> 'product';
BEGIN
    IF r.kind <> 'cases' OR hcp IS NULL OR prod IS NULL THEN RETURN r; END IF;
    IF EXISTS (SELECT 1 FROM medical.docs d WHERE d.tenant_id = r.tenant_id AND d.kind = 'cases'
               AND d.doc -> 'hcp' ->> 'id' = hcp AND d.doc ->> 'product' = prod
               AND d.doc ->> 'status' NOT IN ('sent', 'declined', 'rejected')) THEN
        INSERT INTO shared.contact_hold VALUES (r.tenant_id, hcp, prod, 'open_medical_case') ON CONFLICT DO NOTHING;
    ELSE
        DELETE FROM shared.contact_hold WHERE tenant_id = r.tenant_id AND hcp_id = hcp AND product = prod AND reason = 'open_medical_case';
    END IF;
    RETURN r;
END $$;
CREATE TRIGGER case_hold AFTER INSERT OR UPDATE OR DELETE ON medical.docs FOR EACH ROW EXECUTE FUNCTION shared.sync_case_hold();

CREATE FUNCTION shared.sync_freeze_hold() RETURNS trigger LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog AS $$
BEGIN
    IF TG_OP = 'DELETE' THEN
        IF OLD.kind = 'freezes' THEN
            DELETE FROM shared.contact_hold WHERE tenant_id = OLD.tenant_id AND hcp_id = OLD.doc ->> 'hcp' AND product = '*' AND reason = 'safety_freeze';
        END IF;
        RETURN OLD;
    END IF;
    IF NEW.kind = 'freezes' THEN
        INSERT INTO shared.contact_hold VALUES (NEW.tenant_id, NEW.doc ->> 'hcp', '*', 'safety_freeze') ON CONFLICT DO NOTHING;
    END IF;
    RETURN NEW;
END $$;
CREATE TRIGGER freeze_hold AFTER INSERT OR UPDATE OR DELETE ON safety.docs FOR EACH ROW EXECUTE FUNCTION shared.sync_freeze_hold();
REVOKE ALL ON FUNCTION shared.sync_case_hold(), shared.sync_freeze_hold() FROM PUBLIC;
