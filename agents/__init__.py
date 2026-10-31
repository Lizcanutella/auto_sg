"""Agents (workstream C). Use `make_agent` or `protocol.mediator.build_agents`."""
from agents.base import Agent, Context, Draft
from agents.scripted import MisreportingAgent, ScriptedAgent


def make_agent(strategy: str, view, role, params, acceptance: str = "budget", **kw) -> Agent:
    if strategy == "scripted":
        return ScriptedAgent(view, role, params, acceptance)
    if strategy == "misreporting":
        return MisreportingAgent(view, role, params, acceptance)
    if strategy == "llm":
        from agents.llm import LLMAgent
        return LLMAgent(view, role, params, acceptance, **kw)
    raise ValueError(f"unknown strategy {strategy!r}")


__all__ = ["Agent", "Context", "Draft", "MisreportingAgent", "ScriptedAgent", "make_agent"]
