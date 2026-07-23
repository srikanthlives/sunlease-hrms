import { useEffect, useState } from 'react'
import api from '../api'
import { usePeriod } from '../period/PeriodContext'
import { useEmployeeFilters, applyEmployeeFilters } from '../period/EmployeeFilterContext'
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '../components/ui/card'
import { Alert } from '../components/ui/alert'
import { Table, THead, TBody, TR, TH, TD } from '../components/ui/table'
import { MONTH_NAMES } from '../lib/utils'
import { STATUS_META, STATUS_OPTIONS, STATUS_LEGEND } from '../lib/attendanceStatus'

function isDateInWindow(employee, dateStr) {
  if (!employee || !dateStr) return false

  const parseDateParts = (value) => {
    if (!value) return null
    const parts = value.split('-').map(Number)
    if (parts.length < 2 || parts.some(Number.isNaN)) return null
    return [parts[0], parts[1], parts[2] ?? 1]
  }

  const compareDates = (left, right) => {
    if (left[0] !== right[0]) return left[0] < right[0] ? -1 : 1
    if (left[1] !== right[1]) return left[1] < right[1] ? -1 : 1
    if (left[2] !== right[2]) return left[2] < right[2] ? -1 : 1
    return 0
  }

  const current = parseDateParts(dateStr)
  if (!current) return false

  const doj = parseDateParts(employee.date_of_joining)
  if (doj && compareDates(current, doj) < 0) return false

  const dol = parseDateParts(employee.date_of_leaving)
  if (dol && compareDates(current, dol) > 0) return false

  return true
}

export default function AttendanceGrid() {
  const { month, year } = usePeriod()
  const filters = useEmployeeFilters()
  const [grid, setGrid] = useState(null)
  const [employees, setEmployees] = useState([])
  const [error, setError] = useState('')

  function load() {
    api.get('/attendance/grid', { params: { month, year } })
      .then((r) => setGrid(r.data))
      .catch((err) => setError(err.response?.data?.detail || 'Failed to load attendance grid'))
    api.get('/employees').then((r) => setEmployees(r.data)).catch(() => {})
  }
  useEffect(load, [month, year])

  async function updateCell(employeeId, date, status) {
    setGrid((prev) => ({
      ...prev,
      rows: prev.rows.map((r) => r.employee_id === employeeId ? { ...r, statuses: { ...r.statuses, [date]: status } } : r),
    }))
    try {
      if (status === '') {
        await api.delete('/attendance/daily', { params: { employee_id: employeeId, date } })
      } else {
        await api.post('/attendance/daily', { employee_id: employeeId, date, status })
      }
      load() // refresh so the per-employee summary columns stay accurate
    } catch (err) {
      alert(err.response?.data?.detail || 'Failed to update attendance')
      load()
    }
  }

  function employeeOf(row) {
    return employees.find((e) => e.id === row.employee_id)
  }

  const displayedRows = grid ? applyEmployeeFilters(grid.rows, filters, employeeOf) : []
  const filtersActive = filters.sortBy !== 'default' || filters.deptFilter || filters.locFilter

  return (
    <div className="space-y-6">
      <div>
        <h1 className="font-display text-2xl font-semibold">Attendance — Monthly Grid</h1>
        <p className="text-sm text-muted-foreground">
          Day-by-day attendance for every employee eligible this period. Present days drive payroll proration;
          earned leave accrues at 1 day per 20 days worked, capped at 15/year.
        </p>
      </div>

      <p className="text-sm font-medium text-muted-foreground">
        Period: <span className="text-foreground">{MONTH_NAMES[month - 1]} {year}</span>
        <span className="ml-1 text-xs">(change from the top bar)</span>
      </p>

      {error && <Alert variant="destructive">{error}</Alert>}
      {!error && !grid && <p className="text-muted-foreground">Loading…</p>}

      {grid && (
        <div className="space-y-4">
          <div className="flex flex-wrap gap-3 text-xs">
            {STATUS_LEGEND.map(([code, desc]) => (
              <span key={code} className="inline-flex items-center gap-1.5 rounded-full border border-border px-2 py-1">
                <span className={`inline-flex h-5 w-7 items-center justify-center rounded text-[10px] font-semibold ${STATUS_META[code].className}`}>{code}</span>
                <span className="text-muted-foreground">{desc}</span>
              </span>
            ))}
          </div>

          <Alert>
            <b>Total</b> = P + 2P×2 + WO + EL &nbsp;·&nbsp; <b>Present</b> = P + 2P×2 &nbsp;·&nbsp;
            <b>LOP</b> = max(0, Absent − EL). Marking a day <b>EL</b> is blocked with an error if the employee
            doesn't have enough earned-leave balance accrued yet — see Earned Leave Balances.
          </Alert>

          <Card>
            <CardHeader>
              <CardTitle className="text-base">{MONTH_NAMES[month - 1]} {year} — {displayedRows.length} of {grid.rows.length} eligible employee(s)</CardTitle>
              <CardDescription>
                Click any day cell to mark/change attendance. Scroll right to see all days.
                {filtersActive && ' Filtered/sorted via the "Employee filters" bar above.'}
              </CardDescription>
            </CardHeader>
            <CardContent>
              <Table>
                <THead>
                  <TR>
                    <TH className="sticky left-0 bg-secondary/60">Employee</TH>
                    {grid.days.map((d) => <TH key={d} className="text-center">{d}</TH>)}
                    <TH className="text-center">Total</TH>
                    <TH className="text-center">Present</TH>
                    <TH className="text-center">WO</TH>
                    <TH className="text-center">Rest (R)</TH>
                    <TH className="text-center">Absent</TH>
                    <TH className="text-center">EL</TH>
                    <TH className="text-center">Suspended</TH>
                    <TH className="text-center">LOP</TH>
                  </TR>
                </THead>
                <TBody>
                  {displayedRows.map((row) => (
                    <TR key={row.employee_id}>
                      <TD className="sticky left-0 whitespace-nowrap bg-card font-medium">
                        {row.employee_code} · {row.name}
                      </TD>
                      {grid.days.map((d) => {
                        const dateStr = `${year}-${String(month).padStart(2, '0')}-${String(d).padStart(2, '0')}`
                        const value = row.statuses[dateStr] || ''
                        const emp = employeeOf(row)
                        const active = isDateInWindow(emp, dateStr)
                        return (
                          <TD key={d} className="p-1 text-center">
                            <select
                              value={value}
                              onChange={(e) => {
                                if (!active) return
                                updateCell(row.employee_id, dateStr, e.target.value)
                              }}
                              disabled={!active}
                              className={`h-7 w-12 rounded border-0 text-center text-[11px] font-semibold focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/40 ${STATUS_META[value].className} ${!active ? 'cursor-not-allowed opacity-60 bg-muted text-muted-foreground' : ''}`}
                              title={active ? '' : 'Attendance is disabled outside the employee\'s join/leave window'}
                              aria-disabled={!active}
                              onMouseDown={(e) => {
                                if (!active) e.preventDefault()
                              }}
                              onKeyDown={(e) => {
                                if (!active) e.preventDefault()
                              }}
                              onClick={(e) => {
                                if (!active) e.preventDefault()
                              }}
                            >
                              {STATUS_OPTIONS.map((opt) => <option key={opt} value={opt}>{opt || '-'}</option>)}
                            </select>
                          </TD>
                        )
                      })}
                      <TD className="text-center font-mono-num font-semibold">{row.total}</TD>
                      <TD className="text-center font-mono-num">{row.present}</TD>
                      <TD className="text-center font-mono-num text-slate-600">{row.week_offs}</TD>
                      <TD className="text-center font-mono-num text-cyan-700">{row.rest_days}</TD>
                      <TD className="text-center font-mono-num text-red-700">{row.absent}</TD>
                      <TD className="text-center font-mono-num text-purple-700">{row.el}</TD>
                      <TD className="text-center font-mono-num text-orange-700">{row.suspended ?? 0}</TD>
                      <TD className="text-center font-mono-num font-semibold text-amber-700">{row.lop}</TD>
                    </TR>
                  ))}
                  {grid.rows.length === 0 && (
                    <TR><TD colSpan={grid.days.length + 9} className="py-8 text-center text-muted-foreground">No employees are eligible for this period.</TD></TR>
                  )}
                  {grid.rows.length > 0 && displayedRows.length === 0 && (
                    <TR><TD colSpan={grid.days.length + 9} className="py-8 text-center text-muted-foreground">No eligible employees match the current filters.</TD></TR>
                  )}
                  {displayedRows.length > 0 && (
                    <TR className="border-t-2 border-border bg-secondary/50 font-semibold hover:bg-secondary/50">
                      <TD className="sticky left-0 bg-secondary/50">Total ({displayedRows.length} employee(s))</TD>
                      {grid.days.map((d) => <TD key={d}></TD>)}
                      <TD className="text-center font-mono-num">{sumField(displayedRows, 'total')}</TD>
                      <TD className="text-center font-mono-num">{sumField(displayedRows, 'present')}</TD>
                      <TD className="text-center font-mono-num">{sumField(displayedRows, 'week_offs')}</TD>
                      <TD className="text-center font-mono-num">{sumField(displayedRows, 'rest_days')}</TD>
                      <TD className="text-center font-mono-num">{sumField(displayedRows, 'absent')}</TD>
                      <TD className="text-center font-mono-num">{sumField(displayedRows, 'el')}</TD>
                      <TD className="text-center font-mono-num text-orange-700">{sumField(displayedRows, 'suspended')}</TD>
                      <TD className="text-center font-mono-num text-amber-700">{sumField(displayedRows, 'lop')}</TD>
                    </TR>
                  )}
                </TBody>
              </Table>
            </CardContent>
          </Card>
        </div>
      )}
    </div>
  )
}

function sumField(rows, field) {
  return Math.round(rows.reduce((sum, r) => sum + (r[field] || 0), 0) * 100) / 100
}
