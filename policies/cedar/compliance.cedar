// Only compliance changes what the AI may send without a human, runs the ledger checks, erases a person's data, promotes a release, replays a parked event and resets the platform.
permit (principal, action in [Action::"SetAutonomy", Action::"AuditLedger", Action::"ErasePerson", Action::"ResetDemo", Action::"PromoteRelease", Action::"ReplayDeadLetter"], resource)
when { principal.role == "compliance" };
