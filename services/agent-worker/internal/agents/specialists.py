from typing import Dict, Any
from langchain.agents import AgentExecutor, create_tool_calling_agent
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_openai import ChatOpenAI
from langchain_anthropic import ChatAnthropic
from internal.agents.schemas import (
    SkillsLeadDecision,
    RepositorySummary,
    ImplementationPlan
)
from internal.tools.repository import ReadOnlyRepositoryTools
from internal.agents.model_factory import get_model
from pydantic import BaseModel
import json


class SkillsLeadAgent:
    """Agent that selects appropriate specialists for a task"""
    
    def __init__(self, model_name: str = "gpt-4"):
        self.model = get_model(model_name)
        self.available_specialists = [
            "go-developer",
            "angular-developer",
            "angular-ui-developer",
            "devops-developer",
            "backend-test-engineer",
            "angular-test-engineer",
            "code-reviewer",
            "completion-verifier"
        ]
    
    async def select_specialists(self, task: str, repository_summary: Dict[str, Any]) -> SkillsLeadDecision:
        """Select appropriate specialists for the task"""
        
        prompt = ChatPromptTemplate.from_messages([
            ("system", """You are the skills-lead agent. Your job is to select the appropriate specialist agents for a given task.

Available specialists:
- go-developer: For Go backend development
- angular-developer: For Angular component development
- angular-ui-developer: For Angular UI/UX work
- devops-developer: For DevOps and infrastructure changes
- backend-test-engineer: For backend testing
- angular-test-engineer: For Angular testing
- code-reviewer: For code review
- completion-verifier: For verifying completion against acceptance criteria

Analyze the task and repository summary to determine which specialists are needed."""),
            ("human", "Task: {task}\n\nRepository Summary:\n{repository_summary}")
        ])
        
        chain = prompt | self.model.with_structured_output(SkillsLeadDecision)
        
        result = await chain.ainvoke({
            "task": task,
            "repository_summary": json.dumps(repository_summary, indent=2)
        })
        
        return result


class RepoScoutAgent:
    """Agent that analyzes a repository"""
    
    def __init__(self, repository_path, model_name: str = "gpt-4"):
        self.repository_path = repository_path
        self.model = get_model(model_name)
        self.repo_tools = ReadOnlyRepositoryTools(repository_path)
    
    async def analyze_repository(self) -> RepositorySummary:
        """Analyze the repository and return a summary"""
        
        # Gather repository information
        all_files = self.repo_tools.list_files()
        directory_structure = self.repo_tools.get_directory_structure()
        
        # Detect language based on file extensions
        language_counts = {}
        for file_path in all_files:
            ext = file_path.split('.')[-1] if '.' in file_path else 'unknown'
            language_counts[ext] = language_counts.get(ext, 0) + 1
        
        primary_language = max(language_counts.items(), key=lambda x: x[1])[0] if language_counts else "unknown"
        
        # Categorize files
        test_files = [f for f in all_files if 'test' in f.lower() or f.endswith('_test.go') or f.endswith('.test.ts')]
        config_files = [f for f in all_files if any(x in f.lower() for x in ['config', 'yaml', 'json', 'toml', 'env'])]
        main_files = [f for f in all_files if f not in test_files and f not in config_files]
        
        # Detect build system
        build_system = None
        if "Makefile" in all_files or "makefile" in all_files:
            build_system = "make"
        elif "package.json" in all_files:
            build_system = "npm"
        elif "go.mod" in all_files:
            build_system = "go"
        elif "Cargo.toml" in all_files:
            build_system = "cargo"
        
        # Detect test framework
        test_framework = None
        if any("_test.go" in f for f in all_files):
            test_framework = "go testing"
        elif any("ginkgo" in f for f in all_files):
            test_framework = "ginkgo"
        elif any(".spec.ts" in f for f in all_files):
            test_framework = "jasmine/karma"
        elif any("pytest" in f for f in all_files):
            test_framework = "pytest"
        
        # Use LLM to enhance the summary
        prompt = ChatPromptTemplate.from_messages([
            ("system", """You are the repo-scout agent. Analyze the repository information and provide a comprehensive summary.

Focus on:
- Frameworks and libraries used
- Project type (web, cli, library, etc.)
- Key files that are important
- Dependencies that are critical"""),
            ("human", """Repository Information:
- Primary language: {primary_language}
- Build system: {build_system}
- Test framework: {test_framework}
- Total files: {total_files}
- Test files: {test_files}
- Main source files: {main_files}
- Config files: {config_files}
- Directory structure: {directory_structure}

Provide a comprehensive repository summary.""")
        ])
        
        chain = prompt | self.model.with_structured_output(RepositorySummary)
        
        result = await chain.ainvoke({
            "primary_language": primary_language,
            "build_system": build_system,
            "test_framework": test_framework,
            "total_files": len(all_files),
            "test_files": len(test_files),
            "main_files": len(main_files),
            "config_files": len(config_files),
            "directory_structure": json.dumps(directory_structure, indent=2)
        })
        
        # Override with actual counts
        result.total_files = len(all_files)
        result.test_files = len(test_files)
        result.main_source_files = len(main_files)
        result.config_files = len(config_files)
        result.directory_structure = directory_structure
        result.build_system = build_system
        result.test_framework = test_framework
        result.primary_language = primary_language
        
        return result


class SolutionPlannerAgent:
    """Agent that creates implementation plans"""
    
    def __init__(self, model_name: str = "gpt-4"):
        self.model = get_model(model_name)
    
    async def create_plan(
        self,
        task: str,
        repository_summary: RepositorySummary,
        selected_specialists: list[str]
    ) -> ImplementationPlan:
        """Create an implementation plan for the task"""
        
        prompt = ChatPromptTemplate.from_messages([
            ("system", """You are the solution-planner agent. Your job is to create a detailed implementation plan for a given task.

The plan should include:
- A clear description of what will be implemented
- Which files will be modified or created
- Acceptance criteria for success
- Estimated number of steps
- Potential risks
- Suggested approach
- Any new dependencies needed
- Tests that should be written"""),
            ("human", """Task: {task}

Repository Summary:
{repository_summary}

Selected Specialists: {selected_specialists}

Create a detailed implementation plan.""")
        ])
        
        chain = prompt | self.model.with_structured_output(ImplementationPlan)
        
        result = await chain.ainvoke({
            "task": task,
            "repository_summary": repository_summary.model_dump_json(indent=2),
            "selected_specialists": ", ".join(selected_specialists)
        })
        
        return result
