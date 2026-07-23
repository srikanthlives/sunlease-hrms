import { useEffect, useState } from 'react'
import { useParams, Link } from 'react-router-dom'
import api from '../api'
import { Card, CardContent } from '../components/ui/card'
import { Badge } from '../components/ui/badge'
import { MONTH_NAMES, formatCurrency } from '../lib/utils'
import { ArrowLeft, Landmark, FileText } from 'lucide-react'

export default function CTCDetail() {
  const { id } = useParams()
  const [payslip, setPayslip] = useState(null)
  const [employee, setEmployee] = useState(null)

  useEffect(() => {
    api.get(`/payroll/payslips/${id}`).then((r) => {
      setPayslip(r.data)
      api.get(`/employees/${r.data.employee_id}`).then((er) => setEmployee(er.data))
    })
  }, [id])

  if (!payslip) return <p className="text-muted-foreground">Loading…</p>

  const earnings = payslip.lines.filter((l) => l.component_type === 'earning')
  const deductions = payslip.lines.filter((l) => l.component_type === 'deduction')
  const employerLines = payslip.lines.filter((l) => l.component_type === 'employer_contribution')
  const referenceLines = payslip.lines.filter((l) => l.component_type === 'reference')

  return (
    <div className="mx-auto max-w-3xl space-y-4">
      <div className="flex items-center justify-between">
        <Link to="/payslips" className="inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground">
          <ArrowLeft className="h-4 w-4" /> Back to payslips
        </Link>
        <Link to={`/payslips/${id}`} className="inline-flex items-center gap-1 text-sm text-primary underline">
          <FileText className="h-3.5 w-3.5" /> View payslip
        </Link>
      </div>

      <Card>
        <CardContent className="space-y-8 p-8">
          <div className="flex items-center gap-2 border-b border-dashed border-border pb-6">
            <Landmark className="h-6 w-6 text-primary" />
            <div>
              <p className="font-display text-xl font-semibold">Cost to Company (CTC)</p>
              <p className="text-xs text-muted-foreground">
                {employee ? `${employee.employee_code} · ${employee.first_name} ${employee.last_name}` : ''} — {MONTH_NAMES[payslip.month - 1]} {payslip.year}
                {payslip.template_no && ` · Template ${payslip.template_no}`}
              </p>
            </div>
          </div>

          <Alert>
            This view is for internal cost tracking only — employer contributions and calculation-reference
            values shown here never appear on the employee's payslip and don't affect their net pay.
          </Alert>

          <div>
            <h4 className="mb-3 font-display text-sm font-semibold text-primary">Employee earnings (paid)</h4>
            <div className="space-y-2">
              {earnings.map((l) => <LineRow key={l.component_code} line={l} />)}
            </div>
            <div className="mt-3 flex justify-between border-t border-border pt-2 text-sm font-semibold">
              <span>Gross earnings</span>
              <span className="font-mono-num">₹ {formatCurrency(payslip.gross_earnings)}</span>
            </div>
          </div>

          <div>
            <h4 className="mb-3 font-display text-sm font-semibold text-destructive">Employee deductions</h4>
            <div className="space-y-2">
              {deductions.map((l) => <LineRow key={l.component_code} line={l} />)}
              {deductions.length === 0 && <p className="text-sm text-muted-foreground">No deductions.</p>}
            </div>
            <div className="mt-3 flex justify-between border-t border-border pt-2 text-sm font-semibold">
              <span>Gross deductions</span>
              <span className="font-mono-num">₹ {formatCurrency(payslip.gross_deductions)}</span>
            </div>
          </div>

          <div className="flex items-center justify-between rounded-md bg-secondary px-6 py-3 text-sm font-semibold">
            <span>Net pay (what the employee receives)</span>
            <span className="font-mono-num text-lg">₹ {formatCurrency(payslip.net_pay)}</span>
          </div>

          <div className="border-t border-dashed border-border pt-6">
            <h4 className="mb-3 font-display text-sm font-semibold text-amber-700">Employer contributions (cost only, not paid to employee)</h4>
            <div className="space-y-2">
              {employerLines.map((l) => <LineRow key={l.component_code} line={l} />)}
              {employerLines.length === 0 && <p className="text-sm text-muted-foreground">No employer-side contributions on this template.</p>}
            </div>
            <div className="mt-3 flex justify-between border-t border-border pt-2 text-sm font-semibold">
              <span>Total employer contribution</span>
              <span className="font-mono-num">₹ {formatCurrency(payslip.employer_cost_total)}</span>
            </div>
          </div>

          {referenceLines.length > 0 && (
            <div className="rounded-md bg-muted/50 p-4">
              <h4 className="mb-2 font-display text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                Reference values (calculation helpers only — not money)
              </h4>
              <div className="space-y-1.5">
                {referenceLines.map((l) => (
                  <div key={l.component_code} className="flex items-center justify-between text-sm text-muted-foreground">
                    <span>{l.component_name} <span className="font-mono-num text-xs">({l.component_code})</span></span>
                    <span className="font-mono-num">₹ {formatCurrency(l.amount)}</span>
                  </div>
                ))}
              </div>
            </div>
          )}

          <div className="flex items-center justify-between rounded-md bg-primary px-6 py-4 text-primary-foreground">
            <span className="font-display text-lg font-semibold">Total CTC (this month)</span>
            <span className="font-mono-num text-2xl font-bold">₹ {formatCurrency(payslip.ctc_total)}</span>
          </div>
        </CardContent>
      </Card>
    </div>
  )
}

function Alert({ children }) {
  return <div className="rounded-md border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-800">{children}</div>
}

function LineRow({ line }) {
  const sourceBadge = {
    template_default: null,
    variable_override: <Badge variant="warning" className="ml-2">overridden</Badge>,
    adhoc: <Badge variant="muted" className="ml-2">ad-hoc</Badge>,
    unresolved: <Badge variant="destructive" className="ml-2">unresolved</Badge>,
  }[line.source]

  return (
    <div className="flex items-center justify-between text-sm">
      <span className="flex items-center text-foreground/90">{line.component_name}{sourceBadge}</span>
      <span className="font-mono-num">₹ {formatCurrency(line.amount)}</span>
    </div>
  )
}
