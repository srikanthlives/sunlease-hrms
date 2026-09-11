import { useEffect, useState } from "react";
import { Upload, Download, Trash2, History, FileStack, ReceiptText } from "lucide-react";
import client, { apiErrorMessage } from "../api/client";
import { Card, Button, Input, Select, Table, StatusBadge, formatDate } from "../components/ui";
import { useGlobalFilter } from "../context/GlobalFilterContext";

const MONTH_NAMES = [
  "January", "February", "March", "April", "May", "June",
  "July", "August", "September", "October", "November", "December",
];

export default function SalaryStructure() {
  const { year, month } = useGlobalFilter();
  const [employees, setEmployees] = useState([]);
  const [components, setComponents] = useState([]);
  const [episodeId, setEpisodeId] = useState("");
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [showHistory, setShowHistory] = useState(false);

  const [form, setForm] = useState({ component_id: "", amount: "", percentage: "", formula: "", effective_from: new Date().toISOString().slice(0, 10) });
  const [saving, setSaving] = useState(false);

  const [endingRow, setEndingRow] = useState(null);
  const [endDate, setEndDate] = useState(new Date().toISOString().slice(0, 10));
  const [ending, setEnding] = useState(false);

  const [overrides, setOverrides] = useState([]);
  const [overrideForm, setOverrideForm] = useState({ component_id: "", amount: "", remarks: "" });
  const [overrideSaving, setOverrideSaving] = useState(false);
  const [overrideError, setOverrideError] = useState("");

  const [bulkOpen, setBulkOpen] = useState(false);
  const [bulkFile, setBulkFile] = useState(null);
  const [bulkUploading, setBulkUploading] = useState(false);
  const [bulkResult, setBulkResult] = useState(null);
  const [bulkError, setBulkError] = useState("");

  const [matchingTemplates, setMatchingTemplates] = useState([]);
  const [templateOpen, setTemplateOpen] = useState(false);
  const [templateId, setTemplateId] = useState("");
  const [templateRows, setTemplateRows] = useState([]);
  const [templateEffectiveFrom, setTemplateEffectiveFrom] = useState(new Date().toISOString().slice(0, 10));
  const [templateApplying, setTemplateApplying] = useState(false);
  const [templateError, setTemplateError] = useState("");
  const [templateResult, setTemplateResult] = useState(null);

  const [payslipPopup, setPayslipPopup] = useState(null); // { loading, error, data }

  useEffect(() => {
    client.get("/employees").then((res) => setEmployees(res.data)).catch(() => {});
    client.get("/payroll/components").then((res) => setComponents(res.data.filter((c) => c.is_active))).catch(() => {});
  }, []);

  useEffect(() => {
    if (!episodeId) { setMatchingTemplates([]); return; }
    client.get(`/employees/${episodeId}`).then((res) => {
      const assignment = (res.data.assignments || []).find((a) => !a.effective_to);
      const params = {};
      if (assignment?.cost_center_id) params.cost_center_id = assignment.cost_center_id;
      if (assignment?.project_id) params.project_id = assignment.project_id;
      return client.get("/payroll/templates", { params });
    }).then((res) => setMatchingTemplates(res.data || [])).catch(() => setMatchingTemplates([]));
  }, [episodeId]);

  function openTemplateModal() {
    setTemplateOpen(true);
    setTemplateId("");
    setTemplateRows([]);
    setTemplateResult(null);
    setTemplateError("");
    setTemplateEffectiveFrom(new Date().toISOString().slice(0, 10));
  }

  function pickTemplate(id) {
    setTemplateId(id);
    setTemplateResult(null);
    setTemplateError("");
    if (!id) { setTemplateRows([]); return; }
    client.get(`/payroll/templates/${id}/components`)
      .then((res) => setTemplateRows(res.data.map((r) => ({ ...r, amount: r.amount ?? "", percentage: r.percentage ?? "" }))))
      .catch((err) => setTemplateError(apiErrorMessage(err)));
  }

  function updateTemplateRow(index, field, value) {
    setTemplateRows((prev) => prev.map((r, i) => i === index ? { ...r, [field]: value } : r));
  }

  async function applyTemplate() {
    if (!episodeId || !templateId || templateRows.length === 0) return;
    setTemplateError("");
    setTemplateApplying(true);
    try {
      const res = await client.post("/payroll/structure/apply-template", {
        episode_id: Number(episodeId),
        template_id: Number(templateId),
        effective_from: templateEffectiveFrom,
        components: templateRows.map((r) => ({
          component_id: r.component_id,
          amount: r.amount === "" ? null : Number(r.amount),
          percentage: r.percentage === "" ? null : Number(r.percentage),
          formula: r.formula || null,
        })),
      });
      setTemplateResult(res.data);
      reload();
    } catch (err) {
      setTemplateError(apiErrorMessage(err));
    } finally {
      setTemplateApplying(false);
    }
  }

  function closeTemplateModal() {
    setTemplateOpen(false);
  }

  function reload() {
    if (!episodeId) return;
    setLoading(true);
    setError("");
    client.get(`/payroll/structure/${episodeId}`, { params: showHistory ? { history: true } : {} })
      .then((res) => setRows(res.data))
      .catch((err) => setError(apiErrorMessage(err)))
      .finally(() => setLoading(false));
  }
  useEffect(reload, [episodeId, showHistory]);

  function reloadOverrides() {
    if (!episodeId) return;
    client.get(`/payroll/overrides/${episodeId}`, { params: { year, month } })
      .then((res) => setOverrides(res.data))
      .catch((err) => setOverrideError(apiErrorMessage(err)));
  }
  useEffect(reloadOverrides, [episodeId, year, month]);

  async function submit() {
    if (!episodeId || !form.component_id) return;
    setError("");
    setSaving(true);
    try {
      await client.post("/payroll/structure", {
        episode_id: Number(episodeId),
        component_id: Number(form.component_id),
        amount: form.amount === "" ? null : Number(form.amount),
        percentage: form.percentage === "" ? null : Number(form.percentage),
        formula: form.formula === "" ? null : form.formula,
        effective_from: form.effective_from,
      });
      setForm({ component_id: "", amount: "", percentage: "", formula: "", effective_from: new Date().toISOString().slice(0, 10) });
      reload();
    } catch (err) {
      setError(apiErrorMessage(err));
    } finally {
      setSaving(false);
    }
  }

  async function submitOverride() {
    if (!episodeId || !overrideForm.component_id || overrideForm.amount === "") return;
    setOverrideError("");
    setOverrideSaving(true);
    try {
      await client.post("/payroll/overrides", {
        episode_id: Number(episodeId),
        component_id: Number(overrideForm.component_id),
        year, month,
        amount: Number(overrideForm.amount),
        remarks: overrideForm.remarks || null,
      });
      setOverrideForm({ component_id: "", amount: "", remarks: "" });
      reloadOverrides();
    } catch (err) {
      setOverrideError(apiErrorMessage(err));
    } finally {
      setOverrideSaving(false);
    }
  }

  async function removeOverride(id) {
    if (!window.confirm("Remove this override? The recurring structure amount will apply again for this month.")) return;
    try {
      await client.delete(`/payroll/overrides/${id}`);
      reloadOverrides();
    } catch (err) {
      setOverrideError(apiErrorMessage(err));
    }
  }

  async function submitEndRow() {
    if (!endingRow) return;
    setError("");
    setEnding(true);
    try {
      await client.post(`/payroll/structure/${endingRow.id}/end`, { effective_to: endDate });
      setEndingRow(null);
      reload();
    } catch (err) {
      setError(apiErrorMessage(err));
    } finally {
      setEnding(false);
    }
  }

  function startEditRow(row) {
    setForm({
      component_id: String(row.component_id), amount: row.amount ?? "", percentage: row.percentage ?? "",
      formula: row.formula || "", effective_from: new Date().toISOString().slice(0, 10),
    });
  }

  function openPayslipPopup() {
    if (!episodeId) return;
    setPayslipPopup({ loading: true, error: "", data: null });
    client.get(`/payroll/structure/${episodeId}/sample-payslip`)
      .then((res) => setPayslipPopup({ loading: false, error: "", data: res.data }))
      .catch((err) => setPayslipPopup({ loading: false, error: apiErrorMessage(err), data: null }));
  }

  async function downloadTemplate() {
    const res = await client.get("/payroll/structure-bulk-upload-template", { responseType: "blob" });
    const url = URL.createObjectURL(res.data);
    const a = document.createElement("a");
    a.href = url;
    a.download = "hrms_salary_structure_bulk_upload_template.xlsx";
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
      const res = await client.post("/payroll/structure-bulk-upload", form2);
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

  const selectedFormComponent = components.find((c) => String(c.id) === form.component_id);

  const columns = [
    { key: "component_name", header: "Component" },
    {
      key: "amount", header: "Amount / % / Formula",
      render: (r) => r.formula ? <code className="text-xs">{r.formula}</code> : r.amount != null ? r.amount : r.percentage != null ? `${r.percentage}%` : "—",
    },
    { key: "effective_from", header: "Effective From", render: (r) => formatDate(r.effective_from) },
    { key: "effective_to", header: "Effective To", render: (r) => r.effective_to ? formatDate(r.effective_to) : "—" },
    { key: "status", header: "Status", render: (r) => <StatusBadge status={r.effective_to ? "INACTIVE" : "ACTIVE"} /> },
    {
      key: "_actions", header: "", align: "right",
      render: (r) => !r.effective_to && (
        <div className="flex gap-2 justify-end">
          <Button variant="outline" size="sm" onClick={() => startEditRow(r)}>Edit</Button>
          <Button variant="outline" size="sm" onClick={() => { setEndingRow(r); setEndDate(new Date().toISOString().slice(0, 10)); }}>
            End
          </Button>
        </div>
      ),
    },
  ];

  const overrideColumns = [
    { key: "component_name", header: "Component" },
    { key: "amount", header: "Override Amount", render: (r) => r.amount },
    { key: "remarks", header: "Remarks", render: (r) => r.remarks || "—" },
    { key: "created_by", header: "Set By" },
    {
      key: "_actions", header: "", align: "right",
      render: (r) => (
        <Button variant="ghost" size="sm" title="Remove override" aria-label="Remove override" onClick={() => removeOverride(r.id)}>
          <Trash2 size={14} className="text-danger" />
        </Button>
      ),
    },
  ];

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-display font-semibold text-ink">Salary Structure</h1>
          <p className="text-sm text-ink/50 mt-1">
            Per-employee, effective-dated component assignment. Adding a new row for an existing component closes
            the prior one automatically (same effective-dating convention as Department assignment).
          </p>
        </div>
        <Button variant="outline" onClick={() => setBulkOpen(true)} className="gap-1.5">
          <Upload size={14} /> Bulk Upload
        </Button>
      </div>
      {error && <div className="text-sm text-danger bg-danger/10 rounded-md px-3 py-2">{error}</div>}

      <Card>
        <Select label="Employee" value={episodeId} onChange={(e) => setEpisodeId(e.target.value)}>
          <option value="">Select employee...</option>
          {employees.map((e) => (
            <option key={e.episode_id} value={e.episode_id}>{e.employee_number} — {e.first_name} {e.last_name}</option>
          ))}
        </Select>
      </Card>

      {episodeId && (
        <>
          <Card>
            <div className="flex items-center justify-between mb-3">
              <h2 className="text-sm font-semibold text-ink">Load from Template</h2>
              <div className="flex gap-2">
                <Button variant="outline" size="sm" onClick={openPayslipPopup} className="gap-1.5">
                  <ReceiptText size={14} /> Sample Payslip (31 days)
                </Button>
                <Button variant="outline" size="sm" onClick={openTemplateModal} disabled={matchingTemplates.length === 0} className="gap-1.5">
                  <FileStack size={14} /> Load from Template
                </Button>
              </div>
            </div>
            <p className="text-xs text-ink/50">
              {matchingTemplates.length > 0
                ? `${matchingTemplates.length} template(s) available for this employee's Cost Center/Project (or global).`
                : "No salary templates match this employee's Cost Center/Project yet — configure one under Salary Templates."}
            </p>
          </Card>

          <Card>
            <h2 className="text-sm font-semibold text-ink mb-3">Add / Update Component</h2>
            <div className="grid grid-cols-4 gap-2">
              <Select
                value={form.component_id}
                onChange={(e) => {
                  const selected = components.find((c) => String(c.id) === e.target.value);
                  setForm({
                    ...form, component_id: e.target.value,
                    formula: selected?.default_calculation === "FORMULA" ? (selected.formula || "") : "",
                  });
                }}
              >
                <option value="">Component...</option>
                {components.map((c) => <option key={c.id} value={c.id}>{c.name}{c.default_calculation === "FORMULA" ? " (Formula)" : ""}</option>)}
              </Select>
              {selectedFormComponent?.default_calculation === "FORMULA" ? (
                <Input
                  className="col-span-2"
                  placeholder="Formula, e.g. BASIC * 0.4"
                  value={form.formula}
                  onChange={(e) => setForm({ ...form, formula: e.target.value })}
                />
              ) : (
                <>
                  <Input type="number" step="any" placeholder="Amount" value={form.amount} onChange={(e) => setForm({ ...form, amount: e.target.value })} />
                  <Input type="number" step="any" placeholder="Percentage of Basic" value={form.percentage} onChange={(e) => setForm({ ...form, percentage: e.target.value })} />
                </>
              )}
              <Input type="date" value={form.effective_from} onChange={(e) => setForm({ ...form, effective_from: e.target.value })} />
            </div>
            <p className="text-xs text-ink/40 mt-1">
              {selectedFormComponent?.default_calculation === "FORMULA"
                ? "This component is formula-based — leave blank to use its default formula, or override it for just this employee."
                : "Provide either an Amount or a Percentage (not both)."}
            </p>
            <div>
              <Button className="mt-3" onClick={submit} disabled={!form.component_id || saving}>{saving ? "Saving…" : "Save"}</Button>
            </div>
          </Card>

          <Card>
            <div className="flex items-center justify-between mb-3">
              <h2 className="text-sm font-semibold text-ink">{showHistory ? "Salary Version History" : "Active Structure"}</h2>
              <Button variant="outline" size="sm" onClick={() => setShowHistory((v) => !v)} className="gap-1.5">
                <History size={14} /> {showHistory ? "Show Active Only" : "Show Full History"}
              </Button>
            </div>
            {showHistory && (
              <p className="text-xs text-ink/50 mb-3">
                Every version of every component for this employee, past and present, by start/end date.
              </p>
            )}
            {loading ? <div className="text-sm text-ink/40 py-10 text-center">Loading…</div> : <Table columns={columns} rows={rows} keyField="id" empty="No salary structure configured yet." />}
          </Card>

          <Card>
            <h2 className="text-sm font-semibold text-ink mb-1">Monthly Overrides — {MONTH_NAMES[month - 1]} {year}</h2>
            <p className="text-xs text-ink/50 mb-3">
              Override a recurring component's value for just this month (e.g. Group Insurance is normally ₹50 but
              wasn't collected this month — override it to 0) without touching the ongoing structure above. Change
              the period from the filter bar above.
            </p>
            {overrideError && <div className="text-sm text-danger bg-danger/10 rounded-md px-3 py-2 mb-3">{overrideError}</div>}
            <div className="grid grid-cols-4 gap-2">
              <Select value={overrideForm.component_id} onChange={(e) => setOverrideForm({ ...overrideForm, component_id: e.target.value })}>
                <option value="">Component...</option>
                {[...new Map(rows.map((r) => [r.component_id, r])).values()].map((r) => (
                  <option key={r.component_id} value={r.component_id}>{r.component_name}</option>
                ))}
              </Select>
              <Input type="number" step="any" placeholder="Override Amount" value={overrideForm.amount} onChange={(e) => setOverrideForm({ ...overrideForm, amount: e.target.value })} />
              <Input placeholder="Remarks (optional)" value={overrideForm.remarks} onChange={(e) => setOverrideForm({ ...overrideForm, remarks: e.target.value })} />
              <Button onClick={submitOverride} disabled={!overrideForm.component_id || overrideForm.amount === "" || overrideSaving}>
                {overrideSaving ? "Saving…" : "Set Override"}
              </Button>
            </div>
            <div className="mt-3">
              <Table columns={overrideColumns} rows={overrides} keyField="id" empty="No overrides set for this period." />
            </div>
          </Card>
        </>
      )}

      {payslipPopup && (
        <div className="fixed inset-0 bg-black/30 flex items-center justify-center z-50" onClick={() => setPayslipPopup(null)}>
          <div className="bg-white rounded-lg p-5 w-full max-w-lg max-h-[85vh] overflow-y-auto" onClick={(e) => e.stopPropagation()}>
            <h3 className="text-sm font-semibold text-ink mb-1">Sample Payslip</h3>
            <p className="text-xs text-ink/50 mb-4">
              Illustrative payslip for a fully-worked 31-day month, using this employee's active salary structure.
              Excludes PF/ESI/PT/LWF, which apply during actual payroll processing.
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

      {endingRow && (
        <div className="fixed inset-0 bg-black/30 flex items-center justify-center z-50" onClick={() => setEndingRow(null)}>
          <div className="bg-white rounded-lg p-5 w-full max-w-sm" onClick={(e) => e.stopPropagation()}>
            <h3 className="text-sm font-semibold text-ink mb-1">End {endingRow.component_name}</h3>
            <p className="text-xs text-ink/50 mb-4">
              Discontinues this component with no replacement version, effective the date below. It won't apply to
              any payroll run processed for a later period.
            </p>
            <Input type="date" label="End Date" value={endDate} min={endingRow.effective_from} onChange={(e) => setEndDate(e.target.value)} />
            <div className="flex justify-end gap-2 mt-4">
              <Button variant="outline" onClick={() => setEndingRow(null)} disabled={ending}>Cancel</Button>
              <Button variant="danger" onClick={submitEndRow} disabled={ending}>{ending ? "Ending…" : "End Component"}</Button>
            </div>
          </div>
        </div>
      )}

      {templateOpen && (
        <div className="fixed inset-0 bg-black/30 flex items-center justify-center z-50" onClick={closeTemplateModal}>
          <div className="bg-white rounded-lg p-5 w-full max-w-2xl max-h-[85vh] overflow-y-auto" onClick={(e) => e.stopPropagation()}>
            <h3 className="text-sm font-semibold text-ink mb-1">Load Salary Structure from Template</h3>
            <p className="text-xs text-ink/50 mb-4">
              Pick a template to pre-fill component amounts below — every value stays editable before you apply it.
            </p>

            <div className="grid grid-cols-2 gap-2 mb-4">
              <Select label="Template" value={templateId} onChange={(e) => pickTemplate(e.target.value)}>
                <option value="">Select template...</option>
                {matchingTemplates.map((t) => (
                  <option key={t.id} value={t.id}>{t.name} ({t.cost_center_name || "Global"}{t.project_name ? ` / ${t.project_name}` : ""})</option>
                ))}
              </Select>
              <Input type="date" label="Effective From" value={templateEffectiveFrom} onChange={(e) => setTemplateEffectiveFrom(e.target.value)} />
            </div>

            {templateError && <div className="text-sm text-danger bg-danger/10 rounded-md px-3 py-2 mb-3">{templateError}</div>}

            {templateResult && (
              <div className="mb-4 text-sm">
                <div className="text-ok font-medium mb-1">{templateResult.applied} component(s) applied.</div>
                {templateResult.errors?.length > 0 && (
                  <div className="border border-danger/20 bg-danger/5 rounded-md p-2 max-h-32 overflow-y-auto">
                    {templateResult.errors.map((e, i) => (
                      <div key={i} className="text-xs text-ink/60">{e.message}</div>
                    ))}
                  </div>
                )}
              </div>
            )}

            {templateRows.length > 0 && (
              <div className="space-y-2 mb-4">
                <div className="grid grid-cols-4 gap-2 text-xs font-medium text-ink/50 px-1">
                  <span>Component</span><span>Amount</span><span>% of Basic</span><span>Formula</span>
                </div>
                {templateRows.map((r, i) => (
                  <div key={r.component_id} className="grid grid-cols-4 gap-2 items-center">
                    <span className="text-sm text-ink">{r.component_name}</span>
                    <Input type="number" step="any" value={r.amount} onChange={(e) => updateTemplateRow(i, "amount", e.target.value)} />
                    <Input type="number" step="any" value={r.percentage} onChange={(e) => updateTemplateRow(i, "percentage", e.target.value)} />
                    <Input placeholder="e.g. BASIC * 0.4" value={r.formula || ""} onChange={(e) => updateTemplateRow(i, "formula", e.target.value)} />
                  </div>
                ))}
              </div>
            )}

            <div className="flex justify-end gap-2 mt-4">
              <Button variant="outline" onClick={closeTemplateModal}>Close</Button>
              <Button onClick={applyTemplate} disabled={!templateId || templateRows.length === 0 || templateApplying}>
                {templateApplying ? "Applying…" : "Apply to Structure"}
              </Button>
            </div>
          </div>
        </div>
      )}

      {bulkOpen && (
        <div className="fixed inset-0 bg-black/30 flex items-center justify-center z-50" onClick={closeBulkModal}>
          <div className="bg-white rounded-lg p-5 w-full max-w-lg" onClick={(e) => e.stopPropagation()}>
            <h3 className="text-sm font-semibold text-ink mb-1">Bulk Upload Salary Structure</h3>
            <p className="text-xs text-ink/50 mb-4">
              One row per employee per component. Each row upserts through the same effective-dating logic as
              adding a component manually.
            </p>

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
