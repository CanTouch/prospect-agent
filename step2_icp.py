"""Step 2: classify B2B vs B2C, then branch to the right ICP logic."""
import json, os, sys
from typing import TypedDict, Literal
from dotenv import load_dotenv
from groq import Groq
from langgraph.graph import StateGraph, START, END

from step1_profile import fetch_site, analyze_company, parse_json, MODEL

load_dotenv()
client = Groq(api_key=os.environ["GROQ_API_KEY"])


class AgentState(TypedDict):
    url: str
    page_text: str
    profile: dict
    business_model: str
    icp: dict


CLASSIFY_PROMPT = """Based on this company profile, is their business model B2B (sells to other
businesses/companies) or B2C (sells to individual consumers)? Some companies do both --
pick whichever is PRIMARY.

Company profile:
{profile}

Return ONLY a JSON object: {{"business_model": "B2B" or "B2C", "reasoning": "one sentence why"}}"""


def classify_business_model(state: AgentState) -> dict:
    resp = client.chat.completions.create(
        model=MODEL,
        messages=[{"role": "user", "content": CLASSIFY_PROMPT.format(profile=json.dumps(state["profile"]))}],
        temperature=0.1,
    )
    result = parse_json(resp.choices[0].message.content)
    return {"business_model": result["business_model"]}


def route_by_model(state: AgentState) -> Literal["b2b_icp", "b2c_icp"]:
    return "b2b_icp" if state["business_model"] == "B2B" else "b2c_icp"


B2B_ICP_PROMPT = """This is a B2B company. Based on their profile, determine who their IDEAL
CUSTOMER COMPANIES are.

Company profile:
{profile}

Return ONLY a JSON object with keys:
icp_summary (1-2 sentences),
industries (list of 3-6 industries that would buy),
company_size (e.g. "small business 5-30 employees", "enterprise"),
buying_signals (list of 3-5 signals a company needs this),
search_keywords (list of 5-8 search terms to FIND these companies online)."""

B2C_ICP_PROMPT = """This is a B2C company selling to individual consumers. Based on their profile,
determine who their IDEAL CUSTOMERS are as people, and where/how to reach local prospects.

Company profile:
{profile}

Return ONLY a JSON object with keys:
icp_summary (1-2 sentences describing the ideal customer as a person),
demographics (age range, income level, homeowner/renter, etc.),
geography (local, regional, national -- and why),
buying_signals (list of 3-5 life events or signals that indicate someone needs this),
search_keywords (list of 5-8 search terms to find LOCAL directories, review sites, or
communities where these consumers can be reached, e.g. "Nextdoor [city] homeowners",
"Google Maps [service] near me reviews")."""


def b2b_icp(state: AgentState) -> dict:
    resp = client.chat.completions.create(
        model=MODEL,
        messages=[{"role": "user", "content": B2B_ICP_PROMPT.format(profile=json.dumps(state["profile"]))}],
        temperature=0.2,
    )
    return {"icp": parse_json(resp.choices[0].message.content)}


def b2c_icp(state: AgentState) -> dict:
    resp = client.chat.completions.create(
        model=MODEL,
        messages=[{"role": "user", "content": B2C_ICP_PROMPT.format(profile=json.dumps(state["profile"]))}],
        temperature=0.2,
    )
    return {"icp": parse_json(resp.choices[0].message.content)}


graph = StateGraph(AgentState)
graph.add_node("fetch_site", fetch_site)
graph.add_node("analyze_company", analyze_company)
graph.add_node("classify_business_model", classify_business_model)
graph.add_node("b2b_icp", b2b_icp)
graph.add_node("b2c_icp", b2c_icp)

graph.add_edge(START, "fetch_site")
graph.add_edge("fetch_site", "analyze_company")
graph.add_edge("analyze_company", "classify_business_model")
graph.add_conditional_edges("classify_business_model", route_by_model, {
    "b2b_icp": "b2b_icp",
    "b2c_icp": "b2c_icp",
})
graph.add_edge("b2b_icp", END)
graph.add_edge("b2c_icp", END)

app = graph.compile()

if __name__ == "__main__":
    url = sys.argv[1] if len(sys.argv) > 1 else "https://kuppelabs.com"
    result = app.invoke({"url": url})
    print("=== COMPANY PROFILE ===")
    print(json.dumps(result["profile"], indent=2))
    print(f"\n=== BUSINESS MODEL: {result['business_model']} ===")
    print("\n=== ICP ===")
    print(json.dumps(result["icp"], indent=2))
