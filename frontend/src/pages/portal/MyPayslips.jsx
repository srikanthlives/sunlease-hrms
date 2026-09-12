import { useEffect, useState } from "react";
import client, { apiErrorMessage } from "../../api/client";
import { Card, Button, Table } from "../../components/ui";
import PayslipDetailCard from "../../components/PayslipDetailCard";

export default function MyPayslips() {
  const [payslips, setPayslips] = useState([]);
  const [selectedId, setSelectedId] = useState(null);
  const [detail, setDetail] = useState(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    client.get("/me/payslips")
      .then((res) => setPayslips(res.data))
      .catch((err) => setError(apiErrorMessage(err)))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    if (!selectedId) return;
    setDetail(null);
    client.get(`/me/payslips/${selectedId}`)
      .then((res) => setDetail(res.data))
      .catch((err) => setError(apiErrorMessage(err)));
  }, [selectedId]);

  if (selectedId && detail) {
    return (
      <div className="space-y-6">
        <div className="flex items-center justify-between print:hidden">
          <h1 className="text-xl font-display font-semibold text-ink">Payslip</h1>
          <div className="flex gap-2">
            <Button variant="outline" onClick={() => window.print()}>Print</Button>
            <Button variant="outline" onClick={() => setSelectedId(null)}>Back to My Payslips</Button>
          </div>
        </div>
        <PayslipDetailCard detail={detail} />
      </div>
    );
  }

  const columns = [
    { key: "run_id", header: "Payroll Run" },
    { key: "gross_earnings", header: "Gross Earnings", render: (r) => r.gross_earnings.toFixed(2) },
    { key: "net_pay", header: "Net Pay", render: (r) => r.net_pay.toFixed(2) },
    { key: "total_payable", header: "Total Payable", render: (r) => r.total_payable.toFixed(2) },
    {
      key: "_actions", header: "", align: "right",
      render: (r) => <Button size="sm" variant="outline" onClick={() => setSelectedId(r.id)}>View</Button>,
    },
  ];

  return (
    <div className="space-y-6">
      <h1 className="text-xl font-display font-semibold text-ink">My Payslips</h1>
      {error && <div className="text-sm text-danger bg-danger/10 rounded-md px-3 py-2">{error}</div>}
      <Card>
        {loading ? (
          <div className="text-sm text-ink/40 py-6 text-center">Loading…</div>
        ) : (
          <Table columns={columns} rows={payslips} empty="No payslips yet." />
        )}
      </Card>
    </div>
  );
}
