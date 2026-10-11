"""H5 Tool guard (BUILD_SPEC §11.3, plan decision c). Owning session, active run only.

- Skill, WebFetch and every mcp__* tool: blocked for every caller.
- WebSearch: blocked in the main session; allowed only for the installed researcher variant.
- Agent (also its legacy name Task): allowed only for the nine workflow agents, and only
  from the main session.
- Any other tool not in RUN_TOOLS is blocked too, so tools that can run commands or start
  work outside the workflow (for example Monitor, Workflow, CronCreate) cannot bypass H1.
"""

from __future__ import annotations

from _common import Deny, HookContext, workflow_agents

EXPLICITLY_BLOCKED = ("Skill", "WebFetch")
AGENT_TOOLS = ("Agent", "Task")
RUN_TOOLS = frozenset(
    {
        "Read", "Glob", "Grep", "LS", "NotebookRead",
        "Write", "Edit", "MultiEdit", "NotebookEdit",   # governed by H2
        "Bash",                                          # governed by H1
        "Agent", "Task",                                 # checked below
        "WebSearch",                                     # checked below, then H3/H4
        "TodoWrite", "TaskCreate", "TaskUpdate", "TaskList", "TaskGet", "ToolSearch",
    }
)


def check(ctx: HookContext) -> None:
    tool = ctx.payload.get("tool_name") or ""
    agent = ctx.agent_type
    if tool in EXPLICITLY_BLOCKED or tool.startswith("mcp__"):
        raise Deny("H5", f"{tool} is blocked during a feature-research run")
    if tool == "WebSearch":
        installed = (ctx.setup or {}).get("researcher_variant")
        if agent is None:
            raise Deny("H5", "WebSearch is blocked in the main session during a run; only the researcher searches")
        if agent != installed:
            raise Deny("H5", f"WebSearch is allowed only for {installed}, not {agent}")
        return
    if tool in AGENT_TOOLS:
        if agent is not None:
            raise Deny("H5", "subagents may not start other agents during a run")
        ti = ctx.payload.get("tool_input") or {}
        sub = ti.get("subagent_type")
        allowed = workflow_agents(ctx.setup)
        if sub not in allowed:
            raise Deny("H5", f"only workflow agents may run during a run ({', '.join(allowed)}); got {sub!r}")
        return
    if tool not in RUN_TOOLS:
        raise Deny("H5", f"{tool} is not permitted during a feature-research run")
