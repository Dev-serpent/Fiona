# Fiona AI Agents

This directory contains all Fiona agent definitions. Each agent is a single Markdown (`.md`) file with YAML front matter.

## Adding an Agent

Create a new `.md` file in this directory (or in a subdirectory). No code changes are required — Fiona's Agent Manager discovers and registers agents automatically.

## Agent File Format

```markdown
---
name: agent-name
version: 1.0.0
description: What this agent does
author: Fiona
tags: [tag1, tag2]
capabilities:
  - capability1
  - capability2
supported_tasks:
  - task description 1
  - task description 2
preferred_tools:
  - tool_name_1
  - tool_name_2
restrictions:
  - restriction 1
  - restriction 2
examples:
  - query: "Example user input"
    response: "Expected agent output"
confidence_threshold: 0.7
dependencies:
  - skill-name
skills:
  - skill-name
model_override: null
---

The rest of this file is the system prompt. It is only used if `system_prompt` is
not explicitly set in the front matter above.
```

## Field Reference

| Field | Required | Description |
|-------|----------|-------------|
| `name` | Yes | Unique identifier (lowercase, hyphenated) |
| `version` | Yes | Semantic version string |
| `description` | Yes | Short description of the agent's role |
| `author` | No | Author name (default: "Fiona") |
| `tags` | No | List of searchable tags |
| `capabilities` | No | What this agent can do |
| `supported_tasks` | No | Specific task descriptions |
| `preferred_tools` | No | Tool names this agent prefers to use |
| `restrictions` | No | Rules/limitations for this agent |
| `examples` | No | Example interactions |
| `confidence_threshold` | No | Minimum confidence (0.0-1.0, default: 0.7) |
| `dependencies` | No | Required skills or other agents |
| `skills` | No | Skills this agent composes |
| `model_override` | No | Specific LLM model for this agent |
| `system_prompt` | No | System prompt (default: file body) |
| `conversational_prompt` | No | Alternative prompt for casual chat |

## Built-in Agents

The `builtins/` subdirectory contains the 6 built-in agents that ship with Fiona.
These are registered at startup and provide backward compatibility with the
Personality-based API.
