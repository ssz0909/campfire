"""Webmaster page/day performance reports."""
from alembic import op
from app.models.geo import GeoSearchDaily
revision = '20261110_geo_webmaster'
down_revision = '20261109_geo'
branch_labels = None
depends_on = None

def upgrade():
    GeoSearchDaily.__table__.create(op.get_bind(), checkfirst=True)

def downgrade():
    GeoSearchDaily.__table__.drop(op.get_bind())
