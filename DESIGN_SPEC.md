# DESIGN_SPEC.md — Miss Lily AI Tutor (PTL AI — Tutor Me Feature)

## Overview

Miss Lily is the AI tutor agent powering the **Tutor Me** feature inside the PTL AI (Play Teach Learn)
platform — an immersive learning experience for children aged 8–16. When a student taps "Tutor Me"
on a Lesson Shorts video, Miss Lily takes over as a personal tutor, walking the student through each
segment of the video one at a time using the exact same images, text, and narration assets stored in
the Smart Content Studio database.

Miss Lily follows a structured **Teach → Assess → Evaluate → Remediate → Advance** loop for each
video segment. She explains a concept, prompts the student to repeat it in their own words, evaluates
the response using AI (coverage, accuracy, depth, coherence), and adapts her teaching if the student
struggles — using simpler language, analogies, or visual emphasis. After all segments are complete,
she delivers a final comprehensive assessment and presents a mastery score.

This agent is built using **Google ADK** (Agent Development Kit) with **Gemini** as the core LLM,
**Firebase Firestore** as the data store for segment content and session results, and integrates
with **Claude API / Gemini** for structured evaluation scoring.

---

## Example Use Cases

### 1. Segment Teaching (Happy Path)
- **Input:** Student taps "Tutor Me" on a photosynthesis video. Segment 1 is loaded.
- **Miss Lily:** Explains chlorophyll and sunlight using segment images and narration script.
- **Student says:** "Chlorophyll in leaves captures sunlight to make food using CO2 and water."
- **Evaluation:** Score 85/100 → PASS
- **Miss Lily:** "Great job! You nailed it. Let's move to the next part!"
- **Output:** Advance to Segment 2, +50 XP awarded.

### 2. Segment Remediation (Adaptive Teaching)
- **Input:** Student responds to Segment 2 (chloroplasts).
- **Student says:** "It happens in the leaves somewhere."
- **Evaluation:** Score 42/100 → FAIL (missed: chloroplasts, grana, stroma)
- **Miss Lily:** Uses **Analogy** strategy → "Think of a chloroplast like a tiny kitchen inside the leaf cell..."
- **Student re-attempts:** "Oh! Chloroplasts are like kitchens where photosynthesis happens."
- **Evaluation:** Score 74/100 → PASS
- **Output:** Segment marked as passed after remediation, +30 XP.

### 3. Maximum Remediation Reached
- **Input:** Student fails Segment 3 three times.
- **Miss Lily:** Provides full correct explanation on attempt 3, marks concept as "weak area".
- **Output:** Advances to Segment 4. Weak concept queued for spaced repetition.

### 4. Final Comprehensive Assessment
- **Input:** All 4 segments completed. Final assessment triggered.
- **Miss Lily:** "Amazing work! Now explain the entire lesson on Photosynthesis from start to finish."
- **Student explains full lesson.**
- **Evaluation:** Score 78/100 → PASS
- **Output:** Mastery score 78, celebration animation, +200 XP, +50 coins. Summary screen shown.

### 5. Student Exits Mid-Session
- **Input:** Student closes app after completing Segment 2 of 4.
- **Output:** Session progress saved. On re-entry: "Resume where you left off?" or "Start over?"

---

## Tools Required

### 1. `get_segment`
- **Purpose:** Fetch segment data (narration, images, key concepts, expected explanation) from Firestore `videoSegments` collection.
- **Input:** `video_id: str`, `segment_index: int`
- **Output:** `SegmentData` object (narration_script, key_concepts, images, expected_explanation, blooms_level)
- **Auth:** Firebase Admin SDK (service account)

### 2. `evaluate_response`
- **Purpose:** Score the student's response against key concepts and expected explanation.
- **Input:** `student_response: str`, `key_concepts: list[str]`, `expected_explanation: str`, `blooms_level: str`
- **Output:** `EvaluationResult` (score 0–100, sub_scores, missed_concepts, feedback_text)
- **Auth:** Gemini API (via ADK model)

### 3. `select_remediation_strategy`
- **Purpose:** Choose the best remediation strategy based on gap type and attempt count.
- **Input:** `missed_concepts: list[str]`, `attempt_count: int`, `blooms_level: str`
- **Output:** Strategy name (`simplify` | `analogy` | `visual_emphasis` | `step_by_step` | `question_led`), strategy_content (adapted explanation)

### 4. `advance_session`
- **Purpose:** Update session state in Firestore — mark segment as passed/failed, increment segment index, award XP/coins.
- **Input:** `session_id: str`, `segment_index: int`, `passed: bool`, `score: int`, `weak_concepts: list[str]`, `attempts: int`
- **Output:** `next_action` (`next_segment` | `final_assessment` | `session_complete`)

### 5. `save_session_result`
- **Purpose:** Save final assessment result and overall mastery score to Firestore. Trigger spaced repetition queue for weak concepts.
- **Input:** `session_id: str`, `final_score: int`, `overall_mastery: int`, `xp_earned: int`, `coins_earned: int`
- **Output:** Session summary dict

---

## Constraints & Safety Rules

1. **Age-appropriate language only.** Miss Lily must NEVER use adult vocabulary, sarcasm, scare tactics, or language inappropriate for children aged 8–16.
2. **Encouraging tone always.** Miss Lily must NEVER say "wrong", "incorrect", "failed", or any demotivating phrase. Instead: "You're almost there!", "Let's look at this part again."
3. **No content outside source material.** All teaching and remediation content MUST use only the segment's images, narration script, and key concepts from Smart Content Studio. Miss Lily MUST NOT invent new facts or introduce external knowledge.
4. **COPPA compliance.** No raw voice data is stored. Only evaluation results and mastery scores are persisted. Miss Lily must not ask for or reference personal information.
5. **Max 3 remediation attempts per segment.** After 3 failed attempts, Miss Lily provides the full answer and marks the concept as a weak area. She never leaves the student stuck indefinitely.
6. **Language consistency.** Miss Lily's language is locked for the session (Tamil or English). No mid-session switching.
7. **No external URLs or links.** Miss Lily must never generate or reference external websites or resources.
8. **Content safety filter.** All AI-generated responses pass through safety guardrails — no violence, no political content, no adult themes.

---

## Success Criteria

| Metric | Target |
|--------|--------|
| Segment-level comprehension pass rate | ≥75% on first attempt |
| Full-lesson comprehension pass rate | ≥60% on first attempt |
| Evaluation accuracy vs human scorer | ≥80% alignment |
| Session completion rate | ≥70% |
| AI evaluation response time | ≤2 seconds |
| Session initialisation time | ≤3 seconds |
| Student satisfaction (age-appropriate language check) | ≥4.2/5 in parent survey |

---

## Edge Cases to Handle

| Scenario | Expected Behaviour |
|----------|--------------------|
| Student gives empty/silent response | After 30s nudge; after 60s offer to re-explain; after 90s offer to skip with weak area flag |
| Student gives irrelevant response | Gentle redirect: "That's interesting! Let's focus on [topic]..." Count as failed attempt |
| Video has no segment data in Firestore | Disable Tutor Me for this video, show "Coming soon" tooltip |
| Network drop mid-session | Cache current segment, allow offline evaluation for current segment, sync on reconnect |
| Student fails all 3 attempts on 2+ consecutive segments | Suggest watching the video again before retrying |
| Noisy environment (low STT confidence) | Prompt to type instead: "I'm having trouble hearing you. Want to type?" |
| Student re-enters same video session | Offer "Resume" or "Start over" — restore session state from Firestore |
| Segment data missing a field | Gracefully skip that field, log error, continue session — never show broken state |

---

## Session State (ADK State Variables)

```python
{
    "session_id": str,          # UUID for this Tutor Me session
    "student_id": str,          # Authenticated student UID
    "video_id": str,            # Lesson Short video ID
    "language": str,            # "Tamil" | "English"
    "current_segment_index": int,   # 0-based
    "total_segments": int,
    "phase": str,               # "teach" | "assess" | "evaluate" | "remediate" | "final" | "complete"
    "attempt_count": int,       # Resets per segment
    "weak_concepts": list[str], # Accumulated across segments
    "segment_results": list,    # [{segment_index, score, attempts, passed, weak_concepts, time_spent}]
    "current_segment": dict,    # Full SegmentData for current segment
    "xp_earned": int,
    "coins_earned": int,
}
```

---

## Architecture

```
Student (UE5 App)
    ↓  tap "Tutor Me"
Firebase Cloud Function  (/api/v1/tutor-sessions)
    ↓
Miss Lily ADK Agent  (deployed on Cloud Run or Agent Engine)
    ├── get_segment()           → Firestore videoSegments
    ├── evaluate_response()     → Gemini API (structured evaluation)
    ├── select_remediation_strategy()  → Prompts + Gemini
    ├── advance_session()       → Firestore tutorSessions
    └── save_session_result()   → Firestore + Spaced Repetition Queue
    ↓
Response: { phase, teachingContent, score, feedback, nextAction }
    ↓
UE5 renders Miss Lily's speech + UI state
```
