"""
Tests for the mining module.
"""

import shutil
import unittest
from pathlib import Path

from prism.data.repair.instance import ChangeSelection
from prism.data.repair.mining import RepairInstanceDB


class TestRepairInstanceDB(unittest.TestCase):
    """
    Class for testing RepairInstanceDB.
    """

    _test_db_path = Path("test_db")
    _cache_label = {
        "project_name": "test_project",
        "initial_commit_sha": "abcde",
        "repaired_commit_sha": "12345",
        "initial_coq_version": "8.10.2",
        "repaired_coq_version": "8.10.2"
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
    _expected_relative_filename = RepairInstanceDB.get_file_name(
        change_index=0,
        **_cache_label)
    _expected_absolute_filename = _test_db_path / _expected_relative_filename
    _expected_record = (
        1,
        'test_project',
        'abcde',
        "12345",
        '8.10.2',
        '8.10.2',
        'a 1 b 2',
        'a 1',
        'a 1 b 2 c 3',
        'a 1 b 2 c 3 d 4',
        str(_expected_relative_filename))

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

    def test_insert_record(self) -> None:
        """
        Verify records get inserted properly.
        """
        with RepairInstanceDB(self._test_db_path) as db:
            path: Path = db.insert_record_get_path(
                **self._cache_label,
                change_selection=self._change_selection)
            db.cursor.execute("SELECT * FROM records")
            result = db.cursor.fetchall()
            self.assertListEqual(result, [self._expected_record])
            self.assertEqual(path, self._expected_absolute_filename)
            change_selection = self._change_selection
            assert isinstance(change_selection.added_commands, list)
            change_selection.added_commands.append(("y", 25))
            db.insert_record_get_path(
                **self._cache_label,
                change_selection=change_selection)
            change_selection.added_commands.append(("z", 26))
            db.insert_record_get_path(
                **self._cache_label,
                change_selection=change_selection)
            db.cursor.execute("SELECT * FROM records WHERE id = 3")
            result = db.cursor.fetchone()
            self.assertEqual(result[0], 3)

    def test_get_record(self):
        """
        Verify records are fetched correctly.
        """
        with RepairInstanceDB(self._test_db_path) as db:
            db.insert_record_get_path(
                **self._cache_label,
                change_selection=self._change_selection)
            record = db.get_record(
                **self._cache_label,
                change_selection=self._change_selection)
            expected_record = {
                'id': 1,
                **self._cache_label,
                **{
                    'added_commands': 'a 1 b 2',
                    'affected_commands': 'a 1',
                    'changed_commands': 'a 1 b 2 c 3',
                    'dropped_commands': 'a 1 b 2 c 3 d 4',
                    'file_name': str(self._expected_relative_filename)
                }
            }
            assert record is not None
            self.assertDictEqual(record, expected_record)

    def tearDown(self):
        """
        Remove the test database once each test is finished.
        """
        shutil.rmtree(self._test_db_path)


if __name__ == "__main__":
    unittest.main()
