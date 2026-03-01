from app.services.datastore import sanitize_table_name


def test_sanitize_table_name():
    assert sanitize_table_name("my-dataset") == "my_dataset"
    assert sanitize_table_name("123abc") == "t_123abc"
    assert sanitize_table_name("Hello World!") == "hello_world"
    assert sanitize_table_name("a" * 100)[:63] == "a" * 63


def test_sanitize_table_name_special_chars():
    assert sanitize_table_name("data.gov/test") == "data_gov_test"
    assert sanitize_table_name("  spaces  ") == "spaces"
