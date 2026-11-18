"""Available connectors by workspace industry; extend this registry for new providers."""
from app.services.industry_templates import ALIASES


CONNECTORS = (
    {
        'type': 'hotel',
        'provider': 'dingdanlaile',
        'name': '订单来了',
        'industries': ('travel',),
    },
)


def available_connectors(industry: str | None) -> list[dict]:
    code = (industry or '').strip()
    code = ALIASES.get(code, code)
    return [dict(item) for item in CONNECTORS if code in item['industries']]
