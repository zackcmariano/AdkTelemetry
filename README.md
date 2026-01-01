# 🧠 Oraicle-Agent

> **Turn any Google-ADK Agent into a Root Agent - instantly.**

Oraicle-Agent is a **groundbreaking Python library** that extends the Google Agent Development Kit (Google-ADK), enabling **any agent to become a `root_agent` dynamically**, without hacks, forks, or duplicated apps.

This unlocks a **new architectural paradigm** for multi-agent systems:
- Multiple conversational entrypoints
- Direct chat with sub-agents
- True Agent-to-Agent (A2A) orchestration
- Seamless deployment on **Vertex AI Agent Engine**

---

## 🚀 Why Oraicle-Agent exists

Google-ADK assumes:
- One `root_agent` per application
- Sub-agents can’t be direct entrypoints
- One conversational domain per deployment

**Oraicle-Agent breaks this limitation - intentionally and cleanly.**

With Oraicle-Agent, **any agent can become the root of a conversation**, while still participating in a larger A2A system.

> 🔥 This is not a hack.  
> 🔥 This is not a fork.  
> 🔥 This is a new abstraction layer.

---

## ✨ What makes Oraicle-Agent unique?

### ✅ Dynamic Root Agents
Choose *at runtime* which agent owns the conversation.

### ✅ Direct Sub-Agent Chat
Users can talk directly to a specialized agent (teacher, assistant, expert) **without losing context isolation**.

### ✅ A2A-First Architecture
Root agents orchestrate other agents, while still being callable as standalone conversational entities.

### ✅ Google-ADK & Vertex AI Compatible
Works with:
- `adk web`
- ADK loader
- Vertex AI Agent Engine

---

## 🧩 The core idea (one line)

> **Any `Agent` can be a `root_agent` if it is explicitly declared as one.**

Oraicle-Agent formalizes this idea.

---

## 📦 Installation

```bash
pip install oraicle
```

---

## ⚡ Quick Start

```python
from oraicle import autoagent
from google.adk.agents import Agent

history_teacher = Agent(
    name="history_teacher",
    model="gemini-2.0-flash",
    instruction="You are a history teacher."
)

autoagent(history_teacher)
```

---

## ☁️ Deploying to Vertex AI Agent Engine

```python
from app.sub_agents.history_teacher.agent import history_teacher
```

---

## 📄 License

MIT License © 2026  
Built with 🤖 for the GenAI community.