"""Prompt templates for Deal Analysis generation."""

SYSTEM_PROMPT = """\
You are a senior sales advisor at Renessai, a technology consultancy. \
You have deep expertise in enterprise sales, solution design, and \
structured deal qualification.

Your task is to analyse a meeting transcript (and optional reference \
materials) and produce a structured Deal Analysis document.

Rules you MUST follow:
- Extract only facts stated or clearly implied in the provided materials.
- NEVER invent budgets, timelines, stakeholder names, or metrics.
- When information is missing or uncertain, write "Unknown / Not provided" \
for that field.
- After the Deal Analysis, list every field you marked as unknown in a \
separate MISSING INFORMATION section.
- Write in concise, professional English suitable for an internal \
sales document.
- Use bullet points for lists; keep paragraphs short.
"""

USER_TEMPLATE = """\
Analyse the materials below and produce a Deal Analysis using EXACTLY \
the following structure. Output valid JSON matching the schema described.

## Required output (JSON)

Return a single JSON object with two keys:

```
{{
  "deal_analysis": {{
    "opportunity_snapshot": {{
      "company": "...",
      "industry_segment": "...",
      "size": "...",
      "contacts": "...",
      "opportunity_name": "...",
      "stage_and_target_close": "..."
    }},
    "problem_impact": {{
      "core_problem_statement": "...",
      "business_impact": "risks, value, KPIs as described"
    }},
    "current_desired_state": {{
      "current_state": "tools, what's working/not, constraints",
      "desired_future_state": "outcomes, must-haves, nice-to-haves, non-negotiables"
    }},
    "buying_dynamics": {{
      "stakeholders_power_map": "...",
      "decision_process_timing": "...",
      "perceived_risks": "..."
    }},
    "renessai_fit": {{
      "how_renessai_solves_top_pains": "...",
      "differentiation_vs_status_quo": "...",
      "delivery_phasing_idea": "..."
    }},
    "proof_next_actions": {{
      "proof_points_to_use": "...",
      "next_steps": "..."
    }}
  }},
  "missing_info": [
    "Budget range",
    "Decision timeline",
    "..."
  ]
}}
```

For every field where the source materials do not provide the answer, \
set the value to "Unknown / Not provided" and add a short label for \
that field to the "missing_info" array.

## Source materials

{context}
"""


def format_user_prompt(context: str) -> str:
    """Format the user prompt with assembled context.

    Args:
        context: Pre-assembled context string from ContextBuilder
            (transcript + references + web content).

    Returns:
        Formatted user prompt ready to send to the LLM.
    """
    return USER_TEMPLATE.format(context=context)
