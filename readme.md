# 🎵 AI-Powered Music Trend Curation Pipeline

An autonomous, serverless, **$0-budget data engineering pipeline** designed for independent music record labels, artist managers, and A&R teams. 

The pipeline continuously monitors short-form video feeds, streaming charts, and creator communities, extracts high-velocity social media formats using **Google Gemini AI**, deduplicates candidates against historical logs, matches them against an active artist roster's musical genres, and writes atomic updates to **Google Sheets** connected to **Looker Studio (Google Data Studio)**.

---

## 📑 Table of Contents

- [Architectural Overview](#-architectural-overview)
- [Pipeline Lifecycle (Stages A–D)](#-pipeline-lifecycle-stages-ad)
- [Project Directory Structure](#-project-directory-structure)
- [Prerequisites & Free-Tier Setup](#-prerequisites--free-tier-setup)
- [Installation & Quickstart](#-installation--quickstart)
- [Environment Configuration (`.env`)](#-environment-configuration-env)
- [Google Sheets Data Schema](#-google-sheets-data-schema)
- [CLI Usage & Operating Modes](#-cli-usage--operating-modes)
- [Performance & Budget Optimizations](#-performance--budget-optimizations)
- [Troubleshooting & FAQs](#-troubleshooting--faqs)
- [Technical Roadmap](#-technical-roadmap)

---

## 🏗 Architectural Overview

```
                                ┌────────────────────────────────────────┐
                                │      Multi-Source Data Ingestion       │
                                ├────────────────────────────────────────┤
                                │  • TikTok (Billboard Top 50 + Apify)   │
                                │  • YouTube (Data API v3 + Trends24)    │
                                │  • Spotify (Kworb Daily Streams AU)    │
                                │  • Editorial (Substack / Industry RSS) │
                                └───────────────────┬────────────────────┘
                                                    │
                                                    ▼
                                ┌────────────────────────────────────────┐
                                │   Local Disk Cache (.cache/raw_items)  │
                                └───────────────────┬────────────────────┘
                                                    │
                                                    ▼
                                ┌────────────────────────────────────────┐
                                │    Stage B: Structured LLM Engine      │
                                │  • Unified Single-Call Platform Batch  │
                                │  • Google Gemini 3.8 / Flash           │
                                │  • Automatic API Key Quota Rotation    │
                                └───────────────────┬────────────────────┘
                                                    │
                                                    ▼
                                ┌────────────────────────────────────────┐
                                │    Stage C: Normalization & Matching   │
                                │  • Regex Genre Normalization Engine    │
                                │  • Dual-Genre Artist Roster Matching   │
                                │  • URL & Title Deduplication           │
                                └───────────────────┬────────────────────┘
                                                    │
                                                    ▼
                                ┌────────────────────────────────────────┐
                                │   Stage D: Atomic Batch Write (gspread)│
                                │  • Append to Google Sheets (Row 4+)    │
                                │  • Live Connector to Looker Studio     │
                                └────────────────────────────────────────┘
```

---

## 🔄 Pipeline Lifecycle (Stages A–D)

1. **Stage A: Multi-Source Ingestion (`src/sources/`)**
   Collects raw, trending audio, viral video formats, and streaming movers across TikTok, YouTube, Spotify, and industry newsletters into normalized `RawItem` objects.
2. **Stage B: Structured AI Extraction (`src/classifier.py`)**
   Assembles a **Unified Single-Call Prompt** grouping candidates into platform buckets. A single call to **Google Gemini** evaluates the candidates, filtering out corporate advertisements and e-commerce spam to extract exactly **3 to 5 curated trends per platform** via a strict Pydantic JSON schema (`UnifiedTrendResponse`).
3. **Stage C: Deduplication & Artist Matching (`src/matcher.py`)**
   Normalizes genres using case- and punctuation-resilient regular expressions (`re.sub(r"[-_/]+", " ", ...)`). Cross-references incoming trends against the `Artist roster` to calculate match counts and formatted artist strings, while checking historical links in `Trend library` and `Send log` to eliminate duplicate entries.
4. **Stage D: Atomic Sync (`src/sheets.py`)**
   Executes a single atomic batch append (`append_rows(..., table_range="A4:O4")`) to Google Sheets, instantly populating the Looker Studio dashboard without triggering per-row API quota limits.

---

## 📂 Project Directory Structure

```text
TrendsDashboard/
├── .cache/                                 # Local disk cache (auto-generated, git-ignored)
│   ├── raw_ingested_cache.json            # Scraped raw candidates (preserves scraping quotas)
│   └── classified_trends_checkpoint.json  # Checkpointed LLM outputs (preserves Gemini RPD)
├── src/
│   ├── __init__.py
│   ├── config.py                          # Global settings, taxonomy Literals, env loader
│   ├── models.py                          # Pydantic schemas (RawItem, ExtractedTrend, UnifiedResponse)
│   ├── cache.py                           # Cache manager with TTL and file-corruption safety
│   ├── classifier.py                      # Gemini LLM engine with unified prompt & key rotation
│   ├── matcher.py                         # Regex genre normalizer & dual-genre artist matching
│   ├── sheets.py                          # gspread client with atomic batch appending
│   ├── pipeline.py                        # Main CLI orchestrator
│   └── sources/                           # Modular plug-and-play scraping modules
│       ├── __init__.py
│       ├── base.py                        # Abstract BaseSource interface
│       ├── tiktok.py                      # Billboard TikTok Top 50 + high-view creator formats
│       ├── youtube.py                     # Official YouTube API v3 + Trends24 fallback
│       ├── spotify.py                     # Kworb Spotify Daily Australia scraper (0-auth)
│       └── rss.py                         # Substack & editorial industry newsletter parser
├── .env.example                           # Template for required environment variables
├── requirements.txt                       # Locked production dependencies
├── service_account.json                   # Google Cloud Service Account key (git-ignored)
└── README.md
```

---

## 🔑 Prerequisites & Free-Tier Setup

You can run this entire stack for **$0/month** by taking advantage of recurring free-tier allowances:

### 1. Google Cloud Service Account (Google Sheets API)
* Enable the **Google Sheets API** and **Google Drive API** in your Google Cloud Console.
* Create a **Service Account**, generate a JSON key file, and save it as `service_account.json` in your project root.
* Open your Google Sheet, click **Share**, and grant your Service Account email (e.g. `pipeline-sa@project.iam.gserviceaccount.com`) **Editor** permissions.
* *Note on Corporate Accounts:* If your Google Cloud organization enforces the `iam.disableServiceAccountKeyCreation` policy, create the project under a personal `@gmail.com` account and share the corporate sheet with that service account.

### 2. Google Gemini API (AI Studio)
* Generate a free API key at [Google AI Studio](https://aistudio.google.com/).
* **Pro-Tip:** Generate a secondary key under a second project to configure `GEMINI_API_KEY_BACKUP`. The pipeline will automatically switch keys if your primary hits a daily limit.

### 3. Apify Free Tier (TikTok Scraper)
* Create an account at [Apify](https://apify.com/) to receive a recurring **$5.00/month free credit**.
* Retrieve your API token from **Settings > Integrations > API Token**.
* The pipeline caps runs to ~10 items, spending `< $0.01` per execution.

### 4. YouTube Data API v3
* In the Google Cloud Console, enable the **YouTube Data API v3** and create an API Key under **APIs & Services > Credentials**.

---

## 🚀 Installation & Quickstart

### 1. Clone & Set Up Virtual Environment
```bash
git clone <your-repo-url>
cd TrendsDashboard
python3 -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Configure Environment Variables
Copy `.env.example` to `.env`:
```bash
cp .env.example .env
```
Open `.env` and fill in your keys (see below).

### 3. Run a Non-Destructive Dry Run
Test the entire pipeline from ingestion through classification and matching without modifying your Google Sheet:
```bash
python -m src.pipeline --dry-run
```

---

## ⚙ Environment Configuration (`.env`)

```bash
# ==============================================================================
# Google Cloud Service Account & Google Sheets
# ==============================================================================
# Path to service account JSON (or raw JSON string for GitHub Actions)
GCP_SA_CREDENTIALS="service_account.json"

# The Google Sheet Document ID (from URL: /d/<GOOGLE_SHEET_ID>/edit)
GOOGLE_SHEET_ID="your_google_sheet_id_here"

# ==============================================================================
# AI Extraction (Google Gemini 3.8 / Flash)
# ==============================================================================
# Primary API Key from https://aistudio.google.com/
GEMINI_API_KEY="AIzaSyPrimary..."

# Backup API Keys (Automatically invoked on 429 / daily quota exhaustion)
GEMINI_API_KEY_BACKUP="AIzaSyBackup1..."
GEMINI_API_KEY_BACKUP_2="AIzaSyBackup2..."

# Optional: Override model alias (default: gemini-flash-latest)
GEMINI_MODEL="gemini-flash-latest"

# ==============================================================================
# Ingestion API Credentials
# ==============================================================================
# Apify Free Tier Token ($5.00/month free credit)
APIFY_API_TOKEN="apify_api_..."

# Google Cloud YouTube Data API v3 key
YOUTUBE_API_KEY="AIzaSy..."

# ==============================================================================
# Feature-Flagged Ingestion Sources (Optional)
# ==============================================================================
# Spotify Web API (Optional: Kworb scraper runs out-of-the-box with 0 keys)
SPOTIFY_CLIENT_ID=""
SPOTIFY_CLIENT_SECRET=""

# TokInsight on RapidAPI (Optional: leave blank to skip)
RAPIDAPI_KEY=""
```

---

## 📊 Google Sheets Data Schema

The pipeline interacts with three specific tabs inside your Google Sheet. **Table headers start on Row 4** (Rows 1–3 are reserved for dashboards, operational notes, and color legends):

### Tab 1: `Trend library` (Atomic Output Tab)
*Columns A through O (15 Columns):*
1. **`ID`**: Auto-generated sequential ID (`T001`, `T019`, `T022`, etc.).
2. **`Trend name`**: Short title of the sound, challenge, or video format.
3. **`Trend summary`**: Narrative paragraph explaining origin, execution style, and creator behavior.
4. **`Platform`**: `TikTok` | `Instagram` | `YouTube` | `YouTube Shorts` | `Multi-platform`.
5. **`Type`**: `Sound` | `Format` | `Challenge` | `Topic` | `Hashtag`.
6. **`Genres`**: Comma-separated list drawn strictly from the canonical genre taxonomy.
7. **`Date spotted`**: Date of cataloging (`DD Mon YYYY` format, e.g. `26 Oct 2026`).
8. **`Status`**: `Active` | `Idea`.
9. **`Example link`**: Canonical URL to an example video, Spotify track, or TikTok audio page.
10. **`How to execute it`**: 1-sentence tactical prompt for an independent artist.
11. **`Hashtags / keywords`**: Space-separated searchable tags.
12. **`Source`**: Ingestion provenance (`Automated Pipeline`).
13. **`Notes`**: Strategic A&R advice, audio mix notes, or audience targeting considerations.
14. **`Matched Artists Count`**: Integer count of matched artists on your roster.
15. **`Matched Artists Names`**: Semicolon-delimited list of artist names (e.g. `K.LAW; Allira; TGAR`).

### Tab 2: `Artist roster` (Read-Only Matching Database)
* **Header Row:** Row 4.
* **Key Columns:** Column B (`Artist`) and Column C (`Genres`).
* **Format:** Genres can be stored as comma-separated text (`Pop, R&B`) or JSON arrays (`["Pop", "R&B", "Trap"]`).

### Tab 3: `Send log` (Historical Tracking & Deduplication)
* **Header Row:** Row 4.
* Tracks artist recommendations that have already been dispatched, preventing duplicate recommendations.

> **Note on Connector Pages (`_...`):** Auxiliary sheets starting with an underscore are used by Looker Studio for joins. The pipeline never modifies these tabs.

---

## 💻 CLI Usage & Operating Modes

The pipeline includes granular CLI flags to test individual components without burning quotas:

```bash
# 1. Standard Production Run (Scrapes, classifies, matches, and writes to Sheets)
python -m src.pipeline

# 2. Dry-Run Mode (Simulates everything and prints table to console; skips Sheets)
python -m src.pipeline --dry-run

# 3. Scrape-Only Mode (Pulls from scrapers and saves to .cache/; skips Gemini & Sheets)
python -m src.pipeline --refresh-cache --scrape-only

# 4. Classify-Only Mode (Reads from local .cache/; runs Gemini & Matching; 0 network scraping)
python -m src.pipeline --classify-only --dry-run

# 5. Isolate a Single Platform Scraper (Choices: tiktok, youtube, spotify, rss)
python -m src.pipeline --source tiktok --scrape-only
python -m src.pipeline --source spotify --scrape-only

# 6. Force Cache Invalidation (Bypasses TTL and scrapes everything fresh)
python -m src.pipeline --refresh-cache
```

---

## ⚡ Performance & Budget Optimizations

### 1. Single-Call Unified Prompt (1 Request Per Day)
Rather than executing separate LLM requests for each source, `src/classifier.py` compiles raw items into one structured prompt with Markdown dividers. Gemini returns a `UnifiedTrendResponse` with dedicated lists for each platform, consuming **exactly 1 API request per run**.

### 2. Automatic Gemini API Key Rotation
If a key hits Google's free-tier rate limit (`429 RESOURCE_EXHAUSTED`), the classifier catches the exception, logs a warning, and switches to `GEMINI_API_KEY_BACKUP` without failing the pipeline.

### 3. $0 Spotify Ingestion (Kworb Scraping Engine)
Instead of dealing with Spotify Developer App restrictions (`403 Forbidden` on playlists under Client Credentials), `src/sources/spotify.py` parses Kworb's daily Australia streaming charts. It extracts the **Top 30 streaming tracks**, stream volumes, and valid Spotify URLs using zero API keys.

### 4. Apify Free-Tier Guardrails
`src/sources/tiktok.py` combines the **official Billboard TikTok Top 50 Chart** (0 Apify credits) with an Apify creator format scraper capped at 10 items with a `playCount > 50,000` quality gate. This setup spends `< $0.01` per run against your $5.00 monthly credit.

### 5. Multi-Tier Checkpointing
* **Raw Item Cache (`.cache/raw_ingested_cache.json`):** Scraped payloads are stored on disk with a 12-hour TTL.
* **LLM Checkpoint (`.cache/classified_trends_checkpoint.json`):** Classified trends are keyed by content hash. If a downstream step fails, restarting the script reloads previous classifications in milliseconds.

---

## 🛠 Troubleshooting & FAQs

#### Q: Google Cloud says: *"An organisation policy that blocks service accounts key creation has been enforced."*
* **Fix:** Your Google Workspace domain enforces `constraints/iam.disableServiceAccountKeyCreation`. Create a free GCP project using a personal `@gmail.com` account, generate your `service_account.json` there, and share your spreadsheet with that service account's email address.

#### Q: Getting `503 UNAVAILABLE` from Gemini API
* **Fix:** Google's free-tier model capacity occasionally experiences momentary traffic spikes. The pipeline includes built-in exponential backoff with jitter (`3s`, `6s`, `12s`). It retries automatically and will switch to your backup key if capacity remains unavailable.

#### Q: VS Code warning: *"An environment file is configured but terminal environment injection is disabled."*
* **Fix:** Add `"python.terminal.useEnvFile": true` to your `.vscode/settings.json`, or ignore it. The script calls `load_dotenv()` explicitly at runtime, so your `.env` variables load regardless.

#### Q: Why did a trend have `Matched Artists Count = 0`?
* **Fix:** The trend's genres didn't match any artists in your `Artist roster`. Ensure Gemini adheres to the canonical genre taxonomy: `['Pop', 'R&B', 'Dark R&B', 'Hip-Hop', 'Rap', 'Pop Rap', 'Trap', 'Indian Hip-Hop', 'R&B/Soul', 'Soul', 'House', 'Dance', 'Edm', 'Indie Pop', 'Afrobeats', 'All']`.

---

## 🗺 Technical Roadmap

- [x] **Phase 1:** Clean and standardize Google Sheets schema (`Trend library`, `Artist roster`, `Send log`).
- [x] **Phase 2:** Provision free-tier API credentials and establish service account authentication.
- [x] **Phase 3:** Build modular ingestion engine, single-call Gemini classification, resilient genre matching, and atomic sheet syncing.
- [ ] **Phase 4:** Cloud deployment via **GitHub Actions** (automated weekly cron schedule every Monday at 9:00 AM UTC).
- [ ] **Phase 5:** Implement **Trend Lifecycle & Velocity Tracking** (auto-promoting active trends between `🚀 Surging`, `🔥 Peak`, `📉 Cooling`, and `💤 Stale` using daily view delta calculations).