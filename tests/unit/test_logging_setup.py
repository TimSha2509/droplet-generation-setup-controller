from pathlib import Path

from loguru import logger

from droplet_lab.logging_setup import setup_logging


def test_setup_creates_log_file_and_writes(tmp_path: Path) -> None:
    log_file = setup_logging(tmp_path, level="DEBUG")
    logger.bind(component="test").info("hello world")
    logger.complete()  # flush async sinks

    assert log_file.exists()
    content = log_file.read_text()
    assert "hello world" in content
    assert "test" in content


def test_setup_is_idempotent(tmp_path: Path) -> None:
    setup_logging(tmp_path)
    setup_logging(tmp_path)  # must not crash
    logger.bind(component="x").info("ok")
    logger.complete()
