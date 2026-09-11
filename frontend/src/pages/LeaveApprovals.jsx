import { useEffect, useState } from "react";
import { ChevronDown, ChevronRight } from "lucide-react";
import client, { apiErrorMessage } from "../api/client";
import { Card, Button, StatusBadge, formatDateTime, formatDate } from "../components/ui";

export default function LeaveApprovals() {
  const [rows, setRows] = useState([]);
  const [leaveTypes, setLeaveTypes] = useState([]);
  const [error, setError] = useState("");
  const [busyId, setBusyId] = useState(null);
  const [expanded, setExpanded] = useState({});

  function reload() {
    client.get("/leave/applications", { params: { status_: "PENDING" } }).then((res) => setRows(res.data));
    client.get("/leave/types").then((res) => setLeaveTypes(res.data));
  }
  useEffect(reload, []);

  function toggle(id) {
    setExpanded((e) => ({ ...e, [id]: !e[id] }));
  }

  function leaveTypeName(id) {
    return leaveTypes.find((t) => t.id === id)?.name || `#${id}`;
  }

  async function act(id, action) {
    setBusyId(id);
    setError("");
    try {
      const remarks = window.prompt(`Remarks for ${action} (optional):`) || "";
      await client.post(`/leave/applications/${id}/${action}`, { remarks });
      reload();
    } catch (err) {
      setError(apiErrorMessage(err));
    } finally {
      setBusyId(null);
    }
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-xl font-display font-semibold text-ink">Leave Approvals</h1>
        <p className="text-sm text-ink/50 mt-1">Leave applications awaiting review. Balance is deducted only on approval.</p>
      </div>
      {error && <div className="text-sm text-danger bg-danger/10 rounded-md px-3 py-2">{error}</div>}

      <Card>
        {rows.length === 0 && <div className="text-sm text-ink/40 py-10 text-center">No pending applications.</div>}
        <div className="space-y-3">
          {rows.map((r) => {
            const isOpen = !!expanded[r.id];
            return (
              <div key={r.id} className="border border-ink/10 rounded-md">
                <button onClick={() => toggle(r.id)} className="w-full flex items-center justify-between gap-3 p-4 text-left">
                  <div className="flex items-center gap-2 min-w-0">
                    <span className="text-ink/40 shrink-0">{isOpen ? <ChevronDown size={16} /> : <ChevronRight size={16} />}</span>
                    <div className="min-w-0">
                      <div className="text-sm font-medium truncate">
                        Employee #{r.episode_id} — {leaveTypeName(r.leave_type_id)} — {formatDate(r.start_date)} to {formatDate(r.end_date)} ({r.days} day{r.days === 1 ? "" : "s"})
                      </div>
                      <div className="text-xs text-ink/50 mt-0.5">Applied on {formatDateTime(r.created_at)}</div>
                    </div>
                  </div>
                  <StatusBadge status={r.status} />
                </button>
                {isOpen && (
                  <div className="px-4 pb-4">
                    <table className="w-full text-xs mb-2">
                      <tbody>
                        <tr className="border-t border-ink/5">
                          <td className="py-1 pr-3 font-mono w-40">half_day</td>
                          <td className="py-1 font-medium">{r.is_half_day ? `Yes (${r.half_day_session || "—"})` : "No"}</td>
                        </tr>
                        <tr className="border-t border-ink/5">
                          <td className="py-1 pr-3 font-mono">reason</td>
                          <td className="py-1 font-medium">{r.reason || "—"}</td>
                        </tr>
                      </tbody>
                    </table>
                    {r.review_remarks && <div className="text-xs text-ink/50 mb-2">Remarks: {r.review_remarks}</div>}
                    {r.status === "PENDING" && (
                      <div className="flex gap-2">
                        <Button size="sm" variant="accent" onClick={() => act(r.id, "approve")} disabled={busyId === r.id}>Approve</Button>
                        <Button size="sm" variant="danger" onClick={() => act(r.id, "reject")} disabled={busyId === r.id}>Reject</Button>
                      </div>
                    )}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      </Card>
    </div>
  );
}
