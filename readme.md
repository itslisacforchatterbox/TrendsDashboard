# 🎵 AI-Powered Music Trend Curation & Lifecycle Pipeline

An autonomous, serverless, **$0-budget data engineering pipeline** designed for independent music record labels, artist managers, and A&R teams. 

The pipeline continuously monitors short-form video feeds, streaming charts, and creator communities, extracts high-velocity social media formats using **Google Gemini AI**, deduplicates candidates against historical logs, matches them against an active artist roster's musical genres, and writes atomic updates to **Google Sheets** connected to **Looker Studio (Google Data Studio)**. 

It features an automated **Trend Lifecycle & Velocity Tracking Engine (Stage E)** that prevents artist managers from recommending stale or cooling trends by tracking view velocities, platform-specific decay half-lives, and structural evergreen formats.

---

## 📑 Table of Contents

- [Architectural Overview](#-architectural-overview)
- [Pipeline Lifecycle (Stages A–E)](#-pipeline-lifecycle-stages-ae)
- [Trend Status Determination Architecture](#-trend-status-determination-architecture)
  - [1. Status Taxonomy & Lifecycle States](#1-status-taxonomy--lifecycle-states)
  - [2. Platform-Specific Lifecycle Evaluation](#2-platform-specific-lifecycle-evaluation)
  - [3. The 3-Gate Evergreen Framework](#3-the-3-gate-evergreen-framework)
  - [4. The 28-Day Topical Idea Expiration Rule](#4-the-28-day-topical-idea-expiration-rule)
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
                                │  • TikTok (Billboard Top 50 + Formats) │
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
                                │  • 3-Gate Structural Nature Extractor  │
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
                                │  • Append New Trends (A4:O4)           │
                                └───────────────────┬────────────────────┘
                                                    │
                                                    ▼
                                ┌────────────────────────────────────────┐
                                │ Stage E: Trend Lifecycle & Status Audit│
                                │  • Batch YouTube View Delta Engine     │
                                │  • Native Short-Form Half-Life Decay   │
                                │  • 28-Day Topical Idea Expiration      │
                                │  • Single-Batch Column H Update        │
                                │  • Ghost Row Cleanup                   │
                                └───────────────────┬────────────────────┘
                                                    │
                                                    ▼
                                ┌────────────────────────────────────────┐
                                │  Live Google Sheets ──> Looker Studio  │
                                └────────────────────────────────────────┘
```

---

## 🔄 Pipeline Lifecycle (Stages A–E)

1. **Stage A: Multi-Source Ingestion (`src/sources/`)**  
   Collects raw, trending audio, viral video formats, and streaming movers across TikTok, YouTube, Spotify, and industry newsletters into normalized `RawItem` objects.
2. **Stage B: Structured AI Extraction (`src/classifier.py`)**  
   Assembles a **Unified Single-Call Prompt** grouping candidates into platform buckets. A single call to **Google Gemini** evaluates the candidates, filtering out corporate advertisements and e-commerce spam to extract exactly **3 to 5 curated trends per platform** via a strict Pydantic JSON schema (`UnifiedTrendResponse`). It also executes the **3-Gate Test** to structurally classify trends as either `Evergreen_Format` or `Temporal_Wave`.
3. **Stage C: Deduplication & Artist Matching (`src/matcher.py`)**  
   Normalizes genres using case- and punctuation-resilient regular expressions (`re.sub(r"[-_/]+", " ", ...)`). Cross-references incoming trends against the `Artist roster` to calculate match counts and formatted artist strings, while checking historical links in `Trend library` and `Send log` to eliminate duplicate entries.
4. **Stage D: Atomic Sync (`src/sheets.py`)**  
   Executes a single atomic batch append (`append_rows(..., table_range="A4:O4")`) to Google Sheets, instantly appending new rows without row-by-row rate limits.
5. **Stage E: Post-Run Lifecycle Audit (`src/tracker.py`)**  
   Audits every active trend in the spreadsheet. Computes view velocity deltas via batch YouTube queries, evaluates short-form platform age half-lives, transitions expired topical ideas to `💤 Stale`, protects `💡 Evergreen` content formats, updates Column H (`Status`) in a single atomic batch call, and wipes trailing ghost cells.

---

## 🧭 Trend Status Determination Architecture

Recommending a trend that peaked three weeks ago hurts an artist's algorithmic reach. The pipeline moves beyond static "Active" tags to a **dynamic, multi-factor lifecycle engine**.

```text
               ┌────────────────────────────────────────────────────────┐
               │                  TREND AUDIT PIPELINE                  │
               └───────────┬────────────────────────────────┬───────────┘
                           │                                │
                           ▼                                ▼
              [Structural Classification]          [Execution Platform]
              • Gate 1: Audio Ownership            • YouTube URL -> Idea
              • Gate 2: 18-Month Test              • TikTok/Spotify -> Velocity
              • Gate 3: Creative Template          • Manual Override Protection
                           │                                │
                           └───────────────┬────────────────┘
                                           │
                                           ▼
               ┌────────────────────────────────────────────────────────┐
               │                CALCULATED STATUS OUTPUT                │
               ├────────────────────────────────────────────────────────┤
               │ 💡 Evergreen │ 🚀 Surging │ 🔥 Peak │ 📉 Cooling │ 💤 Stale │
               └────────────────────────────────────────────────────────┘
```

### 1. Status Taxonomy & Lifecycle States

| Status | Label | Definition & Threshold | Action for Artist / Manager |
| :--- | :--- | :--- | :--- |
| **`💡 Evergreen`** | Evergreen | Timeless creative format using the artist's *own* music. Immune to 28-day decay. | **Permanent Asset:** Execute anytime for catalog releases. |
| **`🚀 Surging`** | Surging | Breakout velocity ($V > 40\text{k views/day}$) or active sound $\le 7$ days old. | **High Priority:** Film and publish within 48–72 hours. |
| **`🔥 Peak`** | Peak | High volume ($V > 15\text{k views/day}$), but daily growth has plateaued ($8–14$ days old). | **Caution:** Execute only with an immediate, high-effort angle. |
| **`📉 Cooling`** | Cooling | View velocity collapsing or audio wave $15–27$ days old. Saturation reached. | **Skip:** Algorithmic reach is actively decaying. |
| **`💤 Stale`** | Stale | Daily velocity flatlined ($< 5\text{k/day}$) or age $\ge 28$ days. Cultural wave has ended. | **Do Not Execute:** Archive or ignore. |
| **`Idea`** | Creative Idea | Music video release, topical reference point, or concept without a live audio vehicle. | **Inspiration:** Adapt narrative or visual style for own rollout. |

---

### 2. Platform-Specific Lifecycle Evaluation

The engine applies distinct evaluation logic depending on the link origin and platform:

#### A. YouTube-Sourced Trends (`youtube.com` / `youtu.be`)
* **Core Rule:** Music videos charting on YouTube (e.g. Ayra Starr collab, Eminem music video) are **cultural reference points, not short-form audio trends**. An artist cannot lip-sync or dance to an arbitrary YouTube video link on their own TikTok account.
* **Status Assignment:** Any trend whose `Example link` is a YouTube URL is classified as **`Idea`**.
* **Expiration:** Because these represent news/chart moments, they are governed by the **28-Day Expiration Rule**. If $\text{Age} \ge 28\text{ days}$, they automatically transition to **`💤 Stale`**.
* **YouTube Shorts Exception:** If the link is explicitly a YouTube Shorts sound/format, the engine runs a quantitative view velocity check via the YouTube Data API:
  $$\text{Daily Velocity } (V) = \frac{\text{Current Views} - \text{Snapshot Views}}{\text{Hours Elapsed}} \times 24$$
  * If $V \ge 40,000 \text{ views/day}$ and $\text{Age} \le 10 \text{ days} \implies$ **`🚀 Surging`**
  * If $V \ge 15,000 \text{ views/day}$ and $\text{Age} \le 21 \text{ days} \implies$ **`🔥 Peak`**
  * If $V < 15,000 \text{ views/day}$ and $\text{Age} \le 28 \text{ days} \implies$ **`📉 Cooling`**
  * If $\text{Age} > 28 \text{ days} \implies$ **`💤 Stale`**

#### B. Spotify Audio Trends (Kworb Australia Chart)
* Evaluates real-time daily streaming numbers and rank shifts directly from Kworb's daily data:
  * **`🚀 Surging`:** Day-over-day streams positive (`Streams+ > 0`) and weekly momentum positive (`7Day+ > 0`).
  * **`🔥 Peak`:** Daily streams $> 100,000$, but day-over-day growth has stalled or turned negative.
  * **`📉 Cooling`:** Multi-day drop-off (`Streams+ < 0` and `7Day+ < 0`).
  * **`💤 Stale`:** Drops out of the Top 100/200 chart entirely or age $\ge 28$ days.

#### C. Native TikTok & Instagram Audio Trends
* Evaluates vertical short-form sound half-lives:
  * **Day 0–7 ($\le 7$ days):** **`🚀 Surging`** (Early breakout window)
  * **Day 8–14 ($8–14$ days):** **`🔥 Peak`** (FYP saturation window)
  * **Day 15–27 ($15–27$ days):** **`📉 Cooling`** (Algorithm fatigue)
  * **Day 28+ ($\ge 28$ days):** **`💤 Stale`** (Dead wave)

---

### 3. The 3-Gate Evergreen Framework

Rather than using fragile title keywords (like `"acoustic"` or `"freestyle"`), the pipeline uses a **3-Gate structural test** executed by Gemini at extraction time:

```text
Gate 1: Audio Ownership (The Dependency Test)
  Does this trend require a specific 3rd-party commercial song or audio meme?
  ├── YES ──► Temporal Wave (Subject to 14–28 day decay)
  └── NO  ──► Proceed to Gate 2

Gate 2: Temporal Invariance (The 18-Month Rule)
  Can an artist execute this exact concept 18 months from now for a new single?
  ├── NO  ──► Temporal Wave (Tied to current news or meme culture)
  └── YES ──► Proceed to Gate 3

Gate 3: Template Structure (The Vehicle Test)
  Is this a repeatable performance or storytelling template (Type = Format / Challenge)?
  ├── NO  ──► Topical Idea
  └── YES ──► 💡 Evergreen (Permanent asset; never expires)
```

**Examples of True Evergreen Formats:**
* *Stripped / Acoustic Performance:* One-take intimate vocal close-up.
* *Unreleased Snippet / Lyric Teaser:* Panning studio B-roll or car singing with on-screen text.
* *Open Verse / Duet Challenge:* Leaving an 8-bar gap for creators to stitch.
* *DAW Beat Deconstruction:* Screen-recording the step-by-step production of a beat drop.

**Manual Curation Override:** If a human manager enters `Evergreen` in Column L (`Source`) or Column M (`Notes`), the lifecycle tracker honors it as an immutable manual override and assigns **`💡 Evergreen`**.

---

### 4. The 28-Day Topical Idea Expiration Rule

Trending ideas based on cultural moments (e.g. awards shows, viral news, seasonal themes) have a finite shelf-life. 
* Any row where `Type == "Topic"`, `Status == "Idea"`, or whose link is a standard YouTube video is tagged as an **Idea**.
* The tracker monitors its `Date spotted` (Column G).
* Once $\text{Age} \ge 28 \text{ days}$, its status automatically transitions from `Idea` $\rightarrow$ **`💤 Stale`**.
* This keeps your Looker Studio dashboard clean and prevents managers from acting on outdated cultural moments.

---

## 📂 Project Directory Structure

```text
TrendsDashboard/
├── .cache/                                 # Local disk cache (auto-generated, git-ignored)
│   ├── raw_ingested_cache.json            # Scraped raw candidates (preserves scraping quotas)
│   ├── classified_trends_checkpoint.json  # Checkpointed LLM outputs (preserves Gemini RPD)
│   └── metric_snapshots.json              # Historical view/stream counts for delta velocity tracking
├── src/
│   ├── __init__.py
│   ├── config.py                          # Global taxonomy Literals, env loader, multi-key rotation
│   ├── models.py                          # Pydantic schemas (RawItem, ExtractedTrend, UnifiedTrendResponse)
│   ├── cache.py                           # Cache manager with TTL and file-corruption safety
│   ├── classifier.py                      # Gemini LLM engine with unified prompt & key rotation
│   ├── matcher.py                         # Regex genre normalizer & dual-genre artist matching
│   ├── tracker.py                         # Stage E: Quantitative lifecycle & velocity delta engine
│   ├── sheets.py                          # gspread client with atomic batch appending
│   ├── pipeline.py                        # Main CLI orchestrator with granular flags
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
Test the entire pipeline from ingestion through classification, matching, and lifecycle audit without modifying your Google Sheet:
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
8. **`Status`**: Dynamic lifecycle state: `🚀 Surging` | `🔥 Peak` | `📉 Cooling` | `💤 Stale` | `💡 Evergreen` | `Idea`.
9. **`Example link`**: Canonical URL to an example video, Spotify track, or TikTok audio page.
10. **`How to execute it`**: 1-sentence tactical prompt for an independent artist.
11. **`Hashtags / keywords`**: Space-separated searchable tags.
12. **`Source`**: Ingestion provenance (`Automated Pipeline` or `Evergreen`).
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

```bash
# 1. Full Production Pipeline (Scrape -> Classify -> Match -> Sync -> Stage E Lifecycle Audit)
python -m src.pipeline

# 2. Lifecycle Audit Only (Audit and update Column H statuses in Google Sheets without scraping)
python -m src.pipeline --track-lifecycle

# 3. Lifecycle Audit Simulation (Simulate status transitions in terminal; skips Sheets write)
python -m src.tracker

# 4. Dry-Run Mode (Simulate full pipeline execution without modifying Google Sheets)
python -m src.pipeline --dry-run

# 5. Scrape-Only Mode (Pull from scrapers and save to .cache/; skips Gemini & Sheets)
python -m src.pipeline --refresh-cache --scrape-only

# 6. Classify-Only Mode (Read from local .cache/; runs Gemini & Matching; 0 network scraping)
python -m src.pipeline --classify-only --dry-run

# 7. Isolate a Single Platform Scraper (Choices: tiktok, youtube, spotify, rss)
python -m src.pipeline --source tiktok --scrape-only
python -m src.pipeline --source spotify --scrape-only

# 8. Force Cache Invalidation (Bypass TTL and scrape everything fresh)
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
* **Metric Snapshots (`.cache/metric_snapshots.json`):** Stores historical view counts and timestamps to calculate velocity deltas over time without an external database.

### 6. Contiguous Boundary & Ghost-Row Protection
`src/tracker.py` stops scanning rows immediately when it hits the end of the sequential `T\d{3}` IDs. It prevents stray records at the bottom of the sheet from introducing row-shift offsets, and automatically wipes any ghost labels appearing in trailing cells.

---

## 🛠 Troubleshooting & FAQs

#### Q: Why are all YouTube trends categorized as "Idea"?
* **Answer:** YouTube links represent full-length music videos or audio uploads (not replicable TikTok/Reels creator trends). To prevent artists from jumping on a song without an active challenge or sound vehicle, they are classified as **`Idea`** and expire after 28 days if not acted upon.

#### Q: How does the system prevent Evergreen trends from expiring?
* **Answer:** The pipeline uses the **3-Gate Test** to verify that a trend is an audio-agnostic creative format (e.g. lyric reveal, open-verse duet, acoustic performance) where the artist uses their *own* music. Once tagged **`💡 Evergreen`**, the lifecycle tracker exempts it from the 28-day expiration rule.

#### Q: Google Cloud says: *"An organisation policy that blocks service accounts key creation has been enforced."*
* **Fix:** Your Google Workspace domain enforces `constraints/iam.disableServiceAccountKeyCreation`. Create a free GCP project using a personal `@gmail.com` account, generate your `service_account.json` there, and share your spreadsheet with that service account's email address.

#### Q: Getting `503 UNAVAILABLE` from Gemini API
* **Fix:** Google's free-tier model capacity occasionally experiences momentary traffic spikes. The pipeline includes built-in exponential backoff with jitter (`3s`, `6s`, `12s`). It retries automatically and will switch to your backup key if capacity remains unavailable.

#### Q: Why did a trend have `Matched Artists Count = 0`?
* **Fix:** The trend's genres didn't match any artists in your `Artist roster`. Ensure Gemini adheres to the canonical genre taxonomy: `['Pop', 'R&B', 'Dark R&B', 'Hip-Hop', 'Rap', 'Pop Rap', 'Trap', 'Indian Hip-Hop', 'R&B/Soul', 'Soul', 'House', 'Dance', 'Edm', 'Indie Pop', 'Afrobeats', 'All']`.

---

## 🗺 Technical Roadmap

- [x] **Phase 1:** Clean and standardize Google Sheets schema (`Trend library`, `Artist roster`, `Send log`).
- [x] **Phase 2:** Provision free-tier API credentials and establish service account authentication.
- [x] **Phase 3:** Build modular ingestion engine, single-call Gemini classification, resilient genre matching, and atomic sheet syncing.
- [x] **Phase 4:** Build the **Quantitative Trend Lifecycle & Velocity Tracking Engine (Stage E)** with 3-Gate Evergreen detection and 28-day idea expiration.
- [ ] **Phase 5:** Cloud deployment via **GitHub Actions** (automated weekly cron schedule every Monday at 9:00 AM UTC).