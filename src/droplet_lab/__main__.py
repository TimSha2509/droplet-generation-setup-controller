"""Allows `python -m droplet_lab` to invoke the CLI."""

from droplet_lab.cli import app


def main() -> None:
    app()


if __name__ == "__main__":
    main()
