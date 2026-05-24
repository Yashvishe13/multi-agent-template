"""Sub-agent with ReAct loop, deferred skill loading, and terminal access."""

from __future__ import annotations

import asyncio
import uuid
from typing import Annotated, Literal, TypedDict

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from langgraph.graph import END, StateGraph

from harness.console_log import sub as log_sub
from harness.schemas import AgentStep
from harness.skill_loader import Skill, get_skill_by_name, skill_names_catalog
from harness.terminal import run_command
from harness.trace_logger import TraceLogger

MODEL_NAME = "gpt-4o-mini"
MAX_REACT_STEPS = 12
MAX_SKILL_CONTENT = 12000


class SubAgentState(TypedDict):
    task: str
    subject: str
    agent_id: str
    loaded_skill: Skill | None
    pending_skill_name: str | None
    messages: Annotated[list, lambda left, right: left + right]
    observations: Annotated[list[str], lambda left, right: left + right]
    error_history: Annotated[list[str], lambda left, right: left + right]
    step: int
    max_steps: int
    final_result: str
    status: Literal["running", "done", "failed"]


def _build_system_prompt() -> str:
    return f"""You are a focused sub-agent executing one delegated task.

First steps:
- When a task mentions a file or data: FIRST run `find . -name "*keyword*"` or `ls -la` to discover what exists. Do NOT guess paths.
- Basic shell commands (ls, find, grep, cat, head, curl, pip) do NOT need a skill. Just use code=true directly.
- Only load a skill when you need specialized domain knowledge (e.g., PDF manipulation, web search APIs).

Available skills (names only — full SKILL.md loads on your next step after you choose):
{skill_names_catalog()}

Respond using structured JSON with fields:
- thought: your reasoning
- skill_name: exact skill name to load next iteration, or null if none needed
- code: true to execute a terminal command, false otherwise
- command: shell command when code=true
- content: message/result when code=false
- done: true when the subtask is fully complete
- spawn_subagents: always set to empty list [] (sub-agents do not delegate further)

Skill usage (important — read carefully):
- Skills are REFERENCE DOCUMENTATION, not actions. Loading a skill gives you code examples and instructions.
- To use a skill: first set skill_name to load it (code=false), then on the NEXT step use code=true with a command based on the skill's examples.
- Do NOT set skill_name to the same skill that was already loaded. Move on to executing a command.
- Only set skill_name when a catalog skill clearly applies; otherwise leave it null.
- When a skill shows Python code examples, you MUST use EXACTLY the libraries shown in the skill (e.g., if skill says "pypdf" do NOT use "PyPDF2"). Copy the import names from the skill examples.

Rules:
- Use code=true when you need to execute a terminal command. This is how you actually DO things.
- Set done=true only on the final step with the completed result in content.

How to write commands:
- All commands run in a shell (bash). Python code must be wrapped: python3 -c '...' or write a temp script.
- Skill examples show Python code — they are NOT shell commands. You must wrap them.
- For multi-line Python, ALWAYS write a temp script file instead of one-liners:
  python3 -c "
  import pypdf
  reader = pypdf.PdfReader('file.pdf')
  for page in reader.pages:
      print(page.extract_text())
  "
- NEVER use semicolons to join Python statements with 'with', 'for', 'if', 'try' — it causes SyntaxError.
  BAD:  python -c "import x; with x.open('f') as y: print(y.read())"
  GOOD: python3 -c "
  import x
  with x.open('f') as y:
      print(y.read())
  "

Error handling:
- When a command fails, READ the error carefully. Diagnose root cause before retrying.
- Common fixes: missing package → pip install it; missing file → check if it exists first; syntax error → rewrite as multiline.
- NEVER retry the exact same failing command. Always change approach based on error output.
- "command not found" means you tried to run Python code directly in the shell — wrap it in python3 -c.
"""


def _inject_pending_skill(state: SubAgentState) -> tuple[list, Skill | None, str | None]:
    messages = list(state["messages"])
    loaded_skill = state.get("loaded_skill")
    pending = state.get("pending_skill_name")

    if not pending:
        return messages, loaded_skill, None

    if loaded_skill and loaded_skill.name.lower() == pending.strip().lower():
        messages.append(
            HumanMessage(
                content=(
                    f"Skill `{pending}` is ALREADY LOADED in your context. "
                    f"Do NOT request it again. Use code=true with a command based on the skill examples above."
                )
            )
        )
        log_sub(state["agent_id"], state["subject"], f"skill `{pending}` already loaded — nudging to execute")
        return messages, loaded_skill, None

    skill = get_skill_by_name(pending)
    if skill:
        messages.append(
            HumanMessage(
                content=(
                    f"Loaded skill `{skill.name}` — reference docs below. "
                    f"NOW use code=true on your next step to execute a command based on these examples.\n\n"
                    f"{skill.content[:MAX_SKILL_CONTENT]}"
                )
            )
        )
        loaded_skill = skill
        log_sub(state["agent_id"], state["subject"], f"loaded skill `{skill.name}`")
    else:
        messages.append(HumanMessage(content=f"Unknown skill `{pending}` — continue without it."))
        log_sub(state["agent_id"], state["subject"], f"unknown skill `{pending}`")

    return messages, loaded_skill, None


def _create_react_node(llm: ChatOpenAI, tracer: TraceLogger):
    structured_llm = llm.with_structured_output(AgentStep)

    def react(state: SubAgentState) -> SubAgentState:
        step_num = state["step"] + 1
        messages, loaded_skill, _ = _inject_pending_skill(state)

        error_history = state.get("error_history", [])
        if error_history:
            error_summary = (
                "PREVIOUS ERRORS (do NOT retry the same command — diagnose and change approach):\n"
                + "\n".join(f"  - {e}" for e in error_history[-5:])
            )
            messages.append(HumanMessage(content=error_summary))

        log_sub(state["agent_id"], state["subject"], f"step {step_num} running…")
        response: AgentStep = structured_llm.invoke(messages)

        pending_skill_name: str | None = None
        skill_note = ""
        if response.skill_name:
            if get_skill_by_name(response.skill_name):
                pending_skill_name = response.skill_name.strip()
                skill_note = f"Skill `{pending_skill_name}` queued for next step."
                log_sub(
                    state["agent_id"],
                    state["subject"],
                    f"chose skill `{pending_skill_name}` → next iter",
                )
            else:
                skill_note = f"Unknown skill `{response.skill_name}`."
                log_sub(state["agent_id"], state["subject"], skill_note)

        tracer.log(
            "subagent_step",
            {
                "subject": state["subject"],
                "step": step_num,
                "thought": response.thought,
                "skill_name": response.skill_name,
                "code": response.code,
                "done": response.done,
            },
        )

        observation_parts: list[str] = []
        if skill_note:
            observation_parts.append(skill_note)

        assistant_content = response.content or response.thought
        terminal_result = None

        if response.code:
            if not response.command:
                observation_parts.append("Error: code=true but no command provided.")
            else:
                log_sub(
                    state["agent_id"],
                    state["subject"],
                    f"exec `{response.command[:50]}…`" if len(response.command) > 50 else f"exec `{response.command}`",
                )
                terminal_result = run_command(response.command)
                observation_parts.append(
                    f"Command: {terminal_result.command}\n"
                    f"Exit code: {terminal_result.returncode}\n"
                    f"STDOUT:\n{terminal_result.stdout}\n"
                    f"STDERR:\n{terminal_result.stderr}"
                )
                tracer.log(
                    "terminal_exec",
                    {
                        "agent_id": state["agent_id"],
                        "command": response.command,
                        "success": terminal_result.success,
                        "returncode": terminal_result.returncode,
                    },
                )
        elif response.done:
            observation_parts.append(f"Subtask complete: {assistant_content}")
            log_sub(state["agent_id"], state["subject"], "done")
        else:
            observation_parts.append(assistant_content or "Continuing…")

        observation = "\n".join(observation_parts)

        new_errors: list[str] = []
        if terminal_result and not terminal_result.success:
            error_entry = f"cmd=`{response.command[:80]}` stderr=`{terminal_result.stderr.strip()[:200]}`"
            new_errors.append(error_entry)

        update: SubAgentState = {
            "messages": [
                AIMessage(content=assistant_content),
                HumanMessage(content=f"Observation: {observation}"),
            ],
            "observations": [observation],
            "error_history": new_errors,
            "step": step_num,
            "loaded_skill": loaded_skill,
            "pending_skill_name": pending_skill_name,
        }

        if response.done:
            update["final_result"] = assistant_content or observation
            update["status"] = "done"
        elif step_num >= state["max_steps"]:
            update["final_result"] = observation
            update["status"] = "failed"
            log_sub(state["agent_id"], state["subject"], "max steps reached")

        return update

    return react


def _route_after_react(state: SubAgentState) -> Literal["react", "end"]:
    if state["status"] in {"done", "failed"} or state["step"] >= state["max_steps"]:
        return "end"
    return "react"


def build_subagent_graph(llm: ChatOpenAI, tracer: TraceLogger):
    graph = StateGraph(SubAgentState)
    graph.add_node("react", _create_react_node(llm, tracer))
    graph.set_entry_point("react")
    graph.add_conditional_edges("react", _route_after_react, {"react": "react", "end": END})
    return graph.compile()


async def run_subagent(
    task: str,
    subject: str,
    tracer: TraceLogger,
    max_steps: int = MAX_REACT_STEPS,
) -> dict:
    agent_id = f"sub-{uuid.uuid4().hex[:8]}"
    sub_tracer = tracer.child(agent_id)

    sub_tracer.log("subagent_spawn", {"subject": subject, "task": task})
    log_sub(agent_id, subject, "started")

    llm = ChatOpenAI(model=MODEL_NAME, temperature=0)
    graph = build_subagent_graph(llm, sub_tracer)

    initial_state: SubAgentState = {
        "task": task,
        "subject": subject,
        "agent_id": agent_id,
        "loaded_skill": None,
        "pending_skill_name": None,
        "messages": [
            SystemMessage(content=_build_system_prompt()),
            HumanMessage(content=f"Subject: {subject}\nTask: {task}"),
        ],
        "observations": [],
        "error_history": [],
        "step": 0,
        "max_steps": max_steps,
        "final_result": "",
        "status": "running",
    }

    final_state = await asyncio.to_thread(graph.invoke, initial_state)
    loaded = final_state.get("loaded_skill")
    result = {
        "agent_id": agent_id,
        "subject": subject,
        "task": task,
        "skill_used": loaded.name if loaded else None,
        "status": final_state.get("status", "done"),
        "result": final_state.get("final_result", ""),
        "steps": final_state.get("step", 0),
    }
    sub_tracer.log("subagent_complete", result)
    return result
