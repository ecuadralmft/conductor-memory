# Conductor Memory

MCP server for persistent workspace memory across AI chat sessions.

Built for [Kiro CLI](https://github.com/aws/kiro-cli) — works with any MCP-compatible client.

## What It Does

Conductor Memory gives AI agents persistent, structured memory that survives across sessions. Instead of starting from zero every time, agents load previous decisions, learnings, and project context automatically.

### Memory Tiers

| Tier | Purpose | Write Mode |
|------|---------|------------|
| `project` | Tech stack, structure, conventions | Freeform, overwrite OK |
| `decisions` | Architectural decisions with rationale | Append-only |
| `learnings` | Patterns, gotchas, agent notes | Append-only |
| `active` | Last session state, next steps | Overwrite at session end |
| `glossary` | Domain terms, abbreviations | Append-only |

## Prerequisites

- Python 3.10+
- [Kiro CLI](https://github.com/aws/kiro-cli) (or any MCP client)

## Install

```bash
git clone <this-repo-url>
cd conductor-memory
./install.sh
```

The installer will:
1. Copy the server to `~/.kiro/mcp/memory/`
2. Create a Python virtual environment and install dependencies
3. Register in `~/.kiro/settings/mcp.json`

Restart Kiro CLI after install.

### Manual Install

```bash
mkdir -p ~/.kiro/mcp/memory
cp mcp/server.py ~/.kiro/mcp/memory/
cp mcp/requirements.txt ~/.kiro/mcp/memory/

python3 -m venv ~/.kiro/mcp/memory/.venv
~/.kiro/mcp/memory/.venv/bin/pip install -r ~/.kiro/mcp/memory/requirements.txt

kiro-cli mcp add \
  --name memory \
  --scope default \
  --command ~/.kiro/mcp/memory/.venv/bin/python3 \
  --args ~/.kiro/mcp/memory/server.py
```

### Agent Access

Add `"includeMcpJson": true` to any agent config in `~/.kiro/agents/<name>.json` to give it memory access.

## Tools

### `memory_read`
Read from a specific tier or all tiers. Supports text search and last-N filtering.

| Param | Type | Default | Description |
|-------|------|---------|-------------|
| `tier` | string | required | `project`, `decisions`, `learnings`, `active`, `glossary`, or `all` |
| `search` | string | — | Filter entries containing this text |
| `last_n` | int | — | Return only the last N entries |

### `memory_write`
Write to a memory tier. Append-only tiers get timestamped entries with optional tags.

| Param | Type | Default | Description |
|-------|------|---------|-------------|
| `tier` | string | required | Target tier |
| `content` | string | required | Text to write |
| `mode` | string | `append` | `append` or `overwrite` (overwrite only for project/active) |
| `tags` | list[str] | — | Tags for searchability |
| `source` | string | — | Attribution (e.g., agent name, session ID) |

### `memory_search`
Search across all or specific tiers for a text pattern.

| Param | Type | Default | Description |
|-------|------|---------|-------------|
| `query` | string | required | Text to search for |
| `tiers` | list[str] | all | Tiers to search |

### `memory_compact`
Compact a tier to reduce size. Backs up the original first.

| Param | Type | Default | Description |
|-------|------|---------|-------------|
| `tier` | string | required | Tier to compact |
| `strategy` | string | `dedup` | `dedup` or `prune_older_than` |
| `days` | int | 30 | For prune strategy: remove entries older than N days |

### `memory_status`
Get health status of all memory tiers: existence, entry counts, sizes, compaction needs.

## Storage

Memory lives in `conductor/memory/` at the workspace root:

```
conductor/memory/
├── project.md
├── decisions.md
├── learnings.md
├── active.md
├── glossary.md
└── backups/        # Pre-compaction backups
```

All files are human-readable markdown. Git-trackable if desired.

## Entry Format

Append-only tiers use timestamped entries:

```markdown
---
date: 2026-04-09T18:45:00Z
tags: [architecture, database]
source: pickle-rick/session-xyz
---
Decision: Use PostgreSQL over SQLite for the API layer.
Rationale: Need concurrent writes and the dataset will exceed 10GB.
```

## File Structure

```
conductor-memory/
├── mcp/
│   ├── server.py          # MCP server (5 tools)
│   └── requirements.txt   # Python dependencies
├── install.sh             # One-command installer
├── .gitignore
└── README.md
```

## License

MIT
