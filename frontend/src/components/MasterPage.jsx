import { useEffect, useState } from "react";
import client, { apiErrorMessage } from "../api/client";
import { Card, Button, Input, Select, Checkbox, Table, StatusBadge } from "./ui";

// Generic CRUD screen for a simple master entity (Company, Cost Center,
// Department, Project, Employee Category - blueprint §2/§13). Each `field`
// is one of:
//   {name, label, type: "text" | "number" | "time"}
//   {name, label, type: "select", optionsResource, optionLabel} - foreign-key dropdown
//   {name, label, type: "staticSelect", options: [{value,label}]} - fixed enum dropdown
//   {name, label, type: "checkbox"} - boolean
// "Delete" removes the row permanently if nothing references it yet;
// otherwise it falls back to deactivating (is_active=false) so records
// that already point at it keep working - see masters.py's
// _delete_or_deactivate (blueprint §21's "never delete" applies once a
// master row is actually in use).
export default function MasterPage({ title, description, resource, fields, idField = "id", allowDeactivate = true, allowEdit = true }) {
  const [rows, setRows] = useState([]);
  const [optionsMap, setOptionsMap] = useState({});
  const [form, setForm] = useState({});
  const [editingId, setEditingId] = useState(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);

  const selectFields = fields.filter((f) => f.type === "select");

  function emptyForm() {
    const f = {};
    fields.forEach((field) => { f[field.name] = field.type === "checkbox" ? !!field.default : (field.default ?? ""); });
    return f;
  }

  function reload() {
    setLoading(true);
    client.get(resource, { params: { include_inactive: true } }).then((res) => setRows(res.data)).finally(() => setLoading(false));
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
      if (f.type === "select") payload[f.name] = form[f.name] ? Number(form[f.name]) : null;
      else if (f.type === "checkbox") payload[f.name] = !!form[f.name];
      else if (f.type === "number") payload[f.name] = form[f.name] === "" ? null : Number(form[f.name]);
      else payload[f.name] = form[f.name];
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
    fields.forEach((field) => {
      f[field.name] = field.type === "checkbox" ? !!row[field.name] : (row[field.name] ?? "");
    });
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
    const label = row.name || row.code;
    if (!window.confirm(`Delete "${label}"? If it's not referenced anywhere it will be removed permanently; otherwise it will be deactivated instead.`)) return;
    try {
      const res = await client.delete(`${resource}/${row[idField]}`);
      if (editingId === row[idField]) cancelEdit();
      reload();
      if (res.data && res.data.deleted === false) {
        window.alert(`"${label}" is still in use, so it was deactivated instead of deleted. It will no longer be selectable, but existing records referencing it are unaffected.`);
      }
    } catch (err) {
      setError(apiErrorMessage(err));
    }
  }

  async function activate(row) {
    try {
      await client.post(`${resource}/${row[idField]}/activate`);
      reload();
    } catch (err) {
      setError(apiErrorMessage(err));
    }
  }

  const columns = [
    ...fields.map((f) => ({
      key: f.name,
      header: f.label,
      render: (row) => {
        if (f.type === "select") return optionLabelFor(f, row[f.name]);
        if (f.type === "checkbox") return <StatusBadge status={row[f.name] ? "ACTIVE" : "INACTIVE"} />;
        if (f.type === "staticSelect") return (f.options.find((o) => o.value === row[f.name])?.label) || row[f.name] || "—";
        return row[f.name] || row[f.name] === 0 ? row[f.name] : "—";
      },
    })),
    ...(allowDeactivate && !fields.some((f) => f.name === "is_active") ? [{
      key: "is_active",
      header: "Status",
      render: (row) => <StatusBadge status={row.is_active ? "ACTIVE" : "INACTIVE"} />,
    }] : []),
    {
      key: "_actions",
      header: "",
      align: "right",
      render: (row) => (
        <div className="flex gap-2 justify-end">
          {allowEdit && <Button variant="outline" size="sm" onClick={() => startEdit(row)}>Edit</Button>}
          {allowDeactivate && (row.is_active === false
            ? <Button variant="outline" size="sm" onClick={() => activate(row)}>Activate</Button>
            : <Button variant="danger" size="sm" onClick={() => deactivate(row)}>Delete</Button>)}
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
          {fields.map((field) => {
            if (field.type === "select") {
              return (
                <Select key={field.name} value={form[field.name] ?? ""} onChange={(e) => setForm({ ...form, [field.name]: e.target.value })}>
                  <option value="">{field.label}...</option>
                  {(optionsMap[field.name] || []).map((o) => <option key={o.id} value={o.id}>{o[field.optionLabel]}</option>)}
                </Select>
              );
            }
            if (field.type === "staticSelect") {
              return (
                <Select key={field.name} value={form[field.name] ?? ""} onChange={(e) => setForm({ ...form, [field.name]: e.target.value })}>
                  <option value="">{field.label}...</option>
                  {field.options.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
                </Select>
              );
            }
            if (field.type === "checkbox") {
              return (
                <Checkbox
                  key={field.name}
                  label={field.label}
                  checked={!!form[field.name]}
                  onChange={(e) => setForm({ ...form, [field.name]: e.target.checked })}
                  className="self-center"
                />
              );
            }
            return (
              <Input
                key={field.name}
                type={field.type === "number" ? "number" : field.type === "time" ? "time" : field.type === "date" ? "date" : "text"}
                step={field.type === "number" ? "any" : undefined}
                placeholder={field.label}
                value={form[field.name] ?? ""}
                onChange={(e) => setForm({ ...form, [field.name]: e.target.value })}
              />
            );
          })}
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
