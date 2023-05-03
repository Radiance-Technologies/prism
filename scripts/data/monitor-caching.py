"""
Script to perform cache extraction.
"""
import argparse
import time
import curses
import traceback

from prism.data.build_cache import CoqProjectBuildCache


def main():
    """
    Monitor cache files.
    """
    # Clear
    parser = argparse.ArgumentParser(
        description="Monitor cache files.")
    parser.add_argument(
        "cache_dir",
        type=str,
        help="The directory to read cache from and write new cache to.")
    args = parser.parse_args()
    cache = CoqProjectBuildCache(args.cache_dir)

    stdscr = curses.initscr()   # initialize curses screen
    try:
        curses.noecho()             # turn off auto echoing of keypress on to screen
        curses.cbreak()             # enter break mode where pressing Enter key
                                    #  after keystroke is not required for it to register
        stdscr.keypad(True)            # enable special Key values such as curses.KEY_LEFT etc
        stdscr.nodelay(True)
        stdscr.clear()
        start = time.time()
        while True:
            message = cache.get_status_message()
            lines = message.split('\n')
            lineno = 0
            for lineno, line in enumerate(lines):
                stdscr.addstr(lineno, 0, line, curses.A_NORMAL)
            stdscr.addstr(lineno+1, 0, f"UPTIME: {time.time() - start}")
            stdscr.addstr(lineno+2, 0, "Enter 'q' to quit")
            ch = stdscr.getch()
            if ch == ord('q'):
                break
            stdscr.refresh()
            stdscr.timeout(1000)
    except Exception:
        traceback.print_exc()     # print trace back log of the error
    finally:
        # --- Cleanup on exit ---
        stdscr.keypad(False)
        curses.echo()
        curses.nocbreak()
        curses.endwin()


if __name__ == "__main__":
    main()
