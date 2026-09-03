import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import client, { apiErrorMessage } from "../api/client";
import { Card, Button, Input, Select, Checkbox, StatusBadge, SectionDivider, formatDate, formatDateTime } from "../components/ui";
import { useAuth } from "../context/AuthContext";

const TABS = [
  "Overview", "Personal", "Employment", "Organization", "Statutory",
  "Bank Accounts", "Documents", "Driving Licence", "Dependents", "Nominees", "Separation", "Audit History",
];

export default function EmployeeProfile() {
  const { episodeId } = useParams();
  const navigate = useNavigate();
  const { can, user } = useAuth();
  const [detail, setDetail] = useState(null);
  const [audit, setAudit] = useState([]);
  const [tab, setTab] = useState("Overview");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [requiredDocs, setRequiredDocs] = useState([]);
  const [docUploadingId, setDocUploadingId] = useState(null);
  const [dlRequirement, setDlRequirement] = useState({ show: false, is_required: false });
  const [drivingLicence, setDrivingLicence] = useState({});
  const [dlSaving, setDlSaving] = useState(false);
  const [photoUrl, setPhotoUrl] = useState(null);
  const [sepForm, setSepForm] = useState({ separation_type: "RESIGNATION", resignation_date: "", notice_period_days: "", last_working_date: "", reason: "", remarks: "" });
  const [checklist, setChecklist] = useState({});
  const [sepBusy, setSepBusy] = useState(false);
  const [banner, setBanner] = useState("");

  function reload() {
    client.get(`/employees/${episodeId}`).then((res) => {
      setDetail(res.data);
      setDrivingLicence(res.data.driving_licence || {});
      setChecklist(res.data.separation || {});
      if (res.data.employee.has_photo) {
        client.get(`/employees/${episodeId}/photo`, { responseType: "blob" })
          .then((r) => setPhotoUrl(URL.createObjectURL(r.data)))
          .catch(() => setPhotoUrl(null));
      } else {
        setPhotoUrl(null);
      }
    });
    client.get(`/employees/${episodeId}/audit`).then((res) => setAudit(res.data));
    client.get(`/employees/${episodeId}/required-documents`).then((res) => setRequiredDocs(res.data));
    client.get(`/employees/${episodeId}/driving-licence-requirement`).then((res) => setDlRequirement(res.data));
  }

  useEffect(reload, [episodeId]);

  async function saveDrivingLicence() {
    setDlSaving(true);
    setError("");
    try {
      await client.put(`/employees/${episodeId}/driving-licence`, drivingLicence);
      reload();
    } catch (err) {
      setError(apiErrorMessage(err));
    } finally {
      setDlSaving(false);
    }
  }

  async function uploadDocument(documentTypeId, file) {
    if (!file) return;
    setDocUploadingId(documentTypeId);
    setError("");
    setBanner("");
    try {
      const form = new FormData();
      form.append("document_type_id", documentTypeId);
      form.append("file", file);
      const res = await client.post(`/employees/${episodeId}/documents`, form);
      if (res.data?.submitted_for_approval) {
        setBanner("Replacement submitted for approval — the current document stays in effect until an Approver reviews it (see Change Requests).");
      }
      reload();
    } catch (err) {
      setError(apiErrorMessage(err));
    } finally {
      setDocUploadingId(null);
    }
  }

  async function removeDocument(documentMetaId) {
    setError("");
    try {
      await client.delete(`/employees/${episodeId}/documents/${documentMetaId}`);
      reload();
    } catch (err) {
      setError(apiErrorMessage(err));
    }
  }

  async function downloadDocument(documentMetaId, fileName) {
    const res = await client.get(`/employees/${episodeId}/documents/${documentMetaId}/download`, { responseType: "blob" });
    const url = URL.createObjectURL(res.data);
    const a = document.createElement("a");
    a.href = url;
    a.download = fileName || "document";
    a.click();
    URL.revokeObjectURL(url);
  }

  async function act(action) {
    setBusy(true);
    setError("");
    try {
      await client.post(`/employees/${episodeId}/${action}`);
      reload();
    } catch (err) {
      setError(apiErrorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  async function initiateSeparation() {
    setSepBusy(true);
    setError("");
    try {
      await client.post(`/employees/${episodeId}/separate`, sepForm);
      reload();
    } catch (err) {
      setError(apiErrorMessage(err));
    } finally {
      setSepBusy(false);
    }
  }

  async function saveChecklist() {
    setSepBusy(true);
    setError("");
    try {
      await client.put(`/employees/${episodeId}/separation/checklist`, checklist);
      reload();
    } catch (err) {
      setError(apiErrorMessage(err));
    } finally {
      setSepBusy(false);
    }
  }

  async function completeSeparation() {
    setSepBusy(true);
    setError("");
    try {
      await client.post(`/employees/${episodeId}/separation/complete`);
      reload();
    } catch (err) {
      setError(apiErrorMessage(err));
    } finally {
      setSepBusy(false);
    }
  }

  async function cancelSeparation() {
    setSepBusy(true);
    setError("");
    try {
      await client.post(`/employees/${episodeId}/separation/cancel`);
      reload();
    } catch (err) {
      setError(apiErrorMessage(err));
    } finally {
      setSepBusy(false);
    }
  }

  if (!detail) return <div className="text-sm text-ink/40 py-10 text-center">Loading…</div>;
  const { episode, employee, address } = detail;
  const presentAddressLine = [address.present_line1, address.present_line2, address.present_city, address.present_state, address.present_pincode, address.present_country].filter(Boolean).join(", ");
  const permanentAddressLine = [address.permanent_line1, address.permanent_line2, address.permanent_city, address.permanent_state, address.permanent_pincode, address.permanent_country].filter(Boolean).join(", ");

  return (
    <div className="space-y-5">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          {photoUrl && <img src={photoUrl} alt="Employee photo" className="w-12 h-14 object-cover rounded-md border border-ink/15" />}
          <div>
            <h1 className="text-xl font-display font-semibold text-ink">{employee.first_name} {employee.last_name}</h1>
            <p className="text-sm text-ink/50 mt-1">
              {episode.employee_number} · {episode.designation || "—"} · <StatusBadge status={episode.status} />
            </p>
          </div>
        </div>
        <div className="flex gap-2">
          {episode.status === "PENDING_APPROVAL" && (
            <>
              <Button variant="accent" onClick={() => act("approve")} disabled={busy}>Approve</Button>
              <Button variant="danger" onClick={() => act("reject")} disabled={busy}>Reject</Button>
            </>
          )}
          {episode.status === "DRAFT" && (
            <Button variant="outline" onClick={() => navigate(`/employees/${episodeId}/wizard`)}>Continue Draft</Button>
          )}
          {episode.status !== "DRAFT" && episode.status !== "SEPARATED" && (user?.role === "HR_ADMIN" || can("employee.edit")) && (
            <Button variant="outline" onClick={() => navigate(`/employees/${episodeId}/wizard`)}>Edit</Button>
          )}
        </div>
      </div>
      {error && <div className="text-sm text-danger bg-danger/10 rounded-md px-3 py-2">{error}</div>}
      {banner && <div className="text-sm text-brand-700 bg-brand-50 rounded-md px-3 py-2">{banner}</div>}

      <div className="flex gap-1.5 flex-wrap">
        {TABS.map((t) => (
          <button
            key={t}
            onClick={() => setTab(t)}
            className={`text-[11px] px-2.5 py-1 rounded-full border ${
              t === tab ? "bg-brand-800 text-white border-brand-800" : "bg-white text-ink/50 border-ink/15"
            }`}
          >
            {t}
          </button>
        ))}
      </div>

      <Card>
        {tab === "Overview" && (
          <div className="grid grid-cols-2 gap-3 text-sm">
            <Field label="Employee Number" value={episode.employee_number} />
            <Field label="Status" value={<StatusBadge status={episode.status} />} />
            <Field label="Designation" value={episode.designation} />
            <Field label="Date of Joining" value={formatDate(episode.date_of_joining)} />
            <Field label="Mobile" value={employee.mobile_number} />
            <Field label="Official Email" value={employee.official_email} />
          </div>
        )}

        {tab === "Personal" && (
          <div className="space-y-5">
            <SectionDivider>Basic Details</SectionDivider>
            <div className="grid grid-cols-2 gap-3 text-sm">
              <Field label="First Name" value={employee.first_name} />
              <Field label="Middle Name" value={employee.middle_name} />
              <Field label="Last Name" value={employee.last_name} />
              <Field label="Father's/Husband's Name" value={employee.father_husband_name} />
              <Field label="Gender" value={employee.gender} />
              <Field label="Date of Birth" value={formatDate(employee.date_of_birth)} />
              <Field label="Marital Status" value={employee.marital_status} />
            </div>

            <SectionDivider>Education</SectionDivider>
            <div className="grid grid-cols-2 gap-3 text-sm">
              <Field label="Educational Qualification" value={employee.educational_qualification} />
            </div>

            <SectionDivider>Contact Details</SectionDivider>
            <div className="grid grid-cols-2 gap-3 text-sm">
              <Field label="Mobile" value={employee.mobile_number} />
              <Field label="Alternate Mobile" value={employee.alternate_mobile_number} />
              <Field label="Personal Email" value={employee.personal_email} />
              <Field label="Official Email" value={employee.official_email} />
            </div>

            <SectionDivider>Identity Documents</SectionDivider>
            <div className="grid grid-cols-2 gap-3 text-sm">
              <Field label="Aadhaar" value={employee.aadhaar} />
              <Field label="PAN" value={employee.pan} />
            </div>

            <SectionDivider>Previous Experience</SectionDivider>
            <div className="grid grid-cols-2 gap-3 text-sm">
              <Field label="Previous Designation" value={employee.previous_designation} />
              <Field label="Previous Company Name" value={employee.previous_company_name} />
              <Field label="Date of Joining (Previous Company)" value={formatDate(employee.previous_date_of_joining)} />
              <Field label="Total Experience" value={employee.total_experience_years != null ? `${employee.total_experience_years} years` : null} />
              <Field label="Previous Company Details" value={employee.previous_company_details} />
            </div>

            <SectionDivider>Address</SectionDivider>
            <div className="grid grid-cols-2 gap-3 text-sm">
              <Field label="Present Address" value={presentAddressLine} />
              <Field label="Permanent Address" value={address.same_as_present ? "Same as Present Address" : permanentAddressLine} />
            </div>

            <SectionDivider>Emergency Contact</SectionDivider>
            <div className="grid grid-cols-2 gap-3 text-sm">
              <Field label="Emergency Contact" value={employee.emergency_contact_name ? `${employee.emergency_contact_name} (${employee.emergency_contact_relationship || "—"}) — ${employee.emergency_contact_mobile || "—"}` : null} />
            </div>
          </div>
        )}

        {tab === "Employment" && (
          <div className="grid grid-cols-2 gap-3 text-sm">
            <Field label="Employment Type" value={episode.employment_type} />
            <Field label="Designation" value={episode.designation} />
            <Field label="Work Location" value={episode.work_location} />
            <Field label="Shift Group" value={episode.shift_group} />
            <Field label="Date of Joining" value={formatDate(episode.date_of_joining)} />
            <Field label="Confirmation Date" value={formatDate(episode.confirmation_date)} />
            <Field label="Separation Date" value={formatDate(episode.separation_date)} />
            <Field label="Separation Reason" value={episode.separation_reason} />
          </div>
        )}

        {tab === "Organization" && (
          <div className="space-y-2 text-sm">
            {detail.assignments.length === 0 && <p className="text-ink/40">No organizational assignment recorded yet.</p>}
            {detail.assignments.map((a) => (
              <div key={a.id} className="border border-ink/10 rounded-md p-3">
                <div>Cost Center #{a.cost_center_id} · Department #{a.department_id} {a.project_id ? `· Project #${a.project_id}` : ""}</div>
                <div className="text-ink/40 text-xs mt-1">{formatDate(a.effective_from)} — {a.effective_to ? formatDate(a.effective_to) : "present"}</div>
              </div>
            ))}
            <div className="flex items-center justify-between pt-2">
              <h3 className="text-sm font-semibold text-ink">Cost Allocation</h3>
              {detail.allocations.some((a) => !a.effective_to) && (
                <span className="text-xs text-ink/50">
                  {detail.allocations.filter((a) => !a.effective_to).reduce((sum, a) => sum + a.percentage, 0)}% currently allocated
                </span>
              )}
            </div>
            {detail.allocations.length === 0 && <p className="text-ink/40">No cost allocation recorded yet.</p>}
            {detail.allocations.map((a) => (
              <div key={a.id} className="border border-ink/10 rounded-md p-3">
                <div>{a.percentage}% — {a.cost_center_name || `Cost Center #${a.cost_center_id}`} {a.project_name ? `· ${a.project_name}` : ""}</div>
                <div className="text-ink/40 text-xs mt-1">{formatDate(a.effective_from)} — {a.effective_to ? formatDate(a.effective_to) : "present"}</div>
              </div>
            ))}
          </div>
        )}

        {tab === "Statutory" && (
          <div className="space-y-3 text-sm">
            {detail.statutory.length === 0 && <p className="text-ink/40">No statutory information recorded yet.</p>}
            {detail.statutory.map((s) => (
              <div key={s.id} className="border border-ink/10 rounded-md p-4 space-y-4">
                <div>
                  <div className="flex items-center gap-2 mb-2">
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
                  <div className="flex items-center gap-2 mb-2">
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

                <div>
                  <span className="text-xs font-semibold uppercase tracking-wide text-ink/40">Other Eligibility</span>
                  <div className="grid grid-cols-2 gap-3 mt-2">
                    <Field label="Professional Tax Eligible" value={s.pt_eligible ? "Yes" : "No"} />
                    <Field label="Gratuity Eligible" value={s.gratuity_eligible ? "Yes" : "No"} />
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}

        {tab === "Bank Accounts" && (
          <div className="space-y-2 text-sm">
            {detail.bank_accounts.length === 0 && <p className="text-ink/40">No bank account recorded yet.</p>}
            {detail.bank_accounts.map((b) => (
              <div key={b.id} className="border border-ink/10 rounded-md p-3">
                <div>{b.bank_name} — {b.account_number} ({b.ifsc})</div>
                <div className="text-ink/40 text-xs mt-1">{b.is_primary ? "Primary" : "Secondary"} · Verification: {b.verification_status}</div>
              </div>
            ))}
          </div>
        )}

        {tab === "Documents" && (
          <div className="space-y-2">
            {requiredDocs.length === 0 && (
              <p className="text-sm text-ink/40 py-6 text-center">No document requirements configured for this employee's Type/Category/Designation.</p>
            )}
            {requiredDocs.map((d) => (
              <div key={d.document_type_id} className="border border-ink/10 rounded-md p-3 flex items-center justify-between gap-4">
                <div>
                  <div className="text-sm font-medium text-ink flex items-center gap-2">
                    {d.document_type_name}
                    {d.is_mandatory ? (
                      <span className="text-[10px] font-medium px-1.5 py-0.5 rounded-full bg-danger/10 text-danger">Mandatory</span>
                    ) : (
                      <span className="text-[10px] font-medium px-1.5 py-0.5 rounded-full bg-ink/5 text-ink/50">Optional</span>
                    )}
                  </div>
                  {d.uploaded ? (
                    <div className="text-xs text-ink/50 mt-0.5">{d.file_name} · {d.verification_status}</div>
                  ) : (
                    <div className="text-xs text-ink/40 mt-0.5">Not uploaded</div>
                  )}
                </div>
                <div className="flex items-center gap-2">
                  {d.uploaded && (
                    <>
                      <Button variant="outline" size="sm" onClick={() => downloadDocument(d.document_meta_id, d.file_name)}>Download</Button>
                      {can("employee.documents.upload") && (
                        <Button variant="danger" size="sm" onClick={() => removeDocument(d.document_meta_id)}>Remove</Button>
                      )}
                    </>
                  )}
                  {can("employee.documents.upload") && (
                    <label className="text-xs">
                      <span className={`inline-block px-3 py-1.5 rounded-md border border-ink/15 cursor-pointer hover:bg-ink/5 ${docUploadingId === d.document_type_id ? "opacity-50 pointer-events-none" : ""}`}>
                        {docUploadingId === d.document_type_id ? "Uploading…" : d.uploaded ? "Replace" : "Upload"}
                      </span>
                      <input type="file" className="hidden" onChange={(e) => uploadDocument(d.document_type_id, e.target.files[0])} />
                    </label>
                  )}
                </div>
              </div>
            ))}
          </div>
        )}

        {tab === "Driving Licence" && (
          <div className="space-y-4">
            {!dlRequirement.show ? (
              <p className="text-sm text-ink/40 py-6 text-center">
                Not applicable — no Document Configuration rule matches this employee's Employee Type/Category/Designation.
              </p>
            ) : (
              <>
                <p className="text-xs text-ink/40">
                  {dlRequirement.is_required ? "Required for this employee." : "Optional for this employee."}
                </p>
                {can("employee.sensitive.edit") ? (
                  <>
                    <div className="grid grid-cols-2 gap-4">
                      <Input label="Licence Number" value={drivingLicence.licence_number || ""} onChange={(e) => setDrivingLicence({ ...drivingLicence, licence_number: e.target.value })} />
                      <Input label="Badge Number" value={drivingLicence.badge_number || ""} onChange={(e) => setDrivingLicence({ ...drivingLicence, badge_number: e.target.value })} />
                      <Input label="Vehicle Class" value={drivingLicence.vehicle_class || ""} onChange={(e) => setDrivingLicence({ ...drivingLicence, vehicle_class: e.target.value })} placeholder="e.g. LMV, HMV" />
                      <Input label="Issuing Authority" value={drivingLicence.issuing_authority || ""} onChange={(e) => setDrivingLicence({ ...drivingLicence, issuing_authority: e.target.value })} />
                      <Input label="Issue Date" type="date" value={drivingLicence.issue_date || ""} onChange={(e) => setDrivingLicence({ ...drivingLicence, issue_date: e.target.value })} />
                      <Input label="Expiry Date" type="date" value={drivingLicence.expiry_date || ""} onChange={(e) => setDrivingLicence({ ...drivingLicence, expiry_date: e.target.value })} />
                    </div>
                    <Button onClick={saveDrivingLicence} disabled={dlSaving}>{dlSaving ? "Saving…" : "Save"}</Button>
                  </>
                ) : (
                  <div className="grid grid-cols-2 gap-3 text-sm">
                    <Field label="Licence Number" value={drivingLicence.licence_number} />
                    <Field label="Badge Number" value={drivingLicence.badge_number} />
                    <Field label="Vehicle Class" value={drivingLicence.vehicle_class} />
                    <Field label="Issuing Authority" value={drivingLicence.issuing_authority} />
                    <Field label="Issue Date" value={formatDate(drivingLicence.issue_date)} />
                    <Field label="Expiry Date" value={formatDate(drivingLicence.expiry_date)} />
                  </div>
                )}
              </>
            )}
          </div>
        )}

        {tab === "Dependents" && (
          <div className="space-y-2 text-sm">
            {detail.dependents.length === 0 && <p className="text-ink/40">No dependents recorded.</p>}
            {detail.dependents.map((d) => <div key={d.id} className="border border-ink/10 rounded-md p-3">{d.name} — {d.relationship_type || "—"}</div>)}
          </div>
        )}

        {tab === "Nominees" && (
          <div className="space-y-2 text-sm">
            {detail.nominees.length === 0 && <p className="text-ink/40">No nominees recorded.</p>}
            {detail.nominees.map((n) => <div key={n.id} className="border border-ink/10 rounded-md p-3">{n.name} — {n.nomination_type || "—"} ({n.percentage ?? "—"}%)</div>)}
          </div>
        )}

        {tab === "Separation" && (
          <div className="space-y-4">
            {episode.status === "ACTIVE" && (
              can("employee.separate") ? (
                <>
                  <p className="text-xs text-ink/40">Initiate the exit process — the employee moves to Notice Period.</p>
                  <div className="grid grid-cols-2 gap-4">
                    <Select label="Separation Type" value={sepForm.separation_type} onChange={(e) => setSepForm({ ...sepForm, separation_type: e.target.value })}>
                      <option value="RESIGNATION">Resignation</option>
                      <option value="TERMINATION">Termination</option>
                      <option value="ABSCONDING">Absconding</option>
                      <option value="RETIREMENT">Retirement</option>
                      <option value="DEATH">Death</option>
                      <option value="CONTRACT_COMPLETION">Contract Completion</option>
                      <option value="OTHER">Other</option>
                    </Select>
                    <Input label="Resignation Date" type="date" value={sepForm.resignation_date} onChange={(e) => setSepForm({ ...sepForm, resignation_date: e.target.value })} />
                    <Input label="Notice Period (Days)" type="number" value={sepForm.notice_period_days} onChange={(e) => setSepForm({ ...sepForm, notice_period_days: e.target.value })} />
                    <Input label="Last Working Date" type="date" value={sepForm.last_working_date} onChange={(e) => setSepForm({ ...sepForm, last_working_date: e.target.value })} />
                    <Input label="Reason" value={sepForm.reason} onChange={(e) => setSepForm({ ...sepForm, reason: e.target.value })} />
                    <Input label="Remarks" value={sepForm.remarks} onChange={(e) => setSepForm({ ...sepForm, remarks: e.target.value })} />
                  </div>
                  <Button variant="danger" onClick={initiateSeparation} disabled={sepBusy}>{sepBusy ? "Submitting…" : "Initiate Exit"}</Button>
                </>
              ) : <p className="text-sm text-ink/40 py-6 text-center">No exit has been initiated.</p>
            )}

            {episode.status === "NOTICE_PERIOD" && (
              <>
                <SectionDivider>Separation Details</SectionDivider>
                <div className="grid grid-cols-3 gap-3 text-sm">
                  <Field label="Separation Type" value={detail.separation?.separation_type} />
                  <Field label="Resignation Date" value={formatDate(detail.separation?.resignation_date)} />
                  <Field label="Notice Period (Days)" value={detail.separation?.notice_period_days} />
                  <Field label="Last Working Date" value={formatDate(detail.separation?.last_working_date)} />
                  <Field label="Reason" value={detail.separation?.reason} />
                  <Field label="Remarks" value={detail.separation?.remarks} />
                </div>

                {can("employee.separate") && (
                  <>
                    <SectionDivider>Exit Checklist</SectionDivider>
                    <div className="grid grid-cols-2 gap-3">
                      <Checkbox label="Exit Interview Done" checked={!!checklist.exit_interview_done} onChange={(e) => setChecklist({ ...checklist, exit_interview_done: e.target.checked })} />
                      <Checkbox label="Asset Return Done" checked={!!checklist.asset_return_done} onChange={(e) => setChecklist({ ...checklist, asset_return_done: e.target.checked })} />
                      <Checkbox label="Clearance Done" checked={!!checklist.clearance_done} onChange={(e) => setChecklist({ ...checklist, clearance_done: e.target.checked })} />
                      <Checkbox label="Document Issuance Done" checked={!!checklist.document_issuance_done} onChange={(e) => setChecklist({ ...checklist, document_issuance_done: e.target.checked })} />
                    </div>
                    <div className="grid grid-cols-2 gap-4">
                      <Select label="Full & Final Status" value={checklist.full_final_status || "PENDING"} onChange={(e) => setChecklist({ ...checklist, full_final_status: e.target.value })}>
                        <option value="PENDING">Pending</option>
                        <option value="IN_PROGRESS">In Progress</option>
                        <option value="COMPLETED">Completed</option>
                      </Select>
                      <Input label="Last Working Date" type="date" value={checklist.last_working_date || ""} onChange={(e) => setChecklist({ ...checklist, last_working_date: e.target.value })} />
                    </div>
                    <Input label="Remarks" value={checklist.remarks || ""} onChange={(e) => setChecklist({ ...checklist, remarks: e.target.value })} />
                    <div className="flex gap-2">
                      <Button onClick={saveChecklist} disabled={sepBusy}>{sepBusy ? "Saving…" : "Save Checklist"}</Button>
                      <Button variant="accent" onClick={completeSeparation} disabled={sepBusy}>Mark as Separated</Button>
                      <Button variant="outline" onClick={cancelSeparation} disabled={sepBusy}>Cancel Exit</Button>
                    </div>
                  </>
                )}
              </>
            )}

            {episode.status === "SEPARATED" && (
              <div className="space-y-4">
                <SectionDivider>Separation Summary</SectionDivider>
                <div className="grid grid-cols-3 gap-3 text-sm">
                  <Field label="Separation Type" value={detail.separation?.separation_type} />
                  <Field label="Resignation Date" value={formatDate(detail.separation?.resignation_date)} />
                  <Field label="Notice Period (Days)" value={detail.separation?.notice_period_days} />
                  <Field label="Last Working Date" value={formatDate(detail.separation?.last_working_date)} />
                  <Field label="Reason" value={detail.separation?.reason} />
                  <Field label="Full & Final Status" value={detail.separation?.full_final_status} />
                  <Field label="Exit Interview Done" value={detail.separation?.exit_interview_done ? "Yes" : "No"} />
                  <Field label="Asset Return Done" value={detail.separation?.asset_return_done ? "Yes" : "No"} />
                  <Field label="Clearance Done" value={detail.separation?.clearance_done ? "Yes" : "No"} />
                  <Field label="Document Issuance Done" value={detail.separation?.document_issuance_done ? "Yes" : "No"} />
                  <Field label="Remarks" value={detail.separation?.remarks} />
                </div>
              </div>
            )}

            {episode.status !== "ACTIVE" && episode.status !== "NOTICE_PERIOD" && episode.status !== "SEPARATED" && (
              <p className="text-sm text-ink/40 py-6 text-center">Exit is only applicable once an employee is Active.</p>
            )}
          </div>
        )}

        {tab === "Audit History" && (
          <div className="space-y-2 text-sm">
            {audit.length === 0 && <p className="text-ink/40">No audit entries yet.</p>}
            {audit.map((a, i) => (
              <div key={i} className="border border-ink/10 rounded-md p-3">
                <div className="flex justify-between">
                  <span className="font-medium">{a.action.replace(/_/g, " ")} — {a.entity.replace(/_/g, " ")}</span>
                  <span className="text-ink/40 text-xs">{formatDateTime(a.timestamp)}</span>
                </div>
                <div className="text-ink/50 text-xs mt-1">
                  by {a.username} ({a.role})
                  {a.old_value || a.new_value ? ` — ${a.old_value ?? "—"} → ${a.new_value ?? "—"}` : ""}
                </div>
              </div>
            ))}
          </div>
        )}
      </Card>
    </div>
  );
}

function Field({ label, value }) {
  return (
    <div>
      <div className="text-xs text-ink/40">{label}</div>
      <div className="text-ink">{value || "—"}</div>
    </div>
  );
}
