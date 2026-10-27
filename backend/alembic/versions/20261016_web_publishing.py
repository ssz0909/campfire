"""Web-session publisher snapshots and approval identity."""
from alembic import op
import sqlalchemy as sa
revision = '20261016_web_publishing'
down_revision = '20261016_publishing'
branch_labels = None
depends_on = None

def upgrade():
    op.add_column('platform_connections', sa.Column('metrics_snapshot', sa.JSON(), nullable=True))
    op.add_column('publish_jobs', sa.Column('request_key', sa.String(100), nullable=True))
    op.add_column('publish_jobs', sa.Column('content_snapshot', sa.JSON(), nullable=True))
    op.add_column('publish_jobs', sa.Column('reviewed_by', sa.UUID(), sa.ForeignKey('users.id'), nullable=True))
    op.create_unique_constraint('uq_publish_request_key', 'publish_jobs', ['company_id', 'request_key'])

def downgrade():
    op.drop_constraint('uq_publish_request_key','publish_jobs',type_='unique')
    for column in ('reviewed_by','content_snapshot','request_key'):
        op.drop_column('publish_jobs',column)
    op.drop_column('platform_connections','metrics_snapshot')
