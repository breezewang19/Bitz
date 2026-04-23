# agent/loop.py
"""Agent 核心循环 - Anthropic 协议"""
from agent.context import Context
from agent.adapter import LLMAdapter, LLMResponse
from agent.subagent import SubAgentPool


class Agent:
    """Agent 主循环"""

    def __init__(self, llm_adapter: LLMAdapter, tools, context: Context, max_steps: int = 10):
        self.llm_adapter = llm_adapter
        self.tools = tools
        self.context = context
        self.max_steps = max_steps

    def run(self, user_input: str) -> str:
        """核心循环"""
        self.context.add_user(user_input)

        for step in range(self.max_steps):
            messages = self.context.get_messages()
            tools = self.tools.list_for_llm() if hasattr(self.tools, 'list_for_llm') else []

            response = self.llm_adapter.chat(messages, tools)

            if response.stop_reason == "end_turn":
                return response.content

            if response.stop_reason == "tool_use":
                # 添加 assistant 的 tool_use 消息到 context
                self.context.add_assistant_message(response.content)

                # 执行工具并添加结果
                for tool_use in response.content:
                    tool_name = tool_use["name"]
                    tool_args = tool_use["input"]
                    tool_id = tool_use["id"]

                    result = self.tools.execute(tool_name, tool_args)
                    self.context.add_tool_result(tool_id, result)
                continue

        return f"Error: Exceeded max_steps ({self.max_steps})"


def create_spawn_tools(llm_adapter, base_tools):
    """
    创建 spawn_subagents 工具（仅主 Agent 可用）

    SubAgentPool 使用精简版 tools（无 spawn_subagents），防止递归。
    """
    from agent.tools import ToolRegistry

    pool = SubAgentPool(llm_adapter=llm_adapter, base_tools=base_tools, max_parallel=5)

    def spawn_subagents_handler(tasks: list[str], depth: int = 0) -> str:
        """
        并行执行多个子任务

        Args:
            tasks: 子任务列表
            depth: 深度标识（主 Agent 调用时为 0）

        Returns:
            格式化后的结果
        """
        # 防护：SubAgent 不应调用此工具
        if depth > 0:
            return "[错误] SubAgent 不可拆分任务"

        # 防护：超限检查
        if len(tasks) > 5:
            return f"[错误] 任务数量 {len(tasks)} 超过限制 (5)"

        results = pool.spawn(tasks, depth=depth)
        return pool.format_results(tasks, results)

    tools = ToolRegistry()

    # 注册 spawn_subagents（只有主 Agent 有这个工具）
    tools.register(
        name="spawn_subagents",
        description="并行执行多个子任务，每个子任务由独立 Agent 处理",
        input_schema={
            "type": "object",
            "properties": {
                "tasks": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "子任务列表（最多5个）"
                },
                "depth": {
                    "type": "integer",
                    "description": "深度标识（内部使用）",
                    "default": 0
                }
            },
            "required": ["tasks"]
        },
        handler=spawn_subagents_handler
    )

    # 保留 base_tools 中的工具
    for name, tool in base_tools.tools.items():
        tools.register(
            name=tool.name,
            description=tool.description,
            input_schema=tool.input_schema,
            handler=tool.handler
        )

    return tools
