"""Independent publishing accounts and browser profiles."""
from alembic import op
import sqlalchemy as sa
revision = '20261030_matrix_accounts'
down_revision = '20261029_video_music'
branch_labels = None
depends_on = None


def upgrade():
    op.drop_constraint('uq_platform_connection_company_platform', 'platform_connections', type_='unique')
    op.add_column('platform_connections', sa.Column('label', sa.String(100), nullable=True))
    op.add_column('platform_connections', sa.Column('session_profile', sa.String(36), nullable=True))
    # Freeze existing task targets before new same-platform accounts can be added.
    connection = op.get_bind()
    accounts = sa.table('platform_connections', sa.column('id', sa.Uuid()), sa.column('company_id', sa.Uuid()), sa.column('platform', sa.String()))
    tasks = sa.table('operation_tasks', sa.column('id', sa.Uuid()), sa.column('company_id', sa.Uuid()), sa.column('input_params', sa.JSON()))
    by_company = {}
    for row in connection.execute(sa.select(accounts)).mappings():
        by_company.setdefault(str(row['company_id']), {})[row['platform']] = str(row['id'])
    for row in connection.execute(sa.select(tasks)).mappings():
        params = row['input_params'] or {}
        platforms = params.get('publish_platforms', [])
        known = by_company.get(str(row['company_id']), {})
        if 'publish_account_ids' not in params and platforms and all(p in known for p in platforms):
            connection.execute(tasks.update().where(tasks.c.id == row['id']).values(input_params={**params, 'publish_account_ids':[known[p] for p in platforms]}))
    # Existing connections keep NULL profile: their original browser directory stays valid.


def downgrade():
    # Fail if multiple accounts exist; never silently discard accounts or history.
    connection = op.get_bind()
    duplicates = connection.execute(sa.text('SELECT 1 FROM platform_connections GROUP BY company_id, platform HAVING COUNT(*) > 1 LIMIT 1')).first()
    if duplicates:
        raise RuntimeError('Remove additional platform accounts before downgrading')
    op.drop_column('platform_connections', 'session_profile')
    op.drop_column('platform_connections', 'label')
    op.create_unique_constraint('uq_platform_connection_company_platform', 'platform_connections', ['company_id', 'platform'])
