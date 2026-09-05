"""Unit tests for DataLogger -- the structured, single-CSV logging used to
derive raDrift = f(mount RArate) empirically from a live (or simulated)
run. Both guide_step and adjustment rows go in the same file, in real
chronological order, distinguished by the event_type column."""

import csv

from src.model.data_logger import DataLogger


def _read_rows(path):
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def test_creates_the_file_with_a_header(tmp_path):
    path = tmp_path / "data.csv"
    DataLogger(str(path))

    assert path.exists()
    with open(path) as f:
        header = f.readline().strip().split(",")
    assert header == DataLogger.FIELDS


def test_log_guide_step_appends_a_row_with_the_right_event_type(tmp_path):
    path = tmp_path / "data.csv"
    logger = DataLogger(str(path))

    logger.log_guide_step(
        timestamp="2026-09-05T20:00:00", elapsed_seconds=12.0, ra_raw_arcsec=1.5,
        applied_ra_rate=0.002, declination_deg=-45.0, side_of_pier=0, dry_run=False,
    )

    rows = _read_rows(path)
    assert len(rows) == 1
    assert rows[0]["event_type"] == "guide_step"
    assert rows[0]["ra_raw_arcsec"] == "1.5"
    assert rows[0]["applied_ra_rate"] == "0.002"
    # adjustment-only columns are blank on a guide_step row
    assert rows[0]["slope_arcsec_per_sec"] == ""


def test_log_adjustment_appends_a_row_with_the_right_event_type(tmp_path):
    path = tmp_path / "data.csv"
    logger = DataLogger(str(path))

    logger.log_adjustment(
        timestamp="2026-09-05T20:00:00", elapsed_seconds=120.0, previous_ra_rate=0.001,
        slope_arcsec_per_sec=0.02, n_samples=60, declination_deg=-45.0, cos_dec=0.707,
        needed_offset_increment=0.0019, damping_factor=0.3, delta_applied=0.00057,
        new_ra_rate=0.00157, dry_run=False,
    )

    rows = _read_rows(path)
    assert len(rows) == 1
    assert rows[0]["event_type"] == "adjustment"
    assert rows[0]["previous_ra_rate"] == "0.001"
    assert rows[0]["slope_arcsec_per_sec"] == "0.02"
    assert rows[0]["dry_run"] == "False"
    # guide_step-only columns are blank on an adjustment row
    assert rows[0]["ra_raw_arcsec"] == ""


def test_guide_step_and_adjustment_rows_interleave_in_call_order(tmp_path):
    path = tmp_path / "data.csv"
    logger = DataLogger(str(path))

    logger.log_guide_step(ra_raw_arcsec=1.0)
    logger.log_guide_step(ra_raw_arcsec=1.1)
    logger.log_adjustment(slope_arcsec_per_sec=0.01)
    logger.log_guide_step(ra_raw_arcsec=1.2)

    rows = _read_rows(path)
    assert [r["event_type"] for r in rows] == [
        "guide_step", "guide_step", "adjustment", "guide_step"
    ]


def test_missing_fields_are_left_blank_not_erroring(tmp_path):
    path = tmp_path / "data.csv"
    logger = DataLogger(str(path))

    logger.log_guide_step(ra_raw_arcsec=1.0)  # everything else omitted

    rows = _read_rows(path)
    assert rows[0]["ra_raw_arcsec"] == "1.0"
    assert rows[0]["applied_ra_rate"] == ""


def test_reopening_an_existing_file_does_not_duplicate_the_header(tmp_path):
    path = tmp_path / "data.csv"

    logger1 = DataLogger(str(path))
    logger1.log_guide_step(ra_raw_arcsec=1.0)

    logger2 = DataLogger(str(path))  # simulates a second app session
    logger2.log_guide_step(ra_raw_arcsec=2.0)

    with open(path) as f:
        lines = f.readlines()
    assert lines[0].strip() == ",".join(DataLogger.FIELDS)
    assert len(lines) == 3  # header + 2 data rows, not 2 headers
