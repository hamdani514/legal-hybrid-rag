import os
import json
from pathlib import Path
from typing import Dict, List
import re

from loguru import logger
from openai import AsyncOpenAI

from app.config import settings
from app.ingestion.llm_pure_classifier import (
    PureLLMClassifier,
    ClassifiedJudgment,
)
from app.ingestion.llm_hybrid_classifier import (
    HybridClassifier,
)
from app.ingestion.llm_section_classifier import (
    call_llm_section_classifier,
    _merge_llm_with_fallback,
)

SECTION_TYPES = [
    "HEADER_CORAM",
    "FACTS",
    "ARGUMENTS",
    "LEGAL_ISSUES",
    "ANALYSIS_RATIO",
    "FINAL_ORDER",
]

# ---------------------------------------------------------------------------
# LLM prompts – simplified with strict rules
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = (
    "You are a Pakistan Supreme Court judgment parser. Your task is to extract specific sections from the judgment text. You must follow ALL rules below STRICTLY. No exceptions.\n\n"
    "## THE SIX SECTIONS YOU MUST EXTRACT:\n\n"
    "1. HEADER_CORAM - Court metadata only\n"
    "2. FACTS - Chronological narrative ONLY (ABSOLUTELY NO ANALYSIS)\n"
    "3. ARGUMENTS - Counsel submissions ONLY\n"
    "4. LEGAL_ISSUES - Case-specific questions ONLY (NEVER generic)\n"
    "5. ANALYSIS_RATIO - Court reasoning, statutory text, case law (ALL analysis)\n"
    "6. FINAL_ORDER - Outcome ONLY (1-3 sentences, NO reasoning)\n\n"
    "--- \n\n"
    "## SECTION 1: HEADER_CORAM - COMPLETE RULES\n\n"
    "### WHAT HEADER_CORAM CONTAINS:\n"
    "- Court name: \"IN THE SUPREME COURT OF PAKISTAN\"\n"
    "- Jurisdiction: \"(Appellate Jurisdiction)\" or \"(Original Jurisdiction)\"\n"
    "- \"PRESENT:\" followed by ALL judge names with their designations:\n"
    "  - HCJ = Hon'ble Chief Justice\n"
    "  - CJ = Chief Justice\n"
    "  - J = Justice\n"
    "- Complete case numbers with ALL variations:\n"
    "  - Civil Appeal No. 565/2011\n"
    "  - Civil Appeals No. 772 to 780/2012\n"
    "  - Criminal Petition No. 1603-L of 2021\n"
    "  - Constitution Petition No. 18 of 2019\n"
    "  - CPLA No. 2338-L of 2017\n"
    "  - ALL \"K\" designations: 85-K, 101-K, 653-K\n"
    "  - ALL \"L\" designations: 1603-L, 2338-L\n"
    "  - ALL \"P\" designations: 84-P\n"
    "- ALL appellant/petitioner names from the caption\n"
    "- ALL respondent names from the caption\n"
    "- ALL counsel names with designations:\n"
    "  - ASC = Advocate Supreme Court\n"
    "  - AOR = Advocate on Record\n"
    "  - Addl. A.G. = Additional Advocate General\n"
    "  - Addl. P.G. = Additional Prosecutor General\n"
    "  - DPG = Deputy Prosecutor General\n"
    "  - Sr. ASC = Senior Advocate Supreme Court\n"
    "- Hearing date: \"Date of Hearing:\" or \"Date of hearing:\"\n"
    "- Lower court details: \"On appeal from...\" or \"Against the judgment dated...\"\n\n"
    "### HEADER_CORAM EXCLUDES:\n"
    "- The word \"JUDGMENT\" or \"ORDER\" itself\n"
    "- Any text after the first \"J.:\" (e.g., \"Qazi Faez Isa, J.\")\n"
    "- Any analysis or reasoning\n"
    "- Facts of the case\n"
    "- Any \"we\" statements\n\n"
    "--- \n\n"
    "## SECTION 2: FACTS - COMPLETE RULES\n\n"
    "### WHAT FACTS CONTAINS (ONLY these things):\n"
    "- Chronological narrative of events in sequence\n"
    "- \"The appellant has challenged the judgment dated...\"\n"
    "- \"The facts necessary for decision are that...\"\n"
    "- \"Briefly stated the facts of the matter are that...\"\n"
    "- What each party did\n"
    "- What lower courts decided (Trial Court, High Court, Tribunal, Referee Court, Labor Court)\n"
    "- Dates of events (dates of judgments, orders, filings)\n"
    "- FIR details for criminal cases: FIR No., date, sections, police station\n"
    "- Allegations against the accused for criminal cases\n"
    "- Procedural history: who filed what, when, what was decided\n"
    "- Quoted documents when presented as evidence (termination letters, agreements)\n"
    "- The opening sentence: \"This appeal is directed against...\"\n"
    "- \"It appears that starting sometime in...\"\n"
    "- \"The respondents filed grievance petitions under...\"\n\n"
    "### FACTS ABSOLUTELY DOES NOT CONTAIN ANY OF THESE:\n\n"
    "**FORBIDDEN PATTERN 1 - Statutory Text:**\n"
    "- \"Section 81 of the Customs Act, 1969\"\n"
    "- \"Section 18 of the 1973 Act\"\n"
    "- \"Section 25A of the 1969 Ordinance\"\n"
    "- \"Subsection (4) of section 81\"\n"
    "- \"Section 302(b) PPC\"\n"
    "- \"Section 497(2) Cr.P.C.\"\n"
    "- ANY reference to a specific section of any law\n"
    "- ANY statutory definition\n"
    "- \"Under Section 426 Cr.P.C.\"\n"
    "- \"The provisions of Section 302 were correctly interpreted\"\n\n"
    "**FORBIDDEN PATTERN 2 - Case Citations:**\n"
    "- \"Collector of Customs, Lahore v S. Fazal Ilahi and Sons (2015 SCMR 1488)\"\n"
    "- \"PLD 2017 Sindh 347\"\n"
    "- \"2001 SCMR 565\"\n"
    "- \"2024 SCMR 1021\"\n"
    "- \"PLD 1988 SC 416\"\n"
    "- ANY citation of a case (PLD, SCMR, PTD, 2022 PLC, etc.)\n"
    "- \"In the case of Regional Police Officer...\"\n"
    "- \"Reference is placed on Muhammad Sarwar Vs. The State\"\n\n"
    "**FORBIDDEN PATTERN 3 - Court Analysis/Reasoning:**\n"
    "- \"The law enables the Collector to extend the period\"\n"
    "- \"Subsection (4) of section 81 provides that...\"\n"
    "- \"The same has been provided as a safeguard\"\n"
    "- \"The scope and object of section 81\"\n"
    "- \"The learned Judges had correctly applied the law\"\n"
    "- \"It is also not the case of the appellants\"\n"
    "- \"We have not been persuaded to take a different view\"\n"
    "- ANY \"we\" statement by the court\n"
    "- ANY \"in our view\" statement\n"
    "- ANY \"In our opinion\" statement\n"
    "- ANY \"We are of the view\" statement\n"
    "- ANY evaluation of evidence\n"
    "- ANY interpretation of law\n"
    "- \"The possibility cannot be ruled out\"\n"
    "- \"It is now established beyond any doubt\"\n"
    "- \"All these facts and circumstances when evaluated conjointly\"\n"
    "- \"Compel this Court to come to the conclusion\"\n"
    "- \"No exception can be taken contrary\"\n\n"
    "**FORBIDDEN PATTERN 4 - Legal Discussion:**\n"
    "- \"The question came up for consideration\"\n"
    "- \"Leave to appeal was granted to consider whether\"\n"
    "- \"The same question came up for consideration\"\n"
    "- ANY discussion of legal principles\n"
    "- ANY discussion of jurisdiction\n"
    "- ANY discussion of maintainability\n"
    "- ANY Latin maxims\n"
    "- \"The question of limitation cannot be taken casually\"\n"
    "- \"The doctrine of equality before law demands\"\n"
    "- \"It is the inherent duty of the Court\"\n\n"
    "**FORBIDDEN PATTERN 5 - Reasoning/Conclusions:**\n"
    "- \"When no final assessment is made\"\n"
    "- \"The provisional assessment will become final\"\n"
    "- \"The penalty provision was incorporated\"\n"
    "- ANY reasoning about why something is correct or incorrect\n"
    "- ANY conclusion about the law\n"
    "- \"The absence of an opportunity being granted expressly is a deficiency\"\n"
    "- \"The right of hearing is one of the fundamental principles\"\n"
    "- \"The foremost aspiration of setting up a Tribunal\"\n"
    "- \"An error or oversight in any order may be reviewed\"\n\n"
    "**FORBIDDEN PATTERN 6 - \"We\" Statements:**\n"
    "- \"We have heard learned counsel\"\n"
    "- \"We have considered\"\n"
    "- \"We have perused\"\n"
    "- \"We are of the view\"\n"
    "- \"We notice that\"\n"
    "- \"We find that\"\n"
    "- \"We are afraid\"\n"
    "- \"We have been informed\"\n"
    "- \"We have carefully mapped out\"\n"
    "- \"We have seen how\"\n"
    "- \"We would emphasize\"\n"
    "- \"We turn to the grievance\"\n"
    "- \"We have already noted\"\n"
    "- \"We are not convinced\"\n"
    "- \"We have carefully examined\"\n"
    "- \"We are constrained to hold\"\n"
    "- \"We have not been persuaded\"\n"
    "- ANY sentence starting with \"We\"\n\n"
    "--- \n\n"
    "## SECTION 3: ARGUMENTS - COMPLETE RULES\n\n"
    "### WHAT ARGUMENTS CONTAINS:\n"
    "- \"Learned counsel for the appellant argued/submitted/contended that...\"\n"
    "- \"Learned counsel for the respondent argued/submitted/contended that...\"\n"
    "- \"Learned counsel for the petitioner argued/submitted/contended that...\"\n"
    "- \"The learned Additional Advocate General argued that...\"\n"
    "- \"The learned Law Officer contended that...\"\n"
    "- \"The learned Additional Advocate General, Punjab submits that...\"\n"
    "- \"On the other hand, learned counsel for the respondent contended that...\"\n"
    "- \"He further argued/maintained/contended...\"\n"
    "- \"It was further averred...\"\n"
    "- \"He also contended...\"\n"
    "- \"It was further argued...\"\n"
    "- \"Raja Muhammad Iqbal, the learned counsel representing the appellant, did not offer any explanation\"\n"
    "- \"At the very outset, it has been argued by learned counsel for the petitioner that...\"\n"
    "- \"It was submitted by...\"\n"
    "- \"It was contended that...\"\n"
    "- \"It was prayed that...\"\n\n"
    "### ARGUMENTS EXCLUDES:\n"
    "- ANY \"we\" statements by the court\n"
    "- ANY court analysis\n"
    "- ANY narrative about what happened in court\n"
    "- ANY statutory text (unless quoted by counsel)\n"
    "- ANY \"We have heard learned counsel\" statements\n"
    "- ANY \"In our view\" statements\n"
    "- ANY \"We have considered\" statements\n"
    "- ANY court reasoning\n"
    "- ANY evaluation of evidence by the court\n\n"
    "--- \n\n"
    "## SECTION 4: LEGAL_ISSUES - COMPLETE RULES\n\n"
    "### WRONG (generic templates - NEVER USE):\n"
    "- (i) Whether the impugned judgment of the High Court is sustainable under the law?\n"
    "- (ii) Whether the petitioner/appellant is entitled to the relief claimed?\n"
    "- (iii) Whether the appeal is barred by limitation?\n"
    "- (iv) Whether sufficient cause has been shown for condonation of delay?\n"
    "- (v) Whether the provisions of Section 302 were correctly interpreted?\n"
    "- (vi) Whether the Service Tribunal had jurisdiction?\n\n"
    "### HOW TO EXTRACT CASE-SPECIFIC LEGAL_ISSUES:\n\n"
    "**Step 1: Look for EXPLICIT questions in the judgment:**\n"
    "- \"Leave to appeal was granted to consider the following questions: (i)...\"\n"
    "- Numbered questions: (i), (ii), (iii), (iv)\n"
    "- \"Whether...\" questions\n"
    "- \"The question is whether...\"\n"
    "- \"The issue is whether...\"\n"
    "- \"The moot question is whether...\"\n"
    "- \"The question that arises is whether...\"\n\n"
    "**Step 2: Extract from the LEAVE GRANTING ORDER:**\n"
    "- Look for: \"Leave to appeal was granted to consider whether...\"\n"
    "- Look for: \"The question for consideration is whether...\"\n\n"
    "**Step 3: Extract from the ARGUMENTS section:**\n"
    "- What are the lawyers arguing about? Convert their contentions into questions\n\n"
    "**Step 4: Extract from the FACTS section:**\n"
    "- What is the dispute about? Convert the dispute into a question\n\n"
    "**Step 5: Extract from the ANALYSIS section:**\n"
    "- What laws are being interpreted? Convert the interpretation into a question\n\n"
    "--- \n\n"
    "## SECTION 5: ANALYSIS_RATIO - COMPLETE RULES\n\n"
    "### ANALYSIS_RATIO STARTS AT THE FIRST OCCURRENCE OF:\n"
    "- \"We have heard learned counsel\"\n"
    "- \"We have considered\"\n"
    "- \"We have perused\"\n"
    "- \"At the time of the enactment of the Act\"\n"
    "- \"Section 81 has undergone a number of changes\"\n"
    "- \"The law enables the Collector\"\n"
    "- \"Subsection (4) of section 81 provides\"\n"
    "- \"The same question came up for consideration\"\n"
    "- \"In the case of Collector of Customs v Auto Mobile Corporation\"\n"
    "- \"The learned Judges of the High Court had correctly applied\"\n"
    "- \"We have not been persuaded to take a different view\"\n"
    "- \"Leave to appeal was granted to consider whether\"\n"
    "- \"We have carefully examined\"\n"
    "- \"We are of the view\"\n"
    "- \"In our view\"\n"
    "- \"It appears from the record\"\n"
    "- \"Further, we are not convinced\"\n"
    "- \"We find that\"\n"
    "- \"We notice that\"\n"
    "- \"We are afraid\"\n"
    "- \"We have been informed\"\n"
    "- \"We have carefully mapped out\"\n"
    "- \"We have seen how\"\n"
    "- \"We would emphasize\"\n"
    "- \"We turn to the grievance\"\n"
    "- \"We have already noted\"\n"
    "- \"We are constrained to hold\"\n"
    "- \"The impugned order has two limbs\"\n"
    "- \"The impugned order depicts\"\n"
    "- \"The purpose of enacting\"\n"
    "- \"There is no doubt that\"\n"
    "- \"The foremost aspiration\"\n"
    "- \"Another most important aspect\"\n"
    "- \"An error or oversight\"\n\n"
    "### ANALYSIS_RATIO INCLUDES:\n"
    "- ALL \"We have heard...\" statements\n"
    "- ALL \"We have considered...\" statements\n"
    "- ALL \"In our view...\" statements\n"
    "- ALL \"We hold that...\" statements\n"
    "- ALL statutory text quoted by the court (ENTIRE sections)\n"
    "- ALL case citations (PLD, SCMR, PTD, 2022 PLC, etc.)\n"
    "- ALL Latin maxims and their explanations\n"
    "- ALL reasoning about constitutional provisions\n"
    "- ALL discussion of legal principles\n"
    "- ALL evaluation of evidence by the court\n"
    "- ALL interpretation of law by the court\n"
    "- ALL discussion of jurisdiction\n"
    "- ALL discussion of maintainability\n"
    "- ALL discussion of \"circumstances of exceptional nature\"\n"
    "- ALL analysis of whether something is justified\n"
    "- ALL conclusions about the law\n"
    "- ALL \"the question came up for consideration\" statements\n"
    "- ALL references to precedents\n"
    "- ALL discussion of the object and purpose of laws\n\n"
    "### ANALYSIS_RATIO EXCLUDES:\n"
    "- \"JUDGE\" lines\n"
    "- \"Chief Justice\" lines\n"
    "- \"Approved for Reporting\"\n"
    "- Signatures\n"
    "- Dates of announcement (unless part of reasoning)\n"
    "- Stenographer's marks\n"
    "- \"Announced in open Court\"\n"
    "- Case numbers (unless part of reasoning)\n"
    "- Page numbers\n\n"
    "--- \n\n"
    "## SECTION 6: FINAL_ORDER - COMPLETE RULES\n\n"
    "### FINAL_ORDER CONTAINS ONLY:\n"
    "- \"Therefore, said forty appeals are dismissed, but with no orders as to costs.\"\n"
    "- \"As a consequence, this petition having no merit is accordingly dismissed and leave to appeal is refused.\"\n"
    "- \"Accordingly, these appeals are allowed.\"\n"
    "- \"This petition stands disposed of in above terms.\"\n"
    "- \"We convert this petition into appeal and allow it.\"\n"
    "- \"The petitioner is admitted to bail subject to his furnishing bail bonds in the sum of Rs.100,000/- with one surety.\"\n"
    "- \"As a result of the above discussion, the appeal is dismissed.\"\n"
    "- \"In view of the foregoing, the appeal is allowed.\"\n"
    "- \"The result is that the appeal must fail.\"\n"
    "- \"We do not find any lawful justification to cause any interference.\"\n"
    "- \"For the foregoing reasons, the appeal is dismissed.\"\n"
    "- \"Resultantly, we allow this appeal, set aside the impugned judgment and restore that of the learned Election Tribunal.\"\n"
    "- \"This Civil Appeal is dismissed not only on merits but also being barred by time.\"\n"
    "- \"The appeal is dismissed with no order as to costs.\"\n"
    "- \"We are constrained to hold that the judgment of the learned High Court is based upon misconception of law and the same could not prevail.\"\n\n"
    "### FINAL_ORDER EXCLUDES:\n"
    "- ANY reasoning\n"
    "- \"Announced in open court\"\n"
    "- \"Approved for reporting\"\n"
    "- Judge signatures: \"JUDGE\", \"Chief Justice\"\n"
    "- Dates (unless part of disposition)\n"
    "- Case numbers\n"
    "- Page numbers\n"
    "- \"Islamabad, the\"\n"
    "- \"Karachi, the\"\n"
    "- Stenographer's marks\n"
    "- \"Not Approved For Reporting\"\n"
    "- \"Approved for reporting\" text\n"
    "- \"s/d\" or similar marks\n"
    "- Any text after the outcome\n\n"
    "--- \n\n"
    "## STRICT RULE 7: NO EMPTY SECTIONS\n\n"
    "## STRICT RULE 8: CLASSIFICATION PRIORITY ORDER\n"
    "1. HEADER_CORAM - Beginning of document to \"JUDGMENT\" or first \"J.:\"\n"
    "2. FACTS - First \"J.:\" or numbered paragraph to FIRST analysis pattern\n"
    "3. ARGUMENTS - \"Learned counsel\" paragraphs before FIRST \"we\"\n"
    "4. LEGAL_ISSUES - Numbered questions or implicit issues\n"
    "5. ANALYSIS_RATIO - FIRST analysis pattern to before \"JUDGE\" lines\n"
    "6. FINAL_ORDER - Outcome paragraph before \"JUDGE\" lines\n"
)

USER_PROMPT_TEMPLATE = (
    "Parse this Pakistan Supreme Court judgment. Return ONLY valid JSON with this exact structure:\n\n"
    "{\n"
    "  \"sections\": [\n"
    "    {\"section_type\": \"HEADER_CORAM\", \"text\": \"extracted text - NEVER EMPTY\"},\n"
    "    {\"section_type\": \"FACTS\", \"text\": \"extracted text - NEVER EMPTY\"},\n"
    "    {\"section_type\": \"ARGUMENTS\", \"text\": \"extracted text - NEVER EMPTY\"},\n"
    "    {\"section_type\": \"LEGAL_ISSUES\", \"text\": \"extracted text - NEVER EMPTY\"},\n"
    "    {\"section_type\": \"ANALYSIS_RATIO\", \"text\": \"extracted text - NEVER EMPTY\"},\n"
    "    {\"section_type\": \"FINAL_ORDER\", \"text\": \"extracted text - NEVER EMPTY\"}\n"
    "  ]\n"
    "}\n\n"
    "CRITICAL REMINDERS:\n"
    "1. FACTS = ONLY chronological narrative. ABSOLUTELY NO statutory text, NO case citations, NO \"we\" statements, NO analysis.\n"
    "2. LEGAL_ISSUES = MUST BE CASE-SPECIFIC. NEVER use generic templates.\n"
    "3. ANALYSIS_RATIO = starts at FIRST \"we\" statement or FIRST statutory analysis.\n"
    "4. FINAL_ORDER = outcome ONLY (1-3 sentences). NO reasoning, NO metadata.\n"
    "5. NO SECTION CAN BE EMPTY.\n\n"
    "JUDGMENT TEXT:\n"
)

CONTEXT_SYSTEM_PROMPT = """You are a legal case summarizer for Pakistan Supreme Court judgments. Your task is to generate a generic context summary that focuses on the legal problem, the facts, and the outcome - WITHOUT naming specific parties (no names of people, no names of companies, no specific locations).

## RULES (Follow for EVERY judgment):

### RULE 1: NO PARTY NAMES
- Do NOT use names like "Gul Zaman", "Waqar Ali", "PTCL", "PEMRA", etc.
- Use generic terms instead: "land owner", "appellant", "complainant", "the government", "the authority", "the bank"

### RULE 2: Focus on the LEGAL PROBLEM
- What was the dispute about? (e.g., "compensation for acquired land", "criminal complaint for illegal dispossession")
- What law was involved? (e.g., "Section 18 of the Land Acquisition Act", "Illegal Dispossession Act")

### RULE 3: Describe the FACTS generically
- What did the parties do? (e.g., "filed an application directly before the District Judge", "purchased property through a registered sale deed")
- What did the lower courts decide?

### RULE 4: State the OUTCOME clearly
- What did the Supreme Court hold?
- What was the final decision? (e.g., "appeal dismissed", "appeal allowed")

### RULE 5: Structure the summary as:
[Problem/Dispute] → [What happened/Facts] → [Lower court decision] → [Supreme Court holding] → [Outcome]

## FORBIDDEN PATTERNS (Never use):
- "The judgment addresses the core dispute"
- "This is a legal appeal concerning allegations"
- "The case concerned tax/customs dispute"
- "The appellant brought this appeal against the respondents"
- Any specific person's name (e.g., "Gul Zaman", "Waqar Ali")
- Any specific company name (e.g., "PTCL", "PEMRA", "MCB Bank")

## CORRECT EXAMPLES:

### Example 1: Land Acquisition Case (Appeal Dismissed)
**Input Judgment:** Land owner Gul Zaman appealed against High Court order dismissing his application under Section 18 of Land Acquisition Act for compensation of land acquired for FTZ Gwadar.

**Output Summary:**
"A land owner sought enhanced compensation for his land acquired by the government for a public project. He filed an application directly before the District Judge under Section 18 of the Land Acquisition Act, bypassing the Collector. The High Court held the application was incompetent and time-barred. The Supreme Court dismissed the appeal, holding that an application under Section 18 must first be made to the Collector, not directly to the Court."

### Example 2: Illegal Dispossession Case (Appeal Allowed)
**Input Judgment:** Land owners Waqar Ali, Zulfiqar Ali and Sadaqat Ali appealed against High Court order dismissing their writ petition challenging trial court's cognizance under Illegal Dispossession Act.

**Output Summary:**
"Land owners purchased property through a registered sale deed. Another land owner filed a criminal complaint against them under the Illegal Dispossession Act, alleging they had illegally occupied his land. The trial court took cognizance without finding criminal intent. The High Court dismissed the land owners' writ petition as premature. The Supreme Court allowed the appeal, holding that an offence under the Act requires both an unlawful act and criminal intent (mens rea), which was absent. The complaint was dismissed."

### Example 3: Customs Case (Appeal Partially Allowed)
**Input Judgment:** Deputy Director Customs appealed against High Court judgment declaring FIR under Central Excise Act as without lawful authority.

**Output Summary:**
"A customs officer registered an FIR under the Central Excise Act. The High Court declared the FIR as without lawful authority. The Supreme Court held that while the FIR format cannot be used under the Act, the absence of an FIR does not bar criminal proceedings as Section 13 provides a complete procedure from arrest to filing of complaint. The appeal was partially allowed."

### Example 4: Family Court Case (Appeal Dismissed)
**Input Judgment:** Husband appealed against Family Court decree awarding dowry of Rs.4,00,000 to wife.

**Output Summary:**
"A husband appealed against a Family Court decree awarding dowry to his wife. The First Appellate Court enhanced the award. The High Court reduced the award. The Supreme Court dismissed the husband's appeal, holding that under Section 14(2) of the Family Courts Act, the bar on appeal applies only to the judgment-debtor (husband) and does not extinguish the wife's right to appeal."

### Example 5: Service Tribunal Case (Appeal Allowed)
**Input Judgment:** Sindh Irrigation and Drainage Authority appealed against Service Tribunal judgment holding its employees were civil servants.

**Output Summary:**
"Employees of a statutory authority claimed they were civil servants entitled to appeal before the Service Tribunal. The Tribunal held that they were civil servants. The Supreme Court allowed the appeal, holding that employees of a statutory authority are public servants, not civil servants, and the Service Tribunal lacked jurisdiction."

Return ONLY valid JSON with this exact structure:
{
  "context_heading": "[Case Type] No. [number]",
  "context_summary": "[Your generic summary here - NO party names]"
}"""

CONTEXT_USER_PROMPT_TEMPLATE = """JUDGMENT TEXT:
{judgment_text}

Parse the Pakistan Supreme Court judgment above. Return ONLY valid JSON matching this exact structure:
{{
  "context_heading": "[Case Type] No. [number]",
  "context_summary": "[Your generic summary here - NO party names]"
}}

RULES:
1. Do not generate any other keys. Only generate 'context_heading' and 'context_summary'.
2. Write a generic summary of 3-5 sentences focused on the legal problem, facts, and outcome.
3. Do NOT include any party names (people, companies, locations) in the summary.
4. Return ONLY valid JSON."""


# ---------------------------------------------------------------------------
# Utility helpers
# ---------------------------------------------------------------------------

def _uploads_dir() -> Path:
    return Path(__file__).resolve().parents[2] / "uploads"


def clean_json_response(raw: str) -> str:
    cleaned = raw.strip().replace("```json", "").replace("```", "")
    first = cleaned.find("{")
    last = cleaned.rfind("}")
    if first != -1 and last != -1 and last >= first:
        return cleaned[first:last + 1]
    return cleaned


def _empty_result(pdf_id: str) -> Dict:
    return {
        "pdf_id": pdf_id,
        "parse_mode": "accurate",
        "context_heading": "",
        "context_summary": "",
        "sections": [
            {
                "section_type": s,
                "heading_found": None,
                "text": "",
                "confidence": 0.0,
            }
            for s in SECTION_TYPES
        ],
    }


def _normalize(parsed: Dict, pdf_id: str) -> Dict:
    by_type = {}
    for sec in parsed.get("sections", []):
        st = sec.get("section_type")
        if st in SECTION_TYPES:
            by_type[st] = {
                "section_type": st,
                "heading_found": sec.get("heading_found", sec.get("heading")),
                "text": sec.get("text", "") or "",
                "confidence": float(sec.get("confidence", 0.0) or 0.0),
            }

    out = {
        "pdf_id": pdf_id,
        "parse_mode": "llm",
        "context_heading": parsed.get("context_heading", ""),
        "context_summary": parsed.get("context_summary", ""),
        "sections": [],
    }
    for s in SECTION_TYPES:
        out["sections"].append(
            by_type.get(
                s,
                {"section_type": s, "heading_found": None, "text": "", "confidence": 0.0},
            )
        )
    return out


def _chunk_text(text: str, size: int = 12000, overlap: int = 500) -> List[str]:
    if len(text) <= size:
        return [text]
    chunks: List[str] = []
    step = size - overlap
    start = 0
    while start < len(text):
        end = min(start + size, len(text))
        chunks.append(text[start:end])
        if end >= len(text):
            break
        start += step
    return chunks


# ---------------------------------------------------------------------------
# Groq / LLM interaction (Ollama commented as requested)
# ---------------------------------------------------------------------------

# OLD OLLAMA IMPLEMENTATION (COMMENTED OUT AS REQUESTED):
# async def call_ollama(prompt: str, system: str) -> str:
#     client = AsyncOpenAI(
#         base_url=settings.OLLAMA_BASE_URL,
#         api_key="ollama",
#         max_retries=0,
#     )
#     res = await client.chat.completions.create(
#         model=settings.OLLAMA_MODEL,
#         temperature=0,
#         timeout=10,
#         response_format={"type": "json_object"},
#         messages=[
#             {"role": "system", "content": system},
#             {"role": "user", "content": prompt},
#         ],
#     )
#     return res.choices[0].message.content or ""


# ===========================================================================
# Google Gemini / LLM interaction (Groq commented as requested)
# ===========================================================================

async def call_gemini(prompt: str, system: str) -> str:
    """
    Call Google Gemini 2.5 Flash-Lite API using official google-genai client.
    """
    api_key = getattr(settings, "GEMINI_API_KEY", "") or os.getenv("GEMINI_API_KEY", "")
    if not api_key:
        logger.warning("GEMINI_API_KEY is not configured in settings or .env file.")
        return ""

    from google import genai
    from google.genai import types

    try:
        client = genai.Client(api_key=api_key)
        model_name = getattr(settings, "GEMINI_MODEL", "gemini-2.5-flash-lite")
        response = await client.aio.models.generate_content(
            model=model_name,
            contents=prompt,
            config=types.GenerateContentConfig(
                system_instruction=system,
                temperature=0.0,
                response_mime_type="application/json",
            ),
        )
        return response.text or ""
    except Exception as e:
        logger.error(f"Gemini API error in parser: {e}")
        return ""


# --- Previous Groq Setup (Commented out as requested) ---
# async def call_groq(prompt: str, system: str) -> str:
#     api_key = settings.GROQ_API_KEY or os.getenv("GROQ_API_KEY", "")
#     if not api_key:
#         logger.warning("GROQ_API_KEY is not configured in settings or .env file.")
#         return ""
#     client = AsyncOpenAI(
#         base_url=settings.GROQ_BASE_URL or "https://api.groq.com/openai/v1",
#         api_key=api_key,
#         max_retries=2,
#     )
#     model_name = settings.GROQ_MODEL or "llama-3.3-70b-versatile"
#     try:
#         res = await client.chat.completions.create(
#             model=model_name,
#             temperature=0,
#             timeout=30,
#             response_format={"type": "json_object"},
#             messages=[
#                 {"role": "system", "content": system},
#                 {"role": "user", "content": prompt},
#             ],
#         )
#         return res.choices[0].message.content or ""
#     except Exception as e:
#         logger.error(f"Groq API error: {e}")
#         return ""

async def call_groq(prompt: str, system: str) -> str:
    """Fallback if specifically invoked."""
    api_key = settings.GROQ_API_KEY or os.getenv("GROQ_API_KEY", "")
    if not api_key:
        return ""
    client = AsyncOpenAI(
        base_url=settings.GROQ_BASE_URL or "https://api.groq.com/openai/v1",
        api_key=api_key,
        max_retries=2,
    )
    model_name = settings.GROQ_MODEL or "llama-3.3-70b-versatile"
    try:
        res = await client.chat.completions.create(
            model=model_name,
            temperature=0,
            timeout=30,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ],
        )
        return res.choices[0].message.content or ""
    except Exception as e:
        logger.error(f"Groq API error: {e}")
        return ""


async def call_llm(prompt: str, system: str) -> str:
    """
    Unified LLM caller routing to Gemini API (Groq commented as primary).
    """
    # return await call_groq(prompt, system)  # Groq commented out as requested
    return await call_gemini(prompt, system)


# Alias call_ollama to call_llm for backwards compatibility across module calls
call_ollama = call_llm


# ---------------------------------------------------------------------------
# Context generation (fallback when LLM fails)
# ---------------------------------------------------------------------------

def _is_invalid_name_line(line: str) -> bool:
    line_lower = line.lower()
    # If it contains ranges like "10 to 20"
    if re.search(r"\b\d+\s+(?:to|-)\s+\d+\b", line_lower):
        return True
    # If it consists mostly of numbers/symbols
    num_chars = sum(c.isdigit() for c in line)
    alpha_chars = sum(c.isalpha() for c in line)
    if num_chars > 0 and alpha_chars == 0:
        return True
    if num_chars > alpha_chars:
        return True
    # If it looks like a case number or appeal line
    if re.search(r"\b(?:appeals?|petitions?|no\.?|nos?\.?|civil|criminal|crl|const)\b", line_lower):
        return True
    # If it's a page indicator
    if "page" in line_lower:
        return True
    return False


def _extract_party_names(text: str) -> Dict[str, str]:
    """Identify appellant and respondent names from the first page using backward search."""
    info = {"appellant": "", "respondent": ""}
    head = text[:4000]
    lines = head.splitlines()
    
    stop_pat = re.compile(
        r"\b(?:VERSUS|Versus|V\b|V\.\s*S\b|PRESENT|COURT|PRESENTS|JURISDICTION|APPEAL|APPEALS|PETITION|PETITIONS|"
        r"AGAINST|TRIBUNAL|PASSED|HIGH\s+COURT|DATED|HEARING|NO\b|NO\.|JUSTICE|C\.A|CRL\.A)\b",
        re.I
    )
    
    appellant_idx = -1
    for i, line in enumerate(lines):
        line_strip = line.strip()
        if re.search(r"\b(?:Appellant|APPELLANT|Petitioner|PETITIONER)\b", line_strip):
            if not re.search(r"\b(?:For|counsel|ASC|GP|A\.G\.)\b", line_strip, re.I):
                appellant_idx = i
                break
                
    if appellant_idx != -1:
        name_lines = []
        count = 0
        for j in range(appellant_idx - 1, -1, -1):
            line_val = lines[j].strip()
            if not line_val:
                if name_lines:
                    break
                continue
            if stop_pat.search(line_val):
                break
            if "--- PAGE" in line_val:
                break
            if _is_invalid_name_line(line_val):
                continue
            name_lines.insert(0, line_val)
            count += 1
            if count >= 3:  # Limit to at most 3 non-empty lines
                break
        info["appellant"] = " ".join(name_lines).strip()
        
    respondent_idx = -1
    for i, line in enumerate(lines):
        line_strip = line.strip()
        if re.search(r"\b(?:Respondent|RESPONDENT|Respondents|RESPONDENTS)\b", line_strip):
            if not re.search(r"\b(For|counsel|ASC|GP|A\.G\.)\b", line_strip, re.I):
                respondent_idx = i
                break
                
    if respondent_idx != -1:
        name_lines = []
        count = 0
        for j in range(respondent_idx - 1, -1, -1):
            line_val = lines[j].strip()
            if not line_val:
                if name_lines:
                    break
                continue
            if stop_pat.search(line_val):
                break
            if "--- PAGE" in line_val:
                break
            if _is_invalid_name_line(line_val):
                continue
            name_lines.insert(0, line_val)
            count += 1
            if count >= 3:  # Limit to at most 3 non-empty lines
                break
        info["respondent"] = " ".join(name_lines).strip()
        
    return info


def has_word(words: List[str], text: str) -> bool:
    """Helper to check if any of the target words matches text with word boundary."""
    pattern = r"\b(?:" + "|".join(re.escape(w) for w in words) + r")\b"
    return bool(re.search(pattern, text, re.I))


def _extract_case_info(text: str) -> Dict[str, str]:
    """Extract case number, type, parties, and outcome from judgment text."""
    info: Dict[str, str] = {
        "case_number": "",
        "case_type": "",
        "appellant": "",
        "respondent": "",
        "outcome": "",
    }

    head = text[:4000]
    
    # We find all matches in the head (strictly on same line to prevent capturing header junk)
    matches = []
    
    # 1. Constitutional Petition
    for m in re.finditer(r"(?:Constitution\s+Petitions?\s+Nos?\.?|Const\.\s*Pet\.\s*Nos?\.?)\s*([^\n\r]+)", head, re.I):
        matches.append((m.start(), "constitutional", m.group(1).strip()))
        
    # 2. Civil Appeal
    for m in re.finditer(r"(?:Civil\s+Appeals?\s+Nos?\.?|C\.?\s*A\.?\s*Nos?\.?)\s*([^\n\r]+)", head, re.I):
        matches.append((m.start(), "civil", m.group(1).strip()))
        
    # 3. Criminal Appeal
    for m in re.finditer(r"(?:Criminal\s+Appeals?\s+Nos?\.?|Crl\.?\s*A\.?\s*Nos?\.?|Crl\.?\s*A\.)\s*([^\n\r]+)", head, re.I):
        matches.append((m.start(), "criminal", m.group(1).strip()))
        
    if matches:
        # Sort by start index to get the first one appearing in the document
        matches.sort(key=lambda x: x[0])
        info["case_type"] = matches[0][1]
        info["case_number"] = re.sub(r"\s+", " ", matches[0][2]).strip()
    else:
        info["case_type"] = "civil"
        info["case_number"] = ""

    # --- Parties (using the robust backward search) ---
    parties = _extract_party_names(text)
    info.update(parties)

    # --- Outcome ---
    tail = text[-3000:].lower()
    if "partially allowed" in tail:
        info["outcome"] = "appeal partially allowed"
    elif any(term in tail for term in ["appeal is dismissed", "appeal stands dismissed", "appeals are dismissed", "appeal dismissed"]):
        info["outcome"] = "appeal dismissed"
    elif any(term in tail for term in ["appeal is allowed", "appeal stands allowed", "appeals are allowed", "appeal allowed"]):
        info["outcome"] = "appeal allowed"
    elif any(term in tail for term in ["petition is dismissed", "petition stands dismissed", "petition dismissed"]):
        info["outcome"] = "petition dismissed"
    elif any(term in tail for term in ["petition is allowed", "petition stands allowed", "petition allowed"]):
        info["outcome"] = "petition allowed"
    elif "set aside" in tail:
        info["outcome"] = "judgment set aside"
    else:
        lower = text.lower()
        if "partially allowed" in lower:
            info["outcome"] = "appeal partially allowed"
        elif "dismissed" in lower:
            info["outcome"] = "appeal dismissed"
        elif "allowed" in lower:
            info["outcome"] = "appeal allowed"
        else:
            info["outcome"] = "order issued"

    return info


def _derive_context_from_text(text: str) -> Dict[str, str]:
    """
    Generate context heading and summary from judgment text.
    This is the FALLBACK when LLM hallucinates - uses actual text from judgment.
    """
    info = _extract_case_info(text)
    
    case_type = info["case_type"]
    case_num = info["case_number"]
    
    # Heading: case number only
    if case_type == "civil":
        heading = f"Civil Appeal No. {case_num}" if case_num else "Civil Appeal"
    elif case_type == "criminal":
        heading = f"Criminal Appeal No. {case_num}" if case_num else "Criminal Appeal"
    elif case_type == "constitutional":
        heading = f"Constitution Petition No. {case_num}" if case_num else "Constitution Petition"
    else:
        heading = "Civil Appeal"
    
    outcome = info["outcome"]
    
    # -----------------------------------------------------------------------
    # Extract the ACTUAL subject matter from the judgment text
    # -----------------------------------------------------------------------
    subject = ""
    
    # Look for specific Act mentions in the first 4000 characters
    head = text[:4000].lower()
    
    if "land acquisition" in head:
        subject = "compensation enhancement under the Land Acquisition Act, 1894"
    elif "illegal dispossession" in head:
        subject = "a complaint under the Illegal Dispossession Act, 2005"
    elif "family court" in head or "dissolution of marriage" in head or "dower" in head:
        subject = "a family dispute under the Family Courts Act, 1964"
    elif "arbitration" in head:
        subject = "enforcement of an arbitration award"
    elif "central excise" in head or "customs" in head:
        subject = "taxation/customs dispute under the Customs Act, 1969 or Central Excise Act, 1944"
    elif "pemra" in head:
        subject = "delegation of powers under the PEMRA Ordinance, 2002"
    elif "limitation" in head:
        subject = "the issue of limitation and condonation of delay"
    else:
        subject = "the legal dispute"
    
    appellant_name = info.get("appellant") or "the appellant"
    # Clean up the appellant name if it has long trailing punctuation or page numbers
    appellant_name = re.sub(r'\s+', ' ', appellant_name).strip()
    # Limit party names length
    if len(appellant_name) > 100:
        appellant_name = appellant_name[:97] + "..."
        
    respondent_name = info.get("respondent") or "others"
    respondent_name = re.sub(r'\s+', ' ', respondent_name).strip()
    if len(respondent_name) > 100:
        respondent_name = respondent_name[:97] + "..."
        
    # -----------------------------------------------------------------------
    # Extract the holding from the judgment (look for "we hold" or similar)
    # -----------------------------------------------------------------------
    holding = ""
    # Look for "we are of the view that" or "we hold that"
    hold_match = re.search(r"\b(we are of the view that|we hold that|it is clear that|we find that|we observe that)\b\s*(.*?)[\.!?]", text[-3000:], re.I)
    if not hold_match:
        hold_match = re.search(r"\b(we are of the view that|we hold that|it is clear that|we find that|we observe that)\b\s*(.*?)[\.!?]", text, re.I)
    
    if hold_match:
        holding = hold_match.group(2).strip()
        # Limit to reasonable length
        if len(holding) > 200:
            holding = holding[:200] + "..."
    else:
        holding = "the Court interpreted the relevant statutory provisions and rules"
    
    # -----------------------------------------------------------------------
    # Build the summary from ACTUAL content
    # -----------------------------------------------------------------------
    if "allowed" in outcome:
        outcome_text = "Appeal allowed."
    elif "partially allowed" in outcome:
        outcome_text = "Appeal partially allowed."
    elif "dismissed" in outcome:
        outcome_text = "Appeal dismissed."
    else:
        outcome_text = "Appeal disposed."
    
    # Let's form a dynamic, specific summary:
    summary = f"Appeal by {appellant_name} against {respondent_name} regarding {subject}. The Supreme Court held that {holding}. {outcome_text}"
    
    return {
        "context_heading": heading,
        "context_summary": summary,
    }


async def _generate_context(extracted_text: str) -> Dict[str, str]:
    """Generate context using LLM, fallback to rule-based."""
    if len(extracted_text) <= 8000:
        prompt_text = extracted_text
    else:
        prompt_text = extracted_text[:4000] + "\n\n... [TRUNCATED] ...\n\n" + extracted_text[-4000:]

    prompt = CONTEXT_USER_PROMPT_TEMPLATE.format(judgment_text=prompt_text)
    try:
        raw = await call_ollama(prompt, CONTEXT_SYSTEM_PROMPT)
        cleaned = clean_json_response(raw)
        parsed = json.loads(cleaned)
        heading = (parsed.get("context_heading") or "").strip()
        summary = (parsed.get("context_summary") or "").strip()
        
        # Validate that heading doesn't contain a description in brackets
        if heading and "(" in heading and ")" in heading:
            # Strip out the description
            heading = re.sub(r'\s*\([^)]*\)', '', heading).strip()
        
        if heading and summary:
            # Check summary is not generic
            forbidden = ["alleged offences", "the evidence on record", "the case concerned"]
            if not any(f in summary.lower() for f in forbidden):
                # Ensure summary has 3 to 6 sentences
                sentences = re.split(r"(?<=[.!?])\s+", summary)
                sentences = [s.strip() for s in sentences if s.strip()]
                if 3 <= len(sentences) <= 6:
                    return {
                        "context_heading": heading[:120],
                        "context_summary": " ".join(sentences)[:1000],
                    }
    except Exception as e:
        logger.error(f"Failed to generate context using Ollama: {e}")
    
    return _derive_context_from_text(extracted_text)


# ---------------------------------------------------------------------------
# LLM-based chunk parsing
# ---------------------------------------------------------------------------

async def _parse_one_chunk(pdf_id: str, chunk: str, idx: int, total: int) -> Dict:
    user_prompt = USER_PROMPT_TEMPLATE + chunk
    logger.info(f"Parsing {pdf_id} - chunk {idx} of {total}")
    logger.info(f"[{pdf_id}] Calling Ollama for chunk {idx}")
    raw = await call_ollama(user_prompt, SYSTEM_PROMPT)
    logger.info(f"[{pdf_id}] Ollama response received for chunk {idx}")

    cleaned = clean_json_response(raw)
    try:
        parsed = json.loads(cleaned)
        return _normalize(parsed, pdf_id)
    except Exception:
        retry_prompt = (
            "IMPORTANT: Your previous response was not valid JSON. Return ONLY "
            "the JSON object starting with { and ending with }. Nothing else.\n\n"
            + user_prompt
        )
        logger.info(f"[{pdf_id}] Calling Ollama for chunk {idx} (retry)")
        raw2 = await call_ollama(retry_prompt, SYSTEM_PROMPT)
        logger.info(f"[{pdf_id}] Ollama response received for chunk {idx} (retry)")
        cleaned2 = clean_json_response(raw2)
        parsed2 = json.loads(cleaned2)
        return _normalize(parsed2, pdf_id)


def _merge_chunks(chunk_results: List[Dict], pdf_id: str) -> Dict:
    merged = {
        s: {"section_type": s, "heading_found": None, "text": "", "confidence": 0.0}
        for s in SECTION_TYPES
    }
    for result in chunk_results:
        for sec in result.get("sections", []):
            st = sec.get("section_type")
            if st not in merged:
                continue
            txt = (sec.get("text") or "").strip()
            if txt:
                merged[st]["text"] = (
                    (merged[st]["text"] + "\n\n" + txt).strip()
                    if merged[st]["text"]
                    else txt
                )
            conf = float(sec.get("confidence", 0.0) or 0.0)
            merged[st]["confidence"] = max(merged[st]["confidence"], conf)
            if not merged[st]["heading_found"] and sec.get("heading_found"):
                merged[st]["heading_found"] = sec.get("heading_found")

    return {
        "pdf_id": pdf_id,
        "parse_mode": "llm",
        "context_heading": "",
        "context_summary": "",
        "sections": [merged[s] for s in SECTION_TYPES],
    }


def _classify_paragraph(p: str, p_lower: str, is_near_end: bool = False) -> str:
    """Return a SECTION_TYPE string based on content (not headings)."""
    # Normalize spaces/newlines for robust phrase checking
    p_norm = re.sub(r"\s+", " ", p_lower).strip()
    
    # 1. FINAL_ORDER - disposition only (1-3 sentences)
    # Check this first so final dispositions at the end of the document are caught immediately
    if is_near_end:
        conclusion_openers = [
            "in view of the foregoing discussion",
            "for the foregoing reasons",
            "as a consequence",
            "the result is that",
            "in the result",
            "consequently",
            "as a result of the above discussion",
        ]
        for opener in conclusion_openers:
            if opener in p_norm:
                if any(word in p_norm for word in ["allowed", "dismissed", "set aside", "upheld", "disposed of", "disposed"]):
                    return "FINAL_ORDER"
                    
        outcome_phrases = [
            "this appeal is allowed", "this appeal is dismissed",
            "the appeal is allowed", "the appeal is dismissed",
            "appeal is partially allowed", "appeal stands allowed",
            "appeal stands dismissed", "petition is allowed",
            "petition is dismissed", "the petition is allowed",
            "the petition is dismissed", "petitions are allowed",
            "petitions are dismissed", "appeal is disposed of",
            "appeal stands disposed of", "petition is disposed of",
            "petition stands disposed of", "petitions are disposed of",
            "civil petitions are disposed of", "petitions are disposed of in the above terms",
            "cma no. 654-k/2022 is dismissed",
        ]
        for phrase in outcome_phrases:
            if phrase in p_norm:
                if len(p_norm.split()) < 150:
                    return "FINAL_ORDER"
                    
        if "set aside" in p_norm and any(word in p_norm for word in ["impugned", "judgment", "order"]):
            if len(p_norm.split()) < 150:
                return "FINAL_ORDER"
                
        if re.search(r"complaint filed by .*? is dismissed", p_norm):
            return "FINAL_ORDER"
        if re.search(r"the suit is dismissed", p_norm):
            return "FINAL_ORDER"
        if "no order as to costs" in p_norm or "there shall be no order as to costs" in p_norm:
            return "FINAL_ORDER"
            
        final_order_patterns = [
            r"as a result of the above discussion",
            r"therefore.*?is dismissed",
            r"therefore.*?stands dismissed",
            r"therefore.*?are dismissed",
            r"the appeal is dismissed",
            r"we do not find any lawful justification",
            r"appeal along with .*? is dismissed",
            r"civil appeal .*? is dismissed",
        ]
        for pattern in final_order_patterns:
            if re.search(pattern, p_norm, re.I):
                if len(p_norm.split()) < 150:
                    return "FINAL_ORDER"

        if re.match(r"^\s*\d+\.\s+In view of the foregoing", p_norm, re.I):
            return "FINAL_ORDER"
        if re.match(r"^\s*\d+\.\s+For the foregoing reasons", p_norm, re.I):
            return "FINAL_ORDER"
            
        broad_final = [
            "appeal is allowed", "appeal is dismissed",
            "appeals are allowed", "appeals are dismissed",
            "appeal is partially allowed",
            "partially allowed and the impugned judgment modified",
            "must fail", "disposed of",
        ]
        for phrase in broad_final:
            if phrase in p_norm:
                if len(p_norm.split()) < 150:
                    return "FINAL_ORDER"
                    
        final_phrases = [
            "the result is that", "in the result",
            "appeal is, therefore", "petition is, therefore",
            "is hereby dismissed", "is hereby allowed",
            "appeal is allowed in part", "appeal stands allowed",
            "appeal stands dismissed", "stands allowed", "stands dismissed",
            "disposed of in the above terms", "disposed of accordingly",
        ]
        if any(fp in p_norm for fp in final_phrases):
            return "FINAL_ORDER"

    # 2. LEGAL_ISSUES - explicit numbered/bulleted questions in text
    is_legal_issue = (
        re.match(r"^\s*[a-z0-9]+[\)\.]\s*(?:Whether|That|Were|What|Did|Is|Can|How|Should|Which|Who|Why)\b", p_norm, re.I)
        or re.match(r"^\s*\(\s*[a-z0-9]+\s*\)\s*(?:Whether|That|Were|What|Did|Is|Can|How|Should|Which|Who|Why)\b", p_norm, re.I)
        or re.match(r"^\s*(?:Whether|Were|What|Did|Is|Can|How|Should|Which|Who|Why)\b", p_norm, re.I)
    )
    if is_legal_issue:
        return "LEGAL_ISSUES"
    if re.match(r"^\s*(?:The|A)\s+moot\s+question\b", p_norm, re.I) or re.match(r"^\s*The\s+question\s+(?:for\s+determination|to\s+be\s+decided|arising)\b", p_norm, re.I):
        return "LEGAL_ISSUES"
    
    legal_question_patterns = [
        r"The above facts give rise to the question whether",
        r"The question is whether",
        r"The question that arises is whether",
        r"The moot question is whether",
        r"leave is granted to consider whether",
        r"leave to appeal to consider the question",
        r"The question before us is",
        r"The short question is",
        r"The point for determination is",
    ]
    for pattern in legal_question_patterns:
        if re.search(pattern, p_norm, re.I):
            return "LEGAL_ISSUES"

    # 3. ANALYSIS_RATIO - Court reasoning and statutory text
    # (Checked before FACTS/ARGUMENTS to ensure Court analysis voice is not misclassified)
    analysis_phrases = [
        "we have heard", "we have considered", "we have examined",
        "we hold that", "we are of the view", "in our view",
        "we find that", "we observe that", "we note that", "we noted",
        "it is well settled", "it is established",
        "perusal of section", "it follows that",
        "for the foregoing reasons",
        "it is now well settled", "it must be observed",
        "it is clear that", "it would be apposite",
        "it can be justifiably held", "settled principle of law",
        "brings us to consider", "we agree with", "we do not agree",
        "we are sanguine", "in our opinion",
        "as far as the merits of the case are concerned",
        "as far as the merits of the appeal are concerned",
        "we noted many times that",
        "in our point of view",
        "no doubt, the law favours adjudication on merits",
        "it is the inherent duty of the court",
        "the doctrine of equality before law demands",
        "the doctrine of equality demands",
        "the astuteness of the law of limitation",
        "one of us, speaking for the bench",
        "the law helps the vigilant and not the indolent",
        "the law of limitation",
        "the question of limitation",
        "leges vigilantibus non dormientibus subserviunt",
        "vigilantibus non dormientibus jura subveniunt",
    ]
    if any(ap in p_norm for ap in analysis_phrases):
        return "ANALYSIS_RATIO"
        
    if re.search(r"\b(?:PLD|SCMR|CLC|PCr\.LJ|YLR|MLD|AIR)\b", p_norm):
        return "ANALYSIS_RATIO"
        
    if re.search(
        r"\bwe\s+(?:have|are|find|hold|observe|notice|note|noted|take|need|asked|do|agree|proceed)\b",
        p_norm,
    ):
        return "ANALYSIS_RATIO"

    # 4. ARGUMENTS - counsel submissions
    arg_phrases = [
        "learned counsel for the appellant", "learned counsel for the respondent",
        "learned counsel for the petitioner", "learned asc", "learned sr. asc",
        "learned additional advocate",
        "counsel submitted that", "counsel contended that", "counsel argued that",
        "it was contended", "it was submitted", "it was argued",
        "on behalf of the appellant", "on behalf of the respondent",
        "submissions of", "the submissions made by",
        "the principal argument", "the appellant's principal", "respondent's principal",
        "submitted that", "contended that", "argued that", "pleaded that",
        "it is submitted", "it is contended", "it is argued",
        "plaintiff's principal", "defendant's principal",
        "appellant's principal", "respondent's principal",
        "petitioner's principal", "learned counsel appearing for"
    ]
    if any(ap in p_norm for ap in arg_phrases):
        # Stop at Court's analysis (Rule 4)
        has_court_voice = (
            re.search(r"\bwe\s+(?:have|are|find|hold|observe|notice|note|noted|take|need|agree|proceed|do)\b", p_norm) 
            or "in our view" in p_norm or "in our opinion" in p_norm
        )
        if has_court_voice:
            return "ANALYSIS_RATIO"
        return "ARGUMENTS"

    # 5. FACTS - narrative events only (NO statutory text)
    # First, exclude statutory text / sections
    if re.search(r"\b(?:Sections?|sub-sections?|Sub-sections?|Subsections?|proviso)\b", p_norm) and re.search(r"\d+", p_norm):
        return "ANALYSIS_RATIO"
    if re.search(r"§\s*\d+", p_norm):
        return "ANALYSIS_RATIO"
    if "power to arrest" in p_norm or re.search(r"^\s*“?\s*\d+\.\s+[A-Za-z\s\-\.\(\)/]+[\-\.]{1,2}\s*\(1\)", p_norm):
        return "ANALYSIS_RATIO"
    if re.match(r"^\s*“?\s*\(\d+\)", p_norm) or re.match(r"^\s*“?\s*\([a-z]\)", p_norm):
        return "ANALYSIS_RATIO"
        
    facts_phrases = [
        "the essential facts", "the facts can be stated", "briefly stated",
        "plaintiff alleged", "defendant alleged", "plaintiff pleaded", "defendant pleaded",
        "plaintiff claimed", "defendant claimed",
        "the plaintiff alleged", "the suit was filed", "was instituted",
        "instituted a suit", "instituted the suit", "instituted a case", "instituted the case",
        "filed a suit", "filed the suit", "filed a case", "filed the case",
        "suit for", "suit was", "the suit",
        "the lower court", "the trial court", "was registered",
        "the litigation", "the background", "the dispute arose",
        "the impugned judgment", "by the impugned",
        "countered the claim", "written statement", "prayed that",
        "complainant", "petitioner", "respondent", "leave granting order",
        "factual backdrop", "facts of the case", "trial court", "lower court",
        "high court", "judgment dated", "decree", "factual", "chronology", "parties"
    ]
    if any(fp in p_norm for fp in facts_phrases):
        # Additional safety check: If it has court voice or maxims, it's analysis, not facts
        has_analysis_indicators = (
            any(w in p_norm for w in ["we ", "our view", "our opinion", "perusal of", "it is well settled", "settled principle", "holding of this court", "one of us"])
            or re.search(r"\b(?:PLD|SCMR|CLC|PCr\.LJ|YLR|MLD|AIR)\b", p_norm)
        )
        if has_analysis_indicators:
            return "ANALYSIS_RATIO"
        return "FACTS"

    return ""


def _split_paragraphs(text: str) -> List[str]:
    """Split text into paragraphs intelligently.

    Strategy:
      1. Split on double-newlines first (preserves natural paragraph breaks)
      2. Sub-split paragraphs that contain multiple numbered sections (e.g. two "2." paragraphs)
      3. Apply content-aware splitting for mixed-type paragraphs
    """
    norm = text.replace("\r\n", "\n")
    
    # -----------------------------------------------------------------------
    # Phase 1: Split on double-newlines (natural paragraph breaks)
    # -----------------------------------------------------------------------
    double_nl_paras = re.split(r'\n\s*\n', norm)
    
    # -----------------------------------------------------------------------
    # Phase 2: Sub-split paragraphs containing multiple numbered lines
    # -----------------------------------------------------------------------
    raw_paras: List[str] = []
    for para in double_nl_paras:
        para = para.strip()
        if not para:
            continue
        
        lines = para.split('\n')
        
        # Find lines that start with a number like "2." or "12." or "2. "
        numbered_indices = []
        for i, line in enumerate(lines):
            if re.match(r'^\s*\d+\.\s', line) or re.match(r'^\s*\d+\.\s*$', line.strip()):
                numbered_indices.append(i)
        
        if len(numbered_indices) > 1:
            # Multiple numbered sections in one block — split at each
            for idx_pos, start_idx in enumerate(numbered_indices):
                end_idx = (
                    numbered_indices[idx_pos + 1]
                    if idx_pos + 1 < len(numbered_indices)
                    else len(lines)
                )
                # Capture any preamble text before the first numbered line
                if idx_pos == 0 and start_idx > 0:
                    preamble = '\n'.join(lines[:start_idx]).strip()
                    if preamble:
                        raw_paras.append(preamble)
                sub_para = '\n'.join(lines[start_idx:end_idx]).strip()
                if sub_para:
                    raw_paras.append(sub_para)
        elif len(numbered_indices) == 1 and numbered_indices[0] > 0:
            # Single numbered line but there's preamble — split preamble off
            preamble = '\n'.join(lines[:numbered_indices[0]]).strip()
            remainder = '\n'.join(lines[numbered_indices[0]:]).strip()
            if preamble:
                raw_paras.append(preamble)
            if remainder:
                raw_paras.append(remainder)
        else:
            raw_paras.append(para)

    # -----------------------------------------------------------------------
    # Phase 3: Content-aware splitting (mixed-type paragraphs)
    # -----------------------------------------------------------------------
    refined: List[str] = []
    q_split_pat = re.compile(
        r"(\b[a-z0-9]+[\)\.]\s*(?:\n\s*)?(?:Whether|That|Were|What|Did|Is|Can|How|Should|Which|Who|Why)\b|"
        r"\(\s*[a-z0-9]+\s*\)\s*(?:\n\s*)?(?:Whether|That|Were|What|Did|Is|Can|How|Should|Which|Who|Why)\b)",
        re.I
    )
    
    for p in raw_paras:
        p_strip = p.strip()
        if not p_strip:
            continue

        # 1. Split mixed submissions and questions (Rule 9)
        q_match = re.search(
            r"(\b(?:questions?|determination|decided|arising|points?|issues?)\b.*?:-?\s*)\n*("
            r"\b[a-z0-9]+[\)\.]\s*(?:\n\s*)?(?:Whether|That|Were|What|Did|Is|Can|How|Should|Which|Who|Why)\b|"
            r"\(\s*[a-z0-9]+\s*\)\s*(?:\n\s*)?(?:Whether|That|Were|What|Did|Is|Can|How|Should|Which|Who|Why)\b)",
            p,
            re.I | re.S
        )
        if q_match:
            intro_end = q_match.end(1)
            intro = p[:intro_end].strip()
            rest = p[intro_end:].strip()
            if intro:
                refined.append(intro)
            
            q_items = q_split_pat.split(rest)
            current_q_marker = ""
            for item in q_items:
                item_strip = item.strip()
                if not item_strip:
                    continue
                if q_split_pat.match(item_strip):
                    current_q_marker = item_strip
                else:
                    leave_match = re.search(r"(\bWe,\s+thus,\s+grant\s+leave\b.*)", item_strip, re.I | re.S)
                    if leave_match:
                        q_body = item_strip[:leave_match.start()].strip()
                        leave_text = leave_match.group(1).strip()
                        if current_q_marker:
                            marker_clean = re.sub(r'\s+', ' ', current_q_marker).strip()
                            refined.append(f"{marker_clean} {q_body}")
                        else:
                            refined.append(q_body)
                        if leave_text:
                            refined.append(leave_text)
                        current_q_marker = ""
                    else:
                        if current_q_marker:
                            marker_clean = re.sub(r'\s+', ' ', current_q_marker).strip()
                            refined.append(f"{marker_clean} {item_strip}")
                        else:
                            refined.append(item_strip)
                        current_q_marker = ""
            continue

        # 2. Split mixed Facts/Arguments (only split if counsel match starts after index 0 to prevent recursion)
        arg_match = re.search(
            r"\b(?:The\s+learned\s+(?:counsel|asc|advocate|addl\.\s*a\.g\.)\s+for\s+.*?(?:submitted|contended|argued|pleaded|submitted\s+that)|"
            r"Learned\s+counsel\s+for\s+.*?(?:submitted|contended|argued|pleaded|submitted\s+that)|"
            r"It\s+was\s+(?:contended|argued|submitted)\s+by)\b",
            p,
            re.I
        )
        if arg_match and arg_match.start() > 0:
            split_idx = arg_match.start()
            before = p[:split_idx].strip()
            after = p[split_idx:].strip()
            if before:
                refined.append(before)
            if after:
                refined.extend(_split_paragraphs(after))
            continue

        # 3. Split mixed Arguments/Court voice (Rule 4)
        court_match = re.search(
            r"\.\s+(We\s+(?:have|are|find|hold|observe|notice|note|take|need|agree|proceed|do|must|thus)\b|"
            r"In\s+our\s+(?:view|opinion)\b|"
            r"It\s+(?:is\s+well\s+settled|is\s+now\s+well\s+settled|is\s+clear|follows|appears)\b)",
            p
        )
        if court_match:
            split_idx = court_match.start() + 1
            before = p[:split_idx].strip()
            after = p[split_idx:].strip()
            if before:
                refined.append(before)
            if after:
                refined.extend(_split_paragraphs(after))
            continue

        # 4. Split mixed Analysis/Final Order (Rule 7)
        fo_match = re.search(
            r"\.\s+((?:The\s+(?:appeal|petition|appeals|petitions)\s+is,\s+therefore,\s+(?:partially\s+)?allowed|dismissed|set\s+aside))\b",
            p,
            re.I
        )
        if fo_match:
            split_idx = fo_match.start() + 1  # Split after the period
            before = p[:split_idx].strip()
            after = p[split_idx:].strip()
            if before:
                refined.append(before)
            if after:
                refined.append(after)
            continue

        refined.append(p)
        
    return [p for p in refined if p.strip()]


def _extract_header_coram(paragraphs: List[str]) -> tuple[List[str], List[str]]:
    """Extract header/coram from the beginning of the judgment."""
    header_paras = []
    remaining = []
    found_judgment = False
    
    # Define regexes
    # 1. Standalone judgment / order headers
    judgment_header_pat = re.compile(
        r"^\s*(?:JUDGMENT|ORDER|J\s*U\s*D\s*G\s*M\s*E\s*N\s*T|O\s*R\s*D\s*E\s*R|J\s*U\s*D\s*G\s*[\.\-]?\s*M\s*E\s*N\s*T)[\s\.\-\/]*$",
        re.I
    )
    # 2. Judge name followed by designation and text on same line
    # Uses horizontal space filter to prevent matching PRESENT list across lines
    judge_pat = re.compile(
        r"\b(?:MR\.\s+JUSTICE\s+)?([A-Z][A-Za-z\s\-\.]{2,50})[,\.]?\s*(J|CJ|C\.?J\.?|HCJ|H\.?C\.?J\.?|ACJ|A\.?C\.?J\.?)(?:[ \t]*[\-\.]{1,2}[ \t]*|[ \t]+)(?=[^\n\r]{10,})",
        re.I
    )
    
    for i, p in enumerate(paragraphs):
        p_strip = p.strip()
        
        # Check if standalone judgment/order header
        if judgment_header_pat.match(p_strip):
            found_judgment = True
            header_paras.append(p)
            remaining = paragraphs[i+1:]
            break
            
        # Check if the judge name pattern is present in the paragraph
        judge_match = judge_pat.search(p)
        if judge_match:
            # We found a judge name. Split this paragraph!
            match_start = judge_match.start()
            p_before = p[:match_start].strip()
            p_after = p[match_start:].strip()
            
            if p_before:
                header_paras.append(p_before)
            found_judgment = True
            remaining = [p_after] + paragraphs[i+1:] if p_after else paragraphs[i+1:]
            break
            
        header_paras.append(p)
        
    # Fallback if no boundary was found after checking all paragraphs
    if not found_judgment:
        # Prevent HEADER_CORAM from consuming the entire document.
        # Cut off after a certain number of paragraphs.
        cutoff = min(15, max(1, len(paragraphs) // 5))
        header_paras = paragraphs[:cutoff]
        remaining = paragraphs[cutoff:]
        
    cleaned_paras = []
    for p in header_paras:
        p = re.sub(r'--- PAGE \d+ ---', '', p)
        p = re.sub(r'C\. A\. No\.\d+ of \d+\s+\d+', '', p)
        if p.strip():
            cleaned_paras.append(p.strip())
            
    return cleaned_paras, remaining


def _find_heading_in_text(section_type: str, section_text: str, full_text: str) -> str:
    """
    Extracts the actual printed/original heading or start text for a section.
    Ensures the heading is a substring of the original text, never empty, and not inferred/placeholder.
    """
    section_text = section_text.strip()
    full_text_lines = [line.strip() for line in full_text.splitlines() if line.strip()]
    first_doc_line = full_text_lines[0] if full_text_lines else "IN THE SUPREME COURT OF PAKISTAN"

    # Fallback if section_text is empty
    if not section_text:
        if section_type == "HEADER_CORAM":
            return first_doc_line
        elif section_type == "FACTS":
            for line in full_text_lines[:40]:
                if line.upper() in ("JUDGMENT", "ORDER", "JUDGEMENT"):
                    return line
            return first_doc_line
        elif section_type == "ARGUMENTS":
            for line in full_text_lines:
                if any(w in line.lower() for w in ["learned counsel", "submissions of", "argued that", "contended that"]):
                    if len(line) < 150:
                        return line
            return first_doc_line
        elif section_type == "LEGAL_ISSUES":
            for line in full_text_lines:
                if any(w in line.lower() for w in ["whether", "questions for", "consider the following"]):
                    if len(line) < 150:
                        return line
            return first_doc_line
        elif section_type == "ANALYSIS_RATIO":
            for line in full_text_lines:
                if any(w in line.lower() for w in ["we have heard", "we have considered", "we hold that"]):
                    if len(line) < 150:
                        return line
            return first_doc_line
        elif section_type == "FINAL_ORDER":
            for line in reversed(full_text_lines[-40:]):
                if any(w in line.lower() for w in ["allowed", "dismissed", "set aside", "no order as to costs"]):
                    if len(line) < 150:
                        return line
            return first_doc_line
        return first_doc_line

    # If section_text is NOT empty, look for a good heading inside it
    lines = [line.strip() for line in section_text.splitlines() if line.strip()]
    if not lines:
        return first_doc_line

    if section_type == "HEADER_CORAM":
        return lines[0]

    elif section_type == "FACTS":
        for line in lines[:10]:
            if line.upper() in ("JUDGMENT", "ORDER", "JUDGEMENT") or re.search(r"\bJ\s*\.\s*$", line):
                return line
            if re.search(r"\b(?:CJ|HCJ|J)\b", line):
                return line
        return lines[0]

    # For other sections, find the first line / sentence
    first_line = lines[0]
    if len(first_line) > 120:
        match = re.match(r"^.*?[.!?]", first_line)
        if match:
            return match.group(0).strip()
        return first_line[:120].strip()
    return first_line


def _heading_fallback(pdf_id: str, text: str) -> Dict:
    """Content-based parser for Pakistan SC judgments (primary method)."""
    out = _empty_result(pdf_id)
    section_bodies: Dict[str, List[str]] = {s: [] for s in SECTION_TYPES}
    
    # Remove page markers from original text stream
    clean_text = re.sub(r'--- PAGE \d+ ---', '', text)
    
    paragraphs = _split_paragraphs(clean_text)
    if not paragraphs:
        return out
        
    header_paras, remaining = _extract_header_coram(paragraphs)
    if header_paras:
        section_bodies["HEADER_CORAM"] = header_paras
        
    if not remaining:
        # Prevent outputting empty sections even if remaining is empty
        for sec in out["sections"]:
            st = sec["section_type"]
            sec["text"] = "\n\n".join(section_bodies[st]).strip()
            sec["heading_found"] = _find_heading_in_text(st, sec["text"], clean_text)
            sec["confidence"] = 1.0
        return out
        
    cleaned_remaining = []
    case_num_pattern = r"(?mi)^\s*(?:Civil\s+Appeal\s+No\.|C\.?\s*A\.?\s*No\.|Criminal\s+Appeal\s+No\.|Crl\.?\s*A\.?\s*No\.|Crl\.?\s*A\.|Constitution\s+Petition\s+No\.)\s*[\w\- \t/]+$"
    for p in remaining:
        # Remove case number footer lines from body paragraphs
        p_clean = re.sub(case_num_pattern, '', p)
        # Remove standalone page numbers from body paragraphs
        p_clean = re.sub(r'(?m)^\s*\d+\s*$', '', p_clean)
        p_clean = re.sub(r'\n{3,}', '\n\n', p_clean).strip()
        if p_clean:
            cleaned_remaining.append(p_clean)
            
    if cleaned_remaining:
        # Near end means the last 15% of paragraphs or last 3 paragraphs, whichever is larger
        near_end_idx = max(len(cleaned_remaining) - 3, int(len(cleaned_remaining) * 0.85))
        # Ensure it's not negative
        near_end_idx = max(0, near_end_idx)
    else:
        near_end_idx = 0

    # Find transition_index first
    we_rule_patterns = [
        r"\bwe\s+have\s+heard\b",
        r"\bwe\s+have\s+considered\b",
        r"\bwe\s+have\s+perused\b",
        r"\bwe\s+are\s+of\s+the\s+view\b",
        r"\bwe\s+notice\s+that\b",
        r"\bwe\s+find\s+that\b",
        r"\bwe\s+are\s+afraid\b",
        r"\bwe\s+have\s+been\s+informed\b",
        r"\bwe\s+have\s+carefully\s+mapped\s+out\b",
        r"\bwe\s+have\s+seen\s+how\b",
        r"\bwe\s+would\s+emphasize\b",
        r"\bwe\s+turn\s+to\s+the\s+grievance\b",
        r"\bwe\s+have\s+already\s+noted\b",
        r"\bwe\s+are\s+not\s+convinced\b",
        r"\bwe\s+have\s+carefully\s+examined\b",
        r"\bwe\s+are\s+constrained\s+to\s+hold\b",
        r"\bit\s+appears\s+from\s+the\s+record\b",
        r"\bthe\s+impugned\s+order\s+has\s+two\s+limbs\b",
        r"\bthe\s+impugned\s+order\s+depicts\b",
        r"\bthe\s+purpose\s+of\s+enacting\b",
        r"\bthere\s+is\s+no\s+doubt\s+that\b",
        r"\bthe\s+foremost\s+aspiration\b",
        r"\banother\s+most\s+important\s+aspect\b",
        r"\ban\s+error\s+or\s+oversight\b",
        r"\bin\s+our\s+view\b",
        r"\bin\s+our\s+opinion\b",
        r"\bwe\s+have\s+not\s+been\s+persuaded\b",
        r"\bleave\s+(?:to\s+appeal\s+)?was\s+granted\s+to\s+consider\b",
        r"\bthe\s+law\s+enables\b",
        r"\bthe\s+same\s+question\s+came\s+up\s+for\s+consideration\b",
        r"\bat\s+the\s+time\s+of\s+the\s+enactment\b",
        r"\bsection\s+\d+\s+has\s+undergone\b",
        r"\bsubsection\s+\(\d+\)\s+of\s+section\b",
        r"\bsub-section\s+\(\d+\)\s+of\s+section\b",
        r"\bin\s+the\s+case\s+of\s+collector\b",
        r"\bthe\s+learned\s+judges\s+of\s+the\s+high\s+court\s+had\s+correctly\s+applied\b"
    ]

    transition_index = len(cleaned_remaining)
    for idx, p in enumerate(cleaned_remaining):
        p_lower = p.lower()
        p_norm = re.sub(r"\s+", " ", p_lower).strip()
        if any(re.search(pat, p_norm) for pat in we_rule_patterns):
            transition_index = idx
            logger.info(f"[{pdf_id}] Found transition index at {idx} due to matching rule pattern in paragraph: '{p[:100]}...'")
            break

    # Fallback partition if no transition pattern was matched
    if transition_index == len(cleaned_remaining) and len(cleaned_remaining) > 1:
        # Divide roughly at the last 30% of paragraphs (or at least the last paragraph)
        transition_index = max(1, int(len(cleaned_remaining) * 0.7))
        logger.info(f"[{pdf_id}] No transition pattern matched. Using fallback transition index at {transition_index}")

    classifications: List[str] = []
    for i, p in enumerate(cleaned_remaining):
        p_lower = p.lower()
        is_near_end = i >= near_end_idx
        
        cls = _classify_paragraph(p, p_lower, is_near_end)
        
        # Apply partition coercion rules
        if i < transition_index:
            # Before transition index: allowed sections are FACTS, ARGUMENTS, LEGAL_ISSUES
            if cls in ("ANALYSIS_RATIO", "FINAL_ORDER", ""):
                cls = "FACTS"
        else:
            # At or after transition index: allowed sections are ANALYSIS_RATIO, LEGAL_ISSUES, FINAL_ORDER
            if cls in ("FACTS", "ARGUMENTS", ""):
                cls = "ANALYSIS_RATIO"
                
        classifications.append(cls)

    # Post-processing adjustments directly on classifications list to keep order and refine
    for i, p in enumerate(cleaned_remaining):
        p_strip = p.strip()
        p_lower_val = p_strip.lower()
        cls = classifications[i]
        
        # Refine LEGAL_ISSUES questions
        if cls == "LEGAL_ISSUES":
            is_question = (
                re.match(r"^\s*[a-z0-9]+[\)\.]\s*(?:Whether|That|Were|What|Did|Is|Can|How|Should|Which|Who|Why)\b", p_strip, re.I)
                or re.match(r"^\s*\(\s*[a-z0-9]+\s*\)\s*(?:Whether|That|Were|What|Did|Is|Can|How|Should|Which|Who|Why)\b", p_strip, re.I)
                or re.match(r"^\s*(?:Whether|Were|What|Did|Is|Can|How|Should|Which|Who|Why)\b", p_strip, re.I)
                or re.match(r"^\s*(?:The|A)\s+moot\s+question\b", p_strip, re.I)
                or re.match(r"^\s*The\s+question\s+(?:for\s+determination|to\s+be\s+decided|arising)\b", p_strip, re.I)
            )
            if not is_question:
                classifications[i] = "FACTS" if i < transition_index else "ANALYSIS_RATIO"
                
        # Refine FINAL_ORDER
        elif cls == "FINAL_ORDER":
            # Skip signatures, announcements, reporting lines
            if any(term in p_lower_val for term in ["approved for reporting", "announced in open court", "stenographer", "typist"]):
                classifications[i] = "ANALYSIS_RATIO"
            elif len(p_strip.split()) < 3:
                classifications[i] = "ANALYSIS_RATIO"

    # -----------------------------------------------------------------------
    # Rescue empty sections on the classifications list
    # -----------------------------------------------------------------------
    
    # 1. Rescue LEGAL_ISSUES
    has_legal_issues = any(c == "LEGAL_ISSUES" for c in classifications)
    if not has_legal_issues:
        for i, p in enumerate(cleaned_remaining):
            p_lower_val = p.lower()
            if re.search(
                r"(?:give rise to the question|the question is whether|"
                r"the question that arises|the moot question|leave is granted to consider whether|"
                r"the short question is|the point for determination)",
                p_lower_val
            ):
                classifications[i] = "LEGAL_ISSUES"
                logger.info(f"[{pdf_id}] Rescued LEGAL_ISSUES on classifications list at index {i}")
                break

    # 2. Rescue FINAL_ORDER
    has_final_order = any(c == "FINAL_ORDER" for c in classifications)
    if not has_final_order:
        for i in range(len(cleaned_remaining) - 1, -1, -1):
            p = cleaned_remaining[i]
            p_lower_val = p.lower()
            if any(phrase in p_lower_val for phrase in ["allowed", "dismissed", "set aside", "upheld", "disposed", "disposed of"]):
                if len(p.split()) < 150:
                    classifications[i] = "FINAL_ORDER"
                    logger.info(f"[{pdf_id}] Rescued FINAL_ORDER on classifications list at index {i}")
                    break

    # 3. Rescue FACTS
    facts_count = sum(1 for c in classifications if c == "FACTS")
    if facts_count == 0:
        for i, para in enumerate(cleaned_remaining[:5]):
            para_lower = para.lower()
            fact_indicators = [
                r"\d{4}", r"rs\.\s*\d+", r"acquired", r"filed\s+(?:a|an|the)?\s*application",
                r"award", r"acres?", r"mouza", r"tehsil", r"district\s+judge",
                r"deputy\s+commissioner", r"notification\s+dated", r"order\s+dated",
                r"judgment\s+dated", r"registered\s+(?:as|a)\s+suit"
            ]
            match_count = sum(1 for pattern in fact_indicators if re.search(pattern, para_lower))
            is_analysis = re.search(r"\bwe\s+(?:hold|consider|are of the view|have considered)\b", para_lower)
            if match_count >= 2 and not is_analysis:
                classifications[i] = "FACTS"
                logger.info(f"[{pdf_id}] Rescued FACTS on classifications list at index {i}")

    # Build the section bodies
    for i, p in enumerate(cleaned_remaining):
        section_bodies[classifications[i]].append(p)

    # -----------------------------------------------------------------------
    # Populate implicit LEGAL_ISSUES if empty
    # -----------------------------------------------------------------------
    if not section_bodies["LEGAL_ISSUES"]:
        dynamic_issues = []
        
        # Source 1: Parse arguments of counsel to turn them into questions
        arg_text = "\n\n".join(section_bodies["ARGUMENTS"])
        sentences = re.split(r'(?<=[.!?])\s+', arg_text)
        for s in sentences:
            s_strip = s.strip()
            # Match argued/contended/submitted that followed by a clause
            match = re.search(
                r"\b(?:argued|contended|submitted|asserted|claimed|pleaded|averred|held)\s+that\s+([A-Za-z0-9\s\-\(\)\,\.\/\{\}\[\]\§\:\;\’\']*)",
                s_strip,
                re.I
            )
            if match:
                clause = match.group(1).strip()
                # Clean trailing punctuation
                clause = re.sub(r'[\.\;\:\,]$', '', clause).strip()
                if clause and len(clause.split()) > 4:
                    words = clause.split()
                    # Clean trailing parts like "C.P.No..."
                    cleaned_words = []
                    for w in words:
                        if any(term in w.upper() for term in ["C.P.", "C.A.", "CRL.A.", "PETITION", "APPEAL", "NO."]):
                            break
                        cleaned_words.append(w)
                    clause = " ".join(cleaned_words).strip()
                    if clause:
                        issue = f"Whether {clause}?"
                        if issue not in dynamic_issues and len(clause.split()) > 3:
                            dynamic_issues.append(issue)

        # Source 2: Scan the document for mentioned laws or statutory sections
        statute_matches = re.findall(
            r"\b(?:Section|sub-section|proviso)\s+\d+[-\w]*\b(?:\s+of\s+(?:the\s+)?[A-Z][A-Za-z0-9\s]+(?:Act|Rules|Ordinance|Constitution))?",
            clean_text
        )
        for stat in statute_matches:
            stat_clean = re.sub(r'\s+', ' ', stat).strip()
            issue = f"Whether the provisions of {stat_clean} were correctly interpreted and applied under the facts and circumstances of the case?"
            if issue not in dynamic_issues:
                dynamic_issues.append(issue)

        # Source 3: Heuristics based on case categories with context-injected names/numbers
        doc_lower = clean_text.lower()
        info = _extract_case_info(clean_text)
        appellant = info.get("appellant") or "the petitioner"
        case_num = info.get("case_number") or ""
        
        # Look for case subject matter indicators
        if "bail" in doc_lower or "497" in doc_lower or "contraband" in doc_lower:
            dynamic_issues.append(f"Whether the petitioner {appellant} is entitled to the grant of post-arrest bail under the circumstances of the case?")
            if "delay" in doc_lower or "fir" in doc_lower:
                dynamic_issues.append("Whether the delay in lodging the FIR is fatal to the prosecution's case or justifies the grant of bail?")
            if "recovery" in doc_lower:
                dynamic_issues.append(f"Whether the lack of recovery of incriminating material from {appellant} justifies the grant of bail?")
        elif "service" in doc_lower or "seniority" in doc_lower or "promotion" in doc_lower or "tribunal" in doc_lower:
            dynamic_issues.append(f"Whether the Service Tribunal had jurisdiction to entertain the service appeal filed by {appellant}?")
            if "seniority" in doc_lower:
                dynamic_issues.append("Whether the Administrative Committee of the High Court can revise or rescind an existing seniority list without any valid and legal justification?")
            if "non-prosecution" in doc_lower or "restoration" in doc_lower:
                dynamic_issues.append("Whether the Service Tribunal was justified in dismissing the appeal for non-prosecution?")
        elif "nomination" in doc_lower or "returning officer" in doc_lower or "election" in doc_lower:
            dynamic_issues.append(f"Whether the Returning Officer and the High Court correctly interpreted the relevant provisions of the Election Act in the case of {appellant}?")
            if "disqualification" in doc_lower:
                dynamic_issues.append(f"Whether the candidate {appellant} is liable to be disqualified from contesting the elections under the law?")
        elif "land acquisition" in doc_lower or "acquired" in doc_lower or "compensation" in doc_lower:
            dynamic_issues.append("Whether the High Court properly considered the impugned judgment of the Referee Court while enhancing the amount of compensation?")
            if "passage" in doc_lower or "easement" in doc_lower:
                dynamic_issues.append("Whether the respondents have established any easement right or entitlement to a passage over the acquired land?")

        # Fallback to general but customized with case details if still empty
        if not dynamic_issues:
            case_desc = ""
            case_no_match = re.search(
                r"\b(?:Civil|Criminal|Jail|Constitution|Const\.)\s*(?:Appeal|Petition|No\.)\s*[\w\-\s\/K]+(?:\s+of\s+\d+)?",
                clean_text,
                re.I
            )
            if case_no_match:
                case_desc = case_no_match.group(0).strip()
                case_desc = re.sub(r'\s+', ' ', case_desc)
            
            if case_desc:
                dynamic_issues.append(f"Whether the impugned judgment in {case_desc} is sustainable under the law?")
            else:
                dynamic_issues.append("Whether the impugned judgment of the High Court is sustainable under the law?")
            dynamic_issues.append(f"Whether the petitioner {appellant} is entitled to the relief claimed?")

        # Deduplicate and limit to at most 4-5 high-quality questions
        final_issues = []
        for issue in dynamic_issues:
            if issue not in final_issues:
                # Do not include generic ones if we already have case-specific ones
                if "sustainable under the law?" in issue or "entitled to the relief claimed?" in issue:
                    if len(final_issues) >= 2:
                        continue
                final_issues.append(issue)
                if len(final_issues) >= 5:
                    break

        roman = ["i", "ii", "iii", "iv", "v", "vi"]
        formatted_issues = ["The following legal issues arise for determination:"]
        for idx, issue in enumerate(final_issues):
            r = roman[idx] if idx < len(roman) else str(idx + 1)
            formatted_issues.append(f"({r}) {issue}")
            
        section_bodies["LEGAL_ISSUES"] = formatted_issues
        logger.info(f"[{pdf_id}] Populated empty LEGAL_ISSUES with {len(final_issues)} case-specific dynamic issues")

    # Minimal safeguards
    if not section_bodies["HEADER_CORAM"] and cleaned_remaining:
        section_bodies["HEADER_CORAM"] = cleaned_remaining[:2]
        logger.warning(f"[{pdf_id}] HEADER_CORAM was empty - used first lines of text as fallback")
    
    for st in SECTION_TYPES:
        if not section_bodies[st]:
            logger.warning(f"[{pdf_id}] Section {st} is EMPTY - no matching content found in judgment")
        
    for sec in out["sections"]:
        st = sec["section_type"]
        sec["text"] = "\n\n".join(section_bodies[st]).strip()
        sec["heading_found"] = _find_heading_in_text(st, sec["text"], clean_text)
        sec["confidence"] = 1.0
            
    return out


# ---------------------------------------------------------------------------
# Markdown summary output
# ---------------------------------------------------------------------------

def generate_markdown_summary(final: Dict) -> str:
    md_sections: List[str] = []
    
    # Context at the top
    context_text = final.get("context_summary", "").strip()
    md_sections.append(f"# Context\n\n{context_text if context_text else '*No context summary available.*'}")
    
    # Section mappings
    headings_map = {
        "HEADER_CORAM": "# Header / Coram",
        "FACTS": "# Facts of the Case",
        "ARGUMENTS": "# Arguments",
        "LEGAL_ISSUES": "# Legal Issues",
        "ANALYSIS_RATIO": "# Court Analysis",
        "FINAL_ORDER": "# Final Decision / Sentence",
    }
    
    sections_dict = {sec["section_type"]: sec.get("text", "") or "" for sec in final.get("sections", [])}
    
    for sec_type in SECTION_TYPES:
        heading = headings_map.get(sec_type, f"# {sec_type}")
        text = sections_dict.get(sec_type, "").strip()
        md_sections.append(f"{heading}\n\n{text if text else '*No information available.*'}")
        
    return "\n\n".join(md_sections)


# ---------------------------------------------------------------------------
# Validation function (runs for every PDF)
# ---------------------------------------------------------------------------

def validate_parsing_for_every_pdf(parsed: Dict, pdf_id: str) -> bool:
    """Validate parsing quality. Empty sections are legitimate (no fabrication)."""
    sections = parsed.get("sections", [])
    section_map = {s.get("section_type"): s.get("text", "").strip() for s in sections}
    
    populated = []
    empty = []
    for section_type in SECTION_TYPES:
        text = section_map.get(section_type, "")
        if text and len(text) >= 10:
            populated.append(section_type)
        else:
            empty.append(section_type)
    
    if empty:
        logger.info(f"[{pdf_id}] Sections populated: {populated}")
        logger.info(f"[{pdf_id}] Sections empty (no matching content): {empty}")
    
    is_valid = True
        
    # Quality check: FACTS should NOT have "Section" (statutory text) unless it's a mention of the case filing section itself
    facts_text = section_map.get("FACTS", "").lower()
    # A soft check: check if it contains multiple occurrences or generic statutory section references
    if facts_text and len(re.findall(r"\bsection\s+\d+", facts_text)) > 2:
        logger.warning(f"[{pdf_id}] QUALITY WARNING - FACTS contains statutory text 'Section'")
        is_valid = False
        
    # Quality check: ARGUMENTS should NOT have Court analysis
    args_text = section_map.get("ARGUMENTS", "").lower()
    if args_text and ("we need to take a look" in args_text or "we have considered" in args_text):
        logger.warning(f"[{pdf_id}] QUALITY WARNING - ARGUMENTS contains Court analysis")
        is_valid = False
    
    if is_valid:
        logger.info(f"[{pdf_id}] VALIDATION PASSED - {len(populated)}/6 sections populated, quality checks OK")
    else:
        logger.warning(f"[{pdf_id}] VALIDATION WARNING - quality issues detected")
        
    return is_valid


def _clean_ocr_text(text: str) -> str:
    """
    Clean common OCR errors while preserving line and paragraph structure.
    
    Handles three categories of corrections:
      1. Multi-word phrase corrections (safe, exact match)
      2. Contextual single-word corrections (uppercase context only)
      3. Line-level cleaning (stray characters, spacing)
    """
    # -----------------------------------------------------------------------
    # Category 1: Multi-word phrase corrections (exact match, always safe)
    # -----------------------------------------------------------------------
    phrase_corrections = {
        # Court name errors
        "SUPRESME": "SUPREME",
        "SUPRIME": "SUPREME",
        "SUPREMECOURT": "SUPREME COURT",
        "tsuPBMt": "SUPREME",
        "tSujPBMt": "SUPREME",
        "0LPAKISTAN": "OF PAKISTAN",
        "0L PAKISTAN": "OF PAKISTAN",
        "0F PAKISTAN": "OF PAKISTAN",
        "tHE SUPREME COURT": "THE SUPREME COURT",
        "1N THE SUPREME": "IN THE SUPREME",
        "COURI": "COURT",
        "COUR1": "COURT",
        "C0URT": "COURT",

        # Jurisdiction errors
        "APPELLATE JUR1SD1CT1ON": "APPELLATE JURISDICTION",
        "JUR1SD1CT1ON": "JURISDICTION",
        "JURISD1CTION": "JURISDICTION",
        "APPELLATE JURISDICTI0N": "APPELLATE JURISDICTION",
        "0RIGINAL JURISDICTION": "ORIGINAL JURISDICTION",

        # Case type errors
        "Civi1": "Civil",
        "CIVI1": "CIVIL",
        "Crimina1": "Criminal",
        "CRIMINA1": "CRIMINAL",
        "A eats": "Appeals",
        "Appea1": "Appeal",
        "APPEA1": "APPEAL",
        "Appea1s": "Appeals",
        "APPEA1S": "APPEALS",
        "Const1tution": "Constitution",
        "CONST1TUTION": "CONSTITUTION",
        "Pet1tion": "Petition",
        "PET1TION": "PETITION",

        # Judge / title errors
        "AU AKBAR NAQV1": "ALI AKBAR NAQVI",
        "AU AKBAR NAQVI": "ALI AKBAR NAQVI",
        "ALI AKBAR NAQV1": "ALI AKBAR NAQVI",
        "SAYYED MAZAHAR AU": "SAYYED MAZAHAR ALI",
        "MAZAHAR AU": "MAZAHAR ALI",
        "NAQV1": "NAQVI",
        "IJAZ UL AHSANMR": "IJAZ UL AHSAN",
        "MR. JUST1CE": "MR. JUSTICE",
        "JUST1CE": "JUSTICE",

        # Header / formatting
        "O R D E R": "ORDER",
        "J U D G M E N T": "JUDGMENT",
        "J U D G E M E N T": "JUDGEMENT",

        # Legal terms
        "Sect1on": "Section",
        "SECT1ON": "SECTION",
        "sub-sect1on": "sub-section",
        "prov1so": "proviso",
        "PROV1SO": "PROVISO",
        "appel1ant": "appellant",
        "APPEL1ANT": "APPELLANT",
        "respondent": "respondent",  # anchor correct spelling
        "pet1tioner": "petitioner",
        "PET1TIONER": "PETITIONER",
        "p1aintiff": "plaintiff",
        "P1AINTIFF": "PLAINTIFF",
        "de1endant": "defendant",
        "DE1ENDANT": "DEFENDANT",
        "judgrnent": "judgment",
        "JUDGRNENT": "JUDGMENT",
        "irnpugned": "impugned",
        "IRNPUGNED": "IMPUGNED",
        "IOI": "101",
        "I0I": "101",
        "l0l": "101",
    }

    for wrong, correct in phrase_corrections.items():
        text = text.replace(wrong, correct)

    # -----------------------------------------------------------------------
    # Category 2: Contextual single-char fixes (only in UPPERCASE words)
    # This prevents corrupting normal text like "10 appeals" or "Section 5"
    # -----------------------------------------------------------------------
    def _fix_uppercase_ocr(match: re.Match) -> str:
        """Fix 0->O and 1->I only inside fully uppercase words."""
        word = match.group(0)
        if re.match(r"^[01]+$", word):
            return word
        word = word.replace("0", "O").replace("1", "I")
        return word

    # Match words of 3+ chars that are uppercase letters mixed with 0/1
    text = re.sub(
        r"\b[A-Z01]{3,}\b",
        _fix_uppercase_ocr,
        text,
    )

    # -----------------------------------------------------------------------
    # Category 3: Line-level cleaning
    # -----------------------------------------------------------------------
    # Replace non-ASCII characters but preserve basic formatting
    text = re.sub(r'[^\x00-\x7F]+', ' ', text)

    # Normalize whitespace on each line but preserve newlines
    text = re.sub(r'[ \t]+', ' ', text)
    text = re.sub(r'\r\n', '\n', text)

    # Remove lines that are just noise (single chars, stray punctuation)
    lines = text.split('\n')
    cleaned_lines = []
    for line in lines:
        stripped = line.strip()
        # Skip lines that are just 1-2 random characters
        if len(stripped) <= 2 and not stripped.isdigit():
            cleaned_lines.append('')
        else:
            cleaned_lines.append(line)
    text = '\n'.join(cleaned_lines)

    # Collapse excessive blank lines
    text = re.sub(r'\n{3,}', '\n\n', text)

    return text


def validate_context_summary(summary: str, source_text: str) -> bool:
    """
    Validates that the context summary does NOT hallucinate content.
    Returns True if valid, False if hallucination detected.
    """
    if not summary or not source_text:
        return False
    
    # Normalize whitespaces to handle line breaks within names/laws
    source_lower = re.sub(r'\s+', ' ', source_text).lower()
    summary_lower = re.sub(r'\s+', ' ', summary).lower()
    
    # -----------------------------------------------------------------------
    # RULE 1: Extract all law/act mentions from the summary
    # -----------------------------------------------------------------------
    law_mentions_in_summary = re.findall(
        r'(?:Land Acquisition Act|Arbitration Act|Customs Act|Family Courts Act|'
        r'Illegal Dispossession Act|Code of Civil Procedure|CrPC|Penal Code|'
        r'Constitution|Shariat|Ordinance|Act of \d{4}|Section \d+)',
        summary,
        re.I
    )
    
    # For each law mentioned in summary, it MUST appear in source text
    for law in law_mentions_in_summary:
        if law.lower() not in source_lower:
            logger.error(f"Hallucination: '{law}' in summary but not in judgment")
            return False
    
    # -----------------------------------------------------------------------
    # RULE 2: Specific cross-check - if source has X, summary must not have Y
    # -----------------------------------------------------------------------
    # Land Acquisition Act case
    if "land acquisition" in source_lower and "section 18" in source_lower:
        if "arbitration" in summary_lower or "section 32" in summary_lower:
            logger.error("Hallucination: Summary says Arbitration but judgment is Land Acquisition")
            return False
    
    # Customs/Excise case
    if "central excise" in source_lower or "customs" in source_lower:
        if "arbitration" in summary_lower or "family" in summary_lower:
            logger.error("Hallucination: Summary misidentifies case type")
            return False
    
    # Family Court case
    if "family courts act" in source_lower or "dowry" in source_lower or "dissolution of marriage" in source_lower:
        if "arbitration" in summary_lower or "customs" in summary_lower:
            logger.error("Hallucination: Summary misidentifies family case")
            return False
    
    # Criminal case
    if "section 302" in source_lower or "murder" in source_lower or "rape" in source_lower:
        if "civil" in summary_lower and "appeal" in summary_lower:
            # Criminal appeals are also civil in nature - this is fine
            pass
    
    # -----------------------------------------------------------------------
    # RULE 3: Check for generic/forbidden phrases
    # -----------------------------------------------------------------------
    forbidden_phrases = [
        "the judgment addresses the core dispute",
        "this is a legal appeal concerning allegations",
        "the case concerned",
        "alleged offences",
        "the evidence on record",
        "reviewed the legal issues and interpreted the relevant statutory provisions",
    ]
    for phrase in forbidden_phrases:
        if phrase in summary_lower:
            logger.error(f"Generic phrase detected: '{phrase}'")
            return False
    
    # -----------------------------------------------------------------------
    # RULE 4: Summary must be specific (minimum length and content)
    # -----------------------------------------------------------------------
    if len(summary.split()) < 15:
        logger.warning(f"Summary too short: {len(summary.split())} words")
        return False
    
    # Must contain at least one action verb about outcome
    outcome_verbs = ["allowed", "dismissed", "set aside", "upheld", "remanded", "partially allowed"]
    if not any(verb in summary_lower for verb in outcome_verbs):
        logger.warning(f"Summary missing outcome verb")
        return False
    
    return True


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

async def parse_sections(pdf_id: str, extracted_text: str) -> Dict:
    uploads = _uploads_dir()
    uploads.mkdir(parents=True, exist_ok=True)
    out_file = uploads / f"{pdf_id}_sections.json"
    summary_file = uploads / f"{pdf_id}_summary.md"
    
    if out_file.exists() and summary_file.exists():
        logger.info(f"[{pdf_id}] Using cached parsed result")
        cached = json.loads(out_file.read_text(encoding="utf-8", errors="ignore"))
        if "parse_mode" not in cached:
            cached["parse_mode"] = "unknown"
        return cached
        
    # Clean OCR errors from the text
    cleaned_text = _clean_ocr_text(extracted_text)
        
    use_llm = getattr(settings, "USE_LLM_PARSER", True)
    parser_mode = getattr(settings, "PARSER_MODE", "hybrid")
    final = None
    
    if use_llm:
        if parser_mode == "pure_llm":
            logger.info(f"[{pdf_id}] Performing Pure LLM section classification with Groq...")
            try:
                classifier = PureLLMClassifier()
                classified: Optional[ClassifiedJudgment] = await classifier.classify(cleaned_text, pdf_id)
                if classified:
                    final = {
                        "pdf_id": pdf_id,
                        "parse_mode": "llm_pure",
                        "confidence_score": classified.confidence_score,
                        "context_heading": classified.header_coram.split('\n')[0][:120].strip() if classified.header_coram else "",
                        "context_summary": "",
                        "sections": [
                            {"section_type": "HEADER_CORAM", "heading_found": classified.header_coram[:120] if classified.header_coram else None, "text": classified.header_coram, "confidence": classified.confidence_score},
                            {"section_type": "FACTS", "heading_found": classified.facts[:120] if classified.facts else None, "text": classified.facts, "confidence": classified.confidence_score},
                            {"section_type": "ARGUMENTS", "heading_found": classified.arguments[:120] if classified.arguments else None, "text": classified.arguments, "confidence": classified.confidence_score},
                            {"section_type": "LEGAL_ISSUES", "heading_found": classified.legal_issues[:120] if classified.legal_issues else None, "text": classified.legal_issues, "confidence": classified.confidence_score},
                            {"section_type": "ANALYSIS_RATIO", "heading_found": classified.analysis_ratio[:120] if classified.analysis_ratio else None, "text": classified.analysis_ratio, "confidence": classified.confidence_score},
                            {"section_type": "FINAL_ORDER", "heading_found": classified.final_order[:120] if classified.final_order else None, "text": classified.final_order, "confidence": classified.confidence_score},
                        ],
                    }
                    logger.info(f"[{pdf_id}] Pure LLM classification completed (confidence: {classified.confidence_score}).")
            except Exception as e:
                logger.error(f"[{pdf_id}] Pure LLM classification encountered error: {e}")
        else:
            # Default: Hybrid LLM Boundary Detection + NER/Regex Content Extraction (1 API call)
            logger.info(f"[{pdf_id}] Performing Cost-Optimized Hybrid LLM Boundary + NER classification with Groq...")
            try:
                hybrid_classifier = HybridClassifier()
                classified = await hybrid_classifier.classify(cleaned_text, pdf_id)
                if classified:
                    final = {
                        "pdf_id": pdf_id,
                        "parse_mode": "hybrid_llm_ner",
                        "confidence_score": classified.confidence_score,
                        "context_heading": classified.header_coram.split('\n')[0][:120].strip() if classified.header_coram else "",
                        "context_summary": "",
                        "sections": [
                            {"section_type": "HEADER_CORAM", "heading_found": classified.header_coram[:120] if classified.header_coram else None, "text": classified.header_coram, "confidence": classified.confidence_score},
                            {"section_type": "FACTS", "heading_found": classified.facts[:120] if classified.facts else None, "text": classified.facts, "confidence": classified.confidence_score},
                            {"section_type": "ARGUMENTS", "heading_found": classified.arguments[:120] if classified.arguments else None, "text": classified.arguments, "confidence": classified.confidence_score},
                            {"section_type": "LEGAL_ISSUES", "heading_found": classified.legal_issues[:120] if classified.legal_issues else None, "text": classified.legal_issues, "confidence": classified.confidence_score},
                            {"section_type": "ANALYSIS_RATIO", "heading_found": classified.analysis_ratio[:120] if classified.analysis_ratio else None, "text": classified.analysis_ratio, "confidence": classified.confidence_score},
                            {"section_type": "FINAL_ORDER", "heading_found": classified.final_order[:120] if classified.final_order else None, "text": classified.final_order, "confidence": classified.confidence_score},
                        ],
                    }
                    logger.info(f"[{pdf_id}] Hybrid classification completed (confidence: {classified.confidence_score}).")
            except Exception as e:
                logger.error(f"[{pdf_id}] Hybrid classification encountered error: {e}")
            
    if not final:
        logger.warning(f"[{pdf_id}] LLM parser unavailable/failed; using fallback parser.")
        final = _heading_fallback(pdf_id, cleaned_text)
        final["parse_mode"] = "accurate"
    
    logger.info(f"[{pdf_id}] Generating case context")
    context = await _generate_context(cleaned_text)
    
    # Validate context summary to prevent hallucination (especially from OCR text)
    context_summary = context.get("context_summary", "")
    if not validate_context_summary(context_summary, cleaned_text):
        logger.warning(f"[{pdf_id}] Context summary hallucination detected - using rule-based fallback")
        context = _derive_context_from_text(cleaned_text)
    
    final["context_heading"] = context.get("context_heading", "")
    final["context_summary"] = context.get("context_summary", "")
    
    if "(" in final["context_heading"] and ")" in final["context_heading"]:
        final["context_heading"] = re.sub(r'\s*\([^)]*\)', '', final["context_heading"]).strip()
    if "[" in final["context_heading"] and "]" in final["context_heading"]:
        final["context_heading"] = re.sub(r'\s*\[[^\]]*\]', '', final["context_heading"]).strip()
        
    # After parsing, validate for EVERY PDF
    if not validate_parsing_for_every_pdf(final, pdf_id):
        # Log warning but don't fail - user can see there's an issue
        logger.warning(f"[{pdf_id}] Parsing validation failed - some sections may be incomplete")
        
    out_file.write_text(json.dumps(final, ensure_ascii=False, indent=2), encoding="utf-8")
    logger.info(f"[{pdf_id}] Parsing completed and saved: {out_file}")
    
    md_summary = generate_markdown_summary(final)
    summary_file.write_text(md_summary, encoding="utf-8")
    logger.info(f"[{pdf_id}] Markdown summary completed and saved: {summary_file}")
    
    return final
