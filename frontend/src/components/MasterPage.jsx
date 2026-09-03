import { useEffect, useState } from "react";
import client, { apiErrorMessage } from "../api/client";
import { Card, Button, Input, Select, Table } from "./ui";

// Generic CRUD screen for a simple master entity (Company, Cost Center,
// Department, Project, Employee Category - blueprint §2/§13). Each `field`
// is either {name, label, type: "text"} or a foreign-key dropdown
// {name, label, type: "select", optionsResource, optionLabel}. "Delete"
// deactivates (is_active=false) rather than removing the row - masters
// are never physically deleted (blueprint §21).
export default function MasterPage({ title, description, resource, fields, idField = "id" }) {
  const [rows, setRows] = useState([]);
  const [optionsMap, setOptionsMap] = useState({});
  const [form, setForm] = useState({});
  const [editingId, setEditingId] = useState(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);

  const selectFields = fields.filter((f) => f.type === "select");

  function emptyForm() {
    const f = {};
    fields.forEach((field) => { f[field.name] = ""; });
    return f;
  }

  function reload() {
    setLoading(true);
    client.get(resource).then((res) => setRows(res.data)).finally(() => setLoading(false));
  }

  useEffect(() => {
    setForm(emptyForm());
    setEditingId(null);
    reload();
    selectFields.forEach((field) => {
      client.get(field.optionsResource).then((res) => {
        setOptionsMap((prev) => ({ ...prev, [field.name]: res.data }));
      });
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [resource]);

  function optionLabelFor(field, id) {
    const opts = optionsMap[field.name] || [];
    const found = opts.find((o) => o.id === id);
    return found ? found[field.optionLabel] : "—";
  }

  async function submit() {
    setError("");
    const payload = {};
    fields.forEach((f) => {
      payload[f.name] = f.type === "select" ? (form[f.name] ? Number(form[f.name]) : null) : form[f.name];
    });
    try {
      if (editingId) {
        await client.put(`${resource}/${editingId}`, payload);
      } else {
        await client.post(resource, payload);
      }
      setForm(emptyForm());
      setEditingId(null);
      reload();
    } catch (err) {
      setError(apiErrorMessage(err));
    }
  }

  function startEdit(row) {
    const f = {};
    fields.forEach((field) => { f[field.name] = row[field.name] ?? ""; });
    setForm(f);
    setEditingId(row[idField]);
    setError("");
  }

  function cancelEdit() {
    setForm(emptyForm());
    setEditingId(null);
    setError("");
  }

  async function deactivate(row) {
    if (!window.confirm(`Deactivate "${row.name || row.code}"? It will no longer be selectable, but existing records referencing it are unaffected.`)) return;
    try {
      await client.delete(`${resource}/${row[idField]}`);
      if (editingId === row[idField]) cancelEdit();
      reload();
    } catch (err) {
      setError(apiErrorMessage(err));
    }
  }

  const columns = [
    ...fields.map((f) => ({
      key: f.name,
      header: f.label,
      render: (row) => (f.type === "select" ? optionLabelFor(f, row[f.name]) : (row[f.name] || "—")),
    })),
    {
      key: "_actions",
      header: "",
      align: "right",
      render: (row) => (
        <div className="flex gap-2 justify-end">
          <Button variant="outline" size="sm" onClick={() => startEdit(row)}>Edit</Button>
          <Button variant="danger" size="sm" onClick={() => deactivate(row)}>Deactivate</Button>
        </div>
      ),
    },
  ];

  const canSubmit = fields.every((f) => !f.required || form[f.name]);

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-xl font-display font-semibold text-ink">{title}</h1>
        {description && <p className="text-sm text-ink/50 mt-1">{description}</p>}
      </div>
      {error && <div className="text-sm text-danger bg-danger/10 rounded-md px-3 py-2">{error}</div>}

      <Card>
        <h2 className="text-sm font-semibold text-ink mb-3">{editingId ? "Edit" : "New"}</h2>
        <div className="grid gap-2" style={{ gridTemplateColumns: `repeat(${fields.length}, minmax(0,1fr))` }}>
          {fields.map((field) =>
            field.type === "select" ? (
              <Select key={field.name} value={form[field.name] ?? ""} onChange={(e) => setForm({ ...form, [field.name]: e.target.value })}>
                <option value="">{field.label}...</option>
                {(optionsMap[field.name] || []).map((o) => <option key={o.id} value={o.id}>{o[field.optionLabel]}</option>)}
              </Select>
            ) : (
              <Input key={field.name} placeholder={field.label} value={form[field.name] ?? ""} onChange={(e) => setForm({ ...form, [field.name]: e.target.value })} />
            )
          )}
        </div>
        <div className="flex gap-2 mt-3">
          <Button onClick={submit} disabled={!canSubmit}>{editingId ? "Save Changes" : "Add"}</Button>
          {editingId && <Button variant="outline" onClick={cancelEdit}>Cancel</Button>}
        </div>
      </Card>

      <Card>
        {loading ? <div className="text-sm text-ink/40 py-10 text-center">Loading…</div> : <Table columns={columns} rows={rows} keyField={idField} />}
      </Card>
    </div>
  );
}
