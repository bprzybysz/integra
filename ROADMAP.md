# Integra — Initialization Roadmap

> Master/orchestrator agent evolved from openclaw-config.
> Primary goal: get into Toptal, land first project, improve life health in a journey.

---

## 1. Pruning Log

Items from INSTRUCTION.md — merged, deferred, or inlined to eliminate overlap and low-gain work.

| Original Item | Action | Rationale |
|---------------|--------|-----------|
| "openclawd setup" + "integra init" | **MERGE** → Stage 0 | Same deliverable |
| "decide data grouping" + "secure intake" | **MERGE** → Stage 1 data lake | Same concern |
| "industry patterns" + "coleman00 patterns" | **MERGE** → architecture principle | Not a stage; applied everywhere |
| "insights from claude code history" | **INLINE** → Stage 2C | CC history archive + scripts + charts exist at known paths. Cross-reference with drug/supplement schedule from 2B. Module `cc_history.py` already built. |
| "train/improve human context" | **DEFER** → post-MVP | Depends on data pipeline maturity |
| matplotlib/sns plots | **DEFER** → when data exists | No data to visualize yet |
| "schedule drug/supplement interrogation" | **INLINE** → Stage 2B data collection | One task within user data collection |
| "user email addresses" | **INLINE** → integra config | Configuration, not a stage |
| "extend user data inputs" | **ARCHITECTURE** → extensible ingestion | Pattern handles future inputs |
| "readable plan format" | **META** → this document | Formatting concern, not deliverable |
| WhatsApp/SMS/email sending | **DEFER** → Stage 3 | Telegram HIL is day-1; others post-MVP |
| iOS Health / YouTube history | **DEFER** → Stage 3 | Depends on data lake being operational |

**Net result**: 12 line items → 4 stages, 3 parallel tracks.

---

## 2. Architecture Overview

```mermaid
graph LR
    subgraph "Stage 0 — Init"
        A[integra repo] --> B[.claude/ setup]
        A --> C[GH Project board]
        D[prp-core plugin<br/>includes ralph loop]
    end

    subgraph "Stage 1 — Foundation"
        F[Orchestrator<br/>cherry-pick openclaw] --> G[Tool Registry]
        G --> H[Telegram HIL]
        G --> I[Data MCP Gateway]
        I --> J[Encrypted<br/>Local Lake]
    end

    subgraph "Stage 2 — Toptal Screening"
        K[RAPID drills] --> L[Stage 2 Codility]
        L --> M[Stage 3 Live Screen]
        M --> N[Stage 4 Project]
        T[query_stack<br/>GH Issues API]
    end

    subgraph "Stage 3 — Health + Habits"
        O[iOS Health ingest] --> Q[Insight Engine]
        P[Comms channels] --> Q
    end

    A --> F
    C --> K
    C --> T
    N --> O

    style A fill:#ED7100,color:#fff,stroke:#BD5A00,stroke-width:1px
    style B fill:#8C4FFF,color:#fff,stroke:#703FCC,stroke-width:1px
    style C fill:#8C4FFF,color:#fff,stroke:#703FCC,stroke-width:1px
    style D fill:#01A88D,color:#fff,stroke:#008670,stroke-width:1px
    style F fill:#ED7100,color:#fff,stroke:#BD5A00,stroke-width:1px
    style G fill:#6B7280,color:#fff,stroke:#555B66,stroke-width:1px
    style H fill:#7AA116,color:#fff,stroke:#618011,stroke-width:1px
    style I fill:#DD344C,color:#fff,stroke:#B0293C,stroke-width:1px
    style J fill:#DD344C,color:#fff,stroke:#B0293C,stroke-width:1px
    style K fill:#C925D1,color:#fff,stroke:#A01EA7,stroke-width:1px
    style L fill:#C925D1,color:#fff,stroke:#A01EA7,stroke-width:1px
    style M fill:#C925D1,color:#fff,stroke:#A01EA7,stroke-width:1px
    style N fill:#C925D1,color:#fff,stroke:#A01EA7,stroke-width:1px
    style O fill:#01A88D,color:#fff,stroke:#008670,stroke-width:1px
    style P fill:#01A88D,color:#fff,stroke:#008670,stroke-width:1px
    style Q fill:#01A88D,color:#fff,stroke:#008670,stroke-width:1px
    style T fill:#C925D1,color:#fff,stroke:#A01EA7,stroke-width:1px
```

---

## 3. Secured Local Data Lake Pattern

All user sensitive data flows through one pattern: **Land → Encrypt → Serve via MCP**.

```mermaid
graph LR
    subgraph "Input Sources"
        U1[User via Telegram]
        U2[iOS Health export]
        U3[YouTube history]
        U4[Chat histories]
        U5[Future sources]
    end

    subgraph "Landing Zone"
        LZ[data/raw/<br/>.gitignored]
    end

    subgraph "Processing"
        ING[Ingestion<br/>Pipeline]
        ENC[age encrypt]
    end

    subgraph "Encrypted Storage"
        ES[data/lake/<br/>structured + encrypted]
    end

    subgraph "Agent Access"
        MCP[Data MCP Server<br/>decrypt on read<br/>audit log<br/>query filtering]
    end

    subgraph "Consumers"
        CL[Claude / integra]
        RPT[Reports / Insights]
    end

    U1 & U2 & U3 & U4 & U5 --> LZ
    LZ --> ING --> ENC --> ES
    ES --> MCP --> CL & RPT

    style LZ fill:#DD344C,color:#fff,stroke:#B0293C,stroke-width:1px
    style ING fill:#ED7100,color:#fff,stroke:#BD5A00,stroke-width:1px
    style ENC fill:#DD344C,color:#fff,stroke:#B0293C,stroke-width:1px
    style ES fill:#DD344C,color:#fff,stroke:#B0293C,stroke-width:1px
    style MCP fill:#8C4FFF,color:#fff,stroke:#703FCC,stroke-width:1px
    style CL fill:#01A88D,color:#fff,stroke:#008670,stroke-width:1px
    style RPT fill:#01A88D,color:#fff,stroke:#008670,stroke-width:1px
```

**Key properties:**
- Raw data never enters git — `.gitignored` landing zone
- Encryption at rest via `age` (modern, simple, no GPG complexity)
- Agent never sees raw files — queries through MCP tools only
- MCP server returns filtered, minimal data (need-to-know principle)
- Audit log tracks: what data, when, which agent session
- Pattern is source-agnostic — new input types add an ingestion adapter, nothing else changes

**MCP tools exposed to agent:**

| Tool | Purpose | Returns |
|------|---------|---------|
| `ingest_data` | Trigger ingestion from landing zone to encrypted lake | Status + record count |
| `query_data` | Query any ingested data category (health, habits, history) | Filtered records |
| `query_stack` | Compute task/quest scores from GH Issues by label + date range | Day/week/total stack breakdown |

- `ingest_data` + `query_data` operate on the encrypted local data lake (Stage 1B)
- `query_stack` operates on GH Issues API (Stage 2B, after task/quest labels exist)

Additional tools added post-MVP as data sources grow.

---

## 4. Task/Quest Pattern

All work and behavior tracking follows one universal pattern. Used for scoring, coaching, and habit management.

### Task Classification

Every task has two axes:

| Axis | Values | Meaning |
|------|--------|---------|
| **Origin** | `planned` / `user-request` / `choice` | How the task was created |
| **Nature** | `job` / `reward` | What kind of task |

**Origin types:**
- `planned` — from roadmap/sprint, exists before user acts
- `user-request` — user asks integra to do something ad-hoc
- `choice` — integra presents options, user picks (questionnaire-driven)

### Scoring: Outcome-Based

```
score = base (pass/fail) + bonus (quality gates passed)

base  = 0 (failed) | 1 (completed)
bonus = +1 per quality gate passed (tests green, review approved, time target met, etc.)
```

No fixed difficulty points. Score reflects **outcome quality**, not estimated effort.

### Reward Task Categories

Tracked daily. All sensitive data encrypted in data lake.

| Category | Type | Unit (user reports) | Quota | Time-sensitive | Sensitive |
|----------|------|---------------------|-------|----------------|-----------|
| Exercise / sleep / hydration | healthy | Binary + duration | — | — | No |
| Supplement/medication compliance | healthy | 4x daily check (M/N/A/E) + async | — | — | Yes |
| Coding practice (RAPID drills) | healthy | Problem count + time | — | — | No |
| Learning (docs, videos, courses) | healthy | Duration + source | — | — | No |
| YouTube consumption | neutral | Blocks (30min units) | — | — | No |
| Gaming — mobile (Royal Match) | quota | Session count + duration | Weekly ceiling | — | No |
| Gaming — desktop (WoW) | quota | Session count + duration | Weekly ceiling | — | No |
| Porn | quota | Blocks (15min units) | Weekly ceiling | — | Yes |
| 3-CMC | addiction-therapy | Lines | Decreasing → 0 → penance | — | Yes |
| K (tip-touch) | addiction-therapy | Touches | Decreasing → 0 → penance | — | Yes |
| X (ecstasy) | addiction-therapy | Half-pills | Decreasing → 0 → penance | — | Yes |
| BCD | controlled-use | Clouds (inhales) | Daily ceiling | Not during work hours + cooldown | Yes |
| THC (weed) | addiction-therapy | Clouds (inhales) | Decreasing → 0 → penance | Not during work hours + cooldown | Yes |

**Quota mechanics** — three tiers:

```
# addiction-therapy (3-CMC, K, X, THC): decay → 0 → penance
  quota_week_n    = quota_week_0 × decay_factor^n
  under quota     = bonus +1
  at quota        = base only
  over quota      = score 0 + coaching flag
  at zero + use   = score 0 + penance task
  THC also:       time-gate (not during work hours) + cooldown

# controlled-use (BCD): stable ceiling + time rules
  daily ceiling   = fixed (no decay)
  under ceiling   = bonus +1
  at ceiling      = base only
  over ceiling    = score 0 + coaching flag
  work-hours use  = score 0 + coaching flag
  cooldown broken = score 0 + coaching flag

# quota (gaming, porn): weekly ceiling
  under quota     = bonus +1
  at quota        = base only
  over quota      = score 0 + coaching flag
```

### Stack = Sum Metric

Three granularities, computed per origin, per nature, or combined:

| Level | Scope | Use |
|-------|-------|-----|
| `stack_day` | Today's completed tasks | Daily accountability |
| `stack_week` | This week (Mon–Sun) | Weekly trend |
| `stack_total` | All time | Progress trajectory |

### Architecture: GH Issues + Labels + MCP

Tasks are GH issues in the integra repo. Labels encode classification:

| Label prefix | Values | Example |
|-------------|--------|---------|
| `origin:` | `planned`, `user-request`, `choice` | `origin:planned` |
| `nature:` | `job`, `reward` | `nature:reward` |
| `category:` | `healthy`, `quota`, `addiction-therapy`, `controlled-use`, `neutral` | `category:quota` |
| `score:` | numeric | `score:3` |

MCP tool `query_stack` computes stacks by querying GH API:
- Filter by labels, closed date range
- Sum scores by grouping
- Return day/week/total breakdown

No custom DB needed. GH Issues are the source of truth.

---

## 5. Stage Breakdown

### Stage 0 — Parallel Init (Day 1)

Three independent tracks, all parallelizable.

| Track | Tasks | Dependency | Owner |
|-------|-------|------------|-------|
| **0A: Repo** | Create `bprzybysz/integra` repo, init structure, CLAUDE.md, .gitignore | None | integra |
| **0B: Plugins** | Install `prp-core` globally (includes ralph loop). `prp-core@prp-marketplace` via `/plugin marketplace add wirasm/prps-agentic-eng` then `/plugin install prp-core`. | None | user |
| **0C: GH Project** | Create project board, define sprint columns, link to integra repo | None | integra |

**Quality gate**: `gh project list` shows board, `/prp-plan` responds, `integra/CLAUDE.md` exists.

**Parallel execution diagram:**

```mermaid
gantt
    title Stage 0 — Parallel Init
    dateFormat X
    axisFormat %s

    section Track 0A
    Create integra repo + scaffold     :a1, 0, 2
    Write CLAUDE.md + .claude/         :a2, 2, 4

    section Track 0B
    Install prp-core plugin (includes ralph) :b1, 0, 2
    Verify commands + test run         :b2, 2, 4

    section Track 0C
    Create GH Project board            :c1, 0, 1
    Define sprint columns + labels     :c2, 1, 3
    Link repos + verify e2e           :c3, 3, 4
```

---

### Stage 1 — Foundation Sprint (Days 2–4)

Two parallel tracks + one sequential.

| Track | Tasks | Dependency | Owner |
|-------|-------|------------|-------|
| **1A: Orchestrator** | Cherry-pick orchestrator.py, registry.py, config.py from openclaw. Rename openclaw→integra. Async Anthropic client. Code-level HIL enforcement. | Stage 0A | integra |
| **1B: Data Lake** | Create data/ structure, age encryption setup, ingestion pipeline scaffold, Data MCP server (2 tools: `ingest_data`, `query_data`). `query_stack` added in Stage 2B when task/quest labels exist. | Stage 0A | integra |
| **1C: Telegram HIL** | Cherry-pick telegram_hil.py, verify approval flow works, connect to orchestrator. | 1A | integra |

**Quality gate**: `uv run pytest tests/ -v` passes, Telegram bot responds to `/start`, `age -d data/lake/test.age` decrypts, MCP server responds to `query_data`.

**Cherry-pick manifest from openclaw-config:**

| Source File | Target | Changes |
|-------------|--------|---------|
| `openclaw/orchestrator.py` | `integra/core/orchestrator.py` | Rename, async client, strip sync wrapper |
| `openclaw/tools/registry.py` | `integra/core/registry.py` | Add `requires_confirmation` flag per tool |
| `openclaw/config.py` | `integra/core/config.py` | Rename, add data lake paths |
| `openclaw/tools/telegram_hil.py` | `integra/integrations/telegram.py` | Keep as-is, it works |
| `openclaw/app.py` | `integra/app.py` | Strip voice routes (defer), add MCP mount |

**Not cherry-picked**: `gmail.py`, `gcalendar.py`, `gdrive.py`, `voice.py`, `tts.py`, `google_auth.py` — all Stage 3 (comms channels).

---

### Stage 2 — Toptal Screening Sprint (Days 5–21)

The actual goal. Two parallel tracks.

| Track | Tasks | Dependency | Owner |
|-------|-------|------------|-------|
| **2A: Coding Drills** | RAPID framework practice (15 patterns × 5 problems each), timed sessions, progress tracking via GH Project issues. | Stage 0C (GH Project for tracking) | **user** |
| **2B: User Data Collection** | Collect drugs/supplements/dietary via Telegram bot questionnaire, ingest to data lake, structured as queryable records. Includes scheduled drug/supplement interrogation (4x daily: M/N/A/E + async). User provides supplement/prescription drug list with package photos + purchase links during onboarding interview. **Daily log advisor** (10 rules from toptal KB): sleep/energy/mood assessment, ADHD-aware coaching, IBS/grief/freeze detection, quota tracking. See `tmp/context-from-toptal.md` and `tmp/drugs-tracking-reward-task.md` for full spec. New module: `integra/integrations/advisor.py`. | Stage 1C (Telegram HIL) + Stage 1B (Data Lake) | integra |
| **2C: Claude Code History** | Reanalyse CC session data after data lake + deps operational. Data already exists: `interviews/toptal/data/claude-history-all.zip.part-a{a,b,c}` (encrypted, split). Scripts exist: `interviews/toptal/scripts/extract_prompts.py` (2098 records), `visualize_prompts.py`. Charts exist: `interviews/toptal/charts/` (9 PNGs). `integra/data/cc_history.py` + `analyze_cc_productivity()` already built. User provides `age` secret key at ingestion time. Cross-reference with drug/supplement schedule from 2B to find productivity correlations. | 2B complete + user provides decryption key | integra |

**Quality gate**: 75 problems solved, pattern recognition >80% accuracy, all user health data ingested and queryable, claude code history analysis queued.

**Toptal screening stage mapping:**

| Toptal Stage | Prep Duration | Key Deliverable | Risk |
|--------------|---------------|-----------------|------|
| Stage 1: Language & Personality | 1 day | 60-sec intro script, "Why Toptal" answer | LOW |
| Stage 2: Codility (90 min, 3 problems) | 1–2 weeks | 75 problems done, RAPID fluent | MEDIUM |
| Stage 3: Live Screen (60 min, 2 problems) | 1 week overlap | Mock sessions, talk-through drill | HIGH |
| Stage 4: Test Project (1–3 weeks) | Planned in pre-stage | PRP for take-home, TDD scaffold | LOW |

---

### Stage 3 — Health & Habits (Post-MVP, lazy-planned)

Planned at pre-stage level only. Details deferred to PRP generation when Stage 2 gate passes.

| Track | Scope | Pre-stage PRP needed |
|-------|-------|---------------------|
| **3A: Health Data Pipeline** | iOS Health export, YouTube history, chat histories. Encrypted archive already at `interviews/toptal/data/allsecretdata.zip.part-a{a,b,c}` — user provides decryption key. | Yes — data schema + ingestion adapters |
| **3B: Communication Channels** | Gmail send, WhatsApp (Twilio), SMS (Twilio), email notifications | Yes — channel priority + approval rules |
| **3C: Insight Engine** | Pattern detection in health data, habit correlation, CC history productivity insights (builds on 2C) | Yes — ML/statistical approach + privacy constraints |

**Quality gate**: Defined per-PRP at pre-stage planning time.

---

## 6. Dependency Graph

```mermaid
graph TB
    S0A[0A: integra repo] --> S1A[1A: Orchestrator]
    S0A --> S1B[1B: Data Lake]
    S0B[0B: Plugins]
    S0C[0C: GH Project] --> S2A[2A: Coding Drills]
    S0C --> SQS[query_stack MCP tool]

    S1A --> S1C[1C: Telegram HIL]
    S1B --> S2B[2B: User Data Collection]
    S1C --> S2B

    S2B --> S2C[2C: Claude Code History]
    S2A --> S3[Stage 3: Health & Habits]
    S2B --> S3


    style S0A fill:#ED7100,color:#fff,stroke:#BD5A00,stroke-width:1px
    style S0B fill:#ED7100,color:#fff,stroke:#BD5A00,stroke-width:1px
    style S0C fill:#ED7100,color:#fff,stroke:#BD5A00,stroke-width:1px
    style S1A fill:#7AA116,color:#fff,stroke:#618011,stroke-width:1px
    style S1B fill:#DD344C,color:#fff,stroke:#B0293C,stroke-width:1px
    style S1C fill:#7AA116,color:#fff,stroke:#618011,stroke-width:1px
    style S2A fill:#C925D1,color:#fff,stroke:#A01EA7,stroke-width:1px
    style S2B fill:#C925D1,color:#fff,stroke:#A01EA7,stroke-width:1px
    style S2C fill:#C925D1,color:#fff,stroke:#A01EA7,stroke-width:1px
    style SQS fill:#C925D1,color:#fff,stroke:#A01EA7,stroke-width:1px
    style S3 fill:#8C4FFF,color:#fff,stroke:#703FCC,stroke-width:1px
```

**Critical path**: 0A → 1A → 1C → 2B → 2C (data collection → drug interrogation → claude code history)
**Parallel path**: 0C → 2A (coding drills run independently, time-dominant activity)

---

## 7. integra Project Structure (Target)

```
integra/
├── CLAUDE.md                          # Project rules, validation commands, architecture notes
├── ROADMAP.md                         # This file — stages, deps, quality gates
├── .mcp.json                          # MCP server config (tracked in git)
├── pyproject.toml                     # uv, ruff, mypy, pytest
├── .claude/
│   ├── commands/
│   │   ├── ingest-data.md             # Custom: trigger data ingestion
│   │   └── youtube-extract.md         # Custom: extract KB from YouTube video
│   ├── hooks/
│   │   └── format-after-edit.sh       # ruff format + ruff check --fix
│   └── settings.local.json            # Permissions, MCP servers
├── integra/
│   ├── __init__.py
│   ├── app.py                         # FastAPI entrypoint
│   ├── core/
│   │   ├── orchestrator.py            # Claude agentic loop (async)
│   │   ├── registry.py                # Tool schemas + dispatch + HIL flags
│   │   └── config.py                  # Pydantic-settings
│   ├── integrations/
│   │   ├── telegram.py                # HIL confirm/notify
│   │   ├── scheduler.py              # Scheduled questionnaires (morning/evening)
│   │   └── questionnaire.py          # Telegram questionnaire flows
│   │   # advisor.py                  # Stage 2B: daily log advisor (10 rules) — not yet created
│   └── data/
│       ├── mcp_server.py              # Data MCP gateway
│       ├── ingestion.py               # Raw → structured pipeline
│       ├── encryption.py              # age encrypt/decrypt helpers
│       ├── collectors.py              # Supplement, drug, meal data collectors
│       ├── schemas.py                 # Data models + RewardCategory enum
│       ├── cc_history.py              # CC session history analysis
│       ├── youtube.py                 # YouTube transcript + metadata extraction
│       └── audit.py                   # Audit log writer
├── data/                              # .gitignored
│   ├── raw/                           # Landing zone (unencrypted, transient)
│   ├── lake/                          # Encrypted structured storage
│   └── audit/                         # Access logs
├── tmp/                              # .gitignored — working notes, KB imports
│   ├── context-from-toptal.md        # Stage 2B+ actionable import
│   └── toptal-interviews-kb-report.md # Full KB assessment
└── tests/
    ├── test_orchestrator.py
    ├── test_registry.py
    ├── test_data_mcp.py
    ├── test_telegram.py
    ├── test_encryption.py
    ├── test_app.py
    ├── test_questionnaire.py
    ├── test_cc_history.py
    ├── test_schemas.py
    ├── test_scheduler.py
    ├── test_collectors.py
    ├── test_audit.py
    └── test_youtube.py
```

> PRP commands (`/prp-prd`, `/prp-plan`, `/prp-implement`, etc.) provided by the globally-installed `prp-core` plugin — no local files needed.

---

## 8. GH Project Sprint Structure

| Sprint | Name | Duration | Contains |
|--------|------|----------|----------|
| Sprint 0 | Init | 1 day | 0A + 0B + 0C (all parallel) |
| Sprint 1 | Foundation | 3 days | 1A + 1B parallel, then 1C |
| Sprint 2 | Toptal Prep | 2 weeks | 2A (user) + 2B (integra) parallel |
| Sprint 3+ | Health & Habits | TBD | Lazy-planned, PRP-driven |

**GH Project columns**: `Backlog` → `Sprint N` → `In Progress` → `Review` → `Done`

**Labels**:
- Stages: `stage-0`, `stage-1`, `stage-2`, `stage-3`
- Ownership: `user-task`, `integra-task`
- Status: `blocked`, `data-sensitive`
- Task/Quest: `origin:planned`, `origin:user-request`, `origin:choice`, `nature:job`, `nature:reward`, `category:healthy`, `category:quota`, `category:addiction-therapy`, `category:controlled-use`, `category:neutral`, `score:N`
- Flags: `flag:penance`

---

## 9. Quality Gates Summary

| Gate | Stage | Criteria | Automated? |
|------|-------|----------|------------|
| G0 | Stage 0 | Repo exists, plugins respond, GH Project has columns | Manual verify |
| G1-code | Stage 1 | `uv run pytest tests/ -v` all pass, `ruff check` clean, `mypy .` clean | Yes |
| G1-hil | Stage 1 | Telegram bot sends approval request, user can approve/deny, result propagates | Manual + integration test |
| G1-data | Stage 1 | `age -d` decrypts test data, MCP `query_data` returns results | Integration test |
| G2-drill | Stage 2 | 75 problems solved, pattern accuracy >80%, 7/10 Easy under 15 min | User self-report |
| G2-data | Stage 2 | All user health data ingested, queryable via MCP, audit log populated | Integration test |
| G2-quest | Stage 2 | `query_stack` returns correct day/week/total for test issues with task/quest labels. At least one `addiction-therapy` quota verified with decay calculation. | Integration test |
| G3-pre | Stage 3 | PRP generated with confidence >7/10 for each Stage 3 track | PRP score |

---

## 10. Plugin Setup + Cheatsheet

**Install** (one-time, ~5 min total):
1. `/plugin marketplace add wirasm/prps-agentic-eng` then `/plugin install prp-core`
2. Delete manual `generate-prp.md` / `execute-prp.md` from existing CE projects (plugin replaces them)
3. Domain-specific agents, hooks, rules.md stay untouched

### Command cheatsheet

```
# PRP workflow (via prp-core plugin — includes ralph loop)
/prp-prd                                   # Generate PRD only
/prp-plan                                  # Generate plan from PRD
/prp-implement                             # Implement from plan
/prp-commit                                # Commit with conventional message
/prp-pr                                    # Create PR from branch
/prp-review                                # Review current changes
/prp-review-agents                         # Multi-agent PR review
/prp-debug                                 # Deep root cause analysis
/prp-issue-investigate                     # Deep investigation, post to GH
/prp-issue-fix                             # Fix from investigation artifact
/prp-codebase-question                     # Research codebase questions
/prp-research-team                         # Design dynamic research team

# Ralph loop (built into prp-core)
/prp-ralph                                 # Autonomous execution until validations pass
/prp-ralph-cancel                          # Stop active loop

# Workflow: PRP + Ralph (autonomous feature)
/prp-prd                                   # Step 1: generate PRD
/prp-plan                                  # Step 2: plan from PRD
# Review plan, approve                     # Step 3: human gate
/prp-ralph                                 # Step 4: autonomous execution with ralph loop
```

---

## Vocabulary

| Term | Definition |
|------|------------|
| **integra** | Master/orchestrator agent replacing openclaw. FastAPI + Claude Opus 4.6. |
| **PRP** | Product Requirements Prompt — implementation blueprint for AI agents (PRD + codebase context + validation gates). |
| **Ralph loop** | Autonomous execution loop via Claude Code stop-hook. Retries until completion promise or max iterations. |
| **Skinner harness** | Full agent control plane: deterministic tool-use lanes, circuit breakers, identity attribution. Post-MVP goal. |
| **HIL** | Human-in-the-Loop — Telegram-based approval flow for sensitive/irreversible actions. |
| **Data MCP** | MCP server mediating agent access to encrypted user data. Decrypt-on-read, audit, query filtering. |
| **age** | Modern file encryption tool (age-encryption.org). Simpler than GPG, no key servers. |
| **Landing zone** | Unencrypted transient area where raw user data is deposited before ingestion. |
| **Quality gate** | Automated or manual checkpoint that must pass before progressing to next stage. |
| **PIV** | Plan → Implement → Validate. Core workflow loop from context engineering methodology. |
| **CE** | Context Engineering — methodology for structuring AI agent inputs to maximize one-pass success. |
| **prp-core** | Claude Code plugin (`prp-core@prp-marketplace` from `wirasm/prps-agentic-eng`) providing PRP workflow commands + built-in ralph loop. |
| **Advisor** | Daily log advisor module (10 rules). ADHD/health-aware coaching: sleep, energy, mood, IBS, grief, freeze detection, quota tracking. Triggers after daily questionnaire via Telegram. |
| **RAPID** | Read & Restate → Assess Pattern → Plan in Pseudocode → Implement → Debug. 0-shot coding protocol from speed-diagnosis.md. |
| **Stack** | Sum metric of task scores. Computed per day/week/total, grouped by origin and/or nature. |
| **Quota** | Decreasing ceiling for tracked behaviors (gaming, substances). `quota_week_n = quota_week_0 × decay^n`. Under quota = bonus. |
| **Controlled-use** | Substance type with stable daily ceiling + time-gate (work hours blocked) + cooldown. For legal therapeutic use (IBS, anxiety). Currently: BCD. |
| **Penance** | Mandatory job task assigned on zero-quota relapse (addiction-therapy). E.g. gym session, study block, cleanup. |
| **Origin** | How a task was created: `planned` (roadmap), `user-request` (ad-hoc), `choice` (picked from options). |
| **Nature** | What kind of task: `job` (scored work) or `reward` (behavior tracking). |
| **query_stack** | MCP tool that queries GH Issues by label + date range to compute stack scores. |
