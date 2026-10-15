// An agent may call a tool only for the case's own country and product.
permit (principal, action == Action::"CallTool", resource)
when {
  principal.kind == "agent" &&
  resource.country == context.case_country &&
  resource.product == context.case_product
};
