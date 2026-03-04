import duckdb
import pandas as pd

from app.services.datastore import assess_data_quality, get_sample, get_schema, load_dataset, run_query


def test_load_csv(tmp_path):
    csv_file = tmp_path / "test.csv"
    csv_file.write_text("name,value\nalice,10\nbob,20\n")

    conn = duckdb.connect(":memory:")
    table_name = load_dataset(conn, csv_file, "test_data")

    assert table_name == "test_data"
    result = conn.execute("SELECT COUNT(*) FROM test_data").fetchone()
    assert result[0] == 2
    conn.close()


def test_get_schema(tmp_path):
    csv_file = tmp_path / "test.csv"
    csv_file.write_text("name,value\nalice,10\nbob,20\n")

    conn = duckdb.connect(":memory:")
    load_dataset(conn, csv_file, "test_data")
    schema = get_schema(conn, "test_data")

    assert len(schema) == 2
    assert schema[0]["name"] == "name"
    conn.close()


def test_get_sample(tmp_path):
    csv_file = tmp_path / "test.csv"
    csv_file.write_text("name,value\nalice,10\nbob,20\ncharlie,30\n")

    conn = duckdb.connect(":memory:")
    load_dataset(conn, csv_file, "test_data")
    sample = get_sample(conn, "test_data", n=2)

    assert len(sample) == 2
    conn.close()


def test_run_query(tmp_path):
    csv_file = tmp_path / "test.csv"
    csv_file.write_text("name,value\nalice,10\nbob,20\n")

    conn = duckdb.connect(":memory:")
    load_dataset(conn, csv_file, "test_data")
    df = run_query(conn, "SELECT name FROM test_data WHERE value > 15")

    assert isinstance(df, pd.DataFrame)
    assert len(df) == 1
    assert df.iloc[0]["name"] == "bob"
    conn.close()


def test_multiple_tables(tmp_path):
    csv1 = tmp_path / "data1.csv"
    csv1.write_text("id,name\n1,alice\n2,bob\n")
    csv2 = tmp_path / "data2.csv"
    csv2.write_text("id,score\n1,90\n2,85\n")

    conn = duckdb.connect(":memory:")
    load_dataset(conn, csv1, "people")
    load_dataset(conn, csv2, "scores")

    df = run_query(
        conn,
        "SELECT p.name, s.score FROM people p JOIN scores s ON p.id = s.id ORDER BY s.score DESC",
    )
    assert len(df) == 2
    assert df.iloc[0]["name"] == "alice"
    conn.close()


def test_assess_data_quality_clean(tmp_path):
    """Clean data should score high with no findings."""
    csv_file = tmp_path / "clean.csv"
    csv_file.write_text("name,value\nalice,10\nbob,20\ncharlie,30\n")

    conn = duckdb.connect(":memory:")
    load_dataset(conn, csv_file, "clean")
    report = assess_data_quality(conn, "clean")

    assert report["row_count"] == 3
    assert report["column_count"] == 2
    assert report["duplicate_rows"] == 0
    assert report["completeness_pct"] == 100.0
    assert report["overall_score"] >= 90
    assert len(report["columns"]) == 2
    # No warning/error findings for clean data
    severe = [f for f in report["findings"] if f["severity"] in ("error", "warning")]
    assert len(severe) == 0
    conn.close()


def test_assess_data_quality_missing_values(tmp_path):
    """Columns with nulls should be flagged."""
    csv_file = tmp_path / "missing.csv"
    csv_file.write_text("name,value\nalice,10\n,\nbob,20\n,\n")

    conn = duckdb.connect(":memory:")
    load_dataset(conn, csv_file, "missing")
    report = assess_data_quality(conn, "missing")

    assert report["completeness_pct"] < 100
    # At least one column should have some_missing or high_missing
    cols_with_missing = [
        c for c in report["columns"] if c.get("missing_count", 0) > 0
    ]
    assert len(cols_with_missing) > 0
    conn.close()


def test_assess_data_quality_duplicates(tmp_path):
    """Duplicate rows should be detected."""
    csv_file = tmp_path / "dups.csv"
    csv_file.write_text("name,value\nalice,10\nalice,10\nbob,20\n")

    conn = duckdb.connect(":memory:")
    load_dataset(conn, csv_file, "dups")
    report = assess_data_quality(conn, "dups")

    assert report["duplicate_rows"] > 0
    dup_findings = [f for f in report["findings"] if "duplicate" in f["message"].lower()]
    assert len(dup_findings) > 0
    conn.close()


def test_assess_data_quality_empty(tmp_path):
    """Empty dataset should return a meaningful report."""
    csv_file = tmp_path / "empty.csv"
    csv_file.write_text("name,value\n")

    conn = duckdb.connect(":memory:")
    load_dataset(conn, csv_file, "empty")
    report = assess_data_quality(conn, "empty")

    assert report["row_count"] == 0
    assert report["overall_score"] == 0
    assert any(f["severity"] == "error" for f in report["findings"])
    conn.close()
