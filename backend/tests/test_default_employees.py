from app.models.digital_employee import DigitalEmployee
from app.schemas.company import CompanyCreate
from app.services.company_service import CompanyService
from app.services.digital_employee_service import DigitalEmployeeService
from tests.conftest import create_test_company, create_test_user


ROLES = {
    "operations_manager", "content_planner", "video_producer",
    "data_analyst", "operations_assistant",
}


def test_new_company_has_five_employees(db):
    owner = create_test_user(db, email="defaults-new@example.com")
    company = CompanyService(db).create_company(owner.id, CompanyCreate(name="Defaults"))
    employees = db.query(DigitalEmployee).filter_by(company_id=company.id).all()
    assert {employee.role_title for employee in employees} == ROLES
    assert len(employees) == 5
    assert all(employee.created_by == owner.id for employee in employees)


def test_existing_company_backfill_is_idempotent_and_keeps_edits(db):
    owner = create_test_user(db, email="defaults-old@example.com")
    company = create_test_company(db, owner, slug="defaults-old")
    service = DigitalEmployeeService(db)
    employees = service.list_employees(company.id)
    ids = {employee.id for employee in employees}
    employees[0].name = "企业专属助理"
    employees[0].is_active = False
    db.commit()
    again = service.list_employees(company.id)
    assert len(again) == 5
    assert {employee.id for employee in again} == ids
    assert employees[0].name == "企业专属助理"
    assert employees[0].is_active is False


def test_backfill_keeps_custom_employees_and_tenant_isolation(db):
    owner = create_test_user(db, email="defaults-custom@example.com")
    first = create_test_company(db, owner, slug="defaults-first")
    second = create_test_company(db, owner, slug="defaults-second")
    custom = DigitalEmployee(company_id=first.id, created_by=owner.id,
                             name="活动助理", role_title="custom")
    db.add(custom)
    db.commit()
    service = DigitalEmployeeService(db)
    assert len(service.list_employees(first.id)) == 6
    assert not db.query(DigitalEmployee).filter_by(company_id=second.id).count()
    assert len(service.list_employees(second.id)) == 5


def test_deleted_default_is_not_recreated(db):
    owner = create_test_user(db, email="defaults-delete@example.com")
    company = create_test_company(db, owner, slug="defaults-delete")
    service = DigitalEmployeeService(db)
    employee = service.list_employees(company.id)[0]
    service.delete_employee(company.id, employee.id)
    assert len(service.list_employees(company.id)) == 4
    assert db.query(DigitalEmployee).filter_by(company_id=company.id).count() == 5
