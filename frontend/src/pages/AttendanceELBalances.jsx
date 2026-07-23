import { useEffect, useState } from 'react'
import api from '../api'
import { usePeriod } from '../period/PeriodContext'
import { useEmployeeFilters, applyEmployeeFilters } from '../period/EmployeeFilterContext'
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '../components/ui/card'
import { Alert } from '../components/ui/alert'
import { Badge } from '../components/ui/badge'
import { Table, THead, TBody, TR, TH, TD } from '../components/ui/table'
import { MONTH_NAMES } from '../lib/utils'

export default function AttendanceELBalances() {
  const { month, year } = usePeriod()
  const filters = useEmployeeFilters()
  const [balances, setBalances] = useState([])
  const [employees, setEmployees] = useState([])
  const [error, setError] = useState('')

  useEffect(() => {
    api.get('/attendance/el-balance', { params: { year, upto_month: month } })
      .then((r) => setBalances(r.data))
      .catch((err) => setError(err.response?.data?.detail || 'Failed to load EL balances'))
    api.get('/employees').then((r) => setEmployees(r.data)).catch(() => {})
  }, [month, year])

  function employeeOf(b) {
    return employees.find((e) => e.id === b.employee_id)
  }

  const displayedBalances = applyEmployeeFilters(balances, filters, employeeOf)
  const filtersActive = filters.sortBy !== 'default' || filters.deptFilter || filters.locFilter

  return (
    <div className="space-y-6">
      <div>
        <h1 className="font-display text-2xl font-semibold">Attendance — Earned Leave Balances</h1>
        <p className="text-sm text-muted-foreground">1 EL accrues per 20 days worked (P/2P/HD only — EL and WO don't count as "worked"), capped at 15/year.</p>
      </div>

      <p className="text-sm font-medium text-muted-foreground">
        Period: <span className="text-foreground">{MONTH_NAMES[month - 1]} {year}</span>
        <span className="ml-1 text-xs">(change from the top bar — balances are shown year-to-date, up to this month)</span>
      </p>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Earned leave — {year}, up to {MONTH_NAMES[month - 1]}</CardTitle>
          <CardDescription>
            {displayedBalances.length} of {balances.length} employee(s)
            {filtersActive && ' · filtered/sorted via the "Employee filters" bar above'}
          </CardDescription>
        </CardHeader>
        <CardContent>
          {error && <Alert variant="destructive">{error}</Alert>}
          <Table>
            <THead><TR><TH>Employee</TH><TH className="text-center">Worked days (YTD)</TH><TH className="text-center">Accrued EL</TH><TH className="text-center">EL taken</TH><TH className="text-center">EL balance</TH><TH></TH></TR></THead>
            <TBody>
              {displayedBalances.map((b) => (
                <TR key={b.employee_id}>
                  <TD>{b.employee_code} · {b.name}</TD>
                  <TD className="text-center font-mono-num">{b.worked_days}</TD>
                  <TD className="text-center font-mono-num">{b.accrued_el}</TD>
                  <TD className="text-center font-mono-num">{b.el_taken}</TD>
                  <TD className={`text-center font-mono-num font-semibold ${b.el_balance < 0 ? 'text-red-600' : 'text-emerald-700'}`}>{b.el_balance}</TD>
                  <TD>{b.cap_reached && <Badge variant="warning">Annual cap reached</Badge>}</TD>
                </TR>
              ))}
              {balances.length === 0 && (
                <TR><TD colSpan={6} className="py-8 text-center text-muted-foreground">No employees found.</TD></TR>
              )}
              {balances.length > 0 && displayedBalances.length === 0 && (
                <TR><TD colSpan={6} className="py-8 text-center text-muted-foreground">No employees match the current filters.</TD></TR>
              )}
            </TBody>
          </Table>
        </CardContent>
      </Card>
    </div>
  )
}
