"""Persist silent video preference without changing existing projects."""
from alembic import op
import sqlalchemy as sa

revision = '20261105_music_disabled'
down_revision = '20261104_industry_templates'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('video_projects', sa.Column('music_disabled', sa.Boolean(), nullable=False, server_default=sa.false()))


def downgrade():
    op.drop_column('video_projects', 'music_disabled')
