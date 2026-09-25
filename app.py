"""Prospect Intelligence Agent - full-page-transition stepper, live thinking motion,
staggered result reveal, and clickable stage history."""
import sys, os, time
sys.path.insert(0, os.path.dirname(__file__))
import streamlit as st

from step1_profile import fetch_site, analyze_company
from step4_merged import (determine_icp, find_competitors, extract_competitors,
                            analyze_competitor_offerings, discover_prospects, extract_prospects)
from step5_outreach import write_outreach
from step6_enrich import enrich_contacts

st.set_page_config(page_title="Prospect Intelligence Agent", page_icon="🎯", layout="wide")

STAGES = ["Research", "Ideal customer", "Competitors", "Your edge", "Prospects", "Outreach", "Contacts"]

CSS = """
<style>
.stApp { background: #0a0a0f; }
section[data-testid="stSidebar"] { background: #0d0d13; border-right: 1px solid #1f1f2b; }
.block-container { padding-top: 2rem; max-width: 920px; }

.stepper { display: flex; align-items: center; margin-bottom: 1.2rem; overflow-x: auto; }
.step-circle {
  width: 30px; height: 30px; border-radius: 50%; display: flex; align-items: center;
  justify-content: center; font-size: 12px; font-weight: 600; flex-shrink: 0;
  border: 1.5px solid #2a2a3a; color: #666; background: #12121a; transition: all 0.4s ease;
}
.step-circle.done { background: #123c2f; border-color: #10b981; color: #34d399; }
.step-circle.active { background: #10b981; border-color: #10b981; color: #0a0a0f; box-shadow: 0 0 0 5px rgba(16,185,129,0.18); }
.step-line { flex: 1; height: 1px; background: #2a2a3a; min-width: 16px; margin: 0 6px; transition: background 0.4s ease; }
.step-line.done { background: #10b981; }

.nav-row .stButton>button {
  background: #12121a !important; border: 1px solid #2a2a3a !important; color: #999 !important;
  font-size: 12px !important; padding: 4px 10px !important; border-radius: 8px !important;
  height: auto !important;
}
.nav-row .stButton>button:hover { border-color: #10b981 !important; color: #10b981 !important; }

@keyframes pageIn { from { opacity: 0; transform: translateY(10px); } to { opacity: 1; transform: translateY(0); } }
.page { animation: pageIn 0.5s ease; }

@keyframes pulse { 0%,100% { opacity: 1; transform: scale(1); } 50% { opacity: 0.5; transform: scale(0.85); } }
.thinking-row { display: flex; align-items: center; gap: 10px; margin-bottom: 18px; }
.dot { width: 9px; height: 9px; border-radius: 50%; background: #10b981; animation: pulse 1.1s ease-in-out infinite; }
.dot:nth-child(2) { animation-delay: 0.15s; }
.dot:nth-child(3) { animation-delay: 0.3s; }
.thinking-title { font-size: 20px; font-weight: 600; color: #eee; }

.terminal {
  background: #0d0d13; border: 1px solid #1f1f2b; border-radius: 10px; padding: 16px 20px;
  font-family: 'SF Mono', 'Fira Code', monospace; font-size: 12.5px; min-height: 90px;
}
@keyframes lineIn { from { opacity: 0; transform: translateX(-4px); } to { opacity: 1; transform: translateX(0); } }
.term-line { opacity: 0; animation: lineIn 0.4s ease forwards; padding: 2px 0; color: #8a8a9a; }
.term-line::before { content: "› "; color: #10b981; }
.term-cursor { display: inline-block; width: 6px; height: 13px; background: #10b981; animation: pulse 0.8s infinite; vertical-align: middle; margin-left: 2px; }

@keyframes cardPop { from { opacity: 0; transform: translateY(14px) scale(0.98); } to { opacity: 1; transform: translateY(0) scale(1); } }
.card {
  background: #12121a; border: 1px solid #1f1f2b; border-radius: 14px; padding: 24px 28px;
  margin-bottom: 16px; animation: cardPop 0.45s ease both;
}
.result-card {
  background: #12121a; border: 1px solid #1f1f2b; border-radius: 14px; padding: 22px 26px;
  margin-bottom: 14px; animation: cardPop 0.45s ease both;
  transition: border-color 0.2s ease;
}
.result-card:hover { border-color: #2f2f45; }

.chip {
  display: inline-block; background: #1a1a26; border: 1px solid #2a2a3a; color: #bbb;
  border-radius: 20px; padding: 4px 12px; font-size: 12px; margin: 3px 4px 3px 0;
}
.chip.query { color: #7dd3fc; border-color: #1e3a4a; background: #0d1f2a; }
.chip.win { color: #34d399; border-color: #10553f; background: #0f1f18; }
.chip.phone { color: #c4b5fd; border-color: #3b2e5c; background: #17132a; }

.company-badge { display: flex; align-items: center; gap: 10px; margin-bottom: 6px; }
.company-avatar {
  width: 34px; height: 34px; border-radius: 8px; background: linear-gradient(135deg,#3b82f6,#8b5cf6);
  display: flex; align-items: center; justify-content: center; font-weight: 700; color: white; font-size: 15px; flex-shrink:0;
}
h1, h2, h3 { color: #eee !important; }
.stMarkdown p { color: #ccc; }
hr { border-color: #1f1f2b !important; }
.section-title { font-size: 22px; font-weight: 600; color: #eee; margin: 8px 0 18px 0; }
</style>
"""
st.markdown(CSS, unsafe_allow_html=True)

import base64
def load_logo():
    try:
        with open('assets/logo_b64.txt') as f:
            return f.read().strip()
    except FileNotFoundError:
        return None
LOGO_B64 = load_logo()



def render_stepper(active_idx, done_idx):
    html = '<div class="stepper">'
    for i, label in enumerate(STAGES):
        cls = "done" if i <= done_idx else ("active" if i == active_idx else "")
        icon = "✓" if i <= done_idx and i != active_idx else str(i + 1)
        html += f'<div class="step-circle {cls}" title="{label}">{icon}</div>'
        if i < len(STAGES) - 1:
            line_cls = "done" if i <= done_idx else ""
            html += f'<div class="step-line {line_cls}"></div>'
    html += "</div>"
    return html


def thinking_page(title, terminal_lines):
    lines_html = "".join(
        f'<div class="term-line" style="animation-delay:{i*0.35}s">{line}</div>'
        for i, line in enumerate(terminal_lines)
    ) + '<span class="term-cursor"></span>'
    return f'''<div class="page">
      <div class="thinking-row"><div class="dot"></div><div class="dot"></div><div class="dot"></div>
        <div class="thinking-title">{title}</div></div>
      <div class="terminal">{lines_html}</div>
    </div>'''


def result_page(inner_html):
    return f'<div class="page"><div class="card">{inner_html}</div></div>'


st.title("Find your next customers")
st.caption("Enter your company URL — we'll research your market, out-position your competitors, and hand you ready-to-send outreach with real contacts.")
st.markdown('<div style="display:flex;gap:16px;margin:14px 0 22px 0;font-size:13px;color:#888"><span>1. Enter your URL</span><span style="color:#333">→</span><span>2. We research your market</span><span style="color:#333">→</span><span>3. Get outreach with real contacts</span><span style="color:#555;margin-left:8px">· ~90 seconds</span></div>', unsafe_allow_html=True)

with st.sidebar:
    if LOGO_B64:
        st.markdown(f'<div style="display:flex;align-items:center;gap:8px;margin-bottom:2px"><img src="data:image/png;base64,{LOGO_B64}" style="height:22px"><span style="font-size:15px;font-weight:600;color:#eee">Prospect Intelligence</span></div>', unsafe_allow_html=True)
    else:
        st.markdown("### 🎯 Prospect Intelligence")
    st.caption("Fully hands-off prospecting")
    st.markdown('<div style="margin-top:24px;padding-top:16px;border-top:1px solid #1f1f2b"><a href="https://kuppelabs.com" target="_blank" style="color:#666;font-size:11px;text-decoration:none">Built by Kuppe Labs</a></div>', unsafe_allow_html=True)
    company_slot = st.empty()

url = st.text_input("Your company URL", placeholder="https://yourcompany.com", label_visibility="collapsed")
run = st.button("Find my prospects →", type="primary", disabled=not url)

stepper_slot = st.empty()
nav_slot = st.empty()
page_slot = st.empty()

if "snapshots" not in st.session_state:
    st.session_state.snapshots = {}
if "final_state" not in st.session_state:
    st.session_state.final_state = None
if "view_stage" not in st.session_state:
    st.session_state.view_stage = None  # None = show final results

THINK_TIME = 1.6

if run:
    st.session_state.snapshots = {}
    st.session_state.view_stage = None
    state = {"url": url}

    steps = [
        ("Reading your website...", ["Fetching page content", "Parsing structure", "Extracting positioning"]),
        ("Identifying your ideal customers...", ["Analyzing your services", "Modeling buyer profile", "Mapping buying signals"]),
        ("Scanning your competitive landscape...", ["Querying live search", "Cross-referencing results", "Filtering real businesses"]),
        ("Checking what your competitors are offering...", ["Comparing feature sets", "Spotting gaps", "Finding your edge"]),
        ("Finding real prospects who need this...", ["Running targeted searches", "Verifying real businesses", "De-duplicating results"]),
        ("Writing your personalized outreach...", ["Drafting messages", "Applying your edge", "Personalizing per prospect"]),
        ("Finding real contact info...", ["Verifying official websites", "Scanning for email & phone", "Cross-checking Hunter.io"]),
    ]

    for i, (title, lines) in enumerate(steps):
        stepper_slot.markdown(render_stepper(i, i - 1), unsafe_allow_html=True)
        page_slot.markdown(thinking_page(title, lines), unsafe_allow_html=True)
        time.sleep(THINK_TIME)

        if i == 0:
            state.update(fetch_site(state)); state.update(analyze_company(state))
            p = state["profile"]
            with st.sidebar:
                company_slot.markdown(f'''
                <div class="company-badge"><div class="company-avatar">{p.get("company_name","?")[:1]}</div>
                <div><b>{p.get("company_name","")}</b><br><span style="color:#888;font-size:12px">{url}</span></div></div>
                <p style="color:#999;font-size:13px">{p.get("what_they_do","")}</p>''', unsafe_allow_html=True)
            html = f"<h3 style='margin-top:0'>You are {p.get('company_name','')}</h3><p>{p.get('what_they_do','')}</p>"
        elif i == 1:
            state.update(determine_icp(state))
            icp = state["icp"]
            kw = "".join(f'<span class="chip query">{k}</span>' for k in icp.get("search_keywords", [])[:6])
            html = f"<h3 style='margin-top:0'>Your ideal customer</h3><p>{icp.get('icp_summary','')}</p>{kw}"
        elif i == 2:
            state.update(find_competitors(state)); state.update(extract_competitors(state))
            comps = state["competitors"]
            chips = "".join(f'<span class="chip">{c["name"]}</span>' for c in comps[:8])
            html = f"<h3 style='margin-top:0'>Found {len(comps)} competitors</h3>{chips}"
        elif i == 3:
            state.update(analyze_competitor_offerings(state))
            adv = state["competitor_offerings"].get("this_company_advantages", [])
            html = f"<h3 style='margin-top:0'>Your competitive edge</h3>" + "".join(
                f'<div style="margin:6px 0"><span class="chip win">✓ {a}</span></div>' for a in adv[:3])
        elif i == 4:
            state.update(discover_prospects(state)); state.update(extract_prospects(state))
            prospects = state["prospects"]
            chips = "".join(f'<span class="chip">{pr["name"]}</span>' for pr in prospects[:10])
            html = f"<h3 style='margin-top:0'>Found {len(prospects)} prospects</h3>{chips}"
        elif i == 5:
            state.update(write_outreach(state))
            html = f"<h3 style='margin-top:0'>{len(state['outreach'])} outreach drafts ready</h3><p>Each one references your real competitive edge.</p>"
        elif i == 6:
            state.update(enrich_contacts(state))
            found = sum(1 for e in state["enriched"] if e.get("contact", {}).get("email") or e.get("contact", {}).get("phone"))
            html = f"<h3 style='margin-top:0'>Contact info found</h3><p>{found} of {len(state['enriched'])} prospects have a verified contact.</p>"

        st.session_state.snapshots[i] = html
        page_slot.markdown(result_page(html), unsafe_allow_html=True)
        time.sleep(0.8)

    stepper_slot.markdown(render_stepper(6, 6), unsafe_allow_html=True)
    page_slot.empty()
    st.session_state.final_state = state
    st.rerun()

# ---------- Post-run: navigation + content ----------
if st.session_state.final_state is not None:
    state = st.session_state.final_state
    done_idx = 6
    active_idx = st.session_state.view_stage if st.session_state.view_stage is not None else 6
    stepper_slot.markdown(render_stepper(active_idx, done_idx), unsafe_allow_html=True)

    with nav_slot.container():
        st.markdown('<div class="nav-row">', unsafe_allow_html=True)
        cols = st.columns(len(STAGES) + 1)
        for i, label in enumerate(STAGES):
            if cols[i].button(label, key=f"nav_{i}"):
                st.session_state.view_stage = i
                st.rerun()
        if cols[-1].button("Results ✓", key="nav_final"):
            st.session_state.view_stage = None
            st.rerun()
        st.markdown('</div>', unsafe_allow_html=True)

    if st.session_state.view_stage is not None:
        html = st.session_state.snapshots.get(st.session_state.view_stage, "<p>No data</p>")
        page_slot.markdown(result_page(html), unsafe_allow_html=True)
    else:
        page_slot.empty()
        st.divider()
        st.markdown('<div class="section-title">Your prospects, ready to send</div>', unsafe_allow_html=True)

        results_container = st.container()
        for idx, e in enumerate(state["enriched"]):
            contact = e.get("contact", {})
            email = contact.get("email")
            phone = contact.get("phone")
            badge = f'<span class="chip win">📧 {email}</span>' if email else ""
            badge += f'<span class="chip phone">📞 {phone}</span>' if phone else ""
            if not email and not phone:
                badge = '<span class="chip">No contact found</span>'
            with results_container:
                st.markdown(f'''<div class="result-card">
                  <h3 style="margin-top:0">{e["name"]}</h3>
                  {badge}
                  <p style="margin-top:12px"><b>{e.get("subject","")}</b></p>
                  <p>{e.get("message","")}</p>
                </div>''', unsafe_allow_html=True)
                if email:
                    st.link_button("✉️ Open in email", f"mailto:{email}?subject={e.get('subject','')}&body={e.get('message','')}", key=f"mail_{idx}")
            time.sleep(0.25)
