import { useEffect, useState } from 'react'
import api from '../api'
import { usePeriod } from '../period/PeriodContext'
import { useEmployeeFilters, applyEmployeeFilters } from '../period/EmployeeFilterContext'
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '../components/ui/card'
import { Button } from '../components/ui/button'
import { Table, THead, TBody, TR, TH, TD } from '../components/ui/table'
import { Badge } from '../components/ui/badge'
import { Alert } from '../components/ui/alert'
import { ExternalLink, Download, ShieldCheck } from 'lucide-react'
import { MONTH_NAMES } from '../lib/utils'

const EPFO_PORTAL = 'https://unifiedportal-mem.epfindia.gov.in/memberinterface/'
const ESIC_PORTAL = 'https://www.esic.gov.in/'

export default function Compliance() {
  const { month, year } = usePeriod()
  const filters = useEmployeeFilters()
  const [employees, setEmployees] = useState([])

  useEffect(() => {
    api.get('/employees/eligible', { params: { month, year } }).then((r) => setEmployees(r.data))
  }, [month, year])

  const displayedEmployees = applyEmployeeFilters(employees, filters, (e) => e)
  const filtersActive = filters.sortBy !== 'default' || filters.deptFilter || filters.locFilter

  const [downloadNote, setDownloadNote] = useState(null)

  async function downloadTemplate(kind) {
    const urls = {
      pf: '/pf-template', esi: '/esi-template', mediclaim: '/mediclaim-template',
    }
    const filenames = {
      pf: `PF_Contribution_Statement_${String(month).padStart(2, '0')}${year}.zip`,
      esi: `ESIC_MC_${String(month).padStart(2, '0')}${year}.xlsx`,
      mediclaim: `Mediclaim_Statement_${String(month).padStart(2, '0')}${year}.xlsx`,
    }
    setDownloadNote(null)
    const res = await api.get(`/compliance${urls[kind]}`, { params: { month, year }, responseType: 'blob' })
    const disposition = res.headers['content-disposition'] || ''
    const filenameMatch = disposition.match(/filename\s*=\s*"?([^";]+)"?/i)
    const url = window.URL.createObjectURL(new Blob([res.data]))
    const a = document.createElement('a')
    a.href = url
    a.download = filenameMatch?.[1] || filenames[kind]
    document.body.appendChild(a)
    a.click()
    a.remove()
    window.URL.revokeObjectURL(url)

    const skippedRaw = res.headers['x-skipped-no-esi-number']
    if (kind === 'esi' && skippedRaw) {
      setDownloadNote(`Skipped (no ESI number on file): ${decodeURIComponent(skippedRaw)}`)
    }
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="font-display text-2xl font-semibold">Compliances</h1>
        <p className="text-sm text-muted-foreground">
          PF (EPFO), ESI (ESIC), and Mediclaim identifiers for each employee, with quick links to the respective portals,
          and downloadable statements for that month's filing.
        </p>
      </div>

      <p className="text-sm font-medium text-muted-foreground">
        Period: <span className="text-foreground">{MONTH_NAMES[month - 1]} {year}</span>
        <span className="ml-1 text-xs">(change from the top bar)</span>
      </p>

      <Alert>
        The <b>ESI statement</b> fills the actual ESIC "Monthly Contribution" upload template — download and upload it
        to the ESIC portal as-is. The <b>PF</b> and <b>Mediclaim</b> statements are practical starting points built from
        payroll data (no official template on file for those yet) — EPFO's ECR format changes periodically, so verify
        column requirements against the current specification before filing those two.
      </Alert>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Download filing templates — {MONTH_NAMES[month - 1]} {year}</CardTitle>
        </CardHeader>
        <CardContent className="flex flex-wrap gap-3">
          <Button variant="outline" onClick={() => downloadTemplate('pf')}><Download className="h-4 w-4" /> PF statement</Button>
          <Button variant="outline" onClick={() => downloadTemplate('esi')}><Download className="h-4 w-4" /> ESI statement</Button>
          <Button variant="outline" onClick={() => downloadTemplate('mediclaim')}><Download className="h-4 w-4" /> Mediclaim statement</Button>
        </CardContent>
        {downloadNote && (
          <CardContent className="pt-0">
            <Alert variant="warning">{downloadNote}</Alert>
          </CardContent>
        )}
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-base flex items-center gap-2"><ShieldCheck className="h-4 w-4 text-primary" /> Employee compliance details</CardTitle>
          <CardDescription>
            Click a number to open the respective portal in a new tab. Showing {displayedEmployees.length} of {employees.length}.
            {filtersActive && ' Filtered/sorted via the "Employee filters" bar above.'}
          </CardDescription>
        </CardHeader>
        <CardContent>
          <Table>
            <THead><TR><TH>Code</TH><TH>Name</TH><TH>PF (UAN)</TH><TH>PF Elig</TH><TH>EPS Elig</TH><TH>ESI Elig</TH><TH>ESI Number</TH><TH>Mediclaim Elig</TH><TH>Mediclaim Policy No.</TH></TR></THead>
            <TBody>
              {displayedEmployees.map((emp) => (
                <TR key={emp.id}>
                  <TD className="font-mono-num">{emp.employee_code}</TD>
                  <TD>{emp.first_name} {emp.last_name}</TD>
                  <TD>
                    {emp.uan ? (
                      <a href={EPFO_PORTAL} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 font-mono-num text-primary underline">
                        {emp.uan} <ExternalLink className="h-3 w-3" />
                      </a>
                    ) : <Badge variant="muted">Not set</Badge>}
                  </TD>
                  <TD>{emp.pf_eligible ? <Badge variant="success">YES</Badge> : <Badge variant="muted">NO</Badge>}</TD>
                  <TD>{emp.eps_eligible ? <Badge variant="success">YES</Badge> : <Badge variant="muted">NO</Badge>}</TD>
                  <TD>{emp.esi_eligible ? <Badge variant="success">YES</Badge> : <Badge variant="muted">NO</Badge>}</TD>
                  <TD>
                    {emp.esi_number ? (
                      <a href={ESIC_PORTAL} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 font-mono-num text-primary underline">
                        {emp.esi_number} <ExternalLink className="h-3 w-3" />
                      </a>
                    ) : <Badge variant="muted">Not set</Badge>}
                  </TD>
                  <TD>{emp.mediclaim_eligible ? <Badge variant="success">YES</Badge> : <Badge variant="muted">NO</Badge>}</TD>
                  <TD className="font-mono-num">
                    {emp.mediclaim_policy_no || <Badge variant="muted">Not set</Badge>}
                  </TD>
                </TR>
              ))}
              {employees.length === 0 && (
                <TR><TD colSpan={5} className="py-8 text-center text-muted-foreground">No employees yet.</TD></TR>
              )}
              {employees.length > 0 && displayedEmployees.length === 0 && (
                <TR><TD colSpan={5} className="py-8 text-center text-muted-foreground">No employees match the current filters.</TD></TR>
              )}
            </TBody>
          </Table>
        </CardContent>
      </Card>
    </div>
  )
}
