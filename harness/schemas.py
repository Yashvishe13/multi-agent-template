"""Shared structured output schemas for agents."""

from __future__ import annotations

from pydantic import BaseModel, Field


class SubagentTask(BaseModel):
    subject: str = Field(description="Clear, traceable subject for the subagent")
    task: str = Field(description="Specific delegated task instructions")


class AgentStep(BaseModel):
    thought: str = Field(description="Reasoning for this step")
    skill_name: str | None = Field(
        default=None,
        description=(
            "Exact name of a skill from the available catalog to load on the next step, "
            "or null/empty if no skill is needed"
        ),
    )
    code: bool = Field(description="True to run a shell command, False for text-only response")
    command: str | None = Field(default=None, description="Shell command when code=True")
    content: str | None = Field(default=None, description="Text response when code=False")
    done: bool = Field(default=False, description="True when the task/subtask is complete")
    spawn_subagents: list[SubagentTask] = Field(
        default_factory=list,
        description=(
            "List of independent subtasks to delegate to parallel subagents. "
            "Only populate when 2+ tasks are truly independent with no data dependencies. "
            "Leave empty for sequential work or simple tasks."
        ),
    )
