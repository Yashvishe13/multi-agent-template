"""Main orchestrator agent: ReAct loop with dynamic planning and subagent spawning."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import subprocess
import sys
import uuid
from pathlib import Path
from typing import Annotated, Literal, TypedDict

from dotenv import load_dotenv
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from langgraph.graph import END, StateGraph

ATTEMPT_ROOT = Path(__file__).resolve().parent.parent
PROJECT_ROOT = ATTEMPT_ROOT.parent
sys.path.insert(0, str(ATTEMPT_ROOT))

from agents.sub_agent import run_subagent  # noqa: E402
from harness.console_log import main as log_main  # noqa: E402
from harness.console_log import run_start  # noqa: E402
from harness.schemas import AgentStep  # noqa: E402
from harness.skill_loader import Skill, get_skill_by_name, skill_names_catalog  # noqa: E402
from harness.terminal import run_command  # noqa: E402
from harness.trace_logger import TraceLogger  # noqa: E402

load_dotenv(PROJECT_ROOT / ".env")

MODEL_NAME = "gpt-4o-mini"
MAX_REACT_STEPS = 15
MAX_SUBAGENTS = 4
MAX_SKILL_CONTENT = 12000


class MainAgentState(TypedDict):
    task: str
    run_id: str
    loaded_skill: Skill | None
    pending_skill_name: str | None
    messages: Annotated[list, lambda left, right: left + right]
    observations: Annotated[list[str], lambda left, right: left + right]
    error_history: Annotated[list[str], lambda left, right: left + right]
    subagent_results: list[dict]
    step: int
    max_steps: int
    final_answer: str
    status: Literal["running", "done", "failed"]


def _gather_environment_context() -> str:
    """Collect runtime environment info so the agent can make informed decisions."""
    parts = []
    try:
        pip_out = subprocess.run(
            ["pip", "list", "--format=columns"],
            capture_output=True, text=True, timeout=15,
        )
        if pip_out.returncode == 0:
            parts.append(f"Installed Python packages:\n{pip_out.stdout.strip()}")
    except Exception:
        parts.append("Could not list installed Python packages.")

    cwd = Path.cwd()
    try:
        files = sorted(str(p.relative_to(cwd)) for p in cwd.rglob("*") if p.is_file())[:80]
        parts.append(f"Working directory: {cwd}\nFiles (first 80):\n" + "\n".join(files))
    except Exception:
        parts.append(f"Working directory: {cwd}")

    return "\n\n".join(parts)


def _main_system_prompt(env_context: str) -> str:
    return f"""You are the main orchestrator agent. You operate in a ReAct loop: reason about what to do, take an action (run a command, load a skill, or delegate to subagents), observe the result, and repeat until the task is complete.

You do NOT need to plan upfront for every task. For simple or straightforward tasks, just start executing. For complex multi-step tasks, think through the steps in your reasoning before acting.

First steps (IMPORTANT):
- When a task mentions a file, directory, or data: FIRST run `find . -name "*keyword*"` or `ls -la` to discover what exists. Do NOT guess paths.
- When you don't know where something is: search for it before trying to open/read it.
- Basic shell commands (ls, find, grep, cat, head, curl, pip) do NOT need a skill. Just use code=true directly.
- Only load a skill when you need specialized domain knowledge (e.g., PDF manipulation, web search APIs).

Subagent delegation:
- You can spawn subagents by populating the spawn_subagents field with a list of tasks.
- Spawn subagents ONLY for truly independent subtasks with no data dependencies between them.
- NEVER spawn subagents in parallel when one task's output is needed as input for another.
  Example: if task A is "find/download a file" and task B is "process that file", B depends on A — do A yourself first, then delegate or do B.
- Think about task dependencies: which steps produce outputs that other steps consume? Only parallelize steps that share no inputs/outputs.
- Launch at most {MAX_SUBAGENTS} subagents at once.
- For simple tasks, just do the work yourself — don't spawn subagents unnecessarily.

Available skills (names only — full SKILL.md loads on your next step after you choose):
{skill_names_catalog()}

Environment context (use this to know what's installed and available):
{env_context}

Respond using structured JSON with fields:
- thought: your reasoning about what to do next and why
- skill_name: exact skill name to load next iteration, or null if none needed
- code: true to execute a terminal command, false otherwise
- command: shell command when code=true
- content: message/result when code=false
- done: true when the overall task is fully complete
- spawn_subagents: list of {{"subject": "...", "task": "..."}} for independent parallel work, or empty list

Skill usage (important — read carefully):
- Skills are REFERENCE DOCUMENTATION, not actions. Loading a skill gives you code examples and instructions.
- To use a skill: first set skill_name to load it (code=false), then on the NEXT step use code=true with a command based on the skill's examples.
- Do NOT set skill_name to the same skill that was already loaded — it's already in your context. Move on to executing a command.
- Do NOT keep requesting the same skill repeatedly. If a skill is loaded, USE IT by writing a command.
- Only set skill_name when a catalog skill clearly applies; otherwise leave it null.
- When a skill shows Python code examples, you MUST use EXACTLY the libraries shown in the skill (e.g., if skill says "pypdf" do NOT use "PyPDF2"). Copy the import names from the skill examples.

Rules:
- Use code=true when you need to execute a terminal command. This is how you actually DO things.
- Set done=true only on the final step with the completed answer in content.

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
- When a command fails, READ the error message carefully. Diagnose the root cause before retrying.
- Common root causes: missing Python package (fix: pip install), missing file (fix: find or download it first), syntax error (fix: rewrite as multiline script).
- NEVER retry the exact same command that just failed. Change your approach based on the error.
- If a dependency is missing, install it. If a file doesn't exist, locate or create it first.
- "command not found" means you tried to run Python code directly in the shell — wrap it in python3 -c.
"""


def _inject_pending_skill(state: MainAgentState) -> tuple[list, Skill | None, str | None]:
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
        log_main(f"skill `{pending}` already loaded — nudging to execute")
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
        log_main(f"loaded skill `{skill.name}`")
    else:
        messages.append(HumanMessage(content=f"Unknown skill `{pending}` — continue without it."))
        log_main(f"unknown skill `{pending}`")

    return messages, loaded_skill, None


async def _spawn_and_collect(
    subagent_tasks: list,
    tracer: TraceLogger,
) -> list[dict]:
    """Spawn subagents for given tasks and collect results."""
    tasks = subagent_tasks[:MAX_SUBAGENTS]
    names = ", ".join(f'"{t.subject}"' for t in tasks)
    log_main(f"spawning {len(tasks)} subagent(s): {names}")

    tracer.log(
        "spawn_subagents",
        {"tasks": [t.model_dump() for t in tasks]},
    )

    coroutines = [
        run_subagent(task=t.task, subject=t.subject, tracer=tracer)
        for t in tasks
    ]
    results = await asyncio.gather(*coroutines, return_exceptions=True)

    normalized: list[dict] = []
    for index, result in enumerate(results):
        if isinstance(result, Exception):
            normalized.append(
                {
                    "subject": tasks[index].subject,
                    "status": "failed",
                    "result": str(result),
                }
            )
            log_main(f'subagent "{tasks[index].subject}" failed')
        else:
            normalized.append(result)
            log_main(
                f'subagent "{result["subject"]}" finished'
                + (f" (skill: {result['skill_used']})" if result.get("skill_used") else "")
            )

    tracer.log("subagents_collected", {"results": normalized})
    log_main("subagents collected")
    return normalized


def _create_react_node(llm: ChatOpenAI, tracer: TraceLogger):
    structured_llm = llm.with_structured_output(AgentStep)

    async def react(state: MainAgentState) -> MainAgentState:
        step_num = state["step"] + 1
        messages, loaded_skill, _ = _inject_pending_skill(state)

        error_history = state.get("error_history", [])
        if error_history:
            error_summary = (
                "PREVIOUS ERRORS (do NOT retry the same command — diagnose and change approach):\n"
                + "\n".join(f"  - {e}" for e in error_history[-5:])
            )
            messages.append(HumanMessage(content=error_summary))

        log_main(f"react step {step_num}…")
        response: AgentStep = await asyncio.to_thread(structured_llm.invoke, messages)

        pending_skill_name: str | None = None
        skill_note = ""
        if response.skill_name:
            if get_skill_by_name(response.skill_name):
                pending_skill_name = response.skill_name.strip()
                skill_note = f"Skill `{pending_skill_name}` queued for next step."
                log_main(f"chose skill `{pending_skill_name}` → next iter")
            else:
                skill_note = f"Unknown skill `{response.skill_name}`."
                log_main(skill_note)

        tracer.log(
            "main_step",
            {
                "step": step_num,
                "thought": response.thought,
                "skill_name": response.skill_name,
                "code": response.code,
                "done": response.done,
                "spawn_subagents": len(response.spawn_subagents),
            },
        )

        observation_parts: list[str] = []
        if skill_note:
            observation_parts.append(skill_note)

        assistant_content = response.content or response.thought
        terminal_result = None

        if response.spawn_subagents:
            subagent_results = await _spawn_and_collect(
                response.spawn_subagents, tracer
            )
            report = "Subagent reports:\n" + json.dumps(subagent_results, indent=2)
            observation_parts.append(report)

            return {
                "messages": [
                    AIMessage(content=assistant_content),
                    HumanMessage(content=f"Observation: {report}"),
                ],
                "observations": [report],
                "error_history": [],
                "subagent_results": subagent_results,
                "step": step_num,
                "loaded_skill": loaded_skill,
                "pending_skill_name": pending_skill_name,
            }

        if response.code:
            if not response.command:
                observation_parts.append("Error: code=true but no command provided.")
            else:
                cmd_preview = response.command[:50] + "…" if len(response.command) > 50 else response.command
                log_main(f"exec `{cmd_preview}`")
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
                        "command": response.command,
                        "success": terminal_result.success,
                        "returncode": terminal_result.returncode,
                    },
                )
        elif response.done:
            observation_parts.append(f"Task complete: {assistant_content}")
            log_main("done")
        else:
            observation_parts.append(assistant_content or "Continuing…")

        observation = "\n".join(observation_parts)

        new_errors: list[str] = []
        if terminal_result and not terminal_result.success:
            error_entry = f"cmd=`{response.command[:80]}` stderr=`{terminal_result.stderr.strip()[:200]}`"
            new_errors.append(error_entry)

        update: MainAgentState = {
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
            update["final_answer"] = assistant_content or observation
            update["status"] = "done"
        elif step_num >= state["max_steps"]:
            update["final_answer"] = observation
            update["status"] = "failed"
            log_main("max steps reached")

        return update

    return react


def _route_after_react(state: MainAgentState) -> Literal["react", "end"]:
    if state["status"] in {"done", "failed"} or state["step"] >= state["max_steps"]:
        return "end"
    return "react"


def build_main_agent_graph(llm: ChatOpenAI, tracer: TraceLogger):
    graph = StateGraph(MainAgentState)
    graph.add_node("react", _create_react_node(llm, tracer))
    graph.set_entry_point("react")
    graph.add_conditional_edges("react", _route_after_react, {"react": "react", "end": END})
    return graph.compile()


async def run_main_agent(task: str, max_steps: int = MAX_REACT_STEPS) -> dict:
    if not os.getenv("OPENAI_API_KEY"):
        raise RuntimeError("OPENAI_API_KEY is not set. Add it to .env at project root.")

    run_id = uuid.uuid4().hex[:12]
    tracer = TraceLogger(run_id=run_id, agent_id="main")
    tracer.log("run_start", {"task": task})
    run_start(run_id, task)

    env_context = _gather_environment_context()

    llm = ChatOpenAI(model=MODEL_NAME, temperature=0)
    graph = build_main_agent_graph(llm, tracer)

    initial_state: MainAgentState = {
        "task": task,
        "run_id": run_id,
        "loaded_skill": None,
        "pending_skill_name": None,
        "messages": [
            SystemMessage(content=_main_system_prompt(env_context)),
            HumanMessage(content=f"User task: {task}"),
        ],
        "observations": [],
        "error_history": [],
        "subagent_results": [],
        "step": 0,
        "max_steps": max_steps,
        "final_answer": "",
        "status": "running",
    }

    final_state = await graph.ainvoke(initial_state)
    loaded = final_state.get("loaded_skill")
    output = {
        "run_id": run_id,
        "task": task,
        "status": final_state.get("status", "done"),
        "skill_used": loaded.name if loaded else None,
        "subagent_results": final_state.get("subagent_results", []),
        "final_answer": final_state.get("final_answer", ""),
        "trace_file": str(tracer.trace_path),
    }
    tracer.log("run_complete", output)
    return output


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the main LangGraph orchestrator agent.")
    parser.add_argument("task", nargs="?", help="Task prompt for the agent")
    parser.add_argument("--max-steps", type=int, default=MAX_REACT_STEPS)
    args = parser.parse_args()

    task = args.task or input("Enter task: ").strip()
    if not task:
        raise SystemExit("Task is required.")

    result = asyncio.run(run_main_agent(task, max_steps=args.max_steps))
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
