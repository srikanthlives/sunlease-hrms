import { useEffect, useState } from "react";
import client, { apiErrorMessage } from "../api/client";
import { Card, Button, Select, StatusBadge, formatDateTime } from "../components/ui";

// The /employees list endpoint has no status filter param, so this page
// fetches the full list and filters client-side to SEPARATED episodes
// (the only ones eligible for Full & Final Settlement) rather than
// guessing an unsupported query param.
export default function FullFinalSettlement() {
  const [employees, setEmployees] = useState([]);
  const [episodeId, setEpisodeId] = useState("");
  const [settlement, setSettlement] = useState(null);
  const [loading, setLoading] = useState(false);
  const [processing, setProcessing] = useState(false);
  const [error, setError] = useState("");
  const [notFound, setNotFound] = useState(false);

  useEffect(() => {
    client.get("/employees").then((res) => setEmployees(res.data.filter((e) => e.status === "SEPARATED"))).catch(() => {});
  }, []);

  function reload() {
    if (!episodeId) return;
    setLoading(true);
    setError("");
    setNotFound(false);
    client.get(`/payroll/full-final/${episodeId}`)
      .then((res) => setSettlement(res.data))
      .catch((err) => {
        if (err?.response?.status === 404) { setNotFound(true); setSettlement(null); }
        else setError(apiErrorMessage(err));
      })
      .finally(() => setLoading(false));
  }
  useEffect(reload, [episodeId]);

  async function processSettlement() {
    if (!episodeId) return;
    setError("");
    setProcessing(true);
    try {
      const res = await client.post(`/payroll/full-final/${episodeId}/process`);
      setSettlement(res.data);
      setNotFound(false);
    } catch (err) {
      setError(apiErrorMessage(err));
    } finally {
      setProcessing(false);
    }
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-xl font-display font-semibold text-ink">Full &amp; Final Settlement</h1>
        <p className="text-sm text-ink/50 mt-1">
          Computes leave encashment, gratuity, notice pay recovery, and net payable for a separated employee.
        </p>
      </div>
      {error && <div className="text-sm text-danger bg-danger/10 rounded-md px-3 py-2">{error}</div>}

      <Card>
        <Select label="Separated Employee" value={episodeId} onChange={(e) => setEpisodeId(e.target.value)}>
          <option value="">Select employee...</option>
          {employees.map((e) => (
            <option key={e.episode_id} value={e.episode_id}>{e.employee_number} — {e.first_name} {e.last_name}</option>
          ))}
        </Select>
      </Card>

      {episodeId && (
        <Card>
          <div className="flex items-center justify-between mb-3">
            <h2 className="text-sm font-semibold text-ink">Settlement</h2>
            <Button onClick={processSettlement} disabled={processing}>
              {processing ? "Processing…" : settlement ? "Reprocess Settlement" : "Process Settlement"}
            </Button>
          </div>

          {loading ? (
            <div className="text-sm text-ink/40 py-6 text-center">Loading…</div>
          ) : notFound && !settlement ? (
            <div className="text-sm text-ink/40 py-6 text-center">No settlement processed yet for this employee.</div>
          ) : settlement ? (
            <div className="space-y-4">
              <div className="flex items-center gap-3">
                <StatusBadge status={settlement.status} />
                {settlement.processed_at && <span className="text-xs text-ink/50">Processed {formatDateTime(settlement.processed_at)}</span>}
              </div>
              <div className="grid grid-cols-3 gap-4 text-sm">
                <div><div className="text-xs text-ink/50">Leave Encashment Days</div><div className="font-medium">{settlement.leave_encashment_days}</div></div>
                <div><div className="text-xs text-ink/50">Leave Encashment Amount</div><div className="font-medium">{settlement.leave_encashment_amount.toFixed(2)}</div></div>
                <div><div className="text-xs text-ink/50">Gratuity Years of Service</div><div className="font-medium">{settlement.gratuity_years_of_service}</div></div>
                <div><div className="text-xs text-ink/50">Gratuity Amount</div><div className="font-medium">{settlement.gratuity_amount.toFixed(2)}</div></div>
                <div><div className="text-xs text-ink/50">Notice Pay Recovery</div><div className="font-medium">{settlement.notice_pay_recovery.toFixed(2)}</div></div>
                <div><div className="text-xs text-ink/50">Other Dues</div><div className="font-medium">{settlement.other_dues.toFixed(2)}</div></div>
              </div>
              <div className="bg-brand-50 border border-brand-200 rounded-md px-4 py-3 flex items-center justify-between">
                <span className="text-sm font-semibold text-ink">Net Payable</span>
                <span className="text-lg font-display font-semibold text-brand-800">{settlement.net_payable.toFixed(2)}</span>
              </div>
            </div>
          ) : null}
        </Card>
      )}
    </div>
  );
}
