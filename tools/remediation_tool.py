from google.adk.tools import ToolContext


def select_remediation_strategy(
    missed_concepts: list[str],
    attempt_count: int,
    blooms_level: str,
    tool_context: ToolContext,
) -> dict:
    """Choose the best remediation strategy based on what the student missed,
    how many attempts they have made, and the cognitive level of the segment.

    Strategies:
    - simplify:       Use simpler language and shorter sentences.
    - analogy:        Connect the concept to something familiar in daily life.
    - visual_emphasis: Direct attention to what is shown in the segment image.
    - step_by_step:   Break the concept into numbered steps.
    - question_led:   Ask guiding questions to lead the student to the answer.
    - full_reveal:    Provide the complete answer (attempt 3 — never leave stuck).

    Args:
        missed_concepts: List of concept strings the student did not cover.
        attempt_count: How many attempts the student has made for this segment.
        blooms_level: Cognitive level — "remember" | "understand" | "apply".

    Returns:
        A dict with strategy name and a short instruction for Miss Lily to follow.
    """
    # Attempt 3 → always reveal the full answer
    if attempt_count >= 3:
        # Add to weak concepts in state
        existing_weak = tool_context.state.get("weak_concepts", [])
        new_weak = [c for c in missed_concepts if c not in existing_weak]
        tool_context.state["weak_concepts"] = existing_weak + new_weak

        return {
            "strategy":    "full_reveal",
            "instruction": (
                "The student has reached their maximum attempts. "
                "Kindly provide the complete correct explanation using the segment "
                "narration script. Then mark these as weak concepts and move on "
                "with encouragement: " + ", ".join(missed_concepts)
            ),
            "weak_concepts_added": new_weak,
        }

    # Strategy selection matrix
    strategy_matrix = {
        # (blooms_level, attempt_count) → strategy
        ("remember",   1): "simplify",
        ("remember",   2): "question_led",
        ("understand", 1): "analogy",
        ("understand", 2): "step_by_step",
        ("apply",      1): "visual_emphasis",
        ("apply",      2): "step_by_step",
    }

    strategy = strategy_matrix.get((blooms_level, attempt_count), "simplify")

    instructions = {
        "simplify": (
            "Use simpler, shorter sentences. Avoid technical terms. "
            "Re-explain these concepts in the most basic way possible: "
            + ", ".join(missed_concepts)
        ),
        "analogy": (
            "Introduce a relatable real-life analogy to explain: "
            + ", ".join(missed_concepts)
            + ". For example: 'Think of it like...' Connect to everyday experiences "
            "the student already understands."
        ),
        "visual_emphasis": (
            "Direct the student's attention to what is visible in the segment image. "
            "Describe what they should be looking at and link it to: "
            + ", ".join(missed_concepts)
        ),
        "step_by_step": (
            "Break down the explanation into clear numbered steps — Step 1, Step 2, Step 3. "
            "Each step should cover one idea. Focus on: "
            + ", ".join(missed_concepts)
        ),
        "question_led": (
            "Ask 2–3 short guiding questions that lead the student to discover: "
            + ", ".join(missed_concepts)
            + ". Wait for their answer after each question."
        ),
    }

    return {
        "strategy":    strategy,
        "instruction": instructions[strategy],
        "missed_concepts": missed_concepts,
    }
