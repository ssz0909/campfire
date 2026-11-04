"""Retain raw model clips and configure cross-project reuse."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '20261104_clip_reuse'
down_revision = '20261104_video_mode'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('video_projects', sa.Column('reuse_policy', sa.String(20), nullable=False, server_default='fresh'))
    op.add_column('provider_tasks', sa.Column('raw_asset_id', postgresql.UUID(as_uuid=True), nullable=True))
    op.create_foreign_key('fk_provider_task_raw_asset', 'provider_tasks', 'assets', ['raw_asset_id'], ['id'])


def downgrade():
    op.drop_constraint('fk_provider_task_raw_asset', 'provider_tasks', type_='foreignkey')
    op.drop_column('provider_tasks', 'raw_asset_id')
    op.drop_column('video_projects', 'reuse_policy')
