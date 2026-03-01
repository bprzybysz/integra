---
title: GH Issue Types & PRP Binding Rules
tags: [github, issues, workflow, labels]
status: current
last-updated: 2026-03-01
related: [prp-guide.md, ARCHITECTURE.md]
---

# GH Issue Types & PRP Binding Rules

## TOC
1. [Issue Type Taxonomy](#1-issue-type-taxonomy)
2. [Label Structure](#2-label-structure)
3. [PRP Binding Rules](#3-prp-binding-rules)
4. [Hub Issues](#4-hub-issues)
5. [Workflow by Type](#5-workflow-by-type)

---

## 1. Issue Type Taxonomy

| Type | Prefix | GH Label | Description |
|------|--------|----------|-------------|
| **hub** | *(none)* | `type:hub` | Parent/epic. Groups related features. Never gets a PRP. |
| **feature** | `feat:` | `type:feature` | New capability. e.g. `feat: cinema.py`, `feat: advisor module` |
| **enhancement** | `enhance:` | `type:enhancement` | Extends existing feature |
| **bug** | `bug:` | `type:bug` | Fix broken behavior |
| **doc** | `doc:` | `type:doc` | Documentation only |
| **misc** | `misc:` | `type:misc` | Infra, config, tooling, CI |

---

## 2. Label Structure

| Namespace | Examples | Purpose |
|-----------|---------|---------|
| `type:*` | `type:feature`, `type:bug` | Issue classification |
| `stage-*` | `stage-2`, `stage-3` | Roadmap stage |
| `origin:*` | `origin:prp`, `origin:ad-hoc` | Where issue came from |
| `nature:*` | `nature:blocking`, `nature:nice-to-have` | Priority signal |
| `category:*` | `category:security`, `category:perf` | Technical domain |
| `flag:*` | `flag:needs-review`, `flag:wont-fix` | Meta-status flags |

---

## 3. PRP Binding Rules

**Relation: 1 GH issue → 0..N PRPs**

| Issue Type | PRP Required? | When to Skip |
|------------|:---:|----------|
| hub | Never | Always (track via child issues) |
| feature | Usually | Only for trivial 1-file features |
| enhancement | Usually | If change is < 20 lines |
| bug | Sometimes | Simple fixes with obvious cause |
| doc | Rarely | Most doc changes need no plan |
| misc | Rarely | Config changes, dependency bumps |

Naming: `prp-<NNN>-slug.md` where NNN = zero-padded GH issue number.
Multi-PRP: `prp-<NNN>.[A-Z]-slug.md`

---

## 4. Hub Issues

Hub issues are epics — they group related feature/enhancement/bug issues.

Structure:
```
#40 Stage 2 (hub)
  ├── #41 feat: scoring engine
  ├── #42 feat: advisor module
  └── #43 enhance: add HALT to intake
```

Rules:
- Hub title has no prefix (not `feat:` etc.)
- Hub body lists child issues with checkboxes
- Hub closed when all children are closed
- No PRP ever created for a hub

---

## 5. Workflow by Type

### feature / enhancement
```
Create issue → Add type:feature + stage-* labels
→ /prp-plan → Comment "PRP created: prp-NNN-..."
→ /prp-ralph → Validations pass
→ Comment "Implementation complete" → Close issue
```

### bug
```
Create issue with bug: prefix → Add type:bug label
→ Simple? → Fix + /prp-commit → Close
→ Complex? → /prp-debug → /prp-issue-fix → Close
```

### doc
```
Create issue with doc: prefix → Add type:doc label
→ Write doc → /prp-commit → Close
```

### hub
```
Create issue (no prefix) → Add type:hub label
→ List child issues in body
→ Close when all children closed
```
