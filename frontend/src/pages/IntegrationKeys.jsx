import { useEffect, useState } from "react";
import { Copy, RefreshCw, ShieldOff, ShieldCheck, Pencil, CalendarClock, Check } from "lucide-react";
import client, { apiErrorMessage } from "../api/client";
import { Card, Button, Input, Table, StatusBadge, formatDateTime } from "../components/ui";
import { useAuth } from "../context/AuthContext";

// Integration (service-token) management. SUPER_ADMIN only, like the rest of
// /api/v1/admin - these keys read employee data without a human login, so
// they sit behind the same gate as database restore, not HR_ADMIN's.
//
// A key's secret is shown exactly once, at creation or rotation: the backend
// stores only its SHA-256 hash, so a lost key is rotated, never recovered.

function toDateInput(value) {
  if (!value) return "";
  const d = new Date(value);
  return Number.isNaN(d.getTime()) ? "" : d.toISOString().slice(0, 10);
}

// A date input gives a bare YYYY-MM-DD; send end-of-day so a key chosen to
// expire "on the 31st" still works through the 31st.
function toExpiryIso(dateStr) {
  return dateStr ? `${dateStr}T23:59:59` : null;
}

export default function IntegrationKeys() {
  const { user: me } = useAuth();
  const isSuperAdmin = me?.role === "SUPER_ADMIN";
  const [tokens, setTokens] = useState([]);
  const [scopes, setScopes] = useState([]);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [form, setForm] = useState({ name: "", scopes: [], expires_on: "" });
  const [issued, setIssued] = useState(null);   // { name, token } - shown once
  const [editing, setEditing] = useState(null);
  const [rotating, setRotating] = useState(null);

  function reload() {
    setLoading(true);
    Promise.all([
      client.get("/admin/service-tokens"),
      client.get("/admin/service-token-scopes"),
    ])
      .then(([t, s]) => { setTokens(t.data); setScopes(s.data); setError(""); })
      .catch((err) => setError(apiErrorMessage(err)))
      .finally(() => setLoading(false));
  }
  useEffect(() => { if (isSuperAdmin) reload(); else setLoading(false); }, [isSuperAdmin]);

  async function createKey() {
    setError("");
    try {
      const res = await client.post("/admin/service-tokens", {
        name: form.name.trim(),
        scopes: form.scopes,
        expires_at: toExpiryIso(form.expires_on),
      });
      setIssued({ name: res.data.name, token: res.data.token });
      setForm({ name: "", scopes: [], expires_on: "" });
      reload();
    } catch (err) {
      setError(apiErrorMessage(err));
    }
  }

  async function setActive(row, active) {
    setError("");
    try {
      await client.post(`/admin/service-tokens/${row.id}/${active ? "activate" : "deactivate"}`);
      reload();
    } catch (err) {
      setError(apiErrorMessage(err));
    }
  }

  function toggleFormScope(code) {
    setForm((f) => ({
      ...f,
      scopes: f.scopes.includes(code) ? f.scopes.filter((c) => c !== code) : [...f.scopes, code],
    }));
  }

  if (!isSuperAdmin) {
    return (
      <Card>
        <p className="text-sm text-ink/60">
          Integration keys are managed by the Super Admin only — they grant access to employee
          data without a human login.
        </p>
      </Card>
    );
  }

  const columns = [
    { key: "name", header: "App / Integration", render: (t) => <span className="font-medium text-ink">{t.name}</span> },
    {
      key: "scopes", header: "Access", render: (t) => (
        <div className="flex flex-wrap gap-1">
          {t.scopes.map((code) => (
            <span key={code} className="text-[11px] px-1.5 py-0.5 rounded bg-ink/5 text-ink/60 border border-ink/10">
              {scopes.find((s) => s.code === code)?.label || code}
            </span>
          ))}
        </div>
      ),
    },
    { key: "status", header: "Status", render: (t) => <StatusBadge status={t.status} /> },
    {
      key: "expires_at", header: "Expires", render: (t) =>
        t.expires_at
          ? <span className={t.is_expired ? "text-danger" : ""}>{formatDateTime(t.expires_at)}</span>
          : <span className="text-ink/40">Never</span>,
    },
    { key: "last_used_at", header: "Last Used", render: (t) => t.last_used_at ? formatDateTime(t.last_used_at) : <span className="text-ink/40">Never</span> },
    { key: "created_at", header: "Created", render: (t) => formatDateTime(t.created_at) },
    {
      key: "_actions", header: "", align: "right", render: (t) => (
        <div className="flex items-center gap-1 justify-end">
          <button
            type="button" title="Edit name, access or expiry"
            className="p-1.5 rounded hover:bg-ink/5 text-ink/50 hover:text-ink"
            onClick={() => setEditing(t)}
          >
            <Pencil size={14} />
          </button>
          <button
            type="button" title="Renew — issue a new secret for this same key"
            className="p-1.5 rounded hover:bg-ink/5 text-ink/50 hover:text-ink"
            onClick={() => setRotating(t)}
          >
            <RefreshCw size={14} />
          </button>
          <button
            type="button" title={t.revoked_at ? "Reactivate" : "Deactivate"}
            className="p-1.5 rounded hover:bg-ink/5 text-ink/50 hover:text-ink"
            onClick={() => setActive(t, !!t.revoked_at)}
          >
            {t.revoked_at ? <ShieldCheck size={14} /> : <ShieldOff size={14} />}
          </button>
        </div>
      ),
    },
  ];

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-xl font-display font-semibold text-ink">Integration Keys</h1>
        <p className="text-sm text-ink/50 mt-1">
          API keys for other Sunlease apps that read HRMS data on a schedule. Each key is a machine
          credential — it never logs in, carries no role, and reaches only the endpoints its access
          grant names.
        </p>
      </div>
      {error && <div className="text-sm text-danger bg-danger/10 rounded-md px-3 py-2">{error}</div>}

      <Card>
        <h2 className="text-sm font-semibold text-ink mb-3">New Key</h2>
        <div className="grid grid-cols-2 gap-3">
          <Input
            label="App / Integration Name" placeholder="e.g. depot-app" value={form.name}
            onChange={(e) => setForm({ ...form, name: e.target.value })} noUppercase
          />
          <Input
            label="Expires On (optional)" type="date" value={form.expires_on}
            onChange={(e) => setForm({ ...form, expires_on: e.target.value })}
          />
        </div>
        <div className="mt-3">
          <div className="text-xs font-medium text-ink/60 mb-1.5">Access</div>
          <div className="space-y-2">
            {scopes.map((s) => (
              <label key={s.code} className="flex items-start gap-2 text-sm">
                <input
                  type="checkbox" className="mt-0.5"
                  checked={form.scopes.includes(s.code)} onChange={() => toggleFormScope(s.code)}
                />
                <span>
                  <span className="text-ink">{s.label}</span>
                  <span className="block text-xs text-ink/50">{s.description}</span>
                </span>
              </label>
            ))}
          </div>
        </div>
        <Button className="mt-4" onClick={createKey} disabled={!form.name.trim() || form.scopes.length === 0}>
          Generate Key
        </Button>
        <p className="text-xs text-ink/50 mt-2">
          The key is shown once, immediately after it is generated — it is stored only as a hash and
          cannot be displayed again.
        </p>
      </Card>

      <Card>
        <h2 className="text-sm font-semibold text-ink mb-3">All Keys</h2>
        <Table columns={columns} rows={tokens} empty={loading ? "Loading…" : "No integration keys yet."} />
      </Card>

      <Card>
        <h2 className="text-sm font-semibold text-ink mb-1">How a key is used</h2>
        <p className="text-xs text-ink/60">
          The consuming app sends the key as a bearer token:
        </p>
        <pre className="mt-2 text-[11px] bg-ink/5 rounded p-2.5 overflow-x-auto text-ink/70">
{`curl -H "Authorization: Bearer <key>" \\
  https://hrms.sunlease.in/api/v1/integrations/employees`}
        </pre>
      </Card>

      {issued && <IssuedKeyModal name={issued.name} token={issued.token} onClose={() => setIssued(null)} />}
      {editing && (
        <EditKeyModal
          row={editing} scopes={scopes} onClose={() => setEditing(null)}
          onSaved={() => { setEditing(null); reload(); }}
        />
      )}
      {rotating && (
        <RotateKeyModal
          row={rotating} onClose={() => setRotating(null)}
          onRotated={(name, token) => { setRotating(null); setIssued({ name, token }); reload(); }}
        />
      )}
    </div>
  );
}

function IssuedKeyModal({ name, token, onClose }) {
  const [copied, setCopied] = useState(false);

  async function copy() {
    try {
      await navigator.clipboard.writeText(token);
      setCopied(true);
    } catch {
      setCopied(false);
    }
  }

  return (
    <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50">
      <div className="bg-white rounded-lg p-5 w-full max-w-lg">
        <h3 className="text-sm font-semibold text-ink mb-2">Key for {name}</h3>
        <p className="text-sm text-ink/60 mb-3">
          Copy this now and store it in the consuming app's configuration. It is not stored in
          HRMS in this form and cannot be shown again — if it is lost, renew the key to issue a
          new one.
        </p>
        <div className="flex items-stretch gap-2">
          <code className="flex-1 text-[11px] bg-ink/5 rounded p-2.5 break-all text-ink/80">{token}</code>
          <Button variant="outline" onClick={copy} className="gap-1.5 shrink-0">
            {copied ? <Check size={14} /> : <Copy size={14} />} {copied ? "Copied" : "Copy"}
          </Button>
        </div>
        <div className="flex justify-end mt-4">
          <Button onClick={onClose}>Done</Button>
        </div>
      </div>
    </div>
  );
}

function EditKeyModal({ row, scopes, onClose, onSaved }) {
  const [name, setName] = useState(row.name);
  const [selected, setSelected] = useState(row.scopes);
  const [expiresOn, setExpiresOn] = useState(toDateInput(row.expires_at));
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  function toggle(code) {
    setSelected((sel) => (sel.includes(code) ? sel.filter((c) => c !== code) : [...sel, code]));
  }

  function extend(days) {
    const base = expiresOn ? new Date(`${expiresOn}T00:00:00`) : new Date();
    const from = base > new Date() ? base : new Date();
    from.setDate(from.getDate() + days);
    setExpiresOn(from.toISOString().slice(0, 10));
  }

  async function save() {
    setBusy(true);
    setError("");
    try {
      await client.put(`/admin/service-tokens/${row.id}`, {
        name: name.trim(),
        scopes: selected,
        expires_at: toExpiryIso(expiresOn),
        never_expires: !expiresOn,
      });
      onSaved();
    } catch (err) {
      setError(apiErrorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="fixed inset-0 bg-black/30 flex items-center justify-center z-50" onClick={busy ? undefined : onClose}>
      <div className="bg-white rounded-lg p-5 w-full max-w-md" onClick={(e) => e.stopPropagation()}>
        <h3 className="text-sm font-semibold text-ink mb-3">Edit Key — {row.name}</h3>
        {error && <div className="text-sm text-danger bg-danger/10 rounded-md px-3 py-2 mb-3">{error}</div>}
        <div className="space-y-3">
          <Input label="App / Integration Name" value={name} onChange={(e) => setName(e.target.value)} noUppercase />
          <div>
            <Input label="Expires On" type="date" value={expiresOn} onChange={(e) => setExpiresOn(e.target.value)} />
            <div className="flex items-center gap-2 mt-1.5">
              <span className="text-xs text-ink/50 inline-flex items-center gap-1"><CalendarClock size={12} /> Renew:</span>
              {[90, 180, 365].map((d) => (
                <button
                  key={d} type="button" onClick={() => extend(d)}
                  className="text-xs px-1.5 py-0.5 rounded border border-ink/15 text-ink/60 hover:bg-ink/5"
                >
                  +{d}d
                </button>
              ))}
              <button
                type="button" onClick={() => setExpiresOn("")}
                className="text-xs px-1.5 py-0.5 rounded border border-ink/15 text-ink/60 hover:bg-ink/5"
              >
                Never
              </button>
            </div>
          </div>
          <div>
            <div className="text-xs font-medium text-ink/60 mb-1.5">Access</div>
            {scopes.map((s) => (
              <label key={s.code} className="flex items-center gap-2 text-sm">
                <input type="checkbox" checked={selected.includes(s.code)} onChange={() => toggle(s.code)} />
                {s.label}
              </label>
            ))}
          </div>
        </div>
        <div className="flex justify-end gap-2 mt-4">
          <Button variant="outline" onClick={onClose} disabled={busy}>Cancel</Button>
          <Button onClick={save} disabled={busy || !name.trim() || selected.length === 0}>
            {busy ? "Saving…" : "Save"}
          </Button>
        </div>
      </div>
    </div>
  );
}

function RotateKeyModal({ row, onClose, onRotated }) {
  const [expiresOn, setExpiresOn] = useState(toDateInput(row.expires_at));
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function rotate() {
    setBusy(true);
    setError("");
    try {
      const res = await client.post(`/admin/service-tokens/${row.id}/rotate`, {
        expires_at: toExpiryIso(expiresOn),
        never_expires: !expiresOn,
      });
      onRotated(res.data.name, res.data.token);
    } catch (err) {
      setError(apiErrorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50" onClick={busy ? undefined : onClose}>
      <div className="bg-white rounded-lg p-5 w-full max-w-md" onClick={(e) => e.stopPropagation()}>
        <h3 className="text-sm font-semibold text-ink mb-2">Renew Key — {row.name}</h3>
        <p className="text-sm text-ink/60 mb-3">
          This issues a new secret for this same key and stops the current one working
          <strong> immediately</strong>. {row.name} will fail every call until its configuration is
          updated with the new key. The key's name, access and usage history are kept, and a
          deactivated key is put back in service.
        </p>
        {error && <div className="text-sm text-danger bg-danger/10 rounded-md px-3 py-2 mb-3">{error}</div>}
        <Input label="New Expiry (blank = never)" type="date" value={expiresOn} onChange={(e) => setExpiresOn(e.target.value)} />
        <div className="flex justify-end gap-2 mt-4">
          <Button variant="outline" onClick={onClose} disabled={busy}>Cancel</Button>
          <Button onClick={rotate} disabled={busy}>{busy ? "Renewing…" : "Renew & Show New Key"}</Button>
        </div>
      </div>
    </div>
  );
}
