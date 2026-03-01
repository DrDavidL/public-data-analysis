import duckdb
import pandas as pd

from app.services.datastore import get_sample, get_schema, load_dataset, run_query


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
