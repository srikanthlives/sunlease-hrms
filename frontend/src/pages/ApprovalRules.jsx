import { useEffect, useState } from "react";
import client, { apiErrorMessage } from "../api/client";
import { Card, Button, Select, Table } from "../components/ui";

const TRANSACTION_TYPES = [
  "EMPLOYEE_CREATION", "IDENTITY_CHANGE", "EMPLOYMENT_CHANGE", "ORG_CHANGE",
  "BANK_CHANGE", "STATUTORY_CHANGE", "SEPARATION",
];

export default function ApprovalRules() {
  const [rules, setRules] = useState([]);
  const [costCenters, setCostCenters] = useState([]);
  const [categories, setCategories] = useState([]);
  const [roles, setRoles] = useState([]);
  const [error, setError] = useState("");
  const [form, setForm] = useState({ cost_center_id: "", employee_category_id: "", transaction_type: "EMPLOYEE_CREATION", approver_role: "" });

  function reload() {
    client.get("/approval-rules").then((res) => setRules(res.data));
    client.get("/cost-centers").then((res) => setCostCenters(res.data));
    client.get("/employee-categories").then((res) => setCategories(res.data));
    client.get("/auth/roles").then((res) => setRoles(res.data.filter((r) => r.name !== "HR_ADMIN")));
  }
  useEffect(reload, []);

  async function createRule() {
    setError("");
    try {
      await client.post("/approval-rules", {
        cost_center_id: form.cost_center_id ? Number(form.cost_center_id) : null,
        employee_category_id: form.employee_category_id ? Number(form.employee_category_id) : null,
        transaction_type: form.transaction_type,
        approver_role: form.approver_role,
      });
      setForm({ cost_center_id: "", employee_category_id: "", transaction_type: "EMPLOYEE_CREATION", approver_role: "" });
      reload();
    } catch (err) {
      setError(apiErrorMessage(err));
    }
  }

  async function removeRule(id) {
    await client.delete(`/approval-rules/${id}`);
    reload();
  }

  const ccName = (id) => costCenters.find((c) => c.id === id)?.name || "Any";
  const catName = (id) => categories.find((c) => c.id === id)?.name || "Any";

  const columns = [
    { key: "transaction_type", header: "Transaction Type" },
    { key: "cost_center", header: "Cost Center", render: (r) => ccName(r.cost_center_id) },
    { key: "employee_category", header: "Employee Category", render: (r) => catName(r.employee_category_id) },
    { key: "approver_role", header: "Approver Role" },
    { key: "actions", header: "", render: (r) => <Button variant="danger" size="sm" onClick={() => removeRule(r.id)}>Remove</Button> },
  ];

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-xl font-display font-semibold text-ink">Approval Rules</h1>
        <p className="text-sm text-ink/50 mt-1">
          Routes approvals by Cost Center + Employee Category + Transaction Type (blueprint §15). Leave Cost Center/Category blank for a fallback rule.
        </p>
      </div>
      {error && <div className="text-sm text-danger bg-danger/10 rounded-md px-3 py-2">{error}</div>}

      <Card>
        <h2 className="text-sm font-semibold text-ink mb-3">New Rule</h2>
        <div className="grid grid-cols-4 gap-2">
          <Select value={form.transaction_type} onChange={(e) => setForm({ ...form, transaction_type: e.target.value })}>
            {TRANSACTION_TYPES.map((t) => <option key={t} value={t}>{t}</option>)}
          </Select>
          <Select value={form.cost_center_id} onChange={(e) => setForm({ ...form, cost_center_id: e.target.value })}>
            <option value="">Any Cost Center</option>
            {costCenters.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
          </Select>
          <Select value={form.employee_category_id} onChange={(e) => setForm({ ...form, employee_category_id: e.target.value })}>
            <option value="">Any Category</option>
            {categories.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
          </Select>
          <Select value={form.approver_role} onChange={(e) => setForm({ ...form, approver_role: e.target.value })}>
            <option value="">Approver Role...</option>
            {roles.map((r) => <option key={r.id} value={r.name}>{r.name}</option>)}
          </Select>
        </div>
        <Button className="mt-3" onClick={createRule} disabled={!form.approver_role}>Add Rule</Button>
      </Card>

      <Card>
        <h2 className="text-sm font-semibold text-ink mb-3">All Rules</h2>
        <Table columns={columns} rows={rules} empty="No approval rules yet — approvals fall back to any Approver." />
      </Card>
    </div>
  );
}
