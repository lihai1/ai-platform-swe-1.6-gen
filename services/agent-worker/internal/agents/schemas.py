from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any


class SkillsLeadDecision(BaseModel):
    """Decision from skills-lead agent about which specialists to use"""
    
    selected_specialists: List[str] = Field(
        description="List of specialist agent names to invoke"
    )
    reasoning: str = Field(
        description="Reasoning for why these specialists were selected"
    )
    estimated_complexity: str = Field(
        description="Estimated complexity: low, medium, or high"
    )
    suggested_phases: List[str] = Field(
        description="Suggested workflow phases to execute"
    )


class RepositorySummary(BaseModel):
    """Summary of a repository from repo-scout agent"""
    
    primary_language: str = Field(description="Main programming language")
    frameworks: List[str] = Field(description="Frameworks and libraries detected")
    project_type: str = Field(description="Type of project: web, cli, library, etc.")
    total_files: int = Field(description="Total number of files")
    test_files: int = Field(description="Number of test files")
    main_source_files: int = Field(description="Number of main source files")
    config_files: int = Field(description="Number of configuration files")
    directory_structure: Dict[str, Any] = Field(description="Simplified directory structure")
    key_files: List[str] = Field(description="Important files to be aware of")
    build_system: Optional[str] = Field(description="Build system: make, npm, cargo, etc.")
    test_framework: Optional[str] = Field(description="Test framework detected")
    dependencies: List[str] = Field(description="Key dependencies")


class ImplementationPlan(BaseModel):
    """Implementation plan from solution-planner agent"""
    
    description: str = Field(description="High-level description of the implementation")
    files_expected_to_change: List[str] = Field(
        description="List of files that will be modified or created"
    )
    acceptance_criteria: List[str] = Field(
        description="List of acceptance criteria for the implementation"
    )
    estimated_steps: int = Field(description="Estimated number of implementation steps")
    risk_factors: List[str] = Field(
        description="Potential risks or challenges"
    )
    suggested_approach: str = Field(
        description="Suggested approach for implementation"
    )
    dependencies_to_add: Optional[List[str]] = Field(
        description="New dependencies that may need to be added"
    )
    tests_to_write: List[str] = Field(
        description="Tests that should be written"
    )


class ImplementationResult(BaseModel):
    """Result from implementation agents"""
    
    files_modified: List[str] = Field(description="Files that were modified")
    files_created: List[str] = Field(description="Files that were created")
    lines_added: int = Field(description="Total lines of code added")
    lines_removed: int = Field(description="Total lines of code removed")
    success: bool = Field(description="Whether implementation was successful")
    errors: List[str] = Field(description="Any errors encountered")
    warnings: List[str] = Field(description="Any warnings")


class TestResult(BaseModel):
    """Result from test execution"""
    
    total_tests: int = Field(description="Total number of tests run")
    passed: int = Field(description="Number of tests that passed")
    failed: int = Field(description="Number of tests that failed")
    skipped: int = Field(description="Number of tests skipped")
    coverage: float = Field(description="Code coverage percentage")
    test_output: str = Field(description="Full test output")
    failed_tests: List[str] = Field(description="Names of failed tests")


class ReviewFinding(BaseModel):
    """A single review finding"""
    
    severity: str = Field(description="Severity: blocking, high, medium, low")
    message: str = Field(description="Review message")
    file: Optional[str] = Field(description="File where issue was found")
    line: Optional[int] = Field(description="Line number where issue was found")


class ReviewResult(BaseModel):
    """Result from code review"""
    
    decision: str = Field(description="Decision: approved, changes_required, rejected")
    findings: List[ReviewFinding] = Field(description="List of review findings")
    summary: str = Field(description="Summary of the review")


class CriterionResult(BaseModel):
    """Result for a single acceptance criterion"""
    
    criterion: str = Field(description="The acceptance criterion")
    passed: bool = Field(description="Whether the criterion was met")
    evidence: str = Field(description="Evidence for the decision")


class VerificationResult(BaseModel):
    """Result from completion verification"""
    
    accepted: bool = Field(description="Whether the implementation is accepted")
    criteria_results: List[CriterionResult] = Field(
        description="Results for each acceptance criterion"
    )
    summary: str = Field(description="Summary of the verification")
