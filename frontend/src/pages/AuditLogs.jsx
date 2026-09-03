import { useEffect, useState } from "react";
import client from "../api/client";
import { Card, Table, formatDateTime } from "../components/ui";

export default function AuditLogs() {
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    client.get("/employees-audit-logs").then((res) => setRows(res.data)).finally(() => setLoading(false));
  }, []);

  const columns = [
    { key: "timestamp", header: "When", width: "14%", render: (r) => formatDateTime(r.timestamp) },
    { key: "username", header: "User", width: "14%", render: (r) => `${r.username || "—"} (${r.role || "—"})` },
    { key: "action", header: "Action", width: "12%" },
    { key: "entity", header: "Entity", width: "16%" },
    { key: "record_id", header: "Record", width: "10%" },
    { key: "change", header: "Change", width: "34%", render: (r) => (r.old_value || r.new_value ? `${r.old_value ?? "—"} → ${r.new_value ?? "—"}` : "—") },
  ];

  return (
    <div className="space-y-5">
      <div>
        <h1 className="text-xl font-display font-semibold text-ink">Audit Logs</h1>
        <p className="text-sm text-ink/50 mt-1">Append-only trail of significant transactions (blueprint §20)</p>
      </div>
      <Card>
        {loading ? <div className="text-sm text-ink/40 py-10 text-center">Loading…</div> : <Table columns={columns} rows={rows} keyField="timestamp" />}
      </Card>
    </div>
  );
}
