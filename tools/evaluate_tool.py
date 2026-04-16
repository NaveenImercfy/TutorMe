from google.adk.tools import ToolContext


def evaluate_response(
    student_response: str,
    key_concepts: list[str],
    expected_explanation: str,
    blooms_level: str,
    tool_context: ToolContext,
) -> dict:
    """Evaluate a student's response against the segment's key concepts and
    expected explanation. Returns a score from 0 to 100, per-dimension
    sub-scores, a list of missed concepts, and feedback text.

    The evaluation criteria are weighted by blooms_level:
    - remember:    coverage x2, accuracy x1, depth x0, coherence x1
    - understand:  coverage x1, accuracy x2, depth x1, coherence x1
    - apply:       coverage x1, accuracy x1, depth x2, coherence x1

    Args:
        student_response: The student's spoken or typed explanation.
        key_concepts: List of concept strings the response should cover.
        expected_explanation: The ideal answer for this segment.
        blooms_level: Cognitive level — "remember" | "understand" | "apply".

    Returns:
        A dict with score (0-100), sub_scores, missed_concepts, and feedback_text.
    """
    if not student_response or not student_response.strip():
        return {
            "score": 0,
            "sub_scores": {"coverage": 0, "accuracy": 0, "depth": 0, "coherence": 0},
            "missed_concepts": list(key_concepts),
            "feedback_text": "I didn't catch your answer. Let's try again!",
            "passed": False,
        }

    response_lower = student_response.lower()

    # --- Coverage: how many key concepts are mentioned ---
    covered = [c for c in key_concepts if c.lower() in response_lower]
    missed  = [c for c in key_concepts if c.lower() not in response_lower]
    coverage_score = int((len(covered) / len(key_concepts)) * 100) if key_concepts else 100

    # --- Accuracy: keyword overlap with expected explanation ---
    expected_words = set(expected_explanation.lower().split())
    response_words = set(response_lower.split())
    stop_words     = {"the", "a", "an", "is", "are", "was", "were", "it", "in",
                      "of", "to", "and", "for", "that", "this", "with", "not"}
    expected_key   = expected_words - stop_words
    overlap        = response_words & expected_key
    accuracy_score = int((len(overlap) / len(expected_key)) * 100) if expected_key else 50
    accuracy_score = min(accuracy_score, 100)

    # --- Depth: length and detail proxy ---
    word_count  = len(student_response.split())
    depth_score = min(int((word_count / 30) * 100), 100)

    # --- Coherence: sentence structure proxy ---
    sentence_count  = student_response.count(".") + student_response.count("!") + student_response.count("?")
    coherence_score = 100 if sentence_count >= 2 else (70 if sentence_count == 1 else 40)

    # --- Weighted total by blooms_level ---
    weights = {
        "remember":   {"coverage": 2, "accuracy": 1, "depth": 0, "coherence": 1},
        "understand": {"coverage": 1, "accuracy": 2, "depth": 1, "coherence": 1},
        "apply":      {"coverage": 1, "accuracy": 1, "depth": 2, "coherence": 1},
    }
    w = weights.get(blooms_level, weights["understand"])
    total_weight = sum(w.values()) or 1

    final_score = int(
        (coverage_score  * w["coverage"] +
         accuracy_score  * w["accuracy"] +
         depth_score     * w["depth"] +
         coherence_score * w["coherence"]) / total_weight
    )

    passed = final_score >= 65

    # --- Update attempt count in state ---
    attempt_count = tool_context.state.get("attempt_count", 0) + 1
    tool_context.state["attempt_count"] = attempt_count

    # --- Build feedback text ---
    if passed:
        feedback_text = "Great job! You covered the key ideas really well."
    elif coverage_score < 50:
        feedback_text = f"You're almost there! Try to include: {', '.join(missed[:3])}."
    else:
        feedback_text = "Good effort! Let's look at a couple of parts together."

    return {
        "score": final_score,
        "sub_scores": {
            "coverage":  coverage_score,
            "accuracy":  accuracy_score,
            "depth":     depth_score,
            "coherence": coherence_score,
        },
        "missed_concepts": missed,
        "feedback_text":   feedback_text,
        "passed":          passed,
        "attempt_count":   attempt_count,
    }
