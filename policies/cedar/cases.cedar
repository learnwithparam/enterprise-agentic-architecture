// Everyone except field representatives sees case detail. Reps see only that a case exists and its status.
permit (principal, action == Action::"ViewCaseDetail", resource)
when { principal.role != "field_rep" };

// Pharmacovigilance handles safety cases.
permit (principal, action == Action::"HandleSafetyCase", resource)
when { principal.role == "pv" };

// A field representative reads the text of an inquiry only when they submitted it themselves.
permit (principal, action == Action::"ViewInquiryText", resource)
when { principal.role != "field_rep" || resource.submitter == principal.name };
