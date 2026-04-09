"""Conductor Memory — MCP server for persistent workspace memory across sessions."""

import fcntl
import json
import os
import re
import shutil
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("memory")

TIERS = ("project", "decisions", "learnings", "active", "glossary")
APPEND_ONLY = ("decisions", "learnings", "glossary")
ENTRY_SEPARATOR = "\n\n---\n\n"
MAX_LINES_BEFORE_COMPACT_WARNING = 500


def _memory_dir(path: str | None = None) -> Path:
    """Resolve memory directory.

    Resolution order:
    1. Walk up from path/cwd to find existing conductor/memory/
    2. Walk up to find .git or .kiro and create conductor/memory/ there
    3. Fall back to ~/.kiro/memory/ (global, always available)
    """
    start = Path(path).resolve() if path else Path.cwd().resolve()
    # Walk up to find existing conductor/memory/ or a workspace root
    cur = start
    while cur != cur.parent:
        if (cur / "conductor" / "memory").exists():
            return cur / "conductor" / "memory"
        if (cur / ".git").exists() or (cur / ".kiro").exists():
            d = cur / "conductor" / "memory"
            d.mkdir(parents=True, exist_ok=True)
            (d / "backups").mkdir(exist_ok=True)
            return d
        cur = cur.parent
    # Global fallback: ~/.kiro/memory/
    d = Path.home() / ".kiro" / "memory"
    d.mkdir(parents=True, exist_ok=True)
    (d / "backups").mkdir(exist_ok=True)
    return d
    (d / "backups").mkdir(exist_ok=True)
    return d


def _tier_path(tier: str, mem_dir: Path | None = None) -> Path:
    d = mem_dir or _memory_dir()
    return d / f"{tier}.md"


def _read_tier(tier: str, mem_dir: Path | None = None) -> str:
    p = _tier_path(tier, mem_dir)
    if p.exists():
        return p.read_text()
    return ""


def _parse_entries(content: str) -> list[dict]:
    """Parse a tier's content into structured entries. Entries are separated by blank-line + --- + blank-line."""
    if not content.strip():
        return []
    # Split on the entry separator (blank line, ---, blank line) but not frontmatter ---
    raw = re.split(r'\n\n---\n\n', content)
    entries = []
    for block in raw:
        block = block.strip()
        if not block:
            continue
        entry = {"raw": block, "date": None, "tags": [], "source": None, "body": block}
        # Parse frontmatter: starts with --- and has a closing ---
        fm_match = re.match(r'^---\s*\n(.*?)\n---\s*\n(.*)', block, re.DOTALL)
        if fm_match:
            fm, body = fm_match.group(1), fm_match.group(2)
            entry["body"] = body.strip()
            for line in fm.splitlines():
                if line.startswith("date:"):
                    entry["date"] = line.split(":", 1)[1].strip()
                elif line.startswith("tags:"):
                    tags_str = line.split(":", 1)[1].strip().strip("[]")
                    entry["tags"] = [t.strip() for t in tags_str.split(",") if t.strip()]
                elif line.startswith("source:"):
                    entry["source"] = line.split(":", 1)[1].strip()
        entries.append(entry)
    return entries


def _format_entry(content: str, tags: list[str] | None = None, source: str | None = None) -> str:
    """Format a new entry with frontmatter."""
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    fm_lines = [f"date: {now}"]
    if tags:
        fm_lines.append(f"tags: [{', '.join(tags)}]")
    if source:
        fm_lines.append(f"source: {source}")
    fm = "\n".join(fm_lines)
    return f"---\n{fm}\n---\n{content}"


def _write_with_lock(path: Path, content: str, mode: str = "w") -> None:
    """Write to file with file-level locking."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, mode) as f:
        fcntl.flock(f.fileno(), fcntl.LOCK_EX)
        f.write(content)
        fcntl.flock(f.fileno(), fcntl.LOCK_UN)


def _backup(tier: str, mem_dir: Path) -> None:
    """Backup a tier before compaction."""
    src = _tier_path(tier, mem_dir)
    if not src.exists():
        return
    ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    dst = mem_dir / "backups" / f"{tier}-{ts}.md"
    shutil.copy2(src, dst)


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------

@mcp.tool()
def memory_read(
    tier: str,
    search: str | None = None,
    last_n: int | None = None,
) -> dict:
    """Read from workspace memory. Tiers: project, decisions, learnings, active, glossary, all."""
    mem_dir = _memory_dir()

    if tier == "all":
        combined = {}
        for t in TIERS:
            content = _read_tier(t, mem_dir)
            if content.strip():
                entries = _parse_entries(content) if t in APPEND_ONLY else []
                combined[t] = {
                    "content": content[:2000] + ("..." if len(content) > 2000 else ""),
                    "entries_count": len(entries) if entries else (1 if content.strip() else 0),
                }
        return {"tier": "all", "tiers": combined, "last_updated": datetime.now(timezone.utc).isoformat()}

    if tier not in TIERS:
        return {"error": f"Unknown tier: {tier}. Valid: {', '.join(TIERS)}, all"}

    content = _read_tier(tier, mem_dir)
    entries = _parse_entries(content) if tier in APPEND_ONLY else []

    if search and content:
        pattern = re.compile(re.escape(search), re.IGNORECASE)
        if entries:
            entries = [e for e in entries if pattern.search(e["raw"])]
            content = ENTRY_SEPARATOR.join(e["raw"] for e in entries)
        else:
            lines = content.splitlines()
            matched = [l for l in lines if pattern.search(l)]
            content = "\n".join(matched)

    if last_n and entries:
        entries = entries[-last_n:]
        content = ENTRY_SEPARATOR.join(e["raw"] for e in entries)

    p = _tier_path(tier, mem_dir)
    last_mod = datetime.fromtimestamp(p.stat().st_mtime, tz=timezone.utc).isoformat() if p.exists() else None

    return {
        "tier": tier,
        "content": content,
        "entries_count": len(entries) if entries else (1 if content.strip() else 0),
        "last_updated": last_mod,
    }


@mcp.tool()
def memory_write(
    tier: str,
    content: str,
    mode: str = "append",
    tags: list[str] | None = None,
    source: str | None = None,
) -> dict:
    """Write to workspace memory. Mode: append (default) or overwrite. Overwrite only allowed for project and active tiers."""
    if tier not in TIERS:
        return {"error": f"Unknown tier: {tier}. Valid: {', '.join(TIERS)}"}

    if mode == "overwrite" and tier in APPEND_ONLY:
        return {"error": f"Tier '{tier}' is append-only. Use mode='append'."}

    mem_dir = _memory_dir()
    p = _tier_path(tier, mem_dir)

    if mode == "overwrite":
        _write_with_lock(p, content + "\n")
    else:
        entry = _format_entry(content, tags, source)
        if p.exists() and p.read_text().strip():
            _write_with_lock(p, ENTRY_SEPARATOR + entry + "\n", mode="a")
        else:
            _write_with_lock(p, entry + "\n")

    # Count entries after write
    new_content = _read_tier(tier, mem_dir)
    entries = _parse_entries(new_content) if tier in APPEND_ONLY else []
    count = len(entries) if entries else (1 if new_content.strip() else 0)

    return {
        "success": True,
        "tier": tier,
        "entries_count": count,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@mcp.tool()
def memory_search(
    query: str,
    tiers: list[str] | None = None,
) -> dict:
    """Search across memory tiers for a text pattern."""
    search_tiers = tiers if tiers else list(TIERS)
    mem_dir = _memory_dir()
    pattern = re.compile(re.escape(query), re.IGNORECASE)
    results = []

    for tier in search_tiers:
        if tier not in TIERS:
            continue
        content = _read_tier(tier, mem_dir)
        if not content:
            continue
        for i, line in enumerate(content.splitlines(), 1):
            if pattern.search(line):
                # Get surrounding context
                lines = content.splitlines()
                start = max(0, i - 3)
                end = min(len(lines), i + 2)
                ctx = "\n".join(lines[start:end])
                results.append({
                    "tier": tier,
                    "line_number": i,
                    "content": line.strip(),
                    "context": ctx,
                })

    return {"results": results, "total_matches": len(results)}


@mcp.tool()
def memory_compact(
    tier: str,
    strategy: str = "dedup",
    days: int = 30,
) -> dict:
    """Compact a memory tier. Strategies: dedup (remove duplicates), prune_older_than (remove old entries)."""
    if tier not in TIERS:
        return {"error": f"Unknown tier: {tier}. Valid: {', '.join(TIERS)}"}
    if tier not in APPEND_ONLY:
        return {"error": f"Tier '{tier}' is freeform, not entry-based. Edit directly."}

    mem_dir = _memory_dir()
    content = _read_tier(tier, mem_dir)
    entries = _parse_entries(content)
    before = len(entries)

    if before == 0:
        return {"tier": tier, "entries_before": 0, "entries_after": 0, "compacted_at": datetime.now(timezone.utc).isoformat()}

    # Backup first
    _backup(tier, mem_dir)

    if strategy == "dedup":
        seen = set()
        unique = []
        for e in entries:
            key = e["body"].strip().lower()
            if key not in seen:
                seen.add(key)
                unique.append(e)
        entries = unique

    elif strategy == "prune_older_than":
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        kept = []
        for e in entries:
            if e["date"]:
                try:
                    entry_date = datetime.fromisoformat(e["date"].replace("Z", "+00:00"))
                    if entry_date >= cutoff:
                        kept.append(e)
                        continue
                except (ValueError, TypeError):
                    pass
            kept.append(e)  # Keep entries without parseable dates
        entries = kept

    else:
        return {"error": f"Unknown strategy: {strategy}. Valid: dedup, prune_older_than"}

    # Rewrite
    new_content = ENTRY_SEPARATOR.join(e["raw"] for e in entries)
    _write_with_lock(_tier_path(tier, mem_dir), new_content + "\n" if new_content else "")

    return {
        "tier": tier,
        "entries_before": before,
        "entries_after": len(entries),
        "compacted_at": datetime.now(timezone.utc).isoformat(),
    }


@mcp.tool()
def memory_status() -> dict:
    """Get status of all memory tiers: existence, entry counts, sizes."""
    mem_dir = _memory_dir()
    tier_info = []

    for tier in TIERS:
        p = _tier_path(tier, mem_dir)
        if p.exists():
            content = p.read_text()
            entries = _parse_entries(content) if tier in APPEND_ONLY else []
            count = len(entries) if entries else (1 if content.strip() else 0)
            size = p.stat().st_size
            last_mod = datetime.fromtimestamp(p.stat().st_mtime, tz=timezone.utc).isoformat()
            warning = count > MAX_LINES_BEFORE_COMPACT_WARNING if entries else False
            tier_info.append({
                "name": tier,
                "exists": True,
                "entries_count": count,
                "last_updated": last_mod,
                "size_bytes": size,
                "needs_compaction": warning,
            })
        else:
            tier_info.append({
                "name": tier,
                "exists": False,
                "entries_count": 0,
                "last_updated": None,
                "size_bytes": 0,
                "needs_compaction": False,
            })

    total = sum(t["size_bytes"] for t in tier_info)
    return {"tiers": tier_info, "total_size_bytes": total, "memory_dir": str(mem_dir)}


if __name__ == "__main__":
    mcp.run(transport="stdio")
