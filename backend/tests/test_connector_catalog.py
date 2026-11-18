import pytest

from app.services.connector_catalog import available_connectors
from tests.conftest import auth_headers, create_test_company, create_test_user


@pytest.mark.parametrize('industry', ['travel', 'hotel', 'tourism', '酒店', '酒店与民宿', '酒旅', '景区'])
def test_travel_aliases(industry):
    assert [c['provider'] for c in available_connectors(industry)] == ['dingdanlaile']


@pytest.mark.parametrize('industry', [None, '', 'generic', 'retail', 'food', '新行业'])
def test_other_industries_have_no_hotel_connector(industry):
    assert available_connectors(industry) == []


def test_workspace_catalog_and_industry_changes(client, db, monkeypatch):
    from app.connectors.hotel.service import HotelConnectorService
    calls = []
    def summary(self):
        calls.append(True)
        return {'status': 'unconfigured'}
    monkeypatch.setattr(HotelConnectorService, 'masked_config_summary', summary)
    owner = create_test_user(db)
    company = create_test_company(db, owner)
    url = f'/api/v1/companies/{company.id}/connectors'
    headers = auth_headers(owner)
    company.industry = 'retail'; db.commit()
    assert client.get(url, headers=headers).json() == {'connectors': []}
    assert calls == []
    company.industry = 'travel'; db.commit()
    response = client.get(url, headers=headers)
    assert response.status_code == 200
    assert response.json()['connectors'][0]['provider'] == 'dingdanlaile'
    assert len(calls) == 1
    stranger = create_test_user(db, email='other-connector@example.test')
    assert client.get(url, headers=auth_headers(stranger)).status_code == 403
    assert client.get(url).status_code == 401
