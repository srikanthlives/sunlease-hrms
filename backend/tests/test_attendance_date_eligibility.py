import unittest
from types import SimpleNamespace

from app.utils.eligibility import is_eligible_on_date


class AttendanceDateEligibilityTests(unittest.TestCase):
    def test_employee_is_not_eligible_before_joining_date(self):
        emp = SimpleNamespace(date_of_joining='2026-05-15', date_of_leaving=None)
        self.assertFalse(is_eligible_on_date(emp, '2026-05-14'))
        self.assertTrue(is_eligible_on_date(emp, '2026-05-15'))

    def test_employee_is_not_eligible_after_leaving_date(self):
        emp = SimpleNamespace(date_of_joining='2026-01-01', date_of_leaving='2026-05-10')
        self.assertTrue(is_eligible_on_date(emp, '2026-05-10'))
        self.assertFalse(is_eligible_on_date(emp, '2026-05-11'))


if __name__ == '__main__':
    unittest.main()
