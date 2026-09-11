import { useEffect, useState } from "react";
import { Upload, Download, Plus, Trash2 } from "lucide-react";
import client, { apiErrorMessage } from "../api/client";
import { Card, Button, Input, Select, Table, StatusBadge } from "../components/ui";
import { useGlobalFilter } from "../context/GlobalFilterContext";

const MONTH_NAMES = [
  "January", "February", "March", "April", "May", "June",
  "July", "August", "September", "October", "November", "December",
];

function emptyForm() {
  return { episode_id: "", label: "", amount: "", is_earning: false, remarks: "" };
}

// Form/table shape mirrors salary-app's AdhocEntries.jsx (single-row
// flex-wrap form, period pinned to the top-bar filter rather than
// re-entered per row, colored Earning/Deduction badge, delete action) -
// adapted to this app's component kit and kept our bulk-upload feature,
// which salary-app doesn't have.
export default function AdhocPayEntries() {
  const { year, month } = useGlobalFilter();
  const [employees, setEmployees] = useState([]);
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [form, setForm] = useState(emptyForm());
  const [submitting, setSubmitting] = useState(false);

  const [bulkOpen, setBulkOpen] = useState(false);
  const [bulkFile, setBulkFile] = useState(null);
  const [bulkUploading, setBulkUploading] = useState(false);
  const [bulkResult, setBulkResult] = useState(null);
  const [bulkError, setBulkError] = useState("");

  useEffect(() => {
    client.get("/employees").then((res) => setEmployees(res.data)).catch(() => {});
  }, []);

  function reload() {
    setLoading(true);
    setError("");
    client.get("/payroll/adhoc-entries", { params: { year, month } })
      .then((res) => setRows(res.data))
      .catch((err) => setError(apiErrorMessage(err)))
      .finally(() => setLoading(false));
  }
  useEffect(reload, [year, month]);

  async function submit() {
    setError("");
    setSubmitting(true);
    try {
      await client.post("/payroll/adhoc-entries", {
        episode_id: Number(form.episode_id), year, month,
        label: form.label, amount: Number(form.amount), is_earning: form.is_earning,
        remarks: form.remarks || null,
      });
      setForm(emptyForm());
      reload();
    } catch (err) {
      setError(apiErrorMessage(err));
    } finally {
      setSubmitting(false);
    }
  }

  async function remove(id) {
    if (!window.confirm("Delete this ad-hoc entry?")) return;
    try {
      await client.delete(`/payroll/adhoc-entries/${id}`);
      reload();
    } catch (err) {
      setError(apiErrorMessage(err));
    }
  }

  async function downloadTemplate() {
    const res = await client.get("/payroll/adhoc-entries-bulk-upload-template", { responseType: "blob" });
    const url = URL.createObjectURL(res.data);
    const a = document.createElement("a");
    a.href = url;
    a.download = "hrms_adhoc_pay_entries_bulk_upload_template.xlsx";
    a.click();
    URL.revokeObjectURL(url);
  }

  async function uploadBulkFile() {
    if (!bulkFile) return;
    setBulkUploading(true);
    setBulkError("");
    setBulkResult(null);
    try {
      const form2 = new FormData();
      form2.append("file", bulkFile);
      const res = await client.post("/payroll/adhoc-entries-bulk-upload", form2);
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

  function employeeLabel(episodeId) {
    const e = employees.find((x) => x.episode_id === episodeId);
    return e ? `${e.employee_number} — ${e.first_name} ${e.last_name}` : episodeId;
  }

  const columns = [
    { key: "episode_id", header: "Employee", render: (r) => employeeLabel(r.episode_id) },
    { key: "is_earning", header: "Type", render: (r) => <StatusBadge status={r.is_earning ? "EARNING" : "DEDUCTION"} /> },
    { key: "label", header: "Label" },
    { key: "amount", header: "Amount", align: "right", render: (r) => `₹ ${Number(r.amount).toLocaleString("en-IN", { minimumFractionDigits: 2 })}` },
    { key: "remarks", header: "Remarks", render: (r) => r.remarks || "—" },
    {
      key: "_actions", header: "", align: "right",
      render: (r) => (
        <Button variant="ghost" size="sm" title="Delete" aria-label="Delete" onClick={() => remove(r.id)}>
          <Trash2 size={14} className="text-danger" />
        </Button>
      ),
    },
  ];

  const canSubmit = form.episode_id && form.label && form.amount !== "";

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-display font-semibold text-ink">Ad-hoc Pay Entries</h1>
          <p className="text-sm text-ink/50 mt-1">
            One-off earnings/deductions for a specific employee, rolled into that month's payslip alongside
            the recurring salary structure — e.g. a uniform deduction when an employee resigns.
          </p>
        </div>
        <Button variant="outline" onClick={() => setBulkOpen(true)} className="gap-1.5">
          <Upload size={14} /> Bulk Upload
        </Button>
      </div>
      <p className="text-sm font-medium text-ink/60">
        Period: <span className="text-ink">{MONTH_NAMES[month - 1]} {year}</span>
        <span className="ml-1 text-xs text-ink/40">(change from the filter bar above)</span>
      </p>
      {error && <div className="text-sm text-danger bg-danger/10 rounded-md px-3 py-2">{error}</div>}

      <Card>
        <h2 className="text-sm font-semibold text-ink mb-3">Add Entry</h2>
        <div className="flex flex-wrap items-end gap-2">
          <div className="w-64">
            <Select label="Employee" value={form.episode_id} onChange={(e) => setForm({ ...form, episode_id: e.target.value })}>
              <option value="">Select employee...</option>
              {employees.map((e) => <option key={e.episode_id} value={e.episode_id}>{e.employee_number} — {e.first_name} {e.last_name}</option>)}
            </Select>
          </div>
          <div className="w-36">
            <Select label="Type" value={form.is_earning ? "earning" : "deduction"} onChange={(e) => setForm({ ...form, is_earning: e.target.value === "earning" })}>
              <option value="deduction">Deduction</option>
              <option value="earning">Earning</option>
            </Select>
          </div>
          <div className="w-48">
            <Input label="Label" placeholder="e.g. Uniform deduction" value={form.label} onChange={(e) => setForm({ ...form, label: e.target.value })} />
          </div>
          <div className="w-32">
            <Input label="Amount" type="number" step="any" placeholder="Amount" value={form.amount} onChange={(e) => setForm({ ...form, amount: e.target.value })} />
          </div>
          <div className="w-56">
            <Input label="Remarks" placeholder="Optional" value={form.remarks} onChange={(e) => setForm({ ...form, remarks: e.target.value })} />
          </div>
          <Button onClick={submit} disabled={!canSubmit || submitting} className="gap-1.5">
            <Plus size={14} /> {submitting ? "Adding…" : "Add"}
          </Button>
        </div>
      </Card>

      <Card>
        <h2 className="text-sm font-semibold text-ink mb-3">Entries — {MONTH_NAMES[month - 1]} {year}</h2>
        {loading ? <div className="text-sm text-ink/40 py-10 text-center">Loading…</div> : <Table columns={columns} rows={rows} keyField="id" empty="No ad-hoc entries for this period." />}
      </Card>

      {bulkOpen && (
        <div className="fixed inset-0 bg-black/30 flex items-center justify-center z-50" onClick={closeBulkModal}>
          <div className="bg-white rounded-lg p-5 w-full max-w-lg" onClick={(e) => e.stopPropagation()}>
            <h3 className="text-sm font-semibold text-ink mb-1">Bulk Upload Ad-hoc Pay Entries</h3>
            <p className="text-xs text-ink/50 mb-4">One row per employee per entry.</p>

            <Button variant="outline" size="sm" onClick={downloadTemplate} className="gap-1.5 mb-4">
              <Download size={14} /> Download Template (.xlsx)
            </Button>

            {bulkError && <div className="text-sm text-danger bg-danger/10 rounded-md px-3 py-2 mb-3">{bulkError}</div>}

            {bulkResult && (
              <div className="mb-4 text-sm">
                <div className="text-ok font-medium mb-1">
                  {bulkResult.created ?? 0} created, {bulkResult.updated ?? 0} updated.
                </div>
                {bulkResult.errors?.length > 0 && (
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
