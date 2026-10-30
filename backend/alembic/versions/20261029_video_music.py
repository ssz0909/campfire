"""Allow tenant-owned background music on video projects."""
from alembic import op
import sqlalchemy as sa

revision = '20261029_video_music'
down_revision = '20261022_video_assets'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('video_projects', sa.Column('music_asset_id', sa.Uuid(), nullable=True))
    op.create_foreign_key('fk_video_music_asset', 'video_projects', 'assets', ['music_asset_id'], ['id'])
    op.add_column('video_projects', sa.Column('music_volume', sa.Numeric(4, 3), nullable=False, server_default='0.25'))


def downgrade():
    op.drop_column('video_projects', 'music_volume')
    op.drop_constraint('fk_video_music_asset', 'video_projects', type_='foreignkey')
    op.drop_column('video_projects', 'music_asset_id')
