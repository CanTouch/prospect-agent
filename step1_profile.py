"""Step 1: URL -> company profile. Two-node LangGraph."""
import json, os, re, sys
import time
from typing import TypedDict
import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from groq import Groq
from langgraph.graph import StateGraph, START, END

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
MODEL = "qwen/qwen3.8-27b"


class AgentState(TypedDict):
    url: str
    page_text: str
    profile: dict


def fetch_site(state: AgentState) -> dict:
    resp = requests.get(state["url"], timeout=15,
                        headers={"User-Agent": "Mozilla/5.0"})
    soup = BeautifulSoup(resp.text, "html.parser")
    for tag in soup(["script", "style", "nav", "footer"]):
        tag.decompose()
    text = " ".join(soup.get_text(" ").split())
    return {"page_text": text[:8000]}


PROFILE_PROMPT = """Analyze this company's website text. Return ONLY a JSON object with keys:
company_name, what_they_do (1-2 sentences), services (list),
target_customers (who buys from them), industries_served (list),
location (or "unknown"), value_proposition (1 sentence).
Use only what the text says. If unclear, write "unknown".

Website text:
{text}"""


def parse_json(raw: str) -> dict:
    raw = re.sub(r"<think>.*?</think>", "", raw, flags=re.S).strip()
    raw = re.sub(r"^```(json)?|```$", "", raw.strip(), flags=re.M).strip()
    return json.loads(raw)


def analyze_company(state: AgentState) -> dict:
    resp = client.chat.completions.create(
        model=MODEL,
        messages=[{"role": "user", "content": PROFILE_PROMPT.format(text=state["page_text"])}],
        temperature=0.1,
    )
    return {"profile": parse_json(resp.choices[0].message.content)}


graph = StateGraph(AgentState)
graph.add_node("fetch_site", fetch_site)
graph.add_node("analyze_company", analyze_company)
graph.add_edge(START, "fetch_site")
graph.add_edge("fetch_site", "analyze_company")
graph.add_edge("analyze_company", END)
app = graph.compile()

if __name__ == "__main__":
    url = sys.argv[1] if len(sys.argv) > 1 else "https://kuppelabs.com"
    result = app.invoke({"url": url})
    print(json.dumps(result["profile"], indent=2))
