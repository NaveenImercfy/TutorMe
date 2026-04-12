import os
from google.adk.agents.llm_agent import Agent
from VideoToTutorMe.tools.segment_tool import get_segment
from VideoToTutorMe.tools.evaluate_tool import evaluate_response
from VideoToTutorMe.tools.remediation_tool import select_remediation_strategy
from VideoToTutorMe.tools.session_tool import advance_session, save_session_result

# Load Miss Lily's persona instruction from prompts/
_PROMPTS_DIR = os.path.join(os.path.dirname(__file__), "prompts")

with open(os.path.join(_PROMPTS_DIR, "miss_lily_persona.md"), "r", encoding="utf-8") as f:
    MISS_LILY_INSTRUCTION = f.read()

root_agent = Agent(
    model="gemini-2.5-flash",
    name="miss_lily",
    description=(
        "Miss Lily — AI Tutor for PTL AI Tutor Me. Guides students aged 8-16 "
        "through lesson segments using a Teach → Assess → Evaluate → Remediate loop."
    ),
    instruction=MISS_LILY_INSTRUCTION,
    tools=[
        get_segment,
        evaluate_response,
        select_remediation_strategy,
        advance_session,
        save_session_result,
    ],
)
