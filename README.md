# Minimal Agent

A lightweight AI agent framework with tool use support.

## Features

- OpenAI-compatible LLM adapter
- Tool registry for extensible tools
- Context management with message trimming
- Agent loop with tool execution
- FastAPI backend with SSE streaming
- Simple web UI

## Quick Start

1. Install dependencies:
```bash
pip install -r requirements.txt
```

2. Configure environment:
```bash
cp .env.example .env
# Edit .env with your API key and settings
```

3. Run the server:
```bash
python main.py
```

4. Open http://localhost:8000 in your browser

## Architecture

- `agent/adapter.py` - LLM adapter (OpenAI compatible)
- `agent/context.py` - Session context management
- `agent/loop.py` - Agent core loop
- `agent/tools.py` - Tool registry
- `api/server.py` - FastAPI SSE backend
- `static/index.html` - Web UI

## Available Tools

- `bash` - Execute bash commands
- `read_file` - Read file contents

## Testing

```bash
pytest -v
```
