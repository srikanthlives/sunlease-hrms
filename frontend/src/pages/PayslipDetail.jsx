import { useEffect, useState } from 'react'
import { useParams, Link } from 'react-router-dom'
import api from '../api'
import { useAuth } from '../auth/AuthContext'
import { Card, CardContent } from '../components/ui/card'
import { Badge } from '../components/ui/badge'
import { MONTH_NAMES, formatCurrency } from '../lib/utils'
import logo from '../logo/sunlease.png'
import { ArrowLeft, Landmark } from 'lucide-react'

export default function PayslipDetail() {
  const { id } = useParams()
  const { user } = useAuth()
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

  return (
    <div className="mx-auto max-w-3xl space-y-4">
      <div className="flex items-center justify-between">
        <Link to="/payslips" className="inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground">
          <ArrowLeft className="h-4 w-4" /> Back to payslips
        </Link>
        {user?.role !== 'employee' && (
          <Link to={`/payslips/${id}/ctc`} className="inline-flex items-center gap-1 text-sm text-amber-700 underline">
            <Landmark className="h-3.5 w-3.5" /> View CTC breakdown
          </Link>
        )}
      </div>

      <Card className="relative overflow-hidden">
        <div className="absolute right-8 top-8 hidden sm:block">
          <div className="stamp flex h-20 w-20 flex-col items-center justify-center text-center text-[10px] font-semibold">
            NET<br />PAY
          </div>
        </div>

        <CardContent className="space-y-8 p-8">
          <div className="flex items-center gap-2 border-b border-dashed border-border pb-6">
            <img src={logo} alt="Sunlease Payroll" className="h-8 w-auto object-contain" />
            <div>
              <p className="text-xs text-muted-foreground">Payslip for {MONTH_NAMES[payslip.month - 1]} {payslip.year}</p>
            </div>
          </div>

          {employee && (
            <div className="grid grid-cols-2 gap-4 text-sm">
              <Info label="Employee" value={`${employee.first_name} ${employee.last_name}`} />
              <Info label="Employee code" value={employee.employee_code} mono />
              <Info label="Designation" value={employee.designation || '—'} />
              <Info label="Department" value={employee.department || '—'} />
              <Info label="Bank account" value={employee.bank_account || '—'} mono />
              <Info label="Attendance" value={`${payslip.present_days} / ${payslip.total_days} days`} mono />
              {payslip.template_no && <Info label="Template used" value={payslip.template_no} mono />}
            </div>
          )}

          <div className="grid grid-cols-2 gap-8 border-t border-dashed border-border pt-6">
            <div>
              <h4 className="mb-3 font-display text-sm font-semibold text-primary">Earnings</h4>
              <div className="space-y-2">
                {earnings.map((l) => (
                  <LineRow key={l.component_code} line={l} />
                ))}
              </div>
              <div className="mt-3 flex justify-between border-t border-border pt-2 text-sm font-semibold">
                <span>Gross earnings</span>
                <span className="font-mono-num">₹ {formatCurrency(payslip.gross_earnings)}</span>
              </div>
            </div>
            <div>
              <h4 className="mb-3 font-display text-sm font-semibold text-destructive">Deductions</h4>
              <div className="space-y-2">
                {deductions.map((l) => (
                  <LineRow key={l.component_code} line={l} />
                ))}
                {deductions.length === 0 && <p className="text-sm text-muted-foreground">No deductions.</p>}
              </div>
              <div className="mt-3 flex justify-between border-t border-border pt-2 text-sm font-semibold">
                <span>Gross deductions</span>
                <span className="font-mono-num">₹ {formatCurrency(payslip.gross_deductions)}</span>
              </div>
            </div>
          </div>

          <div className="flex items-center justify-between rounded-md bg-primary px-6 py-4 text-primary-foreground">
            <span className="font-display text-lg font-semibold">Net Pay</span>
            <span className="font-mono-num text-2xl font-bold">₹ {formatCurrency(payslip.net_pay)}</span>
          </div>

          {payslip.payments.length > 0 && (
            <div className="border-t border-dashed border-border pt-6">
              <h4 className="mb-3 font-display text-sm font-semibold">Payments received this month</h4>
              <div className="space-y-2">
                {payslip.payments.map((p) => (
                  <div key={p.id} className="flex items-center justify-between text-sm">
                    <span className="text-foreground/90">
                      {p.payment_date || '—'}
                      {p.transaction_id && <span className="ml-2 font-mono-num text-xs text-muted-foreground">Txn: {p.transaction_id}</span>}
                      {p.remarks && <span className="ml-2 text-xs text-muted-foreground">({p.remarks})</span>}
                    </span>
                    <span className="font-mono-num">₹ {formatCurrency(p.amount)}</span>
                  </div>
                ))}
              </div>
              <div className="mt-3 flex justify-between border-t border-border pt-2 text-sm font-semibold">
                <span>Total paid</span>
                <span className="font-mono-num">₹ {formatCurrency(payslip.total_paid)}</span>
              </div>
            </div>
          )}

          {payslip.balance !== 0 && (
            <div className={`flex items-center justify-between rounded-md px-6 py-3 ${payslip.balance > 0 ? 'bg-amber-50 text-amber-800 border border-amber-200' : 'bg-emerald-50 text-emerald-800 border border-emerald-200'}`}>
              <span className="text-sm font-semibold">{payslip.balance > 0 ? 'Balance still owed' : 'Overpaid'}</span>
              <span className="font-mono-num text-lg font-bold">₹ {formatCurrency(Math.abs(payslip.balance))}</span>
            </div>
          )}
          {payslip.balance === 0 && payslip.payments.length > 0 && (
            <div className="flex items-center justify-center rounded-md border border-emerald-200 bg-emerald-50 px-6 py-2 text-sm font-medium text-emerald-800">
              Fully paid
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  )
}

function Info({ label, value, mono }) {
  return (
    <div>
      <p className="text-[11px] uppercase tracking-wide text-muted-foreground">{label}</p>
      <p className={mono ? 'font-mono-num' : ''}>{value}</p>
    </div>
  )
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
