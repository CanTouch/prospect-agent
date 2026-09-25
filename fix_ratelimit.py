"""One-time patch: add automatic retry-with-backoff to every Groq client
so hitting the free-tier rate limit pauses and retries instead of crashing."""
import re

WRAPPER = '''client = Groq(api_key=os.environ["GROQ_API_KEY"])
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
client.chat.completions.create = _retrying_create'''

files = ["step1_profile.py", "step4_merged.py", "step5_outreach.py", "step6_enrich.py"]

for fname in files:
    with open(fname) as f:
        content = f.read()

    if "_retrying_create" in content:
        print(f"{fname}: already patched, skipping")
        continue

    if 'client = Groq(api_key=os.environ["GROQ_API_KEY"])' not in content:
        print(f"{fname}: no client found, skipping")
        continue

    content = content.replace(
        'client = Groq(api_key=os.environ["GROQ_API_KEY"])',
        WRAPPER
    )

    # ensure `import time` is present
    if re.search(r"^import time$", content, re.M) is None:
        content = re.sub(r"(^import [^\n]+\n)", r"\1import time\n", content, count=1, flags=re.M)

    with open(fname, "w") as f:
        f.write(content)
    print(f"{fname}: patched")

print("done")
