"""
LangGraph workflow for DiagnosticCouncil parallel opinion generation.

Graph topology:
  START → initialize
        → [Send×N] generate_r1_opinion  (parallel fan-out via Send API)
        → calculate_consensus
        → run_pubmed
        ├─ [iterative + rare_diagnoses] → [Send×N] generate_r2_opinion → calculate_r2_consensus → END
        └─ [standard or no rare dx]                                                              → END
"""
from __future__ import annotations

import json
import operator
import random
import re
from typing import Annotated, Literal

from typing_extensions import TypedDict
from langgraph.graph import StateGraph, START, END
from langgraph.types import Send

from .council import (
    ConsensusStrength,
    DiagnosticOpinion,
    _calc_consensus,
    _get_diagnoses,
    _synth_discussion,
)


# ── State schema ──────────────────────────────────────────────────────────────

class CouncilState(TypedDict):
    # ── inputs ───────────────────────────────────────────────────────────────
    case_info: dict          # {symptoms, patient_history, imaging_findings, vitals}
    num_rollouts: int
    mode: Literal["standard", "iterative"]

    # ── Round-1 fan-out accumulator ───────────────────────────────────────────
    opinions: Annotated[list[dict], operator.add]

    # ── Round-1 results ───────────────────────────────────────────────────────
    consensus_diagnosis: str | None
    consensus_strength: str
    consensus_confidence: float
    discussion_summary: str

    # ── PubMed results ────────────────────────────────────────────────────────
    pubmed_insights: dict
    rare_diagnoses: list[str]

    # ── Round-2 fan-out accumulator ───────────────────────────────────────────
    r2_opinions: Annotated[list[dict], operator.add]

    # ── Round-2 results ───────────────────────────────────────────────────────
    r2_consensus_diagnosis: str | None
    r2_consensus_strength: str
    r2_consensus_confidence: float
    r2_discussion_summary: str


# ── Graph factory ─────────────────────────────────────────────────────────────

def build_council_graph(agent=None, pubmed_agent=None):
    """
    Build and compile the council StateGraph.
    agent and pubmed_agent are captured via closure.
    """

    # ── helpers ───────────────────────────────────────────────────────────────

    def _make_opinion_dict(
        opinion_id: str,
        symptoms: list[str],
        idx: int,
        evidence_ctx: list[str] | None,
    ) -> dict:
        """Generate one diagnostic opinion dict, calling agent if available."""
        if agent is None:
            possible = _get_diagnoses(symptoms)
            primary = possible[idx % len(possible)]
            conf = round(
                0.75 + random.random() * 0.2 + primary.get("confidence_boost", 0), 2
            )
            return {
                "opinion_id": opinion_id,
                "diagnosis": primary["name"],
                "confidence": conf,
                "confidence_percent": f"{int(conf * 100)}%",
                "reasoning": primary["reasoning"],
                "differential_diagnoses": [
                    d["name"] for d in possible if d["name"] != primary["name"]
                ][:3],
                "recommended_tests": primary.get("tests", ["CBC", "BMP"]),
                "urgency": primary.get("urgency", "routine"),
            }

        # Build prompt
        case_info = {}  # resolved in node closure
        prompt = f"""[opinion_id={opinion_id}] Medical diagnostic AI council member.
Provide your independent diagnostic assessment as JSON.
Return EXACTLY ONE valid JSON object:
{{
  "name": "Diagnosis Name",
  "reasoning": "Brief clinical reasoning (1-2 sentences)",
  "confidence": 0.85,
  "differential_diagnoses": ["Alt1", "Alt2"],
  "recommended_tests": ["Test1", "Test2"],
  "urgency": "routine"
}}
Note: urgency MUST be one of: "routine", "urgent", "emergent"."""

        if evidence_ctx:
            rare_list = "\n".join(f"• {d}" for d in evidence_ctx)
            prompt += (
                f"\n\nPubMed case reports identified these rare diagnoses for similar "
                f"presentations:\n{rare_list}\n"
                f"Consider whether any fit this case better than the common alternative."
            )

        return prompt  # sentinel — caller handles agent call

    # ── nodes ─────────────────────────────────────────────────────────────────

    def initialize(state: CouncilState) -> dict:
        """Ensure accumulators start empty (LangGraph merges via operator.add)."""
        return {"opinions": [], "r2_opinions": []}

    def _opinion_node(state: CouncilState) -> dict:
        """
        Shared opinion-generation logic for both rounds.
        Uses _round and _opinion_idx from state to distinguish.
        """
        idx: int = state["_opinion_idx"]           # type: ignore[typeddict-item]
        round_num: int = state.get("_round", 1)     # type: ignore[typeddict-item]
        evidence_ctx = state.get("rare_diagnoses", []) if round_num == 2 else None

        prefix = "ITER-R2-OPINION" if round_num == 2 else "OPINION"
        opinion_id = f"{prefix}-{idx + 1}"

        case_info = state["case_info"]
        symptoms: list[str] = case_info.get("symptoms", [])
        history: str = case_info.get("patient_history", "")
        imaging: str = case_info.get("imaging_findings", "")
        vitals = case_info.get("vitals", {})

        if agent is None:
            possible = _get_diagnoses(symptoms)
            primary = possible[idx % len(possible)]
            conf = round(
                0.75 + random.random() * 0.2 + primary.get("confidence_boost", 0), 2
            )
            opinion = {
                "opinion_id": opinion_id,
                "diagnosis": primary["name"],
                "confidence": conf,
                "confidence_percent": f"{int(conf * 100)}%",
                "reasoning": primary["reasoning"],
                "differential_diagnoses": [
                    d["name"] for d in possible if d["name"] != primary["name"]
                ][:3],
                "recommended_tests": primary.get("tests", ["CBC", "BMP"]),
                "urgency": primary.get("urgency", "routine"),
            }
        else:
            prompt = (
                f"You are a medical diagnostic AI participating in a diagnostic council.\n"
                f"Analyze the following patient case and provide your assessment:\n"
                f"Symptoms: {', '.join(symptoms)}\n"
                f"History: {history}\n"
                f"Imaging: {imaging}\n"
                f"Vitals: {vitals}\n\n"
                f"Provide exactly 1 primary diagnosis and up to 3 differential diagnoses.\n"
                f"Return EXACTLY ONE valid JSON object matching this exact schema and NOTHING ELSE:\n"
                f'{{\n'
                f'  "name": "Diagnosis Name",\n'
                f'  "reasoning": "Brief clinical reasoning (1-2 sentences)",\n'
                f'  "confidence": 0.85,\n'
                f'  "differential_diagnoses": ["Alt1", "Alt2", "Alt3"],\n'
                f'  "recommended_tests": ["Test1", "Test2"],\n'
                f'  "urgency": "routine"\n'
                f'}}\n'
                f'Note: "urgency" MUST be one of: "routine", "urgent", "emergent".'
            )

            if evidence_ctx:
                rare_list = "\n".join(f"• {d}" for d in evidence_ctx)
                prompt += (
                    f"\n\nPublished case report literature has identified these rare "
                    f"diagnoses for similar presentations:\n{rare_list}\n"
                    f"Consider whether any of these rare diagnoses fit this case better "
                    f"than the most common alternative."
                )

            try:
                if hasattr(agent, "process_query"):
                    result = agent.process_query(query=prompt, patient_context=None)
                    response_text = result.get("response", "")
                else:
                    response_text = agent.chat(prompt)

                json_match = re.search(r"```(?:json)?(.*?)```", response_text, re.DOTALL)
                if json_match:
                    response_text = json_match.group(1)
                response_text = (
                    response_text.replace("[Simulated] Processed query: ", "").strip()
                )
                if response_text.endswith("."):
                    response_text = response_text[:-1]

                r = json.loads(response_text)
                conf = float(r.get("confidence", 0.5))
                opinion = {
                    "opinion_id": opinion_id,
                    "diagnosis": r.get("name", "Unknown Diagnosis"),
                    "confidence": conf,
                    "confidence_percent": f"{int(conf * 100)}%",
                    "reasoning": r.get("reasoning", "No reasoning provided."),
                    "differential_diagnoses": r.get("differential_diagnoses", []),
                    "recommended_tests": r.get("recommended_tests", []),
                    "urgency": r.get("urgency", "routine"),
                }
            except Exception as e:
                print(f"[graph] Agent error for {opinion_id}: {e}. Using mock fallback.")
                possible = _get_diagnoses(symptoms)
                primary = possible[idx % len(possible)]
                conf = round(0.75 + random.random() * 0.2, 2)
                opinion = {
                    "opinion_id": opinion_id,
                    "diagnosis": primary["name"],
                    "confidence": conf,
                    "confidence_percent": f"{int(conf * 100)}%",
                    "reasoning": primary["reasoning"] + " (mock fallback)",
                    "differential_diagnoses": [
                        d["name"] for d in possible if d["name"] != primary["name"]
                    ][:3],
                    "recommended_tests": primary.get("tests", ["CBC", "BMP"]),
                    "urgency": primary.get("urgency", "routine"),
                }

        # Round 1 → goes into `opinions`, Round 2 → goes into `r2_opinions`
        key = "r2_opinions" if round_num == 2 else "opinions"
        return {key: [opinion]}

    def calculate_consensus(state: CouncilState) -> dict:
        """Calculate Round-1 consensus from accumulated opinions."""
        opinions = [
            DiagnosticOpinion(
                opinion_id=o["opinion_id"],
                diagnosis=o["diagnosis"],
                confidence=o["confidence"],
                reasoning=o["reasoning"],
                differential_diagnoses=o.get("differential_diagnoses", []),
                recommended_tests=o.get("recommended_tests", []),
                urgency=o["urgency"],
            )
            for o in state["opinions"]
        ]
        diag, strength, conf = _calc_consensus(opinions)
        discussion = _synth_discussion(opinions, diag or "")
        return {
            "consensus_diagnosis": diag,
            "consensus_strength": strength.value,
            "consensus_confidence": conf,
            "discussion_summary": discussion,
        }

    def run_pubmed(state: CouncilState) -> dict:
        """Query PubMed Zebra Hunt and extract rare diagnoses."""
        if pubmed_agent is None:
            return {"pubmed_insights": {}, "rare_diagnoses": []}

        symptoms: list[str] = state["case_info"].get("symptoms", [])
        try:
            pm = pubmed_agent.case_matcher(
                common_symptoms=symptoms[:3],
                atypical_markers=symptoms[3:],
                max_results=4,
            )
            return {
                "pubmed_insights": {
                    "status": "completed",
                    "summary": pm.summary,
                    "rare_diagnoses": pm.rare_diagnoses,
                    "key_findings": pm.key_findings,
                    "citation_list": pm.citation_list,
                    "query_used": pm.query_used,
                    "article_count": len(pm.articles),
                },
                "rare_diagnoses": pm.rare_diagnoses or [],
            }
        except Exception as e:
            return {
                "pubmed_insights": {"status": "error", "error": str(e)},
                "rare_diagnoses": [],
            }

    def route_after_pubmed(state: CouncilState) -> list[Send] | str:
        """
        If mode=iterative AND PubMed found rare diagnoses → fan-out Round 2.
        Otherwise → END.
        """
        if state.get("mode") == "iterative" and state.get("rare_diagnoses"):
            return [
                Send(
                    "generate_r2_opinion",
                    {**state, "_opinion_idx": i, "_round": 2},
                )
                for i in range(state["num_rollouts"])
            ]
        return END

    def calculate_r2_consensus(state: CouncilState) -> dict:
        """Calculate Round-2 consensus from accumulated r2_opinions."""
        opinions = [
            DiagnosticOpinion(
                opinion_id=o["opinion_id"],
                diagnosis=o["diagnosis"],
                confidence=o["confidence"],
                reasoning=o["reasoning"],
                differential_diagnoses=o.get("differential_diagnoses", []),
                recommended_tests=o.get("recommended_tests", []),
                urgency=o["urgency"],
            )
            for o in state["r2_opinions"]
        ]
        diag, strength, conf = _calc_consensus(opinions)
        discussion = _synth_discussion(opinions, diag or "")
        return {
            "r2_consensus_diagnosis": diag,
            "r2_consensus_strength": strength.value,
            "r2_consensus_confidence": conf,
            "r2_discussion_summary": discussion,
        }

    # ── Build and compile graph ───────────────────────────────────────────────

    g = StateGraph(CouncilState)

    g.add_node("initialize", initialize)
    # Two distinct node names sharing the same function — needed so edges can
    # route R1 output to calculate_consensus and R2 output to calculate_r2_consensus.
    g.add_node("generate_r1_opinion", _opinion_node)
    g.add_node("generate_r2_opinion", _opinion_node)
    g.add_node("calculate_consensus", calculate_consensus)
    g.add_node("run_pubmed", run_pubmed)
    g.add_node("calculate_r2_consensus", calculate_r2_consensus)

    def fan_out_r1(state: CouncilState) -> list[Send]:
        return [
            Send("generate_r1_opinion", {**state, "_opinion_idx": i, "_round": 1})
            for i in range(state["num_rollouts"])
        ]

    g.add_edge(START, "initialize")
    g.add_conditional_edges("initialize", fan_out_r1)
    g.add_edge("generate_r1_opinion", "calculate_consensus")
    g.add_edge("calculate_consensus", "run_pubmed")
    g.add_conditional_edges("run_pubmed", route_after_pubmed)
    g.add_edge("generate_r2_opinion", "calculate_r2_consensus")
    g.add_edge("calculate_r2_consensus", END)

    return g.compile()
