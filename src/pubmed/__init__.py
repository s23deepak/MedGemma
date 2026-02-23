"""PubMed integration package — NCBI E-utils API client and synthesis agent."""
from .pubmed_client import PubMedClient, PubMedArticle
from .synthesis_agent import PubMedSynthesisAgent, SearchMode, get_synthesis_agent

__all__ = [
    "PubMedClient", "PubMedArticle",
    "PubMedSynthesisAgent", "SearchMode", "get_synthesis_agent",
]
