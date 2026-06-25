import requests
from urllib.parse import quote

from config.config import Config, ConfigError

BIOPORTAL_URL = "https://data.bioontology.org/search"
DEFAULT_TIMEOUT = 30
DEFAULT_RESULT_LIMIT = 3
SYNONYM_PROPERTY_SUFFIXES = (
    "hasExactSynonym",
    "hasBroadSynonym",
    "hasNarrowSynonym",
    "hasRelatedSynonym",
)


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
            "require_exact_match": "false",
            "also_search_obsolete": "false",

        }

        try:
            headers = {"Authorization": f"apikey token={self._api_key}"}
            response = self._session.get(
                BIOPORTAL_URL,
                params=params,
                headers=headers,
                timeout=DEFAULT_TIMEOUT
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

        results = self._select_distinct_results(
            payload.get("collection", []),
            ontology_id=ontology,
        )
        self._enrich_results_with_class_details(results, headers)

        for result in results:
            result.pop("class_url", None)

        return results

    def _enrich_results_with_class_details(
            self,
            results: list[dict],
            headers: dict[str, str],
    ) -> None:
        """Fetch full class payloads and merge additional synonym properties."""
        for result in results:
            class_url = result.get("class_url")
            if not class_url:
                continue

            try:
                response = self._session.get(
                    class_url,
                    params={"include": "all"},
                    headers=headers,
                    timeout=DEFAULT_TIMEOUT
                )
            except requests.RequestException:
                continue

            if response.status_code != 200:
                continue

            try:
                details = response.json()
            except ValueError:
                continue

            result["synonyms"] = self._merge_synonyms(
                [
                    *result.get("synonyms", []),
                    *self._extract_synonyms(details),
                    *self._extract_property_synonyms(details),
                ]
            )

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

    @classmethod
    def _select_distinct_results(
            cls,
            items: list[dict],
            ontology_id: str | None = None,
            limit: int = DEFAULT_RESULT_LIMIT,
    ) -> list[dict]:
        """Pick the first distinct ontology codes returned by BioPortal."""
        if not items:
            return []

        results = []
        by_code: dict[str, dict] = {}

        for item in items:
            identifier = cls._best_identifier(item)
            if not cls._identifier_matches_ontology(identifier, ontology_id):
                continue

            notation = cls._best_notation(item, identifier)
            code = (notation or identifier or "").strip()

            if not code:
                continue

            key = code.casefold()
            existing = by_code.get(key)
            if existing:
                existing["synonyms"] = cls._merge_synonyms(
                    [*existing["synonyms"], *cls._extract_synonyms(item)]
                )
                if not existing.get("class_url"):
                    existing["class_url"] = cls._extract_class_url(item)
                continue

            result = {
                "identifier": identifier,
                "ontology_id": cls._ontology_id_from_identifier(
                    identifier,
                    ontology_id,
                ),
                "notation": notation,
                "purl": cls._extract_purl(identifier),
                "synonyms": cls._extract_synonyms(item),
                "class_url": cls._extract_class_url(item),
            }
            by_code[key] = result
            results.append(result)

            if len(results) == limit:
                break

        return results

    @staticmethod
    def _extract_class_url(item: dict) -> str:
        """Return the BioPortal class detail URL when it is present."""
        links = item.get("links") or {}
        class_url = links.get("self") if isinstance(links, dict) else ""
        return class_url if isinstance(class_url, str) else ""

    @staticmethod
    def _best_identifier(item) -> str | None:
        """Return the identifier from a BioPortal result."""
        for key in ("@id",):
            candidate = item.get(key)
            if candidate:
                return str(candidate)
        return None

    @staticmethod
    def _best_notation(item: dict, identifier: str | None) -> str:
        """Extract a compact notation (e.g., ``162`` from ``DOID_162``)."""
        if identifier and "_" in identifier:
            return identifier.rsplit("_", maxsplit=1)[-1]

        if identifier and "#" in identifier:
            return identifier.rsplit("#", maxsplit=1)[-1]

        return ""

    @classmethod
    def _identifier_matches_ontology(
            cls,
            identifier: str | None,
            ontology_id: str | None,
    ) -> bool:
        """Return whether an identifier belongs to the searched ontology."""
        expected = cls._normalize_ontology_id(ontology_id)
        if not expected:
            return True

        actual = cls._ontology_id_from_identifier(identifier)
        if not actual:
            return True

        return actual.casefold() == expected.casefold()

    @classmethod
    def _ontology_id_from_identifier(
            cls,
            identifier: str | None,
            fallback: str | None = None,
    ) -> str:
        """Derive the ontology prefix from a returned class identifier."""
        identifier = cls._normalize_iri(identifier)
        if not identifier:
            return cls._normalize_ontology_id(fallback)

        if cls._is_ncit(identifier):
            return "NCIT"

        local_id = identifier.rsplit("#", 1)[-1].rsplit("/", 1)[-1]
        if "_" not in local_id:
            return cls._normalize_ontology_id(fallback)

        prefix = local_id.split("_", 1)[0].strip()
        return prefix.upper() if prefix else cls._normalize_ontology_id(fallback)

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

        return BioPortalClient._ols4_entity_url(onto, iri)

    @staticmethod
    def _ols4_entity_url(ontology_id: str, iri: str) -> str:
        """Build the OLS4 entity page URL for an ontology IRI."""
        encoded_iri = quote(quote(iri, safe=""), safe="")
        return (
            "https://www.ebi.ac.uk/ols4/ontologies/"
            f"{ontology_id.lower()}/entities/{encoded_iri}"
        )

    @staticmethod
    def _extract_synonyms(item: dict) -> list[str]:
        """Collect synonyms from common BioPortal fields."""
        candidates = item.get("synonym") or item.get("synonyms") or []
        if isinstance(candidates, str):
            return [candidates.strip()] if candidates.strip() else []
        if isinstance(candidates, list):
            return [str(s).strip() for s in candidates if str(s).strip()]
        return []

    @staticmethod
    def _extract_property_synonyms(item: dict) -> list[str]:
        """Collect OBO synonym annotation values from a full class payload."""
        properties = item.get("properties") or {}
        if not isinstance(properties, dict):
            return []

        synonyms = []
        for key, values in properties.items():
            if not any(str(key).endswith(suffix)
                       for suffix in SYNONYM_PROPERTY_SUFFIXES):
                continue

            if isinstance(values, str):
                values = [values]

            if isinstance(values, list):
                synonyms.extend(
                    str(value).strip()
                    for value in values
                    if str(value).strip()
                )

        return synonyms

    @staticmethod
    def _merge_synonyms(synonyms: list[str]) -> list[str]:
        """Return synonyms de-duplicated case-insensitively preserving order."""
        merged = []
        seen = set()
        for synonym in synonyms or []:
            normalized = synonym.strip() if isinstance(synonym, str) else ""
            if not normalized:
                continue
            key = normalized.casefold()
            if key in seen:
                continue
            seen.add(key)
            merged.append(normalized)
        return merged
