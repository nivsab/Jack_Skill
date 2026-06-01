# Jack 🔧 — Your Personal Car Assistant

> A Claude Code skill. Install it once, invoke it by typing **"jack"** in any Claude Code session.

Jack is an AI-powered car assistant built as a Claude Code skill. It diagnoses warning lights, retrieves real-time parts prices, and guides you through DIY repairs step-by-step — pulling specs directly from your car's official manufacturer manual.

When a repair is beyond DIY, Jack generates a **Mechanic Script**: a ready-to-use script for your visit to the garage so you don't get overcharged.

### What makes Jack different

Most car AI tools either hallucinate specs or push everything toward "go to a mechanic." Jack does neither. It gives you verified torque values and oil grades from the manufacturer's own PDF, tells you honestly when something is safe to DIY and when it isn't, and — when the answer is "go to a mechanic" — arms you with exactly what to say so you don't get ripped off.

---

## Features

- **Vehicle identification** — looks up any Israeli-registered vehicle by plate number (free government API, no key required)
- **Diagnostics** — warning lights, noises, and symptoms with actionable next steps
- **DIY guidance** — step-by-step instructions with tools, torque specs, and a YouTube tutorial
- **Parts pricing** — real-time comparison between Israeli retailers and AliExpress
- **RAG from manufacturer manuals** — semantic search over your car's PDF manual via Ollama + Supabase
- **Mechanic Script** — a scripted briefing to bring to the garage
- **Safety guardrails** — blocks dangerous instructions and prompt injection attempts
- **Full resilience** — every tool has a graceful fallback; the conversation never stops

---

## Installation

```bash
git clone https://github.com/<your-username>/jack
cd jack
pip install -r requirements.txt
cp .env.example .env
```

---

## API Keys

Open `.env` and fill in the following:

### Required

| Variable | Description | Where to get it |
|----------|-------------|-----------------|
| `JACK_LLM_PROVIDER` | AI provider: `openai` / `anthropic` / `gemini` | — |
| `OPENAI_API_KEY` | If using OpenAI | platform.openai.com/api-keys |
| `ANTHROPIC_API_KEY` | If using Anthropic | console.anthropic.com/keys |
| `GOOGLE_API_KEY` | If using Gemini | aistudio.google.com/apikey |
| `SUPABASE_URL` | Your Supabase project URL | supabase.com → Settings → API |
| `SUPABASE_KEY` | Supabase anon key | supabase.com → Settings → API |
| `GROQ_API_KEY` | Used to auto-seed vehicle specs | console.groq.com/keys |

Only fill in the key for the LLM provider you chose — the rest can stay empty.

### Optional

| Variable | Description |
|----------|-------------|
| `YOUTUBE_API_KEY` | Enables official YouTube Data API v3 results. Without it, DuckDuckGo is used automatically as a fallback. Get it at console.cloud.google.com → YouTube Data API v3 |

> **Vehicle lookup by plate number** uses the Israeli government's open data API — no key or setup required.

---

## Supabase Setup

### 1. Create a new project at [supabase.com](https://supabase.com)

### 2. Run the schema

Open **SQL Editor → New Query**, paste the contents of `migrations/000_full_schema.sql`, and click **Run**.

This creates three tables:

| Table | Purpose |
|-------|---------|
| `vehicle_specs` | Technical specs (torque values, oil types, spark plugs...) |
| `doc_chunks` | Chunked manufacturer manual pages + pgvector embeddings |
| `vehicle_manuals` | Maps vehicle make/model/year to a PDF filename |

### 3. Seed vehicle specs

```bash
python seed.py
```

Populates `vehicle_specs` with baseline specs using Groq. This runs once — specs are cached permanently.

---

## Adding Your Car's Manual (RAG)

This enables Jack to answer questions directly from your manufacturer's PDF manual.

### 1. Download the PDF

Search for: `[make] [model] [year] owner's manual PDF`  
Most manufacturers publish these on their official websites.

### 2. Place it in the manuals folder

```
data/manuals/<filename>.pdf
```

### 3. Install and start Ollama

Jack uses `nomic-embed-text` for local embeddings:

```bash
ollama pull nomic-embed-text
```

Make sure Ollama is running before the next step.

### 4. Run the ingest script

```bash
python rag/ingest.py data/manuals/<filename>.pdf
```

This splits the PDF into chunks, generates embeddings locally via Ollama, and stores them in Supabase with pgvector indexing.

### 5. Register the manual

In Supabase **SQL Editor**, run:

```sql
INSERT INTO vehicle_manuals (make, model, start_year, end_year, engine, pdf_filename)
VALUES ('Toyota', 'Corolla', 2019, 2023, '1.8', 'corolla-2019-manual.pdf');
```

Jack will now retrieve relevant chunks from that manual when answering questions about matching vehicles.

> Two manuals are included out of the box: **Toyota Yaris Hybrid (2019–2020)** and **Kia Rio (2017)**. Run `migrations/001_vehicle_manuals.sql` to register them.

---

## Running Jack

```bash
python main.py
```

---

## Stack

| Tool | Role |
|------|------|
| Claude / GPT-4o / Gemini | Conversation engine |
| Supabase + pgvector | Spec cache + semantic search |
| Ollama (`nomic-embed-text`) | Local embeddings for RAG |
| DuckDuckGo | Parts prices + YouTube video search |
| data.gov.il API | Vehicle lookup by Israeli plate number |
| Groq | Fast spec seeding |
