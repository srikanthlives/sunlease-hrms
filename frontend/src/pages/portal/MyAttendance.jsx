import { useEffect, useState } from "react";
import client, { apiErrorMessage } from "../../api/client";
import { Card, Button, Input, Select, Table, StatusBadge, formatDate, formatDateTime } from "../../components/ui";

function todayIso() {
  return new Date().toISOString().slice(0, 10);
}

function monthStartIso() {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-01`;
}

export default function MyAttendance() {
  const [startDate, setStartDate] = useState(monthStartIso());
  const [endDate, setEndDate] = useState(todayIso());
  const [records, setRecords] = useState([]);
  const [shifts, setShifts] = useState([]);
  const [error, setError] = useState("");
  const [reqError, setReqError] = useState("");
  const [reqSubmitting, setReqSubmitting] = useState(false);
  const [reqForm, setReqForm] = useState({ date: todayIso(), request_type: "CORRECTION", requested_check_in: "", requested_check_out: "", requested_overtime_minutes: "", reason: "" });

  useEffect(() => {
    client.get("/attendance/shifts").then((res) => setShifts(res.data)).catch(() => {});
  }, []);

  function reload() {
    setError("");
    client.get("/me/attendance/records", { params: { start_date: startDate, end_date: endDate } })
      .then((res) => setRecords(res.data))
      .catch((err) => setError(apiErrorMessage(err)));
  }

  useEffect(reload, [startDate, endDate]);

  async function submitRequest() {
    setReqError("");
    setReqSubmitting(true);
    try {
      await client.post("/me/attendance/requests", {
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
  ];

  return (
    <div className="space-y-6">
      <h1 className="text-xl font-display font-semibold text-ink">My Attendance</h1>
      {error && <div className="text-sm text-danger bg-danger/10 rounded-md px-3 py-2">{error}</div>}

      <Card>
        <div className="flex flex-wrap items-end gap-2">
          <Input label="From" type="date" value={startDate} onChange={(e) => setStartDate(e.target.value)} />
          <Input label="To" type="date" value={endDate} onChange={(e) => setEndDate(e.target.value)} />
        </div>
      </Card>

      <Card>
        <h2 className="text-sm font-semibold text-ink mb-3">Records</h2>
        <Table columns={recordColumns} rows={records} empty="No attendance records in this range." />
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
