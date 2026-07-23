import unittest

from app import models
from app.routers.compliance import _build_pf_rows, _build_pf_text_content


class DummyLine:
    def __init__(self, code, amount):
        self.component_code = code
        self.amount = amount


class DummyPayslip:
    def __init__(self, employee_id, gross_earnings, lines):
        self.employee_id = employee_id
        self.gross_earnings = gross_earnings
        self.lines = lines
        self.present_days = 20
        self.total_days = 30


class DummyEmployee:
    def __init__(self, employee_id, employee_code, first_name, last_name, uan, pf_eligible, eps_eligible):
        self.id = employee_id
        self.employee_code = employee_code
        self.first_name = first_name
        self.last_name = last_name
        self.uan = uan
        self.pf_eligible = pf_eligible
        self.eps_eligible = eps_eligible


class DummyDB:
    def __init__(self, employees, payslips):
        self._employees = employees
        self._payslips = payslips

    def query(self, model):
        if model is models.Employee:
            return type('Q', (), {'filter_by': lambda self, **kwargs: type('F', (), {'all': lambda self: self._employees})()})()
        if model is models.Payslip:
            return type('Q', (), {'filter_by': lambda self, **kwargs: type('F', (), {'all': lambda self: self._payslips})()})()
        raise AssertionError(model)


class CompliancePfTests(unittest.TestCase):
    def test_build_pf_rows_uses_eligibility_and_wage_rules(self):
        emp = DummyEmployee(1, 'EMP001', 'Ada', 'Lovelace', '123456', True, True)
        ps = DummyPayslip(1, 12000, [DummyLine('BASIC', 8000), DummyLine('DA', 2000)])

        rows = _build_pf_rows(DummyDB([emp], [ps]), month=4, year=2026)

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['UAN'], '123456')
        self.assertEqual(rows[0]['MEMBER NAME'], 'Ada Lovelace')
        self.assertEqual(rows[0]['GROSS WAGES'], 10000)
        self.assertEqual(rows[0]['EPF WAGES'], 10000)
        self.assertEqual(rows[0]['EPS WAGES'], 10000)
        self.assertEqual(rows[0]['EPF CONTRI REMITTED'], 1200.0)
        self.assertEqual(rows[0]['EPS CONTRI REMITTED'], 833.0)
        self.assertEqual(rows[0]['EPF EPS DIFF REMITTED'], 367.0)

    def test_build_pf_rows_uses_basic_and_da_only_for_gross_wages(self):
        emp = DummyEmployee(2, 'EMP002', 'Grace', 'Hopper', '654321', True, True)
        ps = DummyPayslip(2, 25000, [DummyLine('HRA', 25000)])

        rows = _build_pf_rows(DummyDB([emp], [ps]), month=4, year=2026)

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['GROSS WAGES'], 0.0)
        self.assertEqual(rows[0]['EPF WAGES'], 0.0)
        self.assertEqual(rows[0]['EPF CONTRI REMITTED'], 0.0)

    def test_build_pf_text_content_skips_first_column_and_uses_separator(self):
        rows = [{
            'OPTEDOUT': 'N',
            'UAN': '123456',
            'MEMBER NAME': 'Ada Lovelace',
            'GROSS WAGES': 10000,
            'EPF WAGES': 10000,
            'EPS WAGES': 10000,
            'EDLI WAGES': 10000,
            'EPF CONTRI REMITTED': 1200,
            'EPS CONTRI REMITTED': 833,
            'EPF EPS DIFF REMITTED': 367,
            'NCP DAYS': 0,
            'REFUND OF ADVANCES': 0,
        }]

        content = _build_pf_text_content(rows)

        self.assertEqual(content, '123456#~#Ada Lovelace#~#10000#~#10000#~#10000#~#10000#~#1200#~#833#~#367#~#0#~#0\n')


if __name__ == '__main__':
    unittest.main()
