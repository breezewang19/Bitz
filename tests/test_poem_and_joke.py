"""测试：并行创建两个 SubAgent - 一个生成诗歌，一个生成冷笑话"""
import os
import sys

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

from agent.adapter import LLMAdapter
from agent.tools import ToolRegistry
from agent.subagent import SubAgentPool


def create_base_tools():
    """创建精简版工具集（生成文件和读取目录）"""
    tools = ToolRegistry()
    
    # 写文件工具
    tools.register(
        name="write_file",
        description="在指定路径创建文件并写入内容",
        input_schema={
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "文件路径"},
                "content": {"type": "string", "description": "文件内容"}
            },
            "required": ["path", "content"]
        },
        handler=lambda path, content: _write_file(path, content)
    )
    
    # 读目录工具
    tools.register(
        name="list_directory",
        description="列出目录中的文件和文件夹",
        input_schema={
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "目录路径"}
            },
            "required": ["path"]
        },
        handler=lambda path: _list_dir(path)
    )
    
    return tools


def _write_file(path, content):
    """写入文件"""
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, 'w', encoding='utf-8') as f:
            f.write(content)
        return f"文件已创建: {path}"
    except Exception as e:
        return f"创建文件失败: {e}"


def _list_dir(path):
    """列出目录"""
    try:
        items = os.listdir(path)
        return "\n".join(items) if items else "目录为空"
    except Exception as e:
        return f"读取目录失败: {e}"


def main():
    print("=" * 60)
    print("SubAgent 并行执行测试: 生成诗歌和冷笑话")
    print("=" * 60)
    
    # 创建 LLM 适配器
    api_key = os.getenv("ANTHROPIC_API_KEY")
    base_url = os.getenv("ANTHROPIC_BASE_URL", "https://api.minimaxi.com/anthropic")
    model = os.getenv("ANTHROPIC_MODEL", "MiniMax-M2.7")
    
    llm_adapter = LLMAdapter(api_key=api_key, base_url=base_url, model=model)
    
    # 创建工具集
    base_tools = create_base_tools()
    
    # 创建 SubAgent 池
    pool = SubAgentPool(
        llm_adapter=llm_adapter,
        base_tools=base_tools,
        max_parallel=2,
        timeout=60
    )
    
    # 定义两个任务
    tasks = [
        "在 tests/output 目录下创建一首中文诗歌文件 poem.txt，诗歌要有意境，包含四季元素（春、夏、秋、冬），至少4段",
        "在 tests/output 目录下创建一个冷笑话文件 joke.txt，内容是一个程序员相关的冷笑话，不少于3句话"
    ]
    
    print("\n准备执行以下任务:")
    for i, task in enumerate(tasks, 1):
        print(f"  {i}. {task}")
    print()
    
    # 并行执行
    print("开始并行执行...")
    print("-" * 60)
    
    results = pool.spawn(tasks, depth=1)
    
    print("执行完成!")
    print("=" * 60)
    
    # 格式化输出结果
    output = pool.format_results(tasks, results)
    print(output)
    
    # 验证文件是否创建成功
    print("\n验证生成的文件:")
    print("-" * 60)
    
    output_dir = "tests/output"
    if os.path.exists(output_dir):
        for filename in ["poem.txt", "joke.txt"]:
            filepath = os.path.join(output_dir, filename)
            if os.path.exists(filepath):
                print(f"\n[{filename}] 内容:")
                print(read_file_simple(filepath))
            else:
                print(f"  {filename} 未创建")
    else:
        print(f"  输出目录不存在: {output_dir}")


def read_file_simple(path):
    """简单读取文件"""
    with open(path, 'r', encoding='utf-8') as f:
        return f.read().strip()


if __name__ == "__main__":
    main()
