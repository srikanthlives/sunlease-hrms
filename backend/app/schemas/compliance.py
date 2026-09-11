from datetime import date

from pydantic import BaseModel


class MarkFiledIn(BaseModel):
    challan_reference_number: str
    filed_date: date
    remarks: str | None = None


class AggregateSchemeIn(BaseModel):
    cost_center_id: int | None = None
    year: int
    month: int
