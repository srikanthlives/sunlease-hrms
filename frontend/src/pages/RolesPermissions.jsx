import { useEffect, useState } from "react";
import client, { apiErrorMessage } from "../api/client";
import { Card, Button } from "../components/ui";

export default function RolesPermissions() {
  const [roles, setRoles] = useState([]);
  const [permissions, setPermissions] = useState([]);
  const [grants, setGrants] = useState({}); // role_id -> Set(codes)
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(null);

  useEffect(() => {
    client.get("/auth/roles").then(async (res) => {
      setRoles(res.data);
      const perms = await client.get("/permissions");
      setPermissions(perms.data);
      const entries = await Promise.all(
        res.data.map((r) => client.get(`/roles/${r.id}/permissions`).then((g) => [r.id, new Set(g.data.permission_codes)]))
      );
      setGrants(Object.fromEntries(entries));
    });
  }, []);

  function toggle(roleId, code) {
    setGrants((prev) => {
      const next = new Set(prev[roleId] || []);
      next.has(code) ? next.delete(code) : next.add(code);
      return { ...prev, [roleId]: next };
    });
  }

  async function save(roleId) {
    setSaving(roleId);
    setError("");
    try {
      await client.put(`/roles/${roleId}/permissions`, { permission_codes: [...(grants[roleId] || [])] });
    } catch (err) {
      setError(apiErrorMessage(err));
    } finally {
      setSaving(null);
    }
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-xl font-display font-semibold text-ink">Roles &amp; Permissions</h1>
        <p className="text-sm text-ink/50 mt-1">
          Granular permission grants (blueprint §18). HR_ADMIN is not shown — it implicitly has every permission.
        </p>
      </div>
      {error && <div className="text-sm text-danger bg-danger/10 rounded-md px-3 py-2">{error}</div>}

      <Card>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-xs uppercase tracking-wide text-ink/40 border-b border-ink/10">
                <th className="py-2 px-3">Permission</th>
                {roles.filter((r) => r.name !== "HR_ADMIN").map((r) => (
                  <th key={r.id} className="py-2 px-3 text-center">{r.name}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {permissions.map((code) => (
                <tr key={code} className="border-b border-ink/5 last:border-0">
                  <td className="py-2 px-3 font-mono text-xs">{code}</td>
                  {roles.filter((r) => r.name !== "HR_ADMIN").map((r) => (
                    <td key={r.id} className="py-2 px-3 text-center">
                      <input
                        type="checkbox"
                        checked={grants[r.id]?.has(code) || false}
                        onChange={() => toggle(r.id, code)}
                      />
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <div className="flex gap-2 mt-4">
          {roles.filter((r) => r.name !== "HR_ADMIN").map((r) => (
            <Button key={r.id} variant="outline" size="sm" onClick={() => save(r.id)} disabled={saving === r.id}>
              {saving === r.id ? "Saving…" : `Save ${r.name}`}
            </Button>
          ))}
        </div>
      </Card>
    </div>
  );
}
