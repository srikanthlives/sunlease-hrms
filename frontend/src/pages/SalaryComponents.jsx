import { useEffect, useState } from "react";
import client, { apiErrorMessage } from "../api/client";
import { Card, Button, Input, Select, Checkbox, Table, StatusBadge } from "../components/ui";

// Salary Component master. The backend router only exposes POST (create)
// and PUT (update) for /payroll/components — no DELETE — so unlike
// MasterPage's default (which assumes a deactivate/DELETE verb), this page
// is edit-in-place only: toggle "Active" via the edit form's checkbox
// instead of a separate Deactivate button.
const TYPE_OPTIONS = [
  { value: "EARNING", label: "Earning" },
  { value: "DEDUCTION", label: "Deduction" },
  { value: "EMPLOYER_CONTRIBUTION", label: "Employer Contribution" },
  { value: "ADDITION", label: "Addition (paid out, excluded from Gross/Net)" },
];

const CALC_OPTIONS = [
  { value: "FIXED", label: "Fixed" },
  { value: "PERCENTAGE_OF_BASIC", label: "% of Basic" },
  { value: "FORMULA", label: "Formula" },
];

const FORMULA_VARIABLES = [
  "PRESENT", "ABSENT", "HALF_DAY", "ON_LEAVE", "WEEKLY_OFF", "HOLIDAY",
  "LATE_DAYS", "EARLY_DEP_DAYS", "OT_MIN", "NOT_MARKED",
];

function emptyForm() {
  return {
    code: "", name: "", component_type: "EARNING", default_calculation: "FIXED",
    default_value: "0", formula: "", sequence: "0", is_statutory: false, is_active: true,
  };
}

export default function SalaryComponents() {
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(true);
  const [form, setForm] = useState(emptyForm());
  const [editingId, setEditingId] = useState(null);
  const [error, setError] = useState("");

  function reload() {
    setLoading(true);
    client.get("/payroll/components").then((res) => setRows(res.data)).finally(() => setLoading(false));
  }
  useEffect(reload, []);

  function startEdit(row) {
    setForm({
      code: row.code, name: row.name, component_type: row.component_type,
      default_calculation: row.default_calculation, default_value: String(row.default_value ?? 0),
      formula: row.formula || "",
      sequence: String(row.sequence ?? 0), is_statutory: !!row.is_statutory, is_active: !!row.is_active,
    });
    setEditingId(row.id);
    setError("");
  }

  function cancelEdit() {
    setForm(emptyForm());
    setEditingId(null);
    setError("");
  }

  async function submit() {
    setError("");
    const payload = {
      code: form.code, name: form.name, component_type: form.component_type,
      default_calculation: form.default_calculation, default_value: Number(form.default_value || 0),
      formula: form.default_calculation === "FORMULA" ? (form.formula || null) : null,
      sequence: Number(form.sequence || 0), is_statutory: !!form.is_statutory, is_active: !!form.is_active,
    };
    try {
      if (editingId) await client.put(`/payroll/components/${editingId}`, payload);
      else await client.post("/payroll/components", payload);
      cancelEdit();
      reload();
    } catch (err) {
      setError(apiErrorMessage(err));
    }
  }

  const columns = [
    { key: "sequence", header: "#", sortable: true },
    { key: "code", header: "Code", sortable: true },
    { key: "name", header: "Name", sortable: true },
    { key: "component_type", header: "Type", render: (r) => r.component_type.replace(/_/g, " ") },
    { key: "default_calculation", header: "Calculation", render: (r) => CALC_OPTIONS.find((c) => c.value === r.default_calculation)?.label || r.default_calculation },
    { key: "default_value", header: "Default Value / Formula", render: (r) => r.default_calculation === "FORMULA" ? <code className="text-xs">{r.formula}</code> : r.default_value },
    { key: "is_statutory", header: "Statutory", render: (r) => r.is_statutory ? <StatusBadge status="ACTIVE" /> : "—" },
    { key: "is_active", header: "Status", render: (r) => <StatusBadge status={r.is_active ? "ACTIVE" : "INACTIVE"} /> },
    {
      key: "_actions", header: "", align: "right",
      render: (r) => <Button variant="outline" size="sm" onClick={() => startEdit(r)}>Edit</Button>,
    },
  ];

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-xl font-display font-semibold text-ink">Salary Components</h1>
        <p className="text-sm text-ink/50 mt-1">
          Component master for Earnings, Deductions, Employer Contributions, and Additions used to build employee
          salary structures. Statutory components (PF/ESI/PT/LWF) are computed by the payroll engine at processing
          time, not from the value here. "Addition" (e.g. Bonus, monthly performance/attendance pay) is paid out
          on top of Net Pay as Total Payable, but stays out of Gross/Net and the PF/ESI wage base.
        </p>
      </div>
      {error && <div className="text-sm text-danger bg-danger/10 rounded-md px-3 py-2">{error}</div>}

      <Card>
        <h2 className="text-sm font-semibold text-ink mb-3">{editingId ? "Edit Component" : "New Component"}</h2>
        <div className="grid grid-cols-4 gap-2">
          <Input placeholder="Code" value={form.code} onChange={(e) => setForm({ ...form, code: e.target.value })} />
          <Input placeholder="Name" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />
          <Select value={form.component_type} onChange={(e) => setForm({ ...form, component_type: e.target.value })}>
            {TYPE_OPTIONS.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
          </Select>
          <Select value={form.default_calculation} onChange={(e) => setForm({ ...form, default_calculation: e.target.value })}>
            {CALC_OPTIONS.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
          </Select>
          {form.default_calculation === "FORMULA" ? (
            <Input placeholder="Formula, e.g. BASIC * 0.4" value={form.formula} onChange={(e) => setForm({ ...form, formula: e.target.value })} />
          ) : (
            <Input type="number" step="any" placeholder="Default Value" value={form.default_value} onChange={(e) => setForm({ ...form, default_value: e.target.value })} />
          )}
          <Input type="number" placeholder="Sequence" value={form.sequence} onChange={(e) => setForm({ ...form, sequence: e.target.value })} />
          <Checkbox label="Statutory" checked={form.is_statutory} onChange={(e) => setForm({ ...form, is_statutory: e.target.checked })} className="self-center" />
          <Checkbox label="Active" checked={form.is_active} onChange={(e) => setForm({ ...form, is_active: e.target.checked })} className="self-center" />
        </div>
        {form.default_calculation === "FORMULA" && (
          <p className="text-xs text-ink/40 mt-1">
            Reference other component codes (e.g. BASIC, HRA) or day variables: {FORMULA_VARIABLES.join(", ")}.
            Functions: min, max, round, abs, ceil, floor, roundup(value, nearest), rounddown(value, nearest) (case-insensitive), plus
            IF(condition, then, else), AND(...), OR(...) (must be ALL CAPS) — e.g. {"IF(PRESENT >= 26, 500, 0)"} or ROUNDUP(min(BASIC,15000)*0.12, 1).
          </p>
        )}
        <div className="flex gap-2 mt-3">
          <Button onClick={submit} disabled={!form.code || !form.name || (form.default_calculation === "FORMULA" && !form.formula)}>
            {editingId ? "Save Changes" : "Add"}
          </Button>
          {editingId && <Button variant="outline" onClick={cancelEdit}>Cancel</Button>}
        </div>
      </Card>

      <Card>
        {loading ? <div className="text-sm text-ink/40 py-10 text-center">Loading…</div> : <Table columns={columns} rows={rows} keyField="id" />}
      </Card>
    </div>
  );
}
