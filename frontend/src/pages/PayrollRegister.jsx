import { useEffect, useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { Eye } from "lucide-react";
import client, { apiErrorMessage } from "../api/client";
import { Card, Button, Table, StatusBadge } from "../components/ui";
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

  const earnings = detail.lines.filter((l) => l.component_type === "EARNING");
  const deductions = detail.lines.filter((l) => l.component_type === "DEDUCTION");
  const additions = detail.lines.filter((l) => l.component_type === "ADDITION");
  const employerContributions = detail.lines.filter((l) => l.component_type === "EMPLOYER_CONTRIBUTION");

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

      <Card className="max-w-3xl mx-auto print:shadow-none print:border-0">
        <div className="text-center border-b border-ink/10 pb-4 mb-4">
          <div className="text-lg font-display font-semibold text-ink">Payslip</div>
          <div className="text-sm text-ink/60 mt-1">
            {detail.first_name} {detail.last_name} · {detail.employee_number}
          </div>
        </div>

        <div className="grid grid-cols-3 gap-3 text-xs text-ink/60 border-b border-ink/10 pb-4 mb-4">
          <div>Present Days<div className="text-sm text-ink font-medium">{detail.present_days}</div></div>
          <div>Paid Leave Days<div className="text-sm text-ink font-medium">{detail.paid_leave_days}</div></div>
          <div>LOP Days<div className="text-sm text-ink font-medium">{detail.lop_days}</div></div>
        </div>

        <div className="grid grid-cols-2 gap-6 mb-4">
          <div>
            <h3 className="text-xs font-semibold uppercase tracking-wide text-ink/50 mb-2">Earnings</h3>
            <table className="w-full text-sm">
              <tbody>
                {earnings.map((l, i) => (
                  <tr key={i} className="border-b border-ink/5">
                    <td className="py-1">{l.component_name}</td>
                    <td className="py-1 text-right">{l.amount.toFixed(2)}</td>
                  </tr>
                ))}
                <tr className="font-medium">
                  <td className="py-1.5">Gross Earnings</td>
                  <td className="py-1.5 text-right">{detail.gross_earnings.toFixed(2)}</td>
                </tr>
              </tbody>
            </table>
          </div>
          <div>
            <h3 className="text-xs font-semibold uppercase tracking-wide text-ink/50 mb-2">Deductions</h3>
            <table className="w-full text-sm">
              <tbody>
                {deductions.map((l, i) => (
                  <tr key={i} className="border-b border-ink/5">
                    <td className="py-1">{l.component_name}</td>
                    <td className="py-1 text-right">{l.amount.toFixed(2)}</td>
                  </tr>
                ))}
                <tr className="font-medium">
                  <td className="py-1.5">Gross Deductions</td>
                  <td className="py-1.5 text-right">{detail.gross_deductions.toFixed(2)}</td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>

        {employerContributions.length > 0 && (
          <div className="mb-4">
            <h3 className="text-xs font-semibold uppercase tracking-wide text-ink/50 mb-2">Employer Contributions</h3>
            <table className="w-full text-sm">
              <tbody>
                {employerContributions.map((l, i) => (
                  <tr key={i} className="border-b border-ink/5">
                    <td className="py-1">{l.component_name}</td>
                    <td className="py-1 text-right">{l.amount.toFixed(2)}</td>
                  </tr>
                ))}
                <tr className="font-medium">
                  <td className="py-1.5">Employer Cost Total</td>
                  <td className="py-1.5 text-right">{detail.employer_cost_total.toFixed(2)}</td>
                </tr>
              </tbody>
            </table>
          </div>
        )}

        <div className="flex items-center justify-between border-b border-ink/10 pb-3 mb-3">
          <span className="text-sm font-medium text-ink/70">Net Pay</span>
          <span className="text-sm font-medium text-ink">{detail.net_pay.toFixed(2)}</span>
        </div>

        {additions.length > 0 && (
          <div className="mb-4">
            <h3 className="text-xs font-semibold uppercase tracking-wide text-ink/50 mb-2">
              Additions <span className="normal-case font-normal">(paid out, not part of Gross/Net)</span>
            </h3>
            <table className="w-full text-sm">
              <tbody>
                {additions.map((l, i) => (
                  <tr key={i} className="border-b border-ink/5">
                    <td className="py-1">{l.component_name}</td>
                    <td className="py-1 text-right">{l.amount.toFixed(2)}</td>
                  </tr>
                ))}
                <tr className="font-medium">
                  <td className="py-1.5">Total Additions</td>
                  <td className="py-1.5 text-right">{detail.additional_pay.toFixed(2)}</td>
                </tr>
              </tbody>
            </table>
          </div>
        )}

        <div className="bg-brand-50 border border-brand-200 rounded-md px-4 py-3 flex items-center justify-between mb-4">
          <span className="text-sm font-semibold text-ink">Total Payable</span>
          <span className="text-lg font-display font-semibold text-brand-800">{detail.total_payable.toFixed(2)}</span>
        </div>

        {detail.cost_splits?.length > 0 && (
          <div>
            <h3 className="text-xs font-semibold uppercase tracking-wide text-ink/50 mb-2">Cost Split</h3>
            <Table
              columns={[
                { key: "cost_center_id", header: "Cost Center" },
                { key: "project_id", header: "Project", render: (r) => r.project_id ?? "—" },
                { key: "percentage", header: "%" },
                { key: "amount", header: "Amount", render: (r) => r.amount.toFixed(2) },
              ]}
              rows={detail.cost_splits}
              keyField="cost_center_id"
            />
          </div>
        )}
      </Card>
    </div>
  );
}
