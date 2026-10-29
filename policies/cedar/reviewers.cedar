// A medical reviewer approves or rejects a draft only for their own country.
permit (principal, action in [Action::"ApproveReply", Action::"RejectReply"], resource)
when {
  principal.role == "medical_reviewer" &&
  resource.country == principal.country
};

// No one approves an AI reply on a case that pharmacovigilance owns.
forbid (principal, action in [Action::"ApproveReply", Action::"RejectReply"], resource)
when { resource.route == "pv" };

// A medical reviewer or compliance can ask the improver to look at the corrections; it only proposes.
permit (principal, action == Action::"RefreshProposals", resource)
when { principal.role == "medical_reviewer" || principal.role == "compliance" };
