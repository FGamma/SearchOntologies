import requests

from config.config import Config, ConfigError

BIOPORTAL_URL = "https://data.bioontology.org/search"
DEFAULT_TIMEOUT = 30


class BioPortalError(RuntimeError):
    """Raised for unexpected BioPortal communication issues."""


class BioPortalClient:
    """
    The API key is resolved once at initialization to avoid repeated reads and
    to centralize where ``Config.api_key`` is invoked.
    """

    def __init__(
            self, api_key: str | None = None,
            session: requests.Session | None = None,
    ):
        self._api_key = (api_key or Config.api_key()).strip()
        if not self._api_key:
            raise ConfigError("BioPortal API key is missing or empty")

        self._session = session or requests.Session()

    @property
    def api_key(self) -> str:
        return self._api_key

    def search_ontology(self, cell_value: str,
                        ontology_id: str) -> list[dict]:
        """
        Search a single ontology and return details of the top matches.

        Each returned dictionary contains, when available: ``identifier``
        (best IRI/obo id), ``notation`` (compact code), ``purl`` and
        ``synonyms`` (list of strings).
        """

        ontology = self._normalize_ontology_id(ontology_id)
        term = self._normalize_term_value(cell_value)

        params = {
            "q": term,
            "ontologies": ontology,
            "apikey": self._api_key,
            "require_exact_match": "true",
        }

        try:
            headers = {"Authorization": f"apikey token={self._api_key}"}
            response = self._session.get(
                BIOPORTAL_URL,
                params={
                    "q": term,
                    "ontologies": ontology,
                    "require_exact_match": "true",
                },
                headers=headers,
                timeout=DEFAULT_TIMEOUT,
            )
        except requests.RequestException as exc:
            raise BioPortalError(
                f"Communication error with BioPortal: {exc}") from exc

        if response.status_code != 200:
            raise BioPortalError(
                "BioPortal responded with an unexpected status: "
                f"{response.status_code}"
            )

        try:
            payload = response.json()
        except ValueError as exc:
            raise BioPortalError(
                "Invalid BioPortal response (JSON expected)") from exc

        items = payload.get("collection", [])
        selected_items = self._select_top_items(items)
        if not selected_items:
            return []

        results = []
        for item in selected_items:
            identifier = self._best_identifier(item)
            results.append({
                "identifier": identifier,
                "notation": self._best_notation(identifier),
                "purl": self._extract_purl(identifier),
                "synonyms": self._extract_synonyms(item),
            })

        return results

    @staticmethod
    def _normalize_ontology_id(ontology: str | None) -> str:
        """Normalize ontology identifiers for consistent comparisons."""
        return (ontology or "").strip().upper()

    @staticmethod
    def _normalize_term_value(term: str | None) -> str:
        """Normalize terms for consistent comparisons."""
        return (term or "").strip()

    @staticmethod
    def _normalize_iri(value: str | None) -> str | None:
        """Normalize iri for consistent comparisons."""
        if not isinstance(value, str):
            return None
        value = value.strip()
        return value or None

    @staticmethod
    def _select_top_items(items: list[dict], limit: int = 3) -> list[dict]:
        """Pick the most relevant results returned by BioPortal."""
        if not items:
            return []

        return items[:limit]

    @staticmethod
    def _best_identifier(item) -> str | None:
        """Return the identifier from a BioPortal result."""
        for key in ("@id",):
            candidate = item.get(key)
            if candidate:
                return str(candidate)
        return None

    @staticmethod
    def _best_notation(identifier: str | None) -> str:
        """Extract a compact notation (e.g., ``162`` from ``DOID_162``)."""
        if identifier and "_" in identifier:
            return identifier.rsplit("_", maxsplit=1)[-1]

        if identifier and "#" in identifier:
            return identifier.rsplit("#", maxsplit=1)[-1]

        return ""

    @staticmethod
    def _extract_purl(identifier: str | None) -> str:
        """Derive a canonical PURL for the result."""
        iri = identifier

        if not iri:
            return ""

        if BioPortalClient._is_purl(iri):
            return iri
        if BioPortalClient._is_ncit(iri):
            return BioPortalClient._ncit_to_purl(iri)
        if BioPortalClient._is_ebi(iri):
            return BioPortalClient._ebi_to_purl(iri)

        return iri

    @staticmethod
    def _is_purl(value: str | None) -> bool:
        """Check if it is a canonical PURL"""
        value = BioPortalClient._normalize_iri(value)
        return bool(value and value.startswith((
            "http://purl.obolibrary.org/obo/",
            "https://purl.obolibrary.org/obo/",
        )))

    @staticmethod
    def _is_ncit(value: str | None) -> bool:
        """Check if it is a canonical NCIT"""
        value = BioPortalClient._normalize_iri(value)
        return bool(value and value.startswith((
            "http://ncicb.nci.nih.gov/xml/owl/EVS/Thesaurus.owl",
            "https://ncicb.nci.nih.gov/xml/owl/EVS/Thesaurus.owl",
        )))

    @staticmethod
    def _is_ebi(value: str | None) -> bool:
        """Check if it is a canonical EBI (SWO, EFO)"""
        value = BioPortalClient._normalize_iri(value)
        return bool(value and value.startswith((
            "http://www.ebi.ac.uk/",
            "https://www.ebi.ac.uk/",
        )))

    @staticmethod
    def _ncit_to_purl(iri: str | None) -> str | None:
        """Convert common NCIT IRIs to the canonical OBO PURL form."""
        iri = BioPortalClient._normalize_iri(iri)
        if not iri:
            return None

        local_id = iri.rsplit("#", 1)[-1].rsplit("/", 1)[-1]

        if not local_id:
            return iri

        return f"http://purl.obolibrary.org/obo/NCIT_{local_id}"

    @staticmethod
    def _ebi_to_purl(iri: str | None) -> str | None:
        """Convert common EBI IRIs to the canonical OBO PURL form."""
        iri = BioPortalClient._normalize_iri(iri)
        if not iri:
            return None

        iri_lower = iri.lower()

        if "/swo/" in iri_lower:
            onto = "SWO"
        elif "/efo/" in iri_lower:
            onto = "EFO"
        else:
            return iri

        local_id = iri.rsplit("_", 1)[-1].rsplit("/", 1)[-1]

        if not local_id:
            return iri

        return f"http://purl.obolibrary.org/obo/{onto}_{local_id}"

    @staticmethod
    def _extract_synonyms(item: dict) -> list[str]:
        """Collect synonyms from common BioPortal fields."""
        candidates = item.get("synonym") or item.get("synonyms") or []
        if isinstance(candidates, str):
            return [candidates.strip()] if candidates.strip() else []
        if isinstance(candidates, list):
            return [str(s).strip() for s in candidates if str(s).strip()]
        return []