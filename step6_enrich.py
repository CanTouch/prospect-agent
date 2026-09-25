"""Stage: enrich each prospect with contact info via site scrape + Hunter.io fallback.
Filters out directory/listicle URLs by pattern, then LLM-verifies the remaining candidate."""
import json, os, re, sys
import time
from typing import TypedDict
from urllib.parse import urlparse
import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from groq import Groq
from tavily import TavilyClient
from langgraph.graph import StateGraph, START, END

from step1_profile import fetch_site, analyze_company, parse_json, MODEL
from step4_merged import (determine_icp, find_competitors, extract_competitors,
                            analyze_competitor_offerings, discover_prospects, extract_prospects)
from step5_outreach import write_outreach

load_dotenv()
client = Groq(api_key=os.environ["GROQ_API_KEY"])
_orig_create = client.chat.completions.create
def _retrying_create(*args, **kwargs):
    delay = 15
    for attempt in range(5):
        try:
            return _orig_create(*args, **kwargs)
        except Exception as e:
            is_rate_limit = "rate_limit" in str(e).lower() or "RateLimitError" in type(e).__name__
            if not is_rate_limit or attempt == 4:
                raise
            time.sleep(delay)
            delay = min(delay * 1.5, 45)
client.chat.completions.create = _retrying_create
tavily = TavilyClient(api_key=os.environ["TAVILY_API_KEY"])
HUNTER_KEY = os.environ["HUNTER_API_KEY"]

EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}")
PHONE_RE = re.compile(r"(\+?1[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}")

KNOWN_DIRECTORIES = {
    "yelp.com", "mapquest.com", "angi.com", "homeadvisor.com", "yellowpages.com",
    "bbb.org", "facebook.com", "linkedin.com", "manta.com", "thumbtack.com",
    "nextdoor.com", "google.com", "maps.google.com", "inven.ai", "tracxn.com",
    "hvacinformed.com", "procore.com", "network.procore.com", "builtin.com",
    "signalfire.com", "saastr.com", "local105.org",
}

# path/url substrings that strongly indicate a listicle/directory page, regardless of domain
SUSPICIOUS_PATH_PATTERNS = [
    "directory", "company-lists", "top-", "-in-", "companies-in", "/companies/",
    "network.", "best-", "-alternatives", "vs-", "/blog/", "/news/",
]


class AgentState(TypedDict):
    url: str
    page_text: str
    profile: dict
    icp: dict
    competitor_search_results: list
    competitors: list
    competitor_offerings: dict
    prospect_search_results: list
    prospects: list
    outreach: list
    enriched: list


def get_domain(url: str) -> str:
    return urlparse(url).netloc.replace("www.", "")


def is_known_directory(url: str) -> bool:
    domain = get_domain(url)
    return any(domain == d or domain.endswith("." + d) for d in KNOWN_DIRECTORIES)


def is_suspicious_path(url: str) -> bool:
    return any(pat in url.lower() for pat in SUSPICIOUS_PATH_PATTERNS)


VERIFY_PROMPT = """Company name: "{company_name}"

Candidate websites found by search (already pre-filtered to remove obvious directories):
{candidates}

Is ANY of these candidates the company's OWN official homepage (their actual business
website, where a customer would go to book a service or contact them directly)?
Be strict: if a candidate is a listicle, review aggregator, trade association, news
article, or a DIFFERENT company entirely, do NOT select it.

Return ONLY JSON: {{"official_url": "the exact url" or null, "reasoning": "one sentence"}}"""


def resolve_real_website(company_name: str) -> str | None:
    try:
        res = tavily.search(query=f'"{company_name}" official website contact',
                             max_results=8, search_depth="basic")
        candidates = [
            {"url": r.get("url", ""), "title": r.get("title", "")}
            for r in res.get("results", [])
            if r.get("url") and not is_known_directory(r["url"]) and not is_suspicious_path(r["url"])
        ]
        if not candidates:
            return None

        resp = client.chat.completions.create(
            model=MODEL,
            messages=[{"role": "user", "content": VERIFY_PROMPT.format(
                company_name=company_name, candidates=json.dumps(candidates, indent=2))}],
            temperature=0.0,
        )
        result = parse_json(resp.choices[0].message.content)
        chosen = result.get("official_url")
        # final safety check: reject if the model picked something not in our filtered list
        if chosen and any(c["url"] == chosen for c in candidates):
            return chosen
        return None
    except Exception:
        return None


def scrape_email_from_site(url: str) -> str | None:
    try:
        resp = requests.get(url, timeout=10, headers={"User-Agent": "Mozilla/5.0"})
        soup = BeautifulSoup(resp.text, "html.parser")
        text = soup.get_text(" ")
        matches = EMAIL_RE.findall(text)
        for m in matches:
            if not any(x in m.lower() for x in ["example.com", "sentry", "wixpress"]):
                return m
    except Exception:
        return None
    return None


def scrape_phone_from_site(url: str) -> str | None:
    try:
        resp = requests.get(url, timeout=10, headers={"User-Agent": "Mozilla/5.0"})
        soup = BeautifulSoup(resp.text, "html.parser")
        text = soup.get_text(" ")
        matches = PHONE_RE.findall(text)
        if matches:
            full_matches = PHONE_RE.finditer(text)
            for m in full_matches:
                return m.group(0).strip()
    except Exception:
        return None
    return None


def hunter_domain_search(domain: str) -> dict | None:
    try:
        resp = requests.get(
            "https://api.hunter.io/v2/domain-search",
            params={"domain": domain, "api_key": HUNTER_KEY, "limit": 3},
            timeout=10,
        )
        data = resp.json()
        emails = data.get("data", {}).get("emails", [])
        if emails:
            best = emails[0]
            return {
                "email": best.get("value"),
                "first_name": best.get("first_name"),
                "last_name": best.get("last_name"),
                "position": best.get("position"),
                "confidence": best.get("confidence"),
            }
    except Exception:
        return None
    return None


def enrich_contacts(state: AgentState) -> dict:
    enriched = []
    for o in state["outreach"]:
        prospect_url = o.get("url", "")
        name = o.get("name", "")
        real_url = None

        if prospect_url.startswith("http") and not is_known_directory(prospect_url) and not is_suspicious_path(prospect_url):
            real_url = prospect_url
        else:
            real_url = resolve_real_website(name)

        domain = get_domain(real_url) if real_url else ""
        contact = {"email": None, "source": None, "confidence": None, "resolved_url": real_url}

        phone = scrape_phone_from_site(real_url) if real_url else None

        if real_url:
            scraped = scrape_email_from_site(real_url)
            if scraped:
                contact = {"email": scraped, "phone": phone, "source": "website scrape", "confidence": "medium", "resolved_url": real_url}

        if not contact["email"] and domain:
            hunter_result = hunter_domain_search(domain)
            if hunter_result and hunter_result.get("email"):
                contact = {
                    "email": hunter_result["email"],
                    "phone": phone,
                    "contact_name": f"{hunter_result.get('first_name','')} {hunter_result.get('last_name','')}".strip(),
                    "title": hunter_result.get("position"),
                    "source": "Hunter.io",
                    "confidence": hunter_result.get("confidence"),
                    "resolved_url": real_url,
                }

        if not contact["email"]:
            contact = {"email": None, "phone": phone, "source": "not found", "confidence": None, "resolved_url": real_url}

        enriched.append({**o, "contact": contact})
    return {"enriched": enriched}


graph = StateGraph(AgentState)
graph.add_node("fetch_site", fetch_site)
graph.add_node("analyze_company", analyze_company)
graph.add_node("determine_icp", determine_icp)
graph.add_node("find_competitors", find_competitors)
graph.add_node("extract_competitors", extract_competitors)
graph.add_node("analyze_competitor_offerings", analyze_competitor_offerings)
graph.add_node("discover_prospects", discover_prospects)
graph.add_node("extract_prospects", extract_prospects)
graph.add_node("write_outreach", write_outreach)
graph.add_node("enrich_contacts", enrich_contacts)

graph.add_edge(START, "fetch_site")
graph.add_edge("fetch_site", "analyze_company")
graph.add_edge("analyze_company", "determine_icp")
graph.add_edge("determine_icp", "find_competitors")
graph.add_edge("find_competitors", "extract_competitors")
graph.add_edge("extract_competitors", "analyze_competitor_offerings")
graph.add_edge("analyze_competitor_offerings", "discover_prospects")
graph.add_edge("discover_prospects", "extract_prospects")
graph.add_edge("extract_prospects", "write_outreach")
graph.add_edge("write_outreach", "enrich_contacts")
graph.add_edge("enrich_contacts", END)

app = graph.compile()

if __name__ == "__main__":
    url = sys.argv[1] if len(sys.argv) > 1 else "https://kuppelabs.com"
    result = app.invoke({"url": url})
    print(f"=== FINAL RESULTS ({len(result['enriched'])}) ===\n")
    for e in result["enriched"]:
        print(f"--- {e['name']} ---")
        print(f"Email: {e['contact'].get('email') or 'NOT FOUND'} | Phone: {e['contact'].get('phone') or 'NOT FOUND'} (source: {e['contact'].get('source')})")
        print(f"Resolved URL: {e['contact'].get('resolved_url', 'n/a')}\n")
