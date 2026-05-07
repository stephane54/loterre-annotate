#!/usr/bin/env python3
import json

# Check the structure of the results JSON
with open('outputs_autoprofile_quality/27X_en.json') as f:
    data = json.load(f)

print("Keys in results JSON:", list(data.keys()))
results = data.get('results', [])
print("Number of results:", len(results))
if results:
    r = results[0]
    print("\nFirst result:")
    print("  id:", r.get('id'))
    print("  text snippet:", r.get('text')[:50] if r.get('text') else None)
    print("  Has 'matches':", 'matches' in r)
    if 'matches' in r:
        print("  Number of matches:", len(r['matches']))
