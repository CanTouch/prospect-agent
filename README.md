# Prospect Intelligence Agent

A LangGraph-powered B2B prospecting agent. Give it your company's URL — it researches your market, maps your ideal customers, scans your real competitors, finds matching prospects, and hands you ready-to-send outreach with verified contact info. Fully hands-off.

**Live demo:** https://prospects.kuppelabs.com

## What it does

1. Reads your website and builds a company profile
2. Determines your ideal customer profile (industries, company size, buying signals)
3. Finds your real, named competitors via live web search
4. Analyzes what competitors offer and identifies your competitive edge
5. Discovers real, named prospect companies matching your ICP
6. Drafts personalized outreach for each prospect, using your competitive edge
7. Enriches each prospect with verified contact info (email + phone), scraped from their real website with an LLM-verification step to avoid directory/listicle false positives, with Hunter.io as fallback

## Stack

- Agent orchestration: LangGraph (stateful graph with conditional routing)
- LLM: Groq API (Qwen 27B)
- Web search: Tavily
- Contact enrichment: site scraping + Hunter.io
- UI: Streamlit, custom dark theme with animated staged reveal
- Deployment: Hetzner VPS + nginx + Let's Encrypt SSL

## Architecture

Company URL -> profile -> ICP -> competitor discovery -> competitive edge analysis -> prospect discovery -> personalized outreach -> contact enrichment

Each stage is a LangGraph node; the graph is compiled once and invoked per run. Contact enrichment includes a verification step that rejects directory/listicle URLs so outreach never gets sent to the wrong entity.

## Setup

- Clone the repo
- python3 -m venv venv && source venv/bin/activate
- pip install -r requirements.txt (or install langgraph groq tavily-python requests beautifulsoup4 python-dotenv streamlit)
- Add GROQ_API_KEY, TAVILY_API_KEY, HUNTER_API_KEY to .env
- streamlit run app.py
