"""LangChain ReAct Agent — compatible with langchain >=1.0 (LangGraph-based)."""

from __future__ import annotations

import re
from typing import Any

from langchain_core.tools import BaseTool

_REACT_SYSTEM_PROMPT = """\
당신은 회사 내부 문서 전문가입니다. 주어진 도구를 활용하여 질문에 답하세요.

사용 가능한 도구:
{tools}

형식:
Question: 답해야 할 질문
Thought: 어떻게 접근할지 생각합니다
Action: [{tool_names}] 중 하나
Action Input: 도구에 전달할 입력
Observation: 도구 실행 결과
... (Thought/Action/Action Input/Observation 반복 가능)
Thought: 최종 답변을 알았습니다
Final Answer: 최종 답변

시작!

Question: {input}
Thought:"""


class _AgentExecutorCompat:
    """AgentExecutor-compatible wrapper that runs a simple ReAct loop.

    Provides the same interface used by qa.py:
      executor.invoke({"input": question})
        -> {"output": str, "intermediate_steps": [(action_obj, observation), ...]}
    """

    def __init__(self, llm_adapter: Any, tools: list[BaseTool]) -> None:
        self._llm = llm_adapter
        self._tools: dict[str, BaseTool] = {t.name: t for t in tools}
        self._max_iterations = 5

    def invoke(self, inputs: dict[str, Any]) -> dict[str, Any]:
        question = inputs["input"]
        tool_desc = "\n".join(
            f"- {name}: {tool.description}"
            for name, tool in self._tools.items()
        )
        tool_names = ", ".join(self._tools.keys())

        prompt = _REACT_SYSTEM_PROMPT.format(
            tools=tool_desc,
            tool_names=tool_names,
            input=question,
        )
        scratchpad = ""
        intermediate_steps: list[tuple[Any, str]] = []

        for _ in range(self._max_iterations):
            response = self._llm.invoke(prompt + scratchpad)
            # response may be a string or an AIMessage; normalise to str
            text = response.content if hasattr(response, "content") else str(response)

            # Check for Final Answer
            if "Final Answer:" in text:
                final = text.split("Final Answer:")[-1].strip()
                return {"output": final, "intermediate_steps": intermediate_steps}

            # Parse Action / Action Input
            action_match = re.search(r"Action:\s*(.+)", text)
            input_match = re.search(r"Action Input:\s*(.+)", text)

            if not action_match or not input_match:
                # No parseable action — return what we have
                return {"output": text.strip(), "intermediate_steps": intermediate_steps}

            tool_name = action_match.group(1).strip()
            tool_input = input_match.group(1).strip()

            if tool_name not in self._tools:
                observation = f"Error: unknown tool '{tool_name}'"
            else:
                observation = self._tools[tool_name].invoke(tool_input)

            # Build a lightweight action object compatible with qa.py trace extraction
            class _Action:
                def __init__(self, log: str, tool: str, tool_input: str) -> None:
                    self.log = log
                    self.tool = tool
                    self.tool_input = tool_input

            action_obj = _Action(
                log=text.strip(),
                tool=tool_name,
                tool_input=tool_input,
            )
            intermediate_steps.append((action_obj, observation))
            scratchpad += (
                f"\nAction: {tool_name}\nAction Input: {tool_input}"
                f"\nObservation: {observation}\nThought:"
            )

        # Exhausted iterations
        return {
            "output": "최대 반복 횟수에 도달했습니다. 충분한 정보를 찾지 못했습니다.",
            "intermediate_steps": intermediate_steps,
        }


def build_agent_executor(llm_adapter: Any, tools: list) -> _AgentExecutorCompat:
    """Return an AgentExecutor-compatible object using a ReAct loop."""
    return _AgentExecutorCompat(llm_adapter=llm_adapter, tools=tools)
