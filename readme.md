# 🎵 AI-Powered Music Trend Curation & Lifecycle Pipeline

An autonomous, serverless, **$0-budget data engineering pipeline** designed for independent record labels, artist managers, and A&R teams. 

The pipeline monitors global and regional short-form video feeds, streaming charts, creator communities, and music marketing publications. Using **Google Gemini AI**, it filters out commercial noise, extracts high-velocity social media formats tailored to an active artist roster's real-world aesthetic and sonic identities, deduplicates candidates against historical logs, synchronizes atomic updates to **Google Sheets**, and feeds a live **Looker Studio (Google Data Studio)** intelligence dashboard.

It features an automated **Trend Lifecycle & Velocity Tracking Engine (Stage E)** that monitors view velocity deltas and platform decay rates, updating statuses dynamically so artist managers never pitch cooling or dead trends.

---

## 📑 Table of Contents

- [Architectural Overview](#-architectural-overview)
- [Core Methodologies & Innovations](#-core-methodologies--innovations)
  - [1. Persona-Driven Curation (vs. Naive Genre Matching)](#1-persona-driven-curation-vs-naive-genre-matching)
  - [2. The 3-Gate / 4-Pillar Evergreen Framework](#2-the-3-gate--4-pillar-evergreen-framework)
  - [3. Quantitative Trend Lifecycle & Velocity Tracking](#3-quantitative-trend-lifecycle--velocity-tracking)
  - [4. The 28-Day Topical Idea Expiration Rule](#4-the-28-day-topical-idea-expiration-rule)
  - [5. Zero-Leakage Privacy Architecture](#5-zero-leakage-privacy-architecture)
- [Pipeline Lifecycle (Stages A–E)](#-pipeline-lifecycle-stages-a-e)
- [Project Directory Structure](#-project-directory-structure)
- [Google Sheets Data Schemas](#-google-sheets-data-schemas)
  - [Tab 1: `Trend library`](#tab-1-trend-library-atomic-output-tab)
  - [Tab 2: `Artist profiles`](#tab-2-artist-profiles-private-persona-database)
  - [Tab 3: `Artist roster`](#tab-3-artist-roster-read-only-matching-database)
  - [Tab 4: `Send log`](#tab-4-send-log-deduplication--history)
- [Prerequisites & Free-Tier Setup](#-prerequisites--free-tier-setup)
- [Installation & Quickstart](#-installation--quickstart)
- [Environment Configuration (`.env`)](#-environment-configuration-env)
- [CLI Usage & Operating Modes](#-cli-usage--operating-modes)
- [Standalone Maintenance Tools](#-standalone-maintenance-tools)
- [GitHub Actions Automation & Catch-Up Logic](#-github-actions-automation--catch-up-logic)
- [Troubleshooting & FAQs](#-troubleshooting--faqs)

---

## 🏗 Architectural Overview

```
                                ┌────────────────────────────────────────┐
                                │      Multi-Source Data Ingestion       │
                                ├────────────────────────────────────────┤
                                │  • TikTok (Billboard Top 50 + Formats) │
                                │  • YouTube (Data API v3 - 50 videos)   │
                                │  • Spotify (Kworb Daily Streams AU 30) │
                                │  • Editorial (Later, SocialBee, Blogs) │
                                └───────────────────┬────────────────────┘
                                                    │
                                                    ▼
                                ┌────────────────────────────────────────┐
                                │   Local Disk Cache (.cache/raw_items)  │
                                └───────────────────┬────────────────────┘
                                                    │
                                                    ▼
┌───────────────────────────────┐  ┌────────────────────────────────────────┐
│ Private Google Sheet Database │  │    Stage B: Structured LLM Engine      │
├───────────────────────────────┤  ├────────────────────────────────────────┤
│ Tab: 'Artist profiles'        │─►│  • Injects Rich Roster Intelligence    │
│ • Bios, Sonic Traits, Releases│  │  • Unified Single-Call Batch (1 RPD)   │
│ • Instagram & TikTok Themes   │  │  • Multi-Key Quota Rotation (429)      │
└───────────────────────────────┘  │  • Paced Backoff & Unblocked Timeouts  │
                                   │  • 3-Gate Structural Nature Extractor  │
                                   └───────────────────┬────────────────────┘
                                                       │
                                                       ▼
                                   ┌────────────────────────────────────────┐
                                   │    Stage C: Personalization & Match    │
                                   │  • AI Target Artist Assignment         │
                                   │  • A&R Strategic Fit Reasoning         │
                                   │  • URL & Title Deduplication           │
                                   └───────────────────┬────────────────────┘
                                                       │
                                                       ▼
                                   ┌────────────────────────────────────────┐
                                   │   Stage D: Atomic Batch Sync (gspread) │
                                   │  • Append New Trends (A4:O4)           │
                                   └───────────────────┬────────────────────┘
                                                       │
                                                       ▼
                                   ┌────────────────────────────────────────┐
                                   │ Stage E: Quantitative Lifecycle Audit  │
                                   │  • Batch YouTube View Delta Engine     │
                                   │  • Native Short-Form Half-Life Decay   │
                                   │  • 28-Day Topical Idea Expiration      │
                                   │  • Single-Batch Column H Update        │
                                   │  • Trailing Ghost Cell Cleanup         │
                                   └───────────────────┬────────────────────┘
                                                       │
                                                       ▼
                                   ┌────────────────────────────────────────┐
                                   │  Live Google Sheets ──► Looker Studio  │
                                   └────────────────────────────────────────┘
```

---

## 🧠 Core Methodologies & Innovations

### 1. Persona-Driven Curation (vs. Naive Genre Matching)

Early iterations extracted generic trends and ran string matching against artist genres (e.g. matching an upbeat house dance trend to any artist with `"Pop"` in their tags). This resulted in generic recommendations misaligned with specific artist aesthetics (e.g., pitching a Broadway-style confessional duet to an underground trap rapper).

The upgraded pipeline treats Gemini Flash as a **virtual A&R Director**:
1. At startup, `src/artist_profiler.py` loads rich artist dossiers from the private **`Artist profiles`** tab in Google Sheets.
2. The prompt injects real-world artist context: **cultural background, vocal style, audio metrics (energy, tempo, key, danceability), recent releases, and active social media themes** (e.g. late-night car singing, boutique fitness aesthetics, DAW screen recordings).
3. Gemini evaluates candidate trends against this roster, outputting:
   * **`target_artists`**: The specific 1–3 roster artists who should execute the trend.
   * **`artist_fit_reasoning`**: A strategic explanation detailing why the format aligns with their current release cycle or persona (written directly into Column M: `Notes`).
   * **`how_to_execute_it`**: A tactical, 1-sentence prompt telling the artist what to film or perform.

---

### 2. The 3-Gate / 4-Pillar Evergreen Framework

A major vulnerability in trend curation pipelines is **Evergreen bloat**: over-classifying transient TikTok transition tricks, cosplay edits, and movie trailer cuts as "Evergreen" formats. Once marked evergreen, trends never decay, cluttering the dashboard with outdated records.

The pipeline applies a strict **3-Gate Structural Test** at extraction time:

```text
Gate 1: Audio Ownership (The Dependency Test)
  Does this trend require a specific 3rd-party commercial song or audio meme?
  ├── YES ──► Temporal Wave (Subject to 14–28 day decay)
  └── NO  ──► Proceed to Gate 2

Gate 2: Temporal Invariance (The 18-Month Test)
  Can an artist execute this exact concept 18 months from now for a new single?
  ├── NO  ──► Temporal Wave (Tied to current news, holidays, or memes)
  └── YES ──► Proceed to Gate 3

Gate 3: Template Structure (The Vehicle Test)
  Is this a repeatable performance or storytelling template (Type = Format / Challenge)?
  ├── NO  ──► Topical Idea
  └── YES ──► 💡 Evergreen (Permanent asset; immune to 28-day decay)
```

#### The 4 Foundational Evergreen Pillars
Gemini defaults to `Temporal_Wave`. It is permitted to assign `Evergreen_Format` **only** if the format satisfies four craft-focused pillars:
1. **Audio-Agnostic:** Executed using the artist's *own original music*.
2. **Timeless:** Independent of current pop-culture events or holidays.
3. **Repeatable Template:** A structural storytelling or performance vehicle.
4. **Craft-Centered:** Focuses on core musical talent (vocals, songwriting, beatmaking) rather than a visual gimmick.

*Examples of Valid Evergreen Formats:*
* **Acoustic Raw Vocal Take (T011, T052):** Unvarnished, single-take room-acoustic performance.
* **Unreleased Snippet / Lyric Teaser (T010, T049):** Panning studio B-roll or car singing with on-screen lyrics.
* **Open Verse / Duet Challenge (T045):** Leaving an 8-bar instrumental gap for collaborators.
* **DAW Sample Flip / Beat Switch (T012, T053):** Screen-recording production in FL Studio/Ableton.

*Manual Override:* If a manager types `Evergreen` into Column L (`Source`) or Column M (`Notes`), the lifecycle tracker honors it indefinitely.

---

### 3. Quantitative Trend Lifecycle & Velocity Tracking

Short-form trends move through predictable lifecycle stages. To prevent artists from jumping on a trend after its algorithmic reach has collapsed, **Stage E (`src/tracker.py`)** audits existing rows and updates Column H (`Status`) using quantitative data:

| Status | Label | Mathematical / Velocity Rule | A&R Action |
| :--- | :--- | :--- | :--- |
| **`💡 Evergreen`** | Evergreen | Structural format using own music, or manual override. Immune to decay. | **Permanent Asset:** Execute anytime for catalog or unreleased music. |
| **`🚀 Surging`** | Surging | $V \ge 40\text{k views/day}$ (YouTube Shorts) OR native sound $\le 7$ days old. | **High Priority:** Film and publish within 48–72 hours. |
| **`🔥 Peak`** | Peak | $V \ge 15\text{k views/day}$ (volume high, acceleration slowing) OR sound $8–14$ days old. | **Caution:** Execute only with an immediate, differentiated angle. |
| **`📉 Cooling`** | Cooling | View velocity dropping rapidly OR audio wave $15–27$ days old. Saturation reached. | **Skip:** Algorithmic reach is actively decaying. |
| **`💤 Stale`** | Stale | Daily velocity flatlined ($< 5\text{k/day}$) OR age $\ge 28$ days. Wave is dead. | **Do Not Execute:** Archive or ignore. |
| **`Idea`** | Creative Idea | YouTube music video or topical release. Non-audio reference point. | **Reference:** Adapt creative or narrative concepts for own rollouts. |

#### Real-Time YouTube View Delta Calculation
For YouTube links, the tracker stores `{views, timestamp}` in `.cache/metric_snapshots.json`:
$$\text{Daily View Velocity } (V) = \frac{\text{Current Views} - \text{Previous Snapshot Views}}{\text{Hours Elapsed}} \times 24$$
* The YouTube Data API v3 queries up to **50 videos in a single GET request**, consuming only **1 API quota unit**.
* On day 1 before a delta exists, the tracker uses cold-start velocity: $\text{Average Velocity} = \frac{\text{Total Views}}{\text{Age in Days}}$.

---

### 4. The 28-Day Topical Idea Expiration Rule

* **The Problem:** Music videos charting on YouTube (e.g. Eminem's *"MADARA"*, Ayra Starr's *"Heaven Baby"*) are **cultural reference points, not creator audio trends**. An artist cannot lip-sync to Eminem's official music video audio on their own TikTok channel.
* **The Rule:** Any trend whose example link is a YouTube URL (`youtube.com` or `youtu.be`) or whose Type is `Topic` is automatically classified as **`Idea`**.
* **The Expiration:** Topical ideas are tied to specific news cycles. If an artist has not acted on an idea within **28 days of its `Date spotted`**, its status automatically transitions from `Idea` $\rightarrow$ **`💤 Stale`**.

---

### 5. Zero-Leakage Privacy Architecture

To allow hosting on a **public GitHub repository** without exposing sensitive artist contracts, private SongStats IDs, unreleased single names, or private social media metrics:

```text
Public GitHub Repository (Open Source Code)
├── src/artist_profiler.py (Generic parser, ZERO artist data in code)
└── .gitignore (Strictly excludes data/, .cache/, and credentials)
         │
         │ Authenticates at runtime via GitHub Secrets (GCP_SA_CREDENTIALS)
         ▼
Private Google Cloud / Google Sheet (Secure Database)
└── Tab: 'Artist profiles' (Stores private artist dossiers, handles, and metrics)
```
* **No Artist Data in Git:** `data/artist_profiles.json` and `.cache/` are git-ignored.
* **Dynamic Loading:** The pipeline fetches artist profiles directly from the private `Artist profiles` tab in Google Sheets via `gspread`.
* **Zero-Code Maintenance:** To add an artist, managers simply add a row to the Google Sheet tab. Gemini picks up the new artist profile on the next run with no code changes or commits required.

---

## 🔄 Pipeline Lifecycle (Stages A–E)

### Stage A: Multi-Source Ingestion (`src/sources/`)
* **TikTok (`src/sources/tiktok.py`):** Ingests official **Billboard TikTok Top 50 Chart** hits ($0) alongside curated creator formats from `#openversechallenge` and `#songtransition` via Apify.
* **YouTube (`src/sources/youtube.py`):** Queries **YouTube Data API v3** for the top 50 trending music videos in Australia (Category 10), with fallback to Trends24 Australia.
* **Spotify (`src/sources/spotify.py`):** Scrapes the **Kworb Spotify Daily Australia** chart, capturing the Top 30 streaming tracks, streaming volumes, and valid `open.spotify.com` links ($0, no developer app restrictions).
* **Editorial & RSS (`src/sources/rss.py`):** Parses industry newsletters (*Trapital*, *Digital Native*, *NewEngen*) and scrapes trend blogs (**Later.com Instagram Reels Trends**, **SocialBee TikTok Trends**).

### Stage B: Structured AI Extraction (`src/classifier.py`)
* Compiles candidate pools into a **Single-Call Unified Prompt** partitioned by platform headers.
* Injects rich artist dossiers via `src/artist_profiler.py`.
* Invokes **Google Gemini Flash** with strict Pydantic JSON schemas (`UnifiedTrendResponse`).
* Enforces **unblocked thread timeouts (`concurrent.futures`)** and **progressive backoff (12s $\rightarrow$ 24s $\rightarrow$ 36s)** on HTTP 503 capacity errors.
* Automatically rotates to backup keys (`GEMINI_API_KEY_BACKUP`) upon encountering quota limits.

### Stage C: Personalization & Roster Matching (`src/matcher.py`)
* Prioritizes Gemini’s high-conviction `target_artists` and injects `artist_fit_reasoning` into Column M (`Notes`).
* Falls back to regex-normalized genre matching across primary and secondary artist genres.
* Generates sequential IDs (`T001`, `T019`, `T060`...) based on the sheet's active table boundary.
* Deduplicates against `Trend library` and `Send log` links to prevent repeated recommendations.

### Stage D: Atomic Batch Sync (`src/sheets.py`)
* Formats prepared trends into a 2D array matching the 15-column schema.
* Executes a single atomic batch append (`append_rows(..., table_range="A4:O4")`) to Google Sheets.

### Stage E: Post-Run Lifecycle Status Audit (`src/tracker.py`)
* Audits active rows in `Trend library`.
* Queries live YouTube view counts in **one batch API call** (1 quota point).
* Applies the 28-day expiration rule to topical ideas.
* Protects `💡 Evergreen` rows from decay.
* Updates Column H (`Status`) in **a single atomic range update** (`H5:H{end}`).
* Wipes trailing ghost cells beneath the table to eliminate visual clutter.

---

## 📂 Project Directory Structure

```text
TrendsDashboard/
├── .cache/                                 # Local disk cache (auto-generated, git-ignored)
│   ├── raw_ingested_cache.json            # Scraped raw candidates (preserves scraping quotas)
│   ├── classified_trends_checkpoint.json  # Checkpointed LLM outputs (preserves Gemini RPD)
│   └── metric_snapshots.json              # Historical view/stream counts for delta velocity tracking
├── data/                                   # Local data storage (git-ignored)
│   └── artist_profiles.json               # Offline fallback cache of Google Sheets artist dossiers
├── src/
│   ├── __init__.py
│   ├── config.py                          # Global taxonomy Literals, env loader, multi-key rotation
│   ├── models.py                          # Pydantic schemas (RawItem, ExtractedTrend, UnifiedTrendResponse)
│   ├── cache.py                           # Cache manager with TTL and file-corruption safety
│   ├── artist_profiler.py                 # Dynamic Google Sheets 'Artist profiles' loader & LLM formatter
│   ├── classifier.py                      # Gemini LLM engine with unified prompt, backoff, and key rotation
│   ├── matcher.py                         # Artist assignment, personalization notes, and deduplication
│   ├── tracker.py                         # Stage E: Quantitative lifecycle & velocity delta engine
│   ├── sheets.py                          # gspread client with atomic batch appending
│   ├── reclassify_existing.py             # One-off maintenance tool to audit, personalize, and clean rows
│   ├── pipeline.py                        # Main CLI orchestrator with granular execution flags
│   └── sources/                           # Modular plug-and-play scraping modules
│       ├── __init__.py
│       ├── base.py                        # Abstract BaseSource interface
│       ├── tiktok.py                      # Billboard TikTok Top 50 + high-view creator formats
│       ├── youtube.py                     # Official YouTube API v3 (50 items) + Trends24 fallback
│       ├── spotify.py                     # Kworb Spotify Daily Australia scraper (0-auth)
│       └── rss.py                         # Substack & editorial industry newsletter parser
├── .env.example                           # Template for required environment variables
├── requirements.txt                       # Locked production dependencies
├── service_account.json                   # Google Cloud Service Account key (git-ignored)
└── README.md
```

---

## 📊 Google Sheets Data Schemas

The pipeline coordinates across distinct tabs in your Google Sheet. **Table headers start on Row 4** (Rows 1–3 contain operational notes, color legends, and descriptions):

### Tab 1: `Trend library` (Atomic Output Tab)
*Columns A through O (15 Columns):*
1. **`ID`**: Sequential unique ID (`T001`, `T019`, `T060`...).
2. **`Trend name`**: Short title of the sound, challenge, or format.
3. **`Trend summary`**: Narrative paragraph detailing origin, execution style, and creator behavior.
4. **`Platform`**: `TikTok` | `Instagram` | `YouTube` | `YouTube Shorts` | `Multi-platform`.
5. **`Type`**: `Sound` | `Format` | `Challenge` | `Topic` | `Hashtag`.
6. **`Genres`**: Comma-separated list drawn strictly from canonical taxonomy.
7. **`Date spotted`**: Cataloging date (`DD Mon YYYY` format, e.g. `29 Oct 2026`).
8. **`Status`**: Dynamic lifecycle state: `🚀 Surging` | `🔥 Peak` | `📉 Cooling` | `💤 Stale` | `💡 Evergreen` | `Idea`.
9. **`Example link`**: Direct URL to example video, audio page, or source article.
10. **`How to execute it`**: 1-sentence tactical prompt telling the artist what to film.
11. **`Hashtags / keywords`**: Space-separated searchable tags.
12. **`Source`**: Ingestion provenance (`Automated Pipeline` or `Evergreen`).
13. **`Notes`**: A&R Strategic Fit reasoning and positioning guidance.
14. **`Matched Artists Count`**: Integer count of targeted artists.
15. **`Matched Artists Names`**: Semicolon-delimited list of artist names (e.g. `Nick Marcus; Allira`).

### Tab 2: `Artist profiles` (Private Persona Database)
*Columns A through I (9 Columns):*
1. **`Artist ID`**: SongStats ID or internal ID (e.g. `y4ku2hlc`).
2. **`Artist Name`**: Canonical name (e.g. `K.LAW`).
3. **`Genres`**: Comma-separated genre list (`Pop, R&B, House`).
4. **`Brand Identity & Aesthetic`**: Visual identity, fashion styling, and lifestyle themes.
5. **`Bio & Creative Direction`**: Cultural background, vocal style, and artistic direction.
6. **`Key / Recent Tracks`**: Active singles or unreleased project titles.
7. **`Musical Profile (Audio Traits)`**: Average BPM, key, energy, danceability, and production style.
8. **`Primary Channels & Handles`**: Active handles with follower scales.
9. **`Recent Social Content Themes`**: What they film on IG/TikTok (e.g. car vocals, DAW chops).

### Tab 3: `Artist roster` (Read-Only Matching Database)
* **Header Row:** Row 4.
* **Key Columns:** Column B (`Artist`) and Column C (`Genres`).

### Tab 4: `Send log` (Deduplication & History)
* **Header Row:** Row 4.
* Tracks artist recommendations that have already been dispatched, preventing duplicate recommendations.

> **Note on Connector Pages (`_...`):** Tabs starting with an underscore are used by Looker Studio for data joins. The pipeline never modifies these tabs.

---

## 🔑 Prerequisites & Free-Tier Setup

You can run this entire stack for **$0/month** using recurring free-tier allowances:

### 1. Google Cloud Service Account (Google Sheets API)
* Enable the **Google Sheets API** and **Google Drive API** in your Google Cloud Console.
* Create a **Service Account**, generate a JSON key file, and save it as `service_account.json` in your project root.
* Share your spreadsheet with the service account email as an **Editor**.
* *Corporate Workspace Note:* If your organization policy blocks service account key creation (`constraints/iam.disableServiceAccountKeyCreation`), create the service account in a personal `@gmail.com` GCP project and share the corporate sheet with that address.

### 2. Google Gemini API (AI Studio)
* Generate a free API key at [Google AI Studio](https://aistudio.google.com/).
* **Pro-Tip:** Generate a secondary key under a second Google Cloud project to set `GEMINI_API_KEY_BACKUP`. The pipeline automatically rotates keys if your primary hits a daily limit.

### 3. Apify Free Tier (TikTok Scraper)
* Create a free account at [Apify](https://apify.com/) to receive a recurring **$5.00/month credit**.
* Retrieve your API token from **Settings > Integrations > API Token**.
* Capped runs spend `< $0.01` per execution, staying well within the monthly credit.

### 4. YouTube Data API v3
* Enable the **YouTube Data API v3** in Google Cloud Console and generate an API key.
* **Important:** Set application restrictions to **None** (GitHub Actions uses dynamic cloud runner IPs) and restrict the API to **YouTube Data API v3** only.

---

## 🚀 Installation & Quickstart

### 1. Clone & Set Up Virtual Environment
```bash
git clone <your-repo-url>
cd TrendsDashboard
python3 -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Configure Environment Variables
Copy `.env.example` to `.env`:
```bash
cp .env.example .env
```
Fill in your credentials (see below).

### 3. Test Ingestion of Artist Profiles
Verify your Google Sheet connects and loads artist dossiers without calling Gemini:
```bash
python -m src.artist_profiler
```

### 4. Run a Non-Destructive Dry Run
Test the entire pipeline (ingestion, Gemini extraction, personalization, lifecycle audit) in simulation mode:
```bash
python -m src.pipeline --dry-run --no-timeout
```

---

## ⚙ Environment Configuration (`.env`)

```bash
# ==============================================================================
# Google Cloud Service Account & Google Sheets
# ==============================================================================
# Path to service account JSON (or raw JSON string for GitHub Actions)
GCP_SA_CREDENTIALS="service_account.json"

# Google Sheet Document ID (from URL: /d/<GOOGLE_SHEET_ID>/edit)
GOOGLE_SHEET_ID="your_google_sheet_id_here"

# ==============================================================================
# AI Extraction (Google Gemini 3.8 / Flash)
# ==============================================================================
# Primary API Key from https://aistudio.google.com/
GEMINI_API_KEY="AIzaSyPrimary..."

# Backup API Keys (Automatically invoked on 429 / daily quota exhaustion)
GEMINI_API_KEY_BACKUP="AIzaSyBackup1..."
GEMINI_API_KEY_BACKUP_2="AIzaSyBackup2..."

# Model alias (default: gemini-flash-latest)
GEMINI_MODEL="gemini-flash-latest"

# Execution timeout in seconds (default: 300.0 / 5 minutes)
GEMINI_TIMEOUT_SECONDS="300"

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

## 💻 CLI Usage & Operating Modes

The pipeline includes granular CLI flags to test individual components without burning quotas:

```bash
# 1. Standard Production Run (Full curation, matching, sync, and lifecycle audit)
python -m src.pipeline

# 2. Local Run with Infinite Timeout (Recommended for local testing)
python -m src.pipeline --refresh-cache --force --no-timeout

# 3. Dry-Run Mode (Simulates execution and prints table to console; skips Sheets)
python -m src.pipeline --dry-run --no-timeout

# 4. Lifecycle Audit Only (Audits and updates Column H statuses; skips scraping and Gemini)
python -m src.pipeline --track-lifecycle

# 5. Scrape-Only Mode (Pulls from scrapers and saves to .cache/; skips Gemini & Sheets)
python -m src.pipeline --refresh-cache --scrape-only

# 6. Classify-Only Mode (Reads from local .cache/; runs Gemini & Matching; 0 network scraping)
python -m src.pipeline --classify-only --dry-run --no-timeout

# 7. Isolate a Single Platform Scraper (Choices: tiktok, youtube, spotify, rss)
python -m src.pipeline --source tiktok --scrape-only
python -m src.pipeline --source spotify --scrape-only

# 8. Force Run (Bypasses the idempotency gate even if today was already curated)
python -m src.pipeline --force
```

---

## 🔧 Standalone Maintenance Tools

### 1. One-Off A&R Audit & Sheet Cleanup (`src/reclassify_existing.py`)
If your spreadsheet contains older automated trends that are generic, irrelevant, or over-classified as evergreen, use this tool to re-evaluate them against your artist profiles:
* **Dry-Run Preview:**
  ```bash
  python -m src.reclassify_existing --dry-run --no-timeout
  ```
* **Execute Live Cleanup:**
  ```bash
  python -m src.reclassify_existing --no-timeout
  ```
  *Leaves manual rows (`T001`–`T019`) untouched, deletes irrelevant automated memes, updates retained rows with tailored artist assignments, and synchronizes lifecycle statuses.*

### 2. Standalone Lifecycle Auditor (`src/tracker.py`)
To audit and update Column H statuses without running the scraper or invoking Gemini:
* **Simulation:** `python -m src.tracker` (Runs in dry-run mode by default).
* **Live Update:** `python -m src.pipeline --track-lifecycle`.

### 3. Artist Profile Verification (`src/artist_profiler.py`)
To inspect your artist database and verify what prompt context Gemini receives:
```bash
python -m src.artist_profiler
```

---

## ⏰ GitHub Actions Automation & Catch-Up Logic

The pipeline runs serverlessly on GitHub Actions under a **Self-Healing Catch-Up Schedule** with an **Idempotency Gate**:

### Schedule Configuration (Australian Time vs. UTC)
| Run Slot | UTC Schedule | **Sydney / Melbourne (AEDT)** | Execution Behavior |
| :--- | :--- | :--- | :--- |
| **Primary Run** | `0 21 * * *` (21:00 UTC) | **8:00 AM** | Full scrape, Gemini extraction, sheet append, and lifecycle audit. |
| **Catch-Up 1** | `0 1 * * *` (01:00 UTC) | **12:00 PM (Noon)** | If 8:00 AM succeeded, skips Gemini (0 quota used) and runs a 5s lifecycle audit. If 8:00 AM failed, runs full curation. |
| **Catch-Up 2** | `0 5 * * *` (05:00 UTC) | **4:00 PM** | Afternoon lifecycle audit to refresh statuses before close of business. |

### Why This Architecture Protects Your Quotas
1. **Idempotency Gate:** Checks if 3 or more trends were already logged today (`Date spotted == today`). If true, it skips scraping and Gemini completely, taking 5 seconds and consuming **0 Gemini quota**.
2. **Loud Failure (`sys.exit(1)`):** If all Gemini retries fail due to a 503 outage, the script exits with code `1`. GitHub Actions marks the run red and sends an email notification. The noon catch-up slot automatically recovers the day's curation once server load eases.
3. **Persistent Snapshot Cache:** Uses `actions/cache@v4` to store `.cache/metric_snapshots.json` across cloud runs, ensuring 24-hour YouTube view deltas calculate accurately despite ephemeral virtual machines.

---

## 🛠 Troubleshooting & FAQs

#### Q: How do I add a new artist to the roster?
* **Answer:** Open your private Google Sheet, switch to the **`Artist profiles`** tab, and add a row starting at the bottom of the table. Provide their name, genres, brand identity, key tracks, and content themes. Gemini will automatically incorporate their profile into all future runs.

#### Q: Why are all YouTube trends categorized as "Idea"?
* **Answer:** YouTube links represent full-length music videos or audio uploads (not replicable TikTok/Reels creator trends). To prevent artists from jumping on a song without an active challenge or sound vehicle, they are classified as **`Idea`** and expire after 28 days if not acted upon.

#### Q: Why does Gemini take 1 to 2 minutes to respond?
* **Answer:** Gemini generates **9 to 15 fully structured trend objects** across TikTok, YouTube, and Spotify. Each object contains 11 validated fields, totaling **2,500 to 3,500 tokens of strict JSON**. On Google's free tier, streaming 3,000 tokens takes 60–90 seconds. Always use `--no-timeout` for local runs.

#### Q: Google Cloud says: *"An organisation policy that blocks service accounts key creation has been enforced."*
* **Fix:** Your Google Workspace domain enforces `constraints/iam.disableServiceAccountKeyCreation`. Create a free GCP project using a personal `@gmail.com` account, generate your `service_account.json` there, and share your spreadsheet with that service account's email address.

#### Q: Getting `503 UNAVAILABLE` from Gemini API in GitHub Actions
* **Answer:** GitHub Actions runs in US datacenters (Azure US-Central/East) where Google's API gateways experience heavy free-tier traffic. The pipeline uses a **12s $\rightarrow$ 24s $\rightarrow$ 36s progressive backoff** combined with **automatic key rotation** to allow the serving cluster to autoscale and drain its buffer.

#### Q: How do I re-run a failed job from my phone?
* **Answer:** Open the **GitHub Mobile app** (iOS/Android), navigate to your repository's **Actions** tab, tap the red failed workflow run, and tap **Re-run failed jobs**. The pipeline will execute on a fresh runner without needing your computer.