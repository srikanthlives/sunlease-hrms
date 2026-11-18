import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { SlidersHorizontal, X, Upload, Download, Pencil, Trash2, FileText, Eye, CheckCircle2 } from "lucide-react";
import client, { apiErrorMessage } from "../api/client";
import { Card, Button, Input, Select, Table, StatusBadge, Pagination, usePagination, sortRows, formatDate } from "../components/ui";
import DocumentPreviewModal from "../components/DocumentPreviewModal";
import { useAuth } from "../context/AuthContext";
import ExportWizard from "../components/ExportWizard";
import DocumentBundleModal from "../components/DocumentBundleModal";

const ALL_COLUMNS = [
  {
    key: "employee_number", header: "Employee No.", sortable: true, defaultVisible: true,
    noTruncate: true, sticky: true, stickyWidth: 180,
  },
  {
    key: "name", header: "Name", sortable: true, defaultVisible: true, noTruncate: true,
    sticky: true, stickyWidth: 240,
    sortAccessor: (r) => `${r.last_name} ${r.first_name}`,
    render: (r) => (
      <>
        <span className="font-semibold text-ink">{`${r.first_name} ${r.last_name}`}</span>
        {r.rejoined && <span className="ml-2 text-[10px] font-medium uppercase tracking-wide text-accent-600">{r.origin === "TRANSFER" ? "Transferred in" : "Rejoined"}</span>}
      </>
    ),
  },
  { key: "designation", header: "Designation", sortable: true, defaultVisible: true, maxWidth: 160, render: (r) => r.designation || "—" },
  { key: "cost_center", header: "Cost Center", sortable: true, defaultVisible: true, maxWidth: 160, render: (r) => r.cost_center || "—" },
  { key: "department", header: "Department", sortable: true, defaultVisible: true, maxWidth: 160, render: (r) => r.department || "—" },
  { key: "status", header: "Status", sortable: true, defaultVisible: true, maxWidth: 140, render: (r) => <StatusBadge status={r.status} /> },
  {
    key: "documents", header: "Documents", sortable: true, defaultVisible: true, maxWidth: 110,
    sortAccessor: (r) => r.documents_uploaded_count,
    render: (r) => `${r.documents_uploaded_count}`, // overridden below with the actual button (needs component state)
  },
  { key: "date_of_joining", header: "Date of Joining", sortable: true, defaultVisible: true, maxWidth: 130, tooltip: (r) => formatDate(r.date_of_joining), render: (r) => formatDate(r.date_of_joining) },
  { key: "separation_date", header: "Exit Date", sortable: true, defaultVisible: true, maxWidth: 130, tooltip: (r) => formatDate(r.separation_date), render: (r) => formatDate(r.separation_date) },
  { key: "employment_type", header: "Employment Type", sortable: true, defaultVisible: false, maxWidth: 150, render: (r) => r.employment_type || "—" },
  { key: "employee_category", header: "Category", sortable: true, defaultVisible: false, maxWidth: 130, render: (r) => r.employee_category || "—" },
  { key: "work_location", header: "Work Location", sortable: true, defaultVisible: false, maxWidth: 170, render: (r) => r.work_location || "—" },
  { key: "gender", header: "Gender", sortable: true, defaultVisible: false, maxWidth: 100, render: (r) => r.gender || "—" },
  { key: "mobile_number", header: "Mobile", sortable: true, defaultVisible: false, maxWidth: 130, render: (r) => r.mobile_number || "—" },
  { key: "official_email", header: "Official Email", sortable: true, defaultVisible: false, maxWidth: 200, render: (r) => r.official_email || "—" },
  { key: "project", header: "Project", sortable: true, defaultVisible: false, maxWidth: 170, render: (r) => r.project || "—" },
  { key: "father_husband_name", header: "Father's/Husband's Name", sortable: true, defaultVisible: false, maxWidth: 190, render: (r) => r.father_husband_name || "—" },
  { key: "date_of_birth", header: "Date of Birth", sortable: true, defaultVisible: false, maxWidth: 130, render: (r) => formatDate(r.date_of_birth) },
  { key: "personal_email", header: "Personal Email", sortable: true, defaultVisible: false, maxWidth: 200, render: (r) => r.personal_email || "—" },
  { key: "alternate_mobile_number", header: "Alternate Mobile", sortable: true, defaultVisible: false, maxWidth: 140, render: (r) => r.alternate_mobile_number || "—" },
  { key: "confirmation_date", header: "Confirmation Date", sortable: true, defaultVisible: false, maxWidth: 140, render: (r) => formatDate(r.confirmation_date) },
  { key: "shift_group", header: "Shift Group", sortable: true, defaultVisible: false, maxWidth: 140, render: (r) => r.shift_group || "—" },
  { key: "application_reference_number", header: "Application Ref.", sortable: true, defaultVisible: false, maxWidth: 220, render: (r) => r.application_reference_number || "—" },
];

const STATUS_OPTIONS = ["DRAFT", "PENDING_APPROVAL", "ACTIVE", "INACTIVE", "SUSPENDED", "NOTICE_PERIOD", "SEPARATED"];

// Always-visible actions column - appended after the user-configurable
// ALL_COLUMNS set, never part of the visible-columns picker (mirrors
// AttendanceRegister.jsx's summary view "_actions" column pattern).
function makeActionsColumn(navigate, onDelete) {
  return {
    key: "_actions", header: "", align: "right",
    render: (r) => (
      <div className="flex gap-1.5 justify-end">
        <Button
          size="sm" variant="outline" className="!p-1.5" title="Edit" aria-label="Edit"
          onClick={(e) => { e.stopPropagation(); navigate(`/employees/${r.episode_id}/wizard`); }}
        >
          <Pencil size={14} />
        </Button>
        {r.status === "DRAFT" && (
          <Button
            size="sm" variant="outline" className="!p-1.5" title="Delete" aria-label="Delete"
            onClick={(e) => { e.stopPropagation(); onDelete(r); }}
          >
            <Trash2 size={14} className="text-danger" />
          </Button>
        )}
      </div>
    ),
  };
}

// Bumped (v2) so everyone picks up the new Date of Joining/Exit Date
// defaults below, instead of an already-saved column set silently
// hiding them forever.
// Bumped (v3) so everyone picks up the new Documents column default below.
const VISIBLE_COLUMNS_KEY = "hrms_employees_visible_columns_v3";

function loadVisibleColumns() {
  try {
    const raw = localStorage.getItem(VISIBLE_COLUMNS_KEY);
    if (raw) return new Set(JSON.parse(raw));
  } catch {
    // fall through to default
  }
  return new Set(ALL_COLUMNS.filter((c) => c.defaultVisible).map((c) => c.key));
}

function uniqueValues(rows, key) {
  return [...new Set(rows.map((r) => r[key]).filter(Boolean))].sort();
}

export default function Employees() {
  const navigate = useNavigate();
  const { can } = useAuth();
  const [rows, setRows] = useState([]);
  // Bulk transfer: the episode ids ticked in the list, the destination form
  // once opened, and the preflight answer that says who needs a new number.
  const [picked, setPicked] = useState([]);
  const [moveForm, setMoveForm] = useState(null);
  const [moveNumbers, setMoveNumbers] = useState({});   // episode_id -> typed number
  const [preflight, setPreflight] = useState(null);     // { employees, blocked } | null
  const [moveBusy, setMoveBusy] = useState(false);
  const [moveResult, setMoveResult] = useState(null);
  const [moveError, setMoveError] = useState("");
  const [costCenters, setCostCenters] = useState([]);
  const [projects, setProjects] = useState([]);
  const [departments, setDepartments] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [columnsOpen, setColumnsOpen] = useState(false);
  const [visibleColumns, setVisibleColumns] = useState(loadVisibleColumns);
  const [bulkOpen, setBulkOpen] = useState(false);
  const [exportOpen, setExportOpen] = useState(false);
  const [docsBundleOpen, setDocsBundleOpen] = useState(false);
  const [docsBundleResult, setDocsBundleResult] = useState(null);
  const [bulkFile, setBulkFile] = useState(null);
  const [bulkUploading, setBulkUploading] = useState(false);
  const [bulkResult, setBulkResult] = useState(null);
  const [bulkError, setBulkError] = useState("");

  const [search, setSearch] = useState("");
  // Defaults to ACTIVE - the list otherwise used to be scoped by the
  // shared Month+Cost Center global filter (a proxy for "current"
  // employees); that's gone now, so this status default does the same
  // job directly and explicitly.
  const [statusFilter, setStatusFilter] = useState("ACTIVE");
  const [costCenterFilter, setCostCenterFilter] = useState("");
  const [departmentFilter, setDepartmentFilter] = useState("");
  const [employmentTypeFilter, setEmploymentTypeFilter] = useState("");
  const [categoryFilter, setCategoryFilter] = useState("");
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(25);

  function reload() {
    setLoading(true);
    client.get("/employees").then((res) => setRows(res.data)).finally(() => setLoading(false));
  }

  useEffect(reload, []);

  useEffect(() => {
    Promise.all([client.get("/cost-centers"), client.get("/projects"), client.get("/departments")])
      .then(([cc, pr, de]) => { setCostCenters(cc.data); setProjects(pr.data); setDepartments(de.data); })
      .catch(() => {});
  }, []);

  useEffect(() => {
    localStorage.setItem(VISIBLE_COLUMNS_KEY, JSON.stringify([...visibleColumns]));
  }, [visibleColumns]);

  // No draft row is created here any more - the wizard's "new" sentinel
  // route holds Step 1 entirely in local state and only calls
  // POST /employees/draft (creating the Employee + EmploymentEpisode AND
  // saving Personal Information in one shot) once the user actually
  // clicks Save & Continue. Opening the wizard and leaving immediately no
  // longer touches the database at all - see EmployeeWizard.jsx.
  function createDraft() {
    navigate("/employees/new/wizard");
  }

  async function downloadTemplate() {
    const res = await client.get("/employees-bulk-upload-template", { responseType: "blob" });
    const url = URL.createObjectURL(res.data);
    const a = document.createElement("a");
    a.href = url;
    a.download = "hrms_employee_bulk_upload_template.xlsx";
    a.click();
    URL.revokeObjectURL(url);
  }

  async function uploadBulkFile() {
    if (!bulkFile) return;
    setBulkUploading(true);
    setBulkError("");
    setBulkResult(null);
    try {
      const form = new FormData();
      form.append("file", bulkFile);
      const res = await client.post("/employees-bulk-upload", form);
      setBulkResult(res.data);
      setBulkFile(null);
      reload();
    } catch (err) {
      setBulkError(apiErrorMessage(err));
    } finally {
      setBulkUploading(false);
    }
  }

  async function deleteEmployee(row) {
    if (!window.confirm(`Delete draft employee "${row.first_name} ${row.last_name}"? This cannot be undone.`)) return;
    setError("");
    try {
      await client.delete(`/employees/${row.episode_id}`);
      reload();
    } catch (err) {
      setError(apiErrorMessage(err));
    }
  }

  function closeBulkModal() {
    setBulkOpen(false);
    setBulkFile(null);
    setBulkResult(null);
    setBulkError("");
  }

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

  function clearFilters() {
    setSearch("");
    setStatusFilter("");
    setCostCenterFilter("");
    setDepartmentFilter("");
    setEmploymentTypeFilter("");
    setCategoryFilter("");
  }

  const costCenterOptions = useMemo(() => uniqueValues(rows, "cost_center"), [rows]);
  const departmentOptions = useMemo(() => uniqueValues(rows, "department"), [rows]);
  const categoryOptions = useMemo(() => uniqueValues(rows, "employee_category"), [rows]);
  const employmentTypeOptions = useMemo(() => uniqueValues(rows, "employment_type"), [rows]);

  const filteredRows = useMemo(() => {
    const q = search.trim().toLowerCase();
    return rows.filter((r) => {
      if (q) {
        const haystack = `${r.employee_number} ${r.first_name} ${r.last_name} ${r.designation || ""}`.toLowerCase();
        if (!haystack.includes(q)) return false;
      }
      if (statusFilter && r.status !== statusFilter) return false;
      if (costCenterFilter && r.cost_center !== costCenterFilter) return false;
      if (departmentFilter && r.department !== departmentFilter) return false;
      if (employmentTypeFilter && r.employment_type !== employmentTypeFilter) return false;
      if (categoryFilter && r.employee_category !== categoryFilter) return false;
      return true;
    });
  }, [rows, search, statusFilter, costCenterFilter, departmentFilter, employmentTypeFilter, categoryFilter]);

  useEffect(() => setPage(1), [search, statusFilter, costCenterFilter, departmentFilter, employmentTypeFilter, categoryFilter]);
  const [sort, setSort] = useState(null);
  const sortedRows = useMemo(() => sortRows(filteredRows, ALL_COLUMNS, sort), [filteredRows, sort]);
  useEffect(() => setPage(1), [sort]);
  const { pageRows, page: safePage, pageCount, total } = usePagination(sortedRows, page, pageSize);

  const [docsPopup, setDocsPopup] = useState(null); // { loading, episode, required_documents }
  const [popupPreview, setPopupPreview] = useState(null); // { id, file_name, previewUrl, downloadUrl }

  async function openDocsPopup(row) {
    setDocsPopup({ loading: true, episode: row, required_documents: [] });
    try {
      const res = await client.get(`/employees/${row.episode_id}/required-documents`);
      setDocsPopup({ loading: false, episode: row, required_documents: res.data });
    } catch (err) {
      setDocsPopup({ loading: false, episode: row, required_documents: [], error: apiErrorMessage(err) });
    }
  }

  // One selection, two actions: bulk Transfer and bulk Document download.
  // Every row is tickable, because documents can be downloaded for anyone -
  // only the Transfer button narrows the selection to the ACTIVE records
  // (the only ones the backend will transfer), and says so.
  const transferable = (r) => r.status === "ACTIVE";
  const canTransfer = can("employee.separate");
  const canBundleDocuments = can("employee.documents.view");
  const canSelect = canTransfer || canBundleDocuments;

  function togglePick(id) {
    setPicked((prev) => (prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]));
  }

  // Only the Active records go to the transfer endpoint - the rest of the
  // selection is there for the document download.
  const transferIds = () => pickedRows.filter(transferable).map((r) => r.episode_id);

  function openMove() {
    setMoveError("");
    setPreflight(null);
    setMoveNumbers({});
    setMoveForm({ transfer_type: "INTERNAL", cost_center_id: "", project_id: "", department_id: "", transfer_date: "", remarks: "" });
  }

  // The destination Cost Center and date decide who needs a new number and
  // who already holds one there, so the preflight re-runs whenever either
  // changes - the dialog can't ask for the right numbers before it knows.
  useEffect(() => {
    if (!moveForm?.cost_center_id || !moveForm?.transfer_date || transferIds().length === 0) {
      setPreflight(null);
      return;
    }
    let live = true;
    client.get("/employees-transfer-preflight", {
      params: { cost_center_id: moveForm.cost_center_id, transfer_date: moveForm.transfer_date, episode_ids: transferIds().join(",") },
    })
      .then((res) => { if (live) { setPreflight(res.data); setMoveError(""); } })
      .catch((err) => { if (live) { setPreflight(null); setMoveError(apiErrorMessage(err)); } });
    return () => { live = false; };
  }, [moveForm?.cost_center_id, moveForm?.transfer_date, transferIds().join(",")]);

  async function transferSelected() {
    setMoveError("");
    setMoveBusy(true);
    try {
      const res = await client.post("/employees-transfer", {
        transfer_type: moveForm.transfer_type,
        cost_center_id: Number(moveForm.cost_center_id),
        project_id: Number(moveForm.project_id),
        department_id: Number(moveForm.department_id),
        transfer_date: moveForm.transfer_date,
        remarks: moveForm.remarks || null,
        employees: transferIds().map((id) => ({ episode_id: id, employee_number: moveNumbers[id] || null })),
      });
      setMoveResult(res.data);
      setMoveForm(null);
      setPicked([]);
      reload();
    } catch (err) {
      setMoveError(apiErrorMessage(err));
    } finally {
      setMoveBusy(false);
    }
  }

  // The header tick selects everything on THIS page, not the whole filtered
  // set - a page is what the operator can actually see and vouch for.
  const pageAllPicked = pageRows.length > 0 && pageRows.every((r) => picked.includes(r.episode_id));
  const pickedRows = rows.filter((r) => picked.includes(r.episode_id));
  const pickedTransferable = pickedRows.filter(transferable);
  const selectColumn = {
    key: "_pick",
    header: (
      <input
        type="checkbox" className="rounded border-ink/30" checked={pageAllPicked}
        title={pageAllPicked ? "Clear this page" : "Select every employee on this page"}
        onChange={() => setPicked((prev) => (pageAllPicked
          ? prev.filter((id) => !pageRows.some((r) => r.episode_id === id))
          : [...new Set([...prev, ...pageRows.map((r) => r.episode_id)])]))}
      />
    ),
    sticky: true, stickyWidth: 40, noTruncate: true,
    render: (r) => (
      <input
        type="checkbox" className="rounded border-ink/30" checked={picked.includes(r.episode_id)}
        onClick={(e) => e.stopPropagation()} onChange={() => togglePick(r.episode_id)}
        title={`Select ${r.employee_number || r.first_name}`}
      />
    ),
  };

  const preflightById = Object.fromEntries((preflight?.employees || []).map((e) => [e.episode_id, e]));
  const missingNumbers = (preflight?.employees || []).filter((e) => e.needs_new_number && !(moveNumbers[e.episode_id] || "").trim());
  const moveReady = moveForm && moveForm.cost_center_id && moveForm.project_id && moveForm.department_id
    && moveForm.transfer_date && preflight && preflight.blocked === 0 && missingNumbers.length === 0;

  // What the export wizard opens with: the filters currently narrowing this
  // list, under the keys the backend's export FILTER_KEYS expects (employees
  // filter on resolved names, which is what the list row carries).
  const exportFilters = {
    search, status: statusFilter, cost_center: costCenterFilter, department: departmentFilter,
    employment_type: employmentTypeFilter, employee_category: categoryFilter,
  };
  const exportFilterFields = [
    { key: "search", label: "Search (name, number, designation)" },
    { key: "status", label: "Status", options: STATUS_OPTIONS.map((v) => ({ value: v, label: v.replace(/_/g, " ") })) },
    { key: "cost_center", label: "Cost Center", options: costCenterOptions.map((v) => ({ value: v, label: v })) },
    { key: "department", label: "Department", options: departmentOptions.map((v) => ({ value: v, label: v })) },
    { key: "employment_type", label: "Employment Type", options: employmentTypeOptions.map((v) => ({ value: v, label: v })) },
    { key: "employee_category", label: "Employee Category", options: categoryOptions.map((v) => ({ value: v, label: v })) },
  ];

  const columns = [
    ...(canSelect ? [selectColumn] : []),
    ...ALL_COLUMNS.filter((c) => visibleColumns.has(c.key)).map((c) => (
      c.key === "documents"
        ? {
            ...c,
            render: (r) => (
              <button
                type="button"
                className="inline-flex items-center gap-1 text-xs text-brand-600 hover:underline"
                onClick={(e) => { e.stopPropagation(); openDocsPopup(r); }}
              >
                <FileText size={13} /> {r.documents_uploaded_count}
                {r.documents_all_mandatory_uploaded && <CheckCircle2 size={13} className="text-ok" title="All mandatory documents uploaded" />}
              </button>
            ),
          }
        : c
    )),
    makeActionsColumn(navigate, deleteEmployee),
  ];
  const filtersActive = search || statusFilter || costCenterFilter || departmentFilter || employmentTypeFilter || categoryFilter;

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-display font-semibold text-ink">Employees</h1>
          <p className="text-sm text-ink/50 mt-1">Employee Data Management — Module 1</p>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" onClick={() => setExportOpen(true)} className="gap-1.5">
            <Download size={14} /> Export to Excel
          </Button>
          <Button variant="outline" onClick={() => setBulkOpen(true)} className="gap-1.5">
            <Upload size={14} /> Bulk Upload
          </Button>
          <Button onClick={createDraft}>
            + New Employee
          </Button>
        </div>
      </div>
      {error && <div className="text-sm text-danger bg-danger/10 rounded-md px-3 py-2">{error}</div>}

      <Card>
        <div className="flex flex-wrap items-end gap-2 mb-4">
          <div className="w-56">
            <Input placeholder="Search name, number, designation…" value={search} onChange={(e) => setSearch(e.target.value)} />
          </div>
          <div className="w-40">
            <Select value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)}>
              <option value="">All Statuses</option>
              {STATUS_OPTIONS.map((s) => <option key={s} value={s}>{s.replace(/_/g, " ")}</option>)}
            </Select>
          </div>
          <div className="w-40">
            <Select value={costCenterFilter} onChange={(e) => setCostCenterFilter(e.target.value)}>
              <option value="">All Cost Centers</option>
              {costCenterOptions.map((c) => <option key={c} value={c}>{c}</option>)}
            </Select>
          </div>
          <div className="w-40">
            <Select value={departmentFilter} onChange={(e) => setDepartmentFilter(e.target.value)}>
              <option value="">All Departments</option>
              {departmentOptions.map((d) => <option key={d} value={d}>{d}</option>)}
            </Select>
          </div>
          <div className="w-40">
            <Select value={employmentTypeFilter} onChange={(e) => setEmploymentTypeFilter(e.target.value)}>
              <option value="">All Employment Types</option>
              {employmentTypeOptions.map((t) => <option key={t} value={t}>{t}</option>)}
            </Select>
          </div>
          <div className="w-40">
            <Select value={categoryFilter} onChange={(e) => setCategoryFilter(e.target.value)}>
              <option value="">All Categories</option>
              {categoryOptions.map((c) => <option key={c} value={c}>{c}</option>)}
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

        <div className="text-xs text-ink/40 mb-2">
          {filteredRows.length} of {rows.length} employee{rows.length === 1 ? "" : "s"}
        </div>

        {canSelect && picked.length > 0 && (
          <div className="mb-3 flex flex-wrap items-center gap-3 rounded-md border border-brand-800/20 bg-brand-50 px-3 py-2">
            <span className="text-sm font-semibold text-ink">{picked.length} selected</span>
            {canTransfer && pickedTransferable.length < picked.length && (
              <span className="text-xs text-ink/50">
                {pickedTransferable.length} of them {pickedTransferable.length === 1 ? "is" : "are"} Active — only
                those can be transferred. Documents can be downloaded for all {picked.length}.
              </span>
            )}
            <span className="ml-auto flex items-center gap-2">
              <Button variant="ghost" size="sm" onClick={() => setPicked([])} className="gap-1"><X size={14} /> Clear</Button>
              {canBundleDocuments && (
                <Button variant="outline" size="sm" onClick={() => setDocsBundleOpen(true)} className="gap-1.5">
                  <FileText size={14} /> Download Documents
                </Button>
              )}
              {canTransfer && (
                <Button size="sm" onClick={openMove} disabled={pickedTransferable.length === 0}
                  title={pickedTransferable.length === 0 ? "None of the selected employees are Active" : undefined}>
                  Transfer {pickedTransferable.length === picked.length ? "Selected" : `${pickedTransferable.length} Active`}
                </Button>
              )}
            </span>
          </div>
        )}

        {loading ? (
          <div className="text-sm text-ink/40 py-10 text-center">Loading…</div>
        ) : (
          <>
            <Table
              sort={sort} onSortChange={setSort}
              columns={columns}
              rows={pageRows}
              keyField="episode_id"
              empty={rows.length === 0 ? "No employees yet." : "No employees match the current filters."}
              onRowClick={(r) => navigate(`/employees/${r.episode_id}`)}
              singleLine
              stickyHeader
            />
            <Pagination
              page={safePage} pageCount={pageCount} total={total} pageSize={pageSize}
              onPageChange={setPage} onPageSizeChange={(n) => { setPageSize(n); setPage(1); }}
            />
          </>
        )}
      </Card>

      {exportOpen && (
        <ExportWizard
          entity="EMPLOYEE" initialFilters={exportFilters} filterFields={exportFilterFields}
          onClose={() => setExportOpen(false)}
        />
      )}

      {docsBundleOpen && (
        <DocumentBundleModal
          entity="EMPLOYEE" ids={picked}
          onClose={() => setDocsBundleOpen(false)}
          onDone={(summary) => setDocsBundleResult(summary)}
        />
      )}

      {docsBundleResult && (
        <div className="fixed inset-0 bg-black/30 flex items-center justify-center z-50" onClick={() => setDocsBundleResult(null)}>
          <div className="bg-white rounded-lg p-5 w-full max-w-md" onClick={(e) => e.stopPropagation()}>
            <h3 className="text-sm font-semibold text-ink mb-2">Download Started</h3>
            <p className="text-sm text-ink/80">
              <strong>{docsBundleResult.documents}</strong> document{docsBundleResult.documents === 1 ? "" : "s"} for{" "}
              <strong>{docsBundleResult.people}</strong> employee{docsBundleResult.people === 1 ? "" : "s"}.
            </p>
            {docsBundleResult.skipped > 0 && (
              <p className="text-xs text-ink/50 mt-2">
                {docsBundleResult.skipped} document{docsBundleResult.skipped === 1 ? " was" : "s were"} left out —
                the reasons are listed in <code>_skipped.txt</code> inside the download.
              </p>
            )}
            <div className="mt-4"><Button onClick={() => setDocsBundleResult(null)}>Close</Button></div>
          </div>
        </div>
      )}

      {moveForm && (
        <div className="fixed inset-0 bg-black/30 flex items-center justify-center z-50" onClick={() => !moveBusy && setMoveForm(null)}>
          <div className="bg-white rounded-lg p-5 w-full max-w-3xl max-h-[90vh] overflow-y-auto" onClick={(e) => e.stopPropagation()}>
            <h3 className="text-sm font-semibold text-ink mb-1">
              Transfer {pickedTransferable.length} Employee{pickedTransferable.length === 1 ? "" : "s"}
            </h3>
            <p className="text-xs text-ink/50 mb-4">
              A Cost Center change is a transfer, not an edit: exit formalities start on each current
              record and a draft record opens in the destination, each approved the usual way. Attendance
              and salary history stays behind on the old record. The whole batch is applied together — if
              any one of them cannot move, nothing does and you are told why.
            </p>
            <Select label="Transfer type" value={moveForm.transfer_type}
              onChange={(e) => setMoveForm({ ...moveForm, transfer_type: e.target.value })}>
              <option value="INTERNAL">Internal transfer — service continues, leave/gratuity retained, no final settlement</option>
              <option value="RESIGNATION">Resignation and joining elsewhere — separate service, final settlement calculated automatically on exit approval</option>
            </Select>
            <div className="grid grid-cols-2 gap-3 mt-3">
              <Select label="Transfer to Cost Center*" value={moveForm.cost_center_id}
                onChange={(e) => setMoveForm({ ...moveForm, cost_center_id: e.target.value, project_id: "" })}>
                <option value="">Select...</option>
                {costCenters.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
              </Select>
              <Select label="Project*" value={moveForm.project_id}
                onChange={(e) => setMoveForm({ ...moveForm, project_id: e.target.value })}>
                <option value="">Select...</option>
                {projects.filter((p) => String(p.cost_center_id) === String(moveForm.cost_center_id)).map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
              </Select>
              <Select label="Department*" value={moveForm.department_id}
                onChange={(e) => setMoveForm({ ...moveForm, department_id: e.target.value })}>
                <option value="">Select...</option>
                {departments.map((d) => <option key={d.id} value={d.id}>{d.name}</option>)}
              </Select>
              <Input label="Transfer date*" type="date" value={moveForm.transfer_date}
                onChange={(e) => setMoveForm({ ...moveForm, transfer_date: e.target.value })} />
            </div>
            <div className="mt-3">
              <Input label="Remarks" value={moveForm.remarks} onChange={(e) => setMoveForm({ ...moveForm, remarks: e.target.value })} />
            </div>

            <div className="mt-4 text-xs text-ink/50">
              {!preflight
                ? "Choose the destination Cost Center and the transfer date to see which of them need a new Employee Number."
                : "An Employee Number identifies a person within a Cost Center, so everyone needs their own in the destination — except anyone who served there before, whose old number comes back."}
            </div>
            <div className="mt-2 rounded-md border border-ink/10 overflow-hidden">
              <table className="w-full text-xs">
                <thead className="bg-ink/[0.03] text-left text-ink/40 uppercase tracking-wide">
                  <tr>
                    <th className="px-2 py-1.5">Employee No.</th>
                    <th className="px-2 py-1.5">Name</th>
                    <th className="px-2 py-1.5">From</th>
                    <th className="px-2 py-1.5">New Employee No.</th>
                  </tr>
                </thead>
                <tbody>
                  {pickedTransferable.map((r) => {
                    const pf = preflightById[r.episode_id];
                    return (
                      <tr key={r.episode_id} className="border-t border-ink/5">
                        <td className="px-2 py-1 font-mono">{r.employee_number || "—"}</td>
                        <td className="px-2 py-1">{r.first_name} {r.last_name}</td>
                        <td className="px-2 py-1 text-ink/50">{r.cost_center || "—"}{r.project ? ` / ${r.project}` : ""}</td>
                        <td className="px-2 py-1">
                          {!pf ? <span className="text-ink/30">—</span>
                            : pf.blocked_reason ? <span className="text-danger">{pf.blocked_reason}</span>
                            : pf.destination_employee_number ? (
                              <span className="font-mono text-ink/60" title="Served this Cost Center before — the old number comes back">
                                {pf.destination_employee_number} <span className="font-sans text-ink/40">(reused)</span>
                              </span>
                            ) : (
                              <input
                                className="w-36 rounded border border-ink/20 px-2 py-1 font-mono"
                                placeholder="Required" value={moveNumbers[r.episode_id] || ""}
                                onChange={(e) => setMoveNumbers({ ...moveNumbers, [r.episode_id]: e.target.value })}
                              />
                            )}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
            {preflight?.blocked > 0 && (
              <div className="mt-3 text-sm text-danger bg-danger/10 rounded-md px-3 py-2">
                {preflight.blocked} of {pickedTransferable.length} cannot be transferred (see the reasons above). Nothing can
                be sent until they are removed from the selection.
              </div>
            )}
            {missingNumbers.length > 0 && preflight?.blocked === 0 && (
              <div className="mt-3 text-xs text-ink/50">
                {missingNumbers.length} still need{missingNumbers.length === 1 ? "s" : ""} a new Employee Number.
              </div>
            )}
            {moveError && <div className="mt-3 text-sm text-danger bg-danger/10 rounded-md px-3 py-2">{moveError}</div>}
            <div className="flex gap-2 mt-4">
              <Button onClick={transferSelected} disabled={moveBusy || !moveReady}>
                {moveBusy ? "Transferring..." : "Confirm Transfer"}
              </Button>
              <Button variant="outline" onClick={() => setMoveForm(null)} disabled={moveBusy}>Cancel</Button>
            </div>
          </div>
        </div>
      )}

      {moveResult && (
        <div className="fixed inset-0 bg-black/30 flex items-center justify-center z-50" onClick={() => setMoveResult(null)}>
          <div className="bg-white rounded-lg p-5 w-full max-w-lg" onClick={(e) => e.stopPropagation()}>
            <h3 className="text-sm font-semibold text-ink mb-2">Transfer Started</h3>
            <p className="text-sm text-ink/80">
              <strong>{moveResult.transferred}</strong> employee{moveResult.transferred === 1 ? "" : "s"} put into
              Notice Period, each with a draft record waiting in the destination Cost Center.
            </p>
            <p className="text-xs text-ink/50 mt-2">
              Each transfer completes once the exit is approved and the new record is approved — the new record
              cannot go live before the exit is completed, so nobody ever has two live records.
            </p>
            <div className="mt-3 max-h-56 overflow-y-auto rounded-md border border-ink/10">
              <table className="w-full text-xs">
                <thead className="sticky top-0 bg-ink/[0.03] text-left text-ink/40 uppercase tracking-wide">
                  <tr><th className="px-2 py-1.5">Old No.</th><th className="px-2 py-1.5">New No.</th><th className="px-2 py-1.5"></th></tr>
                </thead>
                <tbody>
                  {(moveResult.employees || []).map((e) => (
                    <tr key={e.episode_id} className="border-t border-ink/5">
                      <td className="px-2 py-1 font-mono">{e.employee_number}</td>
                      <td className="px-2 py-1 font-mono">{e.new_employee_number}</td>
                      <td className="px-2 py-1 text-right">
                        <button className="text-brand-600 hover:underline"
                          onClick={() => { setMoveResult(null); navigate(`/employees/${e.new_episode_id}`); }}>
                          Open new record
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <div className="mt-4"><Button onClick={() => setMoveResult(null)}>Close</Button></div>
          </div>
        </div>
      )}

      {bulkOpen && (
        <div className="fixed inset-0 bg-black/30 flex items-center justify-center z-50" onClick={closeBulkModal}>
          <div className="bg-white rounded-lg p-5 w-full max-w-lg" onClick={(e) => e.stopPropagation()}>
            <h3 className="text-sm font-semibold text-ink mb-1">Bulk Upload Employees</h3>
            <p className="text-xs text-ink/50 mb-4">
              Each row creates a Draft employee — same starting point as "New Employee" — with Personal, Address,
              Employment, and Organizational Assignment fields filled in. Statutory, Bank, Documents, Dependents,
              Nominees, and Driving Licence are completed afterwards per-employee in the wizard. The upload is all-or-nothing: if any row has an error, nothing is saved until every row is corrected.
            </p>

            <Button variant="outline" size="sm" onClick={downloadTemplate} className="gap-1.5 mb-4">
              <Download size={14} /> Download Sample Template (.xlsx)
            </Button>

            {bulkError && <div className="text-sm text-danger bg-danger/10 rounded-md px-3 py-2 mb-3">{bulkError}</div>}

            {bulkResult && (
              <div className="mb-4 text-sm">
                {bulkResult.rolled_back ? (
                  <div className="text-danger font-medium mb-1">
                    Nothing was saved. {bulkResult.errors.length} row(s) have errors ({bulkResult.valid_rows} other row(s) are fine) — correct the file and upload it again; employees are added or updated only when every row is valid.
                  </div>
                ) : (
                  <div className="text-ok font-medium mb-1">
                    {bulkResult.created} created, {bulkResult.updated || 0} updated, {bulkResult.submitted_for_approval || 0} submitted for approval.
                  </div>
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
              <Button size="sm" onClick={uploadBulkFile} disabled={!bulkFile || bulkUploading}>
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
                Documents{docsPopup.episode ? ` — ${docsPopup.episode.first_name} ${docsPopup.episode.last_name}` : ""}
              </h3>
              <Button variant="outline" size="sm" onClick={() => setDocsPopup(null)}>Close</Button>
            </div>
            {docsPopup.loading && <div className="text-sm text-ink/40 py-8 text-center">Loading…</div>}
            {docsPopup.error && <div className="text-sm text-danger bg-danger/10 rounded-md px-3 py-2">{docsPopup.error}</div>}
            {!docsPopup.loading && !docsPopup.error && (
              docsPopup.required_documents.length === 0 ? (
                <p className="text-sm text-ink/40 py-6 text-center">No document requirements configured for this employee's Type/Category/Designation.</p>
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
                            id: d.document_meta_id, file_name: d.file_name,
                            previewUrl: `/employees/${docsPopup.episode.episode_id}/documents/${d.document_meta_id}/preview`,
                            downloadUrl: `/employees/${docsPopup.episode.episode_id}/documents/${d.document_meta_id}/download`,
                          })}
                        >
                          <Eye size={14} />
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
