#!/usr/bin/env python3
"""Test the production ISTEX terms-matcher API and parse response format."""
import urllib.request, urllib.error, json, sys

BASE = "https://terms-tools.services.istex.fr/v1/en/terms-matcher/json-standoff/annotate"

def call(vocab, docs):
    """Send docs as JSON array, return parsed response."""
    url = f"{BASE}?loterreID={vocab}"
    body = json.dumps(docs).encode("utf-8")
    req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        print(f"HTTP {e.code}: {e.read().decode()[:200]}", file=sys.stderr)
        return None

# Test 1: voir la structure complete de la reponse
docs = [{"id": 1, "value": "Spatial memory is a key cognitive process. Long-term memory and working memory updating."}]
resp = call("P66", docs)
print("=== Structure complete de la reponse P66 ===")
print(json.dumps(resp, indent=2, ensure_ascii=False))

print()

# Test 2: voir si 27X fonctionne aussi
docs2 = [{"id": 1, "value": "The Parthenon was a temple of the goddess Athena with a cult dedicated to her."}]
resp2 = call("27X", docs2)
print("=== Structure complete de la reponse 27X ===")
print(json.dumps(resp2, indent=2, ensure_ascii=False))
