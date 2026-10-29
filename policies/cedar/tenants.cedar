// Nothing crosses a tenant: a principal acts only on resources of the tenant it signed in under.
// A forbid beats every permit, so no other policy can widen this.
forbid (principal, action, resource)
unless { principal.tenant == resource.tenant };
