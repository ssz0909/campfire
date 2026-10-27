"""Attach selected source assets to video projects."""
from alembic import op
import sqlalchemy as sa

revision = '20261022_video_assets'
down_revision = '20261016_web_publishing'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('video_projects', sa.Column('selected_asset_ids', sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column('video_projects', 'selected_asset_ids')
