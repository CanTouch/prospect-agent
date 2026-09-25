"""Step 3: use the ICP's search keywords to find real prospects via Tavily."""
import json, os, sys
from typing import TypedDict, Literal
from dotenv import load_dotenv
from groq import Groq
from tavily import TavilyClient
from langgraph.graph import StateGraph, START, END

from step1_profile import fetch_site, analyze_company, parse_json, MODEL
from step2_icp import classify_business_model, route_by_model, b2b_icp, b2c_icp

load_dotenv()
client = Groq(api_key=os.environ["GROQ_API_KEY"])
tavily = TavilyClient(api_key=os.environ["TAVILY_API_KEY"])


class AgentState(TypedDict):
    url: str
    page_text: str
    profile: dict
    business_model: str
    icp: dict
    raw_search_results: list
    prospects: list


def discover_prospects(state: AgentState) -> dict:
    keywords = state["icp"].get("search_keywords", [])[:4]  # limit to control cost/time
    all_results = []
    for kw in keywords:
        try:
            res = tavily.search(query=kw, max_results=5, search_depth="basic")
            for r in res.get("results", []):
                all_results.append({
                    "query": kw,
                    "title": r.get("title", ""),
                    "url": r.get("url", ""),
                    "snippet": r.get("content", "")[:300],
                })
        except Exception as e:
            print(f"  [search failed for '{kw}': {e}]")
    return {"raw_search_results": all_results}


EXTRACT_PROSPECTS_PROMPT = """From these raw web search results, extract a list of DISTINCT
real businesses or entities that could be genuine prospects. Skip directory/aggregator pages
(like Yelp category pages) unless a specific business is named. Skip duplicates.

Search results:
{results}

Return ONLY a JSON object: {{"prospects": [{{"name": "...", "url": "...", "why_found": "1 sentence, which search/context surfaced them"}}]}}
Limit to at most 10 prospects."""


def extract_prospects(state: AgentState) -> dict:
    if not state["raw_search_results"]:
        return {"prospects": []}
    resp = client.chat.completions.create(
        model=MODEL,
        messages=[{"role": "user", "content": EXTRACT_PROSPECTS_PROMPT.format(
            results=json.dumps(state["raw_search_results"], indent=2))}],
        temperature=0.1,
    )
    result = parse_json(resp.choices[0].message.content)
    return {"prospects": result.get("prospects", [])}


graph = StateGraph(AgentState)
graph.add_node("fetch_site", fetch_site)
graph.add_node("analyze_company", analyze_company)
graph.add_node("classify_business_model", classify_business_model)
graph.add_node("b2b_icp", b2b_icp)
graph.add_node("b2c_icp", b2c_icp)
graph.add_node("discover_prospects", discover_prospects)
graph.add_node("extract_prospects", extract_prospects)

graph.add_edge(START, "fetch_site")
graph.add_edge("fetch_site", "analyze_company")
graph.add_edge("analyze_company", "classify_business_model")
graph.add_conditional_edges("classify_business_model", route_by_model, {
    "b2b_icp": "b2b_icp",
    "b2c_icp": "b2c_icp",
})
graph.add_edge("b2b_icp", "discover_prospects")
graph.add_edge("b2c_icp", "discover_prospects")
graph.add_edge("discover_prospects", "extract_prospects")
graph.add_edge("extract_prospects", END)

app = graph.compile()

if __name__ == "__main__":
    url = sys.argv[1] if len(sys.argv) > 1 else "https://kuppelabs.com"
    result = app.invoke({"url": url})
    print(f"=== BUSINESS MODEL: {result['business_model']} ===")
    print(f"\n=== PROSPECTS FOUND: {len(result['prospects'])} ===")
    print(json.dumps(result["prospects"], indent=2))
