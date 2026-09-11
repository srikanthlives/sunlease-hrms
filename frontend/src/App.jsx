import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { AuthProvider, useAuth } from "./context/AuthContext";
import { GlobalFilterProvider } from "./context/GlobalFilterContext";
import MainLayout from "./layouts/MainLayout";
import Login from "./pages/Login";
import Employees from "./pages/Employees";
import EmployeeWizard from "./pages/EmployeeWizard";
import EmployeeProfile from "./pages/EmployeeProfile";
import CompaniesMaster from "./pages/org/CompaniesMaster";
import CostCentersMaster from "./pages/org/CostCentersMaster";
import DepartmentsMaster from "./pages/org/DepartmentsMaster";
import ProjectsMaster from "./pages/org/ProjectsMaster";
import EmployeeCategoriesMaster from "./pages/org/EmployeeCategoriesMaster";
import WorkLocationsMaster from "./pages/org/WorkLocationsMaster";
import DesignationsMaster from "./pages/org/DesignationsMaster";
import EmployeeTypesMaster from "./pages/org/EmployeeTypesMaster";
import DocumentTypesMaster from "./pages/org/DocumentTypesMaster";
import AuditLogs from "./pages/AuditLogs";
import UsersAdmin from "./pages/UsersAdmin";
import RolesPermissions from "./pages/RolesPermissions";
import ApprovalRules from "./pages/ApprovalRules";
import DocumentRequirementsConfig from "./pages/DocumentRequirementsConfig";
import DrivingLicenceRequirementsConfig from "./pages/DrivingLicenceRequirementsConfig";
import ChangeRequests from "./pages/ChangeRequests";
import Shifts from "./pages/Shifts";
import Roster from "./pages/Roster";
import AttendanceRegister from "./pages/AttendanceRegister";
import AttendanceGrid from "./pages/AttendanceGrid";
import AttendanceApprovals from "./pages/AttendanceApprovals";
import LeaveTypesConfig from "./pages/LeaveTypesConfig";
import LeaveEligibilityConfig from "./pages/LeaveEligibilityConfig";
import HolidayCalendar from "./pages/HolidayCalendar";
import LeaveApplications from "./pages/LeaveApplications";
import LeaveApprovals from "./pages/LeaveApprovals";
import SalaryComponents from "./pages/SalaryComponents";
import SalaryTemplates from "./pages/SalaryTemplates";
import SalaryStructure from "./pages/SalaryStructure";
import StatutoryConfigPage from "./pages/StatutoryConfigPage";
import RunPayroll from "./pages/RunPayroll";
import PayrollRegister from "./pages/PayrollRegister";
import AdhocPayEntries from "./pages/AdhocPayEntries";
import FullFinalSettlement from "./pages/FullFinalSettlement";
import ComplianceOverview from "./pages/ComplianceOverview";
import ComplianceRecords from "./pages/ComplianceRecords";

function ProtectedRoute({ children }) {
  const { user, loading } = useAuth();
  if (loading) return <div className="min-h-screen flex items-center justify-center text-ink/40 text-sm">Loading…</div>;
  if (!user) return <Navigate to="/login" replace />;
  return children;
}

export default function App() {
  return (
    <BrowserRouter>
      <AuthProvider>
        <Routes>
          <Route path="/login" element={<Login />} />
          <Route
            path="/"
            element={
              <ProtectedRoute>
                <GlobalFilterProvider>
                  <MainLayout />
                </GlobalFilterProvider>
              </ProtectedRoute>
            }
          >
            <Route index element={<Navigate to="/employees" replace />} />
            <Route path="employees" element={<Employees />} />
            <Route path="employees/:episodeId/wizard" element={<EmployeeWizard />} />
            <Route path="employees/:episodeId" element={<EmployeeProfile />} />
            <Route path="organization" element={<Navigate to="/organization/companies" replace />} />
            <Route path="organization/companies" element={<CompaniesMaster />} />
            <Route path="organization/cost-centers" element={<CostCentersMaster />} />
            <Route path="organization/departments" element={<DepartmentsMaster />} />
            <Route path="organization/projects" element={<ProjectsMaster />} />
            <Route path="organization/categories" element={<EmployeeCategoriesMaster />} />
            <Route path="organization/work-locations" element={<WorkLocationsMaster />} />
            <Route path="organization/designations" element={<DesignationsMaster />} />
            <Route path="organization/employee-types" element={<EmployeeTypesMaster />} />
            <Route path="organization/document-types" element={<DocumentTypesMaster />} />
            <Route path="change-requests" element={<ChangeRequests />} />
            <Route path="shifts" element={<Shifts />} />
            <Route path="roster" element={<Roster />} />
            <Route path="attendance" element={<AttendanceRegister />} />
            <Route path="attendance-grid" element={<AttendanceGrid />} />
            <Route path="attendance-approvals" element={<AttendanceApprovals />} />
            <Route path="leave-types" element={<LeaveTypesConfig />} />
            <Route path="leave-eligibility" element={<LeaveEligibilityConfig />} />
            <Route path="holiday-calendar" element={<HolidayCalendar />} />
            <Route path="leave-applications" element={<LeaveApplications />} />
            <Route path="leave-approvals" element={<LeaveApprovals />} />
            <Route path="salary-components" element={<SalaryComponents />} />
            <Route path="salary-templates" element={<SalaryTemplates />} />
            <Route path="salary-structure" element={<SalaryStructure />} />
            <Route path="statutory-config" element={<StatutoryConfigPage />} />
            <Route path="run-payroll" element={<RunPayroll />} />
            <Route path="payroll-register" element={<PayrollRegister />} />
            <Route path="adhoc-pay-entries" element={<AdhocPayEntries />} />
            <Route path="full-final-settlement" element={<FullFinalSettlement />} />
            <Route path="compliance-overview" element={<ComplianceOverview />} />
            <Route path="compliance-records" element={<ComplianceRecords />} />
            <Route path="admin/users" element={<UsersAdmin />} />
            <Route path="admin/roles-permissions" element={<RolesPermissions />} />
            <Route path="admin/approval-rules" element={<ApprovalRules />} />
            <Route path="admin/document-requirements" element={<DocumentRequirementsConfig />} />
            <Route path="admin/driving-licence-requirements" element={<DrivingLicenceRequirementsConfig />} />
            <Route path="admin/audit-logs" element={<AuditLogs />} />
          </Route>
        </Routes>
      </AuthProvider>
    </BrowserRouter>
  );
}
