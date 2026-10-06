import os
import json
import re
import asyncio
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from loguru import logger
from openai import AsyncOpenAI

from app.config import settings

# ============================================================================
# SECTION DEFINITIONS - For LLM Understanding
# ============================================================================

SECTION_DEFINITIONS = """
1. HEADER_CORAM - Court metadata only:
   - Court name: "IN THE SUPREME COURT OF PAKISTAN"
   - Jurisdiction: "(Appellate Jurisdiction)"
   - "PRESENT:" followed by ALL judge names
   - Case number (exact match from the PDF)
   - Appellant names (exact match)
   - Respondent names (exact match)
   - Counsel names with designations (ASC, AOR, Addl. A.G.)
   - Date of hearing
   - Lower court details

2. FACTS - Chronological narrative ONLY:
   - Procedural history in sequence
   - What happened in lower courts
   - Dates of judgments and orders
   - What each party did
   - ABSOLUTELY NO "Section" references
   - ABSOLUTELY NO case citations (PLD, SCMR)
   - ABSOLUTELY NO "we" statements
   - ABSOLUTELY NO statutory analysis

3. ARGUMENTS - Counsel submissions ONLY:
   - "Learned counsel argued/submitted/contended that..."
   - Contentions of each side
   - ABSOLUTELY NO "we" statements by court
   - ABSOLUTELY NO court reasoning

4. LEGAL_ISSUES - Case-specific questions ONLY:
   - Must be numbered: (i), (ii), (iii), etc.
   - Must start with "Whether"
   - MUST BE CASE-SPECIFIC from the judgment
   - NEVER use generic templates:
     ✗ "Whether the impugned judgment is sustainable?"
     ✗ "Whether the petitioner is entitled to relief?"
   - Extract from leave granting order if present
   - Extract from court's reasoning

5. ANALYSIS_RATIO - Court reasoning ALL:
   - "We have heard/considered"
   - "In our view/opinion"
   - Statutory text quoted by court
   - Case citations (PLD, SCMR)
   - Latin maxims
   - Legal principles
   - Interpretation of law
   - ALL analysis by the court

6. FINAL_ORDER - Outcome ONLY:
   - 1-3 sentences
   - "Appeal allowed/dismissed"
   - "Judgment set aside"
   - "Petition dismissed"
   - NO reasoning
   - NO "Announced in open court"
   - NO "Approved for reporting"
   - NO judge signatures
"""

# ============================================================================
# LLM SYSTEM PROMPT - The FULL instruction
# ============================================================================

SYSTEM_PROMPT = f"""You are a Pakistan Supreme Court judgment section classifier. Your task is to parse a judgment and extract exactly 6 sections.

## THE 6 SECTIONS YOU MUST EXTRACT:

{SECTION_DEFINITIONS}

## CRITICAL RULES:

1. **NO EMPTY SECTIONS** - Every section must have content. If a section would be empty, put the most relevant content there.

2. **USE EXACT TEXT** - Copy text VERBATIM from the judgment. DO NOT summarize or paraphrase.

3. **PRESERVE FORMATTING** - Keep paragraph breaks, numbering, and quoted text.

4. **CLASSIFICATION PRIORITY:**
   - HEADER_CORAM: Beginning of document until "JUDGMENT" or first "J.:"
   - FACTS: After HEADER_CORAM until FIRST "we" statement or statutory analysis
   - ARGUMENTS: "Learned counsel" paragraphs
   - LEGAL_ISSUES: Numbered questions or implicit issues from the case
   - ANALYSIS_RATIO: ALL court reasoning, statutory text, case law
   - FINAL_ORDER: Last 1-3 paragraphs before "JUDGE" lines

5. **FACTS ABSOLUTELY CANNOT CONTAIN:**
   - "Section" references (e.g., "Section 23 of the Ordinance")
   - Case citations (e.g., "2015 SCMR 1488")
   - "We have heard" or any "we" statement
   - Any court analysis or reasoning

6. **LEGAL_ISSUES MUST BE CASE-SPECIFIC:**
   - Extract from: leave granting order, arguments, facts, or analysis
   - NEVER use: "Whether the impugned judgment is sustainable?"
   - ALWAYS be specific: "Whether the Banking Court established under the repealed Act can be considered as 'the Banking Court' for purposes of Section 23(2) of the 2001 Ordinance?"

## OUTPUT FORMAT:

Return ONLY valid JSON with this exact structure:
{{
  "sections": [
    {{"section_type": "HEADER_CORAM", "text": "extracted text"}},
    {{"section_type": "FACTS", "text": "extracted text"}},
    {{"section_type": "ARGUMENTS", "text": "extracted text"}},
    {{"section_type": "LEGAL_ISSUES", "text": "extracted text"}},
    {{"section_type": "ANALYSIS_RATIO", "text": "extracted text"}},
    {{"section_type": "FINAL_ORDER", "text": "extracted text"}}
  ]
}}

DO NOT include any other text, explanation, or commentary."""


@dataclass
class ClassifiedJudgment:
    pdf_id: str
    header_coram: str
    facts: str
    arguments: str
    legal_issues: str
    analysis_ratio: str
    final_order: str
    parse_mode: str = "llm_pure"
    confidence_score: float = 0.0


MAX_CHUNK_SIZE = 6000


class PureLLMClassifier:
    """Pure LLM-based section classifier with no fallback."""

    def __init__(self):
        self.api_key = settings.GROQ_API_KEY or os.getenv("GROQ_API_KEY")
        self.model = settings.GROQ_MODEL or "llama-3.3-70b-versatile"
        self.client = None

        if not self.api_key:
            raise ValueError("GROQ_API_KEY is required in settings or .env")

    def _get_client(self) -> AsyncOpenAI:
        if self.client is None:
            self.client = AsyncOpenAI(
                base_url=settings.GROQ_BASE_URL or "https://api.groq.com/openai/v1",
                api_key=self.api_key,
                max_retries=3,
            )
        return self.client

    def _chunk_text(self, text: str, max_chunk_size: int = MAX_CHUNK_SIZE) -> List[str]:
        """Split text into manageable chunks for LLM within API token limits."""
        if len(text) <= max_chunk_size:
            return [text]

        chunks = []
        paragraphs = re.split(r'\n\s*\n', text)
        current_chunk = ""

        for para in paragraphs:
            if len(current_chunk) + len(para) + 2 > max_chunk_size:
                if current_chunk:
                    chunks.append(current_chunk.strip())
                current_chunk = para
            else:
                if current_chunk:
                    current_chunk += "\n\n" + para
                else:
                    current_chunk = para

        if current_chunk:
            chunks.append(current_chunk.strip())

        return chunks

    def _is_empty_or_placeholder(self, text: str) -> bool:
        """Check if text is a placeholder indicating section not present in a chunk."""
        t = text.lower().strip()
        placeholders = [
            "not available", "no header", "no facts", "no arguments",
            "no legal issues", "no analysis", "no final order", "none in this chunk",
            "not applicable", "n/a", "not present", "none"
        ]
        return any(p in t for p in placeholders) and len(t) < 80

    def _merge_chunk_results(self, chunk_results: List[Dict]) -> Dict[str, str]:
        """Merge results from multiple chunks into final sections."""
        merged = {
            "HEADER_CORAM": "",
            "FACTS": "",
            "ARGUMENTS": "",
            "LEGAL_ISSUES": "",
            "ANALYSIS_RATIO": "",
            "FINAL_ORDER": "",
        }

        for result in chunk_results:
            for section in result.get("sections", []):
                st = section.get("section_type")
                text = section.get("text", "").strip()
                if st in merged and text and not self._is_empty_or_placeholder(text):
                    if merged[st]:
                        if st == "HEADER_CORAM" and len(merged[st]) > 200:
                            continue
                        if st == "FINAL_ORDER" and len(text) > 30:
                            merged[st] = text
                        else:
                            merged[st] += "\n\n" + text
                    else:
                        merged[st] = text

        return merged

    async def classify_chunk(self, chunk: str, chunk_index: int, total_chunks: int = 1) -> Dict:
        """Classify a single text chunk using Groq API with TPM rate-limit retry."""
        client = self._get_client()

        # Trim chunk if needed to stay well within TPM
        if len(chunk) > MAX_CHUNK_SIZE:
            chunk = chunk[:MAX_CHUNK_SIZE]

        max_attempts = 3
        for attempt in range(max_attempts):
            try:
                response = await client.chat.completions.create(
                    model=self.model,
                    messages=[
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {
                            "role": "user",
                            "content": f"Parse this Pakistan Supreme Court judgment chunk ({chunk_index + 1} of {total_chunks}):\n\n{chunk}",
                        },
                    ],
                    temperature=0.0,
                    max_tokens=3000,
                    response_format={"type": "json_object"},
                )

                raw_text = response.choices[0].message.content or ""
                cleaned = self._clean_json_response(raw_text)
                return json.loads(cleaned)

            except Exception as e:
                err_str = str(e).lower()
                if "rate_limit" in err_str or "413" in err_str or "429" in err_str or "tpm" in err_str:
                    wait_time = 2.5 * (attempt + 1)
                    logger.warning(f"Groq TPM limit reached for chunk {chunk_index}, retrying in {wait_time}s... ({e})")
                    await asyncio.sleep(wait_time)
                else:
                    logger.error(f"Chunk {chunk_index} classification error: {e}")
                    if attempt == max_attempts - 1:
                        return {"sections": []}
                    await asyncio.sleep(1.0)

        return {"sections": []}

    def _clean_json_response(self, raw: str) -> str:
        """Clean JSON from LLM response."""
        raw = raw.strip()
        raw = re.sub(r'```json\s*', '', raw)
        raw = re.sub(r'```\s*', '', raw)

        first = raw.find("{")
        last = raw.rfind("}")
        if first != -1 and last != -1 and last > first:
            return raw[first:last + 1]
        return raw

    async def classify(self, text: str, pdf_id: str) -> Optional[ClassifiedJudgment]:
        """
        Main classification method - pure LLM, no fallback.
        """
        if not text or len(text.strip()) < 100:
            logger.error(f"[{pdf_id}] Text too short for classification")
            return None

        # Step 1: Validate text content
        validation_result = self._validate_text_content(text, pdf_id)
        if not validation_result["valid"]:
            logger.warning(f"[{pdf_id}] Text validation note: {validation_result['reason']}")

        # Step 2: Chunk text
        chunks = self._chunk_text(text)
        logger.info(f"[{pdf_id}] Split text into {len(chunks)} chunk(s)")

        # Step 3: Classify each chunk
        chunk_results = []
        for i, chunk in enumerate(chunks):
            logger.info(f"[{pdf_id}] Classifying chunk {i + 1}/{len(chunks)} with {self.model}...")
            result = await self.classify_chunk(chunk, i, len(chunks))
            chunk_results.append(result)

        # Step 4: Merge results
        merged = self._merge_chunk_results(chunk_results)

        # Step 5: Validate sections
        validation = self._validate_sections(merged, text)

        # Step 6: Build result
        return ClassifiedJudgment(
            pdf_id=pdf_id,
            header_coram=merged.get("HEADER_CORAM", "").strip(),
            facts=merged.get("FACTS", "").strip(),
            arguments=merged.get("ARGUMENTS", "").strip(),
            legal_issues=merged.get("LEGAL_ISSUES", "").strip(),
            analysis_ratio=merged.get("ANALYSIS_RATIO", "").strip(),
            final_order=merged.get("FINAL_ORDER", "").strip(),
            confidence_score=validation["confidence"],
        )

    def _validate_text_content(self, text: str, pdf_id: str) -> Dict:
        """
        Validate that the text contains expected Supreme Court judgment content.
        """
        text_upper = text[:2500].upper()

        if "SUPREME COURT OF PAKISTAN" not in text_upper and "IN THE SUPREME COURT" not in text_upper:
            return {"valid": False, "reason": "Missing Supreme Court header"}

        judge_patterns = [
            r"MR\. JUSTICE",
            r"JUSTICE",
            r"CJ",
            r"HCJ",
            r"J\.",
        ]
        has_judge = any(re.search(p, text_upper) for p in judge_patterns)
        if not has_judge:
            return {"valid": False, "reason": "No judge designation found in text"}

        case_patterns = [
            r"CIVIL APPEAL",
            r"CRIMINAL APPEAL",
            r"CONSTITUTION PETITION",
            r"C\.?\s*A\.?",
            r"C\.?\s*P\.?",
            r"CPLA",
        ]
        has_case = any(re.search(p, text_upper) for p in case_patterns)
        if not has_case:
            return {"valid": False, "reason": "No case number pattern found"}

        return {"valid": True, "reason": "Text validation passed"}

    def _validate_sections(self, sections: Dict[str, str], source_text: str) -> Dict:
        """
        Validate that sections are correctly classified.
        Returns validation results and confidence score.
        """
        issues = []
        confidence = 0.9

        # Check 1: FACTS should NOT contain excessive statutory text
        facts = sections.get("FACTS", "").lower()
        if facts:
            section_refs = re.findall(r"\bsection\s+\d+", facts)
            if len(section_refs) > 5:
                issues.append("FACTS contains too many 'Section' references")
                confidence -= 0.15

        # Check 2: LEGAL_ISSUES should contain questions
        issues_text = sections.get("LEGAL_ISSUES", "")
        if issues_text:
            has_numbered = re.search(r"\([ivx0-9]+\)", issues_text, re.I)
            has_whether = "whether" in issues_text.lower()
            if not has_numbered and not has_whether:
                issues.append("LEGAL_ISSUES missing numbered questions or 'Whether'")
                confidence -= 0.1

        # Check 3: FINAL_ORDER must contain outcome
        final_text = sections.get("FINAL_ORDER", "").lower()
        if final_text:
            outcome_verbs = ["allowed", "dismissed", "set aside", "disposed", "remanded", "refused", "bail"]
            if not any(v in final_text for v in outcome_verbs):
                issues.append("FINAL_ORDER missing standard outcome verbs")
                confidence -= 0.1

        # Check 4: ANALYSIS_RATIO must contain analysis markers
        analysis_text = sections.get("ANALYSIS_RATIO", "").lower()
        if analysis_text:
            markers = ["we have", "in our view", "we are of", "we find", "we hold", "learned", "section", "held"]
            if not any(m in analysis_text for m in markers):
                issues.append("ANALYSIS_RATIO missing analysis markers")
                confidence -= 0.15

        # Check 5: Critical sections not empty
        for st in ["HEADER_CORAM", "FACTS", "LEGAL_ISSUES", "ANALYSIS_RATIO", "FINAL_ORDER"]:
            if not sections.get(st, "").strip():
                issues.append(f"{st} is empty")
                confidence -= 0.1

        return {
            "valid": len(issues) < 3,
            "issues": issues,
            "confidence": round(max(0.0, min(1.0, confidence)), 2),
        }
