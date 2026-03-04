"""
Clinical HPO Phenotype Mapper
=============================
Maps free-text clinical descriptions to Human Phenotype Ontology (HPO) terms
using the JAX HPO API (https://hpo.jax.org/api/).

Three-tier lookup strategy
--------------------------
1. Local alias table — zero-latency mapping for the most common clinical phrases
   ("shortness of breath" → HP:0002094, etc.)
2. JAX HPO REST API  — live term search with a 3-second timeout and 512-entry
   LRU cache (avoids hammering the API on repeated queries).
3. Graceful degradation — if the API is unreachable, returns only local matches
   plus a lightweight partial-match against the alias table.

Usage
-----
    from src.clinical.hpo import get_hpo_mapper

    mapper = get_hpo_mapper()

    # Map a single phrase
    term = mapper.map_term("shortness of breath")
    if term:
        print(term.hp_id, term.name)  # HP:0002094 Dyspnea

    # Map all symptoms from clinical text
    terms = mapper.map_symptoms(["chest pain", "dyspnea", "fever"])
    for t in terms:
        print(t.hp_id, t.name, t.source)

    # Convert a note into HPO annotation blocks (for rare-disease matching)
    annotations = mapper.annotate_text(note_text)
"""
from __future__ import annotations

import functools
import json as _json
import re
import urllib.parse
import urllib.request
from dataclasses import dataclass, field


# ── HPO term result type ───────────────────────────────────────────────────────

@dataclass(frozen=True)
class HPOTerm:
    """A single resolved HPO term."""
    hp_id:       str          # e.g. "HP:0002094"
    name:        str          # canonical HPO label
    synonyms:    tuple[str, ...] = field(default_factory=tuple)
    definition:  str = ""
    source:      str = "api"  # "local" | "api" | "partial"


# ── Local alias table ──────────────────────────────────────────────────────────
#
# Common clinical shorthand → (HPO ID, canonical name)
# Entries chosen to cover the most frequent terms in clinical notes.

_LOCAL_ALIASES: dict[str, tuple[str, str]] = {
    # Respiratory
    "shortness of breath":      ("HP:0002094", "Dyspnea"),
    "sob":                       ("HP:0002094", "Dyspnea"),
    "dyspnea":                   ("HP:0002094", "Dyspnea"),
    "breathlessness":            ("HP:0002094", "Dyspnea"),
    "wheezing":                  ("HP:0030828", "Wheezing"),
    "wheeze":                    ("HP:0030828", "Wheezing"),
    "cough":                     ("HP:0012735", "Cough"),
    "productive cough":          ("HP:0031245", "Productive cough"),
    "hemoptysis":                ("HP:0002105", "Hemoptysis"),
    "tachypnea":                 ("HP:0002789", "Tachypnea"),
    "apnea":                     ("HP:0002104", "Apnea"),
    "hypoxia":                   ("HP:0012418", "Decreased oxygen saturation"),
    "stridor":                   ("HP:0010307", "Stridor"),

    # Cardiovascular
    "chest pain":                ("HP:0100749", "Chest pain"),
    "palpitations":              ("HP:0001962", "Palpitations"),
    "syncope":                   ("HP:0001279", "Syncope"),
    "pre-syncope":               ("HP:0012649", "Presyncope"),
    "edema":                     ("HP:0000969", "Edema"),
    "peripheral edema":          ("HP:0007018", "Peripheral edema"),
    "leg swelling":              ("HP:0007018", "Peripheral edema"),
    "tachycardia":               ("HP:0001649", "Tachycardia"),
    "bradycardia":               ("HP:0001662", "Bradycardia"),
    "hypertension":              ("HP:0000822", "Hypertension"),
    "hypotension":               ("HP:0002615", "Hypotension"),

    # Neurological
    "headache":                  ("HP:0002315", "Headache"),
    "migraine":                  ("HP:0002076", "Migraine"),
    "dizziness":                 ("HP:0002321", "Vertigo"),
    "vertigo":                   ("HP:0002321", "Vertigo"),
    "seizure":                   ("HP:0001250", "Seizures"),
    "weakness":                  ("HP:0001324", "Muscle weakness"),
    "numbness":                  ("HP:0003474", "Sensory impairment"),
    "tingling":                  ("HP:0003401", "Paresthesia"),
    "paresthesia":               ("HP:0003401", "Paresthesia"),
    "tremor":                    ("HP:0001337", "Tremor"),
    "ataxia":                    ("HP:0001251", "Ataxia"),
    "confusion":                 ("HP:0001289", "Confusion"),
    "altered mental status":     ("HP:0001289", "Confusion"),

    # Gastrointestinal
    "nausea":                    ("HP:0002018", "Nausea"),
    "vomiting":                  ("HP:0002013", "Vomiting"),
    "abdominal pain":            ("HP:0002027", "Abdominal pain"),
    "diarrhea":                  ("HP:0002014", "Diarrhea"),
    "constipation":              ("HP:0002019", "Constipation"),
    "dysphagia":                 ("HP:0002015", "Dysphagia"),
    "hematemesis":               ("HP:0002248", "Hematemesis"),
    "melena":                    ("HP:0025085", "Bloody stool"),
    "jaundice":                  ("HP:0000952", "Jaundice"),

    # Musculoskeletal
    "arthralgia":                ("HP:0002829", "Arthralgia"),
    "joint pain":                ("HP:0002829", "Arthralgia"),
    "myalgia":                   ("HP:0003326", "Myalgia"),
    "muscle pain":               ("HP:0003326", "Myalgia"),
    "back pain":                 ("HP:0003418", "Back pain"),
    "neck pain":                 ("HP:0002653", "Bone pain"),
    "fracture":                  ("HP:0020110", "Bone fracture"),

    # Systemic / Constitutional
    "fever":                     ("HP:0001945", "Fever"),
    "pyrexia":                   ("HP:0001945", "Fever"),
    "chills":                    ("HP:0025143", "Chills"),
    "fatigue":                   ("HP:0012378", "Fatigue"),
    "malaise":                   ("HP:0033834", "Malaise"),
    "weight loss":               ("HP:0001824", "Decreased body weight"),
    "weight gain":               ("HP:0004324", "Increased body weight"),
    "night sweats":              ("HP:0030166", "Night sweats"),
    "anorexia":                  ("HP:0002039", "Anorexia"),

    # Dermatological
    "rash":                      ("HP:0000988", "Skin rash"),
    "pruritus":                  ("HP:0000971", "Pruritus"),
    "itching":                   ("HP:0000971", "Pruritus"),
    "urticaria":                 ("HP:0001025", "Urticaria"),
    "hives":                     ("HP:0001025", "Urticaria"),
    "pallor":                    ("HP:0000980", "Pallor"),
    "cyanosis":                  ("HP:0000961", "Cyanosis"),

    # Ophthalmological
    "blurred vision":            ("HP:0000622", "Blurred vision"),
    "diplopia":                  ("HP:0000651", "Diplopia"),
    "photophobia":               ("HP:0000613", "Photophobia"),

    # Urological
    "dysuria":                   ("HP:0100518", "Dysuria"),
    "hematuria":                 ("HP:0000790", "Hematuria"),
    "polyuria":                  ("HP:0000103", "Polyuria"),
    "oliguria":                  ("HP:0001575", "Oliguria"),
}

# Compile a name→alias lookup for partial matches (lowercase canonical names)
_CANONICAL_REVERSE: dict[str, str] = {
    v[1].lower(): k for k, v in _LOCAL_ALIASES.items()
}


# ── JAX HPO REST API helper ────────────────────────────────────────────────────

_JAX_SEARCH_URL = "https://hpo.jax.org/api/hpo/search"
_JAX_TERM_URL   = "https://hpo.jax.org/api/hpo/term"


@functools.lru_cache(maxsize=512)
def _jax_search_cached(query: str) -> list[dict] | None:
    """
    Query the JAX HPO search endpoint for one term.

    Returns a list of {id, name, synonym} dicts on success.
    Returns None if the API is unreachable or returns no results.
    Cached with a 512-entry LRU to avoid repeat network calls.
    """
    try:
        encoded = urllib.parse.quote(query[:100])
        url = f"{_JAX_SEARCH_URL}?q={encoded}&max=3&category=terms"
        req = urllib.request.Request(
            url,
            headers={"Accept": "application/json",
                     "User-Agent": "MedGemma/1.0 ClinicalAssistant"},
        )
        with urllib.request.urlopen(req, timeout=3) as resp:
            data = _json.loads(resp.read().decode("utf-8"))

        # API returns {"terms": [{ontologyId, name, synonym}, ...], ...}
        terms = data.get("terms", []) or []
        if terms:
            return [
                {
                    "hp_id": t.get("ontologyId", ""),
                    "name":  t.get("name", ""),
                    "synonyms": t.get("synonym", []) or [],
                }
                for t in terms[:3]
            ]
        return None
    except Exception:
        return None


# ── Core mapper ───────────────────────────────────────────────────────────────

class HPOPhenotypeMapper:
    """
    Maps clinical text / symptom lists to HPO phenotype terms.

    Lookup cascade (fastest first)
    ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
    1. Exact match in local alias table (case-insensitive).
    2. Partial match in local alias table (query is a substring of an alias key).
    3. Partial match against canonical HPO names in local table.
    4. JAX HPO REST API call (cached, 3 s timeout).

    Clinical safety note
    ~~~~~~~~~~~~~~~~~~~~
    Unmapped terms are returned with hp_id="" and source="unmapped" so callers
    can decide whether to surface them as-is rather than silently dropping them.
    """

    # ── Internal lookups ──────────────────────────────────────────────────────

    @staticmethod
    def _exact_local(query: str) -> HPOTerm | None:
        """Exact case-insensitive match against local alias table."""
        entry = _LOCAL_ALIASES.get(query)
        if entry:
            return HPOTerm(hp_id=entry[0], name=entry[1], source="local")
        return None

    @staticmethod
    def _partial_local(query: str) -> HPOTerm | None:
        """
        Partial match: return first alias whose key *contains* the query or
        which the query *contains*.  Prefers shorter keys (more specific).
        """
        candidates: list[tuple[int, str, tuple[str, str]]] = []
        for key, val in _LOCAL_ALIASES.items():
            if query in key or key in query:
                candidates.append((len(key), key, val))
        if candidates:
            candidates.sort()
            best_val = candidates[0][2]
            return HPOTerm(hp_id=best_val[0], name=best_val[1], source="partial")
        return None

    @staticmethod
    def _canonical_match(query: str) -> HPOTerm | None:
        """Partial match against canonical HPO name strings in local table."""
        for canon_lower, alias_key in _CANONICAL_REVERSE.items():
            if query in canon_lower or canon_lower in query:
                entry = _LOCAL_ALIASES[alias_key]
                return HPOTerm(hp_id=entry[0], name=entry[1], source="partial")
        return None

    @staticmethod
    def _api_lookup(query: str) -> HPOTerm | None:
        """Live JAX HPO API lookup (cached)."""
        results = _jax_search_cached(query)
        if results:
            first = results[0]
            hp_id = first.get("hp_id", "")
            name  = first.get("name", query.title())
            syns  = tuple(first.get("synonyms", []))
            if hp_id:
                return HPOTerm(hp_id=hp_id, name=name, synonyms=syns, source="api")
        return None

    # ── Public API ────────────────────────────────────────────────────────────

    def map_term(self, phrase: str) -> HPOTerm | None:
        """
        Map a single clinical phrase to its best HPO term.

        Returns None only when no match can be found at any tier.
        Callers should treat None as "unmapped" (not as "absent").
        """
        q = phrase.lower().strip()
        if not q:
            return None

        # Tier 1: exact local
        t = self._exact_local(q)
        if t:
            return t

        # Tier 2: partial local alias
        t = self._partial_local(q)
        if t:
            return t

        # Tier 3: canonical name match
        t = self._canonical_match(q)
        if t:
            return t

        # Tier 4: live API
        return self._api_lookup(q)

    def map_symptoms(
        self,
        symptoms: list[str],
        *,
        include_unmapped: bool = False,
    ) -> list[HPOTerm]:
        """
        Map a list of symptom strings to HPO terms.

        Args:
            symptoms:        List of free-text symptom phrases.
            include_unmapped: If True, include a placeholder term for each
                             phrase that could not be mapped (hp_id="").

        Returns:
            Deduplicated list of HPOTerm objects.
        """
        seen_ids: set[str] = set()
        results: list[HPOTerm] = []

        for symptom in symptoms:
            term = self.map_term(symptom)
            if term is None:
                if include_unmapped:
                    results.append(
                        HPOTerm(hp_id="", name=symptom, source="unmapped")
                    )
                continue
            if term.hp_id not in seen_ids:
                seen_ids.add(term.hp_id)
                results.append(term)

        return results

    def annotate_text(self, text: str) -> list[HPOTerm]:
        """
        Scan free-text for any local-alias phrase and return matched HPO terms.

        This is a lightweight dictionary scan — it does NOT call the JAX API so
        it can safely run on every note without incurring network latency.

        Returns:
            Deduplicated HPOTerms sorted by position of first occurrence.
        """
        text_lower = text.lower()
        seen_ids: set[str] = set()
        found: list[tuple[int, HPOTerm]] = []  # (position, term)

        for phrase, (hp_id, name) in _LOCAL_ALIASES.items():
            idx = text_lower.find(phrase)
            if idx >= 0 and hp_id not in seen_ids:
                seen_ids.add(hp_id)
                found.append((idx, HPOTerm(hp_id=hp_id, name=name, source="local")))

        found.sort(key=lambda x: x[0])
        return [t for _, t in found]

    def to_prompt_block(self, terms: list[HPOTerm]) -> str:
        """
        Format a list of HPOTerms into a compact prompt injection block.

        Example output:
            HPO Phenotype Annotations:
              HP:0002094 Dyspnea
              HP:0001945 Fever
              HP:0012735 Cough
        """
        if not terms:
            return ""
        lines = ["HPO Phenotype Annotations:"]
        for t in terms:
            if t.hp_id:
                lines.append(f"  {t.hp_id} {t.name}")
            else:
                lines.append(f"  (unmapped) {t.name}")
        return "\n".join(lines)

    def rare_disease_query(self, terms: list[HPOTerm]) -> str:
        """
        Build a rare-disease-oriented diagnostic prompt supplement from
        a set of HPO terms — aligns with the "Counter-Factual Prompting"
        strategy for rare diagnosis.

        Returns a prompt fragment ready to append to a diagnostic prompt.
        """
        if not terms:
            return ""

        ids = " ".join(t.hp_id for t in terms if t.hp_id)
        names = ", ".join(t.name for t in terms if t.hp_id)

        return (
            f"The following HPO phenotype terms have been extracted from the clinical note:\n"
            f"  {names}\n"
            f"HPO IDs: {ids}\n\n"
            f"If the most common diagnosis does NOT fully explain these phenotype terms, "
            f"consider whether a rare syndrome matching this phenotype profile could be present. "
            f"Consult Orphanet / OMIM for differential diagnoses that match ≥3 of the above terms."
        )


# ── Singleton ─────────────────────────────────────────────────────────────────

_mapper: HPOPhenotypeMapper | None = None


def get_hpo_mapper() -> HPOPhenotypeMapper:
    """Return the process-wide singleton HPOPhenotypeMapper."""
    global _mapper
    if _mapper is None:
        _mapper = HPOPhenotypeMapper()
    return _mapper
