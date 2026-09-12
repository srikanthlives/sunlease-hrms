import { useEffect, useRef, useState } from "react";
import { Download, Upload, AlertTriangle } from "lucide-react";
import client, { apiErrorMessage } from "../api/client";
import { Card, Button, Input, Select, Table, StatusBadge } from "../components/ui";
import { useAuth } from "../context/AuthContext";

export default function UsersAdmin() {
  const { user: me } = useAuth();
  const isSuperAdmin = me?.role === "SUPER_ADMIN";
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

      {isSuperAdmin && <DatabaseBackupCard />}

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

// SUPER_ADMIN-only - a role distinct from and narrower-privileged-except-
// here than HR_ADMIN (see backend/app/models/enums.py::RoleName), gating
// the one thing HR_ADMIN itself cannot do: replace the live database.
function DatabaseBackupCard() {
  const fileInputRef = useRef(null);
  const [downloading, setDownloading] = useState(false);
  const [error, setError] = useState("");
  const [pendingFile, setPendingFile] = useState(null);

  async function downloadBackup() {
    setDownloading(true);
    setError("");
    try {
      const res = await client.get("/admin/db-backup", { responseType: "blob" });
      const disposition = res.headers["content-disposition"] || "";
      const match = disposition.match(/filename="?([^"]+)"?/);
      const filename = match ? match[1] : "hrms-backup.db";
      const url = URL.createObjectURL(res.data);
      const a = document.createElement("a");
      a.href = url;
      a.download = filename;
      a.click();
      URL.revokeObjectURL(url);
    } catch (err) {
      setError(await blobErrorMessage(err));
    } finally {
      setDownloading(false);
    }
  }

  function pickFile(e) {
    const file = e.target.files?.[0];
    if (file) setPendingFile(file);
    e.target.value = "";
  }

  return (
    <Card>
      <h2 className="text-sm font-semibold text-ink mb-1">Database Backup &amp; Restore</h2>
      <p className="text-xs text-ink/50 mb-3">
        Super-admin only. Restoring replaces the entire live database — every employee, payroll, attendance, and
        leave record currently in it — with the uploaded file.
      </p>
      {error && <div className="text-sm text-danger bg-danger/10 rounded-md px-3 py-2 mb-3">{error}</div>}
      <div className="flex gap-2">
        <Button variant="outline" onClick={downloadBackup} disabled={downloading} className="gap-1.5">
          <Download size={14} /> {downloading ? "Downloading…" : "Download Backup"}
        </Button>
        <Button variant="outline" onClick={() => fileInputRef.current?.click()} className="gap-1.5">
          <Upload size={14} /> Upload &amp; Restore…
        </Button>
        <input ref={fileInputRef} type="file" accept=".db,.sqlite,.sqlite3" className="hidden" onChange={pickFile} />
      </div>

      {pendingFile && (
        <RestoreConfirmModal file={pendingFile} onClose={() => setPendingFile(null)} />
      )}
    </Card>
  );
}

async function blobErrorMessage(err) {
  const blob = err?.response?.data;
  if (blob instanceof Blob) {
    try {
      const text = await blob.text();
      return JSON.parse(text)?.detail || apiErrorMessage(err);
    } catch {
      return apiErrorMessage(err);
    }
  }
  return apiErrorMessage(err);
}

function RestoreConfirmModal({ file, onClose }) {
  const [step, setStep] = useState(1);
  const [confirmText, setConfirmText] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [done, setDone] = useState(false);

  async function restore() {
    setBusy(true);
    setError("");
    try {
      const form = new FormData();
      form.append("file", file);
      form.append("confirm", "REPLACE");
      await client.post("/admin/db-restore", form);
      setDone(true);
    } catch (err) {
      setError(await blobErrorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50" onClick={busy ? undefined : onClose}>
      <div className="bg-white rounded-lg p-5 w-full max-w-md" onClick={(e) => e.stopPropagation()}>
        {done ? (
          <>
            <h3 className="text-sm font-semibold text-ink mb-2">Database restored</h3>
            <p className="text-sm text-ink/60 mb-4">
              The previous database was saved as a timestamped backup on the server before being replaced. Reload
              the app to see the restored data.
            </p>
            <div className="flex justify-end">
              <Button onClick={() => window.location.reload()}>Reload Now</Button>
            </div>
          </>
        ) : step === 1 ? (
          <>
            <div className="flex items-center gap-2 mb-2 text-danger">
              <AlertTriangle size={18} />
              <h3 className="text-sm font-semibold">This will permanently replace the database</h3>
            </div>
            <p className="text-sm text-ink/60 mb-4">
              Uploading <strong>{file.name}</strong> will overwrite every employee, payroll, attendance, and leave
              record currently in this system with what's in that file. This cannot be undone from within the app —
              a server-side backup of the current database is kept automatically, but recovering it requires server
              file access.
            </p>
            <div className="flex justify-end gap-2">
              <Button variant="outline" onClick={onClose}>Cancel</Button>
              <Button variant="danger" onClick={() => setStep(2)}>Continue</Button>
            </div>
          </>
        ) : (
          <>
            <h3 className="text-sm font-semibold text-ink mb-2">Type REPLACE to confirm</h3>
            <p className="text-sm text-ink/60 mb-3">
              Last chance — this action is irreversible from the app. Type <strong>REPLACE</strong> below to proceed.
            </p>
            {error && <div className="text-sm text-danger bg-danger/10 rounded-md px-3 py-2 mb-3">{error}</div>}
            <Input value={confirmText} onChange={(e) => setConfirmText(e.target.value)} placeholder="REPLACE" disabled={busy} />
            <div className="flex justify-end gap-2 mt-4">
              <Button variant="outline" onClick={onClose} disabled={busy}>Cancel</Button>
              <Button variant="danger" onClick={restore} disabled={busy || confirmText !== "REPLACE"}>
                {busy ? "Restoring…" : "Permanently replace database"}
              </Button>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
