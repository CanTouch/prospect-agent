"""Stages 1-6: profile -> ICP -> competitors -> competitor offerings -> prospects."""
import json, os, sys
import time
from typing import TypedDict
from dotenv import load_dotenv
from groq import Groq
from tavily import TavilyClient
from langgraph.graph import StateGraph, START, END

from step1_profile import fetch_site, analyze_company, parse_json, MODEL

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


# ---------- Stage 3: ICP ----------
ICP_PROMPT = """This is a B2B company. Based on their profile, determine who their IDEAL
CUSTOMER COMPANIES are.

Company profile:
{profile}

Return ONLY a JSON object with keys:
icp_summary (1-2 sentences),
industries (list of 3-6 industries that would buy),
company_size (e.g. "small business 5-30 employees", "enterprise"),
buying_signals (list of 3-5 signals a company needs this),
search_keywords (list of 5-8 search terms to FIND real named companies online --
prefer terms like "[industry] companies in [region]" over generic terms)."""


def determine_icp(state: AgentState) -> dict:
    resp = client.chat.completions.create(
        model=MODEL,
        messages=[{"role": "user", "content": ICP_PROMPT.format(profile=json.dumps(state["profile"]))}],
        temperature=0.2,
    )
    return {"icp": parse_json(resp.choices[0].message.content)}


# ---------- Stage 4: find competitors ----------
def find_competitors(state: AgentState) -> dict:
    profile = state["profile"]
    location = profile.get("location", "")
    services = ", ".join(profile.get("services", [])[:3])
    queries = [
        f"{services} companies near {location}" if location != "unknown" else f"{services} companies",
        f"best {profile.get('company_name','')} alternatives",
        f"top {services} providers",
    ]
    all_results = []
    for q in queries:
        try:
            res = tavily.search(query=q, max_results=5, search_depth="basic")
            for r in res.get("results", []):
                all_results.append({"query": q, "title": r.get("title", ""),
                                     "url": r.get("url", ""), "snippet": r.get("content", "")[:400]})
        except Exception as e:
            print(f"  [search failed for '{q}': {e}]")
    return {"competitor_search_results": all_results}


EXTRACT_COMPETITORS_PROMPT = """From these search results, extract DISTINCT real, named
competitor BUSINESSES to "{company_name}" -- companies offering similar services.
Skip directories, review aggregators, and "{company_name}" itself.

Search results:
{results}

Return ONLY JSON: {{"competitors": [{{"name": "...", "url": "...", "what_they_offer": "1 sentence"}}]}}
Limit to at most 6 competitors."""


def extract_competitors(state: AgentState) -> dict:
    if not state["competitor_search_results"]:
        return {"competitors": []}
    resp = client.chat.completions.create(
        model=MODEL,
        messages=[{"role": "user", "content": EXTRACT_COMPETITORS_PROMPT.format(
            company_name=state["profile"].get("company_name", ""),
            results=json.dumps(state["competitor_search_results"], indent=2))}],
        temperature=0.1,
    )
    result = parse_json(resp.choices[0].message.content)
    return {"competitors": result.get("competitors", [])}


# ---------- Stage 5: competitor offerings deep-dive ----------
OFFERINGS_PROMPT = """Here is a company and the competitors found for it:

Company: {profile}
Competitors: {competitors}

Based on the "what_they_offer" snippets, summarize:
1. common_offerings: what most competitors offer (list)
2. pricing_signals: any pricing/positioning patterns noticed (list, or ["unknown"] if none visible)
3. gaps: things competitors seem to lack or complaints implied (list)
4. this_company_advantages: what this company offers that competitors don't seem to (list)

Return ONLY JSON with those 4 keys."""


def analyze_competitor_offerings(state: AgentState) -> dict:
    if not state["competitors"]:
        return {"competitor_offerings": {"common_offerings": [], "pricing_signals": [], "gaps": [], "this_company_advantages": []}}
    resp = client.chat.completions.create(
        model=MODEL,
        messages=[{"role": "user", "content": OFFERINGS_PROMPT.format(
            profile=json.dumps(state["profile"]), competitors=json.dumps(state["competitors"]))}],
        temperature=0.2,
    )
    return {"competitor_offerings": parse_json(resp.choices[0].message.content)}


# ---------- Stage 6: find prospects ----------
def discover_prospects(state: AgentState) -> dict:
    keywords = state["icp"].get("search_keywords", [])[:4]
    all_results = []
    for kw in keywords:
        try:
            res = tavily.search(query=kw, max_results=5, search_depth="basic")
            for r in res.get("results", []):
                all_results.append({"query": kw, "title": r.get("title", ""),
                                     "url": r.get("url", ""), "snippet": r.get("content", "")[:300]})
        except Exception as e:
            print(f"  [search failed for '{kw}': {e}]")
    return {"prospect_search_results": all_results}


EXTRACT_PROSPECTS_PROMPT = """From these raw web search results, extract a list of DISTINCT
real, named BUSINESSES that could be genuine B2B prospects (not directories, not review
aggregator pages). Skip duplicates.

Search results:
{results}

Return ONLY JSON: {{"prospects": [{{"name": "...", "url": "...", "why_found": "1 sentence"}}]}}
Limit to at most 10 prospects."""


def extract_prospects(state: AgentState) -> dict:
    if not state["prospect_search_results"]:
        return {"prospects": []}
    resp = client.chat.completions.create(
        model=MODEL,
        messages=[{"role": "user", "content": EXTRACT_PROSPECTS_PROMPT.format(
            results=json.dumps(state["prospect_search_results"], indent=2))}],
        temperature=0.1,
    )
    result = parse_json(resp.choices[0].message.content)
    return {"prospects": result.get("prospects", [])}


graph = StateGraph(AgentState)
graph.add_node("fetch_site", fetch_site)
graph.add_node("analyze_company", analyze_company)
graph.add_node("determine_icp", determine_icp)
graph.add_node("find_competitors", find_competitors)
graph.add_node("extract_competitors", extract_competitors)
graph.add_node("analyze_competitor_offerings", analyze_competitor_offerings)
graph.add_node("discover_prospects", discover_prospects)
graph.add_node("extract_prospects", extract_prospects)

graph.add_edge(START, "fetch_site")
graph.add_edge("fetch_site", "analyze_company")
graph.add_edge("analyze_company", "determine_icp")
graph.add_edge("determine_icp", "find_competitors")
graph.add_edge("find_competitors", "extract_competitors")
graph.add_edge("extract_competitors", "analyze_competitor_offerings")
graph.add_edge("analyze_competitor_offerings", "discover_prospects")
graph.add_edge("discover_prospects", "extract_prospects")
graph.add_edge("extract_prospects", END)

app = graph.compile()

if __name__ == "__main__":
    url = sys.argv[1] if len(sys.argv) > 1 else "https://kuppelabs.com"
    result = app.invoke({"url": url})
    print("=== PROFILE ===")
    print(json.dumps(result["profile"], indent=2))
    print("\n=== ICP ===")
    print(json.dumps(result["icp"], indent=2))
    print(f"\n=== COMPETITORS ({len(result['competitors'])}) ===")
    print(json.dumps(result["competitors"], indent=2))
    print("\n=== COMPETITOR OFFERINGS ===")
    print(json.dumps(result["competitor_offerings"], indent=2))
    print(f"\n=== PROSPECTS ({len(result['prospects'])}) ===")
    print(json.dumps(result["prospects"], indent=2))
