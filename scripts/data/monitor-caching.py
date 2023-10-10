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
Script to monitor cache extraction progress.
"""
import argparse
import curses
import time
import traceback

from prism.data.cache.server import CoqProjectBuildCache


def main():
    """
    Monitor cache extraction success and error rates.
    """
    # Clear
    parser = argparse.ArgumentParser(description="Monitor cache files.")
    parser.add_argument(
        "cache_dir",
        type=str,
        help="The directory to read cache from and write new cache to.")
    args = parser.parse_args()
    cache = CoqProjectBuildCache(args.cache_dir)

    stdscr = curses.initscr()  # initialize curses screen
    error = None
    try:
        curses.noecho()  # turn off auto echoing of keypress on to screen
        curses.cbreak()  # enter break mode where pressing Enter key
        #  after keystroke is not required for it to register
        stdscr.keypad(
            True)  # enable special Key values such as curses.KEY_LEFT etc
        stdscr.nodelay(True)
        stdscr.clear()
        start = time.time()
        while True:
            message = cache.get_status_message()
            lines = message.split('\n')
            lineno = 0
            for lineno, line in enumerate(lines):
                stdscr.addstr(lineno, 0, line, curses.A_NORMAL)
            stdscr.addstr(lineno + 1, 0, f"UPTIME: {time.time() - start:.2f}")
            stdscr.addstr(lineno + 2, 0, "Enter 'q' to quit")
            ch = stdscr.getch()
            if ch == ord('q'):
                break
            stdscr.refresh()
            stdscr.timeout(1000)
    except Exception:
        error = traceback.format_exc()  # get traceback log of the error
    finally:
        # --- Cleanup on exit ---
        stdscr.keypad(False)
        curses.echo()
        curses.nocbreak()
        curses.endwin()
    if error is not None:
        print(error)


if __name__ == "__main__":
    main()
