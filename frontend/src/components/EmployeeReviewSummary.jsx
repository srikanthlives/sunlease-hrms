import { SectionDivider, StatusBadge, formatAadhaar, formatDate } from "./ui";

// Read-only, single-scrollable-page summary of a full employee record —
// used by EmployeeProfile's Overview tab. Mirrors the section list/layout
// of EmployeeWizard's Review & Submit step, but is driven entirely by the
// `detail` object GET /employees/{id} returns (not wizard-local state).
export default function EmployeeReviewSummary({ detail, onPreviewDocument }) {
  const { episode, employee, address, driving_licence: drivingLicence } = detail;
  const allocationTotal = detail.allocations.filter((a) => !a.effective_to).reduce((sum, a) => sum + a.percentage, 0);
  const hasDrivingLicence = drivingLicence && (
    drivingLicence.licence_number || drivingLicence.badge_number || drivingLicence.vehicle_class ||
    drivingLicence.issuing_authority || drivingLicence.issue_date || drivingLicence.expiry_date
  );

  return (
    <div className="space-y-6 text-sm">
      <SectionDivider>Personal Information</SectionDivider>
      <div className="grid grid-cols-3 gap-3">
        <Field label="First Name" value={employee.first_name} />
        <Field label="Middle Name" value={employee.middle_name} />
        <Field label="Last Name" value={employee.last_name} />
        <Field label="Father's/Husband's Name" value={employee.father_husband_name} />
        <Field label="Gender" value={employee.gender} />
        <Field label="Date of Birth" value={formatDate(employee.date_of_birth)} />
        <Field label="Marital Status" value={employee.marital_status} />
        <Field label="Educational Qualification" value={employee.educational_qualification} />
      </div>

      <SectionDivider>Previous Experience</SectionDivider>
      <div className="grid grid-cols-3 gap-3">
        <Field label="Previous Designation" value={employee.previous_designation} />
        <Field label="Previous Company Name" value={employee.previous_company_name} />
        <Field label="Date of Joining (Previous Company)" value={formatDate(employee.previous_date_of_joining)} />
        <Field label="Total Experience" value={employee.total_experience_years != null ? `${employee.total_experience_years} years` : null} />
        <Field label="Previous Company Details" value={employee.previous_company_details} />
      </div>

      <SectionDivider>Contact Details</SectionDivider>
      <div className="grid grid-cols-3 gap-3">
        <Field label="Mobile Number" value={employee.mobile_number} />
        <Field label="Alternate Mobile" value={employee.alternate_mobile_number} />
        <Field label="Personal Email" value={employee.personal_email} />
        <Field label="Official Email" value={employee.official_email} />
      </div>

      <SectionDivider>Identity Documents</SectionDivider>
      <div className="grid grid-cols-3 gap-3">
        <Field label="Aadhaar Name" value={employee.aadhaar_name} />
        <Field label="Aadhaar DOB" value={formatDate(employee.aadhaar_dob)} />
        <Field label="Aadhaar Number" value={formatAadhaar(employee.aadhaar)} />
        <Field label="PAN Name" value={employee.pan_name} />
        <Field label="PAN DOB" value={formatDate(employee.pan_dob)} />
        <Field label="PAN Number" value={employee.pan} />
      </div>

      <SectionDivider>Emergency Contact</SectionDivider>
      <div className="grid grid-cols-3 gap-3">
        <Field label="Name" value={employee.emergency_contact_name} />
        <Field label="Relationship" value={employee.emergency_contact_relationship} />
        <Field label="Mobile" value={employee.emergency_contact_mobile} />
      </div>

      <SectionDivider>Address</SectionDivider>
      <div className="grid grid-cols-2 gap-3">
        <Field
          label="Present Address"
          value={[address.present_line1, address.present_line2, address.present_city, address.present_state, address.present_pincode, address.present_country].filter(Boolean).join(", ")}
        />
        <Field
          label="Permanent Address"
          value={address.same_as_present
            ? "Same as Present Address"
            : [address.permanent_line1, address.permanent_line2, address.permanent_city, address.permanent_state, address.permanent_pincode, address.permanent_country].filter(Boolean).join(", ")}
        />
      </div>

      <SectionDivider>Employment Information</SectionDivider>
      <div className="grid grid-cols-3 gap-3">
        <Field label="Employee Number" value={episode.employee_number} />
        <Field label="Employment Type" value={episode.employment_type} />
        <Field label="Employee Category" value={episode.employee_category} />
        <Field label="Designation" value={episode.designation} />
        <Field label="Work Location" value={episode.work_location} />
        <Field label="Shift Group" value={episode.shift_group} />
        <Field label="Date of Joining" value={formatDate(episode.date_of_joining)} />
        <Field label="Confirmation Date" value={formatDate(episode.confirmation_date)} />
        <Field label="Application Reference Number" value={episode.application_reference_number} />
      </div>

      <SectionDivider>Organizational Assignment</SectionDivider>
      <div className="space-y-2">
        {detail.assignments.length === 0 && <p className="text-ink/40 text-xs">No organizational assignment recorded.</p>}
        {detail.assignments.map((a) => (
          <div key={a.id} className="text-xs text-ink/70">
            Cost Center #{a.cost_center_id} · Department #{a.department_id}{a.project_id ? ` · Project #${a.project_id}` : ""}
            {" — "}{formatDate(a.effective_from)} to {a.effective_to ? formatDate(a.effective_to) : "present"}
          </div>
        ))}
      </div>
      <div className="flex items-center justify-between mt-3">
        <span className="text-xs font-semibold uppercase tracking-wide text-ink/40">Cost Allocation</span>
        <AllocationTotalBadge total={allocationTotal} />
      </div>
      <div className="space-y-1">
        {detail.allocations.filter((a) => !a.effective_to).length === 0 && <p className="text-ink/40 text-xs">No cost allocation recorded.</p>}
        {detail.allocations.filter((a) => !a.effective_to).map((a) => (
          <div key={a.id} className="text-xs text-ink/70">{a.percentage}% — {a.cost_center_name}{a.project_name ? ` · ${a.project_name}` : ""}</div>
        ))}
      </div>

      <SectionDivider>Statutory Information</SectionDivider>
      {detail.statutory.length === 0 && <p className="text-ink/40 text-xs">No statutory information recorded.</p>}
      {detail.statutory.map((s) => (
        <div key={s.id} className="space-y-3">
          <div>
            <div className="flex items-center gap-2 mb-1">
              <span className="text-xs font-semibold uppercase tracking-wide text-ink/40">PF</span>
              <StatusBadge status={s.pf_eligible ? "ACTIVE" : "INACTIVE"} />
            </div>
            {s.pf_eligible ? (
              <div className="grid grid-cols-3 gap-3">
                <Field label="Name on File" value={s.pf_name_on_file} />
                <Field label="UAN / Member ID" value={s.uan} />
                <Field label="Effective Date" value={formatDate(s.pf_effective_date)} />
              </div>
            ) : <p className="text-ink/40 text-xs">Not eligible.</p>}
          </div>
          <div>
            <div className="flex items-center gap-2 mb-1">
              <span className="text-xs font-semibold uppercase tracking-wide text-ink/40">ESI</span>
              <StatusBadge status={s.esi_eligible ? "ACTIVE" : "INACTIVE"} />
            </div>
            {s.esi_eligible ? (
              <div className="grid grid-cols-3 gap-3">
                <Field label="Name on File" value={s.esi_name_on_file} />
                <Field label="ESI Number / Member ID" value={s.esi_number} />
                <Field label="Mediclaim Number" value={s.esi_mediclaim_number} />
                <Field label="Effective Date" value={formatDate(s.esi_effective_date)} />
              </div>
            ) : <p className="text-ink/40 text-xs">Not eligible.</p>}
          </div>
          <div className="grid grid-cols-2 gap-3">
            <Field label="Professional Tax Eligible" value={s.pt_eligible ? "Yes" : "No"} />
            <Field label="Gratuity Eligible" value={s.gratuity_eligible ? "Yes" : "No"} />
          </div>
        </div>
      ))}

      <SectionDivider>Bank Information</SectionDivider>
      <div className="space-y-1">
        {detail.bank_accounts.length === 0 && <p className="text-ink/40 text-xs">No bank account recorded.</p>}
        {detail.bank_accounts.map((b) => (
          <div key={b.id} className="text-xs text-ink/70">
            {b.bank_name} — {b.account_number} ({b.ifsc}) {b.is_primary ? "· Primary" : ""} · Verification: {b.verification_status}
          </div>
        ))}
      </div>

      {hasDrivingLicence && (
        <>
          <SectionDivider>Driving Licence</SectionDivider>
          <div className="grid grid-cols-3 gap-3">
            <Field label="Licence Number" value={drivingLicence.licence_number} />
            <Field label="Badge Number" value={drivingLicence.badge_number} />
            <Field label="Vehicle Class" value={drivingLicence.vehicle_class} />
            <Field label="Issuing Authority" value={drivingLicence.issuing_authority} />
            <Field label="Issue Date" value={formatDate(drivingLicence.issue_date)} />
            <Field label="Expiry Date" value={formatDate(drivingLicence.expiry_date)} />
          </div>
        </>
      )}

      <SectionDivider>Documents</SectionDivider>
      <div className="space-y-1">
        {detail.documents.length === 0 && <p className="text-ink/40 text-xs">No documents uploaded.</p>}
        {detail.documents.map((d) => (
          <button
            key={d.id}
            type="button"
            onClick={() => onPreviewDocument && onPreviewDocument(d)}
            className="w-full text-left text-xs text-ink/70 hover:text-brand-800 hover:underline flex items-center gap-2"
          >
            <span className="font-medium text-ink">{d.document_type}</span>
            <span>— {d.file_name}</span>
            <span className="text-ink/40">({d.verification_status})</span>
          </button>
        ))}
      </div>

      <SectionDivider>Dependents</SectionDivider>
      <div className="space-y-1">
        {detail.dependents.length === 0 && <p className="text-ink/40 text-xs">No dependents recorded.</p>}
        {detail.dependents.map((d) => <div key={d.id} className="text-xs text-ink/70">{d.name} — {d.relationship_type || "—"}</div>)}
      </div>

      <SectionDivider>Nominees</SectionDivider>
      <div className="space-y-1">
        {detail.nominees.length === 0 && <p className="text-ink/40 text-xs">No nominees recorded.</p>}
        {detail.nominees.map((n) => <div key={n.id} className="text-xs text-ink/70">{n.name} — {n.nomination_type || "—"} ({n.percentage ?? "—"}%)</div>)}
      </div>
    </div>
  );
}

function AllocationTotalBadge({ total }) {
  const cls = total === 100 ? "bg-ok/10 text-ok" : total > 100 ? "bg-danger/10 text-danger" : "bg-warn/10 text-warn";
  return <span className={`text-xs font-medium px-2 py-1 rounded-full ${cls}`}>{total}% allocated</span>;
}

function Field({ label, value }) {
  return (
    <div>
      <div className="text-[10px] uppercase tracking-wide text-ink/40">{label}</div>
      <div className="text-ink text-sm">{value || value === 0 ? value : "—"}</div>
    </div>
  );
}
