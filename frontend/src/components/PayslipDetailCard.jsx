import { Card, Table } from "./ui";

// Read-only payslip rendering (Earnings/Deductions/Employer Contributions/
// Net Pay/Additions/Total Payable/Cost Split), shared between the admin
// Payroll Register detail view and the employee self-service portal.
export default function PayslipDetailCard({ detail }) {
  const earnings = detail.lines.filter((l) => l.component_type === "EARNING");
  const deductions = detail.lines.filter((l) => l.component_type === "DEDUCTION");
  const additions = detail.lines.filter((l) => l.component_type === "ADDITION");
  const employerContributions = detail.lines.filter((l) => l.component_type === "EMPLOYER_CONTRIBUTION");

  return (
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
  );
}
