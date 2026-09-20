# Child Safety in the Digital World — Survey Results Dashboard

FastAPI backend and modern vanilla HTML/CSS/JS dashboard that reads a Google Forms export (`.xlsx`, `.xls`, `.csv`) from disk, file upload, or a Google Sheets/Drive link, and renders interactive statistics and visualizations with full RTL Arabic support, dynamic filtering, animations, and CSV export capabilities.

The dashboard includes a sticky navigation header, response counters, real participant quotes, KPI cards with circular progress indicators, dynamic filter chips, and four primary tabs:
- Overview (top answer per question and demographic breakdowns)
- Questions (distribution per question)
- Written Voices (qualitative open-ended responses)
- Raw Responses (searchable and paginated data table)

---

## Authentication and Security

The application is protected by a secure authentication layer:
- **Credential Storage**: Credentials can be configured in `.env` (`AUTH_USERNAME`, `AUTH_EMAIL`, `AUTH_PASSWORD`) or synced dynamically from an external Google Sheet user database (`AUTH_SHEET_URL`).
- **Password Hashing**: Verifies passwords using `bcrypt`.
- **Account Verification**: Automatically checks account status (`Active`).
- **Session Management**: Issues signed HMAC-SHA256 session cookies (`HttpOnly`, `SameSite=Lax`).
- **Route Protection**: All API endpoints and dashboard pages require authentication, redirecting unauthenticated requests to `/login`.

---

## Run with Docker Compose

```bash
# Start the container in detached mode
docker compose up -d

# View real-time logs
docker compose logs -f

# Stop the container
docker compose down
```

Open http://localhost:8000. All variables from `.env` and files in `data/` are automatically mounted.

---

## Run Locally (without Docker)

```bash
# Set up virtual environment
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Run development server
uvicorn app.main:app --reload --port 8000
```

Open http://127.0.0.1:8000 — the dataset in `data/` loads automatically on startup.
API documentation is available at `/docs`.

To use a different dataset: place the file into `data/`, or configure the `DRIVE_LINK` variable in `.env` (the Google Sheets file must be shared as "Anyone with the link").

---

## Project Structure

```
app/
  main.py        FastAPI application, routes, authentication middleware, and session management
  loaders.py     File loaders for local disk, multipart uploads, and Google Sheets/Drive export URLs
  analytics.py   Question classification, Arabic text normalization, country merging, distributions, and KPIs
  static/        Frontend dashboard assets (index.html, login.html, styles.css, app.js)
data/
  survey.xlsx    Default survey dataset
Dockerfile       Container definition based on python:3.11-slim
docker-compose.yml Container orchestration configuration
.env.example     Template for environment configuration
requirements.txt Python package dependencies
```

---

## Data Processing Pipeline

Column classifications are determined dynamically at load time:

| Type | Detection Criteria | Visualization |
|---|---|---|
| `single` | Limited repeated categorical values | Doughnut chart (<= 5 options) or horizontal bar |
| `multi` | Header contains selection limits or >= 30% of answers contain delimiters | Horizontal bar chart of split and counted options |
| `open` | High percentage of unique, sentence-length text | Keyword badges and response cards |
| `timestamp` | Datetime dtype | Chronological sorting and date range metadata |

### Normalization and Cleaning
- **Country Standardization**: Varied spellings in Arabic, English, and French (such as "Morocco,Casablanca", "Le Maroc", "Maroc") are normalized to a single consistent country label via `COUNTRY_ALIASES` in `analytics.py`.
- **Text Normalization**: Strips diacritics, tatweel, and hamza variations so variant spellings are grouped accurately under a unified canonical label.

---

## API Endpoints

| Method | Path | Description |
|---|---|---|
| POST | `/api/login` | Authenticate user and issue session cookie |
| POST | `/api/logout` | Clear user session cookie |
| GET | `/api/auth/me` | Current authenticated user profile |
| GET | `/api/health` | Service status and current dataset info |
| GET | `/api/meta` | Total responses, inferred schema, and filter options |
| GET | `/api/kpis` | Summary key performance indicators |
| GET | `/api/highlights` | Dominant answer per closed question |
| GET | `/api/stats` | Question distributions and open-ended responses |
| GET | `/api/question/{id}` | Single question analytical breakdown |
| GET | `/api/responses` | Paginated raw response rows with full-text search |
| POST | `/api/source/upload` | Upload new survey export file |
| POST | `/api/source/drive` | Update data source using Google Sheets link |
| GET | `/api/export/summary.csv` | Export summarized question-answer distributions as CSV |

All GET statistics endpoints support query filtering via the `filters` URL parameter:

```
/api/stats?filters={"Gender":["Female"],"Age":["17 to 18 years"]}
```

---

## Configuration Reference (.env)

| Variable | Description | Default |
|---|---|---|
| `AUTH_USERNAME` | Super admin fallback username | `admin` |
| `AUTH_EMAIL` | Super admin fallback email | `admin@example.com` |
| `AUTH_PASSWORD` | Super admin fallback password | `password123` |
| `SESSION_SECRET_KEY` | Secret key for signing HMAC session cookies | Recommended to generate a secure random string |
| `DRIVE_LINK` | Public Google Sheets/Drive survey data URL | - |
| `AUTH_SHEET_URL` | Google Sheets user authentication database URL | - |
| `PORT` | Application server port | `8000` |
