from datetime import date

from pydantic import BaseModel, Field, model_validator


class SalaryComponentIn(BaseModel):
    code: str
    name: str
    component_type: str  # EARNING/DEDUCTION/EMPLOYER_CONTRIBUTION/ADDITION
    default_calculation: str = "FIXED"  # FIXED/PERCENTAGE_OF_BASIC/FORMULA
    default_value: float = 0
    formula: str | None = None  # required when default_calculation="FORMULA"
    sequence: int = 0
    is_statutory: bool = False
    is_active: bool = True

    @model_validator(mode="after")
    def _check_type(self):
        if self.component_type not in ("EARNING", "DEDUCTION", "EMPLOYER_CONTRIBUTION", "ADDITION"):
            raise ValueError("component_type must be EARNING, DEDUCTION, EMPLOYER_CONTRIBUTION or ADDITION")
        if self.default_calculation not in ("FIXED", "PERCENTAGE_OF_BASIC", "FORMULA"):
            raise ValueError("default_calculation must be FIXED, PERCENTAGE_OF_BASIC or FORMULA")
        if self.default_calculation == "FORMULA" and not self.formula:
            raise ValueError("formula is required when default_calculation is FORMULA")
        return self


class SalaryStructureComponentIn(BaseModel):
    episode_id: int
    component_id: int
    amount: float | None = None
    percentage: float | None = None
    formula: str | None = None  # per-employee override of the component's default formula
    effective_from: date

    @model_validator(mode="after")
    def _check_amount_or_percentage(self):
        if self.amount is None and self.percentage is None and self.formula is None:
            raise ValueError("One of amount, percentage or formula must be provided")
        return self


class SalaryStructureComponentEndIn(BaseModel):
    effective_to: date


class PayrollRunIn(BaseModel):
    cost_center_id: int | None = None
    year: int
    month: int = Field(ge=1, le=12)


class AdhocPayEntryIn(BaseModel):
    episode_id: int
    year: int
    month: int = Field(ge=1, le=12)
    label: str
    amount: float
    is_earning: bool = True
    remarks: str | None = None


class SalaryComponentOverrideIn(BaseModel):
    episode_id: int
    component_id: int
    year: int
    month: int = Field(ge=1, le=12)
    amount: float
    remarks: str | None = None


class StatutoryConfigIn(BaseModel):
    effective_from: date
    pf_employee_rate: float = 0.12
    pf_employer_rate: float = 0.12
    pf_wage_ceiling: float = 15000
    eps_rate: float = 0.0833
    eps_wage_ceiling: float = 15000
    esi_employee_rate: float = 0.0075
    esi_employer_rate: float = 0.0325
    esi_wage_ceiling: float = 21000
    gratuity_days_per_year: int = 15
    gratuity_divisor: int = 26
    lwf_employee_amount: float = 0
    lwf_employer_amount: float = 0
    lwf_frequency: str = "MONTHLY"


class ProfessionalTaxSlabIn(BaseModel):
    state: str
    min_gross: float = 0
    max_gross: float | None = None
    monthly_amount: float
    is_active: bool = True


class SalaryTemplateIn(BaseModel):
    code: str
    name: str
    cost_center_id: int | None = None  # null = applies to any Cost Center (global)
    project_id: int | None = None  # null = applies to any Project within the Cost Center
    is_active: bool = True


class SalaryTemplateComponentIn(BaseModel):
    component_id: int
    amount: float | None = None
    percentage: float | None = None
    formula: str | None = None

    @model_validator(mode="after")
    def _check_amount_or_percentage(self):
        if self.amount is None and self.percentage is None and self.formula is None:
            raise ValueError("One of amount, percentage or formula must be provided")
        return self


class ApplyTemplateComponentIn(BaseModel):
    component_id: int
    amount: float | None = None
    percentage: float | None = None
    formula: str | None = None


class ApplyTemplateIn(BaseModel):
    episode_id: int
    template_id: int
    effective_from: date
    components: list[ApplyTemplateComponentIn]
