import flet as ft


class ViewOntology(ft.Control):
    """Main application view for ontology management."""

    PRIMARY_COLOR = "#376966"
    PRIMARY_CONTAINER_COLOR = "#5A8F8A"
    SURFACE_COLOR = "#F7FAF9"
    SURFACE_VARIANT_COLOR = "#E0E7E6"
    OUTLINE_VARIANT_COLOR = "#C4D2D0"
    BUTTON_BG_COLOR = "#5C9792"
    BUTTON_TEXT_COLOR = "#FFFFFF"

    DEFAULT_PROJECT_LABEL = "ID project: —"
    DEFAULT_METADATA_COUNT_LABEL = "0 elements"
    DEFAULT_EXPORT_FORMAT = "csv"

    COLUMN_WIDTHS = {
        "code": 70,
        "domain": 120,
        "value": 140,
        "ontology": 120,
        "synonyms": 140,
        "iri": 180,
        "choice": 60,
    }

    def __init__(self, page: ft.Page):
        """Initialize view state and references to UI controls."""
        super().__init__()
        # page
        self._page = page

        # controller (it is not initialized. Must be initialized in the main,
        # after the controller is created)
        self._controller = None

        # Main controls (initialized in _build_controls)
        self.img_founding_gide: ft.Column | None = None
        self.btn_select_metadata_file: ft.FilledButton | None = None
        self.btn_export_file: ft.FilledButton | None = None
        self.btn_reset_app: ft.FilledButton | None = None
        self.file_picker: ft.FilePicker | None = None
        self.directory_picker: ft.FilePicker | None = None
        self.dd_export_format: ft.Dropdown | None = None
        self.tbl_metadata: ft.DataTable | None = None
        self.btn_search: ft.FilledTonalButton | None = None
        self.chip_project_id: ft.Chip | None = None
        self.chip_metadata_count: ft.Chip | None = None
        self.empty_metadata_placeholder: ft.Column | None = None
        self.card_metadata_table: ft.Card | None = None

        self.search_progress: ft.ProgressBar | None = None
        self.search_status_text: ft.Text | None = None
        self.search_status_row: ft.Row | None = None

        self._dlg_reset: ft.AlertDialog | None = None
        self._dlg_export: ft.AlertDialog | None = None
        self._pending_export_format = self.DEFAULT_EXPORT_FORMAT
        self._choice_groups: dict[str, list[ft.Checkbox]] = {}

        # Immediate static page settings.
        self._configure_static_page_settings()

    @property
    def controller(self):
        """Return the controller associated with the view."""
        return self._controller

    @property
    def page(self) -> ft.Page:
        """Expose the Flet page instance."""
        return self._page

    def set_controller(self, controller) -> None:
        """Assign the controller that manages application logic."""
        self._controller = controller

    def load_interface(self) -> None:
        """
        Initialize page theme, build controls, bind events, and mount the
        layout to the page.
        """
        self._configure_page_theme()
        self._build_controls()
        self._set_initial_button_state()
        self._bind_events()

        layout = self._define_layout()
        self._page.controls.append(
            ft.Container(
                padding=20,
                expand=True,
                content=ft.Column(
                    [layout],
                    horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                ),
            )
        )

        self._page.update()

    def update_metadata_table(
            self,
            metadata_rows: list[dict],
            project_id: str | None = None,
    ) -> None:
        """Update table, chips, and placeholder state with loaded metadata."""
        if not self.tbl_metadata:
            return

        has_rows = bool(metadata_rows)
        self._choice_groups = {}

        self.tbl_metadata.rows = [
            ft.DataRow(
                color=self._row_color(row),
                cells=[
                    self._build_cell(row.get("code", ""), "code"),
                    self._build_cell(row.get("domain", ""), "domain"),
                    self._build_cell(row.get("value", ""), "value"),
                    self._build_cell(row.get("ontology", ""), "ontology"),
                    self._build_cell(row.get("synonyms", ""), "synonyms"),
                    self._build_cell(row.get("iri", ""), "iri"),
                    self._build_cell(row, "choice"),
                ],
            )
            for row in metadata_rows
        ]

        if self.chip_project_id:
            project_id_text = project_id or "—"
            self.chip_project_id.label = ft.Text(f"ID project: {project_id_text}")

        if self.chip_metadata_count:
            self.chip_metadata_count.label = ft.Text(f"{len(metadata_rows)} elements")

        if self.empty_metadata_placeholder:
            self.empty_metadata_placeholder.visible = not has_rows
        self.tbl_metadata.visible = has_rows
        self.update_page()

    def create_alert(self, message: str) -> None:
        """Show a modal dialog with an informational message."""
        dialog = ft.AlertDialog(title=ft.Text(message))
        self._page.open(dialog)
        self._page.update()

    def update_page(self) -> None:
        """Force a page re-render."""
        self._page.update()

    def set_metadata_loaded_state(self) -> None:
        """Button state after metadata file load."""
        self._apply_button_state(
            select_metadata_disabled=True,
            export_disabled=True,
            reset_disabled=False,
            search_disabled=False,
        )

    def set_after_search_state(self) -> None:
        """Button state when the search is complete."""
        self._apply_button_state(
            select_metadata_disabled=True,
            export_disabled=False,
            reset_disabled=False,
            search_disabled=True,
        )

    def set_search_loading(self, is_loading: bool) -> None:
        """Show or hide the search progress indicator."""
        if self.search_status_row:
            self.search_status_row.visible = is_loading
        self.update_page()

    def reset_interface(self) -> None:
        """Reset the view to its initial state."""
        if self.tbl_metadata:
            self.tbl_metadata.rows = []
            self.tbl_metadata.visible = False
        if self.empty_metadata_placeholder:
            self.empty_metadata_placeholder.visible = True
        if self.chip_project_id:
            self.chip_project_id.label = ft.Text(self.DEFAULT_PROJECT_LABEL)
        if self.chip_metadata_count:
            self.chip_metadata_count.label = ft.Text(
                self.DEFAULT_METADATA_COUNT_LABEL
            )
        if self.search_status_row:
            self.search_status_row.visible = False

        self._set_initial_button_state()
        self._choice_groups = {}
        self.update_page()

    def show_reset_confirmation(self, on_confirm) -> None:
        """Show a reset confirmation dialog before clearing data."""
        self._close_dialog(self._dlg_reset)

        def on_cancel(_):
            self._close_dialog(self._dlg_reset)

        def on_accept(_):
            self._close_dialog(self._dlg_reset)
            on_confirm()
        self._dlg_reset = ft.AlertDialog(
            modal=True,
            title=ft.Text("Reset the application?"),
            content=ft.Text(
                "This will clear loaded metadata, selections, and results."
            ),
            actions=[
                ft.TextButton("Cancel", on_click=on_cancel),
                ft.FilledButton(
                    "Reset",
                    icon=ft.Icons.RESTART_ALT,
                    on_click=on_accept,
                ),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
        )
        self._page.open(self._dlg_reset)

    def show_export_dialog(self, _) -> None:
        """Show dialog to choose format and export directory."""
        self._close_dialog(self._dlg_export)

        def on_cancel(_):
            self._close_dialog(self._dlg_export)

        def on_confirm(_):
            selected_format = (
                self.dd_export_format.value
                if self.dd_export_format
                else self.DEFAULT_EXPORT_FORMAT
            )
            self._pending_export_format = selected_format or self.DEFAULT_EXPORT_FORMAT
            self._close_dialog(self._dlg_export)
            if self.directory_picker:
                self.directory_picker.get_directory_path()

        self._dlg_export = ft.AlertDialog(
            modal=True,
            title=ft.Text("Download ontology exports"),
            content=ft.Column(
                [
                    ft.Text("Choose the format to download."),
                    self.dd_export_format,
                ],
                tight=True,
            ),
            actions=[
                ft.TextButton("Cancel", on_click=on_cancel),
                ft.FilledButton(
                    "Download",
                    icon=ft.Icons.DOWNLOAD,
                    on_click=on_confirm,
                ),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
        )
        self._page.open(self._dlg_export)

    def on_file_picked(self, e: ft.FilePickerResultEvent) -> None:
        """Handle user selection of the metadata file."""
        if e.files:
            if self.empty_metadata_placeholder:
                self.empty_metadata_placeholder.visible = False
            if self.tbl_metadata:
                self.tbl_metadata.visible = True
            self._controller.get_metadata_excel_file(e.files)
            return

        self.create_alert("No file selected!")

    def on_directory_picked(self, e: ft.FilePickerResultEvent) -> None:
        """Handle selected directory for exporting results."""
        if e.path:
            export_format = self._pending_export_format or self.DEFAULT_EXPORT_FORMAT
            self._controller.export_metadata_files(e.path, export_format)
            return

        self.create_alert("No folder selected!")

    def _configure_static_page_settings(self) -> None:
        """Apply base page settings independent of theme."""
        self._page.title = "FoundingGIDE Ontology"
        self._page.horizontal_alignment = ft.CrossAxisAlignment.STRETCH
        self._page.scroll = ft.ScrollMode.AUTO

    def _configure_page_theme(self) -> None:
        """Configure app theme, colors, and app bar."""
        self._page.theme_mode = ft.ThemeMode.LIGHT
        self._page.padding = 20
        self._page.bgcolor = self.PRIMARY_COLOR
        self._page.theme = ft.Theme(
            color_scheme_seed=self.PRIMARY_COLOR,
            use_material3=True,
        )
        self._page.appbar = ft.AppBar(
            title=ft.Text("FoundingGIDE Ontology"),
            center_title=False,
            bgcolor=self.SURFACE_COLOR,
            actions=[
                ft.IconButton(
                    icon=ft.Icons.HELP_OUTLINE,
                    tooltip="Select an Excel file and start the search",
                )
            ],
        )

    def _build_controls(self) -> None:
        """Build all UI control groups."""
        self._build_upload_controls()
        self._build_export_controls()
        self._build_search_controls()
        self._build_table_controls()

    def _build_upload_controls(self) -> None:
        """Create controls for file upload and app reset."""
        self.img_founding_gide = ft.Column(
            [
                ft.Image(
                    src="assets/images/foundingGIDE.png",
                    width=260,
                    fit=ft.ImageFit.CONTAIN,
                ),
            ],
            spacing=4,
        )

        # Button select the metadata Excel file
        self.file_picker = ft.FilePicker()
        self._page.overlay.append(self.file_picker)

        self.btn_select_metadata_file = ft.FilledButton(
            text="Select metadata file",
            icon=ft.Icons.UPLOAD_FILE,
            tooltip="Select the metadata excel file to search for ontologies",
            bgcolor=self.BUTTON_BG_COLOR,
            color=self.BUTTON_TEXT_COLOR,
            expand = True,
        )

        # Button to reset the app
        self.btn_reset_app = ft.FilledButton(
            text="Reset",
            icon=ft.Icons.RESTART_ALT,
            tooltip="Clear loaded data and reset the app",
            bgcolor=self.BUTTON_BG_COLOR,
            color=self.BUTTON_TEXT_COLOR,
            expand=True,
        )

    def _build_export_controls(self) -> None:
        """Create controls required for result export."""
        self.directory_picker = ft.FilePicker()
        self._page.overlay.append(self.directory_picker)

        self.dd_export_format = ft.Dropdown(
            label="Export format",
            value=self.DEFAULT_EXPORT_FORMAT,
            options=[
                ft.dropdown.Option("csv", "CSV (.csv)"),
                ft.dropdown.Option("excel", "Excel (.xlsx)"),
            ],
            width=220,
        )

        self.btn_export_file = ft.FilledButton(
            text="Download",
            icon=ft.Icons.DOWNLOAD,
            tooltip="Download ontology exports in CSV or Excel format",
            bgcolor=self.BUTTON_BG_COLOR,
            color=self.BUTTON_TEXT_COLOR,
            expand=True,
        )

    def _build_search_controls(self) -> None:
        """Create search button and related progress state."""
        self.btn_search = ft.FilledTonalButton(
            text="Search ontologies",
            icon=ft.Icons.SEARCH,
            tooltip="Performs ontology searches on uploaded metadata",
            bgcolor=self.BUTTON_BG_COLOR,
            color=self.BUTTON_TEXT_COLOR,
        )

        # Progress indicator shown during search.
        self.search_progress = ft.ProgressBar(
            width=180,
            value=None,
            color=self.PRIMARY_CONTAINER_COLOR,
        )

        self.search_status_text = ft.Text(
            "Searching ontologies...",
            size=12,
            color=self.PRIMARY_COLOR,
        )

        self.search_status_row = ft.Row(
            controls=[self.search_progress, self.search_status_text],
            spacing=12,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
            visible=False,
        )

    def _build_table_controls(self) -> None:
        """Create metadata table, info chips, and empty placeholder."""
        self.chip_project_id = ft.Chip(
            label=ft.Text(self.DEFAULT_PROJECT_LABEL),
            leading=ft.Icon(ft.Icons.BADGE, size=18),
            bgcolor=self.PRIMARY_CONTAINER_COLOR,
            shape=ft.StadiumBorder(),
        )

        # Chip showing record count.
        self.chip_metadata_count = ft.Chip(
            label=ft.Text(self.DEFAULT_METADATA_COUNT_LABEL),
            leading=ft.Icon(ft.Icons.TABLE_ROWS, size=18),
            bgcolor=self.PRIMARY_CONTAINER_COLOR,
            shape=ft.StadiumBorder(),
        )

        # Metadata table
        self.tbl_metadata = ft.DataTable(
            columns=[
                self._build_column("Code", "code"),
                self._build_column("Domain", "domain"),
                self._build_column("Value", "value"),
                self._build_column("Ontology", "ontology"),
                self._build_column("Synonyms", "synonyms"),
                self._build_column("IRI", "iri"),
                self._build_column("", "choice"),
            ],
            rows=[],
            data_row_min_height=52,
            data_row_max_height=240,
            heading_row_color=self.SURFACE_VARIANT_COLOR,
            divider_thickness=0.8,
            visible=False,
        )

        self.empty_metadata_placeholder = ft.Column(
            [
                ft.Icon(ft.Icons.TABLE_VIEW, size=56, color=self.PRIMARY_COLOR),
                ft.Text(
                    value=(
                        "Load an Excel file to see the metadata organized "
                        "in the table."
                    ),
                    text_align=ft.TextAlign.CENTER,
                ),
            ],
            alignment=ft.MainAxisAlignment.CENTER,
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            visible=True,
        )

        # Card containing the table.
        self.card_metadata_table = ft.Card(
            elevation=2,
            content=ft.Container(
                padding=16,
                expand=True,
                content=ft.Column(
                    controls=[
                        ft.Row(
                            controls=[
                                ft.Text("Metadata", size=18, weight=ft.FontWeight.W_600),
                                self.chip_project_id,
                                self.chip_metadata_count,
                                ft.Container(expand=True),
                                self.btn_search,
                            ],
                            vertical_alignment=ft.CrossAxisAlignment.CENTER,
                        ),
                        ft.Divider(
                            height=12,
                            thickness=1,
                            color=self.OUTLINE_VARIANT_COLOR,
                        ),
                        self.search_status_row,
                        ft.Container(
                            bgcolor=self.SURFACE_COLOR,
                            border_radius=12,
                            padding=8,
                            content=ft.Column(
                                controls=[
                                    ft.Row(
                                        [
                                            ft.Container(
                                                expand=True,
                                                content=self.tbl_metadata,
                                            )
                                        ],
                                        scroll=ft.ScrollMode.AUTO,
                                        expand=True,
                                    ),
                                    self.empty_metadata_placeholder,
                                ],
                                scroll=ft.ScrollMode.AUTO,
                                expand=True,
                            ),
                        ),
                    ],
                    spacing=12,
                ),
            ),
        )

    def _define_layout(self) -> ft.Column:
        """Compose the main page layout."""
        return ft.Column(
            controls=[
                self.img_founding_gide,
                ft.Row(
                    controls=[
                        self.btn_select_metadata_file,
                        self.btn_export_file,
                        self.btn_reset_app,
                    ],
                    alignment=ft.MainAxisAlignment.CENTER,
                    spacing=12,
                ),
                ft.Row(
                    controls=[ft.Container(content=self.card_metadata_table)],
                    alignment=ft.MainAxisAlignment.CENTER,
                    expand=True,
                ),
            ],
            spacing=20,
        )

    def _bind_events(self) -> None:
        """Wire UI events to controller callbacks."""
        self.file_picker.on_result = self.on_file_picked
        self.btn_select_metadata_file.on_click = (
            lambda _: self.file_picker.pick_files(
                allow_multiple=False,
                allowed_extensions=["xlsx"],
            )
        )
        self.btn_search.on_click = self._controller.lookup_term
        self.directory_picker.on_result = self.on_directory_picked
        self.btn_export_file.on_click = self.show_export_dialog
        self.btn_reset_app.on_click = self._controller.request_reset

    def _set_initial_button_state(self) -> None:
        """Set initial button state at bootstrap/reset."""
        self._apply_button_state(
            select_metadata_disabled=False,
            export_disabled=True,
            reset_disabled=False,
            search_disabled=True,
        )

    def _apply_button_state(
            self,
            *,
            select_metadata_disabled: bool,
            export_disabled: bool,
            reset_disabled: bool,
            search_disabled: bool,
    ) -> None:
        """Apply button enabled/disabled state centrally."""
        if self.btn_select_metadata_file:
            self.btn_select_metadata_file.disabled = select_metadata_disabled
        if self.btn_export_file:
            self.btn_export_file.disabled = export_disabled
        if self.btn_reset_app:
            self.btn_reset_app.disabled = reset_disabled
        if self.btn_search:
            self.btn_search.disabled = search_disabled
        self.update_page()

    def _close_dialog(self, dialog: ft.AlertDialog | None) -> None:
        if dialog:
            self._page.close(dialog)

    def _build_column(self, title: str, column_key: str) -> ft.DataColumn:
        """Create a table column with optional predefined width."""
        width = self.COLUMN_WIDTHS.get(column_key)
        label_control: ft.Control = ft.Text(title)

        if width:
            label_control = ft.Container(
                width=width,
                content=ft.Text(title, weight=ft.FontWeight.BOLD),
            )

        return ft.DataColumn(label_control)

    def _build_cell(self, value, column_key: str) -> ft.DataCell:
        """Create a table cell applying per-column format and behavior."""
        width = self.COLUMN_WIDTHS.get(column_key)

        if column_key == "choice":
            content = self._build_choice_cell(value)
        elif column_key == "iri" and value:
            content = ft.Row(
                controls=[
                    ft.IconButton(
                        icon=ft.Icons.OPEN_IN_NEW,
                        on_click=lambda _, url=value: self._page.launch_url(url),
                        tooltip=value,
                        icon_color=self.PRIMARY_COLOR,
                        style=ft.ButtonStyle(
                            padding=0,
                            overlay_color=ft.Colors.TRANSPARENT,
                        ),
                    )
                ],
                spacing=8,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            )
        else:
            content = ft.Text(
                value or "",
                selectable=True,
                max_lines=3,
                overflow=ft.TextOverflow.ELLIPSIS,
            )

        alignment = (
            ft.alignment.center
            if column_key == "choice"
            else ft.alignment.center_left
        )

        return ft.DataCell(
            ft.Container(
                width=width,
                content=content,
                alignment=alignment,
                expand=True,
            )
        )

    def _build_choice_cell(self, row: dict) -> ft.Control:
        """Handle rendering and mutual exclusion for choice-group checkboxes."""
        option = row.get("selection_option")
        if not option:
            return ft.Text("")
        selected_value = row.get("selected_value") or None
        group_id = row.get("selection_group")

        checkbox = ft.Checkbox(
            value=option["value"] == selected_value,
            label="",
            data=option["value"],
        )

        if not group_id:
            return checkbox

        self._choice_groups.setdefault(group_id, []).append(checkbox)

        def on_change(e, group=group_id):
            group_checkboxes = self._choice_groups.get(group, [])
            if not group_checkboxes:
                return

            if not e.control.value:
                default_checkbox = group_checkboxes[0]
                for group_checkbox in group_checkboxes:
                    group_checkbox.value = group_checkbox is default_checkbox
                self._controller.set_user_selection(group, default_checkbox.data)
            else:
                for group_checkbox in group_checkboxes:
                    group_checkbox.value = group_checkbox is e.control
                self._controller.set_user_selection(group, e.control.data)

            for group_checkbox in group_checkboxes:
                group_checkbox.update()

        checkbox.on_change = on_change
        return checkbox

    def _row_color(self, row: dict) -> str:
        """Alternate row colors by group for readability."""
        group_index = row.get("group_index")
        if group_index is None:
            return ""

        if group_index % 2 == 0:
            return self.SURFACE_COLOR
        return self.SURFACE_VARIANT_COLOR
