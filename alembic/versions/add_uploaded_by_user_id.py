"""Add uploaded_by_user_id to files

Revision ID: add_uploaded_by
Revises: 8e56bfb3a8c3
Create Date: 2026-08-17 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'add_uploaded_by'
down_revision: Union[str, Sequence[str], None] = '8e56bfb3a8c3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('files', sa.Column('uploaded_by_user_id', sa.Integer(), nullable=True, server_default='0'))
    op.execute('UPDATE files SET uploaded_by_user_id = owner_user_id WHERE uploaded_by_user_id IS NULL')
    op.alter_column('files', 'uploaded_by_user_id', nullable=False, server_default=None)
    op.create_index(op.f('ix_files_uploaded_by_user_id'), 'files', ['uploaded_by_user_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_files_uploaded_by_user_id'), table_name='files')
    op.drop_column('files', 'uploaded_by_user_id')
