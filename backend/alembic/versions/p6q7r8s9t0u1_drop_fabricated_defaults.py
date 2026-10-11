"""relax NOT NULL on columns whose fabricated defaults were removed
Revision ID: p6q7r8s9t0u1
Revises: o5p6q7r8s9t0
"""
from alembic import op
import sqlalchemy as sa

revision = 'p6q7r8s9t0u1'
down_revision = 'o5p6q7r8s9t0'

# (table, column, type) for columns that become nullable (no fabricated default).
_NULLABLE = [
    ('rider_profiles', 'rating', sa.Float()),
    ('rider_profiles', 'vehicle_fuel_type', sa.String(length=32)),
    ('rider_profiles', 'vehicle_cargo_type', sa.String(length=64)),
    ('rider_profiles', 'rc_status', sa.String(length=32)),
    ('rider_profiles', 'fleet_tier', sa.String(length=64)),
    ('rider_profiles', 'surge_priority_pct', sa.Integer()),
    ('rider_profiles', 'app_language', sa.String(length=64)),
    ('rider_profiles', 'documents_valid_until', sa.String(length=16)),
    ('messes', 'rating', sa.Float()),
    ('messes', 'delivery_fee_cents', sa.Integer()),
    ('deliveries', 'pickup_track_status', sa.String(length=32)),
    ('wallet_transactions', 'risk_score', sa.Integer()),
    ('wallet_transactions', 'risk_label', sa.String(length=64)),
]


def upgrade():
    for table, column, type_ in _NULLABLE:
        with op.batch_alter_table(table, schema=None) as batch_op:
            batch_op.alter_column(column, existing_type=type_, nullable=True)


def downgrade():
    for table, column, type_ in _NULLABLE:
        with op.batch_alter_table(table, schema=None) as batch_op:
            batch_op.alter_column(column, existing_type=type_, nullable=False)
