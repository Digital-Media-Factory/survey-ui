# Agent rules for this repo

Read before editing. Google Antigravity (and most agent IDEs) pick this file up
automatically as project context.

## What this is

A survey-results dashboard for a child digital-safety questionnaire answered by
Arabic-speaking children and teenagers. FastAPI serves JSON; a single static page
renders it with Chart.js. No build step, no npm, no framework — keep it that way
unless asked.

## Hard rules

1. **Never hard-code question text into logic.** Columns are classified at
   runtime in `analytics.py::classify`. A new form export must still work. If you
   need a specific question, match loosely on a substring the way `kpis()` does.
2. **Count with `normalize_text`, display with `tidy`.** Arabic answers arrive
   with diacritics, tatweel and mixed hamza forms, so counting without folding
   splits one bar into three. But never show a folded string: folding turns
   `بالتأكيد` into `بالتاكيد`. `distribution()` counts by key and labels with the
   most common original spelling — keep that split in any new aggregate.
3. **The UI is RTL.** Use logical CSS properties (`inset-inline-start`,
   `padding-inline-end`, `border-inline-start`), never `left`/`right`. The one
   exception is absolute positioning against an offset measurement — `offsetLeft`
   is measured from the left edge in both directions, which is why the tab
   indicator sets `left`.
4. **Animation is opt-out, not decoration.** New motion must sit behind the
   `MOTION` flag in `app.js` or a `prefers-reduced-motion` media query, and must
   not delay data appearing — charts build on intersection, not on a timer.
5. **Filters apply everywhere or nowhere.** Any new panel must accept the same
   `filters` JSON and re-render on change — a chart that ignores the active
   filter is a bug, not a feature.
6. **Free-text answers are children's words.** Don't truncate them in the API,
   don't paraphrase them, don't send them to a third-party service.
7. Run `uvicorn app.main:app --reload` and hit the real endpoints before saying
   something works. `curl "localhost:8000/api/stats" | jq '.blocks[0]'`.

## Conventions

- Python: type hints, `from __future__ import annotations`, no classes where a
  function does.
- JS: plain modules, `const`/`let`, no jQuery, no bundler. DOM strings go through
  `escapeHtml`.
- Colours come from `PALETTE` in `app.js` and the CSS custom properties in
  `:root`. Don't introduce one-off hex values.
- New endpoints are `/api/<noun>` and return JSON objects, never bare arrays.

## Prompts for the next features

Paste one at a time; each is scoped to land in a single review.

**Cross-tabulation**
> Add `GET /api/crosstab?row=<column>&col=<column>&filters=` returning a matrix of
> counts and row percentages. Render it under the charts as a heat-map table where
> cell opacity encodes the row percentage. Follow rule 1 — columns come from
> `/api/meta`, both selects are populated from the schema.

**Trend over time**
> Use the Timestamp column to add a responses-per-day line chart to the KPI strip,
> with a date-range picker that feeds the same `filters` object.

**Persistence and multi-sheet**
> Replace the module-level `STATE` dict with SQLite (`sheets` table: id, name,
> source, uploaded_at, parquet blob). Add `GET /api/sheets` and
> `POST /api/sheets/{id}/activate`, and a sheet switcher in the header.

**Printable report**
> Add `GET /api/export/report.pdf` that renders the current filter state as an
> Arabic RTL PDF: KPIs, one chart per question, and all open answers. Use
> WeasyPrint with the Tajawal font embedded; charts render server-side with
> matplotlib and `arabic_reshaper` + `python-bidi` for the labels.

**Auth**
> Put the whole app behind a single shared password using an HTTP-only session
> cookie and a `/login` page. `/api/*` returns 401 as JSON, the page redirects.
