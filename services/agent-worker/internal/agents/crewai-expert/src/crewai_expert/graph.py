"""LangGraph workflow wiring for the CrewAI expert worker."""

from __future__ import annotations

from functools import partial
from typing import Any

from langgraph.graph import END, StateGraph
from langgraph.checkpoint.base import BaseCheckpointSaver

from crewai_expert.nodes import (
    cancelled_node,
    completed_node,
    created_node,
    failed_node,
    inspect_dependencies_node,
    patch_dependencies_node,
    prepare_patch_approval_node,
    prepare_project_selection_node,
    receive_patch_approval_node,
    receive_project_selection_node,
    resolve_project_node,
    run_crewai_cli_node,
    summarize_project_node,
    sync_dependencies_node,
    verify_project_node,
    waiting_patch_approval_node,
    waiting_project_selection_node,
)
from crewai_expert.state import ExpertState, ExpertStatus


def create_expert_graph(nats: Any, cfg: Any, checkpointer: BaseCheckpointSaver | None = None):
    """Compile the sequential expert graph with the given NATS client and config."""
    workflow = StateGraph(ExpertState)

    nodes = {
        ExpertStatus.CREATED.value: created_node,
        ExpertStatus.RESOLVE_PROJECT.value: resolve_project_node,
        ExpertStatus.PREPARE_PROJECT_SELECTION.value: prepare_project_selection_node,
        ExpertStatus.WAITING_PROJECT_SELECTION.value: waiting_project_selection_node,
        ExpertStatus.RECEIVE_PROJECT_SELECTION.value: receive_project_selection_node,
        ExpertStatus.SUMMARIZE_PROJECT.value: summarize_project_node,
        ExpertStatus.INSPECT_DEPENDENCIES.value: inspect_dependencies_node,
        ExpertStatus.PREPARE_PATCH_APPROVAL.value: prepare_patch_approval_node,
        ExpertStatus.WAITING_PATCH_APPROVAL.value: waiting_patch_approval_node,
        ExpertStatus.RECEIVE_PATCH_APPROVAL.value: receive_patch_approval_node,
        ExpertStatus.PATCH_DEPENDENCIES.value: patch_dependencies_node,
        ExpertStatus.SYNC_DEPENDENCIES.value: sync_dependencies_node,
        ExpertStatus.VERIFY_PROJECT.value: verify_project_node,
        ExpertStatus.RUN_CREWAI_CLI.value: run_crewai_cli_node,
        ExpertStatus.COMPLETED.value: completed_node,
        ExpertStatus.FAILED.value: failed_node,
        ExpertStatus.CANCELLED.value: cancelled_node,
    }

    for node_name, node_func in nodes.items():
        workflow.add_node(node_name, partial(node_func, nats=nats, cfg=cfg))

    workflow.set_entry_point(ExpertStatus.CREATED.value)
    workflow.add_edge(ExpertStatus.CREATED.value, ExpertStatus.RESOLVE_PROJECT.value)

    workflow.add_conditional_edges(
        ExpertStatus.RESOLVE_PROJECT.value,
        lambda s: s["status"],
        {
            ExpertStatus.SUMMARIZE_PROJECT.value: ExpertStatus.SUMMARIZE_PROJECT.value,
            ExpertStatus.PREPARE_PROJECT_SELECTION.value: ExpertStatus.PREPARE_PROJECT_SELECTION.value,
            ExpertStatus.FAILED.value: ExpertStatus.FAILED.value,
        },
    )

    workflow.add_edge(
        ExpertStatus.PREPARE_PROJECT_SELECTION.value,
        ExpertStatus.WAITING_PROJECT_SELECTION.value,
    )
    workflow.add_edge(
        ExpertStatus.WAITING_PROJECT_SELECTION.value,
        ExpertStatus.RECEIVE_PROJECT_SELECTION.value,
    )
    workflow.add_conditional_edges(
        ExpertStatus.RECEIVE_PROJECT_SELECTION.value,
        lambda s: s["status"],
        {
            ExpertStatus.SUMMARIZE_PROJECT.value: ExpertStatus.SUMMARIZE_PROJECT.value,
            ExpertStatus.PREPARE_PROJECT_SELECTION.value: ExpertStatus.PREPARE_PROJECT_SELECTION.value,
            ExpertStatus.FAILED.value: ExpertStatus.FAILED.value,
        },
    )

    workflow.add_edge(
        ExpertStatus.SUMMARIZE_PROJECT.value, ExpertStatus.INSPECT_DEPENDENCIES.value
    )
    workflow.add_conditional_edges(
        ExpertStatus.INSPECT_DEPENDENCIES.value,
        lambda s: s["status"],
        {
            ExpertStatus.SYNC_DEPENDENCIES.value: ExpertStatus.SYNC_DEPENDENCIES.value,
            ExpertStatus.PREPARE_PATCH_APPROVAL.value: ExpertStatus.PREPARE_PATCH_APPROVAL.value,
            ExpertStatus.FAILED.value: ExpertStatus.FAILED.value,
        },
    )

    workflow.add_edge(
        ExpertStatus.PREPARE_PATCH_APPROVAL.value,
        ExpertStatus.WAITING_PATCH_APPROVAL.value,
    )
    workflow.add_edge(
        ExpertStatus.WAITING_PATCH_APPROVAL.value,
        ExpertStatus.RECEIVE_PATCH_APPROVAL.value,
    )
    workflow.add_conditional_edges(
        ExpertStatus.RECEIVE_PATCH_APPROVAL.value,
        lambda s: s["status"],
        {
            ExpertStatus.PATCH_DEPENDENCIES.value: ExpertStatus.PATCH_DEPENDENCIES.value,
            ExpertStatus.WAITING_PATCH_APPROVAL.value: ExpertStatus.WAITING_PATCH_APPROVAL.value,
            ExpertStatus.CANCELLED.value: ExpertStatus.CANCELLED.value,
        },
    )

    workflow.add_conditional_edges(
        ExpertStatus.PATCH_DEPENDENCIES.value,
        lambda s: s["status"],
        {
            ExpertStatus.SYNC_DEPENDENCIES.value: ExpertStatus.SYNC_DEPENDENCIES.value,
            ExpertStatus.FAILED.value: ExpertStatus.FAILED.value,
        },
    )

    workflow.add_conditional_edges(
        ExpertStatus.SYNC_DEPENDENCIES.value,
        lambda s: s["status"],
        {
            ExpertStatus.VERIFY_PROJECT.value: ExpertStatus.VERIFY_PROJECT.value,
            ExpertStatus.FAILED.value: ExpertStatus.FAILED.value,
        },
    )

    workflow.add_conditional_edges(
        ExpertStatus.VERIFY_PROJECT.value,
        lambda s: s["status"],
        {
            ExpertStatus.RUN_CREWAI_CLI.value: ExpertStatus.RUN_CREWAI_CLI.value,
            ExpertStatus.INSPECT_DEPENDENCIES.value: ExpertStatus.INSPECT_DEPENDENCIES.value,
            ExpertStatus.FAILED.value: ExpertStatus.FAILED.value,
        },
    )

    workflow.add_conditional_edges(
        ExpertStatus.RUN_CREWAI_CLI.value,
        lambda s: s["status"],
        {
            ExpertStatus.COMPLETED.value: ExpertStatus.COMPLETED.value,
            ExpertStatus.FAILED.value: ExpertStatus.FAILED.value,
            ExpertStatus.CANCELLED.value: ExpertStatus.CANCELLED.value,
        },
    )

    for terminal in (ExpertStatus.COMPLETED, ExpertStatus.FAILED, ExpertStatus.CANCELLED):
        workflow.add_edge(terminal.value, END)

    return workflow.compile(checkpointer=checkpointer)


def create_test_expert_graph(nats: Any, cfg: Any):
    """Compile the expert graph with an in-memory checkpointer for tests."""
    from langgraph.checkpoint.memory import MemorySaver

    return create_expert_graph(nats, cfg, checkpointer=MemorySaver())
