import re
from dataclasses import dataclass, field
from typing import Dict, Tuple

from model.domain import Domain
from model.metadata import Metadata


@dataclass
class MetadataContainer:
    sheet_name: str
    column_index: int
    cells: Dict[str, Metadata] = field(default_factory=dict)

    def get_cells(self) -> Dict[str, Metadata]:
        """Return the metadata mapping keyed by code."""
        return self.cells

    def get_cells_sorted(self) -> Dict[str, Metadata]:
        """Return the metadata mapping ordered by Excel cell reference."""
        return {
            code: metadata
            for code, metadata in sorted(
                self.cells.items(),
                key=lambda item: self._cell_sort_key(item[0])
            )
        }

    def get_metadata_entries_sorted(self) -> tuple[Metadata, ...]:
        """Return metadata entries ordered by Excel cell reference."""
        return tuple(self.get_cells_sorted().values())

    def get_metadata(self, code: str) -> Metadata | None:
        """Return the metadata entry for ``code`` if present."""
        return self.cells.get(code)

    def get_domain(self, code: str) -> Domain:
        """Return the domain for the given metadata code."""
        metadata = self._require_metadata(code)
        return metadata.domain

    def get_value(self, code: str) -> str:
        """Return the stored cell value for ``code``."""
        metadata = self._require_metadata(code)
        return metadata.cell_value

    def get_dataset_id(self) -> str:
        """Return the dataset id."""
        for metadata in self.get_cells().values():
            domain = getattr(metadata, "domain", None)
            if domain and domain.id.casefold() == "dataset":
                return getattr(metadata, "cell_value", "") or ""
        return ""

    def codes(self) -> list[str]:
        """Return the list of available metadata codes."""
        return list(self.cells.keys())

    def set_value(self, code: str, value: str) -> None:
        """Set the cell value for ``code``."""
        metadata = self._require_metadata(code)
        metadata.cell_value = value

    def reset_values(self) -> None:
        """Reset all stored metadata values to empty strings."""
        for metadata in self.cells.values():
            metadata.cell_value = ""

    def _require_metadata(self, code: str) -> Metadata:
        """Return metadata for ``code`` or raise ``KeyError`` if missing."""
        try:
            return self.cells[code]
        except KeyError as exc:
            raise KeyError(f"Unknown metadata code: {code}") from exc

    @staticmethod
    def _cell_sort_key(cell: str) -> Tuple[int, int] | Tuple[float, float]:
        match = re.match(r"([A-Za-z]+)(\d+)$", cell)
        if not match:
            return float("inf"), float("inf")

        column_part, row_part = match.groups()
        column_number = 0
        for char in column_part.upper():
            column_number = column_number * 26 + (ord(char) - ord("A") + 1)
        return column_number, int(row_part)