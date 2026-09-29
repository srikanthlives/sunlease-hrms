import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { X, Upload, Download, SlidersHorizontal, FileText, ClipboardList, Paperclip } from "lucide-react";
import client, { apiErrorMessage } from "../api/client";
import { Card, Button, Input, Select, Table, StatusBadge, SectionDivider, Pagination, usePagination, sortRows, formatAadhaar, formatDate } from "../components/ui";
import DocumentPreviewModal from "../components/DocumentPreviewModal";

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

// "COMP1/GC-SMART-PY/GCM-PRTC-50/STAFF/001" -> "../GCM-PRTC-50/STAFF/001": the
// Company and Cost Center segments are dropped from the list view (the full
// number is in the tooltip and on the candidate's page).
// "COMP1/GC-SMART-PY/GCM-PRTC-50/STAFF/001" -> prefix "../GCM-PRTC-50/STAFF",
// tail "/001" - rendered as two spans so the sequence number at the end is
// NEVER the part that gets cut off if the column is narrow; the prefix
// (Project/Category, less critical for telling candidates apart) truncates
// with an ellipsis instead.
function splitReference(ref) {
  const parts = (ref || "").split("/");
  if (parts.length <= 2) return { prefix: "", tail: ref || "—" };
  const shown = parts.slice(2);
  return { prefix: `../${shown.slice(0, -1).join("/")}`, tail: `/${shown[shown.length - 1]}` };
}

const ALL_COLUMNS = [
  {
    key: "reference_number", header: "Reference #", sortable: true, defaultVisible: true, noTruncate: true, sticky: true, stickyWidth: 280,
    render: (r) => {
      const { prefix, tail } = splitReference(r.reference_number);
      return (
        <span className="flex items-baseline" style={{ width: 220, maxWidth: 220 }} title={r.reference_number}>
          {prefix && <span className="flex-1 min-w-0 overflow-hidden text-ellipsis whitespace-nowrap">{prefix}</span>}
          <span className="flex-none">{tail}</span>
        </span>
      );
    },
  },
  {
    key: "name", header: "Name", sortable: true, defaultVisible: true, noTruncate: true, sticky: true, stickyWidth: 180,
    sortAccessor: (r) => `${r.last_name} ${r.first_name}`,
    render: (r) => <span className="font-semibold text-ink" title={`${r.first_name} ${r.last_name}`}>{`${r.first_name} ${r.last_name}`}</span>,
  },
  { key: "designation_name", header: "Applied For", sortable: true, fixedWidth: 150, defaultVisible: true, render: (r) => r.designation_name || "—" },
  { key: "cost_center_name", header: "Cost Center", sortable: true, fixedWidth: 170, defaultVisible: true, render: (r) => r.cost_center_name || "—" },
  { key: "applied_project_name", header: "Project", sortable: true, fixedWidth: 170, defaultVisible: true, render: (r) => r.applied_project_name || "—" },
  { key: "applied_employee_category_name", header: "Category", sortable: true, fixedWidth: 140, defaultVisible: true, render: (r) => r.applied_employee_category_name || "—" },
  { key: "applied_date", header: "Applied On", sortable: true, fixedWidth: 110, defaultVisible: true, tooltip: (r) => formatDate(r.applied_date), render: (r) => formatDate(r.applied_date) },
  { key: "mobile_number", header: "Mobile", sortable: true, fixedWidth: 120, defaultVisible: true, render: (r) => r.mobile_number || "—" },
  { key: "status", header: "Status", sortable: true, fixedWidth: 130, defaultVisible: true, render: (r) => <StatusBadge status={r.status} /> },
  {
    key: "documents", header: "Documents", sortable: true, defaultVisible: true, fixedWidth: 110,
    sortAccessor: (r) => r.documents_uploaded_count,
    render: (r) => `${r.documents_uploaded_count}`, // overridden below with the actual button (needs component state)
  },
  {
    key: "tests", header: "Tests", sortable: true, defaultVisible: true, fixedWidth: 110,
    sortAccessor: (r) => r.tests_recorded_count,
    render: (r) => `${r.tests_recorded_count}/${r.tests_total_count}`, // overridden below with the actual button
  },
  { key: "gender", header: "Gender", sortable: true, fixedWidth: 90, defaultVisible: false, render: (r) => r.gender || "—" },
  { key: "date_of_birth", header: "Date of Birth", sortable: true, fixedWidth: 110, defaultVisible: false, tooltip: (r) => formatDate(r.date_of_birth), render: (r) => formatDate(r.date_of_birth) },
  { key: "alternate_mobile_number", header: "Alternate Mobile", sortable: true, fixedWidth: 130, defaultVisible: false, render: (r) => r.alternate_mobile_number || "—" },
  { key: "personal_email", header: "Email", sortable: true, fixedWidth: 200, defaultVisible: false, render: (r) => r.personal_email || "—" },
  { key: "educational_qualification", header: "Qualification", sortable: true, fixedWidth: 160, defaultVisible: false, render: (r) => r.educational_qualification || "—" },
  { key: "total_experience_years", header: "Experience (yrs)", sortable: true, fixedWidth: 110, defaultVisible: false, render: (r) => (r.total_experience_years ?? "—") },
  { key: "current_designation", header: "Current Designation", sortable: true, fixedWidth: 160, defaultVisible: false, render: (r) => r.current_designation || "—" },
  { key: "current_company_name", header: "Current Company", sortable: true, fixedWidth: 180, defaultVisible: false, render: (r) => r.current_company_name || "—" },
  { key: "source", header: "Source", sortable: true, fixedWidth: 120, defaultVisible: false, render: (r) => r.source || "—" },
  { key: "remarks", header: "Remarks", sortable: true, fixedWidth: 220, defaultVisible: false, render: (r) => r.remarks || "—" },
  { key: "created_at", header: "Registered On", sortable: true, fixedWidth: 120, defaultVisible: false, tooltip: (r) => formatDate(r.created_at), render: (r) => formatDate(r.created_at) },
];

// Bumped (v2) so everyone picks up the new Documents/Tests column defaults below.
const VISIBLE_COLUMNS_KEY = "hrms_candidates_visible_columns_v2";

function loadVisibleColumns() {
  try {
    const raw = localStorage.getItem(VISIBLE_COLUMNS_KEY);
    if (raw) return new Set(JSON.parse(raw));
  } catch {
    // fall through to default
  }
  return new Set(ALL_COLUMNS.filter((c) => c.defaultVisible).map((c) => c.key));
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
  const [columnsOpen, setColumnsOpen] = useState(false);
  const [visibleColumns, setVisibleColumns] = useState(loadVisibleColumns);
  const [sort, setSort] = useState(null);
  const [docsPopup, setDocsPopup] = useState(null); // { loading, candidate, required_documents }
  const [testsPopup, setTestsPopup] = useState(null); // { loading, candidate, criteria_status }
  const [popupPreview, setPopupPreview] = useState(null); // { id, file_name, previewUrl, downloadUrl }

  async function openDocsPopup(candidateId) {
    setDocsPopup({ loading: true, candidate: null, required_documents: [] });
    try {
      const res = await client.get(`/recruitment/candidates/${candidateId}`);
      setDocsPopup({ loading: false, candidate: res.data, required_documents: res.data.required_documents || [] });
    } catch (err) {
      setDocsPopup({ loading: false, candidate: null, required_documents: [], error: apiErrorMessage(err) });
    }
  }

  async function openTestsPopup(candidateId) {
    setTestsPopup({ loading: true, candidate: null, criteria_status: [] });
    try {
      const res = await client.get(`/recruitment/candidates/${candidateId}`);
      setTestsPopup({ loading: false, candidate: res.data, criteria_status: res.data.criteria_status || [] });
    } catch (err) {
      setTestsPopup({ loading: false, candidate: null, criteria_status: [], error: apiErrorMessage(err) });
    }
  }
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
    // Always fetches every candidate regardless of the Status filter -
    // Status is applied client-side below (same as Cost Center/Project/
    // Category) so that typing a search term (name/reference/mobile/
    // Aadhaar/PAN/DL) can find a match in ANY status, not just whichever
    // one the Status dropdown currently happens to be set to.
    client.get("/recruitment/candidates").then((res) => setCandidates(res.data)).catch((err) => setError(apiErrorMessage(err)));
  }
  useEffect(reload, []);

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
        applied_employee_category_id: Number(form.applied_employee_category_id),
        applied_cost_center_id: Number(form.applied_cost_center_id),
        applied_project_id: Number(form.applied_project_id),
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

  const columns = ALL_COLUMNS.filter((c) => visibleColumns.has(c.key)).map((c) => {
    if (c.key === "documents") {
      return {
        ...c,
        render: (r) => (
          <button
            type="button"
            className="inline-flex items-center gap-1 text-xs text-brand-600 hover:underline"
            onClick={(e) => { e.stopPropagation(); openDocsPopup(r.id); }}
          >
            <FileText size={13} /> {r.documents_uploaded_count}
          </button>
        ),
      };
    }
    if (c.key === "tests") {
      return {
        ...c,
        render: (r) => (
          <button
            type="button"
            className="inline-flex items-center gap-1 text-xs text-brand-600 hover:underline"
            onClick={(e) => { e.stopPropagation(); openTestsPopup(r.id); }}
          >
            <ClipboardList size={13} /> {r.tests_recorded_count}/{r.tests_total_count}
          </button>
        ),
      };
    }
    return c;
  });

  useEffect(() => {
    localStorage.setItem(VISIBLE_COLUMNS_KEY, JSON.stringify([...visibleColumns]));
  }, [visibleColumns]);

  function toggleColumn(key) {
    setVisibleColumns((prev) => {
      const next = new Set(prev);
      next.has(key) ? next.delete(key) : next.add(key);
      return next;
    });
  }

  function resetColumns() {
    setVisibleColumns(new Set(ALL_COLUMNS.filter((c) => c.defaultVisible).map((c) => c.key)));
  }

  const searchTerm = search.trim().toLowerCase();
  const searchDigits = search.replace(/\D/g, "");
  const searchAlnum = search.trim().toUpperCase().replace(/[^A-Z0-9]/g, "");
  const visibleCandidates = candidates.filter((c) => {
    if (searchTerm) {
      const name = `${c.first_name} ${c.last_name}`.toLowerCase();
      const ref = (c.reference_number || "").toLowerCase();
      const aadhaarMatch = searchDigits.length >= 4 && (c.aadhaar || "").includes(searchDigits);
      const panMatch = searchAlnum.length >= 4 && (c.pan || "").includes(searchAlnum);
      const dlMatch = searchAlnum.length >= 4 && (c.dl_licence_number || "").toUpperCase().replace(/[^A-Z0-9]/g, "").includes(searchAlnum);
      const mobileMatch = searchDigits.length >= 4 && (c.mobile_number || "").includes(searchDigits);
      if (!name.includes(searchTerm) && !ref.includes(searchTerm) && !aadhaarMatch && !panMatch && !dlMatch && !mobileMatch) return false;
    }
    // A search term overrides the Status filter (see reload() above) -
    // finding who you're looking for matters more than staying within
    // whatever status happened to be selected.
    if (!searchTerm && statusFilter && c.status !== statusFilter) return false;
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
  const sortedCandidates = useMemo(() => sortRows(visibleCandidates, ALL_COLUMNS, sort), [visibleCandidates, sort]);
  useEffect(() => setPage(1), [sort]);
  const { pageRows, page: safePage, pageCount, total } = usePagination(sortedCandidates, page, pageSize);

  const canCreate = form.first_name && form.last_name && form.applied_designation_id
    && form.applied_employee_category_id && form.applied_cost_center_id && form.applied_project_id
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
            An Application Reference Number (Company Code / Cost Center Code / Project Code / Employee Category / Sequence)
            is generated automatically once created and used as the temp application number until converted to an employee.
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
            <Select label="Employee Category*" value={form.applied_employee_category_id} onChange={(e) => {
              const nextCategoryId = e.target.value;
              const currentDesignation = designations.find((d) => String(d.id) === String(form.applied_designation_id));
              const keepDesignation = currentDesignation && String(currentDesignation.employee_category_id) === String(nextCategoryId);
              setForm({ ...form, applied_employee_category_id: nextCategoryId, applied_designation_id: keepDesignation ? form.applied_designation_id : "" });
            }}>
              <option value="">Select...</option>
              {categories.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
            </Select>
            <Select label="Designation*" value={form.applied_designation_id} onChange={(e) => setForm({ ...form, applied_designation_id: e.target.value })}>
              <option value="">Select...</option>
              {designations
                .filter((d) => !form.applied_employee_category_id || String(d.employee_category_id) === String(form.applied_employee_category_id) || String(d.id) === String(form.applied_designation_id))
                .map((d) => <option key={d.id} value={d.id}>{d.name}</option>)}
            </Select>
            <Input type="date" label="Applied Date" value={form.applied_date} onChange={(e) => setForm({ ...form, applied_date: e.target.value })} />
          </div>

          <SectionDivider>Organizational Assignment</SectionDivider>
          <div className="grid grid-cols-3 gap-2 mb-4">
            <Select label="Cost Center*" value={form.applied_cost_center_id} onChange={(e) => setForm({ ...form, applied_cost_center_id: e.target.value })}>
              <option value="">Select...</option>
              {costCenters.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
            </Select>
            <Select label="Project*" value={form.applied_project_id} onChange={(e) => setForm({ ...form, applied_project_id: e.target.value })}>
              <option value="">Select...</option>
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
            <Input placeholder="Search by name, reference number, mobile, Aadhaar, PAN, or DL number..." value={search} onChange={(e) => setSearch(e.target.value)} noUppercase />
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

          <div className="relative ml-auto">
            <Button variant="outline" size="sm" onClick={() => setColumnsOpen((o) => !o)} className="gap-1.5">
              <SlidersHorizontal size={14} /> Columns
            </Button>
            {columnsOpen && (
              <>
                <div className="fixed inset-0 z-10" onClick={() => setColumnsOpen(false)} />
                <div className="absolute right-0 mt-2 w-56 bg-white border border-ink/10 rounded-md shadow-card z-20 p-3">
                  <div className="flex items-center justify-between mb-2">
                    <span className="text-xs font-semibold text-ink/60 uppercase tracking-wide">Show Columns</span>
                    <button className="text-xs text-brand-700 hover:underline" onClick={resetColumns}>Reset</button>
                  </div>
                  <div className="space-y-1.5 max-h-72 overflow-y-auto">
                    {ALL_COLUMNS.map((c) => (
                      <label key={c.key} className="flex items-center gap-2 text-sm text-ink/80">
                        <input type="checkbox" checked={visibleColumns.has(c.key)} onChange={() => toggleColumn(c.key)} />
                        {c.header}
                      </label>
                    ))}
                  </div>
                </div>
              </>
            )}
          </div>
        </div>
        <Table
          sort={sort} onSortChange={setSort}
          singleLine
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
              Detail page. The upload is all-or-nothing: if any row has an error (for example an Aadhaar/PAN/Driving Licence Number
              that already belongs to another candidate or employee), nothing is saved until every row is corrected.
            </p>

            <Button variant="outline" size="sm" onClick={downloadCandidateTemplate} className="gap-1.5 mb-4">
              <Download size={14} /> Download Sample Template (.xlsx)
            </Button>

            {bulkError && <div className="text-sm text-danger bg-danger/10 rounded-md px-3 py-2 mb-3">{bulkError}</div>}

            {bulkResult && (
              <div className="mb-4 text-sm">
                {bulkResult.rolled_back ? (
                  <div className="text-danger font-medium mb-1">
                    Nothing was saved. {bulkResult.errors.length} row(s) have errors ({bulkResult.valid_rows} other row(s) are fine) — correct the file and upload it again; candidates are added only when every row is valid.
                  </div>
                ) : (
                  <div className="text-ok font-medium mb-1">{bulkResult.created} created.</div>
                )}
                {bulkResult.errors.length > 0 && (
                  <div className="border border-danger/20 bg-danger/5 rounded-md p-2 max-h-40 overflow-y-auto">
                    <div className="text-xs font-medium text-danger mb-1">{bulkResult.errors.length} row(s) to fix:</div>
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

      {docsPopup && (
        <div className="fixed inset-0 bg-black/30 flex items-center justify-center z-50" onClick={() => setDocsPopup(null)}>
          <div className="bg-white rounded-lg p-5 w-full max-w-lg max-h-[80vh] overflow-y-auto" onClick={(e) => e.stopPropagation()}>
            <div className="flex items-center justify-between mb-3">
              <h3 className="text-sm font-semibold text-ink">
                Documents{docsPopup.candidate ? ` — ${docsPopup.candidate.first_name} ${docsPopup.candidate.last_name}` : ""}
              </h3>
              <Button variant="outline" size="sm" onClick={() => setDocsPopup(null)}>Close</Button>
            </div>
            {docsPopup.loading && <div className="text-sm text-ink/40 py-8 text-center">Loading…</div>}
            {docsPopup.error && <div className="text-sm text-danger bg-danger/10 rounded-md px-3 py-2">{docsPopup.error}</div>}
            {!docsPopup.loading && !docsPopup.error && (
              docsPopup.required_documents.length === 0 ? (
                <p className="text-sm text-ink/40 py-6 text-center">No document requirements configured for this candidate's Category/Designation.</p>
              ) : (
                <div className="space-y-2">
                  {docsPopup.required_documents.map((d) => (
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
                        <div className="text-xs text-ink/50 mt-0.5">{d.uploaded ? d.file_name : "—"}</div>
                      </div>
                      {d.uploaded ? (
                        <Button
                          variant="outline" size="sm" className="!p-1.5" title="Preview" aria-label="Preview"
                          onClick={() => setPopupPreview({
                            id: d.document_id, file_name: d.file_name,
                            previewUrl: `/recruitment/candidates/${docsPopup.candidate.id}/documents/${d.document_id}/preview`,
                            downloadUrl: `/recruitment/candidates/${docsPopup.candidate.id}/documents/${d.document_id}/download`,
                          })}
                        >
                          <Paperclip size={14} />
                        </Button>
                      ) : (
                        <span className="text-xs text-ink/30">Not uploaded</span>
                      )}
                    </div>
                  ))}
                </div>
              )
            )}
          </div>
        </div>
      )}

      {testsPopup && (
        <div className="fixed inset-0 bg-black/30 flex items-center justify-center z-50" onClick={() => setTestsPopup(null)}>
          <div className="bg-white rounded-lg p-5 w-full max-w-lg max-h-[80vh] overflow-y-auto" onClick={(e) => e.stopPropagation()}>
            <div className="flex items-center justify-between mb-3">
              <h3 className="text-sm font-semibold text-ink">
                Selection Criteria{testsPopup.candidate ? ` — ${testsPopup.candidate.first_name} ${testsPopup.candidate.last_name}` : ""}
              </h3>
              <Button variant="outline" size="sm" onClick={() => setTestsPopup(null)}>Close</Button>
            </div>
            {testsPopup.loading && <div className="text-sm text-ink/40 py-8 text-center">Loading…</div>}
            {testsPopup.error && <div className="text-sm text-danger bg-danger/10 rounded-md px-3 py-2">{testsPopup.error}</div>}
            {!testsPopup.loading && !testsPopup.error && (
              testsPopup.criteria_status.length === 0 ? (
                <p className="text-sm text-ink/40 py-6 text-center">No selection criteria configured for this candidate's Designation.</p>
              ) : (
                <div className="space-y-2">
                  {testsPopup.criteria_status.map((r) => (
                    <div key={r.criteria_id} className="border border-ink/10 rounded-md p-3 flex items-center justify-between gap-4">
                      <div>
                        <div className="text-sm font-medium text-ink flex items-center gap-2">
                          {r.criteria_name}
                          {r.is_mandatory ? (
                            <span className="text-[10px] font-medium px-1.5 py-0.5 rounded-full bg-danger/10 text-danger">Mandatory</span>
                          ) : (
                            <span className="text-[10px] font-medium px-1.5 py-0.5 rounded-full bg-ink/5 text-ink/50">Optional</span>
                          )}
                        </div>
                        <div className="text-xs text-ink/50 mt-0.5 flex items-center gap-2">
                          <StatusBadge status={r.result} />
                          {r.tested_on && <span>{formatDate(r.tested_on)}</span>}
                        </div>
                      </div>
                      {r.attachment_file_name ? (
                        <Button
                          variant="outline" size="sm" className="!p-1.5" title="Preview" aria-label="Preview"
                          onClick={() => setPopupPreview({
                            id: r.criteria_id, file_name: r.attachment_file_name,
                            previewUrl: `/recruitment/candidates/${testsPopup.candidate.id}/stage-results/${r.criteria_id}/attachment/preview`,
                            downloadUrl: `/recruitment/candidates/${testsPopup.candidate.id}/stage-results/${r.criteria_id}/attachment`,
                          })}
                        >
                          <Paperclip size={14} />
                        </Button>
                      ) : (
                        <span className="text-xs text-ink/30">No proof</span>
                      )}
                    </div>
                  ))}
                </div>
              )
            )}
          </div>
        </div>
      )}

      {popupPreview && (
        <DocumentPreviewModal
          document={popupPreview}
          previewUrl={popupPreview.previewUrl}
          downloadUrl={popupPreview.downloadUrl}
          onClose={() => setPopupPreview(null)}
        />
      )}
    </div>
  );
}
