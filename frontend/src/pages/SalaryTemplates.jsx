import { useEffect, useState } from "react";
import { Trash2, ListTree, ReceiptText } from "lucide-react";
import client, { apiErrorMessage } from "../api/client";
import { Card, Button, Input, Select, Table, StatusBadge } from "../components/ui";

// Reusable salary structure blueprints, scoped to a Cost Center and/or
// Project, or global when both are left unset. Loading a template into
// an employee's structure (see SalaryStructure.jsx) copies these
// component rows as a starting point that the user can still edit
// before applying.
export default function SalaryTemplates() {
  const [templates, setTemplates] = useState([]);
  const [costCenters, setCostCenters] = useState([]);
  const [projects, setProjects] = useState([]);
  const [components, setComponents] = useState([]);
  const [error, setError] = useState("");

  const [form, setForm] = useState({ code: "", name: "", cost_center_id: "", project_id: "", is_active: true });
  const [editingId, setEditingId] = useState(null);
  const [saving, setSaving] = useState(false);

  const [selectedTemplateId, setSelectedTemplateId] = useState("");
  const [templateComponents, setTemplateComponents] = useState([]);
  const [componentForm, setComponentForm] = useState({ component_id: "", amount: "", percentage: "", formula: "" });
  const [editingComponentRowId, setEditingComponentRowId] = useState(null);
  const [componentSaving, setComponentSaving] = useState(false);
  const [componentError, setComponentError] = useState("");

  const [structurePopup, setStructurePopup] = useState(null); // { template, rows }
  const [payslipPopup, setPayslipPopup] = useState(null); // { template, loading, error, data }

  function reloadTemplates() {
    client.get("/payroll/templates").then((res) => setTemplates(res.data)).catch((err) => setError(apiErrorMessage(err)));
  }

  useEffect(() => {
    reloadTemplates();
    client.get("/cost-centers").then((res) => setCostCenters(res.data)).catch(() => {});
    client.get("/projects").then((res) => setProjects(res.data)).catch(() => {});
    client.get("/payroll/components").then((res) => setComponents(res.data.filter((c) => c.is_active))).catch(() => {});
  }, []);

  function reloadTemplateComponents() {
    if (!selectedTemplateId) return;
    client.get(`/payroll/templates/${selectedTemplateId}/components`)
      .then((res) => setTemplateComponents(res.data))
      .catch((err) => setComponentError(apiErrorMessage(err)));
  }
  useEffect(reloadTemplateComponents, [selectedTemplateId]);

  function emptyForm() {
    return { code: "", name: "", cost_center_id: "", project_id: "", is_active: true };
  }

  function startEdit(t) {
    setForm({
      code: t.code, name: t.name,
      cost_center_id: t.cost_center_id != null ? String(t.cost_center_id) : "",
      project_id: t.project_id != null ? String(t.project_id) : "",
      is_active: t.is_active,
    });
    setEditingId(t.id);
  }

  function cancelEdit() {
    setForm(emptyForm());
    setEditingId(null);
    setError("");
  }

  async function submit() {
    setError("");
    setSaving(true);
    const payload = {
      code: form.code, name: form.name,
      cost_center_id: form.cost_center_id === "" ? null : Number(form.cost_center_id),
      project_id: form.project_id === "" ? null : Number(form.project_id),
      is_active: form.is_active,
    };
    try {
      if (editingId) await client.put(`/payroll/templates/${editingId}`, payload);
      else await client.post("/payroll/templates", payload);
      cancelEdit();
      reloadTemplates();
    } catch (err) {
      setError(apiErrorMessage(err));
    } finally {
      setSaving(false);
    }
  }

  async function submitComponent() {
    if (!selectedTemplateId || !componentForm.component_id) return;
    setComponentError("");
    setComponentSaving(true);
    try {
      await client.post(`/payroll/templates/${selectedTemplateId}/components`, {
        component_id: Number(componentForm.component_id),
        amount: componentForm.amount === "" ? null : Number(componentForm.amount),
        percentage: componentForm.percentage === "" ? null : Number(componentForm.percentage),
        formula: componentForm.formula === "" ? null : componentForm.formula,
      });
      setComponentForm({ component_id: "", amount: "", percentage: "", formula: "" });
      setEditingComponentRowId(null);
      reloadTemplateComponents();
    } catch (err) {
      setComponentError(apiErrorMessage(err));
    } finally {
      setComponentSaving(false);
    }
  }

  function startEditComponent(row) {
    setComponentForm({
      component_id: String(row.component_id), amount: row.amount ?? "", percentage: row.percentage ?? "", formula: row.formula || "",
    });
    setEditingComponentRowId(row.id);
    setComponentError("");
  }

  async function removeComponent(rowId) {
    try {
      await client.delete(`/payroll/templates/${selectedTemplateId}/components/${rowId}`);
      if (editingComponentRowId === rowId) { setComponentForm({ component_id: "", amount: "", percentage: "", formula: "" }); setEditingComponentRowId(null); }
      reloadTemplateComponents();
    } catch (err) {
      setComponentError(apiErrorMessage(err));
    }
  }

  function openStructurePopup(t) {
    setStructurePopup({ template: t, rows: [], loading: true });
    client.get(`/payroll/templates/${t.id}/components`)
      .then((res) => setStructurePopup({ template: t, rows: res.data, loading: false }))
      .catch((err) => setStructurePopup({ template: t, rows: [], loading: false, error: apiErrorMessage(err) }));
  }

  function openPayslipPopup(t) {
    setPayslipPopup({ template: t, loading: true, error: "", data: null });
    client.get(`/payroll/templates/${t.id}/sample-payslip`)
      .then((res) => setPayslipPopup({ template: t, loading: false, error: "", data: res.data }))
      .catch((err) => setPayslipPopup({ template: t, loading: false, error: apiErrorMessage(err), data: null }));
  }

  const templateColumns = [
    { key: "code", header: "Code" },
    { key: "name", header: "Name" },
    { key: "cost_center_name", header: "Cost Center", render: (t) => t.cost_center_name || "Global" },
    { key: "project_name", header: "Project", render: (t) => t.project_name || (t.cost_center_id ? "Any" : "—") },
    { key: "is_active", header: "Status", render: (t) => <StatusBadge status={t.is_active ? "ACTIVE" : "INACTIVE"} /> },
    {
      key: "_actions", header: "", align: "right",
      render: (t) => (
        <div className="flex gap-2 justify-end">
          <Button variant="outline" size="sm" onClick={() => startEdit(t)}>Edit</Button>
          <Button variant={selectedTemplateId === String(t.id) ? "primary" : "outline"} size="sm" onClick={() => setSelectedTemplateId(String(t.id))}>
            Components
          </Button>
          <Button variant="outline" size="sm" title="Salary Structure" aria-label="Salary Structure" onClick={() => openStructurePopup(t)}>
            <ListTree size={14} />
          </Button>
          <Button variant="outline" size="sm" title="Sample Payslip (31 days)" aria-label="Sample Payslip" onClick={() => openPayslipPopup(t)}>
            <ReceiptText size={14} />
          </Button>
        </div>
      ),
    },
  ];

  const componentColumns = [
    { key: "component_name", header: "Component" },
    {
      key: "amount", header: "Amount / % / Formula",
      render: (r) => r.formula ? <code className="text-xs">{r.formula}</code> : r.amount != null ? r.amount : r.percentage != null ? `${r.percentage}%` : "—",
    },
    {
      key: "_actions", header: "", align: "right",
      render: (r) => (
        <div className="flex gap-2 justify-end">
          <Button variant="outline" size="sm" onClick={() => startEditComponent(r)}>Edit</Button>
          <Button variant="ghost" size="sm" title="Remove" aria-label="Remove" onClick={() => removeComponent(r.id)}>
            <Trash2 size={14} className="text-danger" />
          </Button>
        </div>
      ),
    },
  ];

  const selectedTemplate = templates.find((t) => String(t.id) === selectedTemplateId);
  const canSubmit = form.code && form.name;

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-xl font-display font-semibold text-ink">Salary Templates</h1>
        <p className="text-sm text-ink/50 mt-1">
          Reusable salary structure blueprints. Scope a template to a Cost Center and/or Project, or leave both
          blank for a global template available everywhere. Loading a template into an employee's structure copies
          its component amounts as a starting point — every value stays editable before applying.
        </p>
      </div>
      {error && <div className="text-sm text-danger bg-danger/10 rounded-md px-3 py-2">{error}</div>}

      <Card>
        <h2 className="text-sm font-semibold text-ink mb-3">{editingId ? "Edit Template" : "New Template"}</h2>
        <div className="grid grid-cols-5 gap-2">
          <Input placeholder="Code" value={form.code} onChange={(e) => setForm({ ...form, code: e.target.value })} />
          <Input placeholder="Name" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />
          <Select value={form.cost_center_id} onChange={(e) => setForm({ ...form, cost_center_id: e.target.value, project_id: "" })}>
            <option value="">Cost Center: Global</option>
            {costCenters.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
          </Select>
          <Select value={form.project_id} onChange={(e) => setForm({ ...form, project_id: e.target.value })} disabled={!form.cost_center_id}>
            <option value="">Project: Any</option>
            {projects.filter((p) => String(p.cost_center_id) === form.cost_center_id).map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
          </Select>
          <Select value={form.is_active ? "1" : "0"} onChange={(e) => setForm({ ...form, is_active: e.target.value === "1" })}>
            <option value="1">Active</option>
            <option value="0">Inactive</option>
          </Select>
        </div>
        <p className="text-xs text-ink/40 mt-1">A Project can only be picked once a Cost Center is selected.</p>
        <div className="flex gap-2 mt-3">
          <Button onClick={submit} disabled={!canSubmit || saving}>{editingId ? "Save Changes" : "Add"}</Button>
          {editingId && <Button variant="outline" onClick={cancelEdit}>Cancel</Button>}
        </div>
      </Card>

      <Card>
        <h2 className="text-sm font-semibold text-ink mb-3">Templates</h2>
        <Table columns={templateColumns} rows={templates} keyField="id" empty="No salary templates configured yet." />
      </Card>

      {selectedTemplateId && (
        <Card>
          <h2 className="text-sm font-semibold text-ink mb-1">Components — {selectedTemplate?.name}</h2>
          <p className="text-xs text-ink/50 mb-3">
            Provide an Amount, a Percentage of Basic, or a Formula per component (formula components fill in
            automatically for Formula-type components). Adding a component that's already in this template
            replaces its value.
          </p>
          {componentError && <div className="text-sm text-danger bg-danger/10 rounded-md px-3 py-2 mb-3">{componentError}</div>}
          <div className="grid grid-cols-4 gap-2">
            <Select
              value={componentForm.component_id}
              onChange={(e) => {
                const selected = components.find((c) => String(c.id) === e.target.value);
                setComponentForm({
                  ...componentForm, component_id: e.target.value,
                  formula: selected?.default_calculation === "FORMULA" ? (selected.formula || "") : "",
                });
              }}
            >
              <option value="">Component...</option>
              {components.map((c) => <option key={c.id} value={c.id}>{c.name}{c.default_calculation === "FORMULA" ? " (Formula)" : ""}</option>)}
            </Select>
            {components.find((c) => String(c.id) === componentForm.component_id)?.default_calculation === "FORMULA" ? (
              <Input
                className="col-span-2"
                placeholder="Formula, e.g. BASIC * 0.4"
                value={componentForm.formula}
                onChange={(e) => setComponentForm({ ...componentForm, formula: e.target.value })}
              />
            ) : (
              <>
                <Input type="number" step="any" placeholder="Amount" value={componentForm.amount} onChange={(e) => setComponentForm({ ...componentForm, amount: e.target.value })} />
                <Input type="number" step="any" placeholder="Percentage of Basic" value={componentForm.percentage} onChange={(e) => setComponentForm({ ...componentForm, percentage: e.target.value })} />
              </>
            )}
            <div className="flex gap-2">
              <Button onClick={submitComponent} disabled={!componentForm.component_id || componentSaving}>
                {componentSaving ? "Saving…" : editingComponentRowId ? "Save Changes" : "Add / Update"}
              </Button>
              {editingComponentRowId && (
                <Button variant="outline" onClick={() => { setComponentForm({ component_id: "", amount: "", percentage: "", formula: "" }); setEditingComponentRowId(null); }}>
                  Cancel
                </Button>
              )}
            </div>
          </div>
          <div className="mt-3">
            <Table columns={componentColumns} rows={templateComponents} keyField="id" empty="No components in this template yet." />
          </div>
        </Card>
      )}

      {structurePopup && (
        <div className="fixed inset-0 bg-black/30 flex items-center justify-center z-50" onClick={() => setStructurePopup(null)}>
          <div className="bg-white rounded-lg p-5 w-full max-w-lg max-h-[85vh] overflow-y-auto" onClick={(e) => e.stopPropagation()}>
            <h3 className="text-sm font-semibold text-ink mb-1">Salary Structure — {structurePopup.template.name}</h3>
            <p className="text-xs text-ink/50 mb-4">
              {structurePopup.template.cost_center_name || "Global"}{structurePopup.template.project_name ? ` / ${structurePopup.template.project_name}` : ""}
            </p>
            {structurePopup.loading ? (
              <div className="text-sm text-ink/40 py-10 text-center">Loading…</div>
            ) : structurePopup.error ? (
              <div className="text-sm text-danger bg-danger/10 rounded-md px-3 py-2">{structurePopup.error}</div>
            ) : (
              <Table
                columns={[
                  { key: "component_name", header: "Component" },
                  {
                    key: "amount", header: "Amount / % / Formula",
                    render: (r) => r.formula ? <code className="text-xs">{r.formula}</code> : r.amount != null ? r.amount : r.percentage != null ? `${r.percentage}%` : "—",
                  },
                ]}
                rows={structurePopup.rows}
                keyField="id"
                empty="No components in this template yet."
              />
            )}
            <div className="flex justify-end mt-4">
              <Button variant="outline" onClick={() => setStructurePopup(null)}>Close</Button>
            </div>
          </div>
        </div>
      )}

      {payslipPopup && (
        <div className="fixed inset-0 bg-black/30 flex items-center justify-center z-50" onClick={() => setPayslipPopup(null)}>
          <div className="bg-white rounded-lg p-5 w-full max-w-lg max-h-[85vh] overflow-y-auto" onClick={(e) => e.stopPropagation()}>
            <h3 className="text-sm font-semibold text-ink mb-1">Sample Payslip — {payslipPopup.template.name}</h3>
            <p className="text-xs text-ink/50 mb-4">
              Illustrative payslip for a fully-worked 31-day month. Excludes PF/ESI/PT/LWF, which depend on a
              specific employee's statutory eligibility and only apply once the template is applied and real
              payroll is run.
            </p>
            {payslipPopup.loading ? (
              <div className="text-sm text-ink/40 py-10 text-center">Loading…</div>
            ) : payslipPopup.error ? (
              <div className="text-sm text-danger bg-danger/10 rounded-md px-3 py-2">{payslipPopup.error}</div>
            ) : payslipPopup.data && (
              <>
                {payslipPopup.data.errors?.length > 0 && (
                  <div className="border border-danger/20 bg-danger/5 rounded-md p-2 mb-3">
                    {payslipPopup.data.errors.map((e, i) => (
                      <div key={i} className="text-xs text-danger">{e.code}: {e.message}</div>
                    ))}
                  </div>
                )}
                <div className="grid grid-cols-2 gap-x-6 gap-y-1 text-sm mb-4">
                  <div className="font-semibold text-ink/70 col-span-2 mb-1">Earnings</div>
                  {payslipPopup.data.lines.filter((l) => l.component_type === "EARNING").map((l) => (
                    <div key={l.code} className="contents">
                      <span className="text-ink/70">{l.name}</span>
                      <span className="text-right">{l.amount.toLocaleString("en-IN", { minimumFractionDigits: 2 })}</span>
                    </div>
                  ))}
                  {payslipPopup.data.lines.some((l) => l.component_type === "DEDUCTION") && (
                    <>
                      <div className="font-semibold text-ink/70 col-span-2 mt-2 mb-1">Deductions</div>
                      {payslipPopup.data.lines.filter((l) => l.component_type === "DEDUCTION").map((l) => (
                        <div key={l.code} className="contents">
                          <span className="text-ink/70">{l.name}</span>
                          <span className="text-right">{l.amount.toLocaleString("en-IN", { minimumFractionDigits: 2 })}</span>
                        </div>
                      ))}
                    </>
                  )}
                  {payslipPopup.data.lines.some((l) => l.component_type === "ADDITION") && (
                    <>
                      <div className="font-semibold text-ink/70 col-span-2 mt-2 mb-1">Additions <span className="normal-case font-normal text-ink/40">(not part of Gross/Net)</span></div>
                      {payslipPopup.data.lines.filter((l) => l.component_type === "ADDITION").map((l) => (
                        <div key={l.code} className="contents">
                          <span className="text-ink/70">{l.name}</span>
                          <span className="text-right">{l.amount.toLocaleString("en-IN", { minimumFractionDigits: 2 })}</span>
                        </div>
                      ))}
                    </>
                  )}
                </div>
                <div className="border-t border-ink/10 pt-3 space-y-1 text-sm">
                  <div className="flex justify-between"><span className="text-ink/50">Gross Earnings</span><span>{payslipPopup.data.gross_earnings.toLocaleString("en-IN", { minimumFractionDigits: 2 })}</span></div>
                  <div className="flex justify-between"><span className="text-ink/50">Gross Deductions</span><span>{payslipPopup.data.gross_deductions.toLocaleString("en-IN", { minimumFractionDigits: 2 })}</span></div>
                  <div className="flex justify-between"><span className="text-ink/50">Net Pay</span><span>{payslipPopup.data.net_pay.toLocaleString("en-IN", { minimumFractionDigits: 2 })}</span></div>
                  {payslipPopup.data.additional_pay > 0 && (
                    <div className="flex justify-between"><span className="text-ink/50">Additions</span><span>{payslipPopup.data.additional_pay.toLocaleString("en-IN", { minimumFractionDigits: 2 })}</span></div>
                  )}
                  <div className="flex justify-between text-base font-semibold text-ink pt-1"><span>Total Payable</span><span>{payslipPopup.data.total_payable.toLocaleString("en-IN", { minimumFractionDigits: 2 })}</span></div>
                </div>
              </>
            )}
            <div className="flex justify-end mt-4">
              <Button variant="outline" onClick={() => setPayslipPopup(null)}>Close</Button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
