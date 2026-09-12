import { useEffect, useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { Eye } from "lucide-react";
import client, { apiErrorMessage } from "../api/client";
import { Card, Button, Table, StatusBadge } from "../components/ui";
import PayslipDetailCard from "../components/PayslipDetailCard";
import { useGlobalFilter } from "../context/GlobalFilterContext";

const MONTH_NAMES = [
  "January", "February", "March", "April", "May", "June",
  "July", "August", "September", "October", "November", "December",
];

// Mirrors AttendanceRegister's two-mode pattern via useSearchParams. The
// aggregate endpoint (GET /payroll/payslips) keys its rows by episode_id
// but the per-employee Payslip only exists once payroll has been
// processed for the period, and the detail endpoint (GET
// /payroll/payslips/{id}) is keyed by the Payslip's own id — so the URL
// param here is `payslip_id`, not `episode_id`.
export default function PayrollRegister() {
  const [searchParams, setSearchParams] = useSearchParams();
  const payslipIdParam = searchParams.get("payslip_id");

  if (payslipIdParam) {
    return <PayrollRegisterDetail payslipId={payslipIdParam} onBack={() => {
      const next = new URLSearchParams(searchParams);
      next.delete("payslip_id");
      setSearchParams(next);
    }} />;
  }
  return <PayrollRegisterSummary onSelectPayslip={(id) => {
    const next = new URLSearchParams(searchParams);
    next.set("payslip_id", String(id));
    setSearchParams(next);
  }} />;
}

function PayrollRegisterSummary({ onSelectPayslip }) {
  const { year, month, costCenterId } = useGlobalFilter();
  const [costCenters, setCostCenters] = useState([]);
  const [run, setRun] = useState(null);
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    client.get("/cost-centers").then((res) => setCostCenters(res.data)).catch(() => {});
  }, []);

  useEffect(() => {
    setLoading(true);
    setError("");
    const params = { year, month };
    if (costCenterId) params.cost_center_id = costCenterId;
    client.get("/payroll/payslips", { params })
      .then((res) => { setRun(res.data.run); setRows(res.data.employees); })
      .catch((err) => setError(apiErrorMessage(err)))
      .finally(() => setLoading(false));
  }, [year, month, costCenterId]);

  const costCenterName = useMemo(
    () => costCenters.find((c) => String(c.id) === String(costCenterId))?.name,
    [costCenters, costCenterId],
  );

  const columns = [
    { key: "employee_number", header: "Employee #", sortable: true },
    { key: "name", header: "Name", sortable: true, sortAccessor: (r) => `${r.first_name} ${r.last_name}`, render: (r) => `${r.first_name} ${r.last_name}` },
    { key: "gross_earnings", header: "Gross Earnings", sortable: true, render: (r) => r.payslip ? r.payslip.gross_earnings.toFixed(2) : "—" },
    { key: "gross_deductions", header: "Gross Deductions", sortable: true, render: (r) => r.payslip ? r.payslip.gross_deductions.toFixed(2) : "—" },
    { key: "net_pay", header: "Net Pay", sortable: true, render: (r) => r.payslip ? r.payslip.net_pay.toFixed(2) : "—" },
    {
      key: "_actions", header: "", align: "right",
      render: (r) => r.payslip ? (
        <Button size="sm" variant="outline" onClick={() => onSelectPayslip(r.payslip.id)}>
          <Eye size={14} /> Details
        </Button>
      ) : <span className="text-xs text-ink/30">Not processed</span>,
    },
  ];

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-xl font-display font-semibold text-ink">
          Payroll Register — {MONTH_NAMES[month - 1]} {year}
        </h1>
        <p className="text-sm text-ink/50 mt-1">
          {costCenterName ? `Cost Center: ${costCenterName}` : "All Cost Centers"}
          {run && <> · Run status: <StatusBadge status={run.status} /></>}
        </p>
      </div>
      {error && <div className="text-sm text-danger bg-danger/10 rounded-md px-3 py-2">{error}</div>}

      <Card>
        {loading ? (
          <div className="text-sm text-ink/40 py-10 text-center">Loading…</div>
        ) : (
          <Table columns={columns} rows={rows} keyField="episode_id" empty="No employees found for this period." />
        )}
      </Card>
    </div>
  );
}

function PayrollRegisterDetail({ payslipId, onBack }) {
  const [detail, setDetail] = useState(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    setError("");
    client.get(`/payroll/payslips/${payslipId}`)
      .then((res) => setDetail(res.data))
      .catch((err) => setError(apiErrorMessage(err)))
      .finally(() => setLoading(false));
  }, [payslipId]);

  if (loading) {
    return <div className="text-sm text-ink/40 py-10 text-center">Loading…</div>;
  }
  if (error || !detail) {
    return (
      <div className="space-y-4">
        {error && <div className="text-sm text-danger bg-danger/10 rounded-md px-3 py-2">{error}</div>}
        <Button variant="outline" onClick={onBack}>Back to Payroll Register</Button>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between print:hidden">
        <div>
          <h1 className="text-xl font-display font-semibold text-ink">
            Payslip — {detail.first_name} {detail.last_name} ({detail.employee_number})
          </h1>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" onClick={() => window.print()}>Print</Button>
          <Button variant="outline" onClick={onBack}>Back to Payroll Register</Button>
        </div>
      </div>

      <PayslipDetailCard detail={detail} />
    </div>
  );
}
