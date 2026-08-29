"""Seed Kong's Q3 nurture campaigns into customer_preferences.campaigns.

Source: "Q3 Candidate Nurture Campaign.docx" (Kong, Aug 2026). Content is stored
as source material for the generator to rewrite per candidate -- not as a
template -- so key_facts pins the figures that must not drift.

Run after applying add_campaigns_field.sql. Idempotent: replaces campaigns whose
key matches, leaves any others untouched.
"""
import json, os, sys
from dotenv import load_dotenv
from supabase import create_client

load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))
sb = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_KEY"))

COMPANY = "Kong"
ASSETS = "https://qnlqclxuzkbtiytgqins.supabase.co/storage/v1/object/public/email-assets"

CAMPAIGNS = [
    {
        "key": "kong-quota-numbers",
        "name": "The numbers behind a Kong quota",
        "email_type": "nurture",
        "is_active": True,
        "source_content": (
            "If you're in sales, you want to know one thing: are reps actually hitting quota?\n"
            "Here's what it looks like at Kong:\n"
            "\U0001F3AF 49% of reps are over 100% attainment\n"
            "\U0001F680 Ramped reps average 117% attainment\n"
            "\U0001F4C8 Productivity per rep doubled Q1 to Q2\n"
            "\U0001F4B0 AMS is running at 170% of plan\n"
            "And we're expanding - Milan is our newest flag in the ground. \U0001F1EE\U0001F1F9\n"
            "Not looking right now? No pressure. But if Kong is on your radar, "
            "this is what we're building."
        ),
        # Pinned: these are quantitative claims about a real company. If the model
        # rounds or drops one, the email states something false.
        "key_facts": [
            "49%",
            "117%",
            "170% of plan",
            "Milan",
        ],
        "subject_examples": [
            "The numbers behind a Kong quota 📊",
        ],
        "tone_notes": "Direct and numbers-forward, aimed at GTM/sales talent. Keep the emoji energy.",
        "image_url": f"{ASSETS}/kong-milan-team.jpg",
        "image_alt": "The Kong team in front of the Duomo in Milan",
        "cta_label": "See what's open at Kong",
        "cta_url": "https://konghq.com/company/careers",
    },
    {
        "key": "kong-ceo-pasta",
        "name": "Our CEO traded APIs for pasta",
        "email_type": "nurture",
        "is_active": True,
        "source_content": (
            "When you're considering your next company, the product and opportunity matter "
            "- but so do the people you're building it with.\n"
            "This is Kong CEO and co-founder Augusto \"Aghi\" Marietti getting hands-on at a "
            "recent team event.\n"
            "It's a small glimpse into something that's hard to capture in a job description: "
            "the culture at Kong.\n"
            "We're ambitious. We move fast. We're building at the intersection of APIs + AI "
            "and competing on a global stage.\n"
            "But we also have leaders who are accessible, roll up their sleeves, and genuinely "
            "enjoy building alongside the team.\n"
            "That combination matters - especially when you're deciding where to spend the next "
            "chapter of your career.\n"
            "You may not be looking right now, and that's okay. I'd still love to keep the "
            "conversation open and give you a window into what we're building at Kong."
        ),
        "key_facts": [
            "Aghi",
        ],
        "subject_examples": [
            "Our CEO traded APIs for pasta 🍝",
            "What leadership looks like at Kong 🦍",
            "Behind the scenes at Kong 🦍",
        ],
        "tone_notes": "Warm and culture-led. Not a hard sell; the ask is only to stay connected.",
        "image_url": f"{ASSETS}/kong-ceo-pasta.png",
        "image_alt": "Kong CEO and co-founder Aghi Marietti cooking pasta at a team event",
        "cta_label": "",
        "cta_url": "",
    },
    {
        "key": "kong-ceo-pasta-punchy",
        "name": "Our CEO traded APIs for pasta (punchy)",
        "email_type": "nurture",
        "is_active": True,
        "source_content": (
            "That's our CEO and co-founder, Aghi Marietti, trading APIs for pasta at a recent "
            "Kong team event.\n"
            "It says a lot about the culture here.\n"
            "Kong is ambitious - AI + APIs, enterprise scale, global growth - but we've managed "
            "to keep the human side of the company as we've grown.\n"
            "Accessible leadership. People who roll up their sleeves. A team that takes the "
            "mission seriously without taking itself too seriously.\n"
            "You may be perfectly happy where you are today. No hard sell from me.\n"
            "I just want to keep Kong on your radar for whenever the timing is right.\n"
            "Stay curious. Stay connected."
        ),
        "key_facts": [
            "Aghi Marietti",
        ],
        "subject_examples": [
            "Yes, that's our CEO making pasta 🍝",
            "Behind the scenes at Kong 🦍",
        ],
        "tone_notes": (
            "Shortest of the three - the doc calls this the 'even punchier version for "
            "passive GTM talent'. Keep it tight; no hard sell."
        ),
        "image_url": f"{ASSETS}/kong-ceo-pasta.png",
        "image_alt": "Kong CEO and co-founder Aghi Marietti cooking pasta at a team event",
        "cta_label": "",
        "cta_url": "",
    },
]


def main():
    rows = sb.table("customer_preferences").select("id, campaigns").eq(
        "company_name", COMPANY).execute().data
    if not rows:
        print(f"No customer_preferences row for {COMPANY}; create one first.")
        return 1

    row = rows[0]
    existing = row.get("campaigns") or []
    if isinstance(existing, str):
        existing = json.loads(existing)

    new_keys = {c["key"] for c in CAMPAIGNS}
    kept = [c for c in existing if c.get("key") not in new_keys]
    merged = kept + CAMPAIGNS

    sb.table("customer_preferences").update({"campaigns": merged}).eq("id", row["id"]).execute()
    print(f"{COMPANY}: {len(kept)} kept + {len(CAMPAIGNS)} seeded = {len(merged)} campaigns")
    for c in merged:
        print(f"  {c['key']:26s} {c.get('email_type','?'):8s} "
              f"facts={len(c.get('key_facts') or [])} "
              f"subjects={len(c.get('subject_examples') or [])} "
              f"img={'Y' if c.get('image_url') else 'N'} "
              f"cta={'Y' if c.get('cta_url') else 'N'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
