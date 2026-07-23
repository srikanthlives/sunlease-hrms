import { useEffect, useState } from 'react'
import api from '../api'
import { useAuth } from '../auth/AuthContext'
import { usePeriod } from '../period/PeriodContext'
import { useEmployeeFilters, applyEmployeeFilters } from '../period/EmployeeFilterContext'
import { Card, CardContent, CardHeader, CardTitle } from '../components/ui/card'
import { Table, THead, TBody, TR, TH, TD } from '../components/ui/table'
import { MONTH_NAMES, formatCurrency } from '../lib/utils'
import { Link } from 'react-router-dom'
import { FileText, Landmark } from 'lucide-react'

export default function Payslips() {
  const { user } = useAuth()
  const { month, year } = usePeriod()
  const filters = useEmployeeFilters()
  const { sortBy, deptFilter, locFilter } = filters
  const [payslips, setPayslips] = useState([])
  const [employees, setEmployees] = useState([])

  const isStaff = user?.role !== 'employee'

  useEffect(() => {
    api.get('/payroll/payslips', { params: { month, year } }).then((r) => setPayslips(r.data))
    if (isStaff) {
      api.get('/employees').then((r) => setEmployees(r.data))
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [month, year, user])

  function employeeOf(id) {
    return employees.find((x) => x.id === id)
  }
  function employeeLabel(id) {
    const e = employeeOf(id)
    return e ? `${e.employee_code} · ${e.first_name} ${e.last_name}` : `#${id}`
  }

  const displayed = isStaff
    ? applyEmployeeFilters(payslips, filters, (p) => employeeOf(p.employee_id))
    : payslips

  const totals = displayed.reduce(
    (acc, p) => {
      acc.gross_earnings += p.gross_earnings || 0
      acc.gross_deductions += p.gross_deductions || 0
      acc.net_pay += p.net_pay || 0
      acc.ctc_total += p.ctc_total || 0
      acc.total_paid += p.total_paid || 0
      acc.balance += p.balance || 0
      return acc
    },
    { gross_earnings: 0, gross_deductions: 0, net_pay: 0, ctc_total: 0, total_paid: 0, balance: 0 }
  )

  const filtersActive = sortBy !== 'default' || deptFilter || locFilter

  return (
    <div className="space-y-6">
      <div>
        <h1 className="font-display text-2xl font-semibold">{user?.role === 'employee' ? 'My Payslips' : 'All Payslips'}</h1>
        <p className="text-sm text-muted-foreground">
          Change the period from the top bar to view a different month.
          {isStaff && ' Sort/filter by department & location from the "Employee filters" bar above.'}
        </p>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">{MONTH_NAMES[month - 1]} {year}</CardTitle>
          {isStaff && filtersActive && (
            <p className="text-xs text-muted-foreground">
              Filtered{deptFilter ? ` · department: ${deptFilter}` : ''}{locFilter ? ` · location: ${locFilter}` : ''}
              {sortBy !== 'default' ? ` · sorted: ${sortBy.replace('_', ' ')}` : ''}
            </p>
          )}
        </CardHeader>
        <CardContent>
          <Table>
            <THead>
              <TR>
                {isStaff && <TH>Employee</TH>}
                <TH>Present/Total</TH><TH>Gross earnings</TH><TH>Gross deductions</TH><TH>Net pay</TH>
                <TH>Total paid</TH><TH>Balance</TH>
                {isStaff && <TH>CTC</TH>}
                <TH></TH>
              </TR>
            </THead>
            <TBody>
              {displayed.map((p) => (
                <TR key={p.id}>
                  {isStaff && <TD>{employeeLabel(p.employee_id)}</TD>}
                  <TD className="font-mono-num">{p.present_days}/{p.total_days}</TD>
                  <TD className="font-mono-num">₹ {formatCurrency(p.gross_earnings)}</TD>
                  <TD className="font-mono-num">₹ {formatCurrency(p.gross_deductions)}</TD>
                  <TD className="font-mono-num font-semibold text-primary">₹ {formatCurrency(p.net_pay)}</TD>
                  <TD className="font-mono-num">₹ {formatCurrency(p.total_paid)}</TD>
                  <TD className={`font-mono-num font-semibold ${p.balance > 0 ? 'text-amber-700' : p.balance < 0 ? 'text-red-600' : 'text-emerald-700'}`}>
                    {p.balance === 0 ? 'Paid' : `₹ ${formatCurrency(Math.abs(p.balance))}${p.balance < 0 ? ' (over)' : ''}`}
                  </TD>
                  {isStaff && (
                    <TD className="font-mono-num font-semibold text-amber-700">
                      {p.ctc_total != null ? `₹ ${formatCurrency(p.ctc_total)}` : '—'}
                    </TD>
                  )}
                  <TD>
                    <div className="flex items-center justify-center gap-1">
                      <Link
                        to={`/payslips/${p.id}`}
                        title="View payslip"
                        className="inline-flex h-8 w-8 items-center justify-center rounded-md text-primary hover:bg-muted"
                      >
                        <FileText className="h-4 w-4" />
                      </Link>
                      {isStaff && (
                        <Link
                          to={`/payslips/${p.id}/ctc`}
                          title="View CTC"
                          className="inline-flex h-8 w-8 items-center justify-center rounded-md text-amber-700 hover:bg-muted"
                        >
                          <Landmark className="h-4 w-4" />
                        </Link>
                      )}
                    </div>
                  </TD>
                </TR>
              ))}
              {displayed.length === 0 && (
                <TR><TD colSpan={isStaff ? 9 : 7} className="py-8 text-center text-muted-foreground">No payslips match this period/filter.</TD></TR>
              )}
              {isStaff && displayed.length > 0 && (
                <TR className="border-t-2 border-border bg-secondary/50 font-semibold hover:bg-secondary/50">
                  <TD>Total ({displayed.length})</TD>
                  <TD></TD>
                  <TD className="font-mono-num">₹ {formatCurrency(totals.gross_earnings)}</TD>
                  <TD className="font-mono-num">₹ {formatCurrency(totals.gross_deductions)}</TD>
                  <TD className="font-mono-num text-primary">₹ {formatCurrency(totals.net_pay)}</TD>
                  <TD className="font-mono-num">₹ {formatCurrency(totals.total_paid)}</TD>
                  <TD className={`font-mono-num ${totals.balance > 0 ? 'text-amber-700' : totals.balance < 0 ? 'text-red-600' : 'text-emerald-700'}`}>
                    ₹ {formatCurrency(Math.abs(totals.balance))}{totals.balance < 0 ? ' (over)' : ''}
                  </TD>
                  <TD className="font-mono-num text-amber-700">₹ {formatCurrency(totals.ctc_total)}</TD>
                  <TD></TD>
                </TR>
              )}
            </TBody>
          </Table>
        </CardContent>
      </Card>
    </div>
  )
}
