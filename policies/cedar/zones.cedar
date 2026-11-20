// Data zones. Only the roles that handle medical or safety work see the medical view of a doctor.
// Marketing and field reps get the commercial view, which holds no case id, case count or safety note.
permit (principal, action == Action::"ViewMedicalZone", resource)
when { principal.role == "medical_reviewer" || principal.role == "pv" || principal.role == "compliance" };
