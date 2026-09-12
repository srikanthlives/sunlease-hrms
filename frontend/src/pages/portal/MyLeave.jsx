import { useEffect, useRef, useState } from "react";
import { Paperclip, Upload } from "lucide-react";
import client, { apiErrorMessage } from "../../api/client";
import { Card, Button, Input, Select, Checkbox, Table, StatusBadge, formatDate, formatDateTime } from "../../components/ui";

const SESSION_OPTIONS = [
  { value: "FIRST_HALF", label: "First Half" },
  { value: "SECOND_HALF", label: "Second Half" },
];

export default function MyLeave() {
  const [leaveTypes, setLeaveTypes] = useState([]);
  const [balances, setBalances] = useState([]);
  const [applications, setApplications] = useState([]);
  const [error, setError] = useState("");
  const [applyError, setApplyError] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [form, setForm] = useState({ leave_type_id: "", start_date: "", end_date: "", is_half_day: false, half_day_session: "FIRST_HALF", reason: "" });
  const [attachmentFile, setAttachmentFile] = useState(null);
  const attachmentInputRef = useRef(null);

  useEffect(() => {
    client.get("/leave/types").then((res) => setLeaveTypes(res.data));
  }, []);

  function reload() {
    setError("");
    client.get("/me/leave/balances").then((res) => setBalances(res.data)).catch((err) => setError(apiErrorMessage(err)));
    client.get("/me/leave/applications").then((res) => setApplications(res.data)).catch((err) => setError(apiErrorMessage(err)));
  }

  useEffect(reload, []);

  async function applyLeave() {
    setApplyError("");
    setSubmitting(true);
    try {
      const res = await client.post("/me/leave/applications", {
        leave_type_id: Number(form.leave_type_id),
        start_date: form.start_date,
        end_date: form.is_half_day ? form.start_date : form.end_date,
        is_half_day: form.is_half_day,
        half_day_session: form.is_half_day ? form.half_day_session : null,
        reason: form.reason || null,
      });
      if (attachmentFile) {
        const formData = new FormData();
        formData.append("file", attachmentFile);
        await client.post(`/me/leave/applications/${res.data.id}/attachment`, formData, { headers: { "Content-Type": "multipart/form-data" } });
      }
      setForm({ leave_type_id: "", start_date: "", end_date: "", is_half_day: false, half_day_session: "FIRST_HALF", reason: "" });
      setAttachmentFile(null);
      if (attachmentInputRef.current) attachmentInputRef.current.value = "";
      reload();
    } catch (err) {
      setApplyError(apiErrorMessage(err));
    } finally {
      setSubmitting(false);
    }
  }

  async function uploadAttachment(applicationId, file) {
    setError("");
    try {
      const formData = new FormData();
      formData.append("file", file);
      await client.post(`/me/leave/applications/${applicationId}/attachment`, formData, { headers: { "Content-Type": "multipart/form-data" } });
      reload();
    } catch (err) {
      setError(apiErrorMessage(err));
    }
  }

  async function downloadAttachment(applicationId, fileName) {
    setError("");
    try {
      const res = await client.get(`/me/leave/applications/${applicationId}/attachment`, { responseType: "blob" });
      const url = URL.createObjectURL(res.data);
      const a = document.createElement("a");
      a.href = url;
      a.download = fileName || "attachment";
      a.click();
      URL.revokeObjectURL(url);
    } catch (err) {
      setError(apiErrorMessage(err));
    }
  }

  async function cancelApplication(id) {
    if (!window.confirm("Cancel this leave application?")) return;
    try {
      await client.post(`/me/leave/applications/${id}/cancel`);
      reload();
    } catch (err) {
      setError(apiErrorMessage(err));
    }
  }

  const balanceColumns = [
    { key: "leave_type_name", header: "Leave Type" },
    { key: "opening_balance", header: "Opening" },
    { key: "accrued", header: "Accrued" },
    { key: "used", header: "Used" },
    { key: "adjusted", header: "Adjusted" },
    { key: "available", header: "Available" },
  ];

  const applicationColumns = [
    { key: "leave_type_id", header: "Leave Type", render: (r) => leaveTypes.find((t) => t.id === r.leave_type_id)?.name || r.leave_type_id },
    { key: "start_date", header: "Start", render: (r) => formatDate(r.start_date) },
    { key: "end_date", header: "End", render: (r) => formatDate(r.end_date) },
    { key: "days", header: "Days" },
    { key: "status", header: "Status", render: (r) => <StatusBadge status={r.status} /> },
    { key: "created_at", header: "Applied", render: (r) => formatDateTime(r.created_at) },
    {
      key: "attachment", header: "Attachment",
      render: (r) => <AttachmentCell application={r} onUpload={uploadAttachment} onDownload={downloadAttachment} />,
    },
    {
      key: "_actions", header: "", align: "right",
      render: (r) => (r.status === "PENDING" || (r.status === "APPROVED" && r.start_date >= new Date().toISOString().slice(0, 10))) ? (
        <Button variant="danger" size="sm" onClick={() => cancelApplication(r.id)}>Cancel</Button>
      ) : null,
    },
  ];

  const canApply = form.leave_type_id && form.start_date && (form.is_half_day || form.end_date);

  return (
    <div className="space-y-6">
      <h1 className="text-xl font-display font-semibold text-ink">My Leave</h1>
      {error && <div className="text-sm text-danger bg-danger/10 rounded-md px-3 py-2">{error}</div>}

      <Card>
        <h2 className="text-sm font-semibold text-ink mb-3">Leave Balances</h2>
        <Table columns={balanceColumns} rows={balances} keyField="leave_type_id" empty="No leave types configured." />
      </Card>

      <Card>
        <h2 className="text-sm font-semibold text-ink mb-3">Apply Leave</h2>
        {applyError && <div className="text-sm text-danger bg-danger/10 rounded-md px-3 py-2 mb-3">{applyError}</div>}
        <div className="grid grid-cols-4 gap-2">
          <Select label="Leave Type" value={form.leave_type_id} onChange={(e) => setForm({ ...form, leave_type_id: e.target.value })}>
            <option value="">Leave Type...</option>
            {leaveTypes.map((t) => <option key={t.id} value={t.id}>{t.name}</option>)}
          </Select>
          <Input type="date" label="Start Date" value={form.start_date} onChange={(e) => setForm({ ...form, start_date: e.target.value })} />
          {!form.is_half_day && (
            <Input type="date" label="End Date" value={form.end_date} onChange={(e) => setForm({ ...form, end_date: e.target.value })} />
          )}
          {form.is_half_day && (
            <Select label="Session" value={form.half_day_session} onChange={(e) => setForm({ ...form, half_day_session: e.target.value })}>
              {SESSION_OPTIONS.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
            </Select>
          )}
          <Input label="Reason" placeholder="Reason" value={form.reason} onChange={(e) => setForm({ ...form, reason: e.target.value })} />
        </div>
        <div className="flex items-center justify-between mt-3">
          <Checkbox
            label="Half Day"
            checked={form.is_half_day}
            onChange={(e) => setForm({ ...form, is_half_day: e.target.checked, end_date: e.target.checked ? form.start_date : form.end_date })}
          />
          <label className="flex items-center gap-1.5 text-xs text-ink/50 cursor-pointer hover:text-ink/80">
            <Paperclip size={12} />
            <span className="truncate max-w-[220px]">{attachmentFile ? attachmentFile.name : "Attach supporting document (optional)"}</span>
            <input
              ref={attachmentInputRef}
              type="file"
              className="hidden"
              onChange={(e) => setAttachmentFile(e.target.files?.[0] || null)}
            />
          </label>
        </div>
        <div>
          <Button className="mt-3" onClick={applyLeave} disabled={!canApply || submitting}>{submitting ? "Applying…" : "Apply Leave"}</Button>
        </div>
      </Card>

      <Card>
        <h2 className="text-sm font-semibold text-ink mb-3">My Applications</h2>
        <Table columns={applicationColumns} rows={applications} empty="No leave applications yet." />
      </Card>
    </div>
  );
}

function AttachmentCell({ application, onUpload, onDownload }) {
  const inputRef = useRef(null);
  const [uploading, setUploading] = useState(false);

  async function handleFile(e) {
    const file = e.target.files?.[0];
    if (!file) return;
    setUploading(true);
    await onUpload(application.id, file);
    setUploading(false);
    if (inputRef.current) inputRef.current.value = "";
  }

  return (
    <div className="flex items-center gap-2">
      {application.attachment_file_name ? (
        <button
          type="button"
          className="inline-flex items-center gap-1 text-xs text-brand-600 hover:underline"
          onClick={() => onDownload(application.id, application.attachment_file_name)}
          title={application.attachment_file_name}
        >
          <Paperclip size={12} /> <span className="max-w-[120px] truncate">{application.attachment_file_name}</span>
        </button>
      ) : (
        <span className="text-xs text-ink/30">—</span>
      )}
      <label className="inline-flex items-center gap-1 text-xs text-ink/50 hover:text-ink/80 cursor-pointer">
        <Upload size={12} />
        <input ref={inputRef} type="file" className="hidden" onChange={handleFile} disabled={uploading} />
      </label>
    </div>
  );
}
