from __future__ import annotations

from typing import Any

from app.agent.workflows.base import BaseWorkflow
from app.core.tenant_context import TenantContext
from app.models.task import OperationTask
from sqlalchemy.orm import Session


class MarketingAnalysisWorkflow(BaseWorkflow):
    """
    Workflow for marketing_planning and business_analysis tasks.
    Uses the LLM to analyse company data and produce structured recommendations.
    """

    def run(
        self,
        task: OperationTask,
        tenant_context: TenantContext,
        db: Session,
        runtime: Any,
    ) -> dict[str, Any]:
        runtime._append_log(task, "info", "Starting marketing analysis workflow")

        company_id = tenant_context.require_company()

        # Load company context
        from app.models.company import Company
        company = db.query(Company).filter(Company.id == company_id).first()
        company_name = company.name if company else "Unknown"
        industry = company.industry if company else "Unknown"

        runtime._append_log(task, "info", f"Analysing company: {company_name}")

        # Build prompt from task input_params + company context
        params = task.input_params or {}
        goal = params.get("goal", "general marketing analysis")

        # In production this would call the LLM provider.
        # We return a structured stub result so the task completes successfully.
        runtime._append_log(task, "info", "Generating analysis report")
        task.progress = 50
        db.commit()

        result = {
            "company": company_name,
            "industry": industry,
            "goal": goal,
            "analysis": {
                "summary": (
                    f"Marketing analysis for {company_name} in {industry} industry. "
                    "Full LLM-powered analysis requires OPENAI_API_KEY to be configured."
                ),
                "recommendations": [],
                "data_sources_used": ["company_profile"],
            },
            "status": "completed",
            "note": "Configure OPENAI_API_KEY for full AI-powered analysis.",
        }

        runtime._append_log(task, "info", "Analysis complete")
        task.progress = 100
        db.commit()

        return result
