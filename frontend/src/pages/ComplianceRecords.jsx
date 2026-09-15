import { useEffect, useState } from "react";
import { Download, FileCheck } from "lucide-react";
import client, { apiErrorMessage } from "../api/client";
import { Card, Button, Input, Select, Table, StatusBadge } from "../components/ui";
import { useGlobalFilter } from "../context/GlobalFilterContext";

const MONTH_NAMES = [
  "January", "February", "March", "April", "May", "June",
  "July", "August", "September", "October", "November", "December",
];

const SCHEMES = ["PF", "ESI", "PT", "LWF", "GRATUITY"];

// Unlike ComplianceOverview (locked to the app-wide global filter period),
// this page is meant for reviewing any past period's records, so filters
// start from the global filter's defaults but are independent local state.
export default function ComplianceRecords() {
  const { year: gYear, month: gMonth, costCenterId: gCostCenterId } = useGlobalFilter();
  const [costCenters, setCostCenters] = useState([]);
  const [scheme, setScheme] = useState("");
  const [costCenterId, setCostCenterId] = useState(gCostCenterId ?? "");
  const [year, setYear] = useState(gYear);
  const [month, setMonth] = useState(gMonth);
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [markingId, setMarkingId] = useState(null);
  const [downloadingId, setDownloadingId] = useState(null);

  useEffect(() => {
    client.get("/cost-centers").then((res) => setCostCenters(res.data)).catch(() => {});
  }, []);

  function reload() {
    setLoading(true);
    setError("");
    const params = { year, month };
    if (scheme) params.scheme = scheme;
    if (costCenterId) params.cost_center_id = costCenterId;
    client.get("/compliance/records", { params })
      .then((res) => setRows(res.data))
      .catch((err) => setError(apiErrorMessage(err)))
      .finally(() => setLoading(false));
  }
  useEffect(reload, [scheme, costCenterId, year, month]);

  async function download(record) {
    setError("");
    setDownloadingId(record.id);
    try {
      const res = await client.get(`/compliance/records/${record.id}/download`, { responseType: "blob" });
      const url = URL.createObjectURL(res.data);
      const a = document.createElement("a");
      a.href = url;
      a.download = `compliance_${record.scheme}_${record.year}_${record.month}.xlsx`;
      a.click();
      URL.revokeObjectURL(url);
    } catch (err) {
      setError(apiErrorMessage(err));
    } finally {
      setDownloadingId(null);
    }
  }

  function costCenterName(id) {
    if (!id) return "All";
    return costCenters.find((c) => String(c.id) === String(id))?.name || "—";
  }

  const columns = [
    { key: "scheme", header: "Scheme" },
    { key: "cost_center", header: "Cost Center", render: (r) => costCenterName(r.cost_center_id) },
    { key: "period", header: "Period", render: (r) => `${MONTH_NAMES[r.month - 1]} ${r.year}` },
    { key: "total_employee_contribution", header: "Employee Contribution", align: "right", render: (r) => r.total_employee_contribution.toFixed(2) },
    { key: "total_employer_contribution", header: "Employer Contribution", align: "right", render: (r) => r.total_employer_contribution.toFixed(2) },
    { key: "employees_covered", header: "Employees Covered", align: "right" },
    { key: "status", header: "Status", render: (r) => <StatusBadge status={r.status} /> },
    {
      key: "_actions", header: "", align: "right",
      render: (r) => (
        <div className="flex gap-2 justify-end">
          {r.status === "PENDING" && (
            <Button size="sm" variant="outline" onClick={() => setMarkingId(r.id)}>
              <FileCheck size={14} /> Mark Filed
            </Button>
          )}
          <Button size="sm" variant="outline" onClick={() => download(r)} disabled={downloadingId === r.id}>
            <Download size={14} /> {downloadingId === r.id ? "…" : "Download"}
          </Button>
        </div>
      ),
    },
  ];

  const markingRecord = rows.find((r) => r.id === markingId);

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-xl font-display font-semibold text-ink">Compliance Records</h1>
        <p className="text-sm text-ink/50 mt-1">Review and file statutory compliance records for any period.</p>
      </div>
      {error && <div className="text-sm text-danger bg-danger/10 rounded-md px-3 py-2">{error}</div>}

      <Card>
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
          <Select label="Scheme" value={scheme} onChange={(e) => setScheme(e.target.value)}>
            <option value="">All Schemes</option>
            {SCHEMES.map((s) => <option key={s} value={s}>{s}</option>)}
          </Select>
          <Select label="Cost Center" value={costCenterId} onChange={(e) => setCostCenterId(e.target.value)}>
            <option value="">All Cost Centers</option>
            {costCenters.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
          </Select>
          <Select label="Month" value={month} onChange={(e) => setMonth(Number(e.target.value))}>
            {MONTH_NAMES.map((m, i) => <option key={m} value={i + 1}>{m}</option>)}
          </Select>
          <Input label="Year" type="number" value={year} onChange={(e) => setYear(Number(e.target.value))} />
        </div>
      </Card>

      <Card>
        {loading ? (
          <div className="text-sm text-ink/40 py-10 text-center">Loading…</div>
        ) : (
          <Table columns={columns} rows={rows} keyField="id" empty="No compliance records found for this filter." />
        )}
      </Card>

      {markingRecord && (
        <MarkFiledModal
          record={markingRecord}
          onClose={() => setMarkingId(null)}
          onDone={() => { setMarkingId(null); reload(); }}
        />
      )}
    </div>
  );
}

function MarkFiledModal({ record, onClose, onDone }) {
  const [challanReferenceNumber, setChallanReferenceNumber] = useState("");
  const [filedDate, setFiledDate] = useState(new Date().toISOString().slice(0, 10));
  const [remarks, setRemarks] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function submit() {
    setError("");
    setBusy(true);
    try {
      await client.post(`/compliance/records/${record.id}/mark-filed`, {
        challan_reference_number: challanReferenceNumber,
        filed_date: filedDate,
        remarks: remarks || null,
      });
      onDone();
    } catch (err) {
      setError(apiErrorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="fixed inset-0 bg-ink/40 flex items-center justify-center z-50 px-4">
      <Card className="w-full max-w-md">
        <h2 className="text-sm font-semibold text-ink mb-1">Mark Filed — {record.scheme}</h2>
        <p className="text-xs text-ink/50 mb-4">
          {record.year}/{record.month}
        </p>
        {error && <div className="text-sm text-danger bg-danger/10 rounded-md px-3 py-2 mb-3">{error}</div>}
        <div className="space-y-3">
          <Input
            label="Challan Reference Number"
            value={challanReferenceNumber}
            onChange={(e) => setChallanReferenceNumber(e.target.value)}
          />
          <Input
            label="Filed Date"
            type="date"
            value={filedDate}
            onChange={(e) => setFiledDate(e.target.value)}
          />
          <label className="block">
            <span className="block text-xs font-medium text-ink/60 mb-1">Remarks</span>
            <textarea
              className="w-full rounded-md border border-ink/15 px-3 py-2 text-sm bg-white focus:border-brand-500 focus:ring-1 focus:ring-brand-500 outline-none"
              rows={3}
              value={remarks}
              onChange={(e) => setRemarks(e.target.value.toUpperCase())}
            />
          </label>
        </div>
        <div className="flex justify-end gap-2 mt-4">
          <Button variant="outline" onClick={onClose} disabled={busy}>Cancel</Button>
          <Button onClick={submit} disabled={busy || !challanReferenceNumber || !filedDate}>
            {busy ? "Saving…" : "Mark Filed"}
          </Button>
        </div>
      </Card>
    </div>
  );
}
