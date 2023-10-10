#
# Copyright (c) 2023 Radiance Technologies, Inc.
#
# This file is part of PRISM
# (see https://github.com/orgs/Radiance-Technologies/prism).
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Lesser General Public License as
# published by the Free Software Foundation, either version 3 of the
# License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Lesser General Public License for more details.
#
# You should have received a copy of the GNU Lesser General Public
# License along with this program. If not, see
# <http://www.gnu.org/licenses/>.
#
"""
Tests for the mining module.
"""

import shutil
import unittest
from pathlib import Path

from prism.data.repair.instance import ChangeSelection
from prism.data.repair.mining import (
    CommitPairDBRecord,
    RepairInstanceDB,
    RepairInstanceDBRecord,
)

TEST_DIR = Path(__file__).parent


class TestRepairInstanceDB(unittest.TestCase):
    """
    Class for testing RepairInstanceDB.
    """

    _test_db_path = TEST_DIR / "test_db"
    _alt_test_db_path = TEST_DIR / "alt_test_db"
    _commit_pair = CommitPairDBRecord(
        project_name="test_project",
        initial_commit_sha="abcde",
        repaired_commit_sha="12345",
        initial_coq_version="8.10.2",
        repaired_coq_version="8.10.2")
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
    _alt_change_selection = ChangeSelection(
        [("a",
          1)],
        [("a",
          1)],
        [("a",
          1),
         ("c",
          3)],
        [("a",
          1),
         ("c",
          3),
         ("d",
          4)])
    """
    Alternative selection that drops changes to b.
    """
    _expected_relative_filename = RepairInstanceDB.get_file_name(
        _commit_pair,
        change_index=0)
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
                self._commit_pair,
                change_selection=self._change_selection)
            db.cursor.execute("SELECT * FROM records")
            result = db.cursor.fetchall()
            self.assertListEqual(result, [self._expected_record])
            self.assertEqual(path, self._expected_absolute_filename)
            change_selection = self._change_selection
            assert isinstance(change_selection.added_commands, list)
            change_selection.added_commands.append(("y", 25))
            db.insert_record_get_path(
                self._commit_pair,
                change_selection=change_selection)
            change_selection.added_commands.append(("z", 26))
            db.insert_record_get_path(
                self._commit_pair,
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
                self._commit_pair,
                change_selection=self._change_selection)
            record = db.get_record(
                self._commit_pair,
                change_selection=self._change_selection)
            expected_record = RepairInstanceDBRecord(
                *self._commit_pair,
                **{
                    'added_commands': 'a 1 b 2',
                    'affected_commands': 'a 1',
                    'changed_commands': 'a 1 b 2 c 3',
                    'dropped_commands': 'a 1 b 2 c 3 d 4',
                    'file_name': str(self._expected_relative_filename)
                },
                id=1,
            )
            assert record is not None
            self.assertEqual(record, expected_record)

    def test_merge(self):
        """
        Verify two databases can be merged.
        """
        with RepairInstanceDB(self._test_db_path) as db:
            original_path = db.insert_record_get_path(
                self._commit_pair,
                change_selection=self._change_selection)
            with RepairInstanceDB(self._alt_test_db_path) as alt_db:
                alternative_path = alt_db.insert_record_get_path(
                    self._commit_pair,
                    change_selection=self._change_selection)
                old_path = alt_db.insert_record_get_path(
                    self._commit_pair,
                    change_selection=self._alt_change_selection)
                db.merge(alt_db, copy=False)
            records = list(db.get_records_iter())
        new_path = db.db_directory / db.get_file_name(self._commit_pair, 1)
        self.assertEqual(len(records), 2)
        self.assertNotEqual(original_path, alternative_path)
        self.assertNotEqual(old_path, new_path)
        expected_records = [
            RepairInstanceDBRecord(
                *self._commit_pair,
                **self._change_selection.as_joined_dict(),
                id=1,
                file_name=str(original_path.relative_to(db.db_directory))),
            RepairInstanceDBRecord(
                *self._commit_pair,
                **self._alt_change_selection.as_joined_dict(),
                id=2,
                file_name=str(new_path.relative_to(db.db_directory)))
        ]
        self.assertEqual(records, expected_records)

    def tearDown(self):
        """
        Remove the test database once each test is finished.
        """
        shutil.rmtree(self._test_db_path, ignore_errors=True)
        shutil.rmtree(self._alt_test_db_path, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
