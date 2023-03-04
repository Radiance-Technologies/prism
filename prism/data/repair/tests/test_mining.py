"""
Tests for the mining module.
"""
import os
import unittest
from pathlib import Path

from prism.data.repair.instance import ChangeSelection
from prism.data.repair.mining import RepairInstanceDB


class TestRepairInstanceDB(unittest.TestCase):
    """
    Class for testing RepairInstanceDB.
    """

    _test_db_path = Path("./test_db.sqlite3")
    _cache_label = {
        "project_name": "test_project",
        "commit_sha": "abcde",
        "coq_version": "8.10.2"
    }
    _change_selection = ChangeSelection(
        [("a",
          1),
         ("b",
          2)],
        [("a",
          1)],
        [("a",
          1),
         ("b",
          2),
         ("c",
          3)],
        [("a",
          1),
         ("b",
          2),
         ("c",
          3),
         ("d",
          4)])
    _test_record = (
        1,
        'test_project',
        'abcde',
        '8.10.2',
        'a 1 b 2',
        'a 1',
        'a 1 b 2 c 3',
        'a 1 b 2 c 3 d 4',
        'repair-1.yml')

    def test_create_table(self):
        """
        Ensure the 'records' table gets created on __init__.
        """
        with RepairInstanceDB(self._test_db_path) as db:
            db.cursor.execute(
                "SELECT name"
                "    FROM sqlite_master"
                "    WHERE type='table' AND name='records';")
            result = db.cursor.fetchall()
            self.assertListEqual(result, [("records",)])

    def test_insert_record(self):
        """
        Verify records get inserted properly.
        """
        with RepairInstanceDB(self._test_db_path) as db:
            path: Path = db.insert_record(
                self._cache_label,
                self._change_selection)
            db.cursor.execute("SELECT * FROM records")
            result = db.cursor.fetchall()
            self.assertListEqual(result, [self._test_record])
            self.assertEqual(path, Path('repair-1.yml'))
            db.insert_record(self._cache_label, self._change_selection)
            db.insert_record(self._cache_label, self._change_selection)
            db.cursor.execute("SELECT * FROM records WHERE id = 3")
            result = db.cursor.fetchone()
            self.assertEqual(result[0], 3)

    def test_get_record(self):
        """
        Verify records are fetched correctly.
        """
        with RepairInstanceDB(self._test_db_path) as db:
            db.insert_record(self._cache_label, self._change_selection)
            record = db.get_record(self._cache_label, self._change_selection)
            expected_record = {
                'id': 1,
                **{k: v for k,
                   v in self._cache_label.items()},
                **{
                    'added_commands': 'a 1 b 2',
                    'affected_commands': 'a 1',
                    'changed_commands': 'a 1 b 2 c 3',
                    'dropped_commands': 'a 1 b 2 c 3 d 4',
                    'file_name': 'repair-1.yml'
                }
            }
            self.assertDictEqual(record, expected_record)

    def tearDown(self):
        """
        Remove the test database once each test is finished.
        """
        os.remove(self._test_db_path)


if __name__ == "__main__":
    unittest.main()
