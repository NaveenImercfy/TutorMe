import os
import json
from google import genai
from google.adk.tools import ToolContext


def evaluate_response(
    student_response: str,
    key_concepts: list[str],
    expected_explanation: str,
    blooms_level: str,
    tool_context: ToolContext,
) -> dict:
    """Evaluate a student's response using AI semantic scoring.

    Args:
        student_response: The student's spoken or typed explanation.
        key_concepts: List of concept strings the response should cover.
        expected_explanation: The ideal answer for this segment.
        blooms_level: Cognitive level — "remember" | "understand" | "apply".

    Returns:
        A dict with score (0-100), missed_concepts, feedback_text, and passed.
    """
    attempt_count = tool_context.state.get("attempt_count", 0) + 1
    tool_context.state["attempt_count"] = attempt_count

    if not student_response or not student_response.strip():
        return {
            "score": 0,
            "missed_concepts": list(key_concepts),
            "feedback_text": "I didn't catch your answer. Let's try again!",
            "passed": False,
            "attempt_count": attempt_count,
        }

    prompt = f"""Evaluate this student response for an AI tutoring session (ages 8–16).

Key concepts to cover: {json.dumps(key_concepts)}
Ideal explanation: {expected_explanation}
Cognitive level: {blooms_level}
Student response: {student_response}

Score 0–100 considering concept coverage, accuracy, and depth appropriate for {blooms_level} level.
Pass threshold: 70.

Return ONLY valid JSON:
{{
  "score": <0-100>,
  "missed_concepts": ["concepts not covered or incorrectly stated"],
  "feedback_text": "One short encouraging sentence for Miss Lily to say",
  "passed": <true if score >= 70>
}}"""

    try:
        client = genai.Client(api_key=os.environ.get("GOOGLE_API_KEY"))
        response = client.models.generate_content(
            model="gemini-3-flash-preview",
            contents=[prompt],
        )
        raw = response.text.strip()
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        result = json.loads(raw.strip())
    except Exception:
        # Fallback: simple keyword coverage if Gemini call fails
        response_lower = student_response.lower()
        covered = [c for c in key_concepts if c.lower() in response_lower]
        missed  = [c for c in key_concepts if c.lower() not in response_lower]
        score   = int((len(covered) / len(key_concepts)) * 100) if key_concepts else 50
        result  = {
            "score":          score,
            "missed_concepts": missed,
            "feedback_text":  "Good effort! Let's look at a couple of parts together.",
            "passed":         score >= 70,
        }

    result["attempt_count"] = attempt_count
    return result
