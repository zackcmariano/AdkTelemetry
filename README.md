# 🧠 Oraicle

> **Turn any Google-ADK Agent into a Root Agent — instantly.**

Oraicle is a **groundbreaking Python library** that extends the Google Agent Development Kit (Google-ADK), enabling **any agent to become a `root_agent` dynamically**, without hacks, forks, or duplicated apps.

This unlocks a **new architectural paradigm** for multi-agent systems:
- Multiple conversational entrypoints
- Direct chat with sub-agents
- True Agent-to-Agent (A2A) orchestration
- Seamless deployment on **Vertex AI Agent Engine**

---

## 🚀 Why Oraicle exists

Google-ADK assumes:
- One `root_agent` per application
- Sub-agents can’t be direct entrypoints
- One conversational domain per deployment

**Oraicle breaks this limitation — intentionally and cleanly.**

With Oraicle, **any agent can become the root of a conversation**, while still participating in a larger A2A system.

> 🔥 This is not a hack.  
> 🔥 This is not a fork.  
> 🔥 This is a new abstraction layer.

---

## ✨ What makes Oraicle unique?

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

Oraicle formalizes this idea.

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

professor_historia = Agent(
    name="professor_historia",
    model="gemini-2.0-flash",
    instruction="You are a history teacher."
)

autoagent(professor_historia)
```

---

## ☁️ Deploying to Vertex AI Agent Engine

```python
from oraicle.adk.loader_patch import root_agent
```

---

## 📄 License

MIT License © 2025  
Built with ❤️ for the GenAI community.