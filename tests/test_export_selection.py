import unittest

from model.domain import Domain
from model.bio_portal_client import (
    BIOPORTAL_URL,
    SEARCH_PAGE_SIZE,
    BioPortalClient,
)
from model.metadata import Metadata
from model.model_ontology import ModelOntology
from model.ontology import Ontology
from model.ontology_selection import OntologySelection
from UI.controller_ontology import ControllerOntology


class ExportSelectionTests(unittest.TestCase):
    def test_empty_metadata_rows_do_not_shift_selection_group_ids(self):
        model = ModelOntology.__new__(ModelOntology)
        controller = ControllerOntology(None, model)

        empty_metadata = Metadata(
            code="B1",
            cell_name="Empty",
            subdomain="Empty",
            domain=Domain("sample", Ontology(id="NCIT")),
            cell_value="",
        )
        selected_metadata = Metadata(
            code="B2",
            cell_name="Disease",
            subdomain="Disease",
            domain=Domain("disease", Ontology(id="DOID")),
            cell_value="flu",
        )

        rows = controller._build_rows(
            [
                (empty_metadata, "", []),
                (
                    selected_metadata,
                    "flu",
                    [Ontology(id="DOID", value="123", synonyms=["influenza"])],
                ),
            ],
            allow_selection=True,
        )

        selectable_rows = [row for row in rows if row["selection_option"]]

        self.assertEqual(1, len(selectable_rows))
        self.assertEqual(
            "B2:flu:0",
            selectable_rows[0]["selection_group"],
        )

    def test_synonym_export_skips_selected_codes_without_synonyms(self):
        model = ModelOntology.__new__(ModelOntology)

        rows = model._build_selection_rows(
            [
                OntologySelection(code="DOID:123", synonyms=["influenza"]),
                OntologySelection(code="NCIT:456", synonyms=[]),
            ],
            empty_value="",
        )

        self.assertEqual(
            [
                {"OntologyCode": "DOID:123", "Synonyms": "influenza"},
            ],
            rows,
        )

    def test_search_candidates_deduplicates_repeated_ontology_codes(self):
        class FakeBioPortal:
            def search_ontology(self, cell_value, ontology_id):
                return [
                    {
                        "notation": "9538",
                        "purl": "http://purl.obolibrary.org/obo/DOID_9538",
                        "synonyms": ["multiple myeloma"],
                    },
                    {
                        "notation": "9538",
                        "purl": "http://purl.obolibrary.org/obo/DOID_9538",
                        "synonyms": ["Multiple Myeloma", "plasma cell myeloma"],
                    },
                ]

        model = ModelOntology.__new__(ModelOntology)
        model._bioportal = FakeBioPortal()

        candidates = model._search_candidates("cancer (multiple myeloma)", "DOID")

        self.assertEqual(1, len(candidates))
        self.assertEqual("9538", candidates[0].value)
        self.assertEqual(
            ["multiple myeloma", "plasma cell myeloma"],
            candidates[0].synonyms,
        )

    def test_bioportal_client_returns_first_four_distinct_codes(self):
        class FakeResponse:
            status_code = 200

            def json(self):
                return {
                    "collection": [
                        {"@id": "http://purl.obolibrary.org/obo/DOID_9538"},
                        {
                            "@id": "http://purl.obolibrary.org/obo/DOID_9538",
                            "synonym": ["Multiple Myeloma"],
                        },
                        {"@id": "http://purl.obolibrary.org/obo/DOID_111"},
                        {"@id": "http://purl.obolibrary.org/obo/DOID_222"},
                        {"@id": "http://purl.obolibrary.org/obo/DOID_333"},
                        {"@id": "http://purl.obolibrary.org/obo/DOID_444"},
                    ]
                }

        class FakeSession:
            params = None

            def get(self, *args, **kwargs):
                self.params = kwargs.get("params")
                return FakeResponse()

        session = FakeSession()
        client = BioPortalClient(api_key="test-api-key", session=session)

        results = client.search_ontology("cancer (multiple myeloma)", "DOID")

        self.assertNotIn("include", session.params)
        self.assertEqual(SEARCH_PAGE_SIZE, session.params["pagesize"])
        self.assertEqual(
            ["9538", "111", "222", "333"],
            [result["notation"] for result in results],
        )
        self.assertEqual(["Multiple Myeloma"], results[0]["synonyms"])

    def test_bioportal_client_ranks_local_label_and_synonym_matches(self):
        class FakeResponse:
            status_code = 200

            def json(self):
                return {
                    "collection": [
                        {
                            "@id": "http://purl.obolibrary.org/obo/NCIT_C1",
                            "prefLabel": "Unrelated Phase Finding",
                        },
                        {
                            "@id": "http://purl.obolibrary.org/obo/NCIT_C2",
                            "prefLabel": "X-Ray Phase-Contrast Imaging",
                            "synonym": ["Phase-contrast CT"],
                        },
                        {
                            "@id": "http://purl.obolibrary.org/obo/NCIT_C3",
                            "prefLabel": "Phase Contrast CT",
                        },
                    ]
                }

        class FakeSession:
            def get(self, *args, **kwargs):
                return FakeResponse()

        client = BioPortalClient(api_key="test-api-key", session=FakeSession())

        results = client.search_ontology("Phase-contrast CT", "NCIT")

        self.assertEqual(
            ["C3", "C2", "C1"],
            [result["notation"] for result in results],
        )

    def test_bioportal_client_filters_results_by_requested_ontology_prefix(self):
        class FakeResponse:
            status_code = 200

            def json(self):
                return {
                    "collection": [
                        {"@id": "http://purl.obolibrary.org/obo/PR_000000001"},
                        {
                            "@id": "http://purl.obolibrary.org/obo/UBERON_0001911"
                        },
                    ]
                }

        class FakeSession:
            def get(self, *args, **kwargs):
                return FakeResponse()

        client = BioPortalClient(api_key="test-api-key", session=FakeSession())

        results = client.search_ontology("tissue", "UBERON")

        self.assertEqual(1, len(results))
        self.assertEqual("UBERON", results[0]["ontology_id"])
        self.assertEqual("0001911", results[0]["notation"])

    def test_search_candidates_uses_returned_ontology_prefix(self):
        class FakeBioPortal:
            def search_ontology(self, cell_value, ontology_id):
                return [
                    {
                        "ontology_id": "PATO",
                        "notation": "0000001",
                        "purl": "http://purl.obolibrary.org/obo/PATO_0000001",
                        "synonyms": [],
                    },
                ]

        model = ModelOntology.__new__(ModelOntology)
        model._bioportal = FakeBioPortal()

        candidates = model._search_candidates("method", "OBI")

        self.assertEqual("PATO", candidates[0].id)
        self.assertEqual("0000001", candidates[0].value)

    def test_bioportal_client_fetches_full_class_synonym_properties(self):
        class FakeSearchResponse:
            status_code = 200

            def json(self):
                return {
                    "collection": [
                        {
                            "@id": "http://purl.obolibrary.org/obo/UBERON_0001911",
                            "synonym": ["milk patch"],
                            "links": {
                                "self": "https://data.bioontology.org/ontologies/"
                                        "UBERON/classes/UBERON_0001911"
                            },
                        },
                    ]
                }

        class FakeClassResponse:
            status_code = 200

            def json(self):
                return {
                    "synonym": ["milk patch"],
                    "properties": {
                        "http://www.geneontology.org/formats/oboInOwl#"
                        "hasExactSynonym": ["mammary gland exact"],
                        "http://www.geneontology.org/formats/oboInOwl#"
                        "hasBroadSynonym": ["breast gland"],
                    },
                }

        class FakeSession:
            calls = []

            def get(self, url, *args, **kwargs):
                self.calls.append((url, kwargs.get("params")))
                if url == BIOPORTAL_URL:
                    return FakeSearchResponse()
                return FakeClassResponse()

        session = FakeSession()
        client = BioPortalClient(api_key="test-api-key", session=session)

        results = client.search_ontology("mammary gland", "UBERON")

        self.assertEqual(
            ["milk patch", "mammary gland exact", "breast gland"],
            results[0]["synonyms"],
        )
        self.assertEqual({"include": "all"}, session.calls[1][1])

    def test_ebi_swo_iris_resolve_to_ols4_entity_pages(self):
        url = BioPortalClient._extract_purl(
            "http://www.ebi.ac.uk/swo/SWO_1100011"
        )

        self.assertEqual(
            "https://www.ebi.ac.uk/ols4/ontologies/swo/entities/"
            "http%253A%252F%252Fwww.ebi.ac.uk%252Fswo%252FSWO_1100011",
            url,
        )

    def test_ebi_efo_iris_resolve_to_ols4_entity_pages(self):
        url = BioPortalClient._extract_purl(
            "http://www.ebi.ac.uk/efo/EFO_0000001"
        )

        self.assertEqual(
            "https://www.ebi.ac.uk/ols4/ontologies/efo/entities/"
            "http%253A%252F%252Fwww.ebi.ac.uk%252Fefo%252FEFO_0000001",
            url,
        )


if __name__ == "__main__":
    unittest.main()
