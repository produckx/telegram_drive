"""Add registered_ip to users

Revision ID: add_registered_ip
Revises: add_uploaded_by
Create Date: 2026-08-17 14:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'add_registered_ip'
down_revision: Union[str, Sequence[str], None] = 'add_uploaded_by'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('users', sa.Column('registered_ip', sa.String(length=64), nullable=True))
    op.create_index(op.f('ix_users_registered_ip'), 'users', ['registered_ip'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_users_registered_ip'), table_name='users')
    op.drop_column('users', 'registered_ip')
