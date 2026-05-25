from typing import Iterable, Optional

import flet as ft
from flet.core.file_picker import FilePickerFile

from config.config import ConfigError
from model.metadata import Metadata
from model.metadata_container import MetadataContainer
from model.ontology import Ontology
from model.ontology_selection import OntologySelection


class ControllerOntology:
    """Coordinate UI interactions for metadata loading, lookup, and export."""

    def __init__(self, view, model):
        # the view, with the graphical elements of the UI
        self._view = view
        # the model, which implements the logic of the program and holds the
        # persistence
        self._model = model
        self._user_selection: dict[str, str] = {}
        self._selection_candidates: dict[str, dict[str, OntologySelection]] = {}
        self._selection_details: dict[str, OntologySelection] = {}

    def get_metadata_excel_file(
            self,
            metadata_xlsx_file: list[FilePickerFile] | None,
    ) -> None:
        """Read predefined fields from the selected Excel file."""
        if not metadata_xlsx_file:
            self._view.create_alert("No file selected!")
            return

        file_info = metadata_xlsx_file[0]
        file_path = getattr(file_info, "path", None)

        if not file_path:
            self._view.create_alert("Unable to read the selected file path")
            return

        try:
            metadata_container = self._model.read_metadata_fields(file_path)
        except (ValueError, FileNotFoundError) as exc:
            self._view.create_alert(str(exc))
            return

        dataset_id = metadata_container.get_dataset_id()
        self._view.update_metadata_table(
            self._build_metadata_rows(metadata_container),
            dataset_id,
        )
        self._view.set_metadata_loaded_state()

    def lookup_term(self, e: ft.ControlEvent) -> list:
        """BioPortal lookups from the UI."""
        self._view.set_after_search_state()
        self._view.set_search_loading(True)
        try:
            term_results = self._model.search_terms_from_metadata()
            rows = self._build_term_rows(term_results)
            dataset_id = self._model.get_dataset_id()
            self._view.update_metadata_table(rows, dataset_id)
            return rows
        except (ValueError, ConfigError) as exc:
            self._view.create_alert(str(exc))
            return []
        finally:
            self._view.set_search_loading(False)

    def set_user_selection(self, group_id: str, value: str):
        """Store the user's selection for a given row group."""
        self._user_selection[group_id] = value
        selection = self._selection_candidates.get(group_id, {}).get(value)
        if selection:
            self._selection_details[group_id] = selection
        else:
            self._selection_details.pop(group_id, None)

    def export_metadata_files(
            self,
            directory_path: str,
            export_format: str = "csv",
    ) -> None:
        """Export ontology and synonym files in the selected format."""
        if not directory_path:
            self._view.create_alert("No folder selected!")
            return
        if export_format not in {"csv", "excel"}:
            self._view.create_alert("Unsupported export format selected.")
            return
        export_paths = self._model.export_metadata_files(
            directory_path,
            self._user_selection,
            list(self._selection_details.values()),
            export_format=export_format,
        )

        if not export_paths:
            self._view.create_alert("No metadata terms available to export.")
            return

        exported_files = "\n".join(f"- {path}" for path in export_paths)
        self._view.create_alert(
            "Export files saved:\n"
            f"{exported_files}"
        )

    def request_reset(self, e: ft.ControlEvent) -> None:
        """Request a confirmation dialog before resetting the app."""
        self._view.show_reset_confirmation(self.reset_state)

    def reset_state(self) -> None:
        """Reset model data, selections, and UI state."""
        self._model.reset_metadata()
        self._user_selection = {}
        self._selection_candidates = {}
        self._selection_details = {}
        self._view.reset_interface()

    def _build_metadata_rows(self,
                             metadata_container: MetadataContainer,
                             ) -> list:
        """Build read-only table rows from metadata container values."""
        entries = []
        metadata_container_sorted = metadata_container.get_cells_sorted()

        for metadata in metadata_container_sorted.values():
            if metadata is None:
                continue

            domain = metadata.get_domain()
            if domain.id.casefold() == "dataset":
                continue

            ontology = metadata.domain.ontology if getattr(metadata, "domain", None) else None
            terms = self._model.split_terms(
                getattr(metadata, "cell_value", "")) or [""]

            for term in terms:
                entries.append((metadata, term, ontology))

        return self._build_rows(entries, allow_selection=False)

    def _build_term_rows(
            self,
            term_results: list[tuple[Metadata, str, list[Ontology]]],
    ) -> list:
        """Build selectable table rows for ontology term lookup results."""
        return self._build_rows(term_results, allow_selection=True)

    def _build_rows(
            self,
            entries: Iterable[
                tuple[Metadata, str, Optional[Iterable[Ontology]]]
            ],
            allow_selection: bool,
    ) -> list:
        """Create UI table row dictionaries for metadata or term results."""
        rows = []
        if allow_selection:
            self._selection_candidates = {}
            self._selection_details = {}
        for index, (metadata, term, ontology) in enumerate(entries):
            candidates = self._normalize_candidates(ontology)
            group_id = self._model.build_group_id(metadata, term, index)

            if allow_selection:
                self._selection_candidates[group_id] = {}

            default_value = self._resolve_default_value(
                group_id,
                candidates,
                allow_selection,
            )
            for candidate in candidates:
                selection_option = None
                if allow_selection and candidate:
                    label = self._candidate_label(candidate)
                    value = self._candidate_value(candidate)
                    if value:
                        selection_option = {"label": label or value,
                                            "value": value}
                        selection_details = self._build_selection_details(
                            candidate
                        )
                        if selection_details:
                            self._selection_candidates[group_id][
                                value] = selection_details

                rows.append({
                    "code": metadata.code,
                    "domain": metadata.subdomain,
                    "value": term,
                    "ontology": self._format_ontology_display(candidate),
                    "synonyms": ", ".join(getattr(candidate, "synonyms", []))
                    if getattr(candidate, "synonyms", None) else "",
                    "iri": getattr(candidate, "base_uri",
                                   "") if candidate else "",
                    "group_index": index,
                    "selection_group": group_id,
                    "selection_option": selection_option,
                    "selected_value": default_value,
                })

            if allow_selection and default_value:
                selection = self._selection_candidates[group_id].get(
                    default_value
                )
                if selection:
                    self._selection_details[group_id] = selection

        return rows

    def _resolve_default_value(
            self,
            group_id: str,
            candidates: list[Ontology | None],
            allow_selection: bool,
    ) -> str:
        """Keep or infer the default selected candidate for a row group."""
        default_value = self._user_selection.get(group_id, "")
        if default_value or not allow_selection:
            return default_value

        for candidate in candidates:
            candidate_value = self._candidate_value(candidate)
            if not candidate_value:
                continue
            self._user_selection[group_id] = candidate_value
            return candidate_value

        return ""

    @staticmethod
    def _build_selection_details(
            candidate: Ontology,
    ) -> OntologySelection | None:
        code = ControllerOntology._candidate_value(candidate)
        if not code:
            return None
        synonyms = ControllerOntology._merge_synonyms(
            getattr(candidate, "synonyms", []),
        )
        return OntologySelection(code=code, synonyms=synonyms)

    @staticmethod
    def _merge_synonyms(synonyms: list[str]) -> list[str]:
        """Return synonyms de-duplicated case-insensitively preserving order."""
        merged = []
        seen = set()
        for synonym in synonyms or []:
            if not synonym:
                continue
            key = synonym.casefold()
            if key in seen:
                continue
            merged.append(synonym)
            seen.add(key)
        return merged

    @staticmethod
    def _normalize_candidates(ontology):
        """Normalize ontology values to a non-empty candidate list."""
        if ontology is None:
            return [None]
        if isinstance(ontology, str):
            return [ontology]
        try:
            candidates = list(ontology)
        except TypeError:
            return [ontology]
        return candidates or [None]

    @staticmethod
    def _candidate_value(candidate: Ontology | None) -> Optional[str]:
        """Return the value used to identify a candidate in selection menus."""
        if not candidate:
            return None
        ident = getattr(candidate, "id", None)
        value = getattr(candidate, "value", None)
        if ident and value:
            if value.startswith(f"{ident}:"):
                return value
            return f"{ident}:{value}"
        return ident or value

    @staticmethod
    def _candidate_label(candidate: Ontology | None) -> Optional[str]:
        """Return the readable label for a candidate option."""
        if not candidate:
            return None
        return (
                getattr(candidate, "value", None)
                or getattr(candidate, "base_uri", None)
                or getattr(candidate, "id", None)
        )

    @staticmethod
    def _format_ontology_display(candidate: Ontology | None) -> str:
        """Format ontology display text for the table view."""
        if not candidate:
            return ""
        value = getattr(candidate, "value", None)
        ident = getattr(candidate, "id", None)
        if value:
            return f"{ident}: {value}" if ident else value
        return ident or ""