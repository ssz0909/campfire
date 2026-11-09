"""Public business sites, templates, immutable versions and first-party events."""
from alembic import op
from app.models.geo import GeoSite, GeoSlug, GeoVersion, GeoTemplate, GeoEvent, GeoDaily, GeoVisitor, GeoFeedback
revision = '20261109_geo'
down_revision = '20261105_music_disabled'
branch_labels = None
depends_on = None

def upgrade():
    for model in (GeoSite, GeoSlug, GeoVersion, GeoTemplate, GeoEvent, GeoDaily, GeoVisitor, GeoFeedback):
        model.__table__.create(op.get_bind(), checkfirst=True)
    table = GeoTemplate.__table__
    op.bulk_insert(table, [
        {'code':'generic','name':'通用企业','revision':1,'config':{'intro':'企业介绍','services':'产品与服务','faq':'常见问题','accent':'#c05929'}},
        {'code':'travel','name':'酒旅','revision':1,'config':{'intro':'目的地与体验','services':'住宿与游览服务','faq':'出行与服务问答','accent':'#28766a'}},
    ])

def downgrade():
    for model in (GeoFeedback, GeoVisitor, GeoDaily, GeoEvent, GeoVersion, GeoSlug, GeoSite, GeoTemplate):
        model.__table__.drop(op.get_bind())
