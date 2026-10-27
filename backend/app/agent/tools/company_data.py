from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy.orm import Session

from app.models.company import Company


async def get_company_profile(company_id: uuid.UUID, db: Session) -> dict[str, Any]:
    """
    Retrieve company profile data for use in agent workflows.
    Returns structured company info including brand positioning, goals, and products.
    """
    company = (
        db.query(Company)
        .filter(Company.id == company_id, Company.is_deleted == False)
        .first()
    )
    if not company:
        return {"error": f"Company {company_id} not found"}

    from app.models.company import CompanyProduct, Store

    products = (
        db.query(CompanyProduct)
        .filter(CompanyProduct.company_id == company_id, CompanyProduct.is_active == True)
        .all()
    )
    stores = (
        db.query(Store)
        .filter(Store.company_id == company_id, Store.is_active == True)
        .all()
    )

    return {
        "id": str(company.id),
        "name": company.name,
        "industry": company.industry,
        "brand_positioning": company.brand_positioning,
        "target_audience": company.target_audience,
        "brand_voice": company.brand_voice,
        "business_goals": company.business_goals,
        "marketing_forbidden_words": company.marketing_forbidden_words or [],
        "faq": company.faq or [],
        "products": [
            {
                "id": str(p.id),
                "name": p.name,
                "description": p.description,
                "price_info": p.price_info,
                "features": p.features or [],
            }
            for p in products
        ],
        "stores": [
            {
                "id": str(s.id),
                "name": s.name,
                "address": s.address,
            }
            for s in stores
        ],
    }
