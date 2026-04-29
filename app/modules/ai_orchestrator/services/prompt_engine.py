from app.modules.ai_orchestrator.schemas import (
    LearningContextDTO,
    PersonalizedQuizContext,
    TopicContext,
)

PROMPT_VERSIONS = {"quiz": "v2", "gap_analysis": "v1", "content_expansion": "v1"}


def _truncate(text: str, max_length: int = 100) -> str:
    """Helper to truncate strings cleanly."""
    if not text:
        return ""
    return text[: max_length - 3] + "..." if len(text) > max_length else text


def _append_learning_context(
    base_prompt: str,
    learning_context: LearningContextDTO | None,
    level_instruction: str,
    gaps_intro: str,
    gaps_rule: str,
) -> str:
    """
    Appends the target audience profile and gaps to the user prompt if a learning context is provided.
    """
    if not learning_context:
        return base_prompt

    prompt = base_prompt + "\n**Target Audience Profile:**\n"
    level_text = f" {level_instruction}" if level_instruction else ""
    prompt += f"- User Level: {learning_context.user_level}{level_text}\n"
    gaps = learning_context.concept_gaps

    if gaps:
        prompt += f"- {gaps_intro}\n"
        for gap in gaps:
            prompt += f"  * {gap}\n"
        prompt += f"\n*Rule: {gaps_rule}*\n"

    return prompt


def _format_historical_context(context: TopicContext) -> str:
    """
    Extracts and formats historical context efficiently to prevent token bloat
    and reduce LLM hallucinations.
    """
    parts = []
    parts.append(f"**Historical Context:**")
    parts.append(f"- Period: {context.period_name}")
    parts.append(f"- Topic: {context.topic_name}")

    if context.topic_description:
        parts.append(f"- Description: {_truncate(context.topic_description, 250)}")

    events = context.events

    if events:
        parts.append("- Key Events:")
        for ev in events:
            year_info = f" ({ev.year})" if ev.year else ""
            parts.append(f"  * {ev.name}{year_info}: {_truncate(ev.description, 100)}")

    figures = context.figures

    if figures:
        parts.append("- Key Figures:")
        for fig in figures:
            role_info = f" ({fig.role})" if fig.role else ""
            parts.append(f"  * {fig.name}{role_info}: {_truncate(fig.biography, 100)}")

    return "\n".join(parts)


def build_personalized_quiz_prompt(
    context: PersonalizedQuizContext, learning_context: LearningContextDTO
) -> tuple[str, str]:
    """
    Builds the system and user prompts for generating a personalized quiz.
    Returns: (system_prompt, user_prompt)
    """
    topic_name = context.topic_name
    historical_context = (
        f"**Historical Context:**\n"
        f"- Summary: {context.summary}\n"
        f"- Key Facts: {', '.join(context.key_facts)}\n"
        f"- Fun Fact: {context.fun_fact}"
    )
    system_prompt = (
        "You are an expert history teacher creating educational content. "
        "Output a strictly valid JSON object with a 'questions' array. "
        "Each question object must have: "
        "'text' (string, the question), "
        "'options' (array of exactly 4 strings), "
        "'correct_index' (integer 0-3 indicating the correct option), "
        "'concept' (string, a short 2-5 word name for the specific historical concept being tested, e.g. 'Causes of the Revolution' or 'Key Dates').\n\n"
        "CRITICAL RULE: All questions MUST be strictly answerable using ONLY the information provided in the Historical Context below. Do NOT introduce external facts or ask about details not mentioned.\n\n"
        f"{historical_context}"
    )
    user_prompt = (
        f"Generate a quiz with 5 questions for the historical topic: {topic_name}.\n"
    )
    user_prompt = _append_learning_context(
        base_prompt=user_prompt,
        learning_context=learning_context,
        level_instruction="(Adjust language complexity accordingly)",
        gaps_intro="Known Weaknesses (Focus heavily on testing these concepts to help them improve):",
        gaps_rule="At least 2 questions must explicitly test the user's weaknesses to help them overcome concept gaps.",
    )

    print("\n" + "=" * 50)
    print("=== QUIZ PROMPTS ===")
    print("SYSTEM PROMPT:")
    print(system_prompt)
    print("\nUSER PROMPT:")
    print(user_prompt)
    print("=" * 50 + "\n")

    return system_prompt, user_prompt


def build_gap_analysis_prompt(
    context: TopicContext, learning_context: LearningContextDTO
) -> tuple[str, str]:
    """
    Builds the system and user prompts for gap analysis.
    """
    historical_context = _format_historical_context(context)
    system_prompt = (
        "You are an AI tutor analyzing student errors. "
        "Output a strictly valid JSON object with a 'concept_gaps' array. "
        "Each gap object must have: "
        "'concept' (string, the core topic they are failing at), "
        "'explanation' (string, brief explanation of why they might be confused), "
        "'severity' (string: 'low', 'medium', or 'high').\n\n"
        f"{historical_context}"
    )
    user_prompt = (
        "Based on the historical context, analyze the following pre-identified concept gaps for the student. "
        f"Provide a brief explanation and severity for each gap related to the topic: {context.topic_name}.\n"
    )
    user_prompt = _append_learning_context(
        base_prompt=user_prompt,
        learning_context=learning_context,
        level_instruction="",
        gaps_intro="Identified Concept Gaps (You MUST ONLY analyze these exact concepts):",
        gaps_rule="CRITICAL: Your output 'concept_gaps' array must contain EXACTLY the concepts listed above. Do not invent new concepts or omit any. Provide an explanation and severity for each of these specific gaps.",
    )

    print("\n" + "=" * 50)
    print("=== GAP ANALYSIS PROMPTS ===")
    print("SYSTEM PROMPT:")
    print(system_prompt)
    print("\nUSER PROMPT:")
    print(user_prompt)
    print("=" * 50 + "\n")

    return system_prompt, user_prompt


def build_content_expansion_prompt(
    context: TopicContext, learning_context: LearningContextDTO
) -> tuple[str, str]:
    """
    Builds the system and user prompts for content expansion.
    """
    historical_context = _format_historical_context(context)
    system_prompt = (
        "You are an expert historian. Output a strictly valid JSON object with a 'content' object. "
        "The 'content' object must have: "
        "'summary' (string, 2 paragraphs max), "
        "'key_facts' (array of strings), "
        "'fun_fact' (string).\n\n"
        f"{historical_context}"
    )
    user_prompt = f"Provide an engaging expansion for the {context.period_name} of {context.topic_name}'. Make sure the expansion is coherent with the overarching historical background provided.\n"
    user_prompt = _append_learning_context(
        base_prompt=user_prompt,
        learning_context=learning_context,
        level_instruction="(Adjust depth and vocabulary to match this level)",
        gaps_intro="Known Weaknesses (Take extra care to clearly explain these concepts if they are relevant to the expansion):",
        gaps_rule="If the expansion touches on any of these weaknesses, emphasize clarity to help the user overcome them.",
    )

    print("\n" + "=" * 50)
    print("=== CONTENT EXPANSION PROMPTS ===")
    print("SYSTEM PROMPT:")
    print(system_prompt)
    print("\nUSER PROMPT:")
    print(user_prompt)
    print("=" * 50 + "\n")

    return system_prompt, user_prompt
