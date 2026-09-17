import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { X, Upload, Download } from "lucide-react";
import client, { apiErrorMessage } from "../api/client";
import { Card, Button, Input, Select, Table, StatusBadge, SectionDivider, Pagination, usePagination, formatAadhaar, formatDate } from "../components/ui";

const STATUS_OPTIONS = ["APPLIED", "PENDING_APPROVAL", "APPROVED", "REJECTED", "CONVERTED", "WITHDRAWN"];

// Mirrors backend/app/core/validators.py - kept in sync manually since the
// frontend and backend don't share a validation layer. Only checked when
// the field is non-empty (all three are optional).
const MOBILE_REGEX = /^[6-9][0-9]{9}$/;
const AADHAAR_REGEX = /^[2-9][0-9]{11}$/;
const PAN_REGEX = /^[A-Z]{5}[0-9]{4}[A-Z]$/;

function formatError(value, regex, message) {
  return value && !regex.test(value) ? message : undefined;
}

const EMPTY_FORM = {
  first_name: "", middle_name: "", last_name: "", father_husband_name: "", gender: "", date_of_birth: "",
  mobile_number: "", alternate_mobile_number: "", personal_email: "", educational_qualification: "",
  aadhaar: "", aadhaar_name: "", aadhaar_dob: "", pan: "", pan_name: "", pan_dob: "",
  current_designation: "", current_company_name: "", current_company_details: "", current_date_of_joining: "", total_experience_years: "",
  applied_designation_id: "", applied_employee_category_id: "",
  applied_cost_center_id: "", applied_project_id: "",
  applied_date: new Date().toISOString().slice(0, 10),
};

export default function Candidates() {
  const navigate = useNavigate();
  const [candidates, setCandidates] = useState([]);
  const [designations, setDesignations] = useState([]);
  const [costCenters, setCostCenters] = useState([]);
  const [categories, setCategories] = useState([]);
  const [projects, setProjects] = useState([]);
  // Defaults to APPROVED - the most commonly-worked-with state (Selection
  // Criteria being recorded / ready to convert), same reasoning as
  // Employees defaulting to ACTIVE.
  const [statusFilter, setStatusFilter] = useState("APPROVED");
  const [costCenterFilter, setCostCenterFilter] = useState("");
  const [projectFilter, setProjectFilter] = useState("");
  const [categoryFilter, setCategoryFilter] = useState("");
  const [search, setSearch] = useState("");
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(25);
  const [error, setError] = useState("");
  const [showNew, setShowNew] = useState(false);
  const [form, setForm] = useState(EMPTY_FORM);
  const [submitting, setSubmitting] = useState(false);
  const [bulkOpen, setBulkOpen] = useState(false);
  const [bulkFile, setBulkFile] = useState(null);
  const [bulkUploading, setBulkUploading] = useState(false);
  const [bulkResult, setBulkResult] = useState(null);
  const [bulkError, setBulkError] = useState("");

  function reload() {
    const params = {};
    if (statusFilter) params.status_ = statusFilter;
    client.get("/recruitment/candidates", { params }).then((res) => setCandidates(res.data)).catch((err) => setError(apiErrorMessage(err)));
  }
  useEffect(reload, [statusFilter]);

  useEffect(() => {
    client.get("/designations").then((res) => setDesignations(res.data));
    client.get("/cost-centers").then((res) => setCostCenters(res.data));
    client.get("/employee-categories").then((res) => setCategories(res.data));
    client.get("/projects").then((res) => setProjects(res.data));
  }, []);

  async function downloadCandidateTemplate() {
    const res = await client.get("/recruitment/candidates-bulk-upload-template", { responseType: "blob" });
    const url = URL.createObjectURL(res.data);
    const a = document.createElement("a");
    a.href = url;
    a.download = "hrms_candidate_bulk_upload_template.xlsx";
    a.click();
    URL.revokeObjectURL(url);
  }

  async function uploadCandidateBulkFile() {
    if (!bulkFile) return;
    setBulkUploading(true);
    setBulkError("");
    setBulkResult(null);
    try {
      const form = new FormData();
      form.append("file", bulkFile);
      const res = await client.post("/recruitment/candidates-bulk-upload", form);
      setBulkResult(res.data);
      setBulkFile(null);
      reload();
    } catch (err) {
      setBulkError(apiErrorMessage(err));
    } finally {
      setBulkUploading(false);
    }
  }

  function closeBulkModal() {
    setBulkOpen(false);
    setBulkFile(null);
    setBulkResult(null);
    setBulkError("");
  }

  async function createCandidate() {
    setError("");
    setSubmitting(true);
    try {
      const payload = {
        ...form,
        date_of_birth: form.date_of_birth || null,
        aadhaar_dob: form.aadhaar_dob || null,
        pan_dob: form.pan_dob || null,
        current_date_of_joining: form.current_date_of_joining || null,
        total_experience_years: form.total_experience_years === "" ? null : Number(form.total_experience_years),
        applied_designation_id: Number(form.applied_designation_id),
        applied_employee_category_id: form.applied_employee_category_id ? Number(form.applied_employee_category_id) : null,
        applied_cost_center_id: Number(form.applied_cost_center_id),
        applied_project_id: form.applied_project_id ? Number(form.applied_project_id) : null,
      };
      const res = await client.post("/recruitment/candidates", payload);
      setShowNew(false);
      setForm(EMPTY_FORM);
      navigate(`/recruitment/candidates/${res.data.id}`);
    } catch (err) {
      setError(apiErrorMessage(err));
    } finally {
      setSubmitting(false);
    }
  }

  const columns = [
    { key: "reference_number", header: "Reference #", noTruncate: true, sticky: true, stickyWidth: 170 },
    { key: "name", header: "Name", noTruncate: true, sticky: true, stickyWidth: 180, render: (r) => `${r.first_name} ${r.last_name}` },
    { key: "designation_name", header: "Applied For", render: (r) => r.designation_name || "—" },
    { key: "cost_center_name", header: "Cost Center", render: (r) => r.cost_center_name || "—" },
    { key: "applied_project_name", header: "Project", render: (r) => r.applied_project_name || "—" },
    { key: "applied_employee_category_name", header: "Category", render: (r) => r.applied_employee_category_name || "—" },
    { key: "applied_date", header: "Applied On", render: (r) => formatDate(r.applied_date) },
    { key: "mobile_number", header: "Mobile", render: (r) => r.mobile_number || "—" },
    { key: "status", header: "Status", render: (r) => <StatusBadge status={r.status} /> },
  ];

  const searchTerm = search.trim().toLowerCase();
  const visibleCandidates = candidates.filter((c) => {
    if (searchTerm) {
      const name = `${c.first_name} ${c.last_name}`.toLowerCase();
      const ref = (c.reference_number || "").toLowerCase();
      if (!name.includes(searchTerm) && !ref.includes(searchTerm)) return false;
    }
    if (costCenterFilter && String(c.applied_cost_center_id) !== costCenterFilter) return false;
    if (projectFilter && String(c.applied_project_id) !== projectFilter) return false;
    if (categoryFilter && String(c.applied_employee_category_id) !== categoryFilter) return false;
    return true;
  });

  const filtersActive = search || statusFilter || costCenterFilter || projectFilter || categoryFilter;
  function clearFilters() {
    setSearch("");
    setStatusFilter("");
    setCostCenterFilter("");
    setProjectFilter("");
    setCategoryFilter("");
  }

  useEffect(() => setPage(1), [search, statusFilter, costCenterFilter, projectFilter, categoryFilter]);
  const { pageRows, page: safePage, pageCount, total } = usePagination(visibleCandidates, page, pageSize);

  const canCreate = form.first_name && form.last_name && form.applied_designation_id && form.applied_cost_center_id
    && !formatError(form.mobile_number, MOBILE_REGEX, "x")
    && !formatError(form.alternate_mobile_number, MOBILE_REGEX, "x")
    && !formatError(form.aadhaar, AADHAAR_REGEX, "x")
    && !formatError(form.pan, PAN_REGEX, "x");

  return (
    <div className="space-y-6">
      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-xl font-display font-semibold text-ink">Candidates</h1>
          <p className="text-sm text-ink/50 mt-1">Recruitment pipeline — tracked by reference number until converted to an employee.</p>
        </div>
        <div className="flex items-center gap-2">
          <Button variant="outline" onClick={() => setBulkOpen(true)} className="gap-1.5">
            <Upload size={14} /> Bulk Upload
          </Button>
          <Button onClick={() => setShowNew((s) => !s)}>{showNew ? "Cancel" : "New Candidate"}</Button>
        </div>
      </div>
      {error && <div className="text-sm text-danger bg-danger/10 rounded-md px-3 py-2">{error}</div>}

      {showNew && (
        <Card>
          <h2 className="text-sm font-semibold text-ink mb-1">New Candidate</h2>
          <p className="text-xs text-ink/40 mb-3">
            An Application Reference Number (Company Code / Cost Center Code / Project Code / Sequence) is generated
            automatically once created and used as the temp application number until converted to an employee.
          </p>

          <SectionDivider>Personal Information</SectionDivider>
          <div className="grid grid-cols-3 gap-2 mb-4">
            <Input label="First Name" value={form.first_name} onChange={(e) => setForm({ ...form, first_name: e.target.value })} />
            <Input label="Middle Name" value={form.middle_name} onChange={(e) => setForm({ ...form, middle_name: e.target.value })} />
            <Input label="Last Name" value={form.last_name} onChange={(e) => setForm({ ...form, last_name: e.target.value })} />
            <Input label="Father's/Husband's Name" value={form.father_husband_name} onChange={(e) => setForm({ ...form, father_husband_name: e.target.value })} />
            <Select label="Gender" value={form.gender} onChange={(e) => setForm({ ...form, gender: e.target.value })}>
              <option value="">Select...</option>
              <option value="MALE">Male</option>
              <option value="FEMALE">Female</option>
              <option value="OTHER">Other</option>
            </Select>
            <Input type="date" label="Date of Birth" value={form.date_of_birth} onChange={(e) => setForm({ ...form, date_of_birth: e.target.value })} />
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
            <Input label="Email" type="email" value={form.personal_email} onChange={(e) => setForm({ ...form, personal_email: e.target.value })} />
            <Input label="Educational Qualification" value={form.educational_qualification} onChange={(e) => setForm({ ...form, educational_qualification: e.target.value })} />
          </div>

          <SectionDivider>Identity Documents</SectionDivider>
          <div className="text-xs font-semibold uppercase tracking-wide text-ink/40 mb-2">Aadhaar</div>
          <div className="grid grid-cols-3 gap-2 mb-4">
            <Input label="Name (as on Aadhaar)" value={form.aadhaar_name} onChange={(e) => setForm({ ...form, aadhaar_name: e.target.value })} />
            <Input type="date" label="Date of Birth (as on Aadhaar)" value={form.aadhaar_dob} onChange={(e) => setForm({ ...form, aadhaar_dob: e.target.value })} />
            <Input
              label="Aadhaar Number" value={formatAadhaar(form.aadhaar)} maxLength={14}
              onChange={(e) => setForm({ ...form, aadhaar: e.target.value.replace(/\D/g, "").slice(0, 12) })}
              error={formatError(form.aadhaar, AADHAAR_REGEX, "Must be 12 digits, not starting with 0 or 1")}
            />
          </div>
          <div className="text-xs font-semibold uppercase tracking-wide text-ink/40 mb-2">PAN</div>
          <div className="grid grid-cols-3 gap-2 mb-4">
            <Input label="Name (as on PAN)" value={form.pan_name} onChange={(e) => setForm({ ...form, pan_name: e.target.value })} />
            <Input type="date" label="Date of Birth (as on PAN)" value={form.pan_dob} onChange={(e) => setForm({ ...form, pan_dob: e.target.value })} />
            <Input
              label="PAN Number" value={form.pan} maxLength={10}
              onChange={(e) => setForm({ ...form, pan: e.target.value })}
              error={formatError(form.pan, PAN_REGEX, "Must be 5 letters + 4 digits + 1 letter (e.g. ABCDE1234F)")}
            />
          </div>

          <SectionDivider>Current Experience</SectionDivider>
          <div className="grid grid-cols-3 gap-2 mb-4">
            <Input label="Current Designation" value={form.current_designation} onChange={(e) => setForm({ ...form, current_designation: e.target.value })} />
            <Input label="Current Company Name" value={form.current_company_name} onChange={(e) => setForm({ ...form, current_company_name: e.target.value })} />
            <Input type="date" label="Date of Joining (Current Company)" value={form.current_date_of_joining} onChange={(e) => setForm({ ...form, current_date_of_joining: e.target.value })} />
            <Input type="number" step="0.1" min="0" max="60" placeholder="e.g. 5.3" label="Total Experience (years)" value={form.total_experience_years} onChange={(e) => setForm({ ...form, total_experience_years: e.target.value })} />
            <Input label="Current Company Details" value={form.current_company_details} onChange={(e) => setForm({ ...form, current_company_details: e.target.value })} className="col-span-2" />
          </div>

          <SectionDivider>Employment Information</SectionDivider>
          <div className="grid grid-cols-3 gap-2 mb-4">
            <Input label="Application Reference Number" value="Auto-generated on save" disabled />
            <Select label="Employee Category" value={form.applied_employee_category_id} onChange={(e) => setForm({ ...form, applied_employee_category_id: e.target.value })}>
              <option value="">Select...</option>
              {categories.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
            </Select>
            <Select label="Designation" value={form.applied_designation_id} onChange={(e) => setForm({ ...form, applied_designation_id: e.target.value })}>
              <option value="">Select...</option>
              {designations.map((d) => <option key={d.id} value={d.id}>{d.name}</option>)}
            </Select>
            <Input type="date" label="Applied Date" value={form.applied_date} onChange={(e) => setForm({ ...form, applied_date: e.target.value })} />
          </div>

          <SectionDivider>Organizational Assignment</SectionDivider>
          <div className="grid grid-cols-3 gap-2 mb-4">
            <Select label="Cost Center" value={form.applied_cost_center_id} onChange={(e) => setForm({ ...form, applied_cost_center_id: e.target.value })}>
              <option value="">Select...</option>
              {costCenters.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
            </Select>
            <Select label="Project" value={form.applied_project_id} onChange={(e) => setForm({ ...form, applied_project_id: e.target.value })}>
              <option value="">None</option>
              {projects.filter((p) => !form.applied_cost_center_id || p.cost_center_id === Number(form.applied_cost_center_id)).map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
            </Select>
          </div>

          <Button onClick={createCandidate} disabled={!canCreate || submitting}>{submitting ? "Creating…" : "Create Candidate"}</Button>
          <p className="text-xs text-ink/40 mt-2">
            Documents and Driving Licence details (if required for the selected Designation/Category) can be added from
            the candidate's page after creation.
          </p>
        </Card>
      )}

      <Card>
        <div className="flex flex-wrap items-end gap-2 mb-3">
          <div className="w-64">
            <Input placeholder="Search by name or reference number..." value={search} onChange={(e) => setSearch(e.target.value)} noUppercase />
          </div>
          <div className="w-44">
            <Select value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)}>
              <option value="">All Statuses</option>
              {STATUS_OPTIONS.map((s) => <option key={s} value={s}>{s.replace(/_/g, " ")}</option>)}
            </Select>
          </div>
          <div className="w-44">
            <Select value={costCenterFilter} onChange={(e) => setCostCenterFilter(e.target.value)}>
              <option value="">All Cost Centers</option>
              {costCenters.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
            </Select>
          </div>
          <div className="w-44">
            <Select value={projectFilter} onChange={(e) => setProjectFilter(e.target.value)}>
              <option value="">All Projects</option>
              {projects.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
            </Select>
          </div>
          <div className="w-44">
            <Select value={categoryFilter} onChange={(e) => setCategoryFilter(e.target.value)}>
              <option value="">All Categories</option>
              {categories.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
            </Select>
          </div>
          {filtersActive && (
            <Button variant="ghost" size="sm" onClick={clearFilters} className="gap-1">
              <X size={14} /> Clear
            </Button>
          )}
        </div>
        <Table
          columns={columns} rows={pageRows} onRowClick={(r) => navigate(`/recruitment/candidates/${r.id}`)}
          empty={candidates.length === 0 ? "No candidates yet." : "No candidates match the current filters."}
          stickyHeader
        />
        <Pagination
          page={safePage} pageCount={pageCount} total={total} pageSize={pageSize}
          onPageChange={setPage} onPageSizeChange={(n) => { setPageSize(n); setPage(1); }}
        />
      </Card>

      {bulkOpen && (
        <div className="fixed inset-0 bg-black/30 flex items-center justify-center z-50" onClick={closeBulkModal}>
          <div className="bg-white rounded-lg p-5 w-full max-w-lg" onClick={(e) => e.stopPropagation()}>
            <h3 className="text-sm font-semibold text-ink mb-1">Bulk Upload Candidates</h3>
            <p className="text-xs text-ink/50 mb-4">
              Each row creates a new candidate — same as "New Candidate" — with Personal Info, Identity Documents,
              Current Experience, Applied Designation/Cost Center/Category/Project, and Driving Licence details
              filled in. Documents and Selection Criteria are completed afterwards per-candidate on the Candidate
              Detail page. Rows with an Aadhaar/PAN/Driving Licence Number that already belongs to another
              candidate or employee are skipped with an error, same as adding one candidate manually.
            </p>

            <Button variant="outline" size="sm" onClick={downloadCandidateTemplate} className="gap-1.5 mb-4">
              <Download size={14} /> Download Sample Template (.xlsx)
            </Button>

            {bulkError && <div className="text-sm text-danger bg-danger/10 rounded-md px-3 py-2 mb-3">{bulkError}</div>}

            {bulkResult && (
              <div className="mb-4 text-sm">
                <div className="text-ok font-medium mb-1">{bulkResult.created} created.</div>
                {bulkResult.errors.length > 0 && (
                  <div className="border border-danger/20 bg-danger/5 rounded-md p-2 max-h-40 overflow-y-auto">
                    <div className="text-xs font-medium text-danger mb-1">{bulkResult.errors.length} row(s) skipped:</div>
                    {bulkResult.errors.map((e, i) => (
                      <div key={i} className="text-xs text-ink/60">Row {e.row}: {e.message}</div>
                    ))}
                  </div>
                )}
              </div>
            )}

            <div className="flex items-center gap-2">
              <input
                type="file"
                accept=".xlsx"
                onChange={(e) => { setBulkFile(e.target.files[0]); setBulkResult(null); setBulkError(""); }}
                className="text-xs flex-1"
              />
              <Button size="sm" onClick={uploadCandidateBulkFile} disabled={!bulkFile || bulkUploading}>
                {bulkUploading ? "Uploading…" : "Upload"}
              </Button>
            </div>

            <div className="flex justify-end mt-4">
              <Button variant="outline" onClick={closeBulkModal}>Close</Button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
