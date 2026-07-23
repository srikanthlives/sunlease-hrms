import { useEffect, useState } from 'react'
import api from '../api'
import { usePeriod } from '../period/PeriodContext'
import { useEmployeeFilters, applyEmployeeFilters } from '../period/EmployeeFilterContext'
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '../components/ui/card'
import { Button } from '../components/ui/button'
import { Alert } from '../components/ui/alert'
import { Table, THead, TBody, TR, TH, TD } from '../components/ui/table'
import { PlayCircle, Landmark, FileText } from 'lucide-react'
import { MONTH_NAMES, formatCurrency } from '../lib/utils'
import { Link } from 'react-router-dom'

export default function RunPayroll() {
  const { month, year } = usePeriod()
  const filters = useEmployeeFilters()
  const [employees, setEmployees] = useState([])
  const [selectedIds, setSelectedIds] = useState(new Set())
  const [loading, setLoading] = useState(false)
  const [result, setResult] = useState(null)
  const [error, setError] = useState('')

  useEffect(() => {
    setSelectedIds(new Set())
    setResult(null)
    api.get('/employees/eligible', { params: { month, year } }).then((r) => setEmployees(r.data))
  }, [month, year])

  const displayedEmployees = applyEmployeeFilters(employees, filters, (e) => e)
  const filtersActive = filters.sortBy !== 'default' || filters.deptFilter || filters.locFilter

  function toggle(id) {
    const next = new Set(selectedIds)
    next.has(id) ? next.delete(id) : next.add(id)
    setSelectedIds(next)
  }

  function selectAllShown() {
    setSelectedIds(new Set(displayedEmployees.map((e) => e.id)))
  }

  async function run() {
    setLoading(true); setError(''); setResult(null)
    try {
      const { data } = await api.post('/payroll/run', {
        month, year,
        employee_ids: selectedIds.size ? Array.from(selectedIds) : null,
      })
      setResult(data)
    } catch (err) {
      setError(err.response?.data?.detail || 'Payroll run failed')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="font-display text-2xl font-semibold">Run Payroll</h1>
        <p className="text-sm text-muted-foreground">
          Computes payslips from each employee's template, applying attendance, monthly variable overrides, and ad-hoc entries.
          Only employees eligible for this period (joined by this month, and not yet left before it) are shown below — this is based
          on joining/last-working-day dates, not the status field. Leave selection empty to run for everyone eligible.
        </p>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Period: {MONTH_NAMES[month - 1]} {year}</CardTitle>
          <CardDescription>Change this from the top bar — it applies across Attendance, Variables, Ad-hoc, and Payslips too.</CardDescription>
        </CardHeader>
        <CardContent>
          <Button onClick={run} disabled={loading}><PlayCircle className="h-4 w-4" /> {loading ? 'Running…' : 'Run payroll'}</Button>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Eligible employees ({selectedIds.size || 'all ' + employees.length})</CardTitle>
          <CardDescription>
            Employees whose joining date is on/before this period and whose last working day (if any) is on/after it.
            {filtersActive && ' The "Employee filters" bar above narrows what\'s shown/selectable here — running with nothing checked still targets ALL eligible employees, not just the filtered ones, unless you select them (or use "Select all shown" below).'}
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-3">
          {filtersActive && (
            <Button variant="outline" size="sm" onClick={selectAllShown}>Select all shown ({displayedEmployees.length})</Button>
          )}
          <Table>
            <THead><TR><TH></TH><TH>Code</TH><TH>Name</TH><TH>Department</TH><TH>Location</TH><TH>Template</TH><TH>Joined</TH><TH>Last working day</TH></TR></THead>
            <TBody>
              {displayedEmployees.map((emp) => (
                <TR key={emp.id}>
                  <TD><input type="checkbox" checked={selectedIds.has(emp.id)} onChange={() => toggle(emp.id)} /></TD>
                  <TD className="font-mono-num">{emp.employee_code}</TD>
                  <TD>{emp.first_name} {emp.last_name}</TD>
                  <TD className="text-muted-foreground">{emp.department || '—'}</TD>
                  <TD className="text-muted-foreground">{emp.location || '—'}</TD>
                  <TD>{emp.template ? `${emp.template.template_no}` : <span className="text-destructive">No template</span>}</TD>
                  <TD className="font-mono-num text-muted-foreground">{emp.date_of_joining || '—'}</TD>
                  <TD className="font-mono-num text-muted-foreground">{emp.date_of_leaving || '—'}</TD>
                </TR>
              ))}
              {employees.length === 0 && (
                <TR><TD colSpan={8} className="py-6 text-center text-muted-foreground">No employees are eligible for this period.</TD></TR>
              )}
              {employees.length > 0 && displayedEmployees.length === 0 && (
                <TR><TD colSpan={8} className="py-6 text-center text-muted-foreground">No eligible employees match the current filters.</TD></TR>
              )}
            </TBody>
          </Table>
        </CardContent>
      </Card>

      {error && <Alert variant="destructive">{error}</Alert>}

      {result && (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Run complete</CardTitle>
            <CardDescription>{result.generated} payslip(s) generated · run #{result.payroll_run_id}</CardDescription>
          </CardHeader>
          <CardContent className="space-y-3">
            {result.removed_stale.length > 0 && (
              <Alert variant="warning">
                <p className="mb-1 font-medium">Removed stale payslip(s) from earlier runs (employee no longer eligible for this period):</p>
                {result.removed_stale.map((f, i) => <div key={i}>{f}</div>)}
              </Alert>
            )}
            {result.failed.length > 0 && (
              <Alert variant="destructive">
                {result.failed.map((f, i) => <div key={i}>{f}</div>)}
              </Alert>
            )}
            <Table>
              <THead><TR><TH>Employee</TH><TH>Present/Total</TH><TH>Gross earnings</TH><TH>Gross deductions</TH><TH>Net pay</TH><TH>CTC</TH><TH></TH></TR></THead>
              <TBody>
                {result.payslips.map((p) => {
                  const emp = employees.find((e) => e.id === p.employee_id)
                  return (
                    <TR key={p.id}>
                      <TD>{emp ? `${emp.employee_code} · ${emp.first_name} ${emp.last_name}` : p.employee_id}</TD>
                      <TD className="font-mono-num">{p.present_days}/{p.total_days}</TD>
                      <TD className="font-mono-num">₹ {formatCurrency(p.gross_earnings)}</TD>
                      <TD className="font-mono-num">₹ {formatCurrency(p.gross_deductions)}</TD>
                      <TD className="font-mono-num font-semibold text-primary">₹ {formatCurrency(p.net_pay)}</TD>
                      <TD className="font-mono-num font-semibold text-amber-700">₹ {formatCurrency(p.ctc_total)}</TD>
                      <TD>
                        <div className="flex items-center justify-center gap-1">
                          <Link
                            to={`/payslips/${p.id}`}
                            title="View payslip"
                            className="inline-flex h-8 w-8 items-center justify-center rounded-md text-primary hover:bg-muted"
                          >
                            <FileText className="h-4 w-4" />
                          </Link>
                          <Link
                            to={`/payslips/${p.id}/ctc`}
                            title="View CTC"
                            className="inline-flex h-8 w-8 items-center justify-center rounded-md text-amber-700 hover:bg-muted"
                          >
                            <Landmark className="h-4 w-4" />
                          </Link>
                        </div>
                      </TD>
                    </TR>
                  )
                })}
              </TBody>
            </Table>
          </CardContent>
        </Card>
      )}
    </div>
  )
}
