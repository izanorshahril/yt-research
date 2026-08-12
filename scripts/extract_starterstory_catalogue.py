import os
import json
import glob
import re
import csv

# Directory paths
TRANSCRIPT_DIR = os.path.join("data", "transcripts", "starterstory")
OUTPUT_CSV = os.path.join("data", "starterstory_catalogue.csv")

# Known Tech Stack & Tools list for matching (with exact boundary regexes where needed)
TECH_KEYWORDS = [
    ("React Native", r'\bReact Native\b'),
    ("Next.js", r'\bNext(?:\.js)?\b'),
    ("React", r'\bReact\b'),
    ("Vue", r'\bVue(?:\.js)?\b'),
    ("Nuxt", r'\bNuxt(?:\.js)?\b'),
    ("Svelte", r'\bSvelte\b'),
    ("Tailwind CSS", r'\bTailwind(?:CSS)?\b'),
    ("Flutter", r'\bFlutter\b'),
    ("iOS", r'\biOS\b'),
    ("Android", r'\bAndroid\b'),
    ("Swift", r'\bSwift\b'),
    ("Kotlin", r'\bKotlin\b'),
    ("TypeScript", r'\bTypeScript\b'),
    ("JavaScript", r'\bJavaScript\b'),
    ("Node.js", r'\bNode(?:\.js)?\b'),
    ("Python", r'\bPython\b'),
    ("Django", r'\bDjango\b'),
    ("FastAPI", r'\bFastAPI\b'),
    ("Ruby on Rails", r'\b(?:Ruby on Rails|Rails)\b'),
    ("PHP", r'\bPHP\b'),
    ("Laravel", r'\bLaravel\b'),
    ("Supabase", r'\bSupabase\b'),
    ("Firebase", r'\bFirebase\b'),
    ("PostgreSQL", r'\bPostgre(?:SQL)?\b'),
    ("MongoDB", r'\bMongoDB\b'),
    ("Redis", r'\bRedis\b'),
    ("SQLite", r'\bSQLite\b'),
    ("AWS", r'\bAWS\b'),
    ("Vercel", r'\bVercel\b'),
    ("Netlify", r'\bNetlify\b'),
    ("Cloudflare", r'\bCloudflare\b'),
    ("Heroku", r'\bHeroku\b'),
    ("DigitalOcean", r'\bDigitalOcean\b'),
    ("OpenAI", r'\bOpenAI\b'),
    ("ChatGPT", r'\bChatGPT\b'),
    ("GPT-4", r'\bGPT-4\b'),
    ("Claude", r'\bClaude\b'),
    ("Anthropic", r'\bAnthropic\b'),
    ("Midjourney", r'\bMidjourney\b'),
    ("Stable Diffusion", r'\bStable Diffusion\b'),
    ("Ollama", r'\bOllama\b'),
    ("Whisper", r'\bWhisper\b'),
    ("Replicate", r'\bReplicate\b'),
    ("DeepSeek", r'\bDeepSeek\b'),
    ("Stripe", r'\bStripe\b'),
    ("Lemon Squeezy", r'\bLemon Squeezy\b'),
    ("Paddle", r'\bPaddle\b'),
    ("Gumroad", r'\bGumroad\b'),
    ("Zapier", r'\bZapier\b'),
    ("N8N", r'\bn8n\b'),
    ("Make.com", r'\bMake\.com\b'),
    ("Figma", r'\bFigma\b'),
    ("Webflow", r'\bWebflow\b'),
    ("Bubble", r'\bBubble(?:\.io)?\b'),
    ("Framer", r'\bFramer\b'),
    ("WordPress", r'\bWordPress\b'),
    ("Postiz", r'\bPostiz\b'),
    ("Resend", r'\bResend\b'),
    ("Mailchimp", r'\bMailchimp\b'),
    ("Substack", r'\bSubstack\b'),
    ("Discord", r'\bDiscord\b')
]

def clean_text(text):
    if not text:
        return ""
    text = re.sub(r'\s+', ' ', text)
    return text.strip()

def extract_revenue(title, text):
    full_search = f"{title} {text[:1500]}"
    
    # Priority patterns
    patterns = [
        r'\$(\d+(?:,\d+)*(?:\.\d+)?\s*(?:k|m|b|million|thousand)?\s*/\s*(?:month|mo|mrr|year|yr|annual))',
        r'\$(\d+(?:,\d+)*(?:\.\d+)?\s*(?:k|m|b|million|thousand))\s*(?:a|per|\/)\s*(?:month|mo|year|yr|mrr)',
        r'(\$\d+(?:,\d+)*(?:\.\d+)?\s*(?:k|m|million)\s*(?:mrr|arr))'
    ]
    
    for pat in patterns:
        match = re.search(pat, full_search, re.IGNORECASE)
        if match:
            rev = match.group(1).strip()
            # Clean up /mo vs /month formatting safely
            rev = re.sub(r'/(?:month|mo)\b', '/month', rev, flags=re.I)
            rev = re.sub(r'/(?:year|yr|annual)\b', '/year', rev, flags=re.I)
            return rev
            
    # Simple dollar amount in title (e.g. $100K in 90 days, $65K in 3 Days, $1.5M)
    title_rev = re.search(r'\$(\d+(?:\.\d+)?\s*(?:K|M|million|thousand)?)', title, re.I)
    if title_rev:
        val = title_rev.group(0)
        if "/month" in title.lower() or "month" in title.lower():
            return val + "/month"
        elif "year" in title.lower():
            return val + "/year"
        return val

    return "Not specified"

def extract_founder(title, text):
    text_snippet = text[:1500]
    
    patterns = [
        r'(?:This is|Meet)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)',
        r'my name is\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)',
        r"I'm\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)\s+(?:and|a|the)",
        r'([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)\s+(?:built|created|started|launched)\s+a'
    ]
    
    for pat in patterns:
        m = re.search(pat, text_snippet)
        if m:
            candidate = m.group(1).strip()
            if candidate.lower() not in ["most", "this", "here", "today", "what", "how", "after", "before", "when", "some", "first", "last", "okay"]:
                return candidate
                
    title_m = re.search(r'How\s+([A-Z][a-z]+)\s+', title)
    if title_m and title_m.group(1).lower() not in ["i", "to", "we", "this", "a"]:
        return title_m.group(1)
        
    return "Independent Founder"

def extract_business_name(title, text):
    # Check parenthetical product names in title e.g. "(Gravl)" or "(Subscribr Breakdown)"
    paren_m = re.search(r'\(([^)]+)\)', title)
    if paren_m:
        val = paren_m.group(1).replace("Breakdown", "").replace("Case Study", "").strip()
        if val and not val.startswith("$") and len(val) > 2:
            return val
            
    # Check "How [Product] Went From"
    how_m = re.search(r'How\s+([A-Z][A-Za-z0-9_.-]+)\s+Went', title)
    if how_m:
        return how_m.group(1)
        
    # Search transcript for "called [Product]", "named [Product]", "app called [Product]"
    snippet = text[:2500]
    called_m = re.search(r'(?:called|named)\s+([A-Z][A-Za-z0-9_.-]+)', snippet)
    if called_m:
        candidate = called_m.group(1).strip()
        if candidate.lower() not in ["a", "the", "an", "this", "something", "it", "one"]:
            return candidate
            
    # Fallback clean title string
    clean_t = re.sub(r'How I|I Built a|How To|Makes \$[0-9KkMm/.]+\s*|I Make \$[0-9KkMm/.]+\s*', '', title, flags=re.I).strip()
    clean_t = re.sub(r'^\$\d+[\w/]*\s*', '', clean_t).strip()
    if clean_t:
        parts = clean_t.split('|')[0].split('-')[0].split('(')[0].strip()
        if len(parts) > 3:
            return parts[:45]
            
    return "Featured Product"

def extract_category(title, text):
    combined = (title + " " + text).lower()
    
    if "android" in combined or "ios" in combined or "mobile app" in combined or "app store" in combined:
        return "Mobile App"
    elif "micro-saas" in combined or "microsaas" in combined:
        return "Micro-SaaS"
    elif "agency" in combined or "productized service" in combined or "designjoy" in combined:
        return "Productized Agency"
    elif "chrome extension" in combined or "extension" in combined:
        return "Chrome Extension"
    elif "open source" in combined or "github" in combined:
        return "Open Source Tool"
    elif "ai" in combined or "gpt" in combined or "claude" in combined or "vibe coding" in combined:
        return "AI Tool / SaaS"
    elif "newsletter" in combined or "content" in combined or "youtube" in combined:
        return "Content & Media"
    elif "saas" in combined or "software" in combined:
        return "SaaS"
    elif "ecommerce" in combined or "e-commerce" in combined or "shopify" in combined:
        return "E-commerce"
    else:
        return "Digital Product / SaaS"

def extract_budget(text):
    if not text:
        return "$0 (Bootstrapped)"
        
    snippet = text[:3000]
    
    b_match = re.search(r'(?:budget|cost|spent|invested|starting capital)\s*(?:of|was|is)?\s*(\$\d+(?:,\d+)?|\$0|zero|nothing)', snippet, re.I)
    if b_match:
        val = b_match.group(1)
        if val.lower() in ["$0", "zero", "nothing"]:
            return "$0 (Bootstrapped)"
        return val
        
    if "bootstrapped" in snippet.lower() or "$0" in snippet or "no money" in snippet.lower():
        return "$0 (Bootstrapped)"
        
    if "$100" in snippet or "hundred dollars" in snippet.lower():
        return "< $100"
    if "$500" in snippet or "$1,000" in snippet or "$1000" in snippet:
        return "< $1,000"
        
    return "$0 (Bootstrapped)"

def extract_tech_stack(text):
    if not text:
        return "Not specified"
        
    found = []
    for name, regex in TECH_KEYWORDS:
        if re.search(regex, text, re.IGNORECASE):
            if name not in found:
                found.append(name)
                
    if not found:
        return "Custom Tech / Web Stack"
        
    return ", ".join(found)

def generate_short_description(title, text, business_name, category, revenue, founder):
    if text:
        # Extract meaningful first sentences from transcript
        sentences = [s.strip() for s in re.split(r'[.!?]', text[:900]) if len(s.strip()) > 20]
        # Skip generic greetings
        clean_sentences = [s for s in sentences if not s.lower().startswith(("okay,", "so,", "hey", "welcome"))]
        if not clean_sentences:
            clean_sentences = sentences
            
        summary_text = " ".join(clean_sentences[:2])
        if len(summary_text) > 220:
            summary_text = summary_text[:217] + "..."
        if summary_text:
            return f"{summary_text} (Starter Story Case Study)."
            
    return f"Case study covering {business_name}, a {category} built by {founder} generating {revenue}. Featured on Starter Story."

def process_all_transcripts():
    files = sorted(glob.glob(os.path.join(TRANSCRIPT_DIR, "*.json")))
    files = [f for f in files if not f.endswith("channel.json")]
    
    print(f"Processing {len(files)} transcript files...")
    
    records = []
    
    for idx, filepath in enumerate(files, 1):
        filename = os.path.basename(filepath)
        
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)
            
        metadata = data.get("metadata", {})
        transcript_data = data.get("transcript", {})
        
        video_id = metadata.get("video_id", filename.replace(".json", ""))
        video_title = metadata.get("title", "")
        upload_date = metadata.get("upload_date", "")
        video_url = metadata.get("url", f"https://www.youtube.com/watch?v={video_id}")
        
        has_transcript = transcript_data.get("has_transcript", False)
        segments = transcript_data.get("segments", [])
        
        if has_transcript and segments:
            full_text = " ".join(s.get("text", "") for s in segments)
        else:
            full_text = ""
            
        full_text_clean = clean_text(full_text)
        
        revenue = extract_revenue(video_title, full_text_clean)
        founder = extract_founder(video_title, full_text_clean)
        business_name = extract_business_name(video_title, full_text_clean)
        category = extract_category(video_title, full_text_clean)
        budget = extract_budget(full_text_clean)
        tech_stack = extract_tech_stack(full_text_clean)
        description = generate_short_description(video_title, full_text_clean, business_name, category, revenue, founder)
        
        record = {
            "business_name": business_name,
            "founder": founder,
            "category": category,
            "income_revenue": revenue,
            "starting_budget": budget,
            "tech_stack_tools": tech_stack,
            "short_description": description,
            "video_title": video_title,
            "video_date": upload_date,
            "video_url": video_url
        }
        
        records.append(record)
        
    fieldnames = [
        "business_name",
        "founder",
        "category",
        "income_revenue",
        "starting_budget",
        "tech_stack_tools",
        "short_description",
        "video_title",
        "video_date",
        "video_url"
    ]
    
    os.makedirs(os.path.dirname(OUTPUT_CSV), exist_ok=True)
    
    with open(OUTPUT_CSV, "w", newline="", encoding="utf-8") as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(records)
        
    print(f"Successfully generated {OUTPUT_CSV} with {len(records)} product entries.")

if __name__ == "__main__":
    process_all_transcripts()
