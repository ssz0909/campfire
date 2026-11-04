"""Persist quality/cost generation strategy; existing projects stay quality."""
from alembic import op
import sqlalchemy as sa

revision = '20261104_video_mode'
down_revision = '20261030_matrix_accounts'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('video_projects', sa.Column('generation_mode', sa.String(20), nullable=False, server_default='quality'))


def downgrade():
    op.drop_column('video_projects', 'generation_mode')
