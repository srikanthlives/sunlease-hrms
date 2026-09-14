import { useEffect, useRef, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { Paperclip, Upload } from "lucide-react";
import client, { apiErrorMessage } from "../api/client";
import { Card, Button, Input, Select, Table, StatusBadge, SectionDivider, formatDate } from "../components/ui";
import DocumentPreviewModal from "../components/DocumentPreviewModal";

const RESULT_OPTIONS = ["PENDING", "PASS", "FAIL"];

export default function CandidateDetail() {
  const { candidateId } = useParams();
  const navigate = useNavigate();
  const [candidate, setCandidate] = useState(null);
  const [components, setComponents] = useState([]);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [salaryRows, setSalaryRows] = useState([]);
  const [convertForm, setConvertForm] = useState({ employee_number: "", date_of_joining: "" });
  const [docUploadingId, setDocUploadingId] = useState(null);
  const [docError, setDocError] = useState("");
  const [previewDoc, setPreviewDoc] = useState(null);

  function reload() {
    client.get(`/recruitment/candidates/${candidateId}`)
      .then((res) => {
        setCandidate(res.data);
        setSalaryRows(res.data.salary_components.map((s) => ({ component_id: String(s.component_id), amount: s.amount ?? "", percentage: s.percentage ?? "", formula: s.formula ?? "" })));
      })
      .catch((err) => setError(apiErrorMessage(err)));
  }
  useEffect(reload, [candidateId]);

  useEffect(() => {
    client.get("/payroll/components").then((res) => setComponents(res.data));
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

  async function approveCandidate() {
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

  async function rejectCandidate() {
    if (!window.confirm("Reject this candidate?")) return;
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
      await client.delete(`/recruitment/candidates/${candidateId}/documents/${documentId}`);
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

  const isConverted = candidate.status === "CONVERTED";
  const isRejected = candidate.status === "REJECTED";
  const isTerminal = isConverted || isRejected;

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

      {candidate.aadhaar_duplicate_warning?.length > 0 && (
        <div className="text-sm text-amber-800 bg-amber-50 border border-amber-200 rounded-md px-3 py-2">
          <strong>Aadhaar number warning</strong> — this candidate's Aadhaar also matches:
          <ul className="list-disc list-inside mt-1">
            {candidate.aadhaar_duplicate_warning.map((w, i) => <li key={i}>{w}</li>)}
          </ul>
        </div>
      )}

      <Card>
        <SectionDivider>Personal Information</SectionDivider>
        <div className="grid grid-cols-3 gap-3 text-sm mb-4">
          <Field label="Father's/Husband's Name" value={candidate.father_husband_name} />
          <Field label="Gender" value={candidate.gender} />
          <Field label="Date of Birth" value={formatDate(candidate.date_of_birth)} />
          <Field label="Mobile Number" value={candidate.mobile_number} />
          <Field label="Alternate Mobile Number" value={candidate.alternate_mobile_number} />
          <Field label="Email" value={candidate.personal_email} />
          <Field label="Educational Qualification" value={candidate.educational_qualification} />
          <Field label="Aadhaar Number" value={candidate.aadhaar} />
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
      </Card>

      <Card>
        <h2 className="text-sm font-semibold text-ink mb-3">Documents</h2>
        <p className="text-xs text-ink/40 mb-3">
          Requested documents are resolved from the same Document Configuration (Employee Category/Designation) used for employees.
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
                  <button
                    type="button"
                    className={d.uploaded ? "hover:underline" : ""}
                    disabled={!d.uploaded}
                    onClick={() => d.uploaded && setPreviewDoc({ id: d.document_id, file_name: d.file_name, document_type: d.document_type_name })}
                  >
                    {d.document_type_name}
                  </button>
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
                    <Button variant="outline" size="sm" onClick={() => downloadDocument(d.document_id, d.file_name)}>Download</Button>
                    {!isTerminal && <Button variant="danger" size="sm" onClick={() => removeDocument(d.document_id)}>Remove</Button>}
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
        <Table columns={criteriaColumns} rows={candidate.criteria_status} keyField="criteria_id" empty="No selection criteria configured for this designation." />
        {!candidate.all_mandatory_passed && (
          <p className="text-xs text-ink/40 mt-2">All mandatory criteria must be marked PASS before this candidate can be approved/converted.</p>
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

      {!isTerminal && (
        <Card>
          <h2 className="text-sm font-semibold text-ink mb-3">Actions</h2>
          <div className="flex flex-wrap gap-2 mb-4">
            {candidate.status !== "APPROVED" && (
              <Button variant="accent" onClick={approveCandidate} disabled={busy || !candidate.all_mandatory_passed}>Approve</Button>
            )}
            <Button variant="danger" onClick={rejectCandidate} disabled={busy}>Reject Candidate</Button>
          </div>

          <h3 className="text-xs font-semibold uppercase tracking-wide text-ink/50 mb-2">Convert to Employee</h3>
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
