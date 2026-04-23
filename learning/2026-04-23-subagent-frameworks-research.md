# Agent Framework Subagent/Parallel Agent Implementation Research

## Overview

Research into how major agent frameworks implement subagents, parallel execution, context management, and recursion prevention.

---

## 1. LangGraph

### Architecture
- **Graph-based framework** with nodes (Python functions) and edges
- State managed through a central `State` object (dict or Pydantic model)
- Supports **cycles** for agentic loops (unlike typical DAG workflows)

### Parallel Execution
- Uses `Send` API for fan-out parallel execution
- `add_conditional_edges` enables dynamic routing to multiple nodes
- **Reducer functions** (via `Annotated[...]`) combine outputs from parallel branches

```python
from typing import Annotated
from langgraph.graph import StateGraph

class State(TypedDict):
    joke: str
    poem: str
    combined_output: str

# Parallel nodes called via Send API
def call_llm_1(state: State):
    return {"joke": llm.invoke(f"Joke about {state['topic']}")}
```

### Context Isolation vs Sharing
- **Shared state** across all nodes via single State object
- Nodes receive full state, return partial updates
- Reducers merge updates from parallel branches

### Recursion Prevention
- **No built-in mechanism** - developer must implement via:
  - Max iteration counters in state
  - Conditional edges that route to END based on count
  - External orchestration layer

### Limitations
- Steep learning curve for complex graphs
- Debugging larger graphs challenging
- Manual management of execution flow

---

## 2. AutoGen (Microsoft)

### Architecture
- Agent-based conversation system
- **GroupChatManager** orchestrates multi-agent conversations
- Supports nested agent hierarchies through **Team** concept

### Parallel/Subagent Implementation
- **Selector GroupChat**: Selects next speaker from agent pool
- **Nested Teams**: Teams can contain sub-teams
- Agent groups converse until termination condition met

```python
# GroupChat pattern
from autogen.agentchat import GroupChat, GroupChatManager

group_chat = GroupChat(agents=[agent1, agent2, agent3])
manager = GroupChatManager(groupchat=group_chat)
```

### Context Management
- **Implicit session state** via conversation history
- Messages passed through shared group chat
- Can pass explicit context via function parameters

### Recursion Prevention
- **Termination conditions** (message count, time limits)
- `max_round` parameter in GroupChat
- Speaker selection can be constrained to prevent loops

### Limitations
- Complex setup for simple workflows
- Requires careful management of conversation flow
- Limited visibility into internal agent reasoning

---

## 3. CrewAI

### Architecture
- **Crew/Agent/Task/Tool** hierarchy
- **Process** modes: Sequential, Hierarchical, Parallel

### Parallel/Subagent Implementation
- **Sequential Process**: Tasks execute in order, output feeds next
- **Hierarchical Process**: Manager agent delegates tasks to worker agents
- `allow_delegation=True` flag enables agent-to-agent task delegation

```python
# Hierarchical process
researcher = Agent(role="Researcher", allow_delegation=True)
writer = Agent(role="Writer")

crew = Crew(agents=[researcher, writer], process=Process.hierarchical)
```

### Context Management
- Task **context** parameter passes previous task outputs
- `context=[task1, task2]` chains outputs between tasks
- Agent **memory** feature stores conversation history
- Verbose mode exposes agent reasoning

### Recursion Prevention
- **No explicit recursion prevention**
- Delegation controlled via `allow_delegation` flag
- Process structure (sequential/hierarchical) limits arbitrary nesting

### Limitations
- Limited parallel execution options
- Context window management challenging
- Delegation can create implicit loops without visibility

---

## 4. OpenAI Swarm

### Architecture
- **Lightweight, educational framework** (not production-grade)
- Two primitives: **Agents** and **Handoffs**
- Stateless orchestration - no built-in state management

### Subagent Implementation
- Agents are self-contained with instructions and tools
- **Handoffs** transfer control between agents
- Agent functions can return handoff instructions

```python
from swarm import Swarm, Agent

def transfer_to_b():
    return agent_b

agent_a = Agent(name="Agent A", instructions="...", functions=[transfer_to_b])
```

### Context Management
- **No implicit context sharing** - developers manage explicitly
- Messages passed directly to `client.run()`
- Each agent receives its own instruction set

### Recursion Prevention
- **Developer responsibility entirely**
- No built-in limits on handoff chains
- Must implement external safeguards

### Limitations
- Experimental, not for production use
- No persistence, memory, or complex state
- Limited tooling ecosystem

---

## 5. LlamaIndex

### Subagent Concepts
- **AgentRunner** architecture with hierarchical agents
- **Sub-Agent** functionality via `SubAgent` class
- Supports nested agent execution for specialized tasks

### Key Patterns
- Tool use and task decomposition built-in
- Context passing through agent hierarchy
- Query planning for multi-step tasks

---

## Common Patterns & Innovations

### Architectural Patterns
1. **Graph/State Machine**: LangGraph - flexible cycles and conditions
2. **Team Hierarchy**: AutoGen - nested agent groups with management
3. **Crew/Role Assignment**: CrewAI - explicit role-based delegation
4. **Handoff/Transfer**: Swarm - explicit control transfer primitives

### Context Management Approaches
| Framework | Approach |
|-----------|----------|
| LangGraph | Centralized state with reducer merges |
| AutoGen | Implicit conversation history |
| CrewAI | Task context chaining + agent memory |
| Swarm | Developer-managed stateless |

### Recursion Prevention Mechanisms
| Framework | Mechanism |
|-----------|------------|
| LangGraph | Counter-based conditional edges (manual) |
| AutoGen | max_round, termination conditions |
| CrewAI | allow_delegation flag, process constraints |
| Swarm | None (developer responsibility) |

---

## Key Findings

1. **No universal solution** for recursion prevention - each framework handles differently (or not at all)

2. **Context isolation varies**: From fully shared (LangGraph) to fully isolated (Swarm)

3. **Parallel execution patterns**: Send API (LangGraph), GroupChat (AutoGen), Process modes (CrewAI)

4. **Subagent depth limits**: Most frameworks rely on developer discipline; only AutoGen has structured termination

5. **Memory management**: Growing concern as agent conversations grow - frameworks adding memory/context summarization features

---

## Recommendations

- **For complex workflows**: LangGraph (flexibility) or AutoGen (structure)
- **For team-based tasks**: CrewAI (role-based, clear delegation)
- **For education/prototyping**: Swarm (minimal overhead)
- **Always implement**: Max iteration limits, depth counters, and timeout mechanisms regardless of framework
