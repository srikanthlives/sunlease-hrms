import { useEffect, useState } from "react";
import client, { apiErrorMessage } from "../api/client";
import { Card, Button, Input, Select, Table, Checkbox } from "../components/ui";

export default function SelectionCriteriaConfig() {
  const [criteria, setCriteria] = useState([]);
  const [designations, setDesignations] = useState([]);
  const [costCenters, setCostCenters] = useState([]);
  const [assignments, setAssignments] = useState([]);
  const [designationFilter, setDesignationFilter] = useState("");
  const [error, setError] = useState("");
  const [newCriteria, setNewCriteria] = useState({ name: "", description: "" });
  const [assignForm, setAssignForm] = useState({ designation_id: "", cost_center_id: "", criteria_id: "", is_mandatory: true, sequence: "0" });

  function reload() {
    client.get("/recruitment/criteria").then((res) => setCriteria(res.data));
    client.get("/designations").then((res) => setDesignations(res.data));
    client.get("/cost-centers").then((res) => setCostCenters(res.data));
  }
  useEffect(reload, []);

  function reloadAssignments() {
    if (!designationFilter) {
      setAssignments([]);
      return;
    }
    client.get("/recruitment/designation-criteria", { params: { designation_id: designationFilter } }).then((res) => setAssignments(res.data));
  }
  useEffect(reloadAssignments, [designationFilter]);

  async function createCriteria() {
    setError("");
    try {
      await client.post("/recruitment/criteria", newCriteria);
      setNewCriteria({ name: "", description: "" });
      reload();
    } catch (err) {
      setError(apiErrorMessage(err));
    }
  }

  async function addAssignment() {
    setError("");
    try {
      await client.post("/recruitment/designation-criteria", {
        designation_id: Number(assignForm.designation_id),
        cost_center_id: assignForm.cost_center_id ? Number(assignForm.cost_center_id) : null,
        criteria_id: Number(assignForm.criteria_id),
        is_mandatory: assignForm.is_mandatory,
        sequence: Number(assignForm.sequence || 0),
      });
      setAssignForm({ ...assignForm, criteria_id: "", sequence: "0" });
      setDesignationFilter(assignForm.designation_id);
      reloadAssignments();
    } catch (err) {
      setError(apiErrorMessage(err));
    }
  }

  async function removeAssignment(id) {
    if (!window.confirm("Remove this requirement?")) return;
    try {
      await client.delete(`/recruitment/designation-criteria/${id}`);
      reloadAssignments();
    } catch (err) {
      setError(apiErrorMessage(err));
    }
  }

  const criteriaColumns = [
    { key: "name", header: "Name" },
    { key: "description", header: "Description", render: (r) => r.description || "—" },
    { key: "is_active", header: "Active", render: (r) => (r.is_active ? "Yes" : "No") },
  ];

  const assignmentColumns = [
    { key: "sequence", header: "#" },
    { key: "criteria_name", header: "Criteria" },
    { key: "cost_center_name", header: "Cost Center (blank = global)", render: (r) => r.cost_center_name || "All Cost Centers" },
    { key: "is_mandatory", header: "Mandatory", render: (r) => (r.is_mandatory ? "Yes" : "Optional") },
    {
      key: "_actions", header: "", align: "right",
      render: (r) => <Button variant="danger" size="sm" onClick={() => removeAssignment(r.id)}>Remove</Button>,
    },
  ];

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-xl font-display font-semibold text-ink">Selection Criteria</h1>
        <p className="text-sm text-ink/50 mt-1">
          Define selection-process tests/stages, then assign which ones each Designation requires — optionally scoped
          to a specific Cost Center (a Cost-Center-scoped requirement overrides a global one for the same criteria).
        </p>
      </div>
      {error && <div className="text-sm text-danger bg-danger/10 rounded-md px-3 py-2">{error}</div>}

      <Card>
        <h2 className="text-sm font-semibold text-ink mb-3">New Selection Criteria</h2>
        <div className="grid grid-cols-3 gap-2">
          <Input placeholder="Name (e.g. Govt Steering Test)" value={newCriteria.name} onChange={(e) => setNewCriteria({ ...newCriteria, name: e.target.value })} />
          <Input placeholder="Description (optional)" value={newCriteria.description} onChange={(e) => setNewCriteria({ ...newCriteria, description: e.target.value })} />
          <Button onClick={createCriteria} disabled={!newCriteria.name}>Add Criteria</Button>
        </div>
      </Card>

      <Card>
        <h2 className="text-sm font-semibold text-ink mb-3">All Selection Criteria</h2>
        <Table columns={criteriaColumns} rows={criteria} empty="No selection criteria yet." />
      </Card>

      <Card>
        <h2 className="text-sm font-semibold text-ink mb-3">Designation Requirements</h2>
        <div className="grid grid-cols-5 gap-2 mb-4">
          <Select value={assignForm.designation_id} onChange={(e) => { setAssignForm({ ...assignForm, designation_id: e.target.value }); setDesignationFilter(e.target.value); }}>
            <option value="">Designation...</option>
            {designations.map((d) => <option key={d.id} value={d.id}>{d.name}</option>)}
          </Select>
          <Select value={assignForm.cost_center_id} onChange={(e) => setAssignForm({ ...assignForm, cost_center_id: e.target.value })}>
            <option value="">All Cost Centers</option>
            {costCenters.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
          </Select>
          <Select value={assignForm.criteria_id} onChange={(e) => setAssignForm({ ...assignForm, criteria_id: e.target.value })}>
            <option value="">Criteria...</option>
            {criteria.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
          </Select>
          <Input type="number" placeholder="Sequence" value={assignForm.sequence} onChange={(e) => setAssignForm({ ...assignForm, sequence: e.target.value })} />
          <Button onClick={addAssignment} disabled={!assignForm.designation_id || !assignForm.criteria_id}>Add Requirement</Button>
        </div>
        <Checkbox label="Mandatory (must pass to convert to employee)" checked={assignForm.is_mandatory} onChange={(e) => setAssignForm({ ...assignForm, is_mandatory: e.target.checked })} />

        {designationFilter ? (
          <div className="mt-4">
            <Table columns={assignmentColumns} rows={assignments} empty="No requirements set for this designation yet." />
          </div>
        ) : (
          <p className="text-xs text-ink/40 mt-4">Select a designation above to view/edit its requirements.</p>
        )}
      </Card>
    </div>
  );
}
