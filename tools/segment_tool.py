import os
import requests
from google import genai
from google.genai import types
from google.adk.tools import ToolContext

_VISION_PROMPT = (
    "You are helping an AI tutor teach students aged 8-16. "
    "Describe the educational content in this image clearly and specifically — "
    "include all numbers, statistics, labels, diagrams, and key concepts visible. "
    "Keep it concise (3-5 sentences)."
)


def _describe_image(image_url: str) -> str:
    """Pass image URL directly to Gemini Vision and get an educational description."""
    try:
        client = genai.Client(api_key=os.environ.get("GOOGLE_API_KEY"))
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=[
                types.Part.from_uri(file_uri=image_url, mime_type="image/png"),
                types.Part.from_text(_VISION_PROMPT),
            ],
        )
        return response.text
    except Exception:
        # Fallback: fetch bytes if direct URL not supported
        try:
            img_bytes = requests.get(image_url, timeout=10).content
            client = genai.Client(api_key=os.environ.get("GOOGLE_API_KEY"))
            response = client.models.generate_content(
                model="gemini-2.5-flash",
                contents=[
                    types.Part.from_bytes(data=img_bytes, mime_type="image/png"),
                    types.Part.from_text(_VISION_PROMPT),
                ],
            )
            return response.text
        except Exception as e:
            return f"Image available on screen. (Description unavailable: {e})"


def get_segment(segment_index: int, tool_context: ToolContext) -> dict:
    """Get the narration text, image description, key concepts, expected explanation,
    and blooms level for a given segment index from the current session state.

    Args:
        segment_index: The 0-based index of the segment to retrieve.

    Returns:
        A dict with segment data, or an error message if index is out of range.
    """
    state = tool_context.state

    narration_texts       = state.get("narration_texts", [])
    images                = state.get("images", [])
    key_concepts          = state.get("key_concepts", [])
    expected_explanations = state.get("expected_explanations", [])
    blooms_levels         = state.get("blooms_levels", [])
    total_segments        = len(narration_texts)

    if not narration_texts:
        return {"error": "No segment data found in session state."}

    if segment_index < 0 or segment_index >= total_segments:
        return {"error": f"segment_index {segment_index} is out of range. Total segments: {total_segments}"}

    image_url = images[segment_index] if segment_index < len(images) else None

    # Use cached image description if available, otherwise fetch and describe
    cache_key = f"img_desc_{segment_index}"
    if cache_key in state:
        image_description = state[cache_key]
    elif image_url:
        image_description = _describe_image(image_url)
        tool_context.state[cache_key] = image_description  # cache for this session
    else:
        image_description = None

    return {
        "segment_index":        segment_index,
        "total_segments":       total_segments,
        "narration_script":     narration_texts[segment_index],
        "image_url":            image_url,
        "image_description":    image_description,
        "key_concepts":         key_concepts[segment_index] if segment_index < len(key_concepts) else [],
        "expected_explanation": expected_explanations[segment_index] if segment_index < len(expected_explanations) else "",
        "blooms_level":         blooms_levels[segment_index] if segment_index < len(blooms_levels) else "understand",
    }
