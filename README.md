<a href="https://founding-gide.eurobioimaging.eu/">
  <img src="assets/images/foundingGIDE.png" alt="FoundingGIDE logo" width="220">
</a>

# FoundingGIDE Ontology

Desktop application (Flet + Python) that helps curate ontology mappings for metadata contained in a predefined Excel template.  
For each metadata value, the app queries BioPortal and lets users select the most suitable ontology code, then exports normalized files (`CSV` or `Excel`) with selected codes and optional synonyms.

---


## Table of Contents

- [What the app does](#what-the-app-does)
- [Core features](#core-features)
- [Architecture](#architecture)
- [Requirements](#requirements)
- [Installation and setup](#installation-and-setup)
- [How to run](#how-to-run)
- [Metadata template contract](#metadata-template-contract)
- [Ontology lookup and selection behavior](#ontology-lookup-and-selection-behavior)
- [Export format](#export-format)
- [Configuration files](#configuration-files)
- [Troubleshooting](#troubleshooting)
- [Limitations and notes](#limitations-and-notes)

---

## What the app does

1. Loads metadata from a specific Excel worksheet and fixed cell coordinates.
2. Splits comma-separated values into individual candidate terms.
3. Queries BioPortal for each term using ontology IDs configured per domain.
4. Lets the user choose one ontology result per term.
5. Exports selected ontology codes and synonyms to files.

---

## Core features

- **Template-driven metadata ingestion**
  - Reads only the coordinates declared in `persistence/metadata_mapping.json`.
  - Validates cell labels before reading associated values.
- **Domain-specific ontology search**
  - Resolves target ontology from `persistence/domain_ontology.json`.
  - Uses BioPortal Search API and keeps the top matches.
- **Interactive curation UI**
  - Browse metadata terms, review candidate ontology codes, and select preferred codes.
- **Flexible export**
  - Export as CSV or Excel.
  - Generates ontology-code and synonym files.

---

## Architecture

| Layer | Responsibility | Main files |
| --- | --- | --- |
| UI | App layout, user actions, dialogs, table rendering | `UI/view_ontology.py`, `UI/controller_ontology.py` |
| Model | Business logic for lookup, grouping, and export rows | `model/model_ontology.py`, `model/ontology_selection.py` |
| Integrations | BioPortal API client and response normalization | `model/bio_portal_client.py` |
| Persistence | Domain ontology map and metadata template map (JSON) | `persistence/domain_ontology.json`, `persistence/metadata_mapping.json` |
| Services | Excel/CSV read-write operations | `services/metadata_file_io.py` |
| Startup | App bootstrap and dependency wiring | `main.py` |

---

## Requirements

- Python **3.10+**
- A valid **BioPortal API key**
- Dependencies from `requirements.txt`

Install dependencies:

```bash
pip install -r requirements.txt
```

---

## Installation and setup

Create a file at:

```text
config/.env
```

## Setup
With at least:

```env
BIOPORTAL_API_KEY=your_bioportal_api_key
```

> If `config/.env` is missing, empty, or the key is blank, the app will raise a configuration error.

---

## How to run

```bash
python main.py
```
This starts the Flet desktop UI.

---

## Metadata template contract

The reader is strict and depends on the mapping configuration in `persistence/metadata_mapping.json`.

Current defaults:

- **Worksheet name**: `metadata template`
- **Value column index**: `4` (Excel column D)
- **Cell coordinates**: fixed list (e.g., `B21`, `B22`, ...)
- **Label validation**: text in each mapped cell must match `cell_name`
- **Dataset ID source**: mapped `dataset` domain entry (used in export filenames)

If a sheet name, cell coordinate, or label does not match expectations, that metadata value is skipped.

---

## Ontology lookup and selection behavior

- Each metadata value can contain multiple terms separated by commas.
- Terms are trimmed and searched independently.
- Ontology ID for each metadata entry is resolved from domain mapping (`domain_ontology.json`).
- For each query, BioPortal results are limited to the top candidates returned by the client logic.
- The selected ontology code is what gets exported in the ontology file.

---

## Export format

After curation, the app can write up to two output files:

1. **Ontology export**
   - CSV: `ontology_export.csv`
   - Excel: `ontology_export.xlsx`
   - Structure: one row per dataset with `DatasetId` and domain-based columns.

2. **Synonyms export**
   - CSV: `ontology_export_synonyms.csv`
   - Excel: `ontology_export_synonyms.xlsx`
   - Structure: `OntologyCode`, `Synonyms`.

If dataset ID is available, filenames are prefixed with it.

---

## Configuration files

### `persistence/domain_ontology.json`
Maps logical domains to ontology acronyms (examples: `disease -> DOID`, `drugs -> CHEBI`, `anatomy -> UBERON`).

### `persistence/metadata_mapping.json`
Declares:
- sheet name,
- value column,
- fixed cell coordinates,
- expected labels,
- domain/subdomain mapping for each coordinate.

Any update to the Excel template should be mirrored in this file.

---

## Troubleshooting

  - Verify `config/.env` exists and contains `BIOPORTAL_API_KEY`.
- **No ontology results**
  - Check network access.
  - Ensure searched terms exist in the target ontology.
- **Template not read as expected**
  - Confirm worksheet name and label text are unchanged.
  - Verify mapped coordinates in `metadata_mapping.json`.
- **Unexpected empty export columns**
  - Ensure a code was selected in the UI for each searchable term.

---

## Limitations and notes

- The app is intentionally coupled to a specific Excel template structure.
- Metadata extraction is position/label based, not schema-discovery based.
- Search quality depends on BioPortal availability and ontology coverage.
- Only selected codes are exported; unselected terms remain empty (or `NULL` fallback).

If you plan to support multiple templates, consider introducing versioned mapping profiles and a template validator step before lookup.