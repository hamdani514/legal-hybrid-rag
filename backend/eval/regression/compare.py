"""Compare an "after" record with two "before" records (eval/regression/freeze.py).

A query counts as CHANGED only if its "after" result differs from BOTH
"before" runs; one whose two "before" runs already differ is reported as
unstable (the LLM query analyser), not as caused by the change.

    venv/Scripts/python.exe eval/regression/compare.py before_a.json before_b.json after.json
"""
import json, sys
a, b, after = (json.load(open(f, encoding="utf-8")) for f in sys.argv[1:4])
key = lambda r: json.dumps([r["shown"], r["no_results"], r["notice"], r["message"]])
changed, unstable, same = [], [], 0
for q in a:
    if key(a[q]) != key(b[q]):
        unstable.append(q)
    elif key(after[q]) != key(a[q]):
        changed.append(q)
    else:
        same += 1
print(f"{len(a)} queries: identical {same} | changed by the code change {len(changed)} | naturally unstable {len(unstable)}")
for q in changed:
    print(f"  CHANGED{' (description)' if after[q]['is_narrative'] else ''}: {q[:90]}")
    print(f"     before: {a[q]['shown'][:3]} no_results={a[q]['no_results']}")
    print(f"     after : {after[q]['shown'][:3]} no_results={after[q]['no_results']} judge={after[q]['judge_used']}")
for q in unstable:
    print(f"  unstable: {q[:90]}")
