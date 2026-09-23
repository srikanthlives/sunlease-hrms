import { useEffect, useState } from "react";
import client, { apiErrorMessage } from "../api/client";
import { Card, Button, Input, Select, Table, Checkbox, StatusBadge } from "../components/ui";

export default function SelectionCriteriaConfig() {
  const [criteria, setCriteria] = useState([]);
  const [designations, setDesignations] = useState([]);
  const [costCenters, setCostCenters] = useState([]);
  const [assignments, setAssignments] = useState([]);
  const [error, setError] = useState("");
  const [newCriteria, setNewCriteria] = useState({ name: "", description: "" });
  const [editingCriteriaId, setEditingCriteriaId] = useState(null);
  const [editCriteriaForm, setEditCriteriaForm] = useState({ name: "", description: "", is_active: true });
  const [editingAssignmentId, setEditingAssignmentId] = useState(null);
  const [editAssignmentForm, setEditAssignmentForm] = useState({ is_mandatory: true, sequence: "0", is_active: true });

  // Add Requirement form - designation is single-select (a requirement
  // always targets exactly one designation), but Cost Center and
  // Criteria are multi-select so one submit can fan out into many rows
  // at once (e.g. "these 3 tests, required for both this Cost Center and
  // that one, plus globally") instead of adding them one at a time.
  const [assignDesignationId, setAssignDesignationId] = useState("");
  const [assignIncludeGlobal, setAssignIncludeGlobal] = useState(true);
  const [assignCostCenterIds, setAssignCostCenterIds] = useState([]);
  const [assignCriteriaIds, setAssignCriteriaIds] = useState([]);
  const [assignIsMandatory, setAssignIsMandatory] = useState(true);
  const [assignSequence, setAssignSequence] = useState("0");
  const [adding, setAdding] = useState(false);

  // Filters for the full requirements list below.
  const [filterDesignation, setFilterDesignation] = useState("");
  const [filterCostCenter, setFilterCostCenter] = useState("");
  const [filterCriteria, setFilterCriteria] = useState("");
  const [filterMandatory, setFilterMandatory] = useState("");
  const [filterActive, setFilterActive] = useState("ACTIVE");

  function reload() {
    client.get("/recruitment/criteria", { params: { include_inactive: true } }).then((res) => setCriteria(res.data));
    client.get("/designations").then((res) => setDesignations(res.data));
    client.get("/cost-centers").then((res) => setCostCenters(res.data));
    reloadAssignments();
  }
  useEffect(reload, []);

  function reloadAssignments() {
    client.get("/recruitment/designation-criteria", { params: { include_inactive: true } }).then((res) => setAssignments(res.data));
  }

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

  function startEditCriteria(row) {
    setEditingCriteriaId(row.id);
    setEditCriteriaForm({ name: row.name, description: row.description || "", is_active: row.is_active });
  }

  function cancelEditCriteria() {
    setEditingCriteriaId(null);
  }

  async function saveEditCriteria() {
    setError("");
    try {
      await client.put(`/recruitment/criteria/${editingCriteriaId}`, editCriteriaForm);
      setEditingCriteriaId(null);
      reload();
    } catch (err) {
      setError(apiErrorMessage(err));
    }
  }

  function toggleInList(list, setList, id) {
    setList(list.includes(id) ? list.filter((x) => x !== id) : [...list, id]);
  }

  async function addAssignments() {
    setError("");
    setAdding(true);
    const scopes = [...(assignIncludeGlobal ? [null] : []), ...assignCostCenterIds];
    const sequence = Number(assignSequence || 0);
    let created = 0;
    const failures = [];
    try {
      for (const costCenterId of scopes) {
        for (const criteriaId of assignCriteriaIds) {
          try {
            await client.post("/recruitment/designation-criteria", {
              designation_id: Number(assignDesignationId),
              cost_center_id: costCenterId,
              criteria_id: criteriaId,
              is_mandatory: assignIsMandatory,
              sequence,
            });
            created += 1;
          } catch (err) {
            const ccName = costCenterId ? (costCenters.find((c) => c.id === costCenterId)?.name || costCenterId) : "Global";
            const critName = criteria.find((c) => c.id === criteriaId)?.name || criteriaId;
            failures.push(`${ccName} / ${critName}: ${apiErrorMessage(err)}`);
          }
        }
      }
      if (failures.length) {
        setError(`${created} requirement(s) added. ${failures.length} skipped — ${failures.join("; ")}`);
      }
      setAssignCriteriaIds([]);
      reloadAssignments();
      setFilterDesignation(assignDesignationId);
    } finally {
      setAdding(false);
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

  function startEditAssignment(row) {
    setEditingAssignmentId(row.id);
    setEditAssignmentForm({ is_mandatory: row.is_mandatory, sequence: String(row.sequence), is_active: row.is_active });
  }

  function cancelEditAssignment() {
    setEditingAssignmentId(null);
  }

  async function saveEditAssignment() {
    setError("");
    try {
      await client.put(`/recruitment/designation-criteria/${editingAssignmentId}`, {
        is_mandatory: editAssignmentForm.is_mandatory,
        sequence: Number(editAssignmentForm.sequence || 0),
        is_active: editAssignmentForm.is_active,
      });
      setEditingAssignmentId(null);
      reloadAssignments();
    } catch (err) {
      setError(apiErrorMessage(err));
    }
  }

  async function toggleAssignmentActive(row) {
    setError("");
    try {
      await client.put(`/recruitment/designation-criteria/${row.id}`, {
        is_mandatory: row.is_mandatory, sequence: row.sequence, is_active: !row.is_active,
      });
      reloadAssignments();
    } catch (err) {
      setError(apiErrorMessage(err));
    }
  }

  const criteriaColumns = [
    {
      key: "name", header: "Name",
      render: (r) => editingCriteriaId === r.id
        ? <Input value={editCriteriaForm.name} onChange={(e) => setEditCriteriaForm({ ...editCriteriaForm, name: e.target.value })} />
        : r.name,
    },
    {
      key: "description", header: "Description",
      render: (r) => editingCriteriaId === r.id
        ? <Input value={editCriteriaForm.description} onChange={(e) => setEditCriteriaForm({ ...editCriteriaForm, description: e.target.value })} />
        : (r.description || "—"),
    },
    {
      key: "is_active", header: "Active",
      render: (r) => editingCriteriaId === r.id
        ? <Checkbox checked={editCriteriaForm.is_active} onChange={(e) => setEditCriteriaForm({ ...editCriteriaForm, is_active: e.target.checked })} />
        : <StatusBadge status={r.is_active ? "ACTIVE" : "INACTIVE"} />,
    },
    {
      key: "_actions", header: "", align: "right",
      render: (r) => editingCriteriaId === r.id ? (
        <div className="flex gap-2 justify-end">
          <Button variant="outline" size="sm" onClick={cancelEditCriteria}>Cancel</Button>
          <Button size="sm" onClick={saveEditCriteria} disabled={!editCriteriaForm.name}>Save</Button>
        </div>
      ) : (
        <Button variant="outline" size="sm" onClick={() => startEditCriteria(r)}>Edit</Button>
      ),
    },
  ];

  const filteredAssignments = assignments.filter((r) => {
    if (filterDesignation && String(r.designation_id) !== filterDesignation) return false;
    if (filterCostCenter === "GLOBAL" && r.cost_center_id) return false;
    if (filterCostCenter && filterCostCenter !== "GLOBAL" && String(r.cost_center_id) !== filterCostCenter) return false;
    if (filterCriteria && String(r.criteria_id) !== filterCriteria) return false;
    if (filterMandatory === "YES" && !r.is_mandatory) return false;
    if (filterMandatory === "NO" && r.is_mandatory) return false;
    if (filterActive === "ACTIVE" && !r.is_active) return false;
    if (filterActive === "INACTIVE" && r.is_active) return false;
    return true;
  });

  const assignmentColumns = [
    { key: "designation_name", header: "Designation" },
    {
      key: "sequence", header: "#",
      render: (r) => editingAssignmentId === r.id
        ? <Input type="number" className="w-16" value={editAssignmentForm.sequence} onChange={(e) => setEditAssignmentForm({ ...editAssignmentForm, sequence: e.target.value })} />
        : r.sequence,
    },
    { key: "criteria_name", header: "Criteria" },
    { key: "cost_center_name", header: "Cost Center (blank = global)", render: (r) => r.cost_center_name || "All Cost Centers" },
    {
      key: "is_mandatory", header: "Mandatory",
      render: (r) => editingAssignmentId === r.id
        ? <Checkbox checked={editAssignmentForm.is_mandatory} onChange={(e) => setEditAssignmentForm({ ...editAssignmentForm, is_mandatory: e.target.checked })} />
        : (r.is_mandatory ? "Yes" : "Optional"),
    },
    {
      key: "is_active", header: "Active",
      render: (r) => editingAssignmentId === r.id
        ? <Checkbox checked={editAssignmentForm.is_active} onChange={(e) => setEditAssignmentForm({ ...editAssignmentForm, is_active: e.target.checked })} />
        : <StatusBadge status={r.is_active ? "ACTIVE" : "INACTIVE"} />,
    },
    {
      key: "_actions", header: "", align: "right",
      render: (r) => editingAssignmentId === r.id ? (
        <div className="flex gap-2 justify-end">
          <Button variant="outline" size="sm" onClick={cancelEditAssignment}>Cancel</Button>
          <Button size="sm" onClick={saveEditAssignment}>Save</Button>
        </div>
      ) : (
        <div className="flex gap-2 justify-end">
          <Button variant="outline" size="sm" onClick={() => startEditAssignment(r)}>Edit</Button>
          <Button variant="outline" size="sm" onClick={() => toggleAssignmentActive(r)}>{r.is_active ? "Deactivate" : "Activate"}</Button>
          <Button variant="danger" size="sm" onClick={() => removeAssignment(r.id)}>Remove</Button>
        </div>
      ),
    },
  ];

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-xl font-display font-semibold text-ink">Selection Criteria</h1>
        <p className="text-sm text-ink/50 mt-1">
          Define selection-process tests/stages, then assign which ones each Designation requires — optionally scoped
          to one or more Cost Centers (a Cost-Center-scoped requirement overrides a global one for the same criteria).
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
        <h2 className="text-sm font-semibold text-ink mb-3">Add Designation Requirement(s)</h2>
        <p className="text-xs text-ink/40 mb-3">
          Pick a Designation, one or more Cost Centers (or leave Global checked to apply everywhere), and one or more
          Tests — every combination is added at once with the same Mandatory/Sequence setting.
        </p>
        <div className="grid grid-cols-2 gap-4 mb-4">
          <div>
            <div className="text-xs font-medium text-ink/60 mb-1">Designation</div>
            <Select value={assignDesignationId} onChange={(e) => setAssignDesignationId(e.target.value)}>
              <option value="">Select designation...</option>
              {designations.map((d) => <option key={d.id} value={d.id}>{d.name}</option>)}
            </Select>

            <div className="text-xs font-medium text-ink/60 mb-1 mt-3">Mandatory / Sequence</div>
            <div className="flex items-center gap-3">
              <Checkbox label="Mandatory" checked={assignIsMandatory} onChange={(e) => setAssignIsMandatory(e.target.checked)} />
              <Input type="number" className="w-24" placeholder="Sequence" value={assignSequence} onChange={(e) => setAssignSequence(e.target.value)} />
            </div>
          </div>

          <div>
            <div className="text-xs font-medium text-ink/60 mb-1">Cost Center(s)</div>
            <div className="border border-ink/10 rounded-md p-2 max-h-36 overflow-y-auto space-y-1">
              <label className="flex items-center gap-2 text-sm">
                <input type="checkbox" checked={assignIncludeGlobal} onChange={(e) => setAssignIncludeGlobal(e.target.checked)} />
                Global (all Cost Centers)
              </label>
              {costCenters.map((cc) => (
                <label key={cc.id} className="flex items-center gap-2 text-sm">
                  <input type="checkbox" checked={assignCostCenterIds.includes(cc.id)} onChange={() => toggleInList(assignCostCenterIds, setAssignCostCenterIds, cc.id)} />
                  {cc.name}
                </label>
              ))}
            </div>
          </div>
        </div>

        <div className="mb-4">
          <div className="text-xs font-medium text-ink/60 mb-1">Test(s)</div>
          <div className="border border-ink/10 rounded-md p-2 max-h-36 overflow-y-auto grid grid-cols-3 gap-1">
            {criteria.filter((c) => c.is_active).map((c) => (
              <label key={c.id} className="flex items-center gap-2 text-sm">
                <input type="checkbox" checked={assignCriteriaIds.includes(c.id)} onChange={() => toggleInList(assignCriteriaIds, setAssignCriteriaIds, c.id)} />
                {c.name}
              </label>
            ))}
          </div>
        </div>

        <Button
          onClick={addAssignments}
          disabled={adding || !assignDesignationId || assignCriteriaIds.length === 0 || (!assignIncludeGlobal && assignCostCenterIds.length === 0)}
        >
          {adding ? "Adding…" : `Add Requirement${assignCriteriaIds.length * (assignCostCenterIds.length + (assignIncludeGlobal ? 1 : 0)) > 1 ? "s" : ""}`}
        </Button>
      </Card>

      <Card>
        <h2 className="text-sm font-semibold text-ink mb-3">All Designation Requirements</h2>
        <div className="flex flex-wrap items-end gap-2 mb-3">
          <div className="w-48">
            <Select value={filterDesignation} onChange={(e) => setFilterDesignation(e.target.value)}>
              <option value="">All Designations</option>
              {designations.map((d) => <option key={d.id} value={d.id}>{d.name}</option>)}
            </Select>
          </div>
          <div className="w-48">
            <Select value={filterCostCenter} onChange={(e) => setFilterCostCenter(e.target.value)}>
              <option value="">All Cost Centers</option>
              <option value="GLOBAL">Global only</option>
              {costCenters.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
            </Select>
          </div>
          <div className="w-48">
            <Select value={filterCriteria} onChange={(e) => setFilterCriteria(e.target.value)}>
              <option value="">All Tests</option>
              {criteria.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
            </Select>
          </div>
          <div className="w-40">
            <Select value={filterMandatory} onChange={(e) => setFilterMandatory(e.target.value)}>
              <option value="">Mandatory or Optional</option>
              <option value="YES">Mandatory only</option>
              <option value="NO">Optional only</option>
            </Select>
          </div>
          <div className="w-40">
            <Select value={filterActive} onChange={(e) => setFilterActive(e.target.value)}>
              <option value="">Active or Inactive</option>
              <option value="ACTIVE">Active only</option>
              <option value="INACTIVE">Inactive only</option>
            </Select>
          </div>
          {(filterDesignation || filterCostCenter || filterCriteria || filterMandatory || filterActive !== "ACTIVE") && (
            <Button
              variant="ghost" size="sm"
              onClick={() => { setFilterDesignation(""); setFilterCostCenter(""); setFilterCriteria(""); setFilterMandatory(""); setFilterActive(""); }}
            >
              Clear
            </Button>
          )}
        </div>
        <Table columns={assignmentColumns} rows={filteredAssignments} empty="No requirements match the current filters." />
      </Card>
    </div>
  );
}
