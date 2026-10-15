// Only compliance changes what the AI may send without a human, and runs the ledger checks.
permit (principal, action in [Action::"SetAutonomy", Action::"AuditLedger"], resource)
when { principal.role == "compliance" };
