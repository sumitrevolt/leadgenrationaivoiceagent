"""Add data credits tables

Revision ID: 004_add_data_credits
Revises: 003_add_billing_tables
Create Date: 2026-01-06

B2B Intelligence Platform - Credit-based billing system
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '004_add_data_credits'
down_revision = '003_add_billing_tables'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create data_credits table
    op.create_table(
        'data_credits',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('client_id', sa.String(36), sa.ForeignKey('clients.id'), nullable=False, unique=True),
        sa.Column('balance', sa.Integer(), default=0),
        sa.Column('lifetime_credits', sa.Integer(), default=0),
        sa.Column('used_credits', sa.Integer(), default=0),
        sa.Column('monthly_limit', sa.Integer(), default=0),
        sa.Column('monthly_used', sa.Integer(), default=0),
        sa.Column('last_used_at', sa.DateTime()),
        sa.Column('reset_at', sa.DateTime()),
        sa.Column('created_at', sa.DateTime(), default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), default=sa.func.now(), onupdate=sa.func.now()),
    )
    op.create_index('ix_data_credits_client', 'data_credits', ['client_id'])
    
    # Create credit_transactions table
    op.create_table(
        'credit_transactions',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('credit_account_id', sa.String(36), sa.ForeignKey('data_credits.id'), nullable=False),
        sa.Column('client_id', sa.String(36), sa.ForeignKey('clients.id'), nullable=False),
        sa.Column('transaction_type', sa.String(50), nullable=False),
        sa.Column('amount', sa.Integer(), nullable=False),
        sa.Column('balance_after', sa.Integer(), nullable=False),
        sa.Column('description', sa.String(500)),
        sa.Column('reference_id', sa.String(100)),
        sa.Column('usage_type', sa.String(50)),
        sa.Column('created_at', sa.DateTime(), default=sa.func.now()),
    )
    op.create_index('ix_credit_tx_client', 'credit_transactions', ['client_id'])
    op.create_index('ix_credit_tx_type', 'credit_transactions', ['transaction_type'])
    op.create_index('ix_credit_tx_created', 'credit_transactions', ['created_at'])
    
    # Create api_keys table
    op.create_table(
        'api_keys',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('client_id', sa.String(36), sa.ForeignKey('clients.id'), nullable=False),
        sa.Column('name', sa.String(100), nullable=False),
        sa.Column('key_prefix', sa.String(10), nullable=False),
        sa.Column('key_hash', sa.String(64), nullable=False, unique=True),
        sa.Column('scopes', sa.Text()),
        sa.Column('rate_limit_per_minute', sa.Integer(), default=60),
        sa.Column('rate_limit_per_day', sa.Integer(), default=10000),
        sa.Column('is_active', sa.Integer(), default=1),
        sa.Column('last_used_at', sa.DateTime()),
        sa.Column('created_at', sa.DateTime(), default=sa.func.now()),
        sa.Column('expires_at', sa.DateTime()),
    )
    op.create_index('ix_api_keys_client', 'api_keys', ['client_id'])
    op.create_index('ix_api_keys_key_hash', 'api_keys', ['key_hash'])
    
    # Create api_usage_logs table
    op.create_table(
        'api_usage_logs',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('client_id', sa.String(36), sa.ForeignKey('clients.id'), nullable=False),
        sa.Column('api_key_id', sa.String(36), sa.ForeignKey('api_keys.id')),
        sa.Column('usage_type', sa.String(50), nullable=False),
        sa.Column('credits_consumed', sa.Integer(), nullable=False),
        sa.Column('endpoint', sa.String(200)),
        sa.Column('method', sa.String(10)),
        sa.Column('query_params', sa.Text()),
        sa.Column('result_count', sa.Integer(), default=0),
        sa.Column('response_time_ms', sa.Integer()),
        sa.Column('created_at', sa.DateTime(), default=sa.func.now()),
    )
    op.create_index('ix_api_usage_client', 'api_usage_logs', ['client_id'])
    op.create_index('ix_api_usage_type', 'api_usage_logs', ['usage_type'])
    op.create_index('ix_api_usage_created', 'api_usage_logs', ['created_at'])
    op.create_index('ix_api_usage_api_key', 'api_usage_logs', ['api_key_id'])


def downgrade() -> None:
    op.drop_table('api_usage_logs')
    op.drop_table('api_keys')
    op.drop_table('credit_transactions')
    op.drop_table('data_credits')
