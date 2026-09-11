import { useEffect, useState } from "react";
import client, { apiErrorMessage } from "../api/client";
import { Card, Button, Input, Select, Table } from "../components/ui";

// NOTE (deviation from spec): as of this writing, backend/app/routers/payroll.py
// does NOT yet expose any StatutoryConfig or ProfessionalTaxSlab endpoints,
// even though backend/app/schemas/payroll.py already defines
// StatutoryConfigIn/ProfessionalTaxSlabIn and the models exist in
// backend/app/models/models.py. Per this task's scope ("do not touch
// backend"), this page is wired to the paths that follow this router's own
// naming convention (/payroll/statutory-config, /payroll/pt-slabs) and will
// 404 until those routes are added — flagged for the backend owner.
const STATUTORY_URL = "/payroll/statutory-config";
const PT_SLABS_URL = "/payroll/pt-slabs";

function emptyConfigForm() {
  return {
    effective_from: new Date().toISOString().slice(0, 10),
    pf_employee_rate: "0.12", pf_employer_rate: "0.12", pf_wage_ceiling: "15000",
    eps_rate: "0.0833", eps_wage_ceiling: "15000",
    esi_employee_rate: "0.0075", esi_employer_rate: "0.0325", esi_wage_ceiling: "21000",
    gratuity_days_per_year: "15", gratuity_divisor: "26",
    lwf_employee_amount: "0", lwf_employer_amount: "0", lwf_frequency: "MONTHLY",
  };
}

export default function StatutoryConfigPage() {
  const [config, setConfig] = useState(null);
  const [form, setForm] = useState(emptyConfigForm());
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);
  const [loading, setLoading] = useState(true);

  const [slabs, setSlabs] = useState([]);
  const [slabForm, setSlabForm] = useState({ state: "", min_gross: "0", max_gross: "", monthly_amount: "", is_active: true });
  const [slabError, setSlabError] = useState("");
  const [slabEditingId, setSlabEditingId] = useState(null);

  function reload() {
    setLoading(true);
    setError("");
    client.get(STATUTORY_URL)
      .then((res) => {
        if (res.data) {
          setConfig(res.data);
          const f = {};
          Object.keys(emptyConfigForm()).forEach((k) => { f[k] = String(res.data[k] ?? ""); });
          setForm(f);
        }
      })
      .catch((err) => setError(apiErrorMessage(err)))
      .finally(() => setLoading(false));
    client.get(PT_SLABS_URL).then((res) => setSlabs(res.data)).catch(() => {});
  }
  useEffect(reload, []);

  async function saveConfig() {
    setError("");
    setSaving(true);
    const payload = {
      effective_from: form.effective_from,
      pf_employee_rate: Number(form.pf_employee_rate), pf_employer_rate: Number(form.pf_employer_rate),
      pf_wage_ceiling: Number(form.pf_wage_ceiling), eps_rate: Number(form.eps_rate),
      eps_wage_ceiling: Number(form.eps_wage_ceiling), esi_employee_rate: Number(form.esi_employee_rate),
      esi_employer_rate: Number(form.esi_employer_rate), esi_wage_ceiling: Number(form.esi_wage_ceiling),
      gratuity_days_per_year: Number(form.gratuity_days_per_year), gratuity_divisor: Number(form.gratuity_divisor),
      lwf_employee_amount: Number(form.lwf_employee_amount), lwf_employer_amount: Number(form.lwf_employer_amount),
      lwf_frequency: form.lwf_frequency,
    };
    try {
      if (config?.id) await client.put(`${STATUTORY_URL}/${config.id}`, payload);
      else await client.post(STATUTORY_URL, payload);
      reload();
    } catch (err) {
      setError(apiErrorMessage(err));
    } finally {
      setSaving(false);
    }
  }

  function startEditSlab(row) {
    setSlabForm({
      state: row.state, min_gross: String(row.min_gross ?? 0), max_gross: row.max_gross != null ? String(row.max_gross) : "",
      monthly_amount: String(row.monthly_amount ?? ""), is_active: !!row.is_active,
    });
    setSlabEditingId(row.id);
  }

  function cancelEditSlab() {
    setSlabForm({ state: "", min_gross: "0", max_gross: "", monthly_amount: "", is_active: true });
    setSlabEditingId(null);
  }

  async function submitSlab() {
    setSlabError("");
    const payload = {
      state: slabForm.state, min_gross: Number(slabForm.min_gross || 0),
      max_gross: slabForm.max_gross === "" ? null : Number(slabForm.max_gross),
      monthly_amount: Number(slabForm.monthly_amount), is_active: !!slabForm.is_active,
    };
    try {
      if (slabEditingId) await client.put(`${PT_SLABS_URL}/${slabEditingId}`, payload);
      else await client.post(PT_SLABS_URL, payload);
      cancelEditSlab();
      reload();
    } catch (err) {
      setSlabError(apiErrorMessage(err));
    }
  }

  const slabColumns = [
    { key: "state", header: "State" },
    { key: "min_gross", header: "Min Gross" },
    { key: "max_gross", header: "Max Gross", render: (r) => r.max_gross != null ? r.max_gross : "No upper bound" },
    { key: "monthly_amount", header: "Monthly Amount" },
    { key: "is_active", header: "Active", render: (r) => r.is_active ? "Yes" : "No" },
    {
      key: "_actions", header: "", align: "right",
      render: (r) => <Button variant="outline" size="sm" onClick={() => startEditSlab(r)}>Edit</Button>,
    },
  ];

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-xl font-display font-semibold text-ink">Statutory Configuration</h1>
        <p className="text-sm text-ink/50 mt-1">
          PF / ESI / EPS rates and wage ceilings, gratuity constants, and LWF amounts used by monthly payroll
          processing and the Full &amp; Final Settlement calculation, plus state-specific Professional Tax slabs.
        </p>
      </div>
      {error && <div className="text-sm text-danger bg-danger/10 rounded-md px-3 py-2">{error}</div>}

      <Card>
        <h2 className="text-sm font-semibold text-ink mb-3">Active Configuration</h2>
        {loading ? <div className="text-sm text-ink/40 py-6 text-center">Loading…</div> : (
          <>
            <div className="grid grid-cols-4 gap-3">
              <Input label="Effective From" type="date" value={form.effective_from} onChange={(e) => setForm({ ...form, effective_from: e.target.value })} />
              <Input label="PF Employee Rate" type="number" step="any" value={form.pf_employee_rate} onChange={(e) => setForm({ ...form, pf_employee_rate: e.target.value })} />
              <Input label="PF Employer Rate" type="number" step="any" value={form.pf_employer_rate} onChange={(e) => setForm({ ...form, pf_employer_rate: e.target.value })} />
              <Input label="PF Wage Ceiling" type="number" step="any" value={form.pf_wage_ceiling} onChange={(e) => setForm({ ...form, pf_wage_ceiling: e.target.value })} />
              <Input label="EPS Rate" type="number" step="any" value={form.eps_rate} onChange={(e) => setForm({ ...form, eps_rate: e.target.value })} />
              <Input label="EPS Wage Ceiling" type="number" step="any" value={form.eps_wage_ceiling} onChange={(e) => setForm({ ...form, eps_wage_ceiling: e.target.value })} />
              <Input label="ESI Employee Rate" type="number" step="any" value={form.esi_employee_rate} onChange={(e) => setForm({ ...form, esi_employee_rate: e.target.value })} />
              <Input label="ESI Employer Rate" type="number" step="any" value={form.esi_employer_rate} onChange={(e) => setForm({ ...form, esi_employer_rate: e.target.value })} />
              <Input label="ESI Wage Ceiling" type="number" step="any" value={form.esi_wage_ceiling} onChange={(e) => setForm({ ...form, esi_wage_ceiling: e.target.value })} />
              <Input label="Gratuity Days / Year" type="number" value={form.gratuity_days_per_year} onChange={(e) => setForm({ ...form, gratuity_days_per_year: e.target.value })} />
              <Input label="Gratuity Divisor" type="number" value={form.gratuity_divisor} onChange={(e) => setForm({ ...form, gratuity_divisor: e.target.value })} />
              <Input label="LWF Employee Amount" type="number" step="any" value={form.lwf_employee_amount} onChange={(e) => setForm({ ...form, lwf_employee_amount: e.target.value })} />
              <Input label="LWF Employer Amount" type="number" step="any" value={form.lwf_employer_amount} onChange={(e) => setForm({ ...form, lwf_employer_amount: e.target.value })} />
              <Select label="LWF Frequency" value={form.lwf_frequency} onChange={(e) => setForm({ ...form, lwf_frequency: e.target.value })}>
                <option value="MONTHLY">Monthly</option>
                <option value="HALF_YEARLY">Half-Yearly</option>
                <option value="YEARLY">Yearly</option>
              </Select>
            </div>
            <div>
              <Button className="mt-3" onClick={saveConfig} disabled={saving}>{saving ? "Saving…" : "Save Configuration"}</Button>
            </div>
          </>
        )}
      </Card>

      <Card>
        <h2 className="text-sm font-semibold text-ink mb-3">{slabEditingId ? "Edit Professional Tax Slab" : "New Professional Tax Slab"}</h2>
        {slabError && <div className="text-sm text-danger bg-danger/10 rounded-md px-3 py-2 mb-3">{slabError}</div>}
        <div className="grid grid-cols-5 gap-2">
          <Input placeholder="State" value={slabForm.state} onChange={(e) => setSlabForm({ ...slabForm, state: e.target.value })} />
          <Input type="number" step="any" placeholder="Min Gross" value={slabForm.min_gross} onChange={(e) => setSlabForm({ ...slabForm, min_gross: e.target.value })} />
          <Input type="number" step="any" placeholder="Max Gross (blank = no upper bound)" value={slabForm.max_gross} onChange={(e) => setSlabForm({ ...slabForm, max_gross: e.target.value })} />
          <Input type="number" step="any" placeholder="Monthly Amount" value={slabForm.monthly_amount} onChange={(e) => setSlabForm({ ...slabForm, monthly_amount: e.target.value })} />
        </div>
        <div className="flex gap-2 mt-3">
          <Button onClick={submitSlab} disabled={!slabForm.state || !slabForm.monthly_amount}>{slabEditingId ? "Save Changes" : "Add Slab"}</Button>
          {slabEditingId && <Button variant="outline" onClick={cancelEditSlab}>Cancel</Button>}
        </div>
      </Card>

      <Card>
        <h2 className="text-sm font-semibold text-ink mb-3">Professional Tax Slabs</h2>
        <Table columns={slabColumns} rows={slabs} keyField="id" empty="No PT slabs configured yet." />
      </Card>
    </div>
  );
}
