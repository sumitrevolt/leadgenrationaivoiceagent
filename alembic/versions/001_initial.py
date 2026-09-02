"""Initial migration - Create all tables

Revision ID: 001_initial
Revises: 
Create Date: 2024-01-01 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '001_initial'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create clients table
    op.create_table(
        'clients',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('business_name', sa.String(255), nullable=False),
        sa.Column('business_type', sa.String(100)),
        sa.Column('industry', sa.String(100)),
        sa.Column('website', sa.String(255)),
        sa.Column('contact_name', sa.String(255), nullable=False),
        sa.Column('contact_email', sa.String(255), nullable=False, unique=True),
        sa.Column('contact_phone', sa.String(20), nullable=False),
        sa.Column('contact_designation', sa.String(100)),
        sa.Column('address', sa.Text),
        sa.Column('city', sa.String(100)),
        sa.Column('state', sa.String(100)),
        sa.Column('country', sa.String(100), default='India'),
        sa.Column('pincode', sa.String(10)),
        sa.Column('gst_number', sa.String(20)),
        sa.Column('plan', sa.String(20), default='starter'),
        sa.Column('status', sa.String(20), default='trial'),
        sa.Column('monthly_call_limit', sa.Integer, default=1000),
        sa.Column('monthly_lead_limit', sa.Integer, default=500),
        sa.Column('max_campaigns', sa.Integer, default=3),
        sa.Column('max_users', sa.Integer, default=2),
        sa.Column('calls_this_month', sa.Integer, default=0),
        sa.Column('leads_this_month', sa.Integer, default=0),
        sa.Column('active_campaigns', sa.Integer, default=0),
        sa.Column('billing_cycle_start', sa.DateTime),
        sa.Column('billing_cycle_end', sa.DateTime),
        sa.Column('next_billing_date', sa.DateTime),
        sa.Column('monthly_amount', sa.Integer, default=1500000),
        sa.Column('api_key', sa.String(64), unique=True),
        sa.Column('webhook_url', sa.String(500)),
        sa.Column('twilio_config', sa.Text),
        sa.Column('exotel_config', sa.Text),
        sa.Column('whatsapp_config', sa.Text),
        sa.Column('hubspot_config', sa.Text),
        sa.Column('zoho_config', sa.Text),
        sa.Column('sheets_config', sa.Text),
        sa.Column('caller_id_number', sa.String(20)),
        sa.Column('caller_id_name', sa.String(100)),
        sa.Column('preferred_voice', sa.String(50), default='ElevenLabs'),
        sa.Column('preferred_language', sa.String(20), default='hinglish'),
        sa.Column('notify_on_hot_lead', sa.Boolean, default=True),
        sa.Column('notify_on_appointment', sa.Boolean, default=True),
        sa.Column('daily_report_enabled', sa.Boolean, default=True),
        sa.Column('weekly_report_enabled', sa.Boolean, default=True),
        sa.Column('created_at', sa.DateTime, default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime, default=sa.func.now(), onupdate=sa.func.now()),
        sa.Column('trial_ends_at', sa.DateTime),
        sa.Column('last_active_at', sa.DateTime),
    )
    op.create_index('ix_clients_business_name', 'clients', ['business_name'])
    op.create_index('ix_clients_status', 'clients', ['status'])

    # Create campaigns table
    op.create_table(
        'campaigns',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('description', sa.Text),
        sa.Column('type', sa.String(20), default='cold_outreach'),
        sa.Column('status', sa.String(20), default='draft'),
        sa.Column('client_id', sa.String(36), sa.ForeignKey('clients.id')),
        sa.Column('client_name', sa.String(255)),
        sa.Column('client_service', sa.String(255)),
        sa.Column('niche', sa.String(50), nullable=False),
        sa.Column('target_cities', sa.Text),
        sa.Column('target_lead_count', sa.Integer, default=500),
        sa.Column('script_name', sa.String(100)),
        sa.Column('script_language', sa.String(20), default='hinglish'),
        sa.Column('start_date', sa.DateTime),
        sa.Column('end_date', sa.DateTime),
        sa.Column('daily_call_limit', sa.Integer, default=100),
        sa.Column('working_hours_start', sa.Time),
        sa.Column('working_hours_end', sa.Time),
        sa.Column('working_days', sa.String(50), default='mon,tue,wed,thu,fri,sat'),
        sa.Column('calls_per_hour', sa.Integer, default=20),
        sa.Column('max_concurrent_calls', sa.Integer, default=5),
        sa.Column('notify_whatsapp', sa.Text),
        sa.Column('notify_email', sa.Text),
        sa.Column('hot_lead_threshold', sa.Integer, default=70),
        sa.Column('sync_to_sheets', sa.Boolean, default=True),
        sa.Column('spreadsheet_id', sa.String(255)),
        sa.Column('sync_to_hubspot', sa.Boolean, default=False),
        sa.Column('hubspot_pipeline_id', sa.String(100)),
        sa.Column('sync_to_zoho', sa.Boolean, default=False),
        sa.Column('leads_scraped', sa.Integer, default=0),
        sa.Column('leads_called', sa.Integer, default=0),
        sa.Column('leads_connected', sa.Integer, default=0),
        sa.Column('leads_qualified', sa.Integer, default=0),
        sa.Column('appointments_booked', sa.Integer, default=0),
        sa.Column('callbacks_scheduled', sa.Integer, default=0),
        sa.Column('connection_rate', sa.Integer, default=0),
        sa.Column('qualification_rate', sa.Integer, default=0),
        sa.Column('conversion_rate', sa.Integer, default=0),
        sa.Column('total_call_cost', sa.Integer, default=0),
        sa.Column('cost_per_lead', sa.Integer, default=0),
        sa.Column('cost_per_appointment', sa.Integer, default=0),
        sa.Column('created_at', sa.DateTime, default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime, default=sa.func.now(), onupdate=sa.func.now()),
        sa.Column('started_at', sa.DateTime),
        sa.Column('completed_at', sa.DateTime),
    )
    op.create_index('ix_campaigns_status', 'campaigns', ['status'])
    op.create_index('ix_campaigns_niche', 'campaigns', ['niche'])

    # Create leads table
    op.create_table(
        'leads',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('company_name', sa.String(255), nullable=False),
        sa.Column('website', sa.String(500)),
        sa.Column('industry', sa.String(100)),
        sa.Column('employee_count', sa.String(50)),
        sa.Column('contact_name', sa.String(255)),
        sa.Column('phone', sa.String(20), nullable=False),
        sa.Column('email', sa.String(255)),
        sa.Column('designation', sa.String(100)),
        sa.Column('address', sa.Text),
        sa.Column('city', sa.String(100)),
        sa.Column('state', sa.String(100)),
        sa.Column('country', sa.String(100), default='India'),
        sa.Column('pincode', sa.String(10)),
        sa.Column('category', sa.String(100)),
        sa.Column('niche', sa.String(50)),
        sa.Column('tags', sa.Text),
        sa.Column('lead_score', sa.Integer, default=0),
        sa.Column('is_hot_lead', sa.Boolean, default=False),
        sa.Column('qualification_data', sa.Text),
        sa.Column('status', sa.String(20), default='new'),
        sa.Column('source', sa.String(20), default='manual'),
        sa.Column('verified', sa.Boolean, default=False),
        sa.Column('phone_verified', sa.Boolean, default=False),
        sa.Column('email_verified', sa.Boolean, default=False),
        sa.Column('assigned_to', sa.String(36), sa.ForeignKey('clients.id')),
        sa.Column('campaign_id', sa.String(36), sa.ForeignKey('campaigns.id')),
        sa.Column('call_attempts', sa.Integer, default=0),
        sa.Column('last_called_at', sa.DateTime),
        sa.Column('next_call_at', sa.DateTime),
        sa.Column('preferred_call_time', sa.String(50)),
        sa.Column('notes', sa.Text),
        sa.Column('appointment_date', sa.DateTime),
        sa.Column('appointment_notes', sa.Text),
        sa.Column('hubspot_id', sa.String(100)),
        sa.Column('zoho_id', sa.String(100)),
        sa.Column('sheets_row', sa.Integer),
        sa.Column('created_at', sa.DateTime, default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime, default=sa.func.now(), onupdate=sa.func.now()),
    )
    op.create_index('ix_leads_company_name', 'leads', ['company_name'])
    op.create_index('ix_leads_phone', 'leads', ['phone'])
    op.create_index('ix_leads_status', 'leads', ['status'])
    op.create_index('ix_leads_lead_score', 'leads', ['lead_score'])
    op.create_index('ix_leads_is_hot_lead', 'leads', ['is_hot_lead'])
    op.create_index('ix_leads_city', 'leads', ['city'])
    op.create_index('ix_leads_category', 'leads', ['category'])
    op.create_index('ix_leads_niche', 'leads', ['niche'])

    # Create call_logs table
    op.create_table(
        'call_logs',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('call_sid', sa.String(100)),
        sa.Column('provider', sa.String(20)),
        sa.Column('direction', sa.String(10), default='outbound'),
        sa.Column('lead_id', sa.String(36), sa.ForeignKey('leads.id')),
        sa.Column('campaign_id', sa.String(36), sa.ForeignKey('campaigns.id')),
        sa.Column('client_id', sa.String(36), sa.ForeignKey('clients.id')),
        sa.Column('from_number', sa.String(20)),
        sa.Column('to_number', sa.String(20), nullable=False),
        sa.Column('initiated_at', sa.DateTime, default=sa.func.now()),
        sa.Column('answered_at', sa.DateTime),
        sa.Column('ended_at', sa.DateTime),
        sa.Column('duration_seconds', sa.Integer, default=0),
        sa.Column('ring_duration', sa.Integer, default=0),
        sa.Column('talk_duration', sa.Integer, default=0),
        sa.Column('status', sa.String(20)),
        sa.Column('outcome', sa.String(20)),
        sa.Column('lead_score', sa.Integer, default=0),
        sa.Column('is_hot_lead', sa.Boolean, default=False),
        sa.Column('qualification_data', sa.Text),
        sa.Column('detected_intent', sa.String(50)),
        sa.Column('recording_url', sa.String(500)),
        sa.Column('recording_duration', sa.Integer),
        sa.Column('transcription', sa.Text),
        sa.Column('summary', sa.Text),
        sa.Column('sentiment', sa.String(20)),
        sa.Column('conversation_quality', sa.Integer),
        sa.Column('objections_faced', sa.Text),
        sa.Column('appointment_scheduled', sa.Boolean, default=False),
        sa.Column('appointment_date', sa.DateTime),
        sa.Column('appointment_notes', sa.Text),
        sa.Column('callback_scheduled', sa.Boolean, default=False),
        sa.Column('callback_date', sa.DateTime),
        sa.Column('callback_notes', sa.Text),
        sa.Column('call_cost', sa.Integer, default=0),
        sa.Column('error_code', sa.String(20)),
        sa.Column('error_message', sa.Text),
        sa.Column('retry_count', sa.Integer, default=0),
        sa.Column('is_retry', sa.Boolean, default=False),
        sa.Column('original_call_id', sa.String(36)),
        sa.Column('created_at', sa.DateTime, default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime, default=sa.func.now(), onupdate=sa.func.now()),
    )
    op.create_index('ix_call_logs_call_sid', 'call_logs', ['call_sid'])
    op.create_index('ix_call_logs_lead_id', 'call_logs', ['lead_id'])
    op.create_index('ix_call_logs_campaign_id', 'call_logs', ['campaign_id'])
    op.create_index('ix_call_logs_outcome', 'call_logs', ['outcome'])


def downgrade() -> None:
    op.drop_table('call_logs')
    op.drop_table('leads')
    op.drop_table('campaigns')
    op.drop_table('clients')
