# api/server.py
"""FastAPI SSE 后端"""
import os
import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, HTMLResponse, StreamingResponse
from dotenv import load_dotenv

load_dotenv()

from agent.adapter import LLMAdapter
from agent.context import Context
from agent.loop import Agent
from agent.tools import ToolRegistry

# 全局 agent 实例
_agent: Agent = None
_tool_registry: ToolRegistry = None


def get_tool_registry() -> ToolRegistry:
    """获取工具注册表（延迟初始化）"""
    global _tool_registry
    if _tool_registry is None:
        _tool_registry = ToolRegistry()

        # 注册 bash 工具
        def bash_handler(command: str) -> str:
            import subprocess
            try:
                result = subprocess.run(
                    command, shell=True, capture_output=True, text=True, timeout=30
                )
                return result.stdout or result.stderr or "(no output)"
            except Exception as e:
                return f"Error: {e}"

        _tool_registry.register(
            name="bash",
            description="Execute a bash command and return the output",
            input_schema={
                "type": "object",
                "properties": {
                    "command": {"type": "string", "description": "The bash command to execute"}
                },
                "required": ["command"]
            },
            handler=bash_handler
        )

        # 注册 read_file 工具
        def read_file_handler(path: str) -> str:
            try:
                with open(path, "r", encoding="utf-8") as f:
                    return f.read()
            except Exception as e:
                return f"Error: {e}"

        _tool_registry.register(
            name="read_file",
            description="Read the contents of a file",
            input_schema={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Path to the file to read"}
                },
                "required": ["path"]
            },
            handler=read_file_handler
        )

    return _tool_registry


def get_agent() -> Agent:
    """获取 Agent 实例（延迟初始化）"""
    global _agent
    if _agent is None:
        api_key = os.getenv("OPENAI_API_KEY", "sk-test")
        base_url = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
        model = os.getenv("OPENAI_MODEL", "gpt-4o")

        adapter = LLMAdapter(api_key=api_key, base_url=base_url, model=model)
        context = Context(
            system_prompt="You are a helpful coding assistant.",
            max_tokens=4096,
            keep_last_n=20
        )
        _agent = Agent(
            llm_adapter=adapter,
            tools=get_tool_registry(),
            context=context,
            max_steps=20
        )
    return _agent


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期"""
    # 启动时初始化
    get_agent()
    get_tool_registry()
    yield
    # 关闭时清理


app = FastAPI(title="Minimal Agent", lifespan=lifespan)


@app.get("/", response_class=FileResponse)
async def index():
    """返回前端页面"""
    return FileResponse("static/index.html")


@app.get("/stream")
async def stream(question: str):
    """SSE 流式响应"""
    async def generate():
        yield f"data: {{\"type\": \"status\", \"content\": \"Thinking...\"}}\n\n"

        try:
            agent = get_agent()
            result = agent.run(question)
            yield f"data: {{\"type\": \"result\", \"content\": {repr(result)}}}\n\n"
        except Exception as e:
            yield f"data: {{\"type\": \"error\", \"content\": {repr(str(e))}}}\n\n"

        yield f"data: {{\"type\": \"done\"}}\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream")
