"""
audit_vibe_profiles.py

Runs after generate_vibe_profiles.py to flag hostels whose vibe_profile
might need a human look, instead of requiring a manual read of all 228.

Flags:
1. TOO_SHORT       - profile is suspiciously short (likely truncated or
                      the model had too little to work with).
2. MISSING_FLAGS    - hostel has flagged_issues but the profile doesn't
                      seem to reference any issue-adjacent language.
3. NO_PROFILE       - hostel has no vibe_profile at all (generation
                      failed/skipped).
4. GENERIC          - profile looks templated/empty-content (rare, but
                      catches degenerate model output).

This does NOT try to judge writing quality - only structural/coverage
red flags a human should double check.
"""

import json
import os

HOSTELS_PATH = os.path.join(os.path.dirname(__file__), "hostels.json")

# Rough vocabulary that suggests a concern/issue is being acknowledged,
# even softly ("some guests have reported...", "can be inconsistent...").
ISSUE_LANGUAGE = [
    "issue", "concern", "inconsistent", "mixed", "hit-or-miss", "hit or miss",
    "some guests", "occasional", "can be", "however", "though", "not ideal",
    "limited", "lacking", "dated", "worn", "noise", "noisy", "mold", "damp",
    "report", "complaint", "downside", "drawback", "challenge",
]

SHORT_WORD_THRESHOLD = 40


def main():
    with open(HOSTELS_PATH, "r", encoding="utf-8") as f:
        hostels = json.load(f)

    flags = []

    for h in hostels:
        profile = h.get("vibe_profile")
        name = h.get("name")
        hid = h.get("id")

        if not profile:
            flags.append((hid, name, "NO_PROFILE", "No vibe_profile field present"))
            continue

        word_count = len(profile.split())
        if word_count < SHORT_WORD_THRESHOLD:
            flags.append((hid, name, "TOO_SHORT", f"Only {word_count} words"))

        if not profile.strip():
            flags.append((hid, name, "GENERIC", "Profile is empty/whitespace"))

        flagged_issues = h.get("flagged_issues") or []
        if flagged_issues:
            lower_profile = profile.lower()
            has_issue_language = any(kw in lower_profile for kw in ISSUE_LANGUAGE)
            if not has_issue_language:
                issue_summaries = "; ".join(fi.get("issue", "?") for fi in flagged_issues)
                flags.append((
                    hid, name, "MISSING_FLAGS",
                    f"Has {len(flagged_issues)} flagged_issue(s) [{issue_summaries}] "
                    f"but profile has no issue-adjacent language"
                ))

    print(f"Total hostels: {len(hostels)}")
    print(f"Flagged for review: {len(flags)}\n")

    by_type = {}
    for hid, name, ftype, detail in flags:
        by_type.setdefault(ftype, []).append((hid, name, detail))

    for ftype in ["NO_PROFILE", "TOO_SHORT", "GENERIC", "MISSING_FLAGS"]:
        items = by_type.get(ftype, [])
        if not items:
            continue
        print(f"=== {ftype} ({len(items)}) ===")
        for hid, name, detail in items:
            print(f"  id={hid:3} {name!r} - {detail}")
        print()

    if not flags:
        print("No issues found - all profiles look structurally sound.")


if __name__ == "__main__":
    main()
