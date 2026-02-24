"""
Health Belief Model (HBM) Profile

Tracks per-patient HBM signals inferred from portal interactions and shapes
AI response tone accordingly.

HBM Components tracked:
  - Perceived Susceptibility  ("Am I at risk?")
  - Perceived Severity        ("Is it serious?")
  - Health Motivation         ("Do I want to be healthy?")
  - Perceived Benefits        ("Will treatment actually help?")
  - Perceived Barriers        (cost, side effects, inconvenience, fear)
  - Cues to Action            (what triggered this question)

Scores are floats in [0.0, 1.0].  0.5 = neutral / unknown.
Updated incrementally after every portal interaction.
Stored in Firestore at: patients/{patient_id}/hbm_profile/current
"""

from __future__ import annotations

import logging
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime

logger = logging.getLogger(__name__)


# ── Signal keyword tables ──────────────────────────────────────────────────────

_SIGNALS: dict[str, list[tuple[float, list[str]]]] = {
    # (delta, keywords)  — delta applied to dimension on match
    "perceived_susceptibility": [
        (-0.15, ["i feel fine", "don't think i have", "probably fine", "i'm okay",
                 "not that serious", "can't happen to me", "won't happen"]),
        (+0.10, ["at risk", "worried i might", "could i get", "do i have",
                 "am i developing", "family history", "prone to"]),
    ],
    "perceived_severity": [
        (-0.15, ["just a little", "minor", "not serious", "probably nothing",
                 "minor issue", "not a big deal", "it's nothing"]),
        (+0.10, ["serious", "dangerous", "life-threatening", "could kill",
                 "long-term damage", "permanent", "disability"]),
    ],
    "health_motivation": [
        (-0.12, ["hard to", "keep forgetting", "not sure it's worth", "can't seem to",
                 "don't see the point", "what's the use", "bother"]),
        (+0.10, ["i want to", "trying to", "committed", "working hard on",
                 "doing my best", "really want to improve", "motivated"]),
    ],
    "perceived_benefits": [
        (-0.12, ["doesn't seem to work", "not helping", "not sure it helps",
                 "same as before", "no difference", "waste of time"]),
        (+0.10, ["feeling better", "working well", "helping a lot",
                 "improvement", "noticing a difference"]),
    ],
    "barrier_cost": [
        (+0.20, ["can't afford", "too expensive", "costs too much", "insurance won't",
                 "insurance denied", "out of pocket", "no coverage", "copay"]),
    ],
    "barrier_side_effects": [
        (+0.18, ["side effects", "makes me sick", "nauseous", "dizzy from",
                 "upset stomach", "can't tolerate", "feeling worse since"]),
    ],
    "barrier_inconvenience": [
        (+0.15, ["too busy", "hard to remember", "forget to take", "difficult to get",
                 "no time", "hard to schedule", "inconvenient"]),
    ],
    "barrier_fear": [
        (+0.18, ["scared", "afraid", "terrified", "nervous about",
                 "worried about taking", "fear of needles", "phobia"]),
    ],
}

_CUES: list[str] = [
    "appointment reminder", "my doctor said", "test results", "lab report",
    "news article", "friend told me", "family member", "advertisement",
    "pharmacist said", "read online",
]


def _detect_signals(text: str) -> dict[str, float]:
    """Return a dict of dimension→delta from a free-text message."""
    text_lower = text.lower()
    deltas: dict[str, float] = {}
    for dimension, rules in _SIGNALS.items():
        for delta, keywords in rules:
            if any(kw in text_lower for kw in keywords):
                deltas[dimension] = deltas.get(dimension, 0.0) + delta
    return deltas


def _detect_cue(text: str) -> str:
    """Return detected cue-to-action label or empty string."""
    text_lower = text.lower()
    for cue in _CUES:
        if cue in text_lower:
            return cue
    return ""


def _clamp(v: float) -> float:
    return max(0.0, min(1.0, v))


# ── Data model ─────────────────────────────────────────────────────────────────


@dataclass
class HealthBeliefProfile:
    """Per-patient HBM profile, updated incrementally from portal messages."""
    patient_id: str

    # Core HBM dimensions (0 = very low, 1 = very high)
    perceived_susceptibility: float = 0.5
    perceived_severity: float = 0.5
    health_motivation: float = 0.5
    perceived_benefits: float = 0.5

    # Barrier sub-scores
    barrier_cost: float = 0.0
    barrier_side_effects: float = 0.0
    barrier_inconvenience: float = 0.0
    barrier_fear: float = 0.0

    # Metadata
    signals: list[str] = field(default_factory=list)      # detected signal labels
    cues_to_action: list[str] = field(default_factory=list)
    interaction_count: int = 0
    last_updated: str = field(default_factory=lambda: datetime.now().isoformat())

    # ── Derived helpers ────────────────────────────────────────────────────────

    @property
    def overall_barrier_score(self) -> float:
        barriers = [
            self.barrier_cost,
            self.barrier_side_effects,
            self.barrier_inconvenience,
            self.barrier_fear,
        ]
        return round(sum(barriers) / len(barriers), 3)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["overall_barrier_score"] = self.overall_barrier_score
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "HealthBeliefProfile":
        data.pop("overall_barrier_score", None)
        allowed = {f for f in cls.__dataclass_fields__}
        return cls(**{k: v for k, v in data.items() if k in allowed})


# ── Service ────────────────────────────────────────────────────────────────────


class HBMProfileService:
    """
    Manages HBM profiles for patients.

    Usage:
        svc = HBMProfileService()
        profile = svc.load(patient_id)
        svc.update_from_message(profile, patient_message)
        guidance = svc.response_guidance(profile)
    """

    def load(self, patient_id: str) -> HealthBeliefProfile:
        """Load profile from Firestore or return a fresh default."""
        try:
            from src.config.firebase_config import get_firestore_client, is_firebase_available
            if is_firebase_available():
                db = get_firestore_client()
                if db is not None:
                    doc = (
                        db.collection("patients")
                        .document(patient_id)
                        .collection("hbm_profile")
                        .document("current")
                        .get()
                    )
                    if doc.exists:
                        return HealthBeliefProfile.from_dict(doc.to_dict())
        except Exception as e:
            logger.debug(f"HBM profile load failed (using default): {e}")
        return HealthBeliefProfile(patient_id=patient_id)

    def save(self, profile: HealthBeliefProfile) -> None:
        """Persist profile to Firestore."""
        try:
            from src.config.firebase_config import get_firestore_client, is_firebase_available
            if not is_firebase_available():
                return
            db = get_firestore_client()
            if db is None:
                return
            (
                db.collection("patients")
                .document(profile.patient_id)
                .collection("hbm_profile")
                .document("current")
                .set(profile.to_dict())
            )
        except Exception as e:
            logger.debug(f"HBM profile save failed (non-fatal): {e}")

    def update_from_message(self, profile: HealthBeliefProfile, message: str) -> None:
        """
        Analyse a patient message, update dimension scores in-place, and save.
        Uses a small learning rate so scores drift gradually, not abruptly.
        """
        lr = 0.6   # weight applied to detected delta (0–1)
        deltas = _detect_signals(message)
        new_signals: list[str] = []

        for dimension, delta in deltas.items():
            current = getattr(profile, dimension, 0.5)
            updated = _clamp(current + delta * lr)
            setattr(profile, dimension, round(updated, 3))
            label = f"{dimension}{'↑' if delta > 0 else '↓'}"
            if label not in profile.signals:
                new_signals.append(label)

        cue = _detect_cue(message)
        if cue and cue not in profile.cues_to_action:
            profile.cues_to_action.append(cue)

        profile.signals = (profile.signals + new_signals)[-30:]   # keep last 30
        profile.interaction_count += 1
        profile.last_updated = datetime.now().isoformat()
        self.save(profile)

    @staticmethod
    def response_guidance(profile: HealthBeliefProfile) -> str:
        """
        Return a short natural-language guidance block to inject into the AI prompt.
        Tells the AI how to shape its response tone based on this patient's HBM profile.
        """
        lines: list[str] = ["Health Belief Profile guidance for this patient:"]

        # Perceived susceptibility
        if profile.perceived_susceptibility < 0.35:
            lines.append(
                "- The patient appears to underestimate their personal risk. "
                "Gently emphasise how their specific conditions and risk factors are relevant."
            )
        elif profile.perceived_susceptibility > 0.75:
            lines.append(
                "- The patient is highly aware of their personal risk. "
                "Be reassuring and focus on concrete actions they can take."
            )

        # Perceived severity
        if profile.perceived_severity < 0.35:
            lines.append(
                "- The patient may minimise the seriousness of their condition. "
                "Provide clear, calm facts about potential complications without alarming them."
            )
        elif profile.perceived_severity > 0.75:
            lines.append(
                "- The patient is anxious about severity. "
                "Acknowledge their concern, then redirect to what is manageable and controllable."
            )

        # Health motivation
        if profile.health_motivation < 0.35:
            lines.append(
                "- The patient shows low motivation. "
                "Use motivational, non-judgmental language. Highlight small, achievable wins."
            )
        elif profile.health_motivation > 0.75:
            lines.append(
                "- The patient is highly motivated. "
                "Provide specific, actionable guidance to channel that motivation."
            )

        # Perceived benefits
        if profile.perceived_benefits < 0.35:
            lines.append(
                "- The patient doubts whether treatment is helping. "
                "Reinforce the evidence for their treatment and explain expected timelines."
            )

        # Barriers
        if profile.barrier_cost > 0.4:
            lines.append(
                "- The patient has expressed cost concerns. "
                "Acknowledge this and, where relevant, mention generic alternatives or assistance programs."
            )
        if profile.barrier_side_effects > 0.4:
            lines.append(
                "- The patient is troubled by side effects. "
                "Validate their experience and advise them to discuss alternatives with their provider."
            )
        if profile.barrier_inconvenience > 0.4:
            lines.append(
                "- The patient finds the treatment inconvenient. "
                "Suggest practical adherence strategies (pill organisers, reminders, routine anchoring)."
            )
        if profile.barrier_fear > 0.4:
            lines.append(
                "- The patient has expressed fear or anxiety about their treatment. "
                "Use calm, empathetic language and normalise their feelings."
            )

        # Cues to action
        if profile.cues_to_action:
            lines.append(
                f"- Detected cues to action: {', '.join(profile.cues_to_action)}. "
                "Acknowledge what prompted their question where appropriate."
            )

        if len(lines) == 1:
            return ""   # neutral profile — no guidance needed
        return "\n".join(lines)


# ── Singleton ──────────────────────────────────────────────────────────────────
_hbm_service: HBMProfileService | None = None


def get_hbm_service() -> HBMProfileService:
    global _hbm_service
    if _hbm_service is None:
        _hbm_service = HBMProfileService()
    return _hbm_service
