import { useEffect, useMemo, useState } from "react";
import client, { apiErrorMessage } from "../api/client";
import { Card, Button, Input, Select, Checkbox, Table, formatDate } from "../components/ui";

const WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"];

function todayIso() {
  return new Date().toISOString().slice(0, 10);
}
function monthAheadIso() {
  const d = new Date();
  d.setDate(d.getDate() + 30);
  return d.toISOString().slice(0, 10);
}

export default function Roster() {
  const [employees, setEmployees] = useState([]);
  const [shifts, setShifts] = useState([]);
  const [episodeId, setEpisodeId] = useState("");
  const [startDate, setStartDate] = useState(todayIso());
  const [endDate, setEndDate] = useState(monthAheadIso());
  const [entries, setEntries] = useState([]);
  const [error, setError] = useState("");
  const [generating, setGenerating] = useState(false);
  const [savingPattern, setSavingPattern] = useState(false);
  const [rowBusyDate, setRowBusyDate] = useState(null);
  const [weekdays, setWeekdays] = useState([]);
  const [patternEffectiveFrom, setPatternEffectiveFrom] = useState(todayIso());
  const [patternWeekday, setPatternWeekday] = useState("6");

  useEffect(() => {
    client.get("/employees").then((res) => setEmployees(res.data));
    client.get("/attendance/shifts").then((res) => setShifts(res.data));
  }, []);

  function reload() {
    if (!episodeId) return;
    setError("");
    client.get(`/attendance/roster/${episodeId}`, { params: { start_date: startDate, end_date: endDate } })
      .then((res) => setEntries(res.data)).catch((err) => setError(apiErrorMessage(err)));
  }
  useEffect(reload, [episodeId, startDate, endDate]);

  const selectedEmployee = useMemo(() => employees.find((e) => String(e.episode_id) === String(episodeId)), [employees, episodeId]);

  function toggleWeekday(idx) {
    setWeekdays((w) => (w.includes(idx) ? w.filter((x) => x !== idx) : [...w, idx]));
  }

  async function generateRoster() {
    if (!episodeId) return;
    setGenerating(true);
    setError("");
    try {
      await client.post("/attendance/roster/generate", {
        episode_id: Number(episodeId),
        start_date: startDate,
        end_date: endDate,
        weekly_off_weekdays: weekdays,
      });
      reload();
    } catch (err) {
      setError(apiErrorMessage(err));
    } finally {
      setGenerating(false);
    }
  }

  async function savePattern() {
    if (!episodeId) return;
    setSavingPattern(true);
    setError("");
    try {
      await client.post("/attendance/weekly-off-pattern", {
        episode_id: Number(episodeId),
        weekday: Number(patternWeekday),
        effective_from: patternEffectiveFrom,
      });
      reload();
    } catch (err) {
      setError(apiErrorMessage(err));
    } finally {
      setSavingPattern(false);
    }
  }

  async function updateEntry(row, changes) {
    setRowBusyDate(row.date);
    setError("");
    try {
      await client.patch(`/attendance/roster/${episodeId}/${row.date}`, {
        shift_id: changes.shift_id !== undefined ? changes.shift_id : row.shift_id,
        second_shift_id: changes.second_shift_id !== undefined ? changes.second_shift_id : row.second_shift_id,
        is_rest_day: changes.is_rest_day !== undefined ? changes.is_rest_day : row.is_rest_day,
        remarks: changes.remarks !== undefined ? changes.remarks : row.remarks,
      });
      reload();
    } catch (err) {
      setError(apiErrorMessage(err));
    } finally {
      setRowBusyDate(null);
    }
  }

  const columns = [
    { key: "date", header: "Date", render: (r) => formatDate(r.date) },
    {
      key: "shift_id", header: "Shift",
      render: (r) => (
        <select
          className="text-xs border border-ink/15 rounded px-1.5 py-1"
          value={r.shift_id ?? ""}
          disabled={rowBusyDate === r.date}
          onChange={(e) => updateEntry(r, { shift_id: e.target.value ? Number(e.target.value) : null })}
        >
          <option value="">No Shift</option>
          {shifts.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
        </select>
      ),
    },
    {
      key: "second_shift_id", header: "2nd Shift (Double)",
      render: (r) => (
        <select
          className="text-xs border border-ink/15 rounded px-1.5 py-1"
          value={r.second_shift_id ?? ""}
          disabled={rowBusyDate === r.date}
          onChange={(e) => updateEntry(r, { second_shift_id: e.target.value ? Number(e.target.value) : null })}
        >
          <option value="">None</option>
          {shifts.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
        </select>
      ),
    },
    { key: "is_weekly_off", header: "Weekly Off", render: (r) => (r.is_weekly_off ? "Yes" : "—") },
    {
      key: "is_rest_day", header: "Rest Day",
      render: (r) => (
        <input
          type="checkbox"
          checked={!!r.is_rest_day}
          disabled={rowBusyDate === r.date}
          onChange={(e) => updateEntry(r, { is_rest_day: e.target.checked })}
        />
      ),
    },
    { key: "is_holiday", header: "Holiday", render: (r) => (r.is_holiday ? "Yes" : "—") },
    { key: "remarks", header: "Remarks", render: (r) => r.remarks || "—" },
  ];

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-xl font-display font-semibold text-ink">Roster</h1>
        <p className="text-sm text-ink/50 mt-1">Calendar-based duty roster — one entry per employee per day.</p>
      </div>
      {error && <div className="text-sm text-danger bg-danger/10 rounded-md px-3 py-2">{error}</div>}

      <Card>
        <div className="flex flex-wrap items-end gap-2">
          <div className="w-72">
            <Select label="Employee" value={episodeId} onChange={(e) => setEpisodeId(e.target.value)}>
              <option value="">Select Employee...</option>
              {employees.map((e) => (
                <option key={e.episode_id} value={e.episode_id}>{e.employee_number} — {e.first_name} {e.last_name}</option>
              ))}
            </Select>
          </div>
          <Input label="From" type="date" value={startDate} onChange={(e) => setStartDate(e.target.value)} />
          <Input label="To" type="date" value={endDate} onChange={(e) => setEndDate(e.target.value)} />
        </div>
      </Card>

      {episodeId && (
        <>
          <Card>
            <h2 className="text-sm font-semibold text-ink mb-3">
              Weekly Off Pattern{selectedEmployee ? ` — ${selectedEmployee.first_name} ${selectedEmployee.last_name}` : ""}
            </h2>
            <div className="flex flex-wrap items-end gap-2">
              <Select label="Weekday" value={patternWeekday} onChange={(e) => setPatternWeekday(e.target.value)}>
                {WEEKDAYS.map((w, i) => <option key={w} value={i}>{w}</option>)}
              </Select>
              <Input label="Effective From" type="date" value={patternEffectiveFrom} onChange={(e) => setPatternEffectiveFrom(e.target.value)} />
              <Button onClick={savePattern} disabled={savingPattern}>{savingPattern ? "Saving…" : "Set Pattern"}</Button>
            </div>
          </Card>

          <Card>
            <h2 className="text-sm font-semibold text-ink mb-3">Generate Roster for Date Range</h2>
            <p className="text-xs text-ink/50 mb-2">Materializes weekly-off days for the selected range. Select the weekday(s) to mark off.</p>
            <div className="flex flex-wrap gap-3 mb-3">
              {WEEKDAYS.map((w, i) => (
                <Checkbox key={w} label={w} checked={weekdays.includes(i)} onChange={() => toggleWeekday(i)} />
              ))}
            </div>
            <Button onClick={generateRoster} disabled={generating}>{generating ? "Generating…" : "Generate Roster"}</Button>
          </Card>

          <Card>
            <h2 className="text-sm font-semibold text-ink mb-3">Roster Entries</h2>
            <Table columns={columns} rows={entries} keyField="date" empty="No roster entries in this range." />
          </Card>
        </>
      )}
    </div>
  );
}
