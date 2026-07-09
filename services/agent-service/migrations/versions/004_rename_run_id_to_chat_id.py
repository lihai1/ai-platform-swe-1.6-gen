"""Rename run_id to chat_id for consistency

Revision ID: 004
Revises: 003
Create Date: 2024-01-01 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '004'
down_revision = '003'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Rename run_id to chat_id in agent_steps
    op.alter_column('agent_steps', 'run_id', new_column_name='chat_id', schema='agent')
    op.drop_index('idx_agent_steps_run_id', table_name='agent_steps', schema='agent')
    op.create_index('idx_agent_steps_chat_id', 'agent_steps', ['chat_id'], schema='agent')
    
    # Rename run_id to chat_id in agent_events
    op.alter_column('agent_events', 'run_id', new_column_name='chat_id', schema='agent')
    op.drop_index('idx_agent_events_run_id', table_name='agent_events', schema='agent')
    op.create_index('idx_agent_events_chat_id', 'agent_events', ['chat_id'], schema='agent')
    
    # Rename run_id to chat_id in skill_snapshots
    op.alter_column('skill_snapshots', 'run_id', new_column_name='chat_id', schema='agent')
    op.drop_index('idx_skill_snapshots_run_id', table_name='skill_snapshots', schema='agent')
    op.create_index('idx_skill_snapshots_chat_id', 'skill_snapshots', ['chat_id'], schema='agent')
    
    # Rename run_id to chat_id in agent_artifacts
    op.alter_column('agent_artifacts', 'run_id', new_column_name='chat_id', schema='agent')
    op.drop_index('idx_agent_artifacts_run_id', table_name='agent_artifacts', schema='agent')
    op.create_index('idx_agent_artifacts_chat_id', 'agent_artifacts', ['chat_id'], schema='agent')
    
    # Rename run_id to chat_id in agent_approvals
    op.alter_column('agent_approvals', 'run_id', new_column_name='chat_id', schema='agent')
    op.drop_index('idx_agent_approvals_run_id', table_name='agent_approvals', schema='agent')
    op.create_index('idx_agent_approvals_chat_id', 'agent_approvals', ['chat_id'], schema='agent')
    
    # Rename run_id to chat_id in workspace_leases
    op.alter_column('workspace_leases', 'run_id', new_column_name='chat_id')
    op.drop_index(op.f('ix_workspace_leases_run_id'), table_name='workspace_leases')
    op.create_index(op.f('ix_workspace_leases_chat_id'), 'workspace_leases', ['chat_id'], unique=False)


def downgrade() -> None:
    # Revert chat_id to run_id in workspace_leases
    op.drop_index(op.f('ix_workspace_leases_chat_id'), table_name='workspace_leases')
    op.create_index(op.f('ix_workspace_leases_run_id'), 'workspace_leases', ['run_id'], unique=False)
    op.alter_column('workspace_leases', 'chat_id', new_column_name='run_id')
    
    # Revert chat_id to run_id in agent_approvals
    op.drop_index('idx_agent_approvals_chat_id', table_name='agent_approvals', schema='agent')
    op.create_index('idx_agent_approvals_run_id', 'agent_approvals', ['run_id'], schema='agent')
    op.alter_column('agent_approvals', 'chat_id', new_column_name='run_id', schema='agent')
    
    # Revert chat_id to run_id in agent_artifacts
    op.drop_index('idx_agent_artifacts_chat_id', table_name='agent_artifacts', schema='agent')
    op.create_index('idx_agent_artifacts_run_id', 'agent_artifacts', ['run_id'], schema='agent')
    op.alter_column('agent_artifacts', 'chat_id', new_column_name='run_id', schema='agent')
    
    # Revert chat_id to run_id in skill_snapshots
    op.drop_index('idx_skill_snapshots_chat_id', table_name='skill_snapshots', schema='agent')
    op.create_index('idx_skill_snapshots_run_id', 'skill_snapshots', ['run_id'], schema='agent')
    op.alter_column('skill_snapshots', 'chat_id', new_column_name='run_id', schema='agent')
    
    # Revert chat_id to run_id in agent_events
    op.drop_index('idx_agent_events_chat_id', table_name='agent_events', schema='agent')
    op.create_index('idx_agent_events_run_id', 'agent_events', ['run_id'], schema='agent')
    op.alter_column('agent_events', 'chat_id', new_column_name='run_id', schema='agent')
    
    # Revert chat_id to run_id in agent_steps
    op.drop_index('idx_agent_steps_chat_id', table_name='agent_steps', schema='agent')
    op.create_index('idx_agent_steps_run_id', 'agent_steps', ['run_id'], schema='agent')
    op.alter_column('agent_steps', 'chat_id', new_column_name='run_id', schema='agent')
