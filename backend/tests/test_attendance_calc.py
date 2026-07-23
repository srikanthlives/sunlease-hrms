import unittest

from app import models
from app.utils.attendance_calc import compute_monthly_attendance_stats


class FakeQuery:
    def __init__(self, rows):
        self.rows = rows

    def filter(self, *args, **kwargs):
        return self

    def all(self):
        return self.rows


class FakeDB:
    def __init__(self, rows):
        self.rows = rows

    def query(self, model):
        return FakeQuery(self.rows)


class DummyRecord:
    def __init__(self, status):
        self.status = status


class AttendanceCalcTests(unittest.TestCase):
    def test_compute_monthly_attendance_stats_counts_suspended(self):
        records = [
            DummyRecord(models.AttendanceStatus.PRESENT),
            DummyRecord(models.AttendanceStatus.SUSPENDED),
            DummyRecord(models.AttendanceStatus.SUSPENDED),
        ]

        stats = compute_monthly_attendance_stats(FakeDB(records), employee_id=1, month=7, year=2026)

        self.assertEqual(stats["total"], 1.0)
        self.assertEqual(stats["present"], 1.0)
        self.assertEqual(stats["suspended"], 2.0)


if __name__ == "__main__":
    unittest.main()
