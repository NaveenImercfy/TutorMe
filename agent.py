import os
from google.adk.agents.llm_agent import Agent
from google.genai import types as genai_types
from TutorMe.tools.segment_tool import get_segment
from TutorMe.tools.evaluate_tool import evaluate_response
from TutorMe.tools.remediation_tool import select_remediation_strategy
from TutorMe.tools.session_tool import setup_session, advance_session, save_session_result

_PROMPTS_DIR = os.path.join(os.path.dirname(__file__), "prompts")

with open(os.path.join(_PROMPTS_DIR, "miss_lily_persona.md"), "r", encoding="utf-8") as f:
    MISS_LILY_INSTRUCTION = f.read()

root_agent = Agent(
    model="gemini-3-flash-preview",
    name="miss_lily",
    description=(
        "Miss Lily — AI Tutor for PTL AI Tutor Me. Guides students aged 8-16 "
        "through lesson segments using a Teach → Assess → Evaluate → Remediate loop."
    ),
    instruction=MISS_LILY_INSTRUCTION,
    generate_content_config=genai_types.GenerateContentConfig(
        temperature=0.3,  # consistent, predictable JSON output
    ),
    tools=[
        setup_session,
        get_segment,
        evaluate_response,
        select_remediation_strategy,
        advance_session,
        save_session_result,
    ],
)
