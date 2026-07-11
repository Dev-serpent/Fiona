# Roadmap

## Doc-base — Document Management in the Fiona Web UI

A LibreOffice-backed document management system accessible entirely through the
fionaLocalPages web dashboard. No separate desktop app — create, edit, format,
and manage documents from the browser.

### Goals

- Provide a full document editing experience (rich text, tables, images, styles)
  inside the existing fionaLocalPages web UI
- Use LibreOffice as the backend rendering/conversion engine (headless mode)
- Store documents as standard ODF (.odt) files on the local filesystem
- Serve documents through the browser with save/revision/export flows

### Proposed Architecture

```
Browser (SPA page) ──► aiohttp API handler ──► LibreOffice headless (libreoffice --headless)
                          │
                          ▼
                   Local filesystem (.odt files)
                          │
                          ▼
                   Optional: export to PDF, DOCX, HTML
```

- **Frontend**: New SPA page in fionaLocalPages with a document editor.
  Could use a contenteditable-based editor or embed a lightweight rich-text
  component. The page communicates with the backend via REST API calls.
- **Backend**: New handler module in `fionaLocalPages/server/handlers/` that:
  - Receives document content as HTML or JSON
  - Converts to/from ODF via LibreOffice headless (`libreoffice --headless
    --convert-to odt ...` and reverse)
  - Manages file listing, open, save, rename, delete, revision history
- **Storage**: Plain `.odt` files in a configurable documents directory
  (default: `~/FionaDocuments/`).
- **LibreOffice Bridge**: A thin Python wrapper in the handler that calls
  `subprocess.run(["libreoffice", "--headless", ...])` for format conversion.
  No Python-UNO bindings required initially.

### Milestones

1. **File browser** — List, open, save, rename, delete `.odt` files from the
   dashboard. Basic `documents/` page.
2. **HTML round-trip** — Convert `.odt` → HTML for editing in the browser,
   convert HTML → `.odt` on save. Read-only preview works.
3. **Rich-text editor** — Embed a contenteditable or lightweight editor in
   the SPA page. Support bold, italic, headings, lists, tables.
4. **Export** — Add PDF and DOCX export via LibreOffice conversion.
5. **Revision history** — Basic snapshot-based versioning (copy on save with
   timestamp).

### Non-goals (v1)

- Real-time collaborative editing
- Spreadsheet or presentation support (future)
- Full LibreOffice feature parity
- PDF rendering in the browser (download only)

---

## New Module — Platform Module Creation Guide

A standard template for adding new subsystems to Fiona.

### Module Layout

Every new module should follow this structure:

```
module-name/
├── __init__.py          # Public API: exports user-facing classes/functions
├── __main__.py          # Optional: `python -m module-name` entry point
├── cli.py               # Optional: CLI subcommand integration
├── core.py              # Core logic
├── config.py            # Configuration dataclass + loader
├── models.py            # Data models / dataclasses
├── errors.py            # Custom exceptions
└── tests/               # Test suite (pytest)
    ├── __init__.py
    └── test_core.py
```

### Integration Points

- **CLI**: Add subcommand in `fiona/cli.py` `_build_parser()` → dispatch in
  `main()` → handler function.
- **Web dashboard**: Add handler module in `fionaLocalPages/server/handlers/`
  + register routes in `app.py` + add SPA page in `pages/` + template in
  `templates/`.
- **pyproject.toml**: Add module directory name to `[tool.setuptools]`
  `packages` list.
- **Backward compatibility**: Keep public imports stable; avoid renaming
  existing exports.

### Checklist

- [ ] Module directory with `__init__.py`
- [ ] CLI subcommand registered (if needed)
- [ ] Dashboard handler + page (if needed)
- [ ] `pyproject.toml` package entry
- [ ] `docs/modules/<module>.md` documentation page
- [ ] `mkdocs.yml` nav entry
- [ ] Test suite under `tests/`
- [ ] `__init__.py` exports clear public API
