import os
import yaml
import json
import hashlib
from pathlib import Path
from typing import Dict, List, Optional
from pydantic import BaseModel, Field
from jsonschema import validate, ValidationError


class SkillDefinition(BaseModel):
    """Definition of a skill"""
    name: str
    version: str
    description: str
    agent_type: str  # "specialist" or "orchestrator"
    capabilities: List[str]
    model_preferences: Dict[str, str] = Field(default_factory=dict)
    temperature: float = 0.7
    max_tokens: Optional[int] = None


class Skill:
    """Represents a loaded skill"""
    
    def __init__(self, skill_dir: Path):
        self.skill_dir = skill_dir
        self.skill_yaml_path = skill_dir / "skill.yaml"
        self.skill_md_path = skill_dir / "SKILL.md"
        self.output_schema_path = skill_dir / "output.schema.json"
        
        self._definition: Optional[SkillDefinition] = None
        self._markdown: Optional[str] = None
        self._output_schema: Optional[dict] = None
        self._content_hash: Optional[str] = None
    
    @property
    def definition(self) -> SkillDefinition:
        if self._definition is None:
            self._load()
        return self._definition
    
    @property
    def markdown(self) -> str:
        if self._markdown is None:
            self._load()
        return self._markdown
    
    @property
    def output_schema(self) -> dict:
        if self._output_schema is None:
            self._load()
        return self._output_schema
    
    @property
    def content_hash(self) -> str:
        if self._content_hash is None:
            self._compute_hash()
        return self._content_hash
    
    def _load(self):
        """Load skill files"""
        # Load skill.yaml
        with open(self.skill_yaml_path, 'r') as f:
            yaml_content = yaml.safe_load(f)
            self._definition = SkillDefinition(**yaml_content)
        
        # Load SKILL.md
        with open(self.skill_md_path, 'r') as f:
            self._markdown = f.read()
        
        # Load output.schema.json
        with open(self.output_schema_path, 'r') as f:
            self._output_schema = json.load(f)
    
    def _compute_hash(self):
        """Compute content hash of all skill files"""
        hasher = hashlib.sha256()
        
        # Hash skill.yaml
        with open(self.skill_yaml_path, 'rb') as f:
            hasher.update(f.read())
        
        # Hash SKILL.md
        with open(self.skill_md_path, 'rb') as f:
            hasher.update(f.read())
        
        # Hash output.schema.json
        with open(self.output_schema_path, 'rb') as f:
            hasher.update(f.read())
        
        self._content_hash = hasher.hexdigest()
    
    def validate_output(self, output: dict) -> bool:
        """Validate output against schema"""
        try:
            validate(instance=output, schema=self.output_schema)
            return True
        except ValidationError:
            return False


class SkillRegistry:
    """Registry for loading and managing skills"""
    
    def __init__(self, agents_dir: Path):
        self.agents_dir = agents_dir
        self._skills: Dict[str, Skill] = {}
        self._profiles: Dict[str, List[str]] = {}  # profile_name -> list of skill names
    
    def load_profile(self, profile_name: str) -> List[str]:
        """Load a skill profile (minimal or full)"""
        profile_path = self.agents_dir / profile_name
        
        if not profile_path.exists():
            raise ValueError(f"Profile {profile_name} not found at {profile_path}")
        
        skill_names = []
        for skill_dir in profile_path.iterdir():
            if skill_dir.is_dir() and (skill_dir / "skill.yaml").exists():
                skill_names.append(skill_dir.name)
        
        self._profiles[profile_name] = skill_names
        return skill_names
    
    def load_skill(self, skill_name: str, profile_name: str = "minimal") -> Skill:
        """Load a specific skill"""
        if skill_name in self._skills:
            return self._skills[skill_name]
        
        skill_dir = self.agents_dir / profile_name / skill_name
        
        if not skill_dir.exists():
            raise ValueError(f"Skill {skill_name} not found in profile {profile_name}")
        
        skill = Skill(skill_dir)
        self._skills[skill_name] = skill
        return skill
    
    def load_all_skills(self, profile_name: str = "minimal") -> Dict[str, Skill]:
        """Load all skills from a profile"""
        skill_names = self.load_profile(profile_name)
        
        for skill_name in skill_names:
            if skill_name not in self._skills:
                self.load_skill(skill_name, profile_name)
        
        return self._skills
    
    def get_skill(self, skill_name: str) -> Optional[Skill]:
        """Get a loaded skill by name"""
        return self._skills.get(skill_name)
    
    def get_skills_by_type(self, agent_type: str) -> List[Skill]:
        """Get all skills of a specific type"""
        return [
            skill for skill in self._skills.values()
            if skill.definition.agent_type == agent_type
        ]


def get_registry(profile_name: str = "minimal") -> SkillRegistry:
    """Get the skill registry for a profile"""
    # Get the directory containing the .agents folder
    # This should be at the root of the agent-service
    current_dir = Path(__file__).parent.parent.parent
    agents_dir = current_dir / ".agents"
    
    if not agents_dir.exists():
        # Create default structure
        agents_dir.mkdir(parents=True, exist_ok=True)
        (agents_dir / "minimal").mkdir(exist_ok=True)
        (agents_dir / "full").mkdir(exist_ok=True)
    
    registry = SkillRegistry(agents_dir)
    registry.load_all_skills(profile_name)
    
    return registry
