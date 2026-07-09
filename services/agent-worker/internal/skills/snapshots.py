from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from internal.models import SkillSnapshot, AgentRun
from internal.skills.registry import Skill
import json


async def create_skill_snapshot(
    session: AsyncSession,
    run_id: str,
    skill: Skill
) -> SkillSnapshot:
    """Create a skill snapshot for a run"""
    
    snapshot = SkillSnapshot(
        chat_id=run_id,
        skill_name=skill.definition.name,
        skill_version=skill.definition.version,
        content_hash=skill.content_hash,
        skill_yaml=skill.skill_yaml_path.read_text(),
        skill_markdown=skill.markdown,
        output_schema=json.dumps(skill.output_schema)
    )
    
    session.add(snapshot)
    await session.commit()
    await session.refresh(snapshot)
    
    return snapshot


async def get_skill_snapshot(
    session: AsyncSession,
    run_id: str,
    skill_name: str
) -> Optional[SkillSnapshot]:
    """Get a skill snapshot for a run"""
    
    query = select(SkillSnapshot).where(
        SkillSnapshot.chat_id == run_id,
        SkillSnapshot.skill_name == skill_name
    )
    
    result = await session.execute(query)
    return result.scalar_one_or_none()


async def get_all_skill_snapshots(
    session: AsyncSession,
    run_id: str
) -> list[SkillSnapshot]:
    """Get all skill snapshots for a run"""
    
    query = select(SkillSnapshot).where(
        SkillSnapshot.chat_id == run_id
    ).order_by(SkillSnapshot.created_at)
    
    result = await session.execute(query)
    return result.scalars().all()


async def verify_skill_integrity(
    session: AsyncSession,
    run_id: str,
    skill: Skill
) -> bool:
    """Verify that a skill's content hash matches the snapshot"""
    
    snapshot = await get_skill_snapshot(session, run_id, skill.definition.name)
    
    if not snapshot:
        return False
    
    return snapshot.content_hash == skill.content_hash
