// A field representative approves an outreach touch only for doctors in their own country.
permit (principal, action == Action::"ApproveOutreach", resource)
when {
  principal.role == "field_rep" &&
  resource.country == principal.country
};
