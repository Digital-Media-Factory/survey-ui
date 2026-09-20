# لوحة نتائج استبيان "أمان الأطفال في العالم الرقمي"

FastAPI backend + vanilla HTML/CSS/JS dashboard that reads a Google Forms export
(`.xlsx`, `.xls`, `.csv`) from **disk, an upload, or a Google Sheets/Drive link**
and renders the same kind of statistics and charts the Forms summary page shows —
but filterable, animated, in RTL Arabic, and exportable.

The interface: a sticky header, a hero with the total response count counting up
and a real participant quote, KPI cards with animated progress rings, filter
chips, and four tabs — overview (top answer per question + demographics), all
questions, the written answers, and the raw response table. Charts animate in as
they scroll into view; everything respects `prefers-reduced-motion`.

Built against the real sheet: 14 responses × 27 questions.

## Run it

```bash
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Open http://127.0.0.1:8000 — the sheet in `data/` loads automatically on startup.
API docs at `/docs`.

To use a different sheet: drop it into `data/`, or upload it from the header, or
paste a Google link (the file must be shared as *Anyone with the link*).

## Project layout

```
app/
  main.py        FastAPI routes + in-memory store
  loaders.py     disk / upload / Drive-link readers, share-link → export URL
  analytics.py   question typing, Arabic cleaning, distributions, KPIs
  static/        index.html · styles.css · app.js  (no build step, no framework)
data/survey.xlsx the Google Forms export
```

## How the numbers are produced

Nothing is hard-coded to these 27 questions — each column is classified at load
time, so a new form export still works:

| Type | Detected by | Rendered as |
|---|---|---|
| `single` | few repeated values | doughnut (≤5 options) or horizontal bar |
| `multi` | header says "يمكنك الاختيار حتى 3" or ≥30% of answers contain a comma | bar of split-and-counted options |
| `open` | answers mostly unique and sentence-length | keyword chips + answer cards |
| `timestamp` | datetime dtype | used for ordering only |

Two cleaning steps matter for this sheet:

- **Country merge.** `Yemen`, `اليمن `, `القاهره` arrive as 7 distinct strings for
  3 countries. `COUNTRY_ALIASES` in `analytics.py` folds them — extend that dict
  as new countries come in.
- **Arabic normalisation, two layers.** `normalize_text` folds diacritics, tatweel
  and hamza forms so `أحياناً` and `احيانا` land in one bar. It is a *grouping key
  only* — the label shown is the most common original spelling, via `tidy`, so the
  screen never displays misspelled Arabic. Filter values are matched the same
  loose way, so a chip still works if the sheet spells it differently.

Single-choice questions with 2–10 options automatically become the filter chips
at the top, and every chart, open answer, KPI and table row respects them.

## API

| Method | Path | Notes |
|---|---|---|
| GET | `/api/health` | is a sheet loaded, and which |
| GET | `/api/meta` | row count, inferred schema, filter options |
| GET | `/api/kpis` | headline percentages |
| GET | `/api/highlights` | most common answer per closed question, strongest first |
| GET | `/api/stats` | every question with its distribution or open answers |
| GET | `/api/question/{id}` | one question block |
| GET | `/api/responses` | paginated raw rows, `search=` does full-row match |
| POST | `/api/source/upload` | multipart file |
| POST | `/api/source/drive` | `{"link": "https://docs.google.com/..."}` |
| GET | `/api/export/summary.csv` | flattened question/answer/count/percent |

All GET endpoints take `filters` as a URL-encoded JSON object:

```
/api/stats?filters={"النوع":["أنثى"],"كم عمرك؟":["17 الى 18 عاما"]}
```

Filter values are compared against **cleaned** text, which is what `/api/meta`
returns — pass those strings straight through and they will match.

## Notes before you ship this

- State lives in a module-level dict, so an upload replaces the sheet for every
  visitor and is lost on restart. For more than one user, persist to SQLite or
  a `sessionStorage`-keyed store.
- There is no auth. These are children's free-text answers; put it behind a login
  before it touches a public host, and keep the timestamp column out of any
  public build.
- Private Drive files need OAuth — the loader deliberately only handles
  link-shared files and tells you when it got an HTML login page instead.


