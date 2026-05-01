# AI Maturity Assessor

A stateful CLI agent that conducts structured stakeholder interviews based on the
**Gartner AI Maturity Model**, scores responses across 6 dimensions, and produces
a Markdown narrative report.

---

## How it works

1. The agent interviews you across **6 dimensions**: Strategy & Vision, Data & Infrastructure,
   Talent & Culture, Governance & Risk, Use Case Portfolio, and Technology & Tooling.
2. Each dimension is scored 1–5 against the Gartner maturity levels (Aware → Transformational).
3. After all 6 dimensions, the LLM generates a narrative report with an executive summary,
   dimension assessments, prioritised recommendations, and 30/60/90-day next steps.
4. Reports are saved to `assessments/<org>_<session_id>.md` with a companion JSON file.

---

## Prerequisites

- Python 3.11+
- zsh (for `setup.sh`)
- An API key for your chosen LLM provider (not required for Ollama)

---

## Setup

```bash
chmod +x setup.sh
source setup.sh
```

`source` (rather than `./`) is required so that `PYTHONPATH` is exported into your
current shell session. The script will:

- Prompt for your `ANTHROPIC_API_KEY` and write it to `.env` if one doesn't exist
- Set `PYTHONPATH` to the project root
- Install dependencies from `requirements.txt`
- Print a confirmation summary

For subsequent sessions, re-run `source setup.sh` to restore `PYTHONPATH`, or add
`export PYTHONPATH=/path/to/ai-maturity-assessor` to your shell profile.

---

## LLM providers

The tool uses a provider-agnostic `LLMClient` interface. Switch providers by setting
environment variables in `.env` — no code changes required.

### Supported providers

| Provider | `LLM_PROVIDER` | Default model | Requires API key |
|---|---|---|---|
| Anthropic (default) | `anthropic` | `claude-opus-4-7` | Yes — `ANTHROPIC_API_KEY` |
| OpenAI | `openai` | `gpt-4o` | Yes — `LLM_API_KEY` |
| Ollama (local) | `ollama` | `llama3.2` | No |
| Azure OpenAI | `azure` | deployment name | Yes — `LLM_API_KEY` |

### Configuration

Add these to your `.env` file (all are optional; defaults shown):

```env
LLM_PROVIDER=anthropic          # anthropic | openai | ollama | azure
LLM_MODEL=claude-opus-4-7       # override the provider's default model
LLM_BASE_URL=                   # custom endpoint; required for ollama
LLM_API_KEY=                    # API key for openai or azure; leave blank for ollama
ANTHROPIC_API_KEY=your_key_here # used when LLM_PROVIDER=anthropic

# Azure OpenAI (only required when LLM_PROVIDER=azure)
AZURE_OPENAI_ENDPOINT=https://<resource>.openai.azure.com/
```

### Using Ollama (local LLM, no API key needed)

1. Install Ollama from [ollama.com](https://ollama.com) and pull a model:

```bash
ollama pull llama3.2
```

2. Update your `.env`:

```env
LLM_PROVIDER=ollama
LLM_MODEL=llama3.2
LLM_BASE_URL=http://localhost:11434/v1
```

3. Run as normal — no API key required:

```bash
python3 src/cli.py
```

**Note on local model quality:** Interview probing and scoring work well on most
models 8B+. Report narrative generation (the `complete_structured` call) relies on
the model following a JSON schema precisely — larger models (30B+) are recommended
for consistent report output. Smaller models may produce malformed JSON and trigger
the fallback prompt-injection path, which is less reliable.

### Using OpenAI

```env
LLM_PROVIDER=openai
LLM_MODEL=gpt-4o
LLM_API_KEY=sk-...
```

### Using Azure OpenAI

1. Deploy a model in your Azure OpenAI resource (e.g. a `gpt-4o` deployment named `my-gpt4o`).

2. Update your `.env`:

```env
LLM_PROVIDER=azure
LLM_MODEL=my-gpt4o                                   # your deployment name
LLM_API_KEY=<your-azure-api-key>
AZURE_OPENAI_ENDPOINT=https://<resource>.openai.azure.com/
```

3. Run as normal:

```bash
python3 src/cli.py
```

**Note:** `LLM_MODEL` must match the **deployment name** in Azure, not the underlying model name (e.g. `my-gpt4o`, not `gpt-4o`).

---

## Usage

### Full interview

```bash
python3 src/cli.py
```

You will be prompted for your organisation's name, industry, and your name and role.
The interview takes approximately 25–30 minutes. Candid answers produce the most
accurate assessment.

Press `Ctrl-C` at any time to interrupt — you will be offered the option to save
the partial session to `assessments/partial_<session_id>.json`.

### Dry run (demo mode — no API calls)

```bash
python3 src/cli.py --dry-run
```

Runs a scripted 2-dimension mock interview using pre-built responses for a fictional
company. No API calls are made. Use this to preview the interview flow or demo the
tool without consuming API credits.

---

## Example output

### Dry-run interview flow

```
╭──────────────────────────── Welcome — DEMO MODE ─────────────────────────────╮
│                                                                              │
│                      AI Maturity Assessment  (dry run)                       │
│                                                                              │
│        This demo simulates 2 of 6 dimensions with scripted responses.        │
│         No API calls are made. Use it to preview the interview flow.         │
│                                                                              │
╰──────────────────────────────────────────────────────────────────────────────╯

─────────────────── Interview  (dry run — 2 of 6 dimensions) ───────────────────

╭───────────────────────────────── Consultant ─────────────────────────────────╮
│  Let's start with strategy. Can you describe how your organisation           │
│  currently thinks about AI — is there a defined direction or roadmap,        │
│  and who owns it?                                                            │
╰──────────────────────────────────────────────────────────────────────────────╯

  You (demo)  Our CTO chairs an informal AI task force. It meets monthly but
              there's no formal mandate or charter yet.

╭───────────────────────────────── Consultant ─────────────────────────────────╮
│  Is there a dedicated AI budget line, or is investment embedded in other     │
│  programmes?                                                                 │
╰──────────────────────────────────────────────────────────────────────────────╯

  You (demo)  No dedicated line — we draw from the IT transformation budget.
              Maybe £200k this year in total.
```

### Score summary table (printed after report generation)

```
────────────────────────────── Assessment Summary ──────────────────────────────

                        Acme Corp
┏━━━━━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━━━┓
┃ Dimension                ┃ Score ┃ Maturity Level          ┃
┡━━━━━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━━━━┩
│ Strategy & Vision        │ 2/5   │ Active                  │
├──────────────────────────┼───────┼─────────────────────────┤
│ Data & Infrastructure    │ 3/5   │ Operational             │
├──────────────────────────┼───────┼─────────────────────────┤
│ Talent & Culture         │ 2/5   │ Active                  │
├──────────────────────────┼───────┼─────────────────────────┤
│ Governance & Risk        │ 1/5   │ Aware                   │
├──────────────────────────┼───────┼─────────────────────────┤
│ Use Case Portfolio       │ 3/5   │ Operational             │
├──────────────────────────┼───────┼─────────────────────────┤
│ Technology & Tooling     │ 2/5   │ Active                  │
├──────────────────────────┼───────┼─────────────────────────┤
│ Overall                  │ 2.2/5 │ Level 2 — Active        │
└──────────────────────────┴───────┴─────────────────────────┘
```

---

## Project structure

```
.
├── src/
│   ├── llm/
│   │   ├── base.py                 # LLMClient ABC — complete() + complete_structured()
│   │   ├── anthropic_client.py     # Anthropic SDK (prompt caching, messages.parse)
│   │   ├── openai_compatible_client.py  # OpenAI SDK — covers OpenAI, Ollama, LM Studio, Azure
│   │   └── factory.py              # create_llm_client() — reads LLM_PROVIDER from env
│   ├── agent/
│   │   ├── interviewer.py          # Conversational interview loop
│   │   ├── prompts.py              # System prompts, opening questions, probe banks
│   │   └── scorer.py               # JSON score parsing, validation, dim.close()
│   ├── models/
│   │   └── assessment.py           # Pydantic state models (single source of truth)
│   ├── output/
│   │   └── report_generator.py     # LLM-generated narrative + session-state assembly
│   └── cli.py                      # Entry point, --dry-run, rich formatting
├── tests/
│   └── test_scorer.py
├── assessments/                    # Generated reports (git-ignored)
├── .env                            # Your config and API keys (git-ignored)
├── .env.example                    # Template with all supported variables
├── requirements.txt
└── setup.sh
```

---

## Maturity levels

| Level | Label | Characteristics |
|---|---|---|
| 1 | **Aware** | Ad hoc AI curiosity, no strategy, isolated experiments |
| 2 | **Active** | Pilots underway, exec interest but no governance, siloed |
| 3 | **Operational** | Repeatable processes, MLOps emerging, some ROI evidence |
| 4 | **Systematic** | Enterprise-wide AI strategy, governance in place, scaled use cases |
| 5 | **Transformational** | AI embedded in business model, continuous learning culture |
