"""partner API keys managed from the admin console
Revision ID: r8s9t0u1v2w3
Revises: q7r8s9t0u1v2
"""
from alembic import op
import sqlalchemy as sa

revision = 'r8s9t0u1v2w3'
down_revision = 'q7r8s9t0u1v2'


def upgrade():
    op.create_table(
        'partner_api_keys',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=128), nullable=False),
        sa.Column('key_hash', sa.String(length=64), nullable=False),
        sa.Column('key_prefix', sa.String(length=16), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False),
        sa.Column('created_by_user_id', sa.Integer(), nullable=True),
        sa.Column('last_used_at', sa.DateTime(), nullable=True),
        sa.Column('rotated_at', sa.DateTime(), nullable=True),
        sa.Column('revoked_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['created_by_user_id'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_partner_api_keys_key_hash', 'partner_api_keys', ['key_hash'], unique=True)
    op.create_index('ix_partner_api_keys_is_active', 'partner_api_keys', ['is_active'])


def downgrade():
    op.drop_index('ix_partner_api_keys_is_active', table_name='partner_api_keys')
    op.drop_index('ix_partner_api_keys_key_hash', table_name='partner_api_keys')
    op.drop_table('partner_api_keys')
