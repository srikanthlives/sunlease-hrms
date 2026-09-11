import { useEffect, useState } from "react";
import client, { apiErrorMessage } from "../api/client";
import { Card, Button, Input, Select, Table } from "../components/ui";

export default function LeaveEligibilityConfig() {
  const [rules, setRules] = useState([]);
  const [leaveTypes, setLeaveTypes] = useState([]);
  const [categories, setCategories] = useState([]);
  const [costCenters, setCostCenters] = useState([]);
  const [error, setError] = useState("");
  const [form, setForm] = useState({ leave_type_id: "", employee_category_id: "", cost_center_id: "", min_service_months: "0", annual_entitlement: "" });

  function reload() {
    client.get("/leave/eligibility-rules").then((res) => setRules(res.data));
    client.get("/leave/types").then((res) => setLeaveTypes(res.data));
    client.get("/employee-categories").then((res) => setCategories(res.data));
    client.get("/cost-centers").then((res) => setCostCenters(res.data));
  }
  useEffect(reload, []);

  async function createRule() {
    setError("");
    try {
      await client.post("/leave/eligibility-rules", {
        leave_type_id: Number(form.leave_type_id),
        employee_category_id: form.employee_category_id ? Number(form.employee_category_id) : null,
        cost_center_id: form.cost_center_id ? Number(form.cost_center_id) : null,
        min_service_months: Number(form.min_service_months || 0),
        annual_entitlement: Number(form.annual_entitlement),
      });
      setForm({ leave_type_id: "", employee_category_id: "", cost_center_id: "", min_service_months: "0", annual_entitlement: "" });
      reload();
    } catch (err) {
      setError(apiErrorMessage(err));
    }
  }

  const nameOf = (list, id) => list.find((x) => x.id === id)?.name || "Any";

  const columns = [
    { key: "leave_type", header: "Leave Type", render: (r) => leaveTypes.find((t) => t.id === r.leave_type_id)?.name || r.leave_type_id },
    { key: "employee_category", header: "Category (blank = global)", render: (r) => nameOf(categories, r.employee_category_id) },
    { key: "cost_center", header: "Cost Center (blank = global)", render: (r) => nameOf(costCenters, r.cost_center_id) },
    { key: "min_service_months", header: "Min Service (months)", render: (r) => r.min_service_months },
    { key: "annual_entitlement", header: "Annual Entitlement", render: (r) => r.annual_entitlement },
  ];

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-xl font-display font-semibold text-ink">Leave Eligibility</h1>
        <p className="text-sm text-ink/50 mt-1">
          Annual entitlement per Leave Type, scoped by Cost Center / Employee Category. Matched most-specific-first —
          Cost Center + Category, then Cost Center only, then Category only, then the global fallback (both blank).
        </p>
      </div>
      {error && <div className="text-sm text-danger bg-danger/10 rounded-md px-3 py-2">{error}</div>}

      <Card>
        <h2 className="text-sm font-semibold text-ink mb-3">New Rule</h2>
        <div className="grid grid-cols-5 gap-2">
          <Select value={form.leave_type_id} onChange={(e) => setForm({ ...form, leave_type_id: e.target.value })}>
            <option value="">Leave Type...</option>
            {leaveTypes.map((t) => <option key={t.id} value={t.id}>{t.name}</option>)}
          </Select>
          <Select value={form.employee_category_id} onChange={(e) => setForm({ ...form, employee_category_id: e.target.value })}>
            <option value="">Any Category</option>
            {categories.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
          </Select>
          <Select value={form.cost_center_id} onChange={(e) => setForm({ ...form, cost_center_id: e.target.value })}>
            <option value="">Any Cost Center</option>
            {costCenters.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
          </Select>
          <Input type="number" placeholder="Min Service (months)" value={form.min_service_months} onChange={(e) => setForm({ ...form, min_service_months: e.target.value })} />
          <Input type="number" placeholder="Annual Entitlement" value={form.annual_entitlement} onChange={(e) => setForm({ ...form, annual_entitlement: e.target.value })} />
        </div>
        <div>
          <Button className="mt-3" onClick={createRule} disabled={!form.leave_type_id || !form.annual_entitlement}>Add Rule</Button>
        </div>
      </Card>

      <Card>
        <h2 className="text-sm font-semibold text-ink mb-3">All Rules</h2>
        <Table columns={columns} rows={rules} empty="No eligibility rules yet." />
      </Card>
    </div>
  );
}
