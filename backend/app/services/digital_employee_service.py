from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models.digital_employee import DigitalEmployee
from app.schemas.digital_employee import DigitalEmployeeCreate, DigitalEmployeeUpdate


class DigitalEmployeeService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def list_employees(self, company_id: uuid.UUID) -> list[DigitalEmployee]:
        self.ensure_default_employees(company_id)
        return (
            self.db.query(DigitalEmployee)
            .filter(
                DigitalEmployee.company_id == company_id,
                DigitalEmployee.is_deleted == False,
            )
            .all()
        )

    def ensure_default_employees(
        self, company_id: uuid.UUID, created_by: uuid.UUID | None = None, *, commit: bool = True,
    ) -> None:
        """Provision the five roles defined in the v1 product specification."""
        from app.models.company import Company
        # Serialize first visits from multiple tabs and provision in the company transaction.
        company = self.db.query(Company).filter(Company.id == company_id).with_for_update().first()
        if company is None:
            return
        created_by = created_by or company.owner_id
        existing = self.db.query(DigitalEmployee).filter(DigitalEmployee.company_id == company_id).all()
        defaults = [
            ("AI 运营总管", "operations_manager", "分析经营状况，汇总问题并生成运营任务建议。"),
            ("AI 内容策划", "content_planner", "分析目标客群，制定营销主题，生成文案与视频创意。"),
            ("AI 视频制作员", "video_producer", "生成脚本、分镜、视频任务并跟踪制作过程。"),
            ("AI 数据分析员", "data_analyst", "分析订单、入住、内容数据和可获得的转化信息。"),
            ("AI 运营助理", "operations_assistant", "汇总任务、提醒审批并输出经营日报。"),
        ]
        for role_title, role, description in defaults:
            employee_id = uuid.uuid5(company_id, f"default-employee:{role}")
            if any(e.id == employee_id or e.role_title in (role, role_title) for e in existing):
                continue
            self.db.add(DigitalEmployee(
                id=employee_id,
                company_id=company_id,
                created_by=created_by,
                name=role_title,
                role_title=role,
                role_description=description,
                work_goals=description,
                system_instructions=f"你是{role_title}，请遵守企业权限、预算和审批规则。",
                allowed_data_scopes=["company"],
                allowed_tools=[],
                allowed_actions=[],
                forbidden_actions=["未经审批发布内容", "绕过权限或预算限制"],
                business_rules=["仅访问所属企业数据", "发布内容和业务变更需人工审批"],
                max_task_budget_cents=500,
                max_iterations=10,
                approval_policy="moderate",
            ))
        if commit:
            self.db.commit()
        else:
            self.db.flush()

    def create_employee(
        self,
        company_id: uuid.UUID,
        created_by: uuid.UUID,
        data: DigitalEmployeeCreate,
    ) -> DigitalEmployee:
        employee = DigitalEmployee(
            company_id=company_id,
            created_by=created_by,
            **data.model_dump(),
        )
        self.db.add(employee)
        self.db.commit()
        self.db.refresh(employee)
        return employee

    def get_employee(
        self, company_id: uuid.UUID, employee_id: uuid.UUID
    ) -> DigitalEmployee:
        employee = (
            self.db.query(DigitalEmployee)
            .filter(
                DigitalEmployee.id == employee_id,
                DigitalEmployee.company_id == company_id,
                DigitalEmployee.is_deleted == False,
            )
            .first()
        )
        if not employee:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Digital employee not found",
            )
        return employee

    def update_employee(
        self,
        company_id: uuid.UUID,
        employee_id: uuid.UUID,
        data: DigitalEmployeeUpdate,
    ) -> DigitalEmployee:
        employee = self.get_employee(company_id, employee_id)
        for field, value in data.model_dump(exclude_unset=True).items():
            setattr(employee, field, value)
        self.db.commit()
        self.db.refresh(employee)
        return employee

    def delete_employee(
        self, company_id: uuid.UUID, employee_id: uuid.UUID
    ) -> None:
        employee = self.get_employee(company_id, employee_id)
        employee.is_deleted = True
        employee.deleted_at = datetime.now(timezone.utc)
        self.db.commit()

    def set_active(
        self,
        company_id: uuid.UUID,
        employee_id: uuid.UUID,
        is_active: bool,
    ) -> DigitalEmployee:
        employee = self.get_employee(company_id, employee_id)
        employee.is_active = is_active
        self.db.commit()
        self.db.refresh(employee)
        return employee
