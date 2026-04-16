import os
import json
from google import genai
from google.genai import types
from google.adk.tools import ToolContext


def _derive_segment_metadata(narration_texts: list[str]) -> dict:
    """Use Gemini to auto-derive key_concepts, expected_explanations,
    and blooms_levels from narration texts in a single API call."""
    prompt = f"""You are an educational content analyst.
Analyse each narration segment below and return a JSON object with three arrays:
- key_concepts: array of arrays — 3 to 5 core concept strings per segment
- expected_explanations: array of strings — one ideal student answer per segment (1-2 sentences)
- blooms_levels: array of strings — one of: "remember", "understand", "apply" per segment

Narration segments:
{json.dumps(narration_texts, indent=2)}

Return ONLY valid JSON. No explanation. No markdown.
Format:
{{
  "key_concepts": [["concept1", "concept2"], ...],
  "expected_explanations": ["explanation1", ...],
  "blooms_levels": ["remember", ...]
}}"""

    try:
        client = genai.Client(api_key=os.environ.get("GOOGLE_API_KEY"))
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=[types.Part.from_text(prompt)],
        )
        raw = response.text.strip()
        # Strip markdown code fences if present
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        return json.loads(raw.strip())
    except Exception as e:
        # Safe fallback — empty concepts, Gemini will still teach from narration
        return {
            "key_concepts":          [[] for _ in narration_texts],
            "expected_explanations": ["" for _ in narration_texts],
            "blooms_levels":         ["understand" for _ in narration_texts],
        }


def setup_session(
    video_id: str,
    images: list[str],
    narration_texts: list[str],
    tool_context: ToolContext,
) -> dict:
    """Initialise the session state with segment data before teaching begins.
    Automatically derives key concepts, expected explanations, and blooms levels
    from the narration texts using AI. Language is auto-detected from the student.

    Call this tool first when the student starts a Tutor Me session.

    Args:
        video_id: The unique ID of the lesson video.
        images: List of image URLs, one per segment.
        narration_texts: List of narration scripts, one per segment.

    Returns:
        Confirmation dict with total_segments and ready status.
    """
    total_segments = len(narration_texts)

    # Auto-derive metadata from narration texts
    metadata = _derive_segment_metadata(narration_texts)

    tool_context.state["video_id"]               = video_id
    tool_context.state["language"]               = "auto"   # detected from student's first reply
    tool_context.state["narration_texts"]        = narration_texts
    tool_context.state["key_concepts"]           = metadata["key_concepts"]
    tool_context.state["expected_explanations"]  = metadata["expected_explanations"]
    tool_context.state["blooms_levels"]          = metadata["blooms_levels"]
    tool_context.state["images"]                 = images
    tool_context.state["total_segments"]         = total_segments
    tool_context.state["current_segment_index"]  = 0
    tool_context.state["phase"]                  = "teach"
    tool_context.state["attempt_count"]          = 0
    tool_context.state["xp_earned"]              = 0
    tool_context.state["coins_earned"]           = 0
    tool_context.state["weak_concepts"]          = []
    tool_context.state["segment_results"]        = []

    return {
        "status":         "ready",
        "total_segments": total_segments,
        "video_id":       video_id,
        "derived_concepts": metadata["key_concepts"],
    }


def advance_session(
    segment_index: int,
    passed: bool,
    score: int,
    weak_concepts: list[str],
    attempts: int,
    tool_context: ToolContext,
) -> dict:
    """Mark a segment as complete, update session state, award XP and coins,
    and determine the next action for Miss Lily.

    XP awards:
    - Pass on first attempt:  50 XP
    - Pass after remediation: 30 XP
    - Segment not passed:     10 XP (participation)

    Args:
        segment_index: The 0-based index of the completed segment.
        passed: Whether the student passed this segment.
        score: The final evaluation score (0-100) for this segment.
        weak_concepts: Concepts the student missed on this segment.
        attempts: Total attempts the student made on this segment.

    Returns:
        A dict with next_action ("next_segment" | "final_assessment" | "session_complete"),
        updated XP, coins, and the next segment index if applicable.
    """
    state          = tool_context.state
    total_segments = state.get("total_segments", 0)

    # --- XP logic ---
    if passed and attempts == 1:
        xp_delta    = 50
        coins_delta = 10
    elif passed:
        xp_delta    = 30
        coins_delta = 5
    else:
        xp_delta    = 10
        coins_delta = 0

    new_xp    = state.get("xp_earned", 0) + xp_delta
    new_coins = state.get("coins_earned", 0) + coins_delta

    # --- Accumulate weak concepts ---
    existing_weak = state.get("weak_concepts", [])
    merged_weak   = list(set(existing_weak + weak_concepts))

    # --- Record segment result ---
    segment_results = state.get("segment_results", [])
    segment_results.append({
        "segment_index": segment_index,
        "score":         score,
        "attempts":      attempts,
        "passed":        passed,
        "weak_concepts": weak_concepts,
    })

    next_segment_index = segment_index + 1

    # --- Determine next action ---
    if next_segment_index < total_segments:
        next_action = "next_segment"
        next_phase  = "teach"
    else:
        next_action = "final_assessment"
        next_phase  = "final"

    # --- Write updated state ---
    tool_context.state["xp_earned"]             = new_xp
    tool_context.state["coins_earned"]           = new_coins
    tool_context.state["weak_concepts"]          = merged_weak
    tool_context.state["segment_results"]        = segment_results
    tool_context.state["current_segment_index"]  = next_segment_index
    tool_context.state["attempt_count"]          = 0
    tool_context.state["phase"]                  = next_phase

    return {
        "next_action":           next_action,
        "next_segment_index":    next_segment_index if next_action == "next_segment" else None,
        "xp_earned":             new_xp,
        "coins_earned":          new_coins,
        "xp_delta":              xp_delta,
        "total_segments":        total_segments,
        "segments_completed":    next_segment_index,
        "weak_concepts":         merged_weak,
    }


def save_session_result(
    final_score: int,
    tool_context: ToolContext,
) -> dict:
    """Save the final assessment result and compute the overall mastery score.
    Marks the session as complete.

    Overall mastery is computed as the average of all segment scores plus
    the final assessment score, weighted equally.

    Args:
        final_score: The student's score (0-100) on the final assessment.

    Returns:
        A dict with overall_mastery, xp_earned, coins_earned, weak_concepts,
        and a session summary.
    """
    state           = tool_context.state
    segment_results = state.get("segment_results", [])

    # --- Compute overall mastery ---
    segment_scores = [r["score"] for r in segment_results]
    all_scores     = segment_scores + [final_score]
    overall_mastery = int(sum(all_scores) / len(all_scores)) if all_scores else final_score

    # --- Final XP/coins for completing assessment ---
    if final_score >= 80:
        final_xp    = 200
        final_coins = 50
    elif final_score >= 65:
        final_xp    = 150
        final_coins = 30
    else:
        final_xp    = 100
        final_coins = 10

    total_xp    = state.get("xp_earned", 0) + final_xp
    total_coins = state.get("coins_earned", 0) + final_coins

    # --- Mark session complete ---
    tool_context.state["phase"]          = "complete"
    tool_context.state["xp_earned"]      = total_xp
    tool_context.state["coins_earned"]   = total_coins
    tool_context.state["final_score"]    = final_score
    tool_context.state["overall_mastery"] = overall_mastery

    return {
        "session_complete":  True,
        "final_score":       final_score,
        "overall_mastery":   overall_mastery,
        "xp_earned":         total_xp,
        "coins_earned":      total_coins,
        "weak_concepts":     state.get("weak_concepts", []),
        "segments_completed": len(segment_results),
        "summary": (
            f"You completed all {len(segment_results)} segments! "
            f"Mastery score: {overall_mastery}/100. "
            f"XP earned: {total_xp}. Coins: {total_coins}."
        ),
    }
