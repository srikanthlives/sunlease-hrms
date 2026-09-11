import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { Upload, Download, Save } from "lucide-react";
import client, { apiErrorMessage } from "../api/client";
import { Card, Button } from "../components/ui";
import { useGlobalFilter } from "../context/GlobalFilterContext";

const STATUS_OPTIONS = ["PRESENT", "ABSENT", "HALF_DAY", "ON_LEAVE", "WEEKLY_OFF", "HOLIDAY"];

const STATUS_ABBR = {
  PRESENT: "P", ABSENT: "A", HALF_DAY: "HD", ON_LEAVE: "L", WEEKLY_OFF: "WO", HOLIDAY: "H",
};

function daysInMonth(year, month) {
  return new Date(year, month, 0).getDate();
}

export default function AttendanceGrid() {
  const { year, month, costCenterId } = useGlobalFilter();
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [editingKey, setEditingKey] = useState(null);
  const [dirty, setDirty] = useState({}); // key -> {episode_id, date, status, check_in, check_out}
  const [saving, setSaving] = useState(false);
  const [saveResult, setSaveResult] = useState(null);

  const [bulkOpen, setBulkOpen] = useState(false);
  const [bulkFile, setBulkFile] = useState(null);
  const [bulkUploading, setBulkUploading] = useState(false);
  const [bulkResult, setBulkResult] = useState(null);
  const [bulkError, setBulkError] = useState("");

  function reload() {
    setLoading(true);
    setError("");
    const params = { year, month };
    if (costCenterId) params.cost_center_id = costCenterId;
    client
      .get("/attendance/records", { params })
      .then((res) => setRows(res.data))
      .catch((err) => setError(apiErrorMessage(err)))
      .finally(() => setLoading(false));
  }

  useEffect(reload, [year, month, costCenterId]);

  const numDays = daysInMonth(year, month);
  const dayNumbers = useMemo(() => Array.from({ length: numDays }, (_, i) => i + 1), [numDays]);

  function cellKey(episodeId, dateStr) {
    return `${episodeId}-${dateStr}`;
  }

  function cellValue(row, dayRecord) {
    const key = cellKey(row.episode_id, dayRecord.date);
    if (dirty[key]) return dirty[key];
    return {
      episode_id: row.episode_id,
      date: dayRecord.date,
      status: dayRecord.status || "",
      check_in: dayRecord.check_in ? dayRecord.check_in.slice(11, 16) : "",
      check_out: dayRecord.check_out ? dayRecord.check_out.slice(11, 16) : "",
    };
  }

  function updateCell(key, patch) {
    setDirty((prev) => ({ ...prev, [key]: { ...prev[key], ...patch } }));
  }

  function startEdit(row, dayRecord) {
    const key = cellKey(row.episode_id, dayRecord.date);
    if (!dirty[key]) {
      setDirty((prev) => ({ ...prev, [key]: cellValue(row, dayRecord) }));
    }
    setEditingKey(key);
  }

  const dirtyCount = Object.keys(dirty).length;

  async function saveAll() {
    setSaving(true);
    setSaveResult(null);
    try {
      const items = Object.values(dirty).map((c) => ({
        episode_id: c.episode_id,
        date: c.date,
        status: c.status || "PRESENT",
        check_in: c.check_in ? `${c.date}T${c.check_in}:00` : null,
        check_out: c.check_out ? `${c.date}T${c.check_out}:00` : null,
      }));
      const res = await client.post("/attendance/records/bulk", { items });
      setSaveResult(res.data);
      setDirty({});
      setEditingKey(null);
      reload();
    } catch (err) {
      setSaveResult({ updated: 0, errors: [{ message: apiErrorMessage(err) }] });
    } finally {
      setSaving(false);
    }
  }

  async function downloadTemplate() {
    const params = { year, month };
    if (costCenterId) params.cost_center_id = costCenterId;
    const res = await client.get("/attendance/bulk-upload-template", { params, responseType: "blob" });
    const url = URL.createObjectURL(res.data);
    const a = document.createElement("a");
    a.href = url;
    a.download = "hrms_attendance_bulk_upload_template.xlsx";
    a.click();
    URL.revokeObjectURL(url);
  }

  async function uploadBulkFile() {
    if (!bulkFile) return;
    setBulkUploading(true);
    setBulkError("");
    setBulkResult(null);
    try {
      const form = new FormData();
      form.append("file", bulkFile);
      const res = await client.post("/attendance/bulk-upload", form);
      setBulkResult(res.data);
      setBulkFile(null);
      reload();
    } catch (err) {
      setBulkError(apiErrorMessage(err));
    } finally {
      setBulkUploading(false);
    }
  }

  function closeBulkModal() {
    setBulkOpen(false);
    setBulkFile(null);
    setBulkResult(null);
    setBulkError("");
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-display font-semibold text-ink">Attendance Grid</h1>
          <p className="text-sm text-ink/50 mt-1">Cost-center-wide monthly attendance — enter and view in one screen.</p>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" onClick={() => setBulkOpen(true)} className="gap-1.5">
            <Upload size={14} /> Bulk Upload
          </Button>
          <Button onClick={saveAll} disabled={dirtyCount === 0 || saving} className="gap-1.5">
            <Save size={14} /> {saving ? "Saving…" : `Save${dirtyCount ? ` (${dirtyCount})` : ""}`}
          </Button>
        </div>
      </div>

      {error && <div className="text-sm text-danger bg-danger/10 rounded-md px-3 py-2">{error}</div>}
      {saveResult && (
        <div className="text-sm">
          <div className="text-ok font-medium">{saveResult.updated} record(s) saved.</div>
          {saveResult.errors?.length > 0 && (
            <div className="border border-danger/20 bg-danger/5 rounded-md p-2 mt-1 max-h-32 overflow-y-auto">
              {saveResult.errors.map((e, i) => (
                <div key={i} className="text-xs text-ink/60">
                  Episode {e.episode_id} on {e.date}: {e.message}
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      <Card>
        {loading ? (
          <div className="text-sm text-ink/40 py-10 text-center">Loading…</div>
        ) : rows.length === 0 ? (
          <div className="text-sm text-ink/40 py-10 text-center">No employees active in this Cost Center / month.</div>
        ) : (
          <div className="overflow-x-auto">
            <table className="text-xs border-collapse w-full">
              <thead>
                <tr>
                  <th className="sticky left-0 bg-white z-10 text-left px-2 py-1.5 border-b border-ink/10 font-medium text-ink/60 min-w-[180px]">
                    Employee
                  </th>
                  {dayNumbers.map((d) => (
                    <th key={d} className="px-1 py-1.5 border-b border-ink/10 font-medium text-ink/60 text-center min-w-[54px]">
                      {d}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {rows.map((row) => (
                  <tr key={row.episode_id} className="hover:bg-ink/[0.02]">
                    <td className="sticky left-0 bg-white z-10 px-2 py-1 border-b border-ink/5 whitespace-nowrap">
                      <Link to={`/attendance?episode_id=${row.episode_id}`} className="text-brand-700 hover:underline">
                        {row.employee_number} — {row.first_name} {row.last_name}
                      </Link>
                    </td>
                    {row.records.map((dayRecord) => {
                      const key = cellKey(row.episode_id, dayRecord.date);
                      const isEditing = editingKey === key;
                      const value = cellValue(row, dayRecord);
                      const isDirty = !!dirty[key];
                      return (
                        <td key={key} className="border-b border-ink/5 text-center align-top p-0.5">
                          {isEditing ? (
                            <div className="flex flex-col gap-0.5 bg-brand-50 border border-brand-200 rounded p-1 min-w-[110px]">
                              <select
                                autoFocus
                                className="text-[11px] border border-ink/10 rounded px-1 py-0.5"
                                value={value.status}
                                onChange={(e) => updateCell(key, { status: e.target.value })}
                                onBlur={() => setEditingKey(null)}
                              >
                                <option value="">—</option>
                                {STATUS_OPTIONS.map((s) => (
                                  <option key={s} value={s}>{STATUS_ABBR[s]}</option>
                                ))}
                              </select>
                              {(value.status === "PRESENT" || value.status === "HALF_DAY") && (
                                <>
                                  <input
                                    type="time"
                                    className="text-[11px] border border-ink/10 rounded px-1 py-0.5"
                                    value={value.check_in}
                                    onChange={(e) => updateCell(key, { check_in: e.target.value })}
                                  />
                                  <input
                                    type="time"
                                    className="text-[11px] border border-ink/10 rounded px-1 py-0.5"
                                    value={value.check_out}
                                    onChange={(e) => updateCell(key, { check_out: e.target.value })}
                                  />
                                </>
                              )}
                            </div>
                          ) : (
                            <button
                              onClick={() => startEdit(row, dayRecord)}
                              className={`w-full py-1.5 rounded text-[11px] font-medium ${
                                isDirty ? "bg-brand-100 text-brand-700" : value.status ? "text-ink/70 hover:bg-ink/5" : "text-ink/25 hover:bg-ink/5"
                              }`}
                              title={dayRecord.date}
                            >
                              {STATUS_ABBR[value.status] || "·"}
                            </button>
                          )}
                        </td>
                      );
                    })}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      {bulkOpen && (
        <div className="fixed inset-0 bg-black/30 flex items-center justify-center z-50" onClick={closeBulkModal}>
          <div className="bg-white rounded-lg p-5 w-full max-w-lg" onClick={(e) => e.stopPropagation()}>
            <h3 className="text-sm font-semibold text-ink mb-1">Bulk Upload Attendance</h3>
            <p className="text-xs text-ink/50 mb-4">
              The downloaded template is pre-scoped to the current Cost Center and Month (one row per employee per
              day). Each row upserts through the same logic as marking attendance manually, so late/early/overtime
              stay consistent.
            </p>

            <Button variant="outline" size="sm" onClick={downloadTemplate} className="gap-1.5 mb-4">
              <Download size={14} /> Download Template (.xlsx)
            </Button>

            {bulkError && <div className="text-sm text-danger bg-danger/10 rounded-md px-3 py-2 mb-3">{bulkError}</div>}

            {bulkResult && (
              <div className="mb-4 text-sm">
                <div className="text-ok font-medium mb-1">
                  {bulkResult.created} created, {bulkResult.updated} updated.
                </div>
                {bulkResult.errors.length > 0 && (
                  <div className="border border-danger/20 bg-danger/5 rounded-md p-2 max-h-40 overflow-y-auto">
                    <div className="text-xs font-medium text-danger mb-1">{bulkResult.errors.length} row(s) skipped:</div>
                    {bulkResult.errors.map((e, i) => (
                      <div key={i} className="text-xs text-ink/60">Row {e.row}: {e.message}</div>
                    ))}
                  </div>
                )}
              </div>
            )}

            <div className="flex items-center gap-2">
              <input
                type="file"
                accept=".xlsx"
                onChange={(e) => { setBulkFile(e.target.files[0]); setBulkResult(null); setBulkError(""); }}
                className="text-xs flex-1"
              />
              <Button size="sm" onClick={uploadBulkFile} disabled={!bulkFile || bulkUploading}>
                {bulkUploading ? "Uploading…" : "Upload"}
              </Button>
            </div>

            <div className="flex justify-end mt-4">
              <Button variant="outline" onClick={closeBulkModal}>Close</Button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
