import { useEffect, useState } from "react";
import client, { apiErrorMessage } from "../api/client";
import { Card, Button, Select, Checkbox } from "../components/ui";

// HR_ADMIN and SUPER_ADMIN both bypass permission checks entirely
// (core/deps.py::require_permission) - granting them explicit
// RolePermission rows would do nothing, so they're not selectable here.
const BYPASS_ROLES = ["HR_ADMIN", "SUPER_ADMIN"];

export default function RolesPermissions() {
  const [roles, setRoles] = useState([]);
  const [permissions, setPermissions] = useState([]);
  const [roleId, setRoleId] = useState("");
  const [granted, setGranted] = useState(new Set());
  const [dirty, setDirty] = useState(false);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);

  const selectableRoles = roles.filter((r) => !BYPASS_ROLES.includes(r.name));

  useEffect(() => {
    client.get("/auth/roles").then((res) => {
      setRoles(res.data);
      const first = res.data.find((r) => !BYPASS_ROLES.includes(r.name));
      if (first) setRoleId(String(first.id));
    });
    client.get("/permissions").then((res) => setPermissions(res.data));
  }, []);

  function loadRole(id) {
    if (!id) return;
    setLoading(true);
    setError("");
    client.get(`/roles/${id}/permissions`)
      .then((res) => {
        setGranted(new Set(res.data.permission_codes));
        setDirty(false);
      })
      .catch((err) => setError(apiErrorMessage(err)))
      .finally(() => setLoading(false));
  }
  useEffect(() => loadRole(roleId), [roleId]);

  function toggle(code) {
    setGranted((prev) => {
      const next = new Set(prev);
      next.has(code) ? next.delete(code) : next.add(code);
      return next;
    });
    setDirty(true);
  }

  async function save() {
    setSaving(true);
    setError("");
    try {
      await client.put(`/roles/${roleId}/permissions`, { permission_codes: [...granted] });
      setDirty(false);
    } catch (err) {
      setError(apiErrorMessage(err));
    } finally {
      setSaving(false);
    }
  }

  const selectedRole = roles.find((r) => String(r.id) === String(roleId));

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-xl font-display font-semibold text-ink">Roles &amp; Permissions</h1>
        <p className="text-sm text-ink/50 mt-1">
          Granular permission grants (blueprint §18). Pick a role, edit its permissions, then save — HR_ADMIN and
          SUPER_ADMIN aren't shown since they implicitly have every permission.
        </p>
      </div>
      {error && <div className="text-sm text-danger bg-danger/10 rounded-md px-3 py-2">{error}</div>}

      <Card>
        <div className="flex items-end justify-between gap-4 mb-4">
          <div className="w-64">
            <Select label="Role" value={roleId} onChange={(e) => setRoleId(e.target.value)}>
              {selectableRoles.map((r) => <option key={r.id} value={r.id}>{r.name}</option>)}
            </Select>
          </div>
          <Button onClick={save} disabled={!dirty || saving || !roleId}>
            {saving ? "Saving…" : `Save ${selectedRole ? selectedRole.name : ""}`}
          </Button>
        </div>

        {loading ? (
          <div className="text-sm text-ink/40 py-10 text-center">Loading…</div>
        ) : (
          <div className="grid grid-cols-2 gap-x-6 gap-y-1">
            {permissions.map((code) => (
              <Checkbox
                key={code}
                label={<span className="font-mono text-xs">{code}</span>}
                checked={granted.has(code)}
                onChange={() => toggle(code)}
              />
            ))}
          </div>
        )}
      </Card>
    </div>
  );
}
