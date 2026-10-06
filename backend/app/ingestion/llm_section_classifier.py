import json
import os
import re
from typing import Dict, List, Optional
from loguru import logger
from openai import AsyncOpenAI

from app.config import settings

SECTION_TYPES = [
    "HEADER_CORAM",
    "FACTS",
    "ARGUMENTS",
    "LEGAL_ISSUES",
    "ANALYSIS_RATIO",
    "FINAL_ORDER",
]

# ---------------------------------------------------------------------------
# LLM Prompts
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """You are a Pakistan Supreme Court judgment section classifier.

Your task is to classify text into exactly ONE of these 6 sections:

1. HEADER_CORAM - Court metadata only
2. FACTS - Chronological narrative ONLY (ABSOLUTELY NO ANALYSIS)
3. ARGUMENTS - Counsel submissions ONLY
4. LEGAL_ISSUES - Case-specific questions ONLY
5. ANALYSIS_RATIO - Court reasoning, statutory text, case law (ALL analysis)
6. FINAL_ORDER - Outcome ONLY (1-3 sentences, NO reasoning)

## SECTION 1: HEADER_CORAM

### WHAT HEADER_CORAM CONTAINS:
- Court name: "IN THE SUPREME COURT OF PAKISTAN"
- Jurisdiction: "(Appellate Jurisdiction)" or "(Original Jurisdiction)"
- "PRESENT:" followed by ALL judge names with designations (HCJ, CJ, J)
- Complete case numbers with ALL variations:
  - Civil Appeal No. 565/2011
  - Civil Appeals No. 772 to 780/2012
  - Criminal Petition No. 1603-L of 2021
  - Constitution Petition No. 18 of 2019
  - CPLA No. 2338-L of 2017
  - ALL "K" designations: 85-K, 101-K, 653-K
  - ALL "L" designations: 1603-L, 2338-L
  - ALL "P" designations: 84-P
- ALL appellant/petitioner names from the caption
- ALL respondent names from the caption
- ALL counsel names with designations:
  - ASC = Advocate Supreme Court
  - AOR = Advocate on Record
  - Addl. A.G. = Additional Advocate General
  - Addl. P.G. = Additional Prosecutor General
  - DPG = Deputy Prosecutor General
  - Sr. ASC = Senior Advocate Supreme Court
- Hearing date: "Date of Hearing:" or "Date of hearing:"
- Lower court details: "On appeal from..." or "Against the judgment dated..."

### HEADER_CORAM EXCLUDES:
- The word "JUDGMENT" or "ORDER" itself
- Any text after the first "J.:" (e.g., "Qazi Faez Isa, J.")
- Any analysis or reasoning
- Facts of the case
- Any "we" statements

---

## SECTION 2: FACTS

### WHAT FACTS CONTAINS (ONLY these things):
- Chronological narrative of events in sequence
- "The appellant has challenged the judgment dated..."
- "The facts necessary for decision are that..."
- "Briefly stated the facts of the matter are that..."
- What each party did
- What lower courts decided (Trial Court, High Court, Tribunal, Referee Court, Labor Court)
- Dates of events (dates of judgments, orders, filings)
- FIR details for criminal cases: FIR No., date, sections, police station
- Allegations against the accused for criminal cases
- Procedural history: who filed what, when, what was decided
- Quoted documents when presented as evidence (termination letters, agreements)
- The opening sentence: "This appeal is directed against..."
- "It appears that starting sometime in..."
- "The respondents filed grievance petitions under..."

### FACTS ABSOLUTELY DOES NOT CONTAIN ANY OF THESE:

**FORBIDDEN PATTERN 1 - Statutory Text:**
- "Section 81 of the Customs Act, 1969"
- "Section 18 of the 1973 Act"
- "Section 25A of the 1969 Ordinance"
- "Subsection (4) of section 81"
- "Section 302(b) PPC"
- "Section 497(2) Cr.P.C."
- ANY reference to a specific section of any law
- ANY statutory definition
- "Under Section 426 Cr.P.C."
- "The provisions of Section 302 were correctly interpreted"

**FORBIDDEN PATTERN 2 - Case Citations:**
- "Collector of Customs, Lahore v S. Fazal Ilahi and Sons (2015 SCMR 1488)"
- "PLD 2017 Sindh 347"
- "2001 SCMR 565"
- "2024 SCMR 1021"
- "PLD 1988 SC 416"
- ANY citation of a case (PLD, SCMR, PTD, 2022 PLC, etc.)
- "In the case of Regional Police Officer..."
- "Reference is placed on Muhammad Sarwar Vs. The State"

**FORBIDDEN PATTERN 3 - Court Analysis/Reasoning:**
- "The law enables the Collector to extend the period"
- "Subsection (4) of section 81 provides that..."
- "The same has been provided as a safeguard"
- "The scope and object of section 81"
- "The learned Judges had correctly applied the law"
- "It is also not the case of the appellants"
- "We have not been persuaded to take a different view"
- ANY "we" statement by the court
- ANY "in our view" statement
- ANY "In our opinion" statement
- ANY "We are of the view" statement
- ANY evaluation of evidence
- ANY interpretation of law
- "The possibility cannot be ruled out"
- "It is now established beyond any doubt"
- "All these facts and circumstances when evaluated conjointly"
- "Compel this Court to come to the conclusion"
- "No exception can be taken contrary"

**FORBIDDEN PATTERN 4 - Legal Discussion:**
- "The question came up for consideration"
- "Leave to appeal was granted to consider whether"
- "The same question came up for consideration"
- ANY discussion of legal principles
- ANY discussion of jurisdiction
- ANY discussion of maintainability
- ANY Latin maxims
- "The question of limitation cannot be taken casually"
- "The doctrine of equality before law demands"
- "It is the inherent duty of the Court"

**FORBIDDEN PATTERN 5 - Reasoning/Conclusions:**
- "When no final assessment is made"
- "The provisional assessment will become final"
- "The penalty provision was incorporated"
- ANY reasoning about why something is correct or incorrect
- ANY conclusion about the law
- "The absence of an opportunity being granted expressly is a deficiency"
- "The right of hearing is one of the fundamental principles"
- "The foremost aspiration of setting up a Tribunal"
- "An error or oversight in any order may be reviewed"

**FORBIDDEN PATTERN 6 - "We" Statements:**
- "We have heard learned counsel"
- "We have considered"
- "We have perused"
- "We are of the view"
- "We notice that"
- "We find that"
- "We are afraid"
- "We have been informed"
- "We have carefully mapped out"
- "We have seen how"
- "We would emphasize"
- "We turn to the grievance"
- "We have already noted"
- "We are not convinced"
- "We have carefully examined"
- "We are constrained to hold"
- "We have not been persuaded"
- ANY sentence starting with "We"

---

## SECTION 3: ARGUMENTS

### WHAT ARGUMENTS CONTAINS:
- "Learned counsel for the appellant argued/submitted/contended that..."
- "Learned counsel for the respondent argued/submitted/contended that..."
- "Learned counsel for the petitioner argued/submitted/contended that..."
- "The learned Additional Advocate General argued that..."
- "The learned Law Officer contended that..."
- "The learned Additional Advocate General, Punjab submits that..."
- "On the other hand, learned counsel for the respondent contended that..."
- "He further argued/maintained/contended..."
- "It was further averred..."
- "He also contended..."
- "It was further argued..."
- "Raja Muhammad Iqbal, the learned counsel representing the appellant, did not offer any explanation"
- "At the very outset, it has been argued by learned counsel for the petitioner that..."
- "It was submitted by..."
- "It was contended that..."
- "It was prayed that..."

### ARGUMENTS EXCLUDES:
- ANY "we" statements by the court
- ANY court analysis
- ANY narrative about what happened in court
- ANY statutory text (unless quoted by counsel)
- ANY "We have heard learned counsel" statements
- ANY "In our view" statements
- ANY "We have considered" statements
- ANY court reasoning
- ANY evaluation of evidence by the court

---

## SECTION 4: LEGAL_ISSUES

### WRONG (generic templates - NEVER USE):
- (i) Whether the impugned judgment of the High Court is sustainable under the law?
- (ii) Whether the petitioner/appellant is entitled to the relief claimed?
- (iii) Whether the appeal is barred by limitation?
- (iv) Whether sufficient cause has been shown for condonation of delay?
- (v) Whether the provisions of Section 302 were correctly interpreted?
- (vi) Whether the Service Tribunal had jurisdiction?

### HOW TO EXTRACT CASE-SPECIFIC LEGAL_ISSUES:

**Step 1: Look for EXPLICIT questions in the judgment:**
- "Leave to appeal was granted to consider the following questions: (i)..."
- Numbered questions: (i), (ii), (iii), (iv)
- "Whether..." questions
- "The question is whether..."
- "The issue is whether..."
- "The moot question is whether..."
- "The question that arises is whether..."

**Step 2: Extract from the LEAVE GRANTING ORDER:**
- Look for: "Leave to appeal was granted to consider whether..."
- Look for: "The question for consideration is whether..."

**Step 3: Extract from the ARGUMENTS section:**
- What are the lawyers arguing about? Convert their contentions into questions

**Step 4: Extract from the FACTS section:**
- What is the dispute about? Convert the dispute into a question

**Step 5: Extract from the ANALYSIS section:**
- What laws are being interpreted? Convert the interpretation into a question

---

## SECTION 5: ANALYSIS_RATIO

### ANALYSIS_RATIO STARTS AT THE FIRST OCCURRENCE OF:
- "We have heard learned counsel"
- "We have considered"
- "We have perused"
- "At the time of the enactment of the Act"
- "Section 81 has undergone a number of changes"
- "The law enables the Collector"
- "Subsection (4) of section 81 provides"
- "The same question came up for consideration"
- "In the case of Collector of Customs v Auto Mobile Corporation"
- "The learned Judges of the High Court had correctly applied"
- "We have not been persuaded to take a different view"
- "Leave to appeal was granted to consider whether"
- "We have carefully examined"
- "We are of the view"
- "In our view"
- "It appears from the record"
- "Further, we are not convinced"
- "We find that"
- "We notice that"
- "We are afraid"
- "We have been informed"
- "We have carefully mapped out"
- "We have seen how"
- "We would emphasize"
- "We turn to the grievance"
- "We have already noted"
- "We are constrained to hold"
- "The impugned order has two limbs"
- "The impugned order depicts"
- "The purpose of enacting"
- "There is no doubt that"
- "The foremost aspiration"
- "Another most important aspect"
- "An error or oversight"

### ANALYSIS_RATIO INCLUDES:
- ALL "We have heard..." statements
- ALL "We have considered..." statements
- ALL "In our view..." statements
- ALL "We hold that..." statements
- ALL statutory text quoted by the court (ENTIRE sections)
- ALL case citations (PLD, SCMR, PTD, 2022 PLC, etc.)
- ALL Latin maxims and their explanations
- ALL reasoning about constitutional provisions
- ALL discussion of legal principles
- ALL evaluation of evidence by the court
- ALL interpretation of law by the court
- ALL discussion of jurisdiction
- ALL discussion of maintainability
- ALL discussion of "circumstances of exceptional nature"
- ALL analysis of whether something is justified
- ALL conclusions about the law
- ALL "the question came up for consideration" statements
- ALL references to precedents
- ALL discussion of the object and purpose of laws

### ANALYSIS_RATIO EXCLUDES:
- "JUDGE" lines
- "Chief Justice" lines
- "Approved for Reporting"
- Signatures
- Dates of announcement (unless part of reasoning)
- Stenographer's marks
- "Announced in open Court"
- Case numbers (unless part of reasoning)
- Page numbers

---

## SECTION 6: FINAL_ORDER

### FINAL_ORDER CONTAINS ONLY:
- "Therefore, said forty appeals are dismissed, but with no orders as to costs."
- "As a consequence, this petition having no merit is accordingly dismissed and leave to appeal is refused."
- "Accordingly, these appeals are allowed."
- "This petition stands disposed of in above terms."
- "We convert this petition into appeal and allow it."
- "The petitioner is admitted to bail subject to his furnishing bail bonds in the sum of Rs.100,000/- with one surety."
- "As a result of the above discussion, the appeal is dismissed."
- "In view of the foregoing, the appeal is allowed."
- "The result is that the appeal must fail."
- "We do not find any lawful justification to cause any interference."
- "For the foregoing reasons, the appeal is dismissed."
- "Resultantly, we allow this appeal, set aside the impugned judgment and restore that of the learned Election Tribunal."
- "This Civil Appeal is dismissed not only on merits but also being barred by time."
- "The appeal is dismissed with no order as to costs."
- "We are constrained to hold that the judgment of the learned High Court is based upon misconception of law and the same could not prevail."

### FINAL_ORDER EXCLUDES:
- ANY reasoning
- "Announced in open court"
- "Approved for reporting"
- Judge signatures: "JUDGE", "Chief Justice"
- Dates (unless part of disposition)
- Case numbers
- Page numbers
- "Islamabad, the"
- "Karachi, the"
- Stenographer's marks
- "Not Approved For Reporting"
- "Approved for reporting" text
- "s/d" or similar marks
- Any text after the outcome

---

## STRICT RULES:

### RULE 1: NO EMPTY SECTIONS
- Every section must have content. If a section would be empty, put the most relevant content there.

### RULE 2: CLASSIFICATION PRIORITY ORDER
1. HEADER_CORAM - Beginning of document to "JUDGMENT" or first "J.:"
2. FACTS - First "J.:" or numbered paragraph to FIRST analysis pattern
3. ARGUMENTS - "Learned counsel" paragraphs before FIRST "we"
4. LEGAL_ISSUES - Numbered questions or implicit issues
5. ANALYSIS_RATIO - FIRST analysis pattern to before "JUDGE" lines
6. FINAL_ORDER - Outcome paragraph before "JUDGE" lines

### RULE 3: CONTENT MUST COME FROM THE JUDGMENT
- DO NOT fabricate or summarize content
- Use the EXACT text from the judgment
- DO NOT add explanatory text

### RULE 4: PRESERVE FORMATTING
- Preserve paragraph breaks and numbering
- Preserve quoted text

### RULE 5: BE PRECISE WITH SECTION BOUNDARIES
- FACTS ends when the first "we" statement appears
- ANALYSIS_RATIO starts at the first "we" statement or statutory analysis
- FINAL_ORDER is the last 1-3 paragraphs before "JUDGE" lines

---

## OUTPUT FORMAT:

Return ONLY valid JSON with this exact structure:

```json
{
  "sections": [
    {"section_type": "HEADER_CORAM", "text": "extracted text"},
    {"section_type": "FACTS", "text": "extracted text"},
    {"section_type": "ARGUMENTS", "text": "extracted text"},
    {"section_type": "LEGAL_ISSUES", "text": "extracted text"},
    {"section_type": "ANALYSIS_RATIO", "text": "extracted text"},
    {"section_type": "FINAL_ORDER", "text": "extracted text"}
  ]
}
```"""

USER_PROMPT_TEMPLATE = """Parse this Pakistan Supreme Court judgment into the 6 sections.

JUDGMENT TEXT:
{judgment_text}

Return ONLY valid JSON with the exact structure shown above. No other text."""


def _extract_json_str(text: str) -> str:
    """Extract json block from raw response if formatted as markdown or surrounded by text."""
    cleaned = text.strip()
    if cleaned.startswith("```json"):
        cleaned = cleaned[7:]
    elif cleaned.startswith("```"):
        cleaned = cleaned[3:]
    if cleaned.endswith("```"):
        cleaned = cleaned[:-3]
    cleaned = cleaned.strip()

    first = cleaned.find("{")
    last = cleaned.rfind("}")
    if first != -1 and last != -1 and last >= first:
        return cleaned[first:last + 1]
    return cleaned


def _validate_llm_sections(sections_dict: Dict, source_text: str) -> bool:
    """
    Validates the structure and quality of sections extracted by the LLM.
    """
    if not isinstance(sections_dict, dict):
        logger.warning("LLM section output is not a dictionary.")
        return False

    sections = sections_dict.get("sections")
    if not isinstance(sections, list) or len(sections) == 0:
        logger.warning("LLM section output missing 'sections' list.")
        return False

    by_type = {}
    for sec in sections:
        if isinstance(sec, dict) and "section_type" in sec:
            by_type[sec["section_type"]] = sec.get("text", "") or ""

    # Ensure required sections exist
    for st in ["HEADER_CORAM", "FACTS", "FINAL_ORDER"]:
        if st not in by_type or not by_type[st].strip():
            logger.warning(f"LLM validation failed: Missing or empty critical section '{st}'.")
            return False

    final_order = by_type.get("FINAL_ORDER", "").lower()
    outcome_verbs = [
        "allowed", "dismissed", "set aside", "upheld", "disposed",
        "refused", "remanded", "bail", "order as to costs", "stands disposed",
        "partially allowed", "converted", "appeal succeeds", "petition fails"
    ]
    if not any(verb in final_order for verb in outcome_verbs):
        logger.warning("LLM validation warning: FINAL_ORDER does not contain a standard outcome verb.")
        # We don't necessarily hard-fail if there's substantial text, but log warning

    legal_issues = by_type.get("LEGAL_ISSUES", "")
    if legal_issues.strip():
        # Check if legal issues has question-like format
        has_question_format = any(w in legal_issues.lower() for w in ["whether", "question", "issue", "?"]) or bool(re.search(r"\([iIvVxX0-9]+\)", legal_issues))
        if not has_question_format:
            logger.warning("LLM validation warning: LEGAL_ISSUES does not appear to contain framed questions.")

    logger.info("LLM section extraction passed validation successfully.")
    return True


async def call_llm_section_classifier(text: str) -> Optional[Dict]:
    """
    Calls Groq LLM API to classify judgment text into 6 distinct sections.
    Returns parsed JSON dict with 'sections' or None if LLM call or validation fails.
    """
    api_key = settings.GROQ_API_KEY or os.getenv("GROQ_API_KEY", "")
    if not api_key:
        logger.warning("GROQ_API_KEY is not configured; skipping LLM section classification.")
        return None

    client = AsyncOpenAI(
        base_url=settings.GROQ_BASE_URL or "https://api.groq.com/openai/v1",
        api_key=api_key,
        max_retries=2,
    )

    model_name = settings.GROQ_MODEL or "llama-3.3-70b-versatile"
    
    # Trim judgment text if exceptionally long while preserving head and tail
    max_len = 75000
    if len(text) > max_len:
        trimmed_text = text[:45000] + "\n\n...[TRUNCATED FOR LENGTH]...\n\n" + text[-30000:]
    else:
        trimmed_text = text

    user_prompt = USER_PROMPT_TEMPLATE.format(judgment_text=trimmed_text)

    try:
        res = await client.chat.completions.create(
            model=model_name,
            temperature=0.0,
            timeout=45,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
        )
        content = res.choices[0].message.content or ""
    except Exception as err:
        logger.warning(f"Groq section classification call with json_object failed ({err}), retrying standard call...")
        try:
            res = await client.chat.completions.create(
                model=model_name,
                temperature=0.0,
                timeout=45,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt},
                ],
            )
            content = res.choices[0].message.content or ""
        except Exception as e:
            logger.error(f"Groq API error during section classification: {e}")
            return None

    if not content:
        logger.warning("Groq API returned empty response for section classification.")
        return None

    try:
        raw_json = _extract_json_str(content)
        parsed = json.loads(raw_json)
        if _validate_llm_sections(parsed, text):
            return parsed
        else:
            logger.warning("LLM sections failed validation checks.")
            return None
    except Exception as e:
        logger.error(f"Failed to parse LLM section classification JSON: {e}")
        return None


def _merge_llm_with_fallback(llm_result: Dict, fallback_result: Dict) -> Dict:
    """
    Merges LLM extraction results with rule-based fallback results.
    Prefers LLM sections where populated, and fills missing/empty sections from fallback.
    """
    merged_sections = []
    llm_by_type = {}
    if isinstance(llm_result, dict):
        for sec in llm_result.get("sections", []):
            if isinstance(sec, dict) and "section_type" in sec:
                llm_by_type[sec["section_type"]] = sec.get("text", "") or ""

    fallback_by_type = {}
    if isinstance(fallback_result, dict):
        for sec in fallback_result.get("sections", []):
            if isinstance(sec, dict) and "section_type" in sec:
                fallback_by_type[sec["section_type"]] = sec

    for st in SECTION_TYPES:
        llm_text = llm_by_type.get(st, "").strip()
        fb_sec = fallback_by_type.get(st, {})
        fb_text = (fb_sec.get("text") or "").strip()
        fb_heading = fb_sec.get("heading_found")

        if llm_text:
            merged_sections.append({
                "section_type": st,
                "heading_found": fb_heading if fb_heading else None,
                "text": llm_text,
                "confidence": 0.95,
            })
        else:
            logger.info(f"Section {st} empty in LLM result; using rule-based fallback.")
            merged_sections.append({
                "section_type": st,
                "heading_found": fb_heading,
                "text": fb_text,
                "confidence": fb_sec.get("confidence", 0.5),
            })

    return {
        "pdf_id": fallback_result.get("pdf_id", ""),
        "parse_mode": "llm_hybrid",
        "context_heading": fallback_result.get("context_heading", ""),
        "context_summary": fallback_result.get("context_summary", ""),
        "sections": merged_sections,
    }
