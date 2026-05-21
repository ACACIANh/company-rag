"""LangChain ReAct Agent — uses langgraph.prebuilt.create_react_agent (langchain >= 1.0)."""

from __future__ import annotations

from typing import Any

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langgraph.prebuilt import create_react_agent

_REACT_SYSTEM_PROMPT = """\
당신은 회사 내부 문서 전문가입니다. 주어진 도구를 활용하여 질문에 답하세요."""


class _AgentExecutorCompat:
    """AgentExecutor-compatible wrapper around langgraph create_react_agent.

    Provides the same interface used by qa.py:
      executor.invoke({"input": question})
        -> {"output": str, "intermediate_steps": [(action_obj, observation), ...]}
    """

    def __init__(self, graph: Any) -> None:
        self._graph = graph

    def invoke(self, inputs: dict[str, Any]) -> dict[str, Any]:
        question = inputs["input"]
        result = self._graph.invoke({"messages": [HumanMessage(content=question)]})
        messages = result.get("messages", [])

        # Extract final answer from last AIMessage
        output = ""
        for msg in reversed(messages):
            if isinstance(msg, AIMessage) and msg.content:
                output = msg.content if isinstance(msg.content, str) else str(msg.content)
                break

        # Build intermediate_steps from tool call / observation pairs
        intermediate_steps: list[tuple[Any, str]] = []
        i = 0
        while i < len(messages):
            msg = messages[i]
            if isinstance(msg, AIMessage) and msg.tool_calls:
                for tool_call in msg.tool_calls:
                    # Find the corresponding ToolMessage
                    observation = ""
                    for j in range(i + 1, len(messages)):
                        if (
                            isinstance(messages[j], ToolMessage)
                            and messages[j].tool_call_id == tool_call["id"]
                        ):
                            observation = str(messages[j].content)
                            break

                    class _Action:
                        def __init__(
                            self, log: str, tool: str, tool_input: str
                        ) -> None:
                            self.log = log
                            self.tool = tool
                            self.tool_input = tool_input

                    action_obj = _Action(
                        log=f"Calling tool: {tool_call['name']}",
                        tool=tool_call["name"],
                        tool_input=str(tool_call.get("args", {})),
                    )
                    intermediate_steps.append((action_obj, observation))
            i += 1

        return {"output": output, "intermediate_steps": intermediate_steps}


def build_agent_executor(llm_adapter: Any, tools: list) -> _AgentExecutorCompat:
    """Return an AgentExecutor-compatible object using langgraph create_react_agent."""
    graph = create_react_agent(llm_adapter, tools, prompt=_REACT_SYSTEM_PROMPT)
    return _AgentExecutorCompat(graph=graph)
