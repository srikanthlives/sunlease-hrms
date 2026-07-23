import { useState, useEffect } from 'react'
import { NavLink, useNavigate } from 'react-router-dom'
import { useAuth } from '../auth/AuthContext'
import { usePeriod } from '../period/PeriodContext'
import { useEmployeeFilters, distinctDepartmentsAndLocations } from '../period/EmployeeFilterContext'
import api from '../api'
import {
  LayoutDashboard, Users, FileStack, CalendarCheck, Upload,
  Receipt, PlayCircle, FileText, LogOut, Landmark, CalendarDays, Wallet, ChevronDown,
  CreditCard, Building2, ShieldCheck, LayoutGrid, CalendarPlus, Filter, RotateCcw,
} from 'lucide-react'
import { cn, MONTH_NAMES } from '../lib/utils'
import logo from '../logo/sunlease.png'

const NAV = [
  { type: 'link', to: '/', label: 'Dashboard', icon: LayoutDashboard, roles: ['admin', 'payroll_processor', 'employee'] },
  { type: 'link', to: '/employees', label: 'Employees', icon: Users, roles: ['admin', 'payroll_processor'] },
  { type: 'link', to: '/templates', label: 'Salary Templates', icon: FileStack, roles: ['admin'] },
  {
    type: 'group', label: 'Attendance', icon: CalendarCheck, roles: ['admin', 'payroll_processor'],
    items: [
      { to: '/attendance', label: 'Monthly Grid', icon: LayoutGrid, end: true },
      { to: '/attendance/upload', label: 'Bulk Upload', icon: Upload },
      { to: '/attendance/el-balances', label: 'Earned Leave Balances', icon: CalendarPlus },
    ],
  },
  {
    type: 'group', label: 'Payroll', icon: Wallet, roles: ['admin', 'payroll_processor'],
    items: [
      { to: '/variable-upload', label: 'Monthly Variables', icon: Upload },
      { to: '/adhoc', label: 'Ad-hoc Entries', icon: Receipt },
      { to: '/run-payroll', label: 'Run Payroll', icon: PlayCircle },
      { to: '/salary-payments', label: 'Salary Payments', icon: CreditCard },
      { to: '/bank-payments', label: 'Bank Payments', icon: Building2 },
      { to: '/payslips', label: 'All Payslips', icon: FileText },
    ],
  },
  { type: 'link', to: '/compliance', label: 'Compliances', icon: ShieldCheck, roles: ['admin', 'payroll_processor'] },
  { type: 'link', to: '/payslips', label: 'My Payslips', icon: FileText, roles: ['employee'] },
]

export default function Layout({ children }) {
  const { user, logout } = useAuth()
  const navigate = useNavigate()
  const { month, year, setMonth, setYear } = usePeriod()
  const { sortBy, deptFilter, locFilter, setSortBy, setDeptFilter, setLocFilter, resetFilters } = useEmployeeFilters()
  const [collapsedGroups, setCollapsedGroups] = useState(new Set())
  const [employees, setEmployees] = useState([])
  const items = NAV.filter((n) => n.roles.includes(user?.role))
  const isStaff = user?.role === 'admin' || user?.role === 'payroll_processor'

  useEffect(() => {
    if (isStaff) {
      api.get('/employees').then((r) => setEmployees(r.data)).catch(() => {})
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [user])

  const { departments, locations } = distinctDepartmentsAndLocations(employees)
  const filtersActive = sortBy !== 'default' || deptFilter || locFilter

  function toggleGroup(label) {
    setCollapsedGroups((prev) => {
      const next = new Set(prev)
      next.has(label) ? next.delete(label) : next.add(label)
      return next
    })
  }

  const linkClass = ({ isActive }) =>
    cn(
      'flex items-center gap-2.5 rounded-md px-3 py-2 text-sm font-medium transition-colors',
      isActive ? 'bg-primary text-primary-foreground' : 'text-foreground/80 hover:bg-muted'
    )

  return (
    <div className="flex min-h-screen">
      <aside className="flex w-64 flex-col border-r border-border bg-card">
        <div className="flex items-center gap-2 border-b border-border px-5 py-4">
          <img src={logo} alt="Sunlease" className="h-12 w-auto max-w-[140px] object-contain" />
          <div className="min-w-0" text-center>
            <p className="text-[11px] text-muted-foreground">HR Management System</p>
          </div>
        </div>
        <nav className="flex-1 space-y-1 p-3">
          {items.map((item, i) => {
            if (item.type === 'group') {
              const isCollapsed = collapsedGroups.has(item.label)
              return (
                <div key={item.label + i}>
                  <button
                    onClick={() => toggleGroup(item.label)}
                    className="flex w-full items-center gap-2.5 rounded-md px-3 py-2 text-sm font-medium text-foreground/80 hover:bg-muted"
                  >
                    <item.icon className="h-4 w-4" />
                    <span className="flex-1 text-left">{item.label}</span>
                    <ChevronDown className={cn('h-4 w-4 transition-transform', isCollapsed && '-rotate-90')} />
                  </button>
                  {!isCollapsed && (
                    <div className="ml-3 mt-0.5 space-y-1 border-l border-border pl-3">
                      {item.items.map((sub, j) => (
                        <NavLink key={sub.to + j} to={sub.to} end={!!sub.end} className={linkClass}>
                          <sub.icon className="h-4 w-4" />
                          {sub.label}
                        </NavLink>
                      ))}
                    </div>
                  )}
                </div>
              )
            }
            return (
              <NavLink key={item.to + item.label + i} to={item.to} end={item.to === '/'} className={linkClass}>
                <item.icon className="h-4 w-4" />
                {item.label}
              </NavLink>
            )
          })}
        </nav>
        <div className="border-t border-border p-3">
          <div className="mb-2 rounded-md bg-muted px-3 py-2">
            <p className="text-sm font-medium">{user?.username}</p>
            <p className="text-[11px] uppercase tracking-wide text-muted-foreground">{user?.role?.replace('_', ' ')}</p>
          </div>
          <button
            onClick={() => { logout(); navigate('/login') }}
            className="flex w-full items-center gap-2 rounded-md px-3 py-2 text-sm text-muted-foreground hover:bg-muted hover:text-foreground"
          >
            <LogOut className="h-4 w-4" /> Sign out
          </button>
        </div>
      </aside>
      <div className="flex flex-1 flex-col overflow-hidden">
        <div className="flex items-center justify-end gap-2 border-b border-border bg-card px-6 py-2.5">
          <CalendarDays className="h-4 w-4 text-muted-foreground" />
          <span className="text-xs font-medium text-muted-foreground">Payroll period</span>
          <select
            value={month}
            onChange={(e) => setMonth(e.target.value)}
            className="h-8 rounded-md border border-border bg-white px-2 text-sm shadow-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/40"
          >
            {MONTH_NAMES.map((m, i) => <option key={m} value={i + 1}>{m}</option>)}
          </select>
          <input
            type="number"
            value={year}
            onChange={(e) => setYear(e.target.value)}
            className="h-8 w-20 rounded-md border border-border bg-white px-2 text-sm shadow-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/40"
          />
          <span className="hidden text-[11px] text-muted-foreground sm:inline">applies to Attendance, Variables, Ad-hoc, Payroll & Payslips</span>
        </div>
        {isStaff && (
          <div className="flex flex-wrap items-center gap-2 border-b border-border bg-card px-6 py-2.5">
            <Filter className="h-4 w-4 text-muted-foreground" />
            <span className="text-xs font-medium text-muted-foreground">Employee filters</span>
            <select
              value={sortBy}
              onChange={(e) => setSortBy(e.target.value)}
              className="h-8 rounded-md border border-border bg-white px-2 text-sm shadow-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/40"
            >
              <option value="default">Sort: default</option>
              <option value="name_asc">Name (A–Z)</option>
              <option value="name_desc">Name (Z–A)</option>
              <option value="code_asc">Code (A–Z)</option>
              <option value="code_desc">Code (Z–A)</option>
            </select>
            <select
              value={deptFilter}
              onChange={(e) => setDeptFilter(e.target.value)}
              className="h-8 rounded-md border border-border bg-white px-2 text-sm shadow-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/40"
            >
              <option value="">All departments</option>
              {departments.map((d) => <option key={d} value={d}>{d}</option>)}
            </select>
            <select
              value={locFilter}
              onChange={(e) => setLocFilter(e.target.value)}
              className="h-8 rounded-md border border-border bg-white px-2 text-sm shadow-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/40"
            >
              <option value="">All locations</option>
              {locations.map((l) => <option key={l} value={l}>{l}</option>)}
            </select>
            {filtersActive && (
              <button
                onClick={resetFilters}
                className="inline-flex h-8 items-center gap-1 rounded-md border border-border px-2 text-xs font-medium text-muted-foreground hover:bg-muted"
              >
                <RotateCcw className="h-3.5 w-3.5" /> Reset
              </button>
            )}
            <span className="hidden text-[11px] text-muted-foreground md:inline">applies to Employees, Run Payroll, Attendance, Salary Payments & All Payslips</span>
          </div>
        )}
        <main className="flex-1 overflow-y-auto p-8">{children}</main>
      </div>
    </div>
  )
}
