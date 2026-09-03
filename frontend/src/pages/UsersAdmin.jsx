import { useEffect, useState } from "react";
import client, { apiErrorMessage } from "../api/client";
import { Card, Button, Input, Select, Table, StatusBadge } from "../components/ui";

export default function UsersAdmin() {
  const [users, setUsers] = useState([]);
  const [roles, setRoles] = useState([]);
  const [costCenters, setCostCenters] = useState([]);
  const [error, setError] = useState("");
  const [form, setForm] = useState({ username: "", full_name: "", email: "", password: "", role_id: "" });
  const [scopeUserId, setScopeUserId] = useState(null);
  const [scopeSelection, setScopeSelection] = useState([]);

  function reload() {
    client.get("/auth/users").then((res) => setUsers(res.data));
    client.get("/auth/roles").then((res) => setRoles(res.data));
    client.get("/cost-centers").then((res) => setCostCenters(res.data));
  }
  useEffect(reload, []);

  async function createUser() {
    setError("");
    try {
      await client.post("/auth/users", { ...form, role_id: Number(form.role_id) });
      setForm({ username: "", full_name: "", email: "", password: "", role_id: "" });
      reload();
    } catch (err) {
      setError(apiErrorMessage(err));
    }
  }

  async function openScope(userId) {
    setScopeUserId(userId);
    const res = await client.get(`/users/${userId}/cost-center-scope`);
    setScopeSelection(res.data.cost_center_ids);
  }

  async function saveScope() {
    setError("");
    try {
      await client.put(`/users/${scopeUserId}/cost-center-scope`, { cost_center_ids: scopeSelection });
      setScopeUserId(null);
    } catch (err) {
      setError(apiErrorMessage(err));
    }
  }

  function toggleScope(id) {
    setScopeSelection((sel) => (sel.includes(id) ? sel.filter((x) => x !== id) : [...sel, id]));
  }

  const columns = [
    { key: "username", header: "Username" },
    { key: "full_name", header: "Name", render: (u) => u.full_name || "—" },
    { key: "role", header: "Role", render: (u) => <StatusBadge status={u.role} /> },
    {
      key: "scope", header: "Cost Center Scope", render: (u) =>
        u.role === "HR_ADMIN" ? <span className="text-ink/40 text-xs">All (bypasses scope)</span> :
          <Button variant="outline" size="sm" onClick={() => openScope(u.id)} className="text-xs">Manage Scope</Button>,
    },
  ];

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-xl font-display font-semibold text-ink">Users &amp; Roles</h1>
        <p className="text-sm text-ink/50 mt-1">Create HRMS logins and manage Cost Center scope (blueprint §18)</p>
      </div>
      {error && <div className="text-sm text-danger bg-danger/10 rounded-md px-3 py-2">{error}</div>}

      <Card>
        <h2 className="text-sm font-semibold text-ink mb-3">New User</h2>
        <div className="grid grid-cols-5 gap-2">
          <Input placeholder="Username" value={form.username} onChange={(e) => setForm({ ...form, username: e.target.value })} />
          <Input placeholder="Full Name" value={form.full_name} onChange={(e) => setForm({ ...form, full_name: e.target.value })} />
          <Input placeholder="Email" value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} />
          <Input placeholder="Password" type="password" value={form.password} onChange={(e) => setForm({ ...form, password: e.target.value })} />
          <Select value={form.role_id} onChange={(e) => setForm({ ...form, role_id: e.target.value })}>
            <option value="">Role...</option>
            {roles.map((r) => <option key={r.id} value={r.id}>{r.name}</option>)}
          </Select>
        </div>
        <Button className="mt-3" onClick={createUser} disabled={!form.username || !form.password || !form.role_id}>
          Create User
        </Button>
      </Card>

      <Card>
        <h2 className="text-sm font-semibold text-ink mb-3">All Users</h2>
        <Table columns={columns} rows={users} />
      </Card>

      {scopeUserId && (
        <div className="fixed inset-0 bg-black/30 flex items-center justify-center z-50" onClick={() => setScopeUserId(null)}>
          <div className="bg-white rounded-lg p-5 w-full max-w-sm" onClick={(e) => e.stopPropagation()}>
            <h3 className="text-sm font-semibold text-ink mb-3">Cost Center Scope</h3>
            <div className="space-y-2 max-h-60 overflow-y-auto">
              {costCenters.map((cc) => (
                <label key={cc.id} className="flex items-center gap-2 text-sm">
                  <input type="checkbox" checked={scopeSelection.includes(cc.id)} onChange={() => toggleScope(cc.id)} />
                  {cc.name} ({cc.code})
                </label>
              ))}
            </div>
            <div className="flex justify-end gap-2 mt-4">
              <Button variant="outline" onClick={() => setScopeUserId(null)}>Cancel</Button>
              <Button onClick={saveScope}>Save</Button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
