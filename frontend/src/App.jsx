import { Routes, Route, Navigate } from 'react-router-dom'
import { useAuth } from './auth/AuthContext'
import Layout from './components/Layout'
import Login from './pages/Login'
import Dashboard from './pages/Dashboard'
import Employees from './pages/Employees'
import Templates from './pages/Templates'
import AttendanceGrid from './pages/AttendanceGrid'
import AttendanceUpload from './pages/AttendanceUpload'
import AttendanceELBalances from './pages/AttendanceELBalances'
import VariableUpload from './pages/VariableUpload'
import AdhocEntries from './pages/AdhocEntries'
import RunPayroll from './pages/RunPayroll'
import Payslips from './pages/Payslips'
import PayslipDetail from './pages/PayslipDetail'
import CTCDetail from './pages/CTCDetail'
import SalaryPayments from './pages/SalaryPayments'
import BankPayments from './pages/BankPayments'
import Compliance from './pages/Compliance'

function Protected({ roles, children }) {
  const { user } = useAuth()
  if (!user) return <Navigate to="/login" replace />
  if (roles && !roles.includes(user.role)) return <Navigate to="/" replace />
  return <Layout>{children}</Layout>
}

export default function App() {
  const { user } = useAuth()

  return (
    <Routes>
      <Route path="/login" element={user ? <Navigate to="/" replace /> : <Login />} />

      <Route path="/" element={<Protected><Dashboard /></Protected>} />
      <Route path="/employees" element={<Protected roles={['admin', 'payroll_processor']}><Employees /></Protected>} />
      <Route path="/templates" element={<Protected roles={['admin']}><Templates /></Protected>} />
      <Route path="/attendance" element={<Protected roles={['admin', 'payroll_processor']}><AttendanceGrid /></Protected>} />
      <Route path="/attendance/upload" element={<Protected roles={['admin', 'payroll_processor']}><AttendanceUpload /></Protected>} />
      <Route path="/attendance/el-balances" element={<Protected roles={['admin', 'payroll_processor']}><AttendanceELBalances /></Protected>} />
      <Route path="/variable-upload" element={<Protected roles={['admin', 'payroll_processor']}><VariableUpload /></Protected>} />
      <Route path="/adhoc" element={<Protected roles={['admin', 'payroll_processor']}><AdhocEntries /></Protected>} />
      <Route path="/run-payroll" element={<Protected roles={['admin', 'payroll_processor']}><RunPayroll /></Protected>} />
      <Route path="/salary-payments" element={<Protected roles={['admin', 'payroll_processor']}><SalaryPayments /></Protected>} />
      <Route path="/bank-payments" element={<Protected roles={['admin', 'payroll_processor']}><BankPayments /></Protected>} />
      <Route path="/compliance" element={<Protected roles={['admin', 'payroll_processor']}><Compliance /></Protected>} />
      <Route path="/payslips" element={<Protected><Payslips /></Protected>} />
      <Route path="/payslips/:id" element={<Protected><PayslipDetail /></Protected>} />
      <Route path="/payslips/:id/ctc" element={<Protected roles={['admin', 'payroll_processor']}><CTCDetail /></Protected>} />

      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  )
}
