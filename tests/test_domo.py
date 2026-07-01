"""Unit tests for domoio.domo.Domo — all HTTP calls are mocked."""
import io
import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch, call
from domoio.domo import Domo, SecretStr


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _mock_response(status_code: int = 200, json_data=None, content: bytes = b"") -> MagicMock:
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = json_data if json_data is not None else {}
    resp.content = content
    resp.raise_for_status = MagicMock()
    if status_code >= 400:
        import httpx
        resp.raise_for_status.side_effect = httpx.HTTPStatusError(
            message=f"{status_code}", request=MagicMock(), response=resp
        )
    return resp


def _make_domo() -> Domo:
    """Return a Domo instance with _get_access_token mocked out."""
    with patch("httpx.get") as mock_get:
        mock_get.return_value = _mock_response(200, {"access_token": "test-token"})
        domo = Domo(
            tenant="test-tenant",
            developer_token="dev-token",
            client_id="client-id",
            client_secret="client-secret",
        )
    return domo


# ---------------------------------------------------------------------------
# __init__ / _get_access_token
# ---------------------------------------------------------------------------

class TestInit:
    def test_raises_if_any_arg_missing(self):
        with pytest.raises(ValueError):
            with patch("httpx.get"):
                Domo(tenant="", developer_token="d", client_id="c", client_secret="s")

    def test_access_token_stored(self):
        domo = _make_domo()
        assert domo._access_token.get_secret_value() == "test-token"

    def test_get_access_token_raises_on_http_error(self):
        with patch("httpx.get") as mock_get:
            mock_get.return_value = _mock_response(401)
            with pytest.raises(Exception):
                Domo(tenant="t", developer_token="d", client_id="c", client_secret="s")

    def test_get_access_token_raises_when_token_missing_in_response(self):
        with patch("httpx.get") as mock_get:
            mock_get.return_value = _mock_response(200, {})
            with pytest.raises(ValueError, match="Unable to authenticate"):
                Domo(tenant="t", developer_token="d", client_id="c", client_secret="s")


# ---------------------------------------------------------------------------
# _get_url
# ---------------------------------------------------------------------------

class TestGetUrl:
    def test_access_token_uses_api_domo(self):
        domo = _make_domo()
        url = domo._get_url("access_token", "v1/datasets")
        assert url == "https://api.domo.com/v1/datasets"

    def test_developer_token_uses_tenant_domain(self):
        domo = _make_domo()
        url = domo._get_url("developer_token", "api/data/v3/datasources")
        assert url == "https://test-tenant.domo.com/api/data/v3/datasources"

    def test_leading_slash_stripped(self):
        domo = _make_domo()
        url = domo._get_url("access_token", "/v1/datasets/abc")
        assert url == "https://api.domo.com/v1/datasets/abc"


# ---------------------------------------------------------------------------
# _get_headers
# ---------------------------------------------------------------------------

class TestGetHeaders:
    def test_access_token_sets_authorization(self):
        domo = _make_domo()
        headers = domo._get_headers("access_token", {})
        assert headers["Authorization"] == "Bearer test-token"

    def test_developer_token_sets_x_domo_header(self):
        domo = _make_domo()
        headers = domo._get_headers("developer_token", {})
        assert headers["X-DOMO-Developer-Token"] == "dev-token"

    def test_default_content_type_and_accept(self):
        domo = _make_domo()
        headers = domo._get_headers("access_token", {})
        assert headers["Content-Type"] == "application/json"
        assert headers["Accept"] == "application/json"


# ---------------------------------------------------------------------------
# get_dataset_details_url
# ---------------------------------------------------------------------------

class TestGetDatasetDetailsUrl:
    def test_url_format(self):
        domo = _make_domo()
        url = domo.get_dataset_details_url("abc-123")
        assert url == "https://test-tenant.domo.com/datasources/abc-123/details/"


# ---------------------------------------------------------------------------
# get_datasets
# ---------------------------------------------------------------------------

class TestGetDatasets:
    def test_returns_list_of_datasets(self):
        domo = _make_domo()
        datasets = [{"id": "1", "name": "Sales"}]
        with patch.object(domo, "_get") as mock_get:
            mock_get.return_value = _mock_response(200, datasets)
            result = domo.get_datasets(name_like="Sales")
        assert result == datasets

    def test_sends_correct_params(self):
        domo = _make_domo()
        with patch.object(domo, "_get") as mock_get:
            mock_get.return_value = _mock_response(200, [])
            domo.get_datasets(name_like="Sales", limit=10, sort="lastTouched")
        params = mock_get.call_args.kwargs["params"]
        assert params["nameLike"] == "Sales"
        assert params["sort"] == "lastTouched"

    def test_returns_empty_list_when_response_not_list(self):
        domo = _make_domo()
        with patch.object(domo, "_get") as mock_get:
            mock_get.return_value = _mock_response(200, {})
            result = domo.get_datasets(name_like="x")
        assert result == []


# ---------------------------------------------------------------------------
# get_dataset_id_by_name
# ---------------------------------------------------------------------------

class TestGetDatasetIdByName:
    def test_exact_match_returns_id(self):
        domo = _make_domo()
        with patch.object(domo, "get_datasets") as mock:
            mock.return_value = [{"id": "abc", "name": "Sales"}, {"id": "xyz", "name": "Sales Data"}]
            result = domo.get_dataset_id_by_name("Sales", exact_match=True)
        assert result == "abc"

    def test_exact_match_returns_none_when_not_found(self):
        domo = _make_domo()
        with patch.object(domo, "get_datasets") as mock:
            mock.return_value = [{"id": "xyz", "name": "Other"}]
            result = domo.get_dataset_id_by_name("Sales", exact_match=True)
        assert result is None

    def test_exact_match_raises_on_duplicates(self):
        domo = _make_domo()
        with patch.object(domo, "get_datasets") as mock:
            mock.return_value = [{"id": "a", "name": "Sales"}, {"id": "b", "name": "Sales"}]
            with pytest.raises(ValueError, match="Found 2 datasets"):
                domo.get_dataset_id_by_name("Sales", exact_match=True)

    def test_non_exact_returns_first(self):
        domo = _make_domo()
        with patch.object(domo, "get_datasets") as mock:
            mock.return_value = [{"id": "a", "name": "Sales Data"}, {"id": "b", "name": "Sales Report"}]
            result = domo.get_dataset_id_by_name("Sales", exact_match=False)
        assert result == "a"

    def test_non_exact_returns_none_when_empty(self):
        domo = _make_domo()
        with patch.object(domo, "get_datasets") as mock:
            mock.return_value = []
            result = domo.get_dataset_id_by_name("Sales", exact_match=False)
        assert result is None


# ---------------------------------------------------------------------------
# dataset_exists
# ---------------------------------------------------------------------------

class TestDatasetExists:
    def test_exists_by_id_true(self):
        domo = _make_domo()
        with patch.object(domo, "_get") as mock_get:
            mock_get.return_value = _mock_response(200)
            assert domo.dataset_exists(dataset_id="abc") is True

    def test_exists_by_id_false(self):
        domo = _make_domo()
        with patch.object(domo, "_get") as mock_get:
            mock_get.return_value = _mock_response(404)
            assert domo.dataset_exists(dataset_id="abc") is False

    def test_exists_by_name_delegates_to_get_dataset_id_by_name(self):
        domo = _make_domo()
        with patch.object(domo, "get_dataset_id_by_name", return_value="abc") as mock:
            assert domo.dataset_exists(dataset_name="Sales") is True
            mock.assert_called_once_with("Sales")

    def test_exists_by_name_false_when_not_found(self):
        domo = _make_domo()
        with patch.object(domo, "get_dataset_id_by_name", return_value=None):
            assert domo.dataset_exists(dataset_name="Sales") is False

    def test_raises_when_neither_provided(self):
        domo = _make_domo()
        with pytest.raises(ValueError):
            domo.dataset_exists()

    def test_raises_when_both_provided(self):
        domo = _make_domo()
        with pytest.raises(ValueError):
            domo.dataset_exists(dataset_id="abc", dataset_name="Sales")


# ---------------------------------------------------------------------------
# create_dataset
# ---------------------------------------------------------------------------

class TestCreateDataset:
    def test_returns_dataset_id(self):
        domo = _make_domo()
        columns = [{"name": "Col1", "type": "STRING"}]
        with patch.object(domo, "_post") as mock_post:
            mock_post.return_value = _mock_response(200, {"id": "new-id"})
            result = domo.create_dataset("My Dataset", "desc", columns)
        assert result == "new-id"

    def test_sends_correct_payload(self):
        domo = _make_domo()
        columns = [{"name": "Col1", "type": "STRING"}]
        with patch.object(domo, "_post") as mock_post:
            mock_post.return_value = _mock_response(200, {"id": "new-id"})
            domo.create_dataset("My Dataset", "desc", columns)
        payload = mock_post.call_args.kwargs["json"]
        assert payload["name"] == "My Dataset"
        assert payload["description"] == "desc"
        assert payload["schema"]["columns"] == columns

    def test_empty_description_defaults_to_empty_string(self):
        domo = _make_domo()
        with patch.object(domo, "_post") as mock_post:
            mock_post.return_value = _mock_response(200, {"id": "x"})
            domo.create_dataset("My Dataset", None, [])
        assert mock_post.call_args.kwargs["json"]["description"] == ""


# ---------------------------------------------------------------------------
# import_data
# ---------------------------------------------------------------------------

class TestImportData:
    def test_returns_true_on_204(self):
        domo = _make_domo()
        with patch.object(domo, "_put") as mock_put:
            mock_put.return_value = _mock_response(204)
            result = domo.import_data("abc", "REPLACE", b"col1\nval1")
        assert result is True

    def test_returns_false_on_200(self):
        domo = _make_domo()
        with patch.object(domo, "_put") as mock_put:
            mock_put.return_value = _mock_response(200)
            result = domo.import_data("abc", "REPLACE", b"col1\nval1")
        assert result is False

    def test_sends_csv_content_type(self):
        domo = _make_domo()
        with patch.object(domo, "_put") as mock_put:
            mock_put.return_value = _mock_response(204)
            domo.import_data("abc", "APPEND", b"data")
        assert mock_put.call_args.kwargs["content_type"] == "text/csv"

    def test_sends_update_method_param(self):
        domo = _make_domo()
        with patch.object(domo, "_put") as mock_put:
            mock_put.return_value = _mock_response(204)
            domo.import_data("abc", "REPLACE", b"data")
        assert mock_put.call_args.kwargs["params"] == {"updateMethod": "REPLACE"}


# ---------------------------------------------------------------------------
# delete_dataset
# ---------------------------------------------------------------------------

class TestDeleteDataset:
    def test_returns_true_on_success(self):
        domo = _make_domo()
        with patch.object(domo, "_delete") as mock_del:
            mock_del.return_value = _mock_response(200)
            result = domo.delete_dataset("abc")
        assert result is True

    def test_returns_false_on_404(self):
        domo = _make_domo()
        with patch.object(domo, "_delete") as mock_del:
            mock_del.return_value = _mock_response(404)
            result = domo.delete_dataset("abc")
        assert result is False


# ---------------------------------------------------------------------------
# truncate_dataset
# ---------------------------------------------------------------------------

class TestTruncateDataset:
    def test_imports_header_only_csv(self):
        domo = _make_domo()
        columns = [{"name": "Col1", "type": "STRING"}, {"name": "Col2", "type": "LONG"}]
        with patch.object(domo, "get_columns_from_dataset", return_value=columns):
            with patch.object(domo, "import_data") as mock_import:
                mock_import.return_value = True
                domo.truncate_dataset("abc")
        mock_import.assert_called_once_with(
            dataset_id="abc",
            update_method="REPLACE",
            csv_bytes=b"Col1,Col2",
        )


# ---------------------------------------------------------------------------
# replace / append variants
# ---------------------------------------------------------------------------

class TestReplaceAndAppend:
    def test_replace_csv(self, tmp_path):
        domo = _make_domo()
        csv_file = tmp_path / "data.csv"
        csv_file.write_bytes(b"col\nval")
        with patch.object(domo, "import_data") as mock_import:
            mock_import.return_value = True
            domo.replace_csv("abc", csv_file)
        mock_import.assert_called_once_with(dataset_id="abc", update_method="REPLACE", csv_bytes=b"col\nval")

    def test_append_csv(self, tmp_path):
        domo = _make_domo()
        csv_file = tmp_path / "data.csv"
        csv_file.write_bytes(b"col\nval")
        with patch.object(domo, "import_data") as mock_import:
            mock_import.return_value = True
            domo.append_csv("abc", csv_file)
        mock_import.assert_called_once_with(dataset_id="abc", update_method="APPEND", csv_bytes=b"col\nval")

    def test_replace_polars(self):
        domo = _make_domo()
        import polars as pl
        df = pl.DataFrame({"col": [1, 2]})
        with patch.object(domo, "import_data") as mock_import:
            mock_import.return_value = True
            domo.replace_polars("abc", df)
        call_kwargs = mock_import.call_args.kwargs
        assert call_kwargs["update_method"] == "REPLACE"
        assert b"col" in call_kwargs["csv_bytes"]

    def test_append_polars(self):
        domo = _make_domo()
        import polars as pl
        df = pl.DataFrame({"col": [1, 2]})
        with patch.object(domo, "import_data") as mock_import:
            mock_import.return_value = True
            domo.append_polars("abc", df)
        assert mock_import.call_args.kwargs["update_method"] == "APPEND"

    def test_replace_parquet(self, tmp_path):
        domo = _make_domo()
        import polars as pl
        parquet_file = tmp_path / "data.parquet"
        pl.DataFrame({"col": [1, 2]}).write_parquet(parquet_file)
        with patch.object(domo, "import_data") as mock_import:
            mock_import.return_value = True
            domo.replace_parquet("abc", parquet_file)
        assert mock_import.call_args.kwargs["update_method"] == "REPLACE"

    def test_append_parquet(self, tmp_path):
        domo = _make_domo()
        import polars as pl
        parquet_file = tmp_path / "data.parquet"
        pl.DataFrame({"col": [1, 2]}).write_parquet(parquet_file)
        with patch.object(domo, "import_data") as mock_import:
            mock_import.return_value = True
            domo.append_parquet("abc", parquet_file)
        assert mock_import.call_args.kwargs["update_method"] == "APPEND"


# ---------------------------------------------------------------------------
# get_columns_from_dataset
# ---------------------------------------------------------------------------

class TestGetColumnsFromDataset:
    def test_returns_column_list(self):
        domo = _make_domo()
        payload = {"schema": {"columns": [{"name": "Col1", "type": "STRING"}, {"name": "Col2", "type": "LONG"}]}}
        with patch.object(domo, "_get") as mock_get:
            mock_get.return_value = _mock_response(200, payload)
            result = domo.get_columns_from_dataset("abc")
        assert result == [{"name": "Col1", "type": "STRING"}, {"name": "Col2", "type": "LONG"}]


# ---------------------------------------------------------------------------
# get_columns_from_csv / get_columns_from_parquet
# ---------------------------------------------------------------------------

class TestGetColumnsFromFile:
    def test_get_columns_from_csv(self, tmp_path):
        domo = _make_domo()
        csv_file = tmp_path / "data.csv"
        csv_file.write_text("name,age\nAlice,30\n")
        result = domo.get_columns_from_csv(csv_file)
        names = [c["name"] for c in result]
        assert "name" in names
        assert "age" in names

    def test_get_columns_from_parquet(self, tmp_path):
        domo = _make_domo()
        import polars as pl
        parquet_file = tmp_path / "data.parquet"
        pl.DataFrame({"name": ["Alice"], "age": [30]}).write_parquet(parquet_file)
        result = domo.get_columns_from_parquet(parquet_file)
        names = [c["name"] for c in result]
        assert "name" in names
        assert "age" in names


# ---------------------------------------------------------------------------
# query_dataset_row_count
# ---------------------------------------------------------------------------

class TestQueryDatasetRowCount:
    def test_returns_count(self):
        domo = _make_domo()
        with patch.object(domo, "_post") as mock_post:
            mock_post.return_value = _mock_response(200, {"rows": [[42]]})
            result = domo.query_dataset_row_count("abc")
        assert result == 42

    def test_returns_zero_on_empty_result(self):
        domo = _make_domo()
        with patch.object(domo, "_post") as mock_post:
            mock_post.return_value = _mock_response(200, {"rows": []})
            result = domo.query_dataset_row_count("abc")
        assert result == 0

    def test_filter_added_to_sql(self):
        domo = _make_domo()
        with patch.object(domo, "_post") as mock_post:
            mock_post.return_value = _mock_response(200, {"rows": [[5]]})
            domo.query_dataset_row_count("abc", filter={"Status": "Active"})
        sql = mock_post.call_args.kwargs["json"]["sql"]
        assert "Status" in sql
        assert "Active" in sql


# ---------------------------------------------------------------------------
# query_dataset
# ---------------------------------------------------------------------------

class TestQueryDataset:
    def test_returns_response_json(self):
        domo = _make_domo()
        payload = {"columns": ["Col1"], "rows": [["val"]]}
        with patch.object(domo, "_post") as mock_post:
            mock_post.return_value = _mock_response(200, payload)
            result = domo.query_dataset("abc")
        assert result == payload

    def test_column_list_in_sql(self):
        domo = _make_domo()
        with patch.object(domo, "_post") as mock_post:
            mock_post.return_value = _mock_response(200, {"columns": [], "rows": []})
            domo.query_dataset("abc", columns=["Col1", "Col2"])
        sql = mock_post.call_args.kwargs["json"]["sql"]
        assert "`Col1`" in sql
        assert "`Col2`" in sql

    def test_limit_in_sql(self):
        domo = _make_domo()
        with patch.object(domo, "_post") as mock_post:
            mock_post.return_value = _mock_response(200, {"columns": [], "rows": []})
            domo.query_dataset("abc", limit=100)
        sql = mock_post.call_args.kwargs["json"]["sql"]
        assert "LIMIT 100" in sql

    def test_no_limit_when_none(self):
        domo = _make_domo()
        with patch.object(domo, "_post") as mock_post:
            mock_post.return_value = _mock_response(200, {"columns": [], "rows": []})
            domo.query_dataset("abc", limit=None)
        sql = mock_post.call_args.kwargs["json"]["sql"]
        assert "LIMIT" not in sql


# ---------------------------------------------------------------------------
# dataset_to_dataframe
# ---------------------------------------------------------------------------

class TestDatasetToDataframe:
    def test_returns_polars_dataframe(self):
        domo = _make_domo()
        import polars as pl
        payload = {"columns": ["Name", "Age"], "rows": [["Alice", 30], ["Bob", 25]]}
        with patch.object(domo, "query_dataset", return_value=payload):
            df = domo.dataset_to_dataframe("abc")
        assert isinstance(df, pl.DataFrame)
        assert df.shape == (2, 2)

    def test_empty_string_becomes_none(self):
        domo = _make_domo()
        import polars as pl
        payload = {"columns": ["Name"], "rows": [[""], ["Alice"]]}
        with patch.object(domo, "query_dataset", return_value=payload):
            df = domo.dataset_to_dataframe("abc")
        assert df["Name"][0] is None

    def test_column_renames_applied(self):
        domo = _make_domo()
        import polars as pl
        payload = {"columns": ["OldName"], "rows": [["val"]]}
        with patch.object(domo, "query_dataset", return_value=payload):
            df = domo.dataset_to_dataframe("abc", column_renames={"OldName": "NewName"})
        assert "NewName" in df.columns
        assert "OldName" not in df.columns


# ---------------------------------------------------------------------------
# dataset_to_csv_file / dataset_to_parquet_file
# ---------------------------------------------------------------------------

class TestDatasetToFile:
    def test_writes_csv_file(self, tmp_path):
        domo = _make_domo()
        import polars as pl
        df = pl.DataFrame({"Col": ["val"]})
        with patch.object(domo, "dataset_to_dataframe", return_value=df):
            out = tmp_path / "out.csv"
            domo.dataset_to_csv_file(path=out, dataset_id="abc")
        assert out.exists()
        assert b"Col" in out.read_bytes()

    def test_writes_parquet_file(self, tmp_path):
        domo = _make_domo()
        import polars as pl
        df = pl.DataFrame({"Col": ["val"]})
        with patch.object(domo, "dataset_to_dataframe", return_value=df):
            out = tmp_path / "out.parquet"
            domo.dataset_to_parquet_file(path=out, dataset_id="abc")
        assert out.exists()
        result = pl.read_parquet(out)
        assert "Col" in result.columns
