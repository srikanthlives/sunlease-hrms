import { useEffect, useState } from 'react'
import { useAuth } from '../auth/AuthContext'
import api from '../api'
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '../components/ui/card'
import { Users, FileStack, PlayCircle, FileText } from 'lucide-react'
import { formatCurrency, MONTH_NAMES } from '../lib/utils'
import { Link } from 'react-router-dom'

export default function Dashboard() {
  const { user } = useAuth()
  const [employees, setEmployees] = useState([])
  const [templates, setTemplates] = useState([])
  const [payslips, setPayslips] = useState([])
  const now = new Date()
  const month = now.getMonth() + 1
  const year = now.getFullYear()

  useEffect(() => {
    if (user?.role !== 'employee') {
      api.get('/employees').then((r) => setEmployees(r.data)).catch(() => {})
      api.get('/templates').then((r) => setTemplates(r.data)).catch(() => {})
    }
    api.get('/payroll/payslips', { params: { month, year } }).then((r) => setPayslips(r.data)).catch(() => {})
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [user])

  return (
    <div className="space-y-8">
      <div>
        <h1 className="font-display text-2xl font-semibold">Welcome back, {user?.username}</h1>
        <p className="text-sm text-muted-foreground">{MONTH_NAMES[month - 1]} {year} · signed in as {user?.role?.replace('_', ' ')}</p>
      </div>

      {user?.role !== 'employee' && (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
          <SummaryCard icon={Users} label="Employees" value={employees.length} />
          <SummaryCard icon={FileStack} label="Salary Templates" value={templates.length} />
          <SummaryCard icon={FileText} label={`Payslips this month`} value={payslips.length} />
        </div>
      )}

      <Card>
        <CardHeader>
          <CardTitle>Quick actions</CardTitle>
          <CardDescription>Jump straight into the most common tasks.</CardDescription>
        </CardHeader>
        <CardContent className="flex flex-wrap gap-3">
          {user?.role !== 'employee' ? (
            <>
              <QuickLink to="/run-payroll" icon={PlayCircle} label="Run this month's payroll" />
              <QuickLink to="/variable-upload" icon={FileStack} label="Upload monthly variables" />
              <QuickLink to="/attendance" icon={Users} label="Update attendance" />
            </>
          ) : (
            <QuickLink to="/payslips" icon={FileText} label="View my payslips" />
          )}
        </CardContent>
      </Card>

      {user?.role === 'employee' && (
        <Card>
          <CardHeader>
            <CardTitle>This month's pay</CardTitle>
          </CardHeader>
          <CardContent>
            {payslips[0] ? (
              <p className="font-mono-num text-3xl font-semibold text-primary">₹ {formatCurrency(payslips[0].net_pay)}</p>
            ) : (
              <p className="text-sm text-muted-foreground">Payslip for this month hasn't been generated yet.</p>
            )}
          </CardContent>
        </Card>
      )}
    </div>
  )
}

function SummaryCard({ icon: Icon, label, value }) {
  return (
    <Card>
      <CardContent className="flex items-center gap-4 py-5">
        <div className="rounded-md bg-primary/10 p-3">
          <Icon className="h-5 w-5 text-primary" />
        </div>
        <div>
          <p className="text-2xl font-semibold font-mono-num">{value}</p>
          <p className="text-xs text-muted-foreground">{label}</p>
        </div>
      </CardContent>
    </Card>
  )
}

function QuickLink({ to, icon: Icon, label }) {
  return (
    <Link
      to={to}
      className="flex items-center gap-2 rounded-md border border-border bg-secondary/40 px-4 py-2.5 text-sm font-medium hover:bg-secondary"
    >
      <Icon className="h-4 w-4" /> {label}
    </Link>
  )
}
