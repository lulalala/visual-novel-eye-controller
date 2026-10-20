from eyeokuri.app import csv_header, csv_row
from eyeokuri.engine import Frame
from eyeokuri.eyes import Observation


def test_csv_row_formats_one_frame():
    obs = Observation(10.5, True, left=0.31234, right=0.3, combined=0.31234, baseline=0.3,
                      ready=True, head_yaw=3.14)
    assert csv_row(Frame(obs, fired=True), start=10.0) == [
        "0.500", "1", "0.3123", "0.3000", "0.3123", "0.3000", "1", "0", "3.1", "", "1",
    ]


def test_csv_row_leaves_missing_values_empty():
    row = csv_row(Frame(Observation(10.5, False), fired=False), start=10.0)
    assert row == ["0.500", "0", "", "", "", "", "0", "0", "", "", "0"]


def test_csv_header_names_each_column_of_a_row():
    row = csv_row(Frame(Observation(0.0, False), fired=False), start=0.0)
    assert len(csv_header()) == len(row)
    assert csv_header()[0] == "t" and csv_header()[-1] == "fired"
