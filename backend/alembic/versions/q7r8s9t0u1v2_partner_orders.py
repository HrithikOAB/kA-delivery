"""partner-registered orders: nullable mess/customer/drop-off, external status, purge test orders
Revision ID: q7r8s9t0u1v2
Revises: p6q7r8s9t0u1
"""
from alembic import op
import sqlalchemy as sa

revision = 'q7r8s9t0u1v2'
down_revision = 'p6q7r8s9t0u1'

_NULLABLE = [
    ('customer_id', sa.Integer()),
    ('mess_id', sa.Integer()),
    ('address_text', sa.String(length=255)),
    ('address_lat', sa.Float()),
    ('address_lng', sa.Float()),
]

_TEST_ORDERS = "SELECT id FROM orders WHERE is_test = 1"
_TEST_DELIVERIES = f"SELECT id FROM deliveries WHERE order_id IN ({_TEST_ORDERS})"
_TEST_BATCHES = f"SELECT batch_id FROM deliveries WHERE order_id IN ({_TEST_ORDERS})"


def upgrade():
    with op.batch_alter_table('orders', schema=None) as batch_op:
        for column, type_ in _NULLABLE:
            batch_op.alter_column(column, existing_type=type_, nullable=True)
        batch_op.add_column(sa.Column('external_order_status', sa.String(length=32), nullable=True))

    # The test-order tool is gone; drop its rows. SQLite does not enforce the
    # FK cascades, so children are removed explicitly.
    op.execute(f"DELETE FROM audit_events WHERE order_id IN ({_TEST_ORDERS})")
    op.execute(f"DELETE FROM delivery_issues WHERE order_id IN ({_TEST_ORDERS})")
    op.execute(f"UPDATE rider_locations SET order_id = NULL WHERE order_id IN ({_TEST_ORDERS})")
    op.execute(f"DELETE FROM delivery_offers WHERE batch_id IN ({_TEST_BATCHES})")
    # Batch ids must be captured before their deliveries are deleted.
    op.execute(f"CREATE TEMP TABLE _purge_batches AS {_TEST_BATCHES}")
    op.execute(f"DELETE FROM deliveries WHERE id IN ({_TEST_DELIVERIES})")
    op.execute("DELETE FROM delivery_batches WHERE id IN (SELECT batch_id FROM _purge_batches)")
    op.execute("DROP TABLE _purge_batches")
    op.execute(f"DELETE FROM order_items WHERE order_id IN ({_TEST_ORDERS})")
    op.execute("DELETE FROM orders WHERE is_test = 1")


def downgrade():
    with op.batch_alter_table('orders', schema=None) as batch_op:
        batch_op.drop_column('external_order_status')
        for column, type_ in _NULLABLE:
            batch_op.alter_column(column, existing_type=type_, nullable=False)
