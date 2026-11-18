# AGENTS.md — AI-Powered Affiliate Automation Bot & Learning Course

> Read by Antigravity, Cursor, and Claude Code at the start of every session.
> Architecture: Clean Architecture + DevOps Best Practices + Verified Commission Flow.

## 🎯 Mission
1. Build a production-grade automated affiliate publisher bot for Telegram (@YourDealsChannel).
2. Reach ₹2,000/month confirmed affiliate commission (via AJIO ACE & Cuelinks Amazon).
3. Provide hands-on learning for: **Python OOP, SQL Database Design, AI Engineering (Gemini), and DevOps (Docker, CI/CD, Task Automation)**.

## 🛡️ Hard Rules (Never Violate)
1. **Flipkart is BLOCKED**: Never promote or generate Flipkart links.
2. **HTTP 200 != Eligible**: Always verify `affiliated == True` or explicit partner approval before publishing.
3. **Never Fabricate Data**: Never hallucinate prices, discounts, ratings, or stocks. If missing, indicate "Check current price".
4. **AI Never Writes Raw Numbers**: Python handles all currency formatting, calculations, and disclosures. AI handles copy, classification, and summaries.
5. **Python Guardrails Over AI**: Content must pass deterministic regex/safety filters before posting.
6. **No Illegal Scraping**: Use official Partner APIs (AJIO Trackier v2, Cuelinks v3 REST API) or curated feeds.
7. **Secrets Security**: API keys live in `.env` only. Never hardcode or log credentials.
8. **Default to DRY_RUN=true**: Test locally without accidental live channel spam until explicitly confirmed.
9. **Affiliate Disclosure Mandate**: Every public post must include FTC/legal affiliate disclosure.

## 📐 Clean Architecture Directory Structure
```
affiliate-pro-course/
├── app/
│   ├── __init__.py
│   ├── config.py             # Pydantic / dataclass settings (.env)
│   ├── models.py             # Domain models (Product, Deal, Link, Post)
│   ├── db.py                 # SQLite engine (Products, Runs, Posts, Metrics)
│   ├── cuelinks_provider.py  # Cuelinks REST API v3 Client
│   ├── ajio_provider.py      # AJIO (Trackier v2) Partner Client
│   ├── content_checker.py    # Deterministic regex guardrails
│   ├── ai_service.py         # Google Gemini LLM Service (Structured Output)
│   ├── deal_generator.py     # AI copy + Template fallback
│   ├── image_creator.py      # PIL banner generator
│   ├── telegram_publisher.py # Telegram Bot API client
│   ├── pipeline.py           # Core orchestrator pipeline
│   └── main.py               # CLI: check-link, demo-ai, run-once, schedule
├── tests/
│   ├── test_cuelinks.py
│   ├── test_ajio.py
│   ├── test_guardrails.py
│   └── test_pipeline.py
├── data/
│   ├── sample_deals.csv
│   └── affiliate.db
├── docs/
│   ├── DEVOPS_ROADMAP.md
│   └── SQL_CHEATSHEET.md
├── Dockerfile
├── requirements.txt
├── .env.example
├── .gitignore
└── AGENTS.md
```

## 🚀 Learning Modules & Milestones
- **Module 1: Foundations & APIs** (HTTP status, JSON payloads, Auth tokens, AJIO & Cuelinks).
- **Module 2: Database & SQL Mastery** (Schema normalization, indexing, deduplication, analytics queries).
- **Module 3: AI Engineering with Gemini** (Pydantic structured output, zero-shot deal summaries, deterministic guardrails).
- **Module 4: Telegram Bot Integration** (HTML formatting, rate limiting, inline action buttons).
- **Module 5: DevOps & Containerization** (Docker container, multi-stage build, health checks, cron automation).
