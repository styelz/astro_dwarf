import json

p = r"C:\Users\pbp16\.cursor\projects\c-Users-pbp16-Desktop-Dwarf-schedule-tool-astro-dwarf\agent-transcripts\6ff8894b-5a5b-4661-b3bc-397bfbe8b9d3\6ff8894b-5a5b-4661-b3bc-397bfbe8b9d3.jsonl"
with open(p, encoding="utf-8", errors="replace") as f:
    for i, line in enumerate(f):
        o = json.loads(line)
        msg = o.get("message")
        print("=" * 40, i, o.get("role"), type(msg).__name__)
        if isinstance(msg, dict):
            print(list(msg.keys())[:20])
            content = msg.get("content")
            if isinstance(content, str):
                print(content[:2000])
            elif isinstance(content, list):
                for part in content[:6]:
                    if isinstance(part, dict):
                        t = part.get("type") or part.get("text") or ""
                        text = part.get("text") or ""
                        print("PART", part.get("type"), (text[:1500] if isinstance(text, str) else str(part)[:400]))
                    else:
                        print("PART", str(part)[:400])
        else:
            print(str(msg)[:2000])
