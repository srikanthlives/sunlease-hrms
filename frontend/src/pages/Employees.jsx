import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { SlidersHorizontal, X, Upload, Download } from "lucide-react";
import client, { apiErrorMessage } from "../api/client";
import { Card, Button, Input, Select, Table, StatusBadge, formatDate } from "../components/ui";

const ALL_COLUMNS = [
  { key: "employee_number", header: "Employee No.", sortable: true, defaultVisible: true },
  {
    key: "name", header: "Name", sortable: true, defaultVisible: true,
    sortAccessor: (r) => `${r.last_name} ${r.first_name}`,
    render: (r) => `${r.first_name} ${r.last_name}`,
  },
  { key: "designation", header: "Designation", sortable: true, defaultVisible: true, render: (r) => r.designation || "—" },
  { key: "cost_center", header: "Cost Center", sortable: true, defaultVisible: true, render: (r) => r.cost_center || "—" },
  { key: "department", header: "Department", sortable: true, defaultVisible: true, render: (r) => r.department || "—" },
  { key: "status", header: "Status", sortable: true, defaultVisible: true, render: (r) => <StatusBadge status={r.status} /> },
  { key: "employment_type", header: "Employment Type", sortable: true, defaultVisible: false, render: (r) => r.employment_type || "—" },
  { key: "employee_category", header: "Category", sortable: true, defaultVisible: false, render: (r) => r.employee_category || "—" },
  { key: "date_of_joining", header: "Date of Joining", sortable: true, defaultVisible: false, render: (r) => formatDate(r.date_of_joining) },
  { key: "work_location", header: "Work Location", sortable: true, defaultVisible: false, render: (r) => r.work_location || "—" },
  { key: "gender", header: "Gender", sortable: true, defaultVisible: false, render: (r) => r.gender || "—" },
  { key: "mobile_number", header: "Mobile", sortable: true, defaultVisible: false, render: (r) => r.mobile_number || "—" },
  { key: "official_email", header: "Official Email", sortable: true, defaultVisible: false, render: (r) => r.official_email || "—" },
];

const STATUS_OPTIONS = ["DRAFT", "PENDING_APPROVAL", "ACTIVE", "INACTIVE", "SUSPENDED", "NOTICE_PERIOD", "SEPARATED"];

const VISIBLE_COLUMNS_KEY = "hrms_employees_visible_columns";

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
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [creating, setCreating] = useState(false);
  const [columnsOpen, setColumnsOpen] = useState(false);
  const [visibleColumns, setVisibleColumns] = useState(loadVisibleColumns);
  const [bulkOpen, setBulkOpen] = useState(false);
  const [bulkFile, setBulkFile] = useState(null);
  const [bulkUploading, setBulkUploading] = useState(false);
  const [bulkResult, setBulkResult] = useState(null);
  const [bulkError, setBulkError] = useState("");

  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState("");
  const [costCenterFilter, setCostCenterFilter] = useState("");
  const [departmentFilter, setDepartmentFilter] = useState("");
  const [employmentTypeFilter, setEmploymentTypeFilter] = useState("");
  const [categoryFilter, setCategoryFilter] = useState("");

  function reload() {
    setLoading(true);
    client.get("/employees").then((res) => setRows(res.data)).finally(() => setLoading(false));
  }

  useEffect(reload, []);

  useEffect(() => {
    localStorage.setItem(VISIBLE_COLUMNS_KEY, JSON.stringify([...visibleColumns]));
  }, [visibleColumns]);

  async function createDraft() {
    setCreating(true);
    setError("");
    try {
      const res = await client.post("/employees/draft");
      navigate(`/employees/${res.data.episode_id}/wizard`);
    } catch (err) {
      setError(apiErrorMessage(err));
    } finally {
      setCreating(false);
    }
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

  const columns = ALL_COLUMNS.filter((c) => visibleColumns.has(c.key));
  const filtersActive = search || statusFilter || costCenterFilter || departmentFilter || employmentTypeFilter || categoryFilter;

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-display font-semibold text-ink">Employees</h1>
          <p className="text-sm text-ink/50 mt-1">Employee Data Management — Module 1</p>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" onClick={() => setBulkOpen(true)} className="gap-1.5">
            <Upload size={14} /> Bulk Upload
          </Button>
          <Button onClick={createDraft} disabled={creating}>
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

        {loading ? (
          <div className="text-sm text-ink/40 py-10 text-center">Loading…</div>
        ) : (
          <Table
            columns={columns}
            rows={filteredRows}
            keyField="episode_id"
            empty={rows.length === 0 ? "No employees yet." : "No employees match the current filters."}
            onRowClick={(r) => navigate(r.status === "DRAFT" ? `/employees/${r.episode_id}/wizard` : `/employees/${r.episode_id}`)}
          />
        )}
      </Card>

      {bulkOpen && (
        <div className="fixed inset-0 bg-black/30 flex items-center justify-center z-50" onClick={closeBulkModal}>
          <div className="bg-white rounded-lg p-5 w-full max-w-lg" onClick={(e) => e.stopPropagation()}>
            <h3 className="text-sm font-semibold text-ink mb-1">Bulk Upload Employees</h3>
            <p className="text-xs text-ink/50 mb-4">
              Each row creates a Draft employee — same starting point as "New Employee" — with Personal, Address,
              Employment, and Organizational Assignment fields filled in. Statutory, Bank, Documents, Dependents,
              Nominees, and Driving Licence are completed afterwards per-employee in the wizard.
            </p>

            <Button variant="outline" size="sm" onClick={downloadTemplate} className="gap-1.5 mb-4">
              <Download size={14} /> Download Sample Template (.xlsx)
            </Button>

            {bulkError && <div className="text-sm text-danger bg-danger/10 rounded-md px-3 py-2 mb-3">{bulkError}</div>}

            {bulkResult && (
              <div className="mb-4 text-sm">
                <div className="text-ok font-medium mb-1">{bulkResult.created} employee{bulkResult.created === 1 ? "" : "s"} created as Draft.</div>
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
    </div>
  );
}
