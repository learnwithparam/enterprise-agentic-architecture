// Only content owners withdraw approved content.
permit (principal, action == Action::"WithdrawContent", resource)
when { principal.role == "content_owner" };
