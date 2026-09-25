"""Stage 7: personalized outreach per prospect, using the competitive angle."""
import json, os, sys
import time
from typing import TypedDict
from dotenv import load_dotenv
from groq import Groq
from tavily import TavilyClient
from langgraph.graph import StateGraph, START, END

from step1_profile import fetch_site, analyze_company, parse_json, MODEL
from step4_merged import (determine_icp, find_competitors, extract_competitors,
                            analyze_competitor_offerings, discover_prospects, extract_prospects)

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


OUTREACH_PROMPT = """You are writing a short, sharp cold outreach message from
"{company_name}" to a specific prospect.

About {company_name}:
{profile}

Why {company_name} beats competitors (use this as ammunition, don't state it generically):
{advantages}

Common gaps in what competitors offer:
{gaps}

The prospect being contacted:
{prospect}

Write a JSON object with:
subject (short, specific, not salesy),
message (3-4 sentences max. Reference something specific to the prospect if possible from
their name/context. Focus on ONE clear benefit tied to {company_name}'s real advantage.
No generic fluff like "I hope this finds you well". End with a soft, low-pressure call to action.)

Return ONLY the JSON object."""


def write_outreach(state: AgentState) -> dict:
    top_prospects = state["prospects"][:5]  # limit for cost
    offerings = state["competitor_offerings"]
    outreach_list = []
    for prospect in top_prospects:
        resp = client.chat.completions.create(
            model=MODEL,
            messages=[{"role": "user", "content": OUTREACH_PROMPT.format(
                company_name=state["profile"].get("company_name", ""),
                profile=json.dumps(state["profile"]),
                advantages=json.dumps(offerings.get("this_company_advantages", [])),
                gaps=json.dumps(offerings.get("gaps", [])),
                prospect=json.dumps(prospect),
            )}],
            temperature=0.4,
        )
        try:
            draft = parse_json(resp.choices[0].message.content)
        except Exception:
            draft = {"subject": "", "message": "[generation failed]"}
        outreach_list.append({**prospect, **draft})
    return {"outreach": outreach_list}


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

graph.add_edge(START, "fetch_site")
graph.add_edge("fetch_site", "analyze_company")
graph.add_edge("analyze_company", "determine_icp")
graph.add_edge("determine_icp", "find_competitors")
graph.add_edge("find_competitors", "extract_competitors")
graph.add_edge("extract_competitors", "analyze_competitor_offerings")
graph.add_edge("analyze_competitor_offerings", "discover_prospects")
graph.add_edge("discover_prospects", "extract_prospects")
graph.add_edge("extract_prospects", "write_outreach")
graph.add_edge("write_outreach", END)

app = graph.compile()

if __name__ == "__main__":
    url = sys.argv[1] if len(sys.argv) > 1 else "https://kuppelabs.com"
    result = app.invoke({"url": url})
    print(f"=== OUTREACH DRAFTS ({len(result['outreach'])}) ===\n")
    for o in result["outreach"]:
        print(f"--- {o['name']} ---")
        print(f"Subject: {o.get('subject','')}")
        print(f"Message: {o.get('message','')}\n")
