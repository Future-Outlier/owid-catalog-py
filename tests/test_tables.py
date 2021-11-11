#
#  test_tables.py
#

from typing import Literal
from owid.catalog.variables import Variable
import tempfile
from os.path import join, exists, splitext
import json

import jsonschema
import pytest
import pandas as pd
import numpy as np

from owid.catalog.tables import Table, SCHEMA
from owid.catalog.meta import VariableMeta, TableMeta
from .mocking import mock


def test_create():
    t = Table({"gdp": [100, 102, 104], "country": ["AU", "SE", "CH"]})
    assert list(t.gdp) == [100, 102, 104]
    assert list(t.country) == ["AU", "SE", "CH"]


def test_add_table_metadata():
    t = Table({"gdp": [100, 102, 104], "country": ["AU", "SE", "CH"]})

    # write some metadata
    t.metadata.short_name = "my_table"
    t.metadata.title = "My table indeed"
    t.metadata.description = (
        "## Well...\n\nI discovered this table in the Summer of '63..."
    )

    # metadata persists with slicing
    t2 = t.iloc[:2]
    assert t2.metadata == t.metadata


def test_read_empty_table_metadata():
    t = Table()
    assert t.metadata == TableMeta()


def test_table_schema_is_valid():
    jsonschema.Draft7Validator.check_schema(SCHEMA)


def test_add_field_metadata():
    t = Table({"gdp": [100, 102, 104], "country": ["AU", "SE", "CH"]})
    title = "GDP per capita in 2011 international $"

    assert t.gdp.metadata == VariableMeta()

    t.gdp.title = title

    # check single field access
    assert t.gdp.title == title

    # check entire metadata access
    assert t.gdp.metadata == VariableMeta(title=title)

    # check field-level metadata persists across slices
    assert t.iloc[:1].gdp.title == title


def test_can_overwrite_column_with_apply():
    table = Table({"a": [1, 2, 3], "b": [4, 5, 6]})
    table.a.metadata.title = "This thing is a"

    v = table.a.apply(lambda x: x + 1)
    assert v.name is not None
    assert v.metadata.title == "This thing is a"

    table["a"] = v
    assert table.a.tolist() == [2, 3, 4]


def test_saving_empty_table_fails():
    t = Table()

    with pytest.raises(Exception):
        t.to_feather("/tmp/example.feather")


# The parametrize decorator runs this test multiple times with different formats
@pytest.mark.parametrize("format", ["csv", "feather"])
def test_round_trip_no_metadata(format: Literal["csv", "feather"]) -> None:
    t1 = Table({"gdp": [100, 102, 104, 100], "countries": ["AU", "SE", "NA", "💡"]})
    with tempfile.TemporaryDirectory() as path:
        filename = join(path, f"table.{format}")
        if format == "feather":
            t1.to_feather(filename)
        else:
            t1.to_csv(filename)

        assert exists(filename)
        assert exists(splitext(filename)[0] + ".meta.json")

        if format == "feather":
            t2 = Table.read_feather(filename)
        else:
            t2 = Table.read_csv(filename)
        assert_tables_eq(t1, t2)


@pytest.mark.parametrize("format", ["csv", "feather"])
def test_round_trip_with_index(format: Literal["csv", "feather"]) -> None:
    t1 = Table({"gdp": [100, 102, 104], "country": ["AU", "SE", "NA"]})
    t1.set_index("country", inplace=True)
    with tempfile.TemporaryDirectory() as path:
        filename = join(path, f"table.{format}")
        if format == "feather":
            t1.to_feather(filename)
        else:
            t1.to_csv(filename)

        assert exists(filename)
        assert exists(splitext(filename)[0] + ".meta.json")

        if format == "feather":
            t2 = Table.read_feather(filename)
        else:
            t2 = Table.read_csv(filename)
        assert_tables_eq(t1, t2)


@pytest.mark.parametrize("format", ["csv", "feather"])
def test_round_trip_with_metadata(format: Literal["csv", "feather"]) -> None:
    t1 = Table({"gdp": [100, 102, 104], "country": ["AU", "SE", "NA"]})
    t1.set_index("country", inplace=True)
    t1.title = "A very special table"
    t1.description = "Something something"

    with tempfile.TemporaryDirectory() as path:
        filename = join(path, f"table.{format}")
        if format == "feather":
            t1.to_feather(filename)
        else:
            t1.to_csv(filename)

        assert exists(filename)
        assert exists(splitext(filename)[0] + ".meta.json")

        if format == "feather":
            t2 = Table.read_feather(filename)
        else:
            t2 = Table.read_csv(filename)
        assert_tables_eq(t1, t2)


def test_field_metadata_copied_between_tables():
    t1 = Table({"gdp": [100, 102, 104], "country": ["AU", "SE", "CH"]})
    t2 = Table({"hdi": [73, 92, 45], "country": ["AU", "SE", "CH"]})

    t1.gdp.description = "A very important measurement"

    t2["gdp"] = t1.gdp
    assert t2.gdp.metadata == t1.gdp.metadata


def test_field_metadata_serialised():
    t1 = Table({"gdp": [100, 102, 104], "country": ["AU", "SE", "CH"]})
    t1.gdp.description = "Something grand"

    with tempfile.TemporaryDirectory() as dirname:
        filename = join(dirname, "test.feather")
        t1.to_feather(filename)

        t2 = Table.read_feather(filename)
        assert_tables_eq(t1, t2)


def test_tables_from_dataframes_have_variable_columns():
    df = pd.DataFrame({"gdp": [100, 102, 104], "country": ["AU", "SE", "CH"]})
    t = Table(df)
    assert isinstance(t.gdp, Variable)

    t.gdp.metadata.title = "test"


def test_tables_always_list_fields_in_metadata():
    df = pd.DataFrame(
        {
            "gdp": [100, 102, 104],
            "country": ["AU", "SE", "CH"],
            "french_fries": ["yes", "no", "yes"],
        }
    )
    t = Table(df.set_index("country"))
    with tempfile.TemporaryDirectory() as temp_dir:
        t.to_feather(join(temp_dir, "example.feather"))
        m = json.load(open(join(temp_dir, "example.meta.json")))

    assert m["primary_key"] == ["country"]
    assert m["fields"] == {"country": {}, "gdp": {}, "french_fries": {}}


def test_field_access_can_be_typecast():
    # https://github.com/owid/owid-catalog-py/issues/12
    t = mock_table()
    t.gdp.metadata.description = "One two three"
    v = t.gdp.astype("object")
    t["gdp"] = v
    assert t.gdp.metadata.description == "One two three"


def test_tables_can_drop_duplicates():
    # https://github.com/owid/owid-catalog-py/issues/11
    t: Table = Table(
        {"gdp": [100, 100, 102, 104], "country": ["AU", "AU", "SE", "CH"]}
    ).set_index(
        "country"
    )  # type: ignore
    t.metadata = mock(TableMeta)

    # in the bug, the dtype of t.duplicated() became object
    dups = t.duplicated()
    assert dups.dtype == np.bool_

    # this caused drop_duplicates() to fail
    t2 = t.drop_duplicates()

    assert isinstance(t2, Table)


def test_extra_fields_ignored_in_metadata() -> None:
    metadata = {"dog": 1, "sheep": [1, 2, 3], "llama": "Sam"}
    table_meta = TableMeta.from_dict(metadata)
    assert table_meta


def assert_tables_eq(lhs: Table, rhs: Table) -> None:
    assert lhs.to_dict() == rhs.to_dict()
    assert lhs.metadata == rhs.metadata
    assert lhs._fields == rhs._fields


def mock_table() -> Table:
    t: Table = Table({"gdp": [100, 102, 104], "country": ["AU", "SE", "CH"]}).set_index(
        "country"
    )  # type: ignore
    t.metadata = mock(TableMeta)
    t.metadata.primary_key = ["country"]
    for col in t.all_columns:
        t._fields[col] = mock(VariableMeta)

    return t
