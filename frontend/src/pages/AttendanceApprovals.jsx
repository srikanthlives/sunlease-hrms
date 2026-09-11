import { useEffect, useState } from "react";
import { ChevronDown, ChevronRight } from "lucide-react";
import client, { apiErrorMessage } from "../api/client";
import { Card, Button, StatusBadge, formatDateTime, formatDate } from "../components/ui";

export default function AttendanceApprovals() {
  const [rows, setRows] = useState([]);
  const [error, setError] = useState("");
  const [busyId, setBusyId] = useState(null);
  const [expanded, setExpanded] = useState({});

  function reload() {
    client.get("/attendance/requests", { params: { status_: "PENDING" } }).then((res) => setRows(res.data));
  }
  useEffect(reload, []);

  function toggle(id) {
    setExpanded((e) => ({ ...e, [id]: !e[id] }));
  }

  async function act(id, action) {
    setBusyId(id);
    setError("");
    try {
      const remarks = window.prompt(`Remarks for ${action} (optional):`) || "";
      await client.post(`/attendance/requests/${id}/${action}`, { remarks });
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
        <h1 className="text-xl font-display font-semibold text-ink">Attendance Approvals</h1>
        <p className="text-sm text-ink/50 mt-1">Correction and overtime requests awaiting review.</p>
      </div>
      {error && <div className="text-sm text-danger bg-danger/10 rounded-md px-3 py-2">{error}</div>}

      <Card>
        {rows.length === 0 && <div className="text-sm text-ink/40 py-10 text-center">No pending requests.</div>}
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
                        Employee #{r.episode_id} — {r.request_type} — {formatDate(r.date)}
                      </div>
                      <div className="text-xs text-ink/50 mt-0.5">Requested on {formatDateTime(r.created_at)}</div>
                    </div>
                  </div>
                  <StatusBadge status={r.status} />
                </button>
                {isOpen && (
                  <div className="px-4 pb-4">
                    <table className="w-full text-xs mb-2">
                      <tbody>
                        {r.request_type === "CORRECTION" ? (
                          <>
                            <tr className="border-t border-ink/5">
                              <td className="py-1 pr-3 font-mono">requested_check_in</td>
                              <td className="py-1 font-medium">{formatDateTime(r.requested_check_in)}</td>
                            </tr>
                            <tr className="border-t border-ink/5">
                              <td className="py-1 pr-3 font-mono">requested_check_out</td>
                              <td className="py-1 font-medium">{formatDateTime(r.requested_check_out)}</td>
                            </tr>
                          </>
                        ) : (
                          <tr className="border-t border-ink/5">
                            <td className="py-1 pr-3 font-mono">requested_overtime_minutes</td>
                            <td className="py-1 font-medium">{r.requested_overtime_minutes ?? "—"}</td>
                          </tr>
                        )}
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
