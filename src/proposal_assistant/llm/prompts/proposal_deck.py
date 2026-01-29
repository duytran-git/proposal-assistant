"""Prompt templates for Proposal Deck content generation."""

SYSTEM_PROMPT = """\
You are a senior proposal writer at Renessai, a technology consultancy. \
You have deep expertise in crafting compelling client proposals and \
translating deal analysis into persuasive presentation content.

Your task is to transform a Deal Analysis document into slide content \
for a 12-slide Proposal Deck.

Rules you MUST follow:
- Use the client's own language and terminology from the Deal Analysis.
- NEVER invent budgets, timelines, stakeholder names, metrics, or facts.
- When information is missing or marked as "Unknown / Not provided", \
write "[Manual input required]" for that field.
- Write in concise, professional English suitable for a client-facing proposal.
- Use bullet points for lists; keep text brief and scannable.
- For Slide 8 (Value Case), if no KPIs or metrics are available, \
set the title to "[Key metric - Manual input required]".
- Each slide's content must fit the specified layout placeholders.
"""

USER_TEMPLATE = """\
Transform the Deal Analysis below into Proposal Deck slide content. \
Output valid JSON matching the schema described.

## Required output (JSON)

Return a single JSON object with 12 slide keys. Each slide has specific \
placeholder fields based on its layout:

```
{{
  "slide_1_cover": {{
    "center_title": "[Client] x Renessai - [Project Name]",
    "subtitle": "Prepared for [Contact Name(s)]"
  }},
  "slide_2_executive_summary": {{
    "title": "Executive Summary",
    "body": "Brief synthesis of situation, stakes, and expected outcomes"
  }},
  "slide_3_client_context": {{
    "title": "Client Context & Objectives",
    "body_left": "Current State: tools, what's working/not, constraints",
    "body_right": "Desired State: outcomes, must-haves, nice-to-haves"
  }},
  "slide_4_challenges": {{
    "title": "Challenges & Business Impact",
    "body": "Core problems and their business impact (risks, value at stake)"
  }},
  "slide_5_proposed_solution": {{
    "title": "Proposed Solution",
    "subtitle": "High-level solution summary (one sentence)",
    "body": "Key capabilities and how Renessai addresses top pains"
  }},
  "slide_6_solution_scope": {{
    "title": "Solution Details & Scope",
    "body": "Must-haves, nice-to-haves, and scope boundaries"
  }},
  "slide_7_implementation": {{
    "title": "Implementation Approach",
    "body_left": "Delivery phases and key milestones",
    "body_right": "Timeline and phasing"
  }},
  "slide_8_value_case": {{
    "title": "Key metric or expected outcome (e.g., '30% cost reduction')",
    "body": "Supporting context and how this value will be achieved"
  }},
  "slide_9_commercials": {{
    "title": "Investment & Terms",
    "body": "Budget range, pricing approach, and commercial terms"
  }},
  "slide_10_risk_mitigation": {{
    "title": "Risk Mitigation",
    "body_left": "Key risks and concerns",
    "body_right": "Mitigation strategies and assurances"
  }},
  "slide_11_proof_of_success": {{
    "title": "Proven Results",
    "body": "Relevant case studies and proof points"
  }},
  "slide_12_next_steps": {{
    "title": "Next Steps",
    "body": "Concrete action items with owners and target dates"
  }}
}}
```

## Content mapping from Deal Analysis

Use the following mapping to source content:

| Slide | Source Fields |
|-------|---------------|
| 1 Cover | opportunity_snapshot.company, opportunity_snapshot.opportunity_name |
| 2 Executive Summary | Synthesize problem_impact + current_desired_state |
| 3 Client Context | current_desired_state.current_state / desired_future_state |
| 4 Challenges | problem_impact.core_problem_statement, business_impact |
| 5 Proposed Solution | renessai_fit.how_renessai_solves_top_pains, differentiation_vs_status_quo |
| 6 Solution Scope | current_desired_state.desired_future_state (must-haves, nice-to-haves) |
| 7 Implementation | renessai_fit.delivery_phasing_idea |
| 8 Value Case | problem_impact.business_impact (extract KPIs if available) |
| 9 Commercials | buying_dynamics.decision_process_timing (budget/pricing info) |
| 10 Risk Mitigation | buying_dynamics.perceived_risks |
| 11 Proof of Success | proof_next_actions.proof_points_to_use |
| 12 Next Steps | proof_next_actions.next_steps |

For any field marked "Unknown / Not provided" in the Deal Analysis, \
use "[Manual input required]" in the corresponding slide content.

## Deal Analysis

{deal_analysis}
"""


def format_user_prompt(deal_analysis: str) -> str:
    """Format the user prompt with the Deal Analysis content.

    Args:
        deal_analysis: JSON string or formatted text of the Deal Analysis.

    Returns:
        Formatted user prompt ready to send to the LLM.
    """
    return USER_TEMPLATE.format(deal_analysis=deal_analysis)
