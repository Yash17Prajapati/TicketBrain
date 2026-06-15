# TicketBrain

AI-powered ticket routing and resolution for [Frappe Helpdesk](https://github.com/frappe/helpdesk).

TicketBrain sits between the customer and your support team. When a ticket arrives it:

1. **Classifies** the ticket (category, priority, confidence score) using a trained ML classifier
2. **Retrieves** relevant KB articles and similar past tickets via RAG (cosine-similarity search)
3. **Generates** a resolution draft through your chosen LLM (Gemini, OpenAI, Anthropic, OpenRouter, or Ollama)
4. **Decides** automatically — high-confidence answers are sent directly; low-confidence tickets are escalated to the right team
5. **Learns** — agents can Accept or Correct AI assignments; corrections are embedded and retrieved for future tickets

---

## Architecture

```
New Ticket
    │
    ▼
ML Classifier  ──→  Category + Confidence
    │
    ▼
RAG Pipeline
  ├─ kb_index.npz       (KB articles + auto-learned resolutions)
  ├─ ticket_index.npz   (past resolved tickets)
  └─ feedback_index.npz (agent corrections)
    │
    ▼
LLM (Gemini / OpenAI / Anthropic / OpenRouter / Ollama)
    │
    ▼
Decision Engine
  ├─ Auto Send    (confidence ≥ threshold, quality checks pass)
  ├─ Pending Approval  (held for agent review)
  └─ Escalate     (low confidence → route to team)
    │
    ▼
Agent panel in Helpdesk portal
  └─ Accept / Correct → feedback indexed for future tickets
```

---

## Prerequisites

| Requirement | Version |
|-------------|---------|
| Python | 3.10+ |
| Node.js | 18+ |
| Frappe | v15 |
| ERPNext | v15 |
| Frappe Helpdesk | latest |
| Redis | any (standard; RediSearch **not** required) |
| MariaDB | 10.6+ |
| An LLM API key **or** Ollama running locally | — |

---

## Setting up Frappe + ERPNext + Helpdesk (fresh system)

Skip this section if you already have a working Frappe bench with ERPNext and Frappe Helpdesk installed.

### System dependencies (Ubuntu 22.04 / 24.04)

```bash
sudo apt update && sudo apt upgrade -y
sudo apt install -y git python3-dev python3-pip python3-venv \
    mariadb-server mariadb-client libmysqlclient-dev \
    redis-server nodejs npm wkhtmltopdf \
    libssl-dev libffi-dev build-essential
```

#### Secure MariaDB

```bash
sudo mysql_secure_installation
```

Then set MariaDB to use the correct character set. Open `/etc/mysql/mariadb.conf.d/50-server.cnf` and add under `[mysqld]`:

```ini
[mysqld]
character-set-client-handshake = FALSE
character-set-server = utf8mb4
collation-server = utf8mb4_unicode_ci

[mysql]
default-character-set = utf8mb4
```

Restart MariaDB:

```bash
sudo systemctl restart mariadb
```

#### Install Node.js 18 (if not already)

```bash
curl -fsSL https://deb.nodesource.com/setup_18.x | sudo -E bash -
sudo apt install -y nodejs
```

#### Install yarn

```bash
sudo npm install -g yarn
```

### Install bench CLI

```bash
sudo pip3 install frappe-bench
```

### Create a new bench

```bash
bench init --frappe-branch version-15 ticketbrain-bench
cd ticketbrain-bench
```

### Get ERPNext and Frappe Helpdesk

```bash
bench get-app --branch version-15 erpnext
bench get-app helpdesk
```

### Create a site

```bash
bench new-site your-site.local --install-app frappe
```

When prompted, set a MySQL root password and an Administrator password for the site.

### Install ERPNext and Helpdesk on the site

```bash
bench --site your-site.local install-app erpnext
bench --site your-site.local install-app helpdesk
```

### Set up a development server

```bash
bench --site your-site.local set-config developer_mode 1
bench use your-site.local
bench start
```

The site will be available at `http://your-site.local:8000`. Add it to `/etc/hosts` if needed:

```bash
echo "127.0.0.1 your-site.local" | sudo tee -a /etc/hosts
```

### (Production only) Set up supervisor + nginx

For a production deployment use the official Frappe easy-install script or configure supervisor and nginx manually. See [Frappe Bench production setup](https://frappeframework.com/docs/user/en/bench/guides/setup-production).

---

## Installation

### 1 — Get the app

```bash
cd /path/to/your/bench
bench get-app https://github.com/Yash17Prajapati/TicketBrain --branch develop
```

### 2 — Install on your site

```bash
bench --site your-site.local install-app ticketbrain
bench --site your-site.local migrate
```

### 3 — Download the embedding model

The 88 MB `all-MiniLM-L6-v2` sentence-transformer model is not stored in git. Download it once:

```bash
cd apps/ticketbrain
../../env/bin/python ticketbrain/ml/setup.py
```

This saves the model to `ticketbrain/ml/models/embedding_model/` and is used for all RAG similarity search. It never calls an external API — it runs entirely on your server.

### 4 — Build the initial Knowledge Base index

```bash
# From the bench root
./env/bin/python apps/ticketbrain/ticketbrain/ml/build_rag_index.py
```

This embeds the built-in KB articles into `kb_index.npz`. The index grows automatically as:
- Agents create HD Articles in Helpdesk
- AI successfully resolves tickets (auto-learned)
- Agents submit corrections

### 5 — Configure your LLM provider

TicketBrain supports five providers. Set **one** of the following in your bench config:

#### Option A — Gemini (recommended, free tier available)

```bash
bench --site your-site.local set-config TICKETBRAIN_LLM_PROVIDER gemini
bench --site your-site.local set-config GEMINI_API_KEY "your-key-here"
```

Get a free key at [aistudio.google.com](https://aistudio.google.com/).

#### Option B — OpenAI

```bash
bench --site your-site.local set-config TICKETBRAIN_LLM_PROVIDER openai
bench --site your-site.local set-config OPENAI_API_KEY "sk-..."
```

#### Option C — Anthropic

```bash
bench --site your-site.local set-config TICKETBRAIN_LLM_PROVIDER anthropic
bench --site your-site.local set-config ANTHROPIC_API_KEY "sk-ant-..."
```

#### Option D — OpenRouter (access 200+ models with one key)

```bash
bench --site your-site.local set-config TICKETBRAIN_LLM_PROVIDER openrouter
bench --site your-site.local set-config OPENROUTER_API_KEY "sk-or-..."
```

#### Option E — Ollama (100% local, no API key needed)

Install [Ollama](https://ollama.com/), pull a model, and start the server:

```bash
ollama pull llama3.2
ollama serve          # listens on http://localhost:11434 by default
```

Then configure TicketBrain:

```bash
bench --site your-site.local set-config TICKETBRAIN_LLM_PROVIDER ollama
# Optional — if Ollama runs on a different host:
bench --site your-site.local set-config OLLAMA_BASE_URL "http://localhost:11434"
# Optional — override the default model (llama3.2):
bench --site your-site.local set-config TICKETBRAIN_LLM_MODEL "llama3.1:8b"
```

#### Override the model for any provider

```bash
bench --site your-site.local set-config TICKETBRAIN_LLM_MODEL "gemini-1.5-pro"
```

Default models per provider:

| Provider | Default model |
|----------|--------------|
| gemini | `gemini-2.0-flash` |
| openai | `gpt-4o-mini` |
| anthropic | `claude-haiku-4-5-20251001` |
| openrouter | `google/gemini-2.0-flash` |
| ollama | `llama3.2` |

### 6 — Disable Helpdesk search indexing (plain Redis only)

If you are running **standard Redis** (not Redis with the RediSearch module), disable Helpdesk's search index to prevent errors:

```bash
bench --site your-site.local execute frappe.db.set_single_value \
  --args '["HD Settings", "search_build_index", 0]'
bench --site your-site.local migrate
```

If you are on Frappe Cloud or have Redis Stack / RediSearch installed, skip this step.

### 7 — Restart workers

```bash
bench restart
```

---

## Verify the installation

1. Open Frappe Desk → go to the **TicketBrain** workspace. You should see shortcuts for AI Interactions, Business Context, Support Tickets, and Knowledge Base.

2. Open **Helpdesk** at `/helpdesk`. Create a new ticket from the customer portal. Within a few seconds you should see the evaluating overlay (dimmed screen + spinner).

3. After processing, open the ticket as an assigned agent. The **TicketBrain AI Recommendation** panel should appear above the activity feed with Accept / Correct Assignment buttons.

4. Check **TB AI Interaction** in Frappe Desk for a record linked to the ticket.

---

## Python dependencies

TicketBrain's Python dependencies are installed automatically by `bench install-app`. The key packages are:

```
sentence-transformers   # embedding model (all-MiniLM-L6-v2)
scikit-learn            # ML classifier
numpy
requests                # Ollama HTTP client
google-genai            # Gemini provider
openai                  # OpenAI + OpenRouter provider
anthropic               # Anthropic provider
```

Install them manually if needed:

```bash
./env/bin/pip install sentence-transformers scikit-learn numpy requests \
    google-genai openai anthropic
```

---

## Retraining the classifier (optional)

A pre-trained classifier is included (`ticketbrain/ml/models/classifier.joblib`). It covers six categories:

- Hardware & Infrastructure
- Software & Applications
- Network & Connectivity
- Account & Access
- Security & Threats
- Data & Reports

To retrain on your own data, edit `ticketbrain/ml/data/training_data.csv` and run:

```bash
cd apps/ticketbrain
../../env/bin/python ticketbrain/ml/train.py
```

---

## Business Context

TicketBrain automatically scans your ERPNext/Frappe data (customers, products, modules) to build a business context that is injected into every LLM prompt. This makes AI responses specific to your company.

After installation, trigger the first scan from Frappe Desk:

**TicketBrain workspace → Business Context → Scan Now**

The scan runs automatically every 7 days after that.

---

## Agent workflow

### Helpdesk portal (at `/helpdesk`)

When a ticket is assigned to an agent, the **TicketBrain AI Recommendation** panel appears above the activity feed:

- **Accept Assignment** — confirms the AI's category, team, and priority assignment
- **Correct Assignment** — opens a dialog to change category, team (HD Team dropdown), and priority; the correction is embedded and used for similar future tickets

### Frappe Desk (at `/app`)

The same workflow is available via the **TicketBrain** button group on the HD Ticket form. Tickets in `Pending Approval` status also show **Review AI Draft** / **Write Custom Reply** actions.

---

## Troubleshooting

### Overlay or panel not showing in Helpdesk portal
- Run `bench --site your-site.local migrate` to ensure the HD Form Script is installed/updated
- Hard-refresh the browser (Ctrl+Shift+R) to clear cached scripts

### `FT.CREATE unknown command` error in logs
Your Redis instance does not have RediSearch. Follow Step 7 above to disable Helpdesk search indexing.

### `ModuleNotFoundError: sentence_transformers`
Run `./env/bin/pip install sentence-transformers` from the bench root.

### Evaluating overlay never disappears
The background worker may not be running. Check: `bench doctor` and ensure the `default` queue worker is active. Also verify the LLM provider key is set correctly.

### AI sends empty or template-only responses
The LLM provider is not configured or the API key is invalid. Check `bench --site your-site.local show-config` and look for `TICKETBRAIN_LLM_PROVIDER` and its key.

---

## Directory structure

```
ticketbrain/
├── ai/
│   ├── context_discovery.py   # Business context auto-scan
│   ├── evaluator.py           # Decision engine (Auto Send / Escalate / Approve)
│   ├── knowledge_extraction.py # Auto-index resolutions + rebuild ticket index
│   ├── llm_provider.py        # Multi-provider LLM abstraction
│   ├── prompt_builder.py      # Structured prompts with KB + feedback context
│   ├── rag.py                 # RAG orchestration
│   ├── retrieval.py           # NPZ index search (kb, ticket, feedback)
│   └── service.py             # Main AI pipeline entry point
├── api/
│   ├── correction.py          # Accept/Correct assignment endpoints
│   ├── knowledge.py           # KB management API
│   └── ticket.py              # Ticket processing + status API
├── events/
│   ├── hd_ticket.py           # on_ticket_created / on_ticket_updated
│   └── hd_ticket_comment.py   # Customer reply handling
├── ml/
│   ├── data/training_data.csv # Classifier training data
│   ├── models/
│   │   ├── classifier.joblib      # Pre-trained SVM classifier (included)
│   │   ├── label_encoder.joblib   # Category label encoder (included)
│   │   └── model_config.json      # Model metadata (included)
│   ├── build_rag_index.py     # Build kb_index.npz from knowledge_base.py
│   ├── setup.py               # Download embedding model (run once)
│   └── train.py               # Retrain classifier on custom data
├── public/js/
│   ├── helpdesk_portal_overlay.js  # Portal overlay + assignment panel
│   ├── hd_ticket.js               # Frappe Desk HD Ticket form actions
│   └── tb_business_context.js     # Business Context form actions
├── setup/
│   └── install.py             # after_install / after_migrate hooks
└── ticketbrain/doctype/
    ├── tb_ai_interaction/     # AI processing record per ticket
    ├── tb_assignment_correction/ # Agent correction records
    ├── tb_business_context/   # Company context document
    └── tb_document/           # Manual KB documents
```

---

## License

MIT
