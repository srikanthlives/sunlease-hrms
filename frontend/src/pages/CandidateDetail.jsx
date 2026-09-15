import { useEffect, useRef, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { Paperclip, Upload } from "lucide-react";
import client, { apiErrorMessage } from "../api/client";
import { Card, Button, Input, Select, Table, StatusBadge, SectionDivider, formatAadhaar, formatDate } from "../components/ui";
import DocumentPreviewModal from "../components/DocumentPreviewModal";

const RESULT_OPTIONS = ["PENDING", "PASS", "FAIL"];

// Mirrors backend/app/core/validators.py - kept in sync manually since the
// frontend and backend don't share a validation layer. Only checked when
// the field is non-empty (all three are optional).
const MOBILE_REGEX = /^[6-9][0-9]{9}$/;
const AADHAAR_REGEX = /^[2-9][0-9]{11}$/;
const PAN_REGEX = /^[A-Z]{5}[0-9]{4}[A-Z]$/;

function formatError(value, regex, message) {
  return value && !regex.test(value) ? message : undefined;
}

const EDIT_FIELDS = [
  "first_name", "middle_name", "last_name", "father_husband_name", "gender", "date_of_birth",
  "mobile_number", "alternate_mobile_number", "personal_email", "educational_qualification",
  "aadhaar", "aadhaar_name", "aadhaar_dob", "pan", "pan_name", "pan_dob",
  "current_designation", "current_company_name", "current_company_details", "current_date_of_joining", "total_experience_years",
  "dl_licence_number", "dl_badge_number", "dl_vehicle_class", "dl_issuing_authority", "dl_issue_date", "dl_expiry_date",
  "applied_designation_id", "applied_employee_category_id", "applied_cost_center_id", "applied_project_id",
  "applied_date", "source", "remarks",
];

export default function CandidateDetail() {
  const { candidateId } = useParams();
  const navigate = useNavigate();
  const [candidate, setCandidate] = useState(null);
  const [components, setComponents] = useState([]);
  const [designations, setDesignations] = useState([]);
  const [categories, setCategories] = useState([]);
  const [costCenters, setCostCenters] = useState([]);
  const [projects, setProjects] = useState([]);
  const [pendingChanges, setPendingChanges] = useState([]);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [salaryRows, setSalaryRows] = useState([]);
  const [convertForm, setConvertForm] = useState({ employee_number: "", date_of_joining: "" });
  const [docUploadingId, setDocUploadingId] = useState(null);
  const [docError, setDocError] = useState("");
  const [previewDoc, setPreviewDoc] = useState(null);
  const [editing, setEditing] = useState(false);
  const [editForm, setEditForm] = useState(null);

  function reload() {
    client.get(`/recruitment/candidates/${candidateId}`)
      .then((res) => {
        setCandidate(res.data);
        setSalaryRows(res.data.salary_components.map((s) => ({ component_id: String(s.component_id), amount: s.amount ?? "", percentage: s.percentage ?? "", formula: s.formula ?? "" })));
      })
      .catch((err) => setError(apiErrorMessage(err)));
    client.get("/recruitment/candidates-change-requests", { params: { candidate_id: candidateId, status_: "PENDING" } })
      .then((res) => setPendingChanges(res.data))
      .catch(() => {});
  }
  useEffect(reload, [candidateId]);

  useEffect(() => {
    client.get("/payroll/components").then((res) => setComponents(res.data));
    client.get("/designations").then((res) => setDesignations(res.data));
    client.get("/employee-categories").then((res) => setCategories(res.data));
    client.get("/cost-centers").then((res) => setCostCenters(res.data));
    client.get("/projects").then((res) => setProjects(res.data));
  }, []);

  async function saveResult(row, result) {
    if ((result === "PASS" || result === "FAIL") && !row.attachment_file_name) {
      const proceed = window.confirm(
        `No proof document is attached for "${row.criteria_name}". Do you really want to mark this ${result}?`,
      );
      if (!proceed) return;
    }
    setError("");
    try {
      await client.post(`/recruitment/candidates/${candidateId}/stage-results`, {
        criteria_id: row.criteria_id, result, tested_on: new Date().toISOString().slice(0, 10),
      });
      reload();
    } catch (err) {
      setError(apiErrorMessage(err));
    }
  }

  async function uploadProof(criteriaId, file) {
    if (!file) return;
    setError("");
    try {
      const form = new FormData();
      form.append("file", file);
      await client.post(`/recruitment/candidates/${candidateId}/stage-results/${criteriaId}/attachment`, form);
      reload();
    } catch (err) {
      setError(apiErrorMessage(err));
    }
  }

  async function downloadProof(criteriaId, fileName) {
    setError("");
    try {
      const res = await client.get(`/recruitment/candidates/${candidateId}/stage-results/${criteriaId}/attachment`, { responseType: "blob" });
      const url = URL.createObjectURL(res.data);
      const a = document.createElement("a");
      a.href = url;
      a.download = fileName || "proof";
      a.click();
      URL.revokeObjectURL(url);
    } catch (err) {
      setError(apiErrorMessage(err));
    }
  }

  function addSalaryRow() {
    setSalaryRows([...salaryRows, { component_id: "", amount: "", percentage: "", formula: "" }]);
  }

  function updateSalaryRow(idx, field, value) {
    const next = [...salaryRows];
    next[idx] = { ...next[idx], [field]: value };
    setSalaryRows(next);
  }

  function removeSalaryRow(idx) {
    setSalaryRows(salaryRows.filter((_, i) => i !== idx));
  }

  async function saveSalary() {
    setError("");
    setBusy(true);
    try {
      const payload = salaryRows
        .filter((r) => r.component_id)
        .map((r) => ({
          component_id: Number(r.component_id),
          amount: r.amount !== "" ? Number(r.amount) : null,
          percentage: r.percentage !== "" ? Number(r.percentage) : null,
          formula: r.formula || null,
        }));
      await client.put(`/recruitment/candidates/${candidateId}/salary-components`, payload);
      reload();
    } catch (err) {
      setError(apiErrorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  async function submitForApproval() {
    setError("");
    setBusy(true);
    try {
      await client.post(`/recruitment/candidates/${candidateId}/submit`);
      reload();
    } catch (err) {
      setError(apiErrorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  async function approveSubmission() {
    setError("");
    setBusy(true);
    try {
      await client.post(`/recruitment/candidates/${candidateId}/approve`);
      reload();
    } catch (err) {
      setError(apiErrorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  async function returnForCorrection() {
    if (!window.confirm("Send this candidate back to Applied for correction?")) return;
    setError("");
    setBusy(true);
    try {
      await client.post(`/recruitment/candidates/${candidateId}/reject`);
      reload();
    } catch (err) {
      setError(apiErrorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  async function disqualifyCandidate() {
    if (!window.confirm("Disqualify this candidate? This removes them from consideration entirely.")) return;
    setBusy(true);
    try {
      await client.post(`/recruitment/candidates/${candidateId}/disqualify`);
      reload();
    } catch (err) {
      setError(apiErrorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  function startEdit() {
    const form = {};
    for (const f of EDIT_FIELDS) form[f] = candidate[f] ?? "";
    setEditForm(form);
    setEditing(true);
  }

  async function saveEdit() {
    setError("");
    setBusy(true);
    try {
      const payload = {
        ...editForm,
        date_of_birth: editForm.date_of_birth || null,
        aadhaar_dob: editForm.aadhaar_dob || null,
        pan_dob: editForm.pan_dob || null,
        current_date_of_joining: editForm.current_date_of_joining || null,
        applied_date: editForm.applied_date || null,
        dl_issue_date: editForm.dl_issue_date || null,
        dl_expiry_date: editForm.dl_expiry_date || null,
        total_experience_years: editForm.total_experience_years === "" ? null : Number(editForm.total_experience_years),
        applied_designation_id: Number(editForm.applied_designation_id),
        applied_employee_category_id: editForm.applied_employee_category_id ? Number(editForm.applied_employee_category_id) : null,
        applied_cost_center_id: Number(editForm.applied_cost_center_id),
        applied_project_id: editForm.applied_project_id ? Number(editForm.applied_project_id) : null,
      };
      const res = await client.put(`/recruitment/candidates/${candidateId}`, payload);
      setEditing(false);
      if (res.data.submitted_for_approval) {
        window.alert("This candidate is already Approved — your changes were submitted as a Change Request and need approval before they take effect.");
      }
      reload();
    } catch (err) {
      setError(apiErrorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  async function uploadDocument(documentTypeId, file) {
    if (!file) return;
    setDocUploadingId(documentTypeId);
    setDocError("");
    try {
      const form = new FormData();
      form.append("document_type_id", documentTypeId);
      form.append("file", file);
      await client.post(`/recruitment/candidates/${candidateId}/documents`, form);
      reload();
    } catch (err) {
      setDocError(apiErrorMessage(err));
    } finally {
      setDocUploadingId(null);
    }
  }

  async function removeDocument(documentId) {
    setDocError("");
    try {
      const res = await client.delete(`/recruitment/candidates/${candidateId}/documents/${documentId}`);
      if (res.data.submitted_for_approval) {
        window.alert("This candidate is already Approved — the deletion was submitted as a Change Request and needs approval before it takes effect.");
      }
      reload();
    } catch (err) {
      setDocError(apiErrorMessage(err));
    }
  }

  async function downloadDocument(documentId, fileName) {
    const res = await client.get(`/recruitment/candidates/${candidateId}/documents/${documentId}/download`, { responseType: "blob" });
    const url = URL.createObjectURL(res.data);
    const a = document.createElement("a");
    a.href = url;
    a.download = fileName || "document";
    a.click();
    URL.revokeObjectURL(url);
  }

  async function convert() {
    setError("");
    setBusy(true);
    try {
      const res = await client.post(`/recruitment/candidates/${candidateId}/convert`, convertForm);
      navigate(`/employees/${res.data.episode_id}/wizard`);
    } catch (err) {
      setError(apiErrorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  if (!candidate) return <div className="text-sm text-ink/40 py-10 text-center">Loading…</div>;

  const criteriaColumns = [
    { key: "sequence", header: "#" },
    { key: "criteria_name", header: "Criteria" },
    { key: "is_mandatory", header: "Mandatory", render: (r) => (r.is_mandatory ? "Yes" : "Optional") },
    { key: "result", header: "Result", render: (r) => <StatusBadge status={r.result} /> },
    { key: "tested_on", header: "Tested On", render: (r) => formatDate(r.tested_on) },
    {
      key: "proof", header: "Proof",
      render: (r) => (
        <ProofCell
          fileName={r.attachment_file_name}
          onUpload={(file) => uploadProof(r.criteria_id, file)}
          onDownload={() => downloadProof(r.criteria_id, r.attachment_file_name)}
        />
      ),
    },
    {
      key: "_actions", header: "", align: "right",
      render: (r) => (
        <div className="flex gap-1 justify-end">
          {RESULT_OPTIONS.map((opt) => (
            <Button key={opt} size="sm" variant={r.result === opt ? "accent" : "outline"} onClick={() => saveResult(r, opt)}>
              {opt}
            </Button>
          ))}
        </div>
      ),
    },
  ];

  const isApplied = candidate.status === "APPLIED";
  const isPendingApproval = candidate.status === "PENDING_APPROVAL";
  const isApproved = candidate.status === "APPROVED";
  const isConverted = candidate.status === "CONVERTED";
  const isRejected = candidate.status === "REJECTED";
  const isTerminal = isConverted || isRejected;
  const canRecordCriteria = isApproved;

  return (
    <div className="space-y-6">
      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-xl font-display font-semibold text-ink">
            {candidate.first_name} {candidate.last_name} · {candidate.reference_number}
          </h1>
          <p className="text-sm text-ink/50 mt-1">
            Applied for {candidate.designation_name} at {candidate.cost_center_name} · <StatusBadge status={candidate.status} />
          </p>
        </div>
        <Button variant="outline" onClick={() => navigate("/recruitment/candidates")}>Back to Candidates</Button>
      </div>
      {error && <div className="text-sm text-danger bg-danger/10 rounded-md px-3 py-2">{error}</div>}

      {isConverted && (
        <div className="text-sm text-brand-700 bg-brand-50 rounded-md px-3 py-2">
          Converted to employee — episode #{candidate.converted_episode_id}.{" "}
          <button className="underline" onClick={() => navigate(`/employees/${candidate.converted_episode_id}`)}>View employee record</button>
        </div>
      )}

      {pendingChanges.length > 0 && (
        <div className="text-sm text-amber-800 bg-amber-50 border border-amber-200 rounded-md px-3 py-2">
          <strong>{pendingChanges.length} pending change request{pendingChanges.length > 1 ? "s" : ""}</strong> awaiting approval —{" "}
          <button className="underline" onClick={() => navigate("/recruitment/change-requests")}>review them here</button>.
        </div>
      )}

      {candidate.aadhaar_duplicate_warning?.length > 0 && (
        <div className="text-sm text-amber-800 bg-amber-50 border border-amber-200 rounded-md px-3 py-2">
          <strong>Aadhaar number warning</strong> — this candidate's Aadhaar also matches:
          <ul className="list-disc list-inside mt-1">
            {candidate.aadhaar_duplicate_warning.map((w, i) => <li key={i}>{w}</li>)}
          </ul>
        </div>
      )}

      {!isTerminal && (
        <Card>
          <h2 className="text-sm font-semibold text-ink mb-3">Workflow</h2>
          <div className="flex flex-wrap gap-2">
            {isApplied && (
              <Button variant="accent" onClick={submitForApproval} disabled={busy}>Submit for Approval</Button>
            )}
            {isPendingApproval && (
              <>
                <Button variant="accent" onClick={approveSubmission} disabled={busy}>Approve</Button>
                <Button variant="outline" onClick={returnForCorrection} disabled={busy}>Send Back for Correction</Button>
              </>
            )}
            <Button variant="danger" onClick={disqualifyCandidate} disabled={busy}>Disqualify Candidate</Button>
          </div>
          {isApplied && <p className="text-xs text-ink/40 mt-2">Selection Criteria can't be recorded until this candidate is approved.</p>}
        </Card>
      )}

      <Card>
        <div className="flex items-center justify-between mb-3">
          <h2 className="text-sm font-semibold text-ink">Candidate Details</h2>
          {!isTerminal && !editing && <Button variant="outline" size="sm" onClick={startEdit}>Edit</Button>}
        </div>

        {editing ? (
          <CandidateEditForm
            form={editForm} setForm={setEditForm} designations={designations} categories={categories}
            costCenters={costCenters} projects={projects}
            onCancel={() => setEditing(false)} onSave={saveEdit} busy={busy}
            showDrivingLicence={candidate.driving_licence_requirement?.show}
          />
        ) : (
          <>
            <SectionDivider>Personal Information</SectionDivider>
            <div className="grid grid-cols-3 gap-3 text-sm mb-4">
              <Field label="Father's/Husband's Name" value={candidate.father_husband_name} />
              <Field label="Gender" value={candidate.gender} />
              <Field label="Date of Birth" value={formatDate(candidate.date_of_birth)} />
              <Field label="Mobile Number" value={candidate.mobile_number} />
              <Field label="Alternate Mobile Number" value={candidate.alternate_mobile_number} />
              <Field label="Email" value={candidate.personal_email} />
              <Field label="Educational Qualification" value={candidate.educational_qualification} />
            </div>

            <SectionDivider>Identity Documents</SectionDivider>
            <div className="text-xs font-semibold uppercase tracking-wide text-ink/40 mb-2">Aadhaar</div>
            <div className="grid grid-cols-3 gap-3 text-sm mb-4">
              <Field label="Name (as on Aadhaar)" value={candidate.aadhaar_name} />
              <Field label="Date of Birth (as on Aadhaar)" value={formatDate(candidate.aadhaar_dob)} />
              <Field label="Aadhaar Number" value={formatAadhaar(candidate.aadhaar)} />
            </div>
            <div className="text-xs font-semibold uppercase tracking-wide text-ink/40 mb-2">PAN</div>
            <div className="grid grid-cols-3 gap-3 text-sm mb-4">
              <Field label="Name (as on PAN)" value={candidate.pan_name} />
              <Field label="Date of Birth (as on PAN)" value={formatDate(candidate.pan_dob)} />
              <Field label="PAN Number" value={candidate.pan} />
            </div>

            <SectionDivider>Current Experience</SectionDivider>
            <div className="grid grid-cols-3 gap-3 text-sm mb-4">
              <Field label="Current Designation" value={candidate.current_designation} />
              <Field label="Current Company Name" value={candidate.current_company_name} />
              <Field label="Date of Joining (Current Company)" value={formatDate(candidate.current_date_of_joining)} />
              <Field label="Total Experience" value={candidate.total_experience_years != null ? `${candidate.total_experience_years} years` : null} />
              <Field label="Current Company Details" value={candidate.current_company_details} />
            </div>

            <SectionDivider>Employment Information</SectionDivider>
            <div className="grid grid-cols-3 gap-3 text-sm mb-4">
              <Field label="Application Reference Number" value={candidate.reference_number} />
              <Field label="Employee Category" value={candidate.applied_employee_category_name} />
              <Field label="Designation" value={candidate.designation_name} />
            </div>

            <SectionDivider>Organizational Assignment</SectionDivider>
            <div className="grid grid-cols-3 gap-3 text-sm">
              <Field label="Cost Center" value={candidate.cost_center_name} />
              <Field label="Project" value={candidate.applied_project_name} />
            </div>

            {candidate.driving_licence_requirement?.show ? (
              <>
                <SectionDivider>Driving Licence</SectionDivider>
                <div className="grid grid-cols-3 gap-3 text-sm">
                  <Field label="Licence Number" value={candidate.dl_licence_number} />
                  <Field label="Badge Number" value={candidate.dl_badge_number} />
                  <Field label="Vehicle Class" value={candidate.dl_vehicle_class} />
                  <Field label="Issuing Authority" value={candidate.dl_issuing_authority} />
                  <Field label="Issue Date" value={formatDate(candidate.dl_issue_date)} />
                  <Field label="Expiry Date" value={formatDate(candidate.dl_expiry_date)} />
                </div>
              </>
            ) : (
              <p className="text-xs text-ink/40 mt-4">
                No Driving Licence requirement configured for this candidate's current Employee Category/Designation
                (Administration → Driving Licence Configuration). If you just changed the Category/Designation on an
                Approved candidate, that edit needs approval first (see the pending change request banner above) before
                this section can appear.
              </p>
            )}
          </>
        )}
      </Card>

      <Card>
        <h2 className="text-sm font-semibold text-ink mb-3">Documents</h2>
        <p className="text-xs text-ink/40 mb-3">
          Requested documents are resolved from the same Document Configuration (Employee Category/Designation) used for employees.
          {isApproved && " This candidate is Approved — deleting an uploaded document now requires HR approver review."}
        </p>
        {docError && <div className="text-sm text-danger bg-danger/10 rounded-md px-3 py-2 mb-3">{docError}</div>}
        {candidate.required_documents.length === 0 && (
          <p className="text-sm text-ink/40 py-4 text-center">No document requirements configured for this Category/Designation.</p>
        )}
        <div className="space-y-2">
          {candidate.required_documents.map((d) => (
            <div key={d.document_type_id} className="border border-ink/10 rounded-md p-3 flex items-center justify-between gap-4">
              <div className="min-w-0">
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
              <div className="flex items-center gap-2 shrink-0">
                {d.uploaded && (
                  <>
                    <Button
                      variant="outline" size="sm"
                      onClick={() => setPreviewDoc({ id: d.document_id, file_name: d.file_name, document_type: d.document_type_name })}
                    >
                      Preview
                    </Button>
                    <Button variant="outline" size="sm" onClick={() => downloadDocument(d.document_id, d.file_name)}>Download</Button>
                    {!isTerminal && (
                      <Button variant="danger" size="sm" onClick={() => removeDocument(d.document_id)}>
                        {isApproved ? "Request Deletion" : "Remove"}
                      </Button>
                    )}
                  </>
                )}
                {!isTerminal && (
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
      </Card>
      {previewDoc && (
        <DocumentPreviewModal
          basePath={`/recruitment/candidates/${candidateId}/documents`}
          document={previewDoc}
          onClose={() => setPreviewDoc(null)}
        />
      )}

      <Card>
        <h2 className="text-sm font-semibold text-ink mb-3">Selection Criteria</h2>
        {!canRecordCriteria && (
          <p className="text-sm text-ink/40 py-4 text-center">
            This candidate must be Approved before Selection Criteria can be recorded.
          </p>
        )}
        {canRecordCriteria && (
          <>
            <Table columns={criteriaColumns} rows={candidate.criteria_status} keyField="criteria_id" empty="No selection criteria configured for this designation." />
            {!candidate.all_mandatory_passed && (
              <p className="text-xs text-ink/40 mt-2">All mandatory criteria must be marked PASS before this candidate can be converted.</p>
            )}
          </>
        )}
      </Card>

      {!isTerminal && (
        <Card>
          <h2 className="text-sm font-semibold text-ink mb-3">Proposed Salary</h2>
          <div className="space-y-2">
            {salaryRows.map((row, idx) => (
              <div key={idx} className="grid grid-cols-5 gap-2 items-end">
                <Select value={row.component_id} onChange={(e) => updateSalaryRow(idx, "component_id", e.target.value)}>
                  <option value="">Component...</option>
                  {components.map((c) => <option key={c.id} value={c.id}>{c.name} ({c.code})</option>)}
                </Select>
                <Input type="number" placeholder="Amount" value={row.amount} onChange={(e) => updateSalaryRow(idx, "amount", e.target.value)} />
                <Input type="number" placeholder="Percentage" value={row.percentage} onChange={(e) => updateSalaryRow(idx, "percentage", e.target.value)} />
                <Input placeholder="Formula" value={row.formula} onChange={(e) => updateSalaryRow(idx, "formula", e.target.value)} />
                <Button variant="danger" size="sm" onClick={() => removeSalaryRow(idx)}>Remove</Button>
              </div>
            ))}
          </div>
          <div className="flex gap-2 mt-3">
            <Button variant="outline" onClick={addSalaryRow}>Add Component</Button>
            <Button onClick={saveSalary} disabled={busy}>{busy ? "Saving…" : "Save Salary"}</Button>
          </div>
        </Card>
      )}

      {!isTerminal && isApproved && (
        <Card>
          <h2 className="text-sm font-semibold text-ink mb-3">Convert to Employee</h2>
          <div className="grid grid-cols-3 gap-2">
            <Input label="Employee Number" value={convertForm.employee_number} onChange={(e) => setConvertForm({ ...convertForm, employee_number: e.target.value })} />
            <Input type="date" label="Date of Joining" value={convertForm.date_of_joining} onChange={(e) => setConvertForm({ ...convertForm, date_of_joining: e.target.value })} />
          </div>
          <Button
            className="mt-3"
            onClick={convert}
            disabled={busy || !candidate.all_mandatory_passed || !convertForm.employee_number || !convertForm.date_of_joining}
          >
            {busy ? "Converting…" : "Convert to Employee"}
          </Button>
          {!candidate.all_mandatory_passed && (
            <p className="text-xs text-ink/40 mt-2">Blocked until every mandatory selection criteria above is marked PASS.</p>
          )}
        </Card>
      )}
    </div>
  );
}

function Field({ label, value }) {
  return (
    <div>
      <div className="text-[10px] uppercase tracking-wide text-ink/40">{label}</div>
      <div className="text-ink text-sm">{value || value === 0 ? value : "—"}</div>
    </div>
  );
}

function CandidateEditForm({ form, setForm, designations, categories, costCenters, projects, onCancel, onSave, busy, showDrivingLicence }) {
  if (!form) return null;
  const set = (field) => (e) => setForm({ ...form, [field]: e.target.value });

  return (
    <div>
      <SectionDivider>Personal Information</SectionDivider>
      <div className="grid grid-cols-3 gap-2 mb-4">
        <Input label="First Name" value={form.first_name} onChange={set("first_name")} />
        <Input label="Middle Name" value={form.middle_name} onChange={set("middle_name")} />
        <Input label="Last Name" value={form.last_name} onChange={set("last_name")} />
        <Input label="Father's/Husband's Name" value={form.father_husband_name} onChange={set("father_husband_name")} />
        <Select label="Gender" value={form.gender} onChange={set("gender")}>
          <option value="">Select...</option>
          <option value="MALE">Male</option>
          <option value="FEMALE">Female</option>
          <option value="OTHER">Other</option>
        </Select>
        <Input type="date" label="Date of Birth" value={form.date_of_birth} onChange={set("date_of_birth")} />
        <Input
          label="Mobile Number" value={form.mobile_number} maxLength={10}
          onChange={(e) => setForm({ ...form, mobile_number: e.target.value.replace(/\D/g, "") })}
          error={formatError(form.mobile_number, MOBILE_REGEX, "Must be 10 digits starting with 6-9")}
        />
        <Input
          label="Alternate Mobile Number" value={form.alternate_mobile_number} maxLength={10}
          onChange={(e) => setForm({ ...form, alternate_mobile_number: e.target.value.replace(/\D/g, "") })}
          error={formatError(form.alternate_mobile_number, MOBILE_REGEX, "Must be 10 digits starting with 6-9")}
        />
        <Input label="Email" type="email" value={form.personal_email} onChange={set("personal_email")} />
        <Input label="Educational Qualification" value={form.educational_qualification} onChange={set("educational_qualification")} />
      </div>

      <SectionDivider>Identity Documents</SectionDivider>
      <div className="text-xs font-semibold uppercase tracking-wide text-ink/40 mb-2">Aadhaar</div>
      <div className="grid grid-cols-3 gap-2 mb-4">
        <Input label="Name (as on Aadhaar)" value={form.aadhaar_name} onChange={set("aadhaar_name")} />
        <Input type="date" label="Date of Birth (as on Aadhaar)" value={form.aadhaar_dob} onChange={set("aadhaar_dob")} />
        <Input
          label="Aadhaar Number" value={formatAadhaar(form.aadhaar)} maxLength={14}
          onChange={(e) => setForm({ ...form, aadhaar: e.target.value.replace(/\D/g, "").slice(0, 12) })}
          error={formatError(form.aadhaar, AADHAAR_REGEX, "Must be 12 digits, not starting with 0 or 1")}
        />
      </div>
      <div className="text-xs font-semibold uppercase tracking-wide text-ink/40 mb-2">PAN</div>
      <div className="grid grid-cols-3 gap-2 mb-4">
        <Input label="Name (as on PAN)" value={form.pan_name} onChange={set("pan_name")} />
        <Input type="date" label="Date of Birth (as on PAN)" value={form.pan_dob} onChange={set("pan_dob")} />
        <Input
          label="PAN Number" value={form.pan} maxLength={10}
          onChange={set("pan")}
          error={formatError(form.pan, PAN_REGEX, "Must be 5 letters + 4 digits + 1 letter (e.g. ABCDE1234F)")}
        />
      </div>

      <SectionDivider>Current Experience</SectionDivider>
      <div className="grid grid-cols-3 gap-2 mb-4">
        <Input label="Current Designation" value={form.current_designation} onChange={set("current_designation")} />
        <Input label="Current Company Name" value={form.current_company_name} onChange={set("current_company_name")} />
        <Input type="date" label="Date of Joining (Current Company)" value={form.current_date_of_joining} onChange={set("current_date_of_joining")} />
        <Input type="number" step="0.1" min="0" max="60" placeholder="e.g. 5.3" label="Total Experience (years)" value={form.total_experience_years} onChange={set("total_experience_years")} />
        <Input label="Current Company Details" value={form.current_company_details} onChange={set("current_company_details")} className="col-span-2" />
      </div>

      <SectionDivider>Employment Information</SectionDivider>
      <div className="grid grid-cols-3 gap-2 mb-4">
        <Select label="Employee Category" value={form.applied_employee_category_id} onChange={(e) => {
          const nextCategoryId = e.target.value;
          const currentDesignation = designations.find((d) => String(d.id) === String(form.applied_designation_id));
          const keepDesignation = currentDesignation && String(currentDesignation.employee_category_id) === String(nextCategoryId);
          setForm({ ...form, applied_employee_category_id: nextCategoryId, applied_designation_id: keepDesignation ? form.applied_designation_id : "" });
        }}>
          <option value="">Select...</option>
          {categories.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
        </Select>
        <Select label="Designation" value={form.applied_designation_id} onChange={set("applied_designation_id")}>
          <option value="">Select...</option>
          {designations
            .filter((d) => !form.applied_employee_category_id || String(d.employee_category_id) === String(form.applied_employee_category_id) || String(d.id) === String(form.applied_designation_id))
            .map((d) => <option key={d.id} value={d.id}>{d.name}</option>)}
        </Select>
        <Input type="date" label="Applied Date" value={form.applied_date} onChange={set("applied_date")} />
      </div>

      <SectionDivider>Organizational Assignment</SectionDivider>
      <div className="grid grid-cols-3 gap-2 mb-4">
        <Select label="Cost Center" value={form.applied_cost_center_id} onChange={set("applied_cost_center_id")}>
          <option value="">Select...</option>
          {costCenters.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
        </Select>
        <Select label="Project" value={form.applied_project_id} onChange={set("applied_project_id")}>
          <option value="">None</option>
          {projects.filter((p) => !form.applied_cost_center_id || p.cost_center_id === Number(form.applied_cost_center_id)).map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
        </Select>
      </div>

      {showDrivingLicence && (
        <>
          <SectionDivider>Driving Licence</SectionDivider>
          <div className="grid grid-cols-3 gap-2 mb-4">
            <Input label="Licence Number" value={form.dl_licence_number} onChange={set("dl_licence_number")} />
            <Input label="Badge Number" value={form.dl_badge_number} onChange={set("dl_badge_number")} />
            <Input label="Vehicle Class" value={form.dl_vehicle_class} onChange={set("dl_vehicle_class")} />
            <Input label="Issuing Authority" value={form.dl_issuing_authority} onChange={set("dl_issuing_authority")} />
            <Input type="date" label="Issue Date" value={form.dl_issue_date} onChange={set("dl_issue_date")} />
            <Input type="date" label="Expiry Date" value={form.dl_expiry_date} onChange={set("dl_expiry_date")} />
          </div>
        </>
      )}

      <div className="flex justify-end gap-2">
        <Button variant="outline" onClick={onCancel} disabled={busy}>Cancel</Button>
        <Button
          onClick={onSave}
          disabled={
            busy
            || !!formatError(form.mobile_number, MOBILE_REGEX, "x")
            || !!formatError(form.alternate_mobile_number, MOBILE_REGEX, "x")
            || !!formatError(form.aadhaar, AADHAAR_REGEX, "x")
            || !!formatError(form.pan, PAN_REGEX, "x")
          }
        >
          {busy ? "Saving…" : "Save"}
        </Button>
      </div>
    </div>
  );
}

function ProofCell({ fileName, onUpload, onDownload }) {
  const inputRef = useRef(null);
  const [uploading, setUploading] = useState(false);

  async function handleFile(e) {
    const file = e.target.files?.[0];
    if (!file) return;
    setUploading(true);
    await onUpload(file);
    setUploading(false);
    if (inputRef.current) inputRef.current.value = "";
  }

  return (
    <div className="flex items-center gap-2">
      {fileName ? (
        <button
          type="button"
          className="inline-flex items-center gap-1 text-xs text-brand-600 hover:underline"
          onClick={onDownload}
          title={fileName}
        >
          <Paperclip size={12} /> <span className="max-w-[100px] truncate">{fileName}</span>
        </button>
      ) : (
        <span className="text-xs text-ink/30">—</span>
      )}
      <label className="inline-flex items-center gap-1 text-xs text-ink/50 hover:text-ink/80 cursor-pointer">
        <Upload size={12} />
        <input ref={inputRef} type="file" className="hidden" onChange={handleFile} disabled={uploading} />
      </label>
    </div>
  );
}
