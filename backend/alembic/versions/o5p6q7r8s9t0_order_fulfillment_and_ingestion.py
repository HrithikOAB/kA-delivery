"""order fulfillment (external couriers) and booking-app ingestion fields
Revision ID: o5p6q7r8s9t0
Revises: n4o5p6q7r8s9
"""
from alembic import op
import sqlalchemy as sa

revision = 'o5p6q7r8s9t0'
down_revision = 'n4o5p6q7r8s9'


def upgrade():
    with op.batch_alter_table('orders', schema=None) as batch_op:
        batch_op.add_column(sa.Column('source', sa.String(length=24), nullable=False, server_default='customer'))
        batch_op.add_column(sa.Column('external_order_ref', sa.String(length=128), nullable=True))
        batch_op.add_column(sa.Column('fulfillment_type', sa.String(length=16), nullable=False, server_default='internal'))
        batch_op.add_column(sa.Column('external_provider', sa.String(length=24), nullable=True))
        batch_op.add_column(sa.Column('external_reference', sa.String(length=128), nullable=True))
        batch_op.add_column(sa.Column('external_note', sa.String(length=512), nullable=True))
        batch_op.add_column(sa.Column('external_status', sa.String(length=24), nullable=True))
        batch_op.add_column(sa.Column('external_assigned_at', sa.DateTime(), nullable=True))
        batch_op.add_column(sa.Column('customer_phone', sa.String(length=32), nullable=True))
        batch_op.create_index('ix_orders_source', ['source'])
        batch_op.create_index('ix_orders_fulfillment_type', ['fulfillment_type'])
        batch_op.create_index('ix_orders_external_order_ref', ['external_order_ref'], unique=True)


def downgrade():
    with op.batch_alter_table('orders', schema=None) as batch_op:
        batch_op.drop_index('ix_orders_external_order_ref')
        batch_op.drop_index('ix_orders_fulfillment_type')
        batch_op.drop_index('ix_orders_source')
        batch_op.drop_column('customer_phone')
        batch_op.drop_column('external_assigned_at')
        batch_op.drop_column('external_status')
        batch_op.drop_column('external_note')
        batch_op.drop_column('external_reference')
        batch_op.drop_column('external_provider')
        batch_op.drop_column('fulfillment_type')
        batch_op.drop_column('external_order_ref')
        batch_op.drop_column('source')
