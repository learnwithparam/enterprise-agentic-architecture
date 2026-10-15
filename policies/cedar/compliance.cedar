// Only compliance changes what the AI may send without a human, runs the ledger checks and resets the platform.
permit (principal, action in [Action::"SetAutonomy", Action::"AuditLedger", Action::"ResetDemo"], resource)
when { principal.role == "compliance" };
