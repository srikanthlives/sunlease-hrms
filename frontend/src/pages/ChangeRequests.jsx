import { useEffect, useState } from "react";
import { ChevronDown, ChevronRight } from "lucide-react";
import client, { apiErrorMessage } from "../api/client";
import { Card, Button, StatusBadge, formatDateTime } from "../components/ui";

export default function ChangeRequests() {
  const [rows, setRows] = useState([]);
  const [error, setError] = useState("");
  const [busyId, setBusyId] = useState(null);
  const [expanded, setExpanded] = useState({});

  function reload() {
    client.get("/employees-change-requests").then((res) => setRows(res.data));
  }
  useEffect(reload, []);

  function toggle(id) {
    setExpanded((e) => ({ ...e, [id]: !e[id] }));
  }

  async function previewDocument(id, which, fileName) {
    const res = await client.get(`/employees-change-requests/${id}/preview`, { params: { which }, responseType: "blob" });
    const url = URL.createObjectURL(res.data);
    const a = document.createElement("a");
    a.href = url;
    a.download = fileName || (which === "new" ? "new-document" : "old-document");
    a.click();
    URL.revokeObjectURL(url);
  }

  async function act(id, action) {
    setBusyId(id);
    setError("");
    try {
      const remarks = action === "reject" ? window.prompt("Reason for rejection (optional):") || "" : "";
      await client.post(`/employees-change-requests/${id}/${action}`, { remarks });
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
        <h1 className="text-xl font-display font-semibold text-ink">Change Requests</h1>
        <p className="text-sm text-ink/50 mt-1">
          Edits to an already-Active employee's identity/employment fields require approval (blueprint §15).
        </p>
      </div>
      {error && <div className="text-sm text-danger bg-danger/10 rounded-md px-3 py-2">{error}</div>}

      <Card>
        {rows.length === 0 && <div className="text-sm text-ink/40 py-10 text-center">No change requests.</div>}
        <div className="space-y-3">
          {rows.map((r) => {
            const isOpen = !!expanded[r.id];
            return (
              <div key={r.id} className="border border-ink/10 rounded-md">
                <button
                  onClick={() => toggle(r.id)}
                  className="w-full flex items-center justify-between gap-3 p-4 text-left"
                >
                  <div className="flex items-center gap-2 min-w-0">
                    <span className="text-ink/40 shrink-0">
                      {isOpen ? <ChevronDown size={16} /> : <ChevronRight size={16} />}
                    </span>
                    <div className="min-w-0">
                      <div className="text-sm font-medium truncate">
                        Employee #{r.episode_id} — {r.transaction_type.replace(/_/g, " ")}
                      </div>
                      <div className="text-xs text-ink/50 mt-0.5">
                        Requested by {r.requested_by || "—"} on {formatDateTime(r.created_at)}
                        {r.reviewed_by && ` · Reviewed by ${r.reviewed_by}`}
                      </div>
                    </div>
                  </div>
                  <StatusBadge status={r.status} />
                </button>
                {isOpen && (
                  <div className="px-4 pb-4">
                    {r.transaction_type === "DOCUMENT_CHANGE" ? (
                      <div className="flex items-center gap-2 mb-2">
                        <Button size="sm" variant="outline" onClick={() => previewDocument(r.id, "old", r.previous_values.old_file_name)}>
                          Download Old Document ({r.previous_values.old_file_name || "—"})
                        </Button>
                        <Button size="sm" variant="outline" onClick={() => previewDocument(r.id, "new", r.changes.new_file_name)}>
                          Download New Document ({r.changes.new_file_name || "—"})
                        </Button>
                      </div>
                    ) : (
                      <table className="w-full text-xs mb-2">
                        <thead>
                          <tr className="text-left text-ink/40">
                            <th className="py-1 pr-3">Field</th>
                            <th className="py-1 pr-3">From</th>
                            <th className="py-1">To</th>
                          </tr>
                        </thead>
                        <tbody>
                          {Object.keys(r.changes).map((field) => (
                            <tr key={field} className="border-t border-ink/5">
                              <td className="py-1 pr-3 font-mono">{field}</td>
                              <td className="py-1 pr-3 text-ink/60">{String(r.previous_values[field] ?? "—")}</td>
                              <td className="py-1 font-medium">{String(r.changes[field] ?? "—")}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    )}
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
