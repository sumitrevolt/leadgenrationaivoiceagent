"""add billing tables

Revision ID: 003_add_billing_tables
Create Date: 2026-01-04

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers
revision = '003_add_billing_tables'
down_revision = '002_add_users'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create enum types
    op.execute("CREATE TYPE paymentgateway AS ENUM ('stripe', 'razorpay')")
    op.execute("CREATE TYPE subscriptionstatus AS ENUM ('trial', 'active', 'past_due', 'cancelled', 'paused', 'expired')")
    op.execute("CREATE TYPE paymentstatus AS ENUM ('pending', 'processing', 'completed', 'failed', 'refunded', 'partially_refunded', 'cancelled')")
    op.execute("CREATE TYPE invoicestatus AS ENUM ('draft', 'open', 'paid', 'void', 'uncollectible')")
    op.execute("CREATE TYPE billingcycle AS ENUM ('monthly', 'quarterly', 'yearly')")
    op.execute("CREATE TYPE pricingplanmodel AS ENUM ('subscription', 'per_lead', 'hybrid')")
    
    # Create subscriptions table
    op.create_table(
        'subscriptions',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('client_id', sa.String(36), sa.ForeignKey('clients.id'), nullable=False, index=True),
        sa.Column('user_id', sa.String(36), sa.ForeignKey('users.id'), nullable=True),
        
        # Plan details
        sa.Column('plan_id', sa.String(50), nullable=False, index=True),
        sa.Column('plan_name', sa.String(100), nullable=False),
        sa.Column('pricing_model', sa.Enum('subscription', 'per_lead', 'hybrid', name='pricingplanmodel'), 
                  default='subscription'),
        
        # Status
        sa.Column('status', sa.Enum('trial', 'active', 'past_due', 'cancelled', 'paused', 'expired', 
                                    name='subscriptionstatus'), default='trial', nullable=False, index=True),
        sa.Column('billing_cycle', sa.Enum('monthly', 'quarterly', 'yearly', name='billingcycle'), 
                  default='monthly'),
        
        # Gateway references
        sa.Column('payment_gateway', sa.Enum('stripe', 'razorpay', name='paymentgateway'), nullable=True),
        sa.Column('stripe_subscription_id', sa.String(255), unique=True, nullable=True, index=True),
        sa.Column('stripe_customer_id', sa.String(255), nullable=True, index=True),
        sa.Column('razorpay_subscription_id', sa.String(255), unique=True, nullable=True, index=True),
        sa.Column('razorpay_customer_id', sa.String(255), nullable=True),
        
        # Pricing
        sa.Column('base_price', sa.Numeric(12, 2), default=0),
        sa.Column('currency', sa.String(3), default='INR'),
        
        # Dates
        sa.Column('started_at', sa.DateTime, default=sa.func.now()),
        sa.Column('trial_ends_at', sa.DateTime, nullable=True),
        sa.Column('current_period_start', sa.DateTime, nullable=True),
        sa.Column('current_period_end', sa.DateTime, nullable=True),
        sa.Column('cancelled_at', sa.DateTime, nullable=True),
        sa.Column('ended_at', sa.DateTime, nullable=True),
        
        # Usage tracking
        sa.Column('calls_used', sa.Integer, default=0),
        sa.Column('calls_limit', sa.Integer, default=0),
        sa.Column('leads_generated', sa.Integer, default=0),
        sa.Column('leads_limit', sa.Integer, default=0),
        sa.Column('appointments_booked', sa.Integer, default=0),
        
        # Balance
        sa.Column('balance', sa.Numeric(12, 2), default=0),
        
        # Extra data
        sa.Column('extra_data', sa.JSON, default=dict),
        sa.Column('cancel_reason', sa.Text, nullable=True),
        
        # Timestamps
        sa.Column('created_at', sa.DateTime, default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime, default=sa.func.now(), onupdate=sa.func.now()),
    )
    
    # Create invoices table (before payments due to FK)
    op.create_table(
        'invoices',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('client_id', sa.String(36), sa.ForeignKey('clients.id'), nullable=False, index=True),
        sa.Column('subscription_id', sa.String(36), sa.ForeignKey('subscriptions.id'), nullable=True, index=True),
        
        # Invoice number
        sa.Column('invoice_number', sa.String(50), unique=True, nullable=False, index=True),
        
        # External references
        sa.Column('stripe_invoice_id', sa.String(255), unique=True, nullable=True),
        sa.Column('razorpay_invoice_id', sa.String(255), unique=True, nullable=True),
        
        # Status
        sa.Column('status', sa.Enum('draft', 'open', 'paid', 'void', 'uncollectible', name='invoicestatus'),
                  default='draft', nullable=False, index=True),
        
        # Billing period
        sa.Column('billing_period_start', sa.DateTime, nullable=True),
        sa.Column('billing_period_end', sa.DateTime, nullable=True),
        
        # Amounts
        sa.Column('subtotal', sa.Numeric(12, 2), default=0),
        sa.Column('discount_amount', sa.Numeric(12, 2), default=0),
        sa.Column('discount_percentage', sa.Numeric(5, 2), default=0),
        sa.Column('tax_amount', sa.Numeric(12, 2), default=0),
        sa.Column('tax_rate', sa.Numeric(5, 2), default=18),
        sa.Column('total', sa.Numeric(12, 2), default=0),
        sa.Column('amount_paid', sa.Numeric(12, 2), default=0),
        sa.Column('amount_due', sa.Numeric(12, 2), default=0),
        sa.Column('currency', sa.String(3), default='INR'),
        
        # Line items
        sa.Column('line_items', sa.JSON, default=list),
        sa.Column('usage_summary', sa.JSON, default=dict),
        
        # PDF
        sa.Column('pdf_url', sa.String(500), nullable=True),
        sa.Column('hosted_invoice_url', sa.String(500), nullable=True),
        
        # Customer details
        sa.Column('customer_name', sa.String(255), nullable=True),
        sa.Column('customer_email', sa.String(255), nullable=True),
        sa.Column('customer_address', sa.JSON, default=dict),
        sa.Column('customer_gstin', sa.String(20), nullable=True),
        
        # Dates
        sa.Column('invoice_date', sa.DateTime, default=sa.func.now()),
        sa.Column('due_date', sa.DateTime, nullable=True),
        sa.Column('paid_at', sa.DateTime, nullable=True),
        sa.Column('voided_at', sa.DateTime, nullable=True),
        
        # Notes
        sa.Column('notes', sa.Text, nullable=True),
        sa.Column('footer', sa.Text, nullable=True),
        
        # Timestamps
        sa.Column('created_at', sa.DateTime, default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime, default=sa.func.now(), onupdate=sa.func.now()),
    )
    
    # Create payments table
    op.create_table(
        'payments',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('client_id', sa.String(36), sa.ForeignKey('clients.id'), nullable=False, index=True),
        sa.Column('subscription_id', sa.String(36), sa.ForeignKey('subscriptions.id'), nullable=True, index=True),
        sa.Column('invoice_id', sa.String(36), sa.ForeignKey('invoices.id'), nullable=True),
        
        # Gateway info
        sa.Column('payment_gateway', sa.Enum('stripe', 'razorpay', name='paymentgateway'), nullable=False),
        sa.Column('gateway_payment_id', sa.String(255), unique=True, nullable=False, index=True),
        sa.Column('gateway_order_id', sa.String(255), nullable=True),
        
        # Amount
        sa.Column('amount', sa.Numeric(12, 2), nullable=False),
        sa.Column('currency', sa.String(3), default='INR'),
        sa.Column('amount_refunded', sa.Numeric(12, 2), default=0),
        
        # Status
        sa.Column('status', sa.Enum('pending', 'processing', 'completed', 'failed', 'refunded', 
                                    'partially_refunded', 'cancelled', name='paymentstatus'),
                  default='pending', nullable=False, index=True),
        
        # Payment method
        sa.Column('payment_method_type', sa.String(50)),
        sa.Column('payment_method_last4', sa.String(4), nullable=True),
        sa.Column('payment_method_brand', sa.String(50), nullable=True),
        
        # Description
        sa.Column('description', sa.String(500), nullable=True),
        
        # Error handling
        sa.Column('failure_code', sa.String(100), nullable=True),
        sa.Column('failure_message', sa.Text, nullable=True),
        
        # Data
        sa.Column('gateway_response', sa.JSON, default=dict),
        sa.Column('extra_data', sa.JSON, default=dict),
        
        # Receipt
        sa.Column('receipt_url', sa.String(500), nullable=True),
        sa.Column('receipt_number', sa.String(100), nullable=True),
        
        # Timestamps
        sa.Column('created_at', sa.DateTime, default=sa.func.now(), index=True),
        sa.Column('updated_at', sa.DateTime, default=sa.func.now(), onupdate=sa.func.now()),
        sa.Column('completed_at', sa.DateTime, nullable=True),
        sa.Column('refunded_at', sa.DateTime, nullable=True),
    )
    
    # Create payment_methods table
    op.create_table(
        'payment_methods',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('client_id', sa.String(36), sa.ForeignKey('clients.id'), nullable=False, index=True),
        
        # Gateway references
        sa.Column('payment_gateway', sa.Enum('stripe', 'razorpay', name='paymentgateway'), nullable=False),
        sa.Column('gateway_payment_method_id', sa.String(255), unique=True, nullable=False),
        sa.Column('stripe_customer_id', sa.String(255), nullable=True),
        sa.Column('razorpay_customer_id', sa.String(255), nullable=True),
        
        # Method type
        sa.Column('type', sa.String(50), nullable=False),
        
        # Card details (masked)
        sa.Column('card_brand', sa.String(50), nullable=True),
        sa.Column('card_last4', sa.String(4), nullable=True),
        sa.Column('card_exp_month', sa.Integer, nullable=True),
        sa.Column('card_exp_year', sa.Integer, nullable=True),
        sa.Column('card_funding', sa.String(20), nullable=True),
        
        # UPI details
        sa.Column('upi_id_masked', sa.String(100), nullable=True),
        
        # Netbanking
        sa.Column('bank_name', sa.String(100), nullable=True),
        
        # Status
        sa.Column('is_default', sa.Boolean, default=False),
        sa.Column('is_active', sa.Boolean, default=True),
        
        # Billing address
        sa.Column('billing_name', sa.String(255), nullable=True),
        sa.Column('billing_address', sa.JSON, default=dict),
        
        # Timestamps
        sa.Column('created_at', sa.DateTime, default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime, default=sa.func.now(), onupdate=sa.func.now()),
    )
    
    # Create usage_records table
    op.create_table(
        'usage_records',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('client_id', sa.String(36), sa.ForeignKey('clients.id'), nullable=False, index=True),
        sa.Column('subscription_id', sa.String(36), sa.ForeignKey('subscriptions.id'), nullable=True, index=True),
        
        # Usage date
        sa.Column('usage_date', sa.DateTime, nullable=False, index=True),
        
        # Usage metrics
        sa.Column('calls_made', sa.Integer, default=0),
        sa.Column('calls_connected', sa.Integer, default=0),
        sa.Column('call_duration_seconds', sa.Integer, default=0),
        sa.Column('qualified_leads', sa.Integer, default=0),
        sa.Column('appointments_booked', sa.Integer, default=0),
        
        # Billing
        sa.Column('billable_amount', sa.Numeric(12, 2), default=0),
        sa.Column('billed', sa.Boolean, default=False),
        sa.Column('billed_at', sa.DateTime, nullable=True),
        sa.Column('invoice_id', sa.String(36), nullable=True),
        
        # Timestamps
        sa.Column('created_at', sa.DateTime, default=sa.func.now()),
    )
    
    # Create indexes
    op.create_index('ix_subscriptions_status_client', 'subscriptions', ['status', 'client_id'])
    op.create_index('ix_payments_status_created', 'payments', ['status', 'created_at'])
    op.create_index('ix_invoices_status_due', 'invoices', ['status', 'due_date'])
    op.create_index('ix_usage_records_client_date', 'usage_records', ['client_id', 'usage_date'])


def downgrade() -> None:
    # Drop indexes
    op.drop_index('ix_usage_records_client_date')
    op.drop_index('ix_invoices_status_due')
    op.drop_index('ix_payments_status_created')
    op.drop_index('ix_subscriptions_status_client')
    
    # Drop tables
    op.drop_table('usage_records')
    op.drop_table('payment_methods')
    op.drop_table('payments')
    op.drop_table('invoices')
    op.drop_table('subscriptions')
    
    # Drop enum types
    op.execute('DROP TYPE IF EXISTS pricingplanmodel')
    op.execute('DROP TYPE IF EXISTS billingcycle')
    op.execute('DROP TYPE IF EXISTS invoicestatus')
    op.execute('DROP TYPE IF EXISTS paymentstatus')
    op.execute('DROP TYPE IF EXISTS subscriptionstatus')
    op.execute('DROP TYPE IF EXISTS paymentgateway')
