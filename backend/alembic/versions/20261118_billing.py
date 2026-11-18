"""Subscription checkout and transactional credit accounting."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
revision = '20261118_billing'
down_revision = '20261110_geo_webmaster'
branch_labels = None
depends_on = None

def common():
    return [sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
            sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now())]

def company():
    return sa.Column('company_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('companies.id'), nullable=False)

def upgrade():
    op.create_table('payment_orders', *common(), company(),
        sa.Column('created_by', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('order_no', sa.String(32), nullable=False),
        sa.Column('idempotency_key', sa.String(64), nullable=False),
        sa.Column('channel', sa.String(16), nullable=False),
        sa.Column('plan_code', sa.String(30), nullable=False),
        sa.Column('plan_snapshot', sa.JSON(), nullable=False),
        sa.Column('amount_fen', sa.Integer(), nullable=False),
        sa.Column('status', sa.String(24), nullable=False),
        sa.Column('code_url', sa.Text(), nullable=True),
        sa.Column('provider_transaction_id', sa.String(100), nullable=True),
        sa.Column('merchant_snapshot', sa.JSON(), nullable=False),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('paid_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('error_message', sa.String(300), nullable=True),
        sa.UniqueConstraint('channel', 'provider_transaction_id', name='uq_payment_provider_transaction'),
        sa.UniqueConstraint('company_id', 'idempotency_key', name='uq_payment_company_request'))
    op.create_index('ix_payment_orders_order_no', 'payment_orders', ['order_no'], unique=True)
    for column in ('company_id', 'status'):
        op.create_index('ix_payment_orders_' + column, 'payment_orders', [column])
    op.create_table('subscription_periods', *common(), company(),
        sa.Column('order_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('payment_orders.id'), nullable=False, unique=True),
        sa.Column('plan_code', sa.String(30), nullable=False),
        sa.Column('plan_name', sa.String(60), nullable=False),
        sa.Column('rates', sa.JSON(), nullable=False),
        sa.Column('starts_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('ends_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('included_units', sa.BigInteger(), nullable=False),
        sa.Column('used_units', sa.BigInteger(), nullable=False),
        sa.Column('reserved_units', sa.BigInteger(), nullable=False))
    for column in ('company_id', 'starts_at', 'ends_at'):
        op.create_index('ix_subscription_periods_' + column, 'subscription_periods', [column])
    op.create_table('ai_usage_ledger', *common(), company(),
        sa.Column('period_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('subscription_periods.id'), nullable=True),
        sa.Column('usage_key', sa.String(100), nullable=False, unique=True),
        sa.Column('kind', sa.String(20), nullable=False),
        sa.Column('status', sa.String(20), nullable=False),
        sa.Column('reserved_units', sa.BigInteger(), nullable=False),
        sa.Column('charged_units', sa.BigInteger(), nullable=False),
        sa.Column('cost_micro_yuan', sa.BigInteger(), nullable=False),
        sa.Column('input_tokens', sa.BigInteger(), nullable=False),
        sa.Column('output_tokens', sa.BigInteger(), nullable=False),
        sa.Column('video_milliseconds', sa.BigInteger(), nullable=False),
        sa.Column('rates', sa.JSON(), nullable=False),
        sa.Column('note', sa.String(250), nullable=True))
    op.create_index('ix_ai_usage_ledger_company_id', 'ai_usage_ledger', ['company_id'])

def downgrade():
    op.drop_table('ai_usage_ledger')
    op.drop_table('subscription_periods')
    op.drop_table('payment_orders')
