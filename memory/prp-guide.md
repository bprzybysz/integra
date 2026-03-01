---
title: PRP ↔ GH Integration Guide
tags: [prp, github, workflow, tooling]
status: current
last-updated: 2026-03-01
related: [gh-issues.md, ARCHITECTURE.md]
---

# PRP ↔ GH Integration Guide

## TOC
1. [Issue Type Taxonomy](#1-issue-type-taxonomy)
2. [PRP Naming Convention](#2-prp-naming-convention)
3. [prp-core Skill Inventory](#3-prp-core-skill-inventory)
4. [Recommended Workflow](#4-recommended-workflow)
5. [GH ↔ PRP Sync](#5-gh--prp-sync)
6. [prp-core vs ctx-eng-plus](#6-prp-core-vs-ctx-eng-plus)
7. [Tutorial: End-to-End Example](#7-tutorial-end-to-end-example)
8. [Decision Matrix](#8-decision-matrix)

---

## 1. Issue Type Taxonomy

| Type | Title Prefix | PRP Required? | Purpose |
|------|-------------|:---:|---------|
| **hub** | *(none)* | Never | Parent/epic. Progress tracked by child states. e.g. "Stage 2" |
| **feature** | `feat:` | Usually (1..N) | New capability. e.g. `feat: cinema.py` |
| **enhancement** | `enhance:` | Usually (0..1) | Extend existing feature |
| **bug** | `bug:` | Sometimes (0..1) | Fix broken behavior. Simple bugs skip PRP |
| **doc** | `doc:` | Rarely (0..1) | Documentation only |
| **misc** | `misc:` | Rarely (0..1) | Infra, config, tooling |

GH labels: `type:hub`, `type:feature`, `type:enhancement`, `type:bug`, `type:doc`, `type:misc`

---

## 2. PRP Naming Convention

**Relation: GH issue → PRP is 1:0..N**

Format: `.claude/PRPs/plans/prp-<NNN>-slug.md`
- `NNN` = zero-padded 3-digit GH issue number
- Multi-PRP: `prp-<NNN>.[A-Z]-slug.md`

Examples:
```
.claude/PRPs/plans/prp-049-cinema-scraper.md        # 1:1
.claude/PRPs/plans/prp-050.A-whatsapp-polling.md    # 1:N part A
.claude/PRPs/plans/prp-050.B-aggregation-engine.md  # 1:N part B
```

Hub issues, simple bugs, and trivial misc issues → no PRP.

---

## 3. prp-core Skill Inventory

| Command | When to Use |
|---------|-------------|
| `/prp-plan` | Create implementation plan for a feature/bug |
| `/prp-implement` | Execute a plan with validation loops |
| `/prp-ralph` | Autonomous loop: run until all validations pass |
| `/prp-ralph-cancel` | Cancel active Ralph loop |
| `/prp-ralph-loop` | Continue Ralph iteration (when state file exists) |
| `/prp-commit` | Quick commit with NL file targeting |
| `/prp-pr` | Create PR from current branch |
| `/prp-review` | Comprehensive PR code review |
| `/prp-review-agents` | Multi-agent PR review (comments, tests, types, docs) |
| `/prp-debug` | Deep root cause analysis |
| `/prp-issue-investigate` | Investigate GH issue, post findings |
| `/prp-issue-fix` | Implement fix from investigation artifact |
| `/prp-prd` | Interactive PRD generator |
| `/prp-research-team` | Dynamic research team for complex questions |
| `/prp-codebase-question` | Parallel agent codebase research |

---

## 4. Recommended Workflow

```mermaid
flowchart TD
    A[GH issue created] --> B{Issue type?}
    B -->|hub| C[Track child issues]
    B -->|feature/enhancement| D[/prp-plan]
    B -->|bug| E{Complex?}
    B -->|doc/misc| F[Implement directly]
    E -->|yes| D
    E -->|no| G[Fix + /prp-commit]
    D --> H[PRP created: prp-NNN-slug.md]
    H --> I[Comment on GH issue]
    I --> J[/prp-ralph or /prp-implement]
    J --> K[Validations pass]
    K --> L[Comment: Implementation complete]
    L --> M{All PRPs done?}
    M -->|yes| N[Close issue]
    M -->|no| J
```

---

## 5. GH ↔ PRP Sync

### Automatic (CLAUDE.md rules)

| Event | Action |
|-------|--------|
| After `/prp-plan` | `gh issue comment <N> -b "PRP created: prp-<NNN>-slug.md"` |
| After `/prp-ralph` completes | `gh issue comment <N> -b "Implementation complete"` + close if all PRPs done |
| Before `/prp-plan` | `gh issue view <N>` — warn if issue is closed |
| After closing issue via `gh` | Check `.claude/PRPs/plans/prp-<NNN>-*` — warn if active PRP exists |

### Manual (/prp-sync)

Run `/prp-sync` to get a full bidirectional audit:
- Active PRPs with closed issues → mismatch warning
- Archived PRPs with open issues → possible stale state

---

## 6. prp-core vs ctx-eng-plus

| Dimension | prp-core | ctx-eng-plus |
|-----------|---------|--------------|
| **Scope** | Implementation planning + execution | Context engineering + compression |
| **GH integration** | Yes (issue-bound PRPs) | No |
| **Autonomous mode** | Yes (/prp-ralph) | No |
| **Multi-agent** | Yes (/prp-review-agents) | Limited |
| **Context tools** | /prp-codebase-question | Specialised context files |
| **Best for** | Feature development, bug fixes | Managing large context windows |
| **Composable?** | Yes — use both in same session | Yes — complementary tools |

---

## 7. Tutorial: End-to-End Example

Scenario: Implement issue #49 `feat: cinema scraper`

```bash
# 1. Check issue
gh issue view 49

# 2. Create PRP
/prp-plan "Implement cinema scraper for issue #49"
# → creates .claude/PRPs/plans/prp-049-cinema-scraper.md

# 3. Comment on issue (CLAUDE.md rule)
gh issue comment 49 -b "PRP created: prp-049-cinema-scraper.md"

# 4. Execute autonomously
/prp-ralph

# 5. After validations pass — comment + close
gh issue comment 49 -b "Implementation complete"
gh issue close 49

# 6. Audit sync
/prp-sync
```

---

## 8. Decision Matrix

| Situation | Tool |
|-----------|------|
| New feature, complex | `/prp-plan` → `/prp-ralph` |
| New feature, simple | `/prp-implement` (skip plan) |
| Bug, obvious fix | `/prp-commit` |
| Bug, unknown cause | `/prp-debug` → `/prp-issue-fix` |
| Large PR review | `/prp-review-agents` |
| Quick PR review | `/prp-review` |
| Research question | `/prp-codebase-question` |
| Codebase exploration | `/prp-research-team` |
| Context overload | ctx-eng-plus tools |
