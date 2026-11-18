import { useEffect, useMemo, useState } from "react";
import { ArrowUp, ArrowDown, Check, Download, Save, Trash2, X } from "lucide-react";
import client, { apiErrorMessage } from "../api/client";
import { Button, Checkbox, Input, Select } from "./ui";

/**
 * Configurable Excel export, shared by the Employees and Candidates lists.
 *
 * Four steps: pick a saved pattern -> choose and order the columns (and the
 * sort) -> filter the rows -> preview and download. The preview and the
 * download post the SAME spec to the backend, which builds both from one
 * function (services/export_service.build_rows), so the preview is the
 * file's first page rather than a guess at it.
 *
 * A "pattern" is a layout only: columns, their order, and the sort. The
 * filters deliberately are not saved with it - which rows to export is a
 * decision for download time, and baking last month's filter into a saved
 * layout is how someone quietly exports the wrong rows.
 *
 * Props:
 *   entity        "EMPLOYEE" | "CANDIDATE"
 *   initialFilters  the list page's current filter state, as {key: value}
 *                   using the same keys the backend's FILTER_KEYS expects
 *   filterFields  [{ key, label, options? }] - how to render each filter;
 *                 options given => a dropdown, otherwise a text box
 *   onClose
 */
const STEPS = ["Pattern", "Columns & Order", "Filters", "Preview"];

export default function ExportWizard({ entity, initialFilters = {}, filterFields = [], onClose }) {
  const [step, setStep] = useState(0);
  const [catalog, setCatalog] = useState(null);       // { columns, default_columns, preview_rows }
  const [selected, setSelected] = useState([]);       // ordered column keys - the file's column order
  const [sortBy, setSortBy] = useState("");
  const [sortDir, setSortDir] = useState("asc");
  // Pre-filled from what the operator is already looking at on the list, so
  // "download what I'm seeing" needs no re-typing - still editable here.
  const [filters, setFilters] = useState(initialFilters);
  const [templates, setTemplates] = useState([]);
  const [templateId, setTemplateId] = useState("");   // "" = not using a saved pattern
  const [saveAs, setSaveAs] = useState("");
  const [shareSaved, setShareSaved] = useState(false);
  const [preview, setPreview] = useState(null);       // { columns, rows, total, shown }
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  const label = entity === "EMPLOYEE" ? "Employees" : "Candidates";

  useEffect(() => {
    setError("");
    Promise.all([
      client.get("/exports/columns", { params: { entity } }),
      client.get("/exports/templates", { params: { entity } }),
    ])
      .then(([cols, tpl]) => {
        setCatalog(cols.data);
        setSelected(cols.data.default_columns.filter((k) => cols.data.columns.some((c) => c.key === k)));
        setTemplates(tpl.data);
      })
      .catch((err) => setError(apiErrorMessage(err)));
  }, [entity]);

  const byKey = useMemo(
    () => Object.fromEntries((catalog?.columns || []).map((c) => [c.key, c])),
    [catalog],
  );
  const groups = useMemo(() => {
    const out = [];
    for (const column of catalog?.columns || []) {
      const group = out.find((g) => g.name === column.group) || (out.push({ name: column.group, columns: [] }), out[out.length - 1]);
      group.columns.push(column);
    }
    return out;
  }, [catalog]);

  const spec = () => ({
    entity,
    columns: selected,
    sort_by: sortBy || null,
    sort_dir: sortDir,
    filters: Object.fromEntries(Object.entries(filters).filter(([, v]) => v !== "" && v != null)),
  });

  function toggleColumn(key) {
    setPreview(null);
    setSelected((prev) => {
      if (prev.includes(key)) {
        // Dropping the sort column would leave the file sorted by something
        // it doesn't contain, which the backend refuses - so clear it here.
        if (sortBy === key) setSortBy("");
        return prev.filter((k) => k !== key);
      }
      return [...prev, key];       // newly ticked columns land at the end, then get moved
    });
  }

  function move(key, delta) {
    setPreview(null);
    setSelected((prev) => {
      const from = prev.indexOf(key);
      const to = from + delta;
      if (from < 0 || to < 0 || to >= prev.length) return prev;
      const next = [...prev];
      next.splice(to, 0, next.splice(from, 1)[0]);
      return next;
    });
  }

  function applyTemplate(id) {
    setTemplateId(id);
    setPreview(null);
    setNotice("");
    if (!id) return;
    const template = templates.find((t) => String(t.id) === String(id));
    if (!template) return;
    // A saved pattern may name a column the current user can't export (a
    // sensitive one); those are dropped rather than failing the whole load.
    const usable = template.columns.filter((k) => byKey[k]);
    setSelected(usable);
    setSortBy(usable.includes(template.sort_by) ? template.sort_by : "");
    setSortDir(template.sort_dir || "asc");
    setSaveAs(template.owned ? template.name : "");
    setShareSaved(Boolean(template.is_shared) && template.owned);
    if (usable.length < template.columns.length) {
      setNotice(`${template.columns.length - usable.length} column(s) in this pattern are not available to you and were left out.`);
    }
  }

  async function loadPreview() {
    setBusy(true);
    setError("");
    try {
      const res = await client.post("/exports/preview", spec());
      setPreview(res.data);
      setStep(3);
    } catch (err) {
      setError(apiErrorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  async function download() {
    setBusy(true);
    setError("");
    try {
      const res = await client.post("/exports/download", spec(), { responseType: "blob" });
      const url = URL.createObjectURL(res.data);
      const a = document.createElement("a");
      a.href = url;
      a.download = `hrms_${entity.toLowerCase()}s_export.xlsx`;
      a.click();
      URL.revokeObjectURL(url);
      onClose();
    } catch (err) {
      setError(apiErrorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  async function savePattern() {
    setBusy(true);
    setError("");
    setNotice("");
    const body = { name: saveAs.trim(), entity, columns: selected, sort_by: sortBy || null, sort_dir: sortDir, is_shared: shareSaved };
    const existing = templates.find((t) => String(t.id) === String(templateId));
    try {
      // Editing a pattern you own updates it in place; otherwise this saves
      // a new one (so "load a shared pattern, tweak it, save as mine" works).
      const res = existing?.owned
        ? await client.put(`/exports/templates/${existing.id}`, body)
        : await client.post("/exports/templates", body);
      const list = await client.get("/exports/templates", { params: { entity } });
      setTemplates(list.data);
      setTemplateId(String(res.data.id));
      setNotice(`Pattern "${res.data.name}" saved.`);
    } catch (err) {
      setError(apiErrorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  async function deletePattern() {
    const existing = templates.find((t) => String(t.id) === String(templateId));
    if (!existing) return;
    if (!window.confirm(`Delete the export pattern "${existing.name}"? The data itself is untouched.`)) return;
    setBusy(true);
    setError("");
    try {
      await client.delete(`/exports/templates/${existing.id}`);
      const list = await client.get("/exports/templates", { params: { entity } });
      setTemplates(list.data);
      setTemplateId("");
      setSaveAs("");
      setNotice(`Pattern "${existing.name}" deleted.`);
    } catch (err) {
      setError(apiErrorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  const activeFilters = filterFields.filter((f) => filters[f.key] !== "" && filters[f.key] != null);
  const canAdvance = step !== 1 || selected.length > 0;

  return (
    <div className="fixed inset-0 bg-black/30 flex items-center justify-center z-50 p-4" onClick={() => !busy && onClose()}>
      <div className="bg-white rounded-lg w-full max-w-4xl max-h-[90vh] flex flex-col" onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center justify-between border-b border-ink/10 px-5 py-3">
          <div>
            <h3 className="text-sm font-semibold text-ink">Export {label} to Excel</h3>
            <p className="text-xs text-ink/50 mt-0.5">
              Choose the columns and their order, filter the rows, check the preview, then download.
            </p>
          </div>
          <button className="text-ink/40 hover:text-ink" onClick={onClose} title="Close"><X size={18} /></button>
        </div>

        <div className="flex items-center gap-1 px-5 py-2.5 border-b border-ink/10 text-xs">
          {STEPS.map((name, index) => (
            <button
              key={name}
              onClick={() => (index <= step || canAdvance) && setStep(index)}
              className={`rounded-full px-2.5 py-1 ${index === step ? "bg-brand-600 text-white font-semibold" : index < step ? "text-brand-600 hover:bg-brand-50" : "text-ink/35"}`}
            >
              {index + 1}. {name}
            </button>
          ))}
          <span className="ml-auto text-ink/40">
            {selected.length} column{selected.length === 1 ? "" : "s"}
            {activeFilters.length > 0 && ` · ${activeFilters.length} filter${activeFilters.length === 1 ? "" : "s"}`}
          </span>
        </div>

        <div className="flex-1 overflow-y-auto px-5 py-4">
          {!catalog && !error && <div className="text-sm text-ink/40 py-8 text-center">Loading…</div>}

          {catalog && step === 0 && (
            <div className="space-y-3">
              <p className="text-xs text-ink/50">
                A saved pattern is a layout — which columns, in which order, sorted how. Start from one, or
                go straight to the next step to build a fresh one.
              </p>
              <Select label="Saved pattern" value={templateId} onChange={(e) => applyTemplate(e.target.value)}>
                <option value="">Start fresh ({catalog.default_columns.length} default columns)</option>
                {templates.map((t) => (
                  <option key={t.id} value={t.id}>
                    {t.name}{t.is_shared ? " (shared)" : ""}{t.owned ? "" : " — someone else's"}
                  </option>
                ))}
              </Select>
              {templates.length === 0 && (
                <p className="text-xs text-ink/40">
                  No patterns saved yet. Configure the columns in the next step and you can save them here as
                  a pattern to reuse.
                </p>
              )}
            </div>
          )}

          {catalog && step === 1 && (
            <div className="grid grid-cols-2 gap-4">
              <div>
                <div className="text-xs font-semibold uppercase tracking-wide text-ink/40 mb-2">Available columns</div>
                <div className="space-y-3">
                  {groups.map((group) => (
                    <div key={group.name}>
                      <div className="text-[11px] font-semibold text-ink/50 mb-1">{group.name}</div>
                      <div className="space-y-0.5">
                        {group.columns.map((column) => (
                          <label key={column.key} className="flex items-center gap-2 text-xs text-ink/80 cursor-pointer hover:bg-ink/[0.02] rounded px-1 py-0.5">
                            <input
                              type="checkbox" className="rounded border-ink/30"
                              checked={selected.includes(column.key)} onChange={() => toggleColumn(column.key)}
                            />
                            {column.label}
                            {column.sensitive && (
                              <span className="text-[10px] uppercase tracking-wide text-accent-600" title="Sensitive — only exportable because you hold employee.sensitive.view">
                                sensitive
                              </span>
                            )}
                          </label>
                        ))}
                      </div>
                    </div>
                  ))}
                </div>
              </div>
              <div>
                <div className="text-xs font-semibold uppercase tracking-wide text-ink/40 mb-2">
                  Column order in the file
                </div>
                {selected.length === 0 ? (
                  <p className="text-xs text-ink/40">Tick at least one column on the left.</p>
                ) : (
                  <ol className="space-y-0.5">
                    {selected.map((key, index) => (
                      <li key={key} className="flex items-center gap-1.5 text-xs rounded border border-ink/10 px-2 py-1">
                        <span className="w-5 text-ink/35 tabular-nums">{index + 1}</span>
                        <span className="flex-1 truncate text-ink/80">{byKey[key]?.label || key}</span>
                        <button className="text-ink/30 hover:text-brand-600 disabled:opacity-20" disabled={index === 0}
                          onClick={() => move(key, -1)} title="Move up"><ArrowUp size={13} /></button>
                        <button className="text-ink/30 hover:text-brand-600 disabled:opacity-20" disabled={index === selected.length - 1}
                          onClick={() => move(key, 1)} title="Move down"><ArrowDown size={13} /></button>
                        <button className="text-ink/30 hover:text-danger" onClick={() => toggleColumn(key)} title="Remove">
                          <X size={13} />
                        </button>
                      </li>
                    ))}
                  </ol>
                )}

                <div className="mt-4 grid grid-cols-2 gap-2">
                  <Select label="Sort by" value={sortBy} onChange={(e) => { setSortBy(e.target.value); setPreview(null); }}>
                    <option value="">Default (newest first)</option>
                    {selected.map((key) => <option key={key} value={key}>{byKey[key]?.label || key}</option>)}
                  </Select>
                  <Select label="Direction" value={sortDir} disabled={!sortBy}
                    onChange={(e) => { setSortDir(e.target.value); setPreview(null); }}>
                    <option value="asc">A → Z / oldest first</option>
                    <option value="desc">Z → A / newest first</option>
                  </Select>
                </div>
                <p className="mt-1 text-[11px] text-ink/40">
                  Only an exported column can be the sort column, and blank values always go last.
                </p>

                <div className="mt-4 rounded-md border border-ink/10 p-2.5">
                  <div className="text-[11px] font-semibold text-ink/50 mb-1.5">Save this layout as a pattern</div>
                  <Input placeholder="e.g. Payroll handover" value={saveAs} onChange={(e) => setSaveAs(e.target.value)} />
                  <div className="mt-2 flex items-center justify-between gap-2">
                    <Checkbox label="Share with everyone" checked={shareSaved} onChange={(e) => setShareSaved(e.target.checked)} />
                    <span className="flex gap-1.5">
                      {templates.find((t) => String(t.id) === String(templateId))?.owned && (
                        <Button variant="ghost" size="sm" onClick={deletePattern} disabled={busy} className="gap-1 text-danger">
                          <Trash2 size={13} /> Delete
                        </Button>
                      )}
                      <Button variant="outline" size="sm" onClick={savePattern}
                        disabled={busy || !saveAs.trim() || selected.length === 0} className="gap-1">
                        <Save size={13} /> Save
                      </Button>
                    </span>
                  </div>
                  <p className="mt-1.5 text-[11px] text-ink/40">
                    Only the layout is saved — the filters on the next step are chosen each time you export.
                  </p>
                </div>
              </div>
            </div>
          )}

          {catalog && step === 2 && (
            <div className="space-y-3">
              <p className="text-xs text-ink/50">
                These start from the filters on the {label} list, so by default you export exactly what you
                were looking at. Clear one to widen the export.
              </p>
              <div className="grid grid-cols-3 gap-3">
                {filterFields.map((field) => (
                  field.options ? (
                    <Select key={field.key} label={field.label} value={filters[field.key] ?? ""}
                      onChange={(e) => { setFilters({ ...filters, [field.key]: e.target.value }); setPreview(null); }}>
                      <option value="">All</option>
                      {field.options.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
                    </Select>
                  ) : (
                    <Input key={field.key} label={field.label} value={filters[field.key] ?? ""}
                      onChange={(e) => { setFilters({ ...filters, [field.key]: e.target.value }); setPreview(null); }} />
                  )
                ))}
              </div>
              <Button variant="ghost" size="sm" className="gap-1"
                onClick={() => { setFilters({}); setPreview(null); }}>
                <X size={13} /> Clear all filters (export everything you can see)
              </Button>
            </div>
          )}

          {catalog && step === 3 && (
            <div>
              {!preview ? (
                <div className="text-sm text-ink/40 py-8 text-center">Building the preview…</div>
              ) : (
                <>
                  <div className="flex items-center gap-2 mb-2 text-xs">
                    <span className="font-semibold text-ink">
                      {preview.total} row{preview.total === 1 ? "" : "s"} will be exported
                    </span>
                    {preview.total > preview.shown && (
                      <span className="text-ink/50">showing the first {preview.shown}</span>
                    )}
                    {preview.total === 0 && (
                      <span className="text-danger">— nothing matches these filters; the file would have only a header row.</span>
                    )}
                  </div>
                  <div className="overflow-auto rounded-md border border-ink/10 max-h-[46vh]">
                    <table className="text-xs whitespace-nowrap">
                      <thead className="sticky top-0 bg-ink/[0.03] text-left text-ink/40 uppercase tracking-wide">
                        <tr>
                          {preview.columns.map((c) => <th key={c.key} className="px-2 py-1.5 font-semibold">{c.label}</th>)}
                        </tr>
                      </thead>
                      <tbody>
                        {preview.rows.map((row, index) => (
                          <tr key={index} className="border-t border-ink/5">
                            {row.map((value, cell) => (
                              <td key={cell} className="px-2 py-1 text-ink/80">
                                {value === true ? "Yes" : value === false ? "No" : value === null || value === "" ? <span className="text-ink/20">—</span> : String(value)}
                              </td>
                            ))}
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                  <p className="mt-2 text-[11px] text-ink/40">
                    This is the file's first page, not an approximation — the download is built from the same
                    columns, order, sort and filters shown here.
                  </p>
                </>
              )}
            </div>
          )}

          {notice && <div className="mt-3 text-xs text-ok bg-ok/10 rounded-md px-3 py-2 flex items-center gap-1.5"><Check size={13} /> {notice}</div>}
          {error && <div className="mt-3 text-sm text-danger bg-danger/10 rounded-md px-3 py-2">{error}</div>}
        </div>

        <div className="flex items-center gap-2 border-t border-ink/10 px-5 py-3">
          {step > 0 && <Button variant="outline" onClick={() => setStep(step - 1)} disabled={busy}>Back</Button>}
          <span className="ml-auto flex gap-2">
            <Button variant="ghost" onClick={onClose} disabled={busy}>Cancel</Button>
            {step < 2 && (
              <Button onClick={() => setStep(step + 1)} disabled={busy || !canAdvance || !catalog}>Next</Button>
            )}
            {step === 2 && (
              <Button onClick={loadPreview} disabled={busy || selected.length === 0}>
                {busy ? "Building…" : "Preview"}
              </Button>
            )}
            {step === 3 && (
              <Button onClick={download} disabled={busy || !preview} className="gap-1.5">
                <Download size={14} /> {busy ? "Preparing…" : "Download .xlsx"}
              </Button>
            )}
          </span>
        </div>
      </div>
    </div>
  );
}
