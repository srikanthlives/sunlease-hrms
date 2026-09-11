import { useEffect, useState } from "react";
import client, { apiErrorMessage } from "../api/client";
import { Card, Button, StatusBadge } from "../components/ui";
import { useGlobalFilter } from "../context/GlobalFilterContext";

const MONTH_NAMES = [
  "January", "February", "March", "April", "May", "June",
  "July", "August", "September", "October", "November", "December",
];

export default function RunPayroll() {
  const { year, month, costCenterId } = useGlobalFilter();
  const [costCenters, setCostCenters] = useState([]);
  const [run, setRun] = useState(null);
  const [loading, setLoading] = useState(true);
  const [processing, setProcessing] = useState(false);
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState(null);
  const [error, setError] = useState("");

  useEffect(() => {
    client.get("/cost-centers").then((res) => setCostCenters(res.data)).catch(() => {});
  }, []);

  function reload() {
    setLoading(true);
    setError("");
    const params = { year, month };
    if (costCenterId) params.cost_center_id = costCenterId;
    client.get("/payroll/runs", { params })
      .then((res) => setRun(res.data[0] || null))
      .catch((err) => setError(apiErrorMessage(err)))
      .finally(() => setLoading(false));
  }
  useEffect(reload, [year, month, costCenterId]);

  async function processPayroll() {
    setError("");
    setProcessing(true);
    setResult(null);
    try {
      const res = await client.post("/payroll/run", { cost_center_id: costCenterId, year, month });
      setResult(res.data);
      reload();
    } catch (err) {
      setError(apiErrorMessage(err));
    } finally {
      setProcessing(false);
    }
  }

  async function approveRun() {
    if (!run) return;
    setError("");
    setBusy(true);
    try {
      await client.post(`/payroll/runs/${run.id}/approve`);
      reload();
    } catch (err) {
      setError(apiErrorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  async function lockRun() {
    if (!run) return;
    setError("");
    setBusy(true);
    try {
      await client.post(`/payroll/runs/${run.id}/lock`);
      reload();
    } catch (err) {
      setError(apiErrorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  const costCenterName = costCenters.find((c) => String(c.id) === String(costCenterId))?.name;

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-xl font-display font-semibold text-ink">Run Payroll</h1>
        <p className="text-sm text-ink/50 mt-1">
          {costCenterName ? `Cost Center: ${costCenterName}` : "All Cost Centers"} · {MONTH_NAMES[month - 1]} {year}
        </p>
      </div>
      {error && <div className="text-sm text-danger bg-danger/10 rounded-md px-3 py-2">{error}</div>}

      <Card>
        <h2 className="text-sm font-semibold text-ink mb-3">Process Payroll</h2>
        <p className="text-xs text-ink/50 mb-3">
          Computes earned days, salary structure, statutory deductions, and ad-hoc entries into payslips for every
          employee active in this Cost Center/month. Re-running while DRAFT or PROCESSED regenerates payslips;
          an APPROVED or LOCKED run refuses reprocessing.
        </p>
        <Button onClick={processPayroll} disabled={processing || (run && (run.status === "APPROVED" || run.status === "LOCKED"))}>
          {processing ? "Processing…" : "Process Payroll"}
        </Button>

        {result && (
          <div className="mt-4 text-sm">
            <div className="text-ok font-medium mb-1">Run status: {result.run.status}</div>
            {result.errors?.length > 0 && (
              <div className="border border-danger/20 bg-danger/5 rounded-md p-2 max-h-40 overflow-y-auto">
                <div className="text-xs font-medium text-danger mb-1">{result.errors.length} employee(s) skipped:</div>
                {result.errors.map((e, i) => (
                  <div key={i} className="text-xs text-ink/60">
                    {typeof e === "string" ? e : JSON.stringify(e)}
                  </div>
                ))}
              </div>
            )}
          </div>
        )}
      </Card>

      <Card>
        <h2 className="text-sm font-semibold text-ink mb-3">Current Run</h2>
        {loading ? (
          <div className="text-sm text-ink/40 py-6 text-center">Loading…</div>
        ) : !run ? (
          <div className="text-sm text-ink/40 py-6 text-center">No payroll run yet for this period.</div>
        ) : (
          <div className="space-y-3">
            <div className="flex items-center gap-3">
              <StatusBadge status={run.status} />
              <span className="text-xs text-ink/50">
                {run.processed_by && `Processed by ${run.processed_by}`}
                {run.approved_by && ` · Approved by ${run.approved_by}`}
                {run.locked_at && ` · Locked`}
              </span>
            </div>
            <div className="flex gap-2">
              <Button onClick={approveRun} disabled={run.status !== "PROCESSED" || busy}>
                {busy ? "Working…" : "Approve"}
              </Button>
              <Button variant="accent" onClick={lockRun} disabled={run.status !== "APPROVED" || busy}>
                {busy ? "Working…" : "Lock"}
              </Button>
            </div>
          </div>
        )}
      </Card>
    </div>
  );
}
