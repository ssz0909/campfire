"""publishing platform connections and jobs"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
revision = '20261016_publishing'; down_revision = '3bb0d4b94bcb'; branch_labels = None; depends_on = None

def upgrade():
    op.create_table('platform_connections',
        sa.Column('company_id', postgresql.UUID(as_uuid=True), nullable=False), sa.Column('platform', sa.String(40), nullable=False),
        sa.Column('status', sa.String(30), nullable=False), sa.Column('account_id', sa.String(255)), sa.Column('account_name', sa.String(255)),
        sa.Column('encrypted_credentials', sa.Text()), sa.Column('scopes', sa.JSON()), sa.Column('last_error', sa.Text()), sa.Column('authorized_at', sa.DateTime(timezone=True)),
        sa.Column('id', postgresql.UUID(as_uuid=True), server_default=sa.text('gen_random_uuid()'), nullable=False), sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False), sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['company_id'], ['companies.id']), sa.PrimaryKeyConstraint('id'), sa.UniqueConstraint('company_id','platform',name='uq_platform_connection_company_platform'))
    op.create_index('ix_platform_connections_company_id','platform_connections',['company_id'])
    op.create_table('publish_jobs',
        sa.Column('company_id', postgresql.UUID(as_uuid=True), nullable=False), sa.Column('platform_connection_id', postgresql.UUID(as_uuid=True), nullable=False), sa.Column('requested_by', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('task_id', postgresql.UUID(as_uuid=True)), sa.Column('video_project_id', postgresql.UUID(as_uuid=True)), sa.Column('asset_id', postgresql.UUID(as_uuid=True)), sa.Column('title', sa.String(255), nullable=False), sa.Column('description', sa.Text()), sa.Column('media_url', sa.Text()), sa.Column('status', sa.String(30), nullable=False), sa.Column('provider_post_id', sa.String(255)), sa.Column('provider_url', sa.Text()), sa.Column('metrics', sa.JSON()), sa.Column('error_message', sa.Text()),
        sa.Column('id', postgresql.UUID(as_uuid=True), server_default=sa.text('gen_random_uuid()'), nullable=False), sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False), sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['company_id'], ['companies.id']), sa.ForeignKeyConstraint(['platform_connection_id'], ['platform_connections.id']), sa.ForeignKeyConstraint(['requested_by'], ['users.id']), sa.ForeignKeyConstraint(['task_id'], ['operation_tasks.id']), sa.ForeignKeyConstraint(['video_project_id'], ['video_projects.id']), sa.ForeignKeyConstraint(['asset_id'], ['assets.id']), sa.PrimaryKeyConstraint('id'))
    op.create_index('ix_publish_jobs_company_id','publish_jobs',['company_id']); op.create_index('ix_publish_jobs_status','publish_jobs',['status'])

def downgrade():
    op.drop_table('publish_jobs'); op.drop_table('platform_connections')
