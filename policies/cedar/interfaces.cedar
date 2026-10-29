// An MCP client calls a tool only if the tool is open to its user. Field representatives get none.
// Tools that show release metrics are marked sensitive and are for compliance alone.
permit (principal, action == Action::"CallMcpTool", resource)
when { principal.role != "field_rep" && (resource.sensitive == "no" || principal.role == "compliance") };
