"""Seed initial roles + permission grants + an HR Admin user + a minimal
org structure + a testable HR_STAFF/APPROVER pair with Cost Center scope,
so the RBAC and approval-routing flow (blueprint §15/§18) is exercisable
immediately after a fresh seed. Safe to re-run (idempotent)."""
from app.core.security import hash_password
from app.db.session import SessionLocal
from app.migrate import migrate
from app.models.models import (
    Role, User, RolePermission, UserCostCenterScope, ApprovalRule,
    Company, CostCenter, Department, Project, EmployeeCategory,
    WorkLocation, Designation, EmployeeType, DocumentType, DocumentRequirement,
    DrivingLicenceRequirement,
)
from app.models.enums import RoleName, Permission, TransactionType

migrate(verbose=True)
db = SessionLocal()

try:
    role_map = {}
    for name in RoleName.ALL:
        role = db.query(Role).filter(Role.name == name).first()
        if not role:
            role = Role(name=name, description=f"{name.replace('_', ' ').title()} role")
            db.add(role)
            db.flush()
        role_map[name] = role

    # Permission grants (HR_ADMIN is never granted rows - it bypasses
    # checks entirely, see core/deps.py::require_permission).
    for role_name, codes in Permission.DEFAULTS.items():
        role_id = role_map[role_name].id
        existing = {g.permission_code for g in db.query(RolePermission).filter(RolePermission.role_id == role_id).all()}
        for code in codes:
            if code not in existing:
                db.add(RolePermission(role_id=role_id, permission_code=code))
    db.flush()

    if not db.query(User).filter(User.username == "admin").first():
        db.add(User(
            username="admin", email="admin@example.com", full_name="HR Administrator",
            hashed_password=hash_password("Admin@123"), role_id=role_map[RoleName.HR_ADMIN].id,
        ))
    db.flush()

    if not db.query(Company).filter(Company.name == "Sunlease Renewables").first():
        db.add(Company(name="Sunlease Renewables"))
    db.flush()
    company = db.query(Company).filter(Company.name == "Sunlease Renewables").first()

    if not db.query(CostCenter).filter(CostCenter.code == "CC-PDY").first():
        db.add(CostCenter(company_id=company.id, name="Puducherry", code="CC-PDY"))
    db.flush()
    cost_center = db.query(CostCenter).filter(CostCenter.code == "CC-PDY").first()

    if not db.query(Department).filter(Department.code == "DEPT-OPS").first():
        db.add(Department(cost_center_id=cost_center.id, name="Operations", code="DEPT-OPS"))

    for cat_name in ["Staff", "Worker", "Driver"]:
        if not db.query(EmployeeCategory).filter(EmployeeCategory.name == cat_name).first():
            db.add(EmployeeCategory(name=cat_name))

    if not db.query(Project).filter(Project.code == "PRJ-BUS1").first():
        db.add(Project(cost_center_id=cost_center.id, name="Bus Route 1", code="PRJ-BUS1"))
    db.flush()
    project = db.query(Project).filter(Project.code == "PRJ-BUS1").first()

    if not db.query(WorkLocation).filter(WorkLocation.code == "WL-PDY-DEPOT").first():
        db.add(WorkLocation(project_id=project.id, name="Puducherry Depot", code="WL-PDY-DEPOT"))

    for desig_name in ["Bus Driver", "Conductor", "Site Supervisor", "HR Executive"]:
        if not db.query(Designation).filter(Designation.name == desig_name).first():
            db.add(Designation(name=desig_name))

    for type_name in ["Permanent", "Contract", "Probation", "Apprentice"]:
        if not db.query(EmployeeType).filter(EmployeeType.name == type_name).first():
            db.add(EmployeeType(name=type_name))

    for doc_name in ["Aadhaar Card", "PAN Card", "Photo", "Educational Certificate", "Driving Licence", "Medical Fitness Certificate"]:
        if not db.query(DocumentType).filter(DocumentType.name == doc_name).first():
            db.add(DocumentType(name=doc_name))

    db.flush()

    # Document Configuration rules (blueprint §14) - Employee Type > Category
    # > Designation priority, demonstrated with a real conflict: Contract
    # staff have Aadhaar/PAN optional company-wide, but a Permanent Bus
    # Driver both requires them (Employee Type wins) and additionally needs
    # a Driving Licence (Category) and Medical Fitness Certificate (Designation).
    doc_types = {d.name: d.id for d in db.query(DocumentType).all()}
    permanent_type = db.query(EmployeeType).filter(EmployeeType.name == "Permanent").first()
    driver_category = db.query(EmployeeCategory).filter(EmployeeCategory.name == "Driver").first()
    bus_driver_designation = db.query(Designation).filter(Designation.name == "Bus Driver").first()

    def ensure_requirement(document_type_id, employee_type_id=None, employee_category_id=None, designation_id=None, is_mandatory=True):
        existing = db.query(DocumentRequirement).filter(
            DocumentRequirement.document_type_id == document_type_id,
            DocumentRequirement.employee_type_id == employee_type_id,
            DocumentRequirement.employee_category_id == employee_category_id,
            DocumentRequirement.designation_id == designation_id,
        ).first()
        if not existing:
            db.add(DocumentRequirement(
                document_type_id=document_type_id, employee_type_id=employee_type_id,
                employee_category_id=employee_category_id, designation_id=designation_id,
                is_mandatory=is_mandatory,
            ))

    # Company-wide baseline: Aadhaar/PAN optional for everyone. Photo used
    # to be a generic document requirement but now lives on Personal
    # Information (Basic Details) instead - see Employee.photo_object_key
    # / routers/employees.py::upload_photo - so its old DocumentType/
    # DocumentRequirement rows are retired (deactivated, not deleted) here
    # for both fresh seeds and databases that seeded it previously.
    ensure_requirement(doc_types["Aadhaar Card"], is_mandatory=False)
    ensure_requirement(doc_types["PAN Card"], is_mandatory=False)
    photo_doc_type = db.query(DocumentType).filter(DocumentType.name == "Photo").first()
    if photo_doc_type:
        photo_doc_type.is_active = False
        db.query(DocumentRequirement).filter(DocumentRequirement.document_type_id == photo_doc_type.id).update({"is_active": False})

    if permanent_type:
        ensure_requirement(doc_types["Aadhaar Card"], employee_type_id=permanent_type.id, is_mandatory=True)
        ensure_requirement(doc_types["PAN Card"], employee_type_id=permanent_type.id, is_mandatory=True)
        ensure_requirement(doc_types["Educational Certificate"], employee_type_id=permanent_type.id, is_mandatory=True)
    if driver_category:
        ensure_requirement(doc_types["Driving Licence"], employee_category_id=driver_category.id, is_mandatory=True)
    if bus_driver_designation:
        ensure_requirement(doc_types["Medical Fitness Certificate"], designation_id=bus_driver_designation.id, is_mandatory=True)

    # Driving Licence wizard step: shown only for the Driver category (not
    # a document upload - a data-entry form, see licence_service.py).
    if driver_category and not db.query(DrivingLicenceRequirement).filter(
        DrivingLicenceRequirement.employee_category_id == driver_category.id
    ).first():
        db.add(DrivingLicenceRequirement(employee_category_id=driver_category.id, is_required=True))

    db.flush()

    # HR_STAFF and APPROVER test users, both scoped to the seeded Cost
    # Center, so scoped visibility + routed approval + change-request
    # review are all testable end to end right after a fresh seed.
    if not db.query(User).filter(User.username == "hrstaff").first():
        db.add(User(
            username="hrstaff", email="hrstaff@example.com", full_name="HR Staff User",
            hashed_password=hash_password("HrStaff@123"), role_id=role_map[RoleName.HR_STAFF].id,
        ))
    if not db.query(User).filter(User.username == "approver").first():
        db.add(User(
            username="approver", email="approver@example.com", full_name="Approver User",
            hashed_password=hash_password("Approver@123"), role_id=role_map[RoleName.APPROVER].id,
        ))
    db.flush()

    hrstaff_user = db.query(User).filter(User.username == "hrstaff").first()
    approver_user = db.query(User).filter(User.username == "approver").first()
    for u in (hrstaff_user, approver_user):
        if not db.query(UserCostCenterScope).filter(
            UserCostCenterScope.user_id == u.id, UserCostCenterScope.cost_center_id == cost_center.id
        ).first():
            db.add(UserCostCenterScope(user_id=u.id, cost_center_id=cost_center.id))

    # Global fallback approval rule: any APPROVER may approve new employee
    # creation when no more specific Cost Center/Category rule matches.
    if not db.query(ApprovalRule).filter(
        ApprovalRule.transaction_type == TransactionType.EMPLOYEE_CREATION,
        ApprovalRule.cost_center_id.is_(None), ApprovalRule.employee_category_id.is_(None),
    ).first():
        db.add(ApprovalRule(
            transaction_type=TransactionType.EMPLOYEE_CREATION,
            approver_role=RoleName.APPROVER,
            cost_center_id=None, employee_category_id=None,
        ))

    db.commit()
    print("Seed complete.")
    print("Logins: admin / Admin@123, hrstaff / HrStaff@123, approver / Approver@123")
finally:
    db.close()
