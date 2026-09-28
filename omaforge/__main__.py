import sys


def main() -> int:
    if len(sys.argv) == 1 or sys.argv[1] in ("gui", "--gui"):
        from omaforge.ui.app import run

        return run()
    from omaforge.cli import main as cli_main

    return cli_main(sys.argv[1:])


if __name__ == "__main__":
    sys.exit(main())
