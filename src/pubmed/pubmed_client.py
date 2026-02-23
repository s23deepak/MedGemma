"""
NCBI E-utils API client for PubMed.

Uses only Python stdlib (urllib, xml.etree) — no extra dependencies.

Rate limits (NCBI policy):
  Without API key : 3 requests/second
  With NCBI_API_KEY: 10 requests/second

Set the NCBI_API_KEY environment variable to a free API key obtained from:
  https://www.ncbi.nlm.nih.gov/account/

E-utils endpoints used:
  esearch  — search PubMed, returns list of PMIDs
  esummary — fetch structured metadata (title, authors, journal, year) as JSON
  efetch   — fetch full abstract text as XML, parsed here to plain text
"""

from __future__ import annotations

import json
import logging
import os
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)

EUTILS_BASE = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
_LAST_REQUEST_TIME: float = 0.0   # module-level rate limiter


@dataclass
class PubMedArticle:
    """Structured representation of a PubMed article."""
    pmid: str
    title: str
    authors: list[str]
    journal: str
    pub_year: str
    pub_type: list[str]       # e.g. ["Case Reports", "Journal Article"]
    abstract: str             # full abstract text
    doi: str = ""
    pmc_id: str = ""          # PMC free full-text ID if available
    mesh_terms: list[str] = field(default_factory=list)

    @property
    def pubmed_url(self) -> str:
        return f"https://pubmed.ncbi.nlm.nih.gov/{self.pmid}/"

    @property
    def doi_url(self) -> str:
        return f"https://doi.org/{self.doi}" if self.doi else ""

    def to_dict(self) -> dict:
        return {
            "pmid": self.pmid,
            "title": self.title,
            "authors": self.authors,
            "journal": self.journal,
            "pub_year": self.pub_year,
            "pub_type": self.pub_type,
            "abstract": self.abstract,
            "doi": self.doi,
            "pmc_id": self.pmc_id,
            "mesh_terms": self.mesh_terms,
            "pubmed_url": self.pubmed_url,
            "doi_url": self.doi_url,
        }

    def to_citation(self) -> str:
        """APA-ish citation string."""
        authors_str = ", ".join(self.authors[:3])
        if len(self.authors) > 3:
            authors_str += " et al."
        return f"{authors_str} ({self.pub_year}). {self.title}. {self.journal}. PMID: {self.pmid}"


class PubMedClient:
    """
    Thin wrapper around NCBI E-utils.

    Usage:
        client = PubMedClient()
        articles = client.search_and_fetch("HbA1c diabetes management", max_results=5)
    """

    def __init__(self, api_key: str | None = None):
        self.api_key = api_key or os.environ.get("NCBI_API_KEY", "")
        self._min_interval = 0.11 if self.api_key else 0.34   # seconds between requests

    # ── Public API ────────────────────────────────────────────────────────────

    def search(
        self,
        query: str,
        max_results: int = 10,
        pub_type_filter: str | None = None,
        date_years_back: int | None = None,
        sort: str = "relevance",
    ) -> list[str]:
        """
        Search PubMed and return a list of PMIDs.

        Args:
            query: PubMed search query (supports MeSH terms, field tags etc.)
            max_results: Maximum number of PMIDs to return (≤ 100 recommended)
            pub_type_filter: Optional publication type, e.g. "Case Reports",
                             "Systematic Review", "Meta-Analysis",
                             "Randomized Controlled Trial"
            date_years_back: Restrict to papers published in last N years
            sort: Sort order — "relevance" (default) or "pub+date"

        Returns:
            List of PMID strings
        """
        full_query = self._build_query(query, pub_type_filter, date_years_back)
        params: dict = {
            "db": "pubmed",
            "term": full_query,
            "retmax": str(max_results),
            "retmode": "json",
            "sort": sort,
        }
        if self.api_key:
            params["api_key"] = self.api_key

        data = self._get_json(f"{EUTILS_BASE}/esearch.fcgi", params)
        pmids: list[str] = data.get("esearchresult", {}).get("idlist", [])
        logger.debug("PubMed search '%s' → %d PMIDs", full_query[:80], len(pmids))
        return pmids

    def fetch_metadata(self, pmids: list[str]) -> dict[str, dict]:
        """
        Fetch article metadata (title, authors, journal, year, DOI) for a list of PMIDs.
        Returns dict keyed by PMID.
        """
        if not pmids:
            return {}
        params: dict = {
            "db": "pubmed",
            "id": ",".join(pmids),
            "retmode": "json",
        }
        if self.api_key:
            params["api_key"] = self.api_key

        data = self._get_json(f"{EUTILS_BASE}/esummary.fcgi", params)
        result: dict = data.get("result", {})
        result.pop("uids", None)
        return result

    def fetch_abstracts_xml(self, pmids: list[str]) -> dict[str, PubMedArticle]:
        """
        Fetch full abstracts for a list of PMIDs via efetch (PubMed XML).
        Returns dict keyed by PMID.
        """
        if not pmids:
            return {}
        params: dict = {
            "db": "pubmed",
            "id": ",".join(pmids[:20]),   # API recommends batches ≤ 200; we cap at 20
            "rettype": "xml",
            "retmode": "xml",
        }
        if self.api_key:
            params["api_key"] = self.api_key

        url = f"{EUTILS_BASE}/efetch.fcgi?" + urllib.parse.urlencode(params)
        self._rate_limit()
        try:
            with urllib.request.urlopen(url, timeout=30) as resp:
                xml_bytes = resp.read()
        except Exception as e:
            logger.error("PubMed efetch failed: %s", e)
            return {}

        return self._parse_pubmed_xml(xml_bytes)

    def search_and_fetch(
        self,
        query: str,
        max_results: int = 5,
        pub_type_filter: str | None = None,
        date_years_back: int | None = None,
        sort: str = "relevance",
    ) -> list[PubMedArticle]:
        """
        Convenience method: search → fetch abstracts → return list of PubMedArticle.
        """
        pmids = self.search(query, max_results, pub_type_filter, date_years_back, sort)
        if not pmids:
            return []
        articles_map = self.fetch_abstracts_xml(pmids)
        # Preserve relevance order
        return [articles_map[pid] for pid in pmids if pid in articles_map]

    # ── Internal helpers ──────────────────────────────────────────────────────

    @staticmethod
    def _build_query(
        query: str,
        pub_type_filter: str | None,
        date_years_back: int | None,
    ) -> str:
        parts = [query]
        if pub_type_filter:
            parts.append(f'"{pub_type_filter}"[Publication Type]')
        if date_years_back:
            import datetime
            year = datetime.datetime.now().year - date_years_back
            parts.append(f"{year}:{datetime.datetime.now().year}[dp]")
        return " AND ".join(f"({p})" for p in parts)

    def _rate_limit(self):
        global _LAST_REQUEST_TIME
        elapsed = time.time() - _LAST_REQUEST_TIME
        if elapsed < self._min_interval:
            time.sleep(self._min_interval - elapsed)
        _LAST_REQUEST_TIME = time.time()

    def _get_json(self, base_url: str, params: dict) -> dict:
        url = base_url + "?" + urllib.parse.urlencode(params)
        self._rate_limit()
        try:
            with urllib.request.urlopen(url, timeout=20) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except Exception as e:
            logger.error("PubMed GET %s failed: %s", base_url, e)
            return {}

    @staticmethod
    def _parse_pubmed_xml(xml_bytes: bytes) -> dict[str, PubMedArticle]:
        """Parse PubMed XML efetch response into PubMedArticle objects."""
        articles: dict[str, PubMedArticle] = {}
        try:
            root = ET.fromstring(xml_bytes)
        except ET.ParseError as e:
            logger.error("PubMed XML parse error: %s", e)
            return articles

        for article_el in root.findall(".//PubmedArticle"):
            try:
                pmid_el = article_el.find(".//PMID")
                if pmid_el is None:
                    continue
                pmid = pmid_el.text or ""

                # Title
                title_el = article_el.find(".//ArticleTitle")
                title = "".join(title_el.itertext()).strip() if title_el is not None else ""

                # Authors
                authors: list[str] = []
                for author in article_el.findall(".//Author"):
                    last = author.findtext("LastName", "")
                    initials = author.findtext("Initials", "")
                    collective = author.findtext("CollectiveName", "")
                    if last:
                        authors.append(f"{last} {initials}".strip())
                    elif collective:
                        authors.append(collective)

                # Journal
                journal = article_el.findtext(".//Journal/Title", "") or \
                          article_el.findtext(".//Journal/ISOAbbreviation", "")

                # Year
                pub_year = (
                    article_el.findtext(".//PubDate/Year", "")
                    or article_el.findtext(".//PubDate/MedlineDate", "")[:4]
                )

                # Publication types
                pub_types: list[str] = [
                    pt.text for pt in article_el.findall(".//PublicationType")
                    if pt.text
                ]

                # Abstract — handles structured abstracts (multiple AbstractText sections)
                abstract_parts: list[str] = []
                for abs_el in article_el.findall(".//AbstractText"):
                    label = abs_el.get("Label", "")
                    text = "".join(abs_el.itertext()).strip()
                    if label:
                        abstract_parts.append(f"{label}: {text}")
                    elif text:
                        abstract_parts.append(text)
                abstract = "\n".join(abstract_parts)

                # DOI
                doi = ""
                for eloc in article_el.findall(".//ELocationID"):
                    if eloc.get("EIdType") == "doi":
                        doi = eloc.text or ""
                        break

                # PMC ID
                pmc_id = ""
                for id_el in article_el.findall(".//ArticleId"):
                    if id_el.get("IdType") == "pmc":
                        pmc_id = id_el.text or ""
                        break

                # MeSH descriptors
                mesh_terms = [
                    mh.findtext("DescriptorName", "")
                    for mh in article_el.findall(".//MeshHeading")
                ]
                mesh_terms = [t for t in mesh_terms if t]

                articles[pmid] = PubMedArticle(
                    pmid=pmid,
                    title=title,
                    authors=authors,
                    journal=journal,
                    pub_year=pub_year,
                    pub_type=pub_types,
                    abstract=abstract,
                    doi=doi,
                    pmc_id=pmc_id,
                    mesh_terms=mesh_terms,
                )
            except Exception as e:
                logger.debug("Skipping article parse error: %s", e)

        return articles
