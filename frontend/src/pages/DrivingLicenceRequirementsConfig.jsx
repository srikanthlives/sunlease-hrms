import { useEffect, useState } from "react";
import client, { apiErrorMessage } from "../api/client";
import { Card, Button, Select, Checkbox, Table, StatusBadge } from "../components/ui";

export default function DrivingLicenceRequirementsConfig() {
  const [rules, setRules] = useState([]);
  const [employeeTypes, setEmployeeTypes] = useState([]);
  const [categories, setCategories] = useState([]);
  const [designations, setDesignations] = useState([]);
  const [error, setError] = useState("");
  const [form, setForm] = useState({ employee_type_id: "", employee_category_id: "", designation_id: "", is_required: true });

  function reload() {
    client.get("/driving-licence-requirements").then((res) => setRules(res.data));
    client.get("/employee-types").then((res) => setEmployeeTypes(res.data));
    client.get("/employee-categories").then((res) => setCategories(res.data));
    client.get("/designations").then((res) => setDesignations(res.data));
  }
  useEffect(reload, []);

  async function createRule() {
    setError("");
    try {
      await client.post("/driving-licence-requirements", {
        employee_type_id: form.employee_type_id ? Number(form.employee_type_id) : null,
        employee_category_id: form.employee_category_id ? Number(form.employee_category_id) : null,
        designation_id: form.designation_id ? Number(form.designation_id) : null,
        is_required: form.is_required,
      });
      setForm({ employee_type_id: "", employee_category_id: "", designation_id: "", is_required: true });
      reload();
    } catch (err) {
      setError(apiErrorMessage(err));
    }
  }

  async function removeRule(id) {
    await client.delete(`/driving-licence-requirements/${id}`);
    reload();
  }

  const nameOf = (list, id) => list.find((x) => x.id === id)?.name || "Any";
  const hasAnyScope = form.employee_type_id || form.employee_category_id || form.designation_id;

  const columns = [
    { key: "employee_type", header: "Employee Type (priority 1)", render: (r) => nameOf(employeeTypes, r.employee_type_id) },
    { key: "employee_category", header: "Category (priority 2)", render: (r) => nameOf(categories, r.employee_category_id) },
    { key: "designation", header: "Designation (priority 3)", render: (r) => nameOf(designations, r.designation_id) },
    { key: "required", header: "Required", render: (r) => <StatusBadge status={r.is_required ? "ACTIVE" : "INACTIVE"} /> },
    {
      key: "candidates", header: "Applies to Candidates?",
      render: (r) => r.employee_type_id ? (
        <span className="text-xs text-ink/40">No — Employee Type set</span>
      ) : (
        <span className="text-xs text-ok">Yes</span>
      ),
    },
    { key: "actions", header: "", render: (r) => <Button variant="danger" size="sm" onClick={() => removeRule(r.id)}>Remove</Button> },
  ];

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-xl font-display font-semibold text-ink">Driving Licence Configuration</h1>
        <p className="text-sm text-ink/50 mt-1">
          Controls whether the Driving Licence step/section appears — in the Employee Wizard <strong>and</strong> on a Candidate's
          page during recruitment — scoped by Employee Type / Category / Designation. When more than one rule matches,{" "}
          <strong>Employee Type wins over Category, which wins over Designation</strong> — leave a dimension blank to make the rule
          apply to everyone on that dimension. Leave all three blank for a global rule.
        </p>
        <p className="text-sm text-amber-800 bg-amber-50 border border-amber-200 rounded-md px-3 py-2 mt-2">
          <strong>To configure for Candidates:</strong> leave Employee Type as "Any Employee Type" (a Candidate has no
          Employee Type yet — that's only chosen at conversion — so a rule that specifies one <em>never</em> reaches
          candidates, only employees post-conversion). Scope the rule by Category and/or Designation instead — e.g.
          Category = "Driver", or Designation = "Bus Driver". The "Applies to Candidates?" column below shows which
          existing rules will actually be seen during recruitment.
        </p>
      </div>
      {error && <div className="text-sm text-danger bg-danger/10 rounded-md px-3 py-2">{error}</div>}

      <Card>
        <h2 className="text-sm font-semibold text-ink mb-3">New Rule</h2>
        <div className="grid grid-cols-3 gap-2">
          <Select value={form.employee_type_id} onChange={(e) => setForm({ ...form, employee_type_id: e.target.value })}>
            <option value="">Any Employee Type</option>
            {employeeTypes.map((t) => <option key={t.id} value={t.id}>{t.name}</option>)}
          </Select>
          <Select value={form.employee_category_id} onChange={(e) => setForm({ ...form, employee_category_id: e.target.value })}>
            <option value="">Any Category</option>
            {categories.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
          </Select>
          <Select value={form.designation_id} onChange={(e) => setForm({ ...form, designation_id: e.target.value })}>
            <option value="">Any Designation</option>
            {designations.map((d) => <option key={d.id} value={d.id}>{d.name}</option>)}
          </Select>
        </div>
        <Checkbox
          label="Required (informational — the form is always optional to skip, this just labels it)"
          checked={form.is_required}
          onChange={(e) => setForm({ ...form, is_required: e.target.checked })}
          className="mt-3"
        />
        <div>
          <Button className="mt-3" onClick={createRule}>Add Rule</Button>
        </div>
        {!hasAnyScope && <p className="text-xs text-warn mt-2">No dimension selected — this will apply to every employee.</p>}
      </Card>

      <Card>
        <h2 className="text-sm font-semibold text-ink mb-3">All Rules</h2>
        <Table columns={columns} rows={rules} empty="No driving licence rules yet — the step is hidden for everyone." />
      </Card>
    </div>
  );
}
