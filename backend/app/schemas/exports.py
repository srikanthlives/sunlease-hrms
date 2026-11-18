from pydantic import BaseModel, Field


class ExportSpecIn(BaseModel):
    """One export, as configured by the wizard. `columns` is ordered - its
    order IS the column order in the file."""
    entity: str                                  # EMPLOYEE / CANDIDATE
    columns: list[str] = Field(min_length=1)
    sort_by: str | None = None
    sort_dir: str | None = "asc"                 # asc / desc
    # Mirrors the entity's own list-page filters; unknown keys are ignored
    # rather than rejected, so the wizard can send its whole filter state.
    filters: dict[str, str | int | None] = {}


class ExportTemplateIn(BaseModel):
    """A saved pattern: a layout only. Filters are chosen at download time,
    never stored - see models.ExportTemplate."""
    name: str
    entity: str
    columns: list[str] = Field(min_length=1)
    sort_by: str | None = None
    sort_dir: str | None = "asc"
    is_shared: bool = False


class DocumentSelectionIn(BaseModel):
    """Which people the bulk document download is for."""
    entity: str                                  # EMPLOYEE / CANDIDATE
    ids: list[int] = Field(min_length=1)         # episode ids / candidate ids


class DocumentBundleIn(DocumentSelectionIn):
    """...and which document types, in the order they become pages."""
    document_type_ids: list[int] = Field(min_length=1)
