# Handoff — Fiona Development Session

**Date:** 2026-06-27
**Project:** Fiona — Desktop-class automation and AI agent frontend

---

## What Was Done This Session

### Scientific Knowledge Retrieval (SciRetrieval)

Built and integrated a complete multi-provider scientific knowledge retrieval subsystem — from foundation ABCs through to web UI integration.

**Architecture:**

```
User Query → Router (domain + intent classification)
                  │
                  ▼
           EntityResolver (synonym registry, canonical IDs)
                  │
                  ▼
           Normalizer (standard schema, cross-provider merge)
                  │
                  ▼
    ┌─────────────┼─────────────┐
    ▼             ▼             ▼
  NCBI          PubChem       NIST
  (BIOLOGY)     (CHEMISTRY)   (CHEMISTRY/PHYSICS)
    │             │             │
    └──────┬──────┘             │
           ▼                    ▼
    SciLab Processor     CacheManager
           │             (conversation TTL 5min,
           │              NIST disk-persisted)
           └────────┬──────────┘
                    ▼
             Final Response
```

**What was built (26 new files in `SciRetrieval/`):**

| Milestone | Files | Lines |
|---|---|---|
| M1 — Foundation (ABCs, models, errors) | 4 | ~250 |
| M2 — Domain Router (keyword classifier) | 2 | ~200 |
| M3 — Multi-Provider Retrieval (NCBI/PubChem/NIST) | 5 | ~600 |
| M4 — Normalizer + EntityResolver | 3 | ~350 |
| M5 — SciLab Pipeline (validate, context, summarize) | 5 | ~550 |
| M6 — CacheManager (conversation + NIST disk) | 3 | ~300 |
| M7 — Integration (CLI, DI, Agent) | 4 | ~400 |
| M8 — Tests (278, 13 files) | 13 | ~2500 |

**Integration into fionaLocalPages:**

| Component | What |
|---|---|
| `server/handlers/sciretrieval.py` | 6 REST endpoints (search, classify, providers, getdata, enrich, cache/clear) |
| `server/app.py` | SciRetrieval routes registered |
| `pages/terminal.js` | `handleScienceCommand()` — 5 subcommands intercepted before shell exec |
| `pages/terminal.js` | `showHelp()` — custom help reference including science commands |
| `server/handlers/agent.py` | `enrich_science: true` option in agent_ask |
| `pages/agent-status.js` | Science badge in Conversation tab |

**CLI surface:**

```bash
fiona sire query "What is the molecular weight of Aspirin?"
fiona sire classify "What is the speed of light?"
fiona sire providers
fiona sire getdata pubchem aspirin
fiona sire cache-clear
```

**Terminal `science` commands (web):**

```text
science search <query>     Search scientific databases
science classify <query>   Classify a scientific query
science providers          List registered data providers
science getdata <p> <e>    Direct provider lookup
science cache              Clear retrieval caches
```

**Keyword list expansion** (post-testing fix):
- Biology: 15 → 30 keywords
- Chemistry: 17 → 32 keywords
- Physics: 17 → 34 keywords
- Intent patterns: 28 → 37 patterns

### Browser Automation Migration (carried forward)

Previous session migrated Playwright → Selenium. SciRetrieval added `science` commands to the same Terminal page without affecting existing browser automation.

### State Machine Fix (carried forward)

Previous session fixed `BrowserManager.start()` to accept ERROR state. No changes this session.

---

## Current State of the Codebase

### SciRetrieval (`SciRetrieval/`)

```
SciRetrieval/
├── __init__.py              # Package exports
├── interfaces.py            # Re-exports from fiona/interfaces.py
├── models.py                # Data models (7 classes)
├── errors.py                # Error hierarchy (6 exception types)
├── router.py                # Domain + intent keyword classifier
├── normalizer.py            # Cross-provider result normalization
├── entity_resolver.py       # Synonym registry + canonical IDs
├── cli.py                   # CLI argument parser
├── data/
│   ├── keywordlist.json     # Domain classification keywords (96 total)
│   └── synonyms.json        # Entity synonyms (4 initial entries)
├── providers/
│   ├── __init__.py          # Provider exports
│   ├── base.py              # BaseProvider ABC + retry logic
│   ├── ncbi.py              # NCBI E-utilities provider
│   ├── pubchem.py           # PubChem PUG REST provider
│   ├── nist.py              # NIST CODATA provider
│   └── manager.py           # ProviderManager (dispatch, merge)
├── scilab/
│   ├── __init__.py          # SciLab exports
│   ├── pipeline.py          # SciLabPipeline orchestrator
│   ├── validator.py         # Cross-field consistency checks
│   ├── context_generator.py # Entity/relationship context builder
│   └── summarizer.py        # Template-based result synthesizer
└── cache/
    ├── __init__.py          # Cache exports
    ├── manager.py           # CacheManager (conversation + NIST)
    └── nist_cache.py        # NistCache (disk-persistent JSON)
```

### FLoP Web Server (`fionaLocalPages/`) — Updated

```
fionaLocalPages/
├── server/
│   └── handlers/
│       ├── sciretrieval.py  # NEW — 6 SciRetrieval REST endpoints
│       ├── agent.py         # Updated — enrich_science support
│       ├── terminal.py      # Backend terminal handler (unchanged)
│       └── ...              # Other handlers
└── pages/
    ├── terminal.js          # Updated — science commands + help
    ├── agent-status.js      # Updated — Science badge
    └── ...                  # Other pages
```

### Key Files Modified (existing)

| File | Change |
|---|---|
| `fiona/interfaces.py` | Added 7 ABCs (IIntentDomainClassifier, IProvider, IEntityResolver, INormalizer, ISciLabProcessor, ICacheManager, IRetrievalManager) |
| `fiona/cli.py` | Added `sire`/`sr` CLI layer (5 subcommands) |
| `fiona/di.py` | Added `register_sci_retrieval()`, `get_sci_retrieval_bridge()` |
| `fiona/__init__.py` | SciRetrieval module exports |
| `Agent/command_registry.py` | Added `sciretrieval_query` CommandSpec |
| `Agent/orchestrator.py` | Added `sciretrieval_query` action handler |
| `fionaLocalPages/server/app.py` | Registered 6 SciRetrieval routes |
| `fionaLocalPages/pages/terminal.js` | Added `handleScienceCommand()`, `showHelp()`, help interceptor |
| `fionaLocalPages/pages/agent-status.js` | Added Science badge |

### Test Results

```
tests/sci_retrieval/ — 278 passed (13 files)
All project tests    — 1018 passed (17 pre-existing env failures)
```

---

## Key Design Decisions

| Decision | Rationale |
|---|---|
| **ABCs in fiona/interfaces.py** (not SciRetrieval/interfaces.py) | Single source of truth, matches existing pattern for all subsystem interfaces |
| **Conversation Cache** (TTL 5 min, in-memory dict) | Simpler than SQLite, supports long scientific discussions naturally; avoids one-link-deep limitation |
| **NIST cache single-level disk** (not L1/L2/L3) | Only add multi-level cache if profiling proves need (data-driven decision) |
| **Multi-provider retrieval** | Queries can use primary + secondary providers (e.g., PubChem primary + NCBI secondary for "What protein binds Aspirin?") |
| **Graceful degradation everywhere** | Provider failures never crash Terminal or Agent pages — errors returned as descriptive messages |
| **EntityResolver** between Normalizer and SciLab | Resolves aliases, assigns canonical IDs, merges cross-provider duplicates with provenance tracking |
| **`science` commands intercepted client-side** in terminal.js | Zero-latency, works without backend shell, follows same pattern as existing interception |
| **Keyword-based classifier** (not ML) | No model dependency, instantly cold-startable, trivially extensible by editing JSON |

---

## Known Issues

### 1. Keyword Coverage (Resolved)

The browser test identified 3 partial failures where queries didn't match expected domains. All three were **keyword data gaps**, not code defects. The `keywordlist.json` was expanded:
- Added `"molecular"`, `"weight"`, `"mass"` etc. to chemistry
- Added `"speed"`, `"light"`, `"frequency"` etc. to physics
- Added `"function"`, `"pathway"`, `"organism"` etc. to biology
- All three queries now classify correctly

### 2. aiohttp Optional Dependency

SciRetrieval providers require `aiohttp>=3.9.0` (optional dependency under `[project.optional-dependencies] sciretrieval`). Without it, providers return graceful error messages. The core pipeline (router, normalizer, entity resolver, SciLab, cache) works without aiohttp.

### 3. Browser State Singleton (carried forward)

`BrowserAutomation/__init__.py` holds a module-level `_default_manager` singleton. This persists across HTTP requests in the FLoP server — intentional but ERROR state from a failed start persists until `start()` is called again (now allowed from ERROR).

---

## Next Steps (Priority Order)

1. **Expand entity synonyms** — `synonyms.json` has only 4 entries (Aspirin, Glucose, TP53, BRCA1). Add more compounds/genes for better entity resolution.
2. **Add more providers** — e.g., arXiv (preprints), Semantic Scholar, PDB (protein structures)
3. **Multi-level NIST cache** — Add L1/L2/L3 hierarchy if profiling shows performance benefit
4. **Keyword auto-expansion** — ML-based or heuristic keyword suggestion from query logs
5. **[DONE] Clean up dead code**: Removed `_playwright_provider.py` and its test file; updated `fiona/di.py`, `BrowserAutomation/__init__.py`, `fiona/interfaces.py`, and documentation references.
6. **Test full browser automation flow through FLoP UI** (manual verification in a real browser)

---

## Relevant Files (Complete List)

### SciRetrieval Core (26 files)

| File | Purpose |
|---|---|
| `SciRetrieval/__init__.py` | Package exports |
| `SciRetrieval/interfaces.py` | ABC re-exports |
| `SciRetrieval/models.py` | 7 data models |
| `SciRetrieval/errors.py` | Error hierarchy |
| `SciRetrieval/router.py` | Domain + intent classifier (173 lines) |
| `SciRetrieval/normalizer.py` | Result normalizer |
| `SciRetrieval/entity_resolver.py` | Synonym registry + canonical IDs |
| `SciRetrieval/cli.py` | CLI argument parser |
| `SciRetrieval/providers/base.py` | BaseProvider ABC + retry |
| `SciRetrieval/providers/ncbi.py` | NCBI E-utilities provider |
| `SciRetrieval/providers/pubchem.py` | PubChem PUG REST provider |
| `SciRetrieval/providers/nist.py` | NIST CODATA provider |
| `SciRetrieval/providers/manager.py` | ProviderManager dispatch + merge |
| `SciRetrieval/scilab/pipeline.py` | SciLabPipeline orchestrator |
| `SciRetrieval/scilab/validator.py` | Cross-field validation |
| `SciRetrieval/scilab/context_generator.py` | Entity context builder |
| `SciRetrieval/scilab/summarizer.py` | Result synthesizer |
| `SciRetrieval/cache/manager.py` | CacheManager (conversation + NIST) |
| `SciRetrieval/cache/nist_cache.py` | NistCache disk-persistent JSON |
| `SciRetrieval/data/keywordlist.json` | 96 domain keywords + 37 intent patterns |
| `SciRetrieval/data/synonyms.json` | 4 entity synonym entries |

### Integration Files (8 modified)

| File | Change |
|---|---|
| `fiona/interfaces.py` | +7 ABCs |
| `fiona/cli.py` | +sire/sr CLI |
| `fiona/di.py` | +register_sci_retrieval() |
| `fiona/__init__.py` | +SciRetrieval exports |
| `Agent/command_registry.py` | +sciretrieval_query command |
| `Agent/orchestrator.py` | +sciretrieval_query handler |
| `fionaLocalPages/server/app.py` | +6 SciRetrieval routes |
| `fionaLocalPages/server/handlers/agent.py` | +enrich_science option |

### fionaLocalPages Frontend (3 files)

| File | Change |
|---|---|
| `fionaLocalPages/server/handlers/sciretrieval.py` | NEW — 6 endpoints |
| `fionaLocalPages/pages/terminal.js` | +handleScienceCommand, +showHelp, +help interceptor |
| `fionaLocalPages/pages/agent-status.js` | +Science badge |

### Tests (13 files)

| File | Tests |
|---|---|
| `tests/sci_retrieval/test_router.py` | 46 |
| `tests/sci_retrieval/test_providers.py` | 30 |
| `tests/sci_retrieval/test_normalizer.py` | 20 |
| `tests/sci_retrieval/test_entity_resolver.py` | 28 |
| `tests/sci_retrieval/test_scilab.py` | 80 |
| `tests/sci_retrieval/test_cache.py` | 28 |
| `tests/sci_retrieval/test_manager.py` | 20 |
| `tests/sci_retrieval/test_integration.py` | 26 |
| Remaining 5 test files | 26 |
| **Total** | **278** |
