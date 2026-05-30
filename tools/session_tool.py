import os
import json
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from google import genai
from google.genai import types
from google.adk.tools import ToolContext

_executor = ThreadPoolExecutor(max_workers=2)


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
            model="gemini-3-flash-preview",
            contents=[prompt],
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
    """Initialise session state. Call first on PREPARE_SESSION or START_SESSION.

    Args:
        video_id: Unique lesson video ID.
        images: Image URLs, one per segment.
        narration_texts: Narration scripts, one per segment.
    """
    total_segments = len(narration_texts)

    # Run metadata derivation + segment 0 image description in parallel
    from TutorMe.tools.segment_tool import _describe_image
    first_image = images[0] if images else ""

    fut_meta  = _executor.submit(_derive_segment_metadata, narration_texts)
    fut_img   = _executor.submit(_describe_image, first_image)
    metadata  = fut_meta.result()
    img_desc_0 = fut_img.result()

    tool_context.state["video_id"]               = video_id
    tool_context.state["user:language"]          = "auto"   # persists across sessions; detected from student's first reply
    tool_context.state["narration_texts"]        = narration_texts
    tool_context.state["key_concepts"]           = metadata["key_concepts"]
    tool_context.state["expected_explanations"]  = metadata["expected_explanations"]
    tool_context.state["blooms_levels"]          = metadata["blooms_levels"]
    tool_context.state["images"]                 = images
    tool_context.state["img_desc_0"]             = img_desc_0   # pre-fetched, skips Vision call in get_segment
    tool_context.state["total_segments"]         = total_segments
    tool_context.state["current_segment_index"]  = 0
    tool_context.state["phase"]                  = "teach"
    tool_context.state["attempt_count"]          = 0
    tool_context.state["segment_started_at"]     = time.time()
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
    """Complete a segment, award XP/coins, return next_action.

    XP: 50 (1st-attempt pass) | 30 (remediation pass) | 10 (participation).

    Args:
        segment_index: 0-based index of completed segment.
        passed: Whether the student passed.
        score: Evaluation score 0-100.
        weak_concepts: Concepts the student missed.
        attempts: Total attempts on this segment.
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

    # --- Record segment result with time_spent ---
    time_spent = int(time.time() - state.get("segment_started_at", time.time()))
    segment_results = state.get("segment_results", [])
    segment_results.append({
        "segment_index": segment_index,
        "score":         score,
        "attempts":      attempts,
        "passed":        passed,
        "weak_concepts": weak_concepts,
        "time_spent":    time_spent,
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
    tool_context.state["segment_started_at"]     = time.time()

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
    """Save final assessment score and compute overall mastery. Marks session complete.

    Args:
        final_score: Student's score (0-100) on the final assessment.
    """
    state           = tool_context.state
    segment_results = state.get("segment_results", [])

    # --- Compute overall mastery ---
    segment_scores = [r["score"] for r in segment_results]
    all_scores     = segment_scores + [final_score]
    overall_mastery = int(sum(all_scores) / len(all_scores)) if all_scores else final_score

    # --- Re-teach gate: if final_score < 60, revisit weakest segments ---
    if final_score < 60:
        weakest = sorted(segment_results, key=lambda r: r["score"])[:3]
        weakest_indices = [r["segment_index"] for r in weakest]
        tool_context.state["phase"]           = "reteach"
        tool_context.state["reteach_indices"] = weakest_indices
        return {
            "session_complete":        False,
            "needs_reteach":           True,
            "reteach_segment_indices": weakest_indices,
            "final_score":             final_score,
            "message":                 "Student needs to revisit weak segments before completing.",
        }

    # --- Final XP/coins for completing assessment ---
    if final_score >= 90:
        final_xp    = 300
        final_coins = 75
    elif final_score >= 80:
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
