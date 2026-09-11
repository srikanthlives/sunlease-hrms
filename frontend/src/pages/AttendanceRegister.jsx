import { useEffect, useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { Eye } from "lucide-react";
import client, { apiErrorMessage } from "../api/client";
import { Card, Button, Input, Select, Table, StatusBadge, formatDate, formatDateTime } from "../components/ui";
import { useGlobalFilter } from "../context/GlobalFilterContext";

const STATUS_OPTIONS = ["PRESENT", "ABSENT", "HALF_DAY", "ON_LEAVE", "WEEKLY_OFF", "HOLIDAY"];

const MONTH_NAMES = [
  "January", "February", "March", "April", "May", "June",
  "July", "August", "September", "October", "November", "December",
];

function todayIso() {
  return new Date().toISOString().slice(0, 10);
}

function monthStartIso(year, month) {
  return `${year}-${String(month).padStart(2, "0")}-01`;
}

function monthEndIso(year, month) {
  const lastDay = new Date(year, month, 0).getDate();
  return `${year}-${String(month).padStart(2, "0")}-${String(lastDay).padStart(2, "0")}`;
}

export default function AttendanceRegister() {
  const [searchParams, setSearchParams] = useSearchParams();
  const episodeIdParam = searchParams.get("episode_id");

  if (episodeIdParam) {
    return <AttendanceRegisterDetail episodeId={episodeIdParam} onBack={() => {
      const next = new URLSearchParams(searchParams);
      next.delete("episode_id");
      setSearchParams(next);
    }} />;
  }
  return <AttendanceRegisterSummary onSelectEpisode={(id) => {
    const next = new URLSearchParams(searchParams);
    next.set("episode_id", String(id));
    setSearchParams(next);
  }} />;
}

// ---------------------------------------------------------------------------
// Summary list: all employees eligible under the global month + cost center
// filter, with a per-employee attendance summary and a Details link into
// the single-employee drill-down.
// ---------------------------------------------------------------------------
function summarize(records) {
  const counts = {
    PRESENT: 0, ABSENT: 0, HALF_DAY: 0, ON_LEAVE: 0, WEEKLY_OFF: 0, HOLIDAY: 0,
  };
  let late = 0;
  let early = 0;
  let overtime = 0;
  let notMarked = 0;
  for (const r of records) {
    if (r.status && Object.prototype.hasOwnProperty.call(counts, r.status)) {
      counts[r.status] += 1;
    } else if (!r.status) {
      notMarked += 1;
    }
    if ((r.late_minutes || 0) > 0) late += 1;
    if ((r.early_departure_minutes || 0) > 0) early += 1;
    overtime += r.overtime_minutes || 0;
  }
  return { ...counts, late, early, overtime, notMarked };
}

function AttendanceRegisterSummary({ onSelectEpisode }) {
  const { year, month, costCenterId } = useGlobalFilter();
  const [costCenters, setCostCenters] = useState([]);
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    client.get("/cost-centers").then((res) => setCostCenters(res.data)).catch(() => {});
  }, []);

  useEffect(() => {
    setLoading(true);
    setError("");
    const params = { year, month };
    if (costCenterId) params.cost_center_id = costCenterId;
    client
      .get("/attendance/records", { params })
      .then((res) => setRows(res.data))
      .catch((err) => setError(apiErrorMessage(err)))
      .finally(() => setLoading(false));
  }, [year, month, costCenterId]);

  const costCenterName = useMemo(
    () => costCenters.find((c) => String(c.id) === String(costCenterId))?.name,
    [costCenters, costCenterId],
  );

  const summaryRows = useMemo(
    () => rows.map((r) => ({ ...r, ...summarize(r.records) })),
    [rows],
  );

  const columns = [
    { key: "employee_number", header: "Employee #", sortable: true, width: "11%" },
    { key: "name", header: "Name", sortable: true, sortAccessor: (r) => `${r.first_name} ${r.last_name}`, render: (r) => `${r.first_name} ${r.last_name}`, width: "17%" },
    { key: "PRESENT", header: "Present", sortable: true, align: "right", width: "6%" },
    { key: "ABSENT", header: "Absent", sortable: true, align: "right", width: "6%" },
    { key: "HALF_DAY", header: "Half Day", sortable: true, align: "right", width: "7%" },
    { key: "ON_LEAVE", header: "On Leave", sortable: true, align: "right", width: "7%" },
    { key: "WEEKLY_OFF", header: "Weekly Off", sortable: true, align: "right", width: "7%" },
    { key: "HOLIDAY", header: "Holiday", sortable: true, align: "right", width: "6%" },
    { key: "late", header: "Late Days", sortable: true, align: "right", width: "7%" },
    { key: "early", header: "Early Dep. Days", sortable: true, align: "right", width: "9%" },
    { key: "overtime", header: "OT (min)", sortable: true, align: "right", width: "6%" },
    { key: "notMarked", header: "Not Marked", sortable: true, align: "right", width: "7%" },
    {
      key: "_actions", header: "", align: "right", width: "4%",
      render: (r) => (
        <Button
          size="sm"
          variant="outline"
          className="!p-1.5"
          title="View Details"
          aria-label="View Details"
          onClick={() => onSelectEpisode(r.episode_id)}
        >
          <Eye size={14} />
        </Button>
      ),
    },
  ];

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-xl font-display font-semibold text-ink">
          Attendance Register — {MONTH_NAMES[month - 1]} {year}
        </h1>
        <p className="text-sm text-ink/50 mt-1">
          {costCenterName ? `Cost Center: ${costCenterName}` : "All Cost Centers"} · Attendance summary for every employee active this period. Click Details for the full daily register.
        </p>
      </div>
      {error && <div className="text-sm text-danger bg-danger/10 rounded-md px-3 py-2">{error}</div>}

      <Card>
        {loading ? (
          <div className="text-sm text-ink/40 py-10 text-center">Loading…</div>
        ) : (
          <Table columns={columns} rows={summaryRows} keyField="episode_id" empty="No employees found for this period." />
        )}
      </Card>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Detail view: the original single-employee register (mark attendance,
// records, exceptions, correction/overtime requests) - unchanged behavior,
// just auto-selected from the URL's episode_id and defaulted to the global
// filter's month.
// ---------------------------------------------------------------------------
function AttendanceRegisterDetail({ episodeId, onBack }) {
  const { year, month } = useGlobalFilter();
  const [employee, setEmployee] = useState(null);
  const [shifts, setShifts] = useState([]);
  const [startDate, setStartDate] = useState(monthStartIso(year, month));
  const [endDate, setEndDate] = useState(monthEndIso(year, month));
  const [records, setRecords] = useState([]);
  const [exceptions, setExceptions] = useState([]);
  const [error, setError] = useState("");
  const [markError, setMarkError] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [busyExceptionId, setBusyExceptionId] = useState(null);
  const [form, setForm] = useState({ date: todayIso(), check_in: "", check_out: "", shift_id: "", status: "PRESENT" });
  const [reqError, setReqError] = useState("");
  const [reqSubmitting, setReqSubmitting] = useState(false);
  const [reqForm, setReqForm] = useState({ date: todayIso(), request_type: "CORRECTION", requested_check_in: "", requested_check_out: "", requested_overtime_minutes: "", reason: "" });

  // Reset the date range to the global filter's month whenever the
  // selected employee or the global month/year changes.
  useEffect(() => {
    setStartDate(monthStartIso(year, month));
    setEndDate(monthEndIso(year, month));
  }, [episodeId, year, month]);

  useEffect(() => {
    client.get("/employees").then((res) => {
      const found = res.data.find((e) => String(e.episode_id) === String(episodeId));
      setEmployee(found || null);
    });
    client.get("/attendance/shifts").then((res) => setShifts(res.data));
  }, [episodeId]);

  function reload() {
    if (!episodeId) return;
    setError("");
    client.get(`/attendance/records/${episodeId}`, { params: { start_date: startDate, end_date: endDate } })
      .then((res) => setRecords(res.data)).catch((err) => setError(apiErrorMessage(err)));
    client.get(`/attendance/exceptions/${episodeId}`).then((res) => setExceptions(res.data)).catch((err) => setError(apiErrorMessage(err)));
  }

  useEffect(reload, [episodeId, startDate, endDate]);

  async function markAttendance() {
    if (!episodeId) return;
    setMarkError("");
    setSubmitting(true);
    try {
      await client.post("/attendance/records", {
        episode_id: Number(episodeId),
        date: form.date,
        check_in: form.check_in ? `${form.date}T${form.check_in}:00` : null,
        check_out: form.check_out ? `${form.date}T${form.check_out}:00` : null,
        shift_id: form.shift_id ? Number(form.shift_id) : null,
        status: form.status,
      });
      setForm({ date: todayIso(), check_in: "", check_out: "", shift_id: "", status: "PRESENT" });
      reload();
    } catch (err) {
      setMarkError(apiErrorMessage(err));
    } finally {
      setSubmitting(false);
    }
  }

  async function resolveException(id) {
    const remarks = window.prompt("Resolution remarks (optional):") || "";
    setBusyExceptionId(id);
    try {
      await client.post(`/attendance/exceptions/${id}/resolve`, { resolution_remarks: remarks });
      reload();
    } catch (err) {
      setError(apiErrorMessage(err));
    } finally {
      setBusyExceptionId(null);
    }
  }

  async function submitRequest() {
    if (!episodeId) return;
    setReqError("");
    setReqSubmitting(true);
    try {
      await client.post("/attendance/requests", {
        episode_id: Number(episodeId),
        date: reqForm.date,
        request_type: reqForm.request_type,
        requested_check_in: reqForm.request_type === "CORRECTION" && reqForm.requested_check_in ? `${reqForm.date}T${reqForm.requested_check_in}:00` : null,
        requested_check_out: reqForm.request_type === "CORRECTION" && reqForm.requested_check_out ? `${reqForm.date}T${reqForm.requested_check_out}:00` : null,
        requested_overtime_minutes: reqForm.request_type === "OVERTIME" && reqForm.requested_overtime_minutes ? Number(reqForm.requested_overtime_minutes) : null,
        reason: reqForm.reason || null,
      });
      setReqForm({ date: todayIso(), request_type: "CORRECTION", requested_check_in: "", requested_check_out: "", requested_overtime_minutes: "", reason: "" });
    } catch (err) {
      setReqError(apiErrorMessage(err));
    } finally {
      setReqSubmitting(false);
    }
  }

  function shiftName(id) {
    return shifts.find((s) => s.id === id)?.name || "—";
  }

  const recordColumns = [
    { key: "date", header: "Date", render: (r) => formatDate(r.date) },
    { key: "shift_id", header: "Shift", render: (r) => shiftName(r.shift_id) },
    { key: "check_in", header: "Check In", render: (r) => formatDateTime(r.check_in) },
    { key: "check_out", header: "Check Out", render: (r) => formatDateTime(r.check_out) },
    { key: "status", header: "Status", render: (r) => <StatusBadge status={r.status} /> },
    { key: "late_minutes", header: "Late (min)" },
    { key: "early_departure_minutes", header: "Early (min)" },
    { key: "overtime_minutes", header: "OT (min)" },
    { key: "source", header: "Source" },
  ];

  const exceptionColumns = [
    { key: "date", header: "Date", render: (r) => formatDate(r.date) },
    { key: "exception_type", header: "Type" },
    { key: "status", header: "Status", render: (r) => <StatusBadge status={r.status} /> },
    { key: "resolution_remarks", header: "Remarks", render: (r) => r.resolution_remarks || "—" },
    {
      key: "_actions", header: "", align: "right",
      render: (r) => r.status === "OPEN" ? (
        <Button size="sm" variant="accent" onClick={() => resolveException(r.id)} disabled={busyExceptionId === r.id}>Resolve</Button>
      ) : null,
    },
  ];

  return (
    <div className="space-y-6">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h1 className="text-xl font-display font-semibold text-ink">
            Attendance — {employee ? `${employee.first_name} ${employee.last_name} (${employee.employee_number})` : `Employee #${episodeId}`}
          </h1>
          <p className="text-sm text-ink/50 mt-1">
            Global period: {MONTH_NAMES[month - 1]} {year}. Date range below defaults to this period but can be adjusted.
          </p>
        </div>
        <Button variant="outline" onClick={onBack}>Back to Attendance Register</Button>
      </div>
      {error && <div className="text-sm text-danger bg-danger/10 rounded-md px-3 py-2">{error}</div>}

      <Card>
        <div className="flex flex-wrap items-end gap-2">
          <Input label="From" type="date" value={startDate} onChange={(e) => setStartDate(e.target.value)} />
          <Input label="To" type="date" value={endDate} onChange={(e) => setEndDate(e.target.value)} />
        </div>
      </Card>

      <Card>
        <h2 className="text-sm font-semibold text-ink mb-3">
          Mark / Add Record{employee ? ` — ${employee.first_name} ${employee.last_name}` : ""}
        </h2>
        {markError && <div className="text-sm text-danger bg-danger/10 rounded-md px-3 py-2 mb-3">{markError}</div>}
        <div className="grid grid-cols-5 gap-2">
          <Input label="Date" type="date" value={form.date} onChange={(e) => setForm({ ...form, date: e.target.value })} />
          <Input label="Check In" type="time" value={form.check_in} onChange={(e) => setForm({ ...form, check_in: e.target.value })} />
          <Input label="Check Out" type="time" value={form.check_out} onChange={(e) => setForm({ ...form, check_out: e.target.value })} />
          <Select label="Shift" value={form.shift_id} onChange={(e) => setForm({ ...form, shift_id: e.target.value })}>
            <option value="">No Shift</option>
            {shifts.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
          </Select>
          <Select label="Status" value={form.status} onChange={(e) => setForm({ ...form, status: e.target.value })}>
            {STATUS_OPTIONS.map((s) => <option key={s} value={s}>{s.replace(/_/g, " ")}</option>)}
          </Select>
        </div>
        <div>
          <Button className="mt-3" onClick={markAttendance} disabled={!form.date || submitting}>{submitting ? "Saving…" : "Mark Attendance"}</Button>
        </div>
      </Card>

      <Card>
        <h2 className="text-sm font-semibold text-ink mb-3">Records</h2>
        <Table columns={recordColumns} rows={records} empty="No attendance records in this range." />
      </Card>

      <Card>
        <h2 className="text-sm font-semibold text-ink mb-3">Exceptions</h2>
        <Table columns={exceptionColumns} rows={exceptions} empty="No exceptions raised." />
      </Card>

      <Card>
        <h2 className="text-sm font-semibold text-ink mb-3">Request Correction / Overtime</h2>
        <p className="text-xs text-ink/50 mb-3">Submits to the Attendance Approvals queue for review.</p>
        {reqError && <div className="text-sm text-danger bg-danger/10 rounded-md px-3 py-2 mb-3">{reqError}</div>}
        <div className="grid grid-cols-5 gap-2">
          <Input label="Date" type="date" value={reqForm.date} onChange={(e) => setReqForm({ ...reqForm, date: e.target.value })} />
          <Select label="Type" value={reqForm.request_type} onChange={(e) => setReqForm({ ...reqForm, request_type: e.target.value })}>
            <option value="CORRECTION">Correction</option>
            <option value="OVERTIME">Overtime</option>
          </Select>
          {reqForm.request_type === "CORRECTION" ? (
            <>
              <Input label="Requested Check In" type="time" value={reqForm.requested_check_in} onChange={(e) => setReqForm({ ...reqForm, requested_check_in: e.target.value })} />
              <Input label="Requested Check Out" type="time" value={reqForm.requested_check_out} onChange={(e) => setReqForm({ ...reqForm, requested_check_out: e.target.value })} />
            </>
          ) : (
            <Input label="Overtime (min)" type="number" value={reqForm.requested_overtime_minutes} onChange={(e) => setReqForm({ ...reqForm, requested_overtime_minutes: e.target.value })} />
          )}
          <Input label="Reason" value={reqForm.reason} onChange={(e) => setReqForm({ ...reqForm, reason: e.target.value })} />
        </div>
        <div>
          <Button className="mt-3" onClick={submitRequest} disabled={!reqForm.date || reqSubmitting}>{reqSubmitting ? "Submitting…" : "Submit Request"}</Button>
        </div>
      </Card>
    </div>
  );
}
