import duckdb
import httpx
import csv
import io
from datetime import datetime
from typing import Any, AsyncIterable, Iterable, Union, Literal
from pathlib import Path
import pandas as pd
import polars as pl
import logging

type AccessMethod = Literal["access_token", "developer_token"]
type UpdateMethod = Literal["APPEND", "REPLACE"] #, "UPSERT"]
type ParquetCompression = Literal["lz4", "uncompressed", "snappy", "gzip", "brotli", "zstd"]

logger = logging.getLogger(__name__)
logger.addHandler(logging.NullHandler())

class SecretStr:
	_secret_value: str | None

	def __init__(self, secret_value: str | None = None):
		self._secret_value = secret_value
	
	def __str__(self) -> str:
		return "*********"
	
	def __repr__(self) -> str:
		return "*********"

	def __bool__(self):
		return self._secret_value is not None

	def get_secret_value(self) -> str:
		return self._secret_value

class Domo:
	_duckdb_type_map: dict[str, str] = {
		"VARCHAR":		"STRING",
		"TEXT":			"STRING",
		"BLOB":			"STRING",
		"BOOLEAN":		"STRING",
		"BOOL":			"STRING",
		"TINYINT":		"LONG",
		"SMALLINT":		"LONG",
		"INTEGER":		"LONG",
		"INT":			"LONG",
		"BIGINT":		"LONG",
		"HUGEINT":		"LONG",
		"UBIGINT":		"LONG",
		"FLOAT":		"DOUBLE",
		"REAL":			"DOUBLE",
		"DOUBLE":		"DOUBLE",
		"DECIMAL":		"DECIMAL",
		"NUMERIC":		"DECIMAL",
		"DATE":			"DATE",
		"TIMESTAMP":	"DATETIME",
		"TIMESTAMP WITH TIME ZONE": "DATETIME",
	}
	_tenant: SecretStr | None = None
	_client_id: SecretStr | None = None
	_client_secret: SecretStr | None = None
	_developer_token: SecretStr | None = None
	_access_token: SecretStr | None = None


	_access_method: str | None = None
	_base_url: str | None = None
	_auth_header_name: SecretStr | None = None
	_auth_header_value: SecretStr | None = None

	def __init__(self,
		tenant: SecretStr | str,
		developer_token: SecretStr | str,
		client_id: SecretStr | str,
		client_secret: SecretStr | str
	) -> None:
		if not tenant or not developer_token or not client_id or not client_secret:
			raise ValueError("All arguments are required")
		self._tenant = tenant if isinstance(tenant, SecretStr) else SecretStr(secret_value=tenant)
		self._developer_token = developer_token if isinstance(developer_token, SecretStr) else SecretStr(secret_value=developer_token)
		self._client_id = client_id if isinstance(client_id, SecretStr) else SecretStr(secret_value=client_id)
		self._client_secret = client_secret if isinstance(client_secret, SecretStr) else SecretStr(secret_value=client_secret)
		self._get_access_token()

	def _get_access_token(self) -> None:
		logger.debug("Requesting OAuth access token")
		response: httpx.Response = httpx.get(
			"https://api.domo.com/oauth/token",
			params={"grant_type": "client_credentials", "scope": "data"},
			auth=(self._client_id.get_secret_value(), self._client_secret.get_secret_value()),
		)
		self._raise_for_status(response=response, log_message="Failed to obtain access token", reraise=True)
		if response:
			response_json = response.json()
			access_token = response_json.get("access_token", None)
			if not access_token:
				logger.error("Authentication response did not contain an access token")
				raise ValueError("Unable to authenticate")
			self._access_token = SecretStr(secret_value=access_token)
			logger.debug("Access token acquired")

	def _get_headers(self,
			access_method: AccessMethod,
			headers: dict,
			content_type: str = "application/json",
			accepts: str = "application/json") -> dict:
		headers: dict = {} if not headers else headers
		if headers.get("Accept") != accepts:
			headers.update({ "Accept": accepts })
		if headers.get("Content-Type") != content_type:
			headers.update({ "Content-Type": content_type })
		match access_method:
			case "access_token":
				value: str = f"Bearer {self._access_token.get_secret_value()}"
				if headers.get("Authorization") != value:
					headers.update({ "Authorization": value })
			case "developer_token":
				value: str = self._developer_token.get_secret_value()
				if headers.get("X-DOMO-Developer-Token") != value:
					headers.update({ "X-DOMO-Developer-Token": value })
		return headers

	def _get_url(self,
			access_method: AccessMethod,
			*segments: str) -> str:
		base_url: str = "https://api.domo.com"
		match access_method:
			case "access_token":
				base_url = "https://api.domo.com"
			case "developer_token":
				base_url = f"https://{self._tenant.get_secret_value()}.domo.com"
		return base_url + "/" + "/".join([s.removeprefix("/").removesuffix("/") for s in segments])

	def _raise_for_status(self, response: httpx.Response, log_message: str | None = None, reraise: bool = True) -> None:
		try:
			response.raise_for_status()
		except httpx.HTTPStatusError as exc:
			error_response = exc.response
			status_reason: str | None = None
			if not log_message:
				try:
					status_reason = error_response.json().get("statusReason")
				except Exception:
					status_reason = None
				log_message = f"Status Code: {error_response.status_code}, Status Reason: {status_reason}"
			else:
				if "$(status_code)" not in log_message and "$(status_reason)" not in log_message:
					log_message += f" (Status Code: {error_response.status_code}, Status Reason: {status_reason})"
				elif "$(status_code)" in log_message and "$(status_reason)" not in log_message:
					log_message = log_message.replace("$(status_code)", str(error_response.status_code))
					log_message += f" (Status Reason: {status_reason})"
				elif "$(status_code)" not in log_message and "$(status_reason)" in log_message:
					log_message = log_message.replace("$(status_reason)", status_reason)
					log_message += f" (Status Code: {error_response.status_code})"
			logger.exception(log_message)
			if reraise:
				raise

	def _get(self,
			access_method: AccessMethod,
			api_path: str,
			headers: dict | None = None,
			params: dict | None = None,
			content_type: str = "application/json",
			accepts: str = "application/json") -> httpx.Response:
		return httpx.get(
			url=self._get_url(access_method, api_path),
			params=params,
			headers=self._get_headers(access_method=access_method, headers=headers, content_type=content_type, accepts=accepts)
		)

	def _post(self,
			access_method: AccessMethod,
			api_path: str,
			headers: dict | None = None,
			params: dict | None = None,
			content_type: str = "application/json",
			accepts: str = "application/json",
			content: Union[str, bytes, Iterable[bytes], AsyncIterable[bytes]] | None = None,
			json: Any | None = None) -> httpx.Response:
		headers: dict = {} if not headers else headers
		return httpx.post(
			url=self._get_url(access_method, api_path),
			params=params,
			headers=self._get_headers(access_method=access_method, headers=headers, content_type=content_type, accepts=accepts),
			content=content,
			json=json
		)

	def _put(self,
			access_method: AccessMethod,
			api_path: str,
			headers: dict | None = None,
			params: dict | None = None,
			content_type: str = "application/json",
			accepts: str = "application/json",
			content: Union[str, bytes, Iterable[bytes], AsyncIterable[bytes]] | None = None,
			json: Any | None = None) -> httpx.Response:
		return httpx.put(
			url=self._get_url(access_method, api_path),
			params=params,
			headers=self._get_headers(access_method=access_method, headers=headers, content_type=content_type, accepts=accepts),
			content=content,
			json=json
		)

	def _delete(self,
			access_method: AccessMethod,
			api_path: str,
			headers: dict | None = None,
			params: dict | None = None,
			content_type: str = "application/json",
			accepts: str = "application/json") -> httpx.Response:
		return httpx.delete(
			url=self._get_url(access_method, api_path),
			params=params,
			headers=self._get_headers(access_method=access_method, headers=headers, content_type=content_type, accepts=accepts)
		)

	def _duckdb_type_to_domo_type(self, data_type: str) -> str:
		return self._duckdb_type_map.get(data_type.upper().split("(")[0].strip(), "STRING")

	def _parquet_to_csv_bytes(self, parquet_path: Path) -> bytes:
		data_frame: pd.DataFrame = duckdb.sql(f"SELECT * FROM read_parquet('{parquet_path}')").df()
		buffer = io.StringIO()
		data_frame.to_csv(buffer, index=False, quoting=csv.QUOTE_NONNUMERIC)
		return buffer.getvalue().encode("utf-8")

	def get_datasets(self,
		name_like: str,
		limit: int = 50,
		sort: Literal["name", "nameDescending", "lastTouched", "lastTouchedAscending", "lastUpdated", "lastUpdatedAscending", "createdAt", "createdAtAscending", "cardCount", "cardCountAscending", "cardViewCount", "cardViewCountAscending", "errorState", "errorStateDescending", "dataSourceId"] = "name"
		) -> list[dict]:
		datasets: list[dict] = []
		limit = limit if limit is not None and limit <= 50 else 50
		offset = 0
		params: dict = {
			"limit": limit,
			"offset": offset,
			"sort": sort,
			"nameLike": name_like
		}
		logger.debug("Listing datasets (nameLike=%r, sort=%s, limit=%d)", name_like, sort, limit)
		response = self._get(access_method="access_token", api_path="v1/datasets", params=params)
		self._raise_for_status(response=response, log_message="Failed to list datasets", reraise=True)
		response_json: list = response.json()
		if isinstance(response_json, list):
			datasets.extend(response_json)
		logger.debug("Found %d dataset(s) matching %r", len(datasets), name_like)
		return datasets

	def get_columns_from_csv(self, csv_path: Path) -> list[dict[str, str]]:
		return [
			{"name": row[0], "type": self._duckdb_type_to_domo_type(row[1])}
			for row in duckdb.sql(f"DESCRIBE SELECT * FROM read_csv('{csv_path}')").fetchall()
		]

	def get_columns_from_parquet(self, parquet_path: Path) -> list[dict[str, str]]:
		return [
			{"name": row[0], "type": self._duckdb_type_to_domo_type(row[1])}
			for row in duckdb.sql(f"DESCRIBE SELECT * FROM read_parquet('{parquet_path}')").fetchall()
		]

	def get_columns_from_dataset(self, dataset_id: str) -> list[dict[str, str]]:
		logger.debug("Getting columns for dataset %s", dataset_id)
		response: httpx.Response = self._get(access_method="access_token", api_path=f"/v1/datasets/{dataset_id}")
		self._raise_for_status(response=response, log_message=f"Failed to get columns for dataset {dataset_id}", reraise=True)
		return [
			{"name": col["name"], "type": col["type"]}
			for col in response.json()["schema"]["columns"]
		]

	def get_dataset_id_by_name(self,
		dataset_name: str,
		exact_match: bool = True) -> str | None:
		logger.debug("Looking up dataset id by name %r (exact_match=%s)", dataset_name, exact_match)
		datasets: list[dict] = self.get_datasets(name_like=dataset_name)
		if not exact_match:
			dataset_id = datasets[0]["id"] if datasets else None
			logger.debug("Resolved dataset %r to id %s", dataset_name, dataset_id)
			return dataset_id
		matches = [ds for ds in datasets if ds["name"] == dataset_name]
		match len(matches):
			case 0:
				logger.debug("No dataset found with name %r", dataset_name)
				return None
			case 1:
				logger.debug("Resolved dataset %r to id %s", dataset_name, matches[0]["id"])
				return matches[0]["id"]
			case _:
				ids = [ds["id"] for ds in matches]
				logger.error("Found %d datasets named %r: %s", len(matches), dataset_name, ids)
				raise ValueError(
					f"Found {len(matches)} datasets named '{dataset_name}': {ids}"
				)
		return None

	def dataset_exists(self,
		dataset_id: str | None = None,
		dataset_name: str | None = None,
	) -> bool:
		exists: bool = False
		if (dataset_id is None) == (dataset_name is None):
			raise ValueError("Provide exactly one of dataset_id or dataset_name.")
		match (dataset_id, dataset_name):
			case (str(), None):
				response: httpx.Response = self._get(access_method="access_token", api_path=f"/v1/datasets/{dataset_id}")
				exists = response.status_code == 200
			case (None, str()):
				exists = self.get_dataset_id_by_name(dataset_name) is not None
		logger.debug("Dataset exists check (id=%s, name=%s) -> %s", dataset_id, dataset_name, exists)
		return exists

	def create_dataset(self,
		dataset_name: str,
		dataset_description: str | None,
		columns: list[dict[str, str]],
	) -> str:
		logger.info("Creating dataset %r (%d column(s))", dataset_name, len(columns))
		response: httpx.Response = self._post(
			access_method="access_token",
			api_path="v1/datasets",
			json={
				"name": dataset_name,
				"description": dataset_description or "",
				"schema": {
					"columns": columns,
				},
			}
		)
		self._raise_for_status(response=response, log_message=f"Failed to create dataset {dataset_name!r}", reraise=True)
		dataset_id: str = response.json()["id"]
		logger.info("Created dataset %r with id %s", dataset_name, dataset_id)
		return dataset_id

	def import_data(self, dataset_id: str, update_method: UpdateMethod, csv_bytes: bytes) -> bool:
		logger.info("Importing data into dataset %s (update_method=%s, %d byte(s))", dataset_id, update_method, len(csv_bytes))
		success: bool = False
		response: httpx.Response = self._put(
			access_method="access_token",
			api_path=f"v1/datasets/{dataset_id}/data",
			params={"updateMethod": update_method},
			content_type="text/csv",
			content=csv_bytes
		)
		self._raise_for_status(response=response, log_message=f"Failed to import data into dataset {dataset_id}", reraise=True)
		if response.status_code == 204:
			success = True
		else:
			success = False
		logger.debug("Import data into dataset %s -> success=%s", dataset_id, success)
		return success

	def delete_dataset(self, dataset_id: str) -> None:
		logger.info("Deleting dataset %s", dataset_id)
		response = self._delete(access_method="access_token", api_path=f"/v1/datasets/{dataset_id}")
		if response.status_code == 404:
			logger.warning("Dataset %s not found, nothing to delete", dataset_id)
			return False
		self._raise_for_status(response=response, log_message=f"Failed to delete dataset {dataset_id}", reraise=True)
		logger.info("Deleted dataset %s", dataset_id)
		return True

	def truncate_dataset(self, dataset_id: str) -> None:
		logger.info("Truncating dataset %s", dataset_id)
		columns = self.get_columns_from_dataset(dataset_id=dataset_id)
		csv_bytes = ",".join(col["name"] for col in columns).encode("utf-8")
		self.import_data(
			dataset_id=dataset_id,
			update_method="REPLACE",
			csv_bytes=csv_bytes)

	def replace_parquet(self,
		dataset_id: str,
		parquet_path: Path
	) -> None:
		logger.info("Replacing dataset %s from parquet file %s", dataset_id, parquet_path)
		self.import_data(
			dataset_id=dataset_id,
			update_method="REPLACE",
			csv_bytes=self._parquet_to_csv_bytes(parquet_path)
		)

	def replace_csv(self,
		dataset_id: str,
		csv_path: Path
	) -> None:
		logger.info("Replacing dataset %s from CSV file %s", dataset_id, csv_path)
		self.import_data(
			dataset_id=dataset_id,
			update_method="REPLACE",
			csv_bytes=csv_path.read_bytes()
		)

	def replace_polars(self,
		dataset_id: str,
		data_frame: pl.DataFrame
	) -> None:
		logger.info("Replacing dataset %s from DataFrame (%d row(s))", dataset_id, data_frame.height)
		buffer = io.BytesIO()
		data_frame.write_csv(buffer)
		self.import_data(
			dataset_id=dataset_id,
			update_method="REPLACE",
			csv_bytes=buffer.getvalue()
		)

	def append_parquet(self,
		dataset_id: str,
		parquet_path: Path
	) -> None:
		logger.info("Appending to dataset %s from parquet file %s", dataset_id, parquet_path)
		self.import_data(
			dataset_id=dataset_id,
			update_method="APPEND",
			csv_bytes=self._parquet_to_csv_bytes(parquet_path)
		)

	def append_csv(self,
		dataset_id: str,
		csv_path: Path
	) -> None:
		logger.info("Appending to dataset %s from CSV file %s", dataset_id, csv_path)
		self.import_data(
			dataset_id=dataset_id,
			update_method="APPEND",
			csv_bytes=csv_path.read_bytes()
		)

	def append_polars(self,
		dataset_id: str,
		data_frame: pl.DataFrame
	) -> None:
		logger.info("Appending to dataset %s from DataFrame (%d row(s))", dataset_id, data_frame.height)
		buffer = io.BytesIO()
		data_frame.write_csv(buffer)
		self.import_data(
			dataset_id=dataset_id,
			update_method="APPEND",
			csv_bytes=buffer.getvalue()
		)

	def query_dataset_row_count(self, dataset_id: str, filter: dict[str, Any] = {}) -> int:
		logger.info("Querying row count for dataset %s", dataset_id)
		sql: str = "SELECT COUNT(*) AS \"Count\" FROM `{}`{} LIMIT 1".format(
			dataset_id,
			"" if not filter else " WHERE {}".format(
				" AND ".join(
					[(f"`{k}` = '{v}'" if isinstance(v, (str, datetime))
						else f"`{k}` IS NULL" if v is None
							else f"`{k}` = {v}"
					) for k, v in filter.items()]
				)
			)
		)
		logger.debug("SQL: %s", sql)
		response = self._post(
			access_method="access_token",
			api_path=f"/v1/datasets/query/execute/{dataset_id}",
			params=None,
			json={"sql": sql})
		self._raise_for_status(response=response, log_message=f"Failed to query dataset {dataset_id}", reraise=True)
		result: list = response.json().get("rows", [])
		if len(result) == 1 and len(result[0]) == 1:
			return result[0][0]
		return 0

	def query_dataset(self, dataset_id: str, columns: list[str] = ["*"], filter: dict[str, Any] = {}, limit: int | None = None) -> dict:
		logger.info("Querying dataset %s", dataset_id)
		column_list: str = "*"
		if columns and columns[0] != "*":
			column_list = ", ".join([f"`{c}`" for c in columns])
		sql: str = "SELECT {} FROM `{}`{}{}".format(
			column_list,
			dataset_id,
			"" if not filter else " WHERE {}".format(
				" AND ".join(
					[(f"`{k}` = '{v}'" if isinstance(v, (str, datetime))
						else f"`{k}` IS NULL" if v is None
							else f"`{k}` = {v}"
					) for k, v in filter.items()]
				)
			),
			"" if limit is None else f" LIMIT {limit}"
		)
		response = self._post(
			access_method="access_token",
			api_path=f"/v1/datasets/query/execute/{dataset_id}",
			params=None,
			json={"sql": sql})
		self._raise_for_status(response=response, log_message=f"Failed to query dataset {dataset_id}", reraise=True)
		response_json: dict = response.json()
		logger.debug("Dataset %s returned %d row(s)", dataset_id, len(response_json.get("rows", [])))
		return response_json

	def dataset_to_dataframe(self,
							dataset_id: str,
							filter: dict[str, Any] = {},
							limit: int | None = None,
							columns: list[str] = ["*"],
							column_renames: dict[str, str] | None = None) -> pl.DataFrame:
		result: dict = self.query_dataset(dataset_id=dataset_id, columns=columns, filter=filter, limit=limit)
		rows = [[None if v == "" else v for v in row] for row in result["rows"]]
		logger.debug("Building dataframe: %d row(s), %d column(s)", len(rows), len(result.get("columns", [])))
		data_frame: pl.DataFrame = pl.DataFrame(
			data=rows,
			schema=result["columns"],
			orient="row",
		)
		if column_renames:
			for key, value in column_renames.items():
				if key in data_frame.columns:
					data_frame = data_frame.rename({key: value})
		return data_frame

	def dataset_to_csv_file(self,
							path: Path,
							dataset_id: str,
							filter: dict[str, Any] = {},
							limit: int | None = None,
							columns: list[str] = ["*"],
							column_renames: dict[str, str] | None = None,
							include_header: bool = True,
							separator: str = ",",
							line_terminator: str = '\n',
							quote_char: str = '"') -> None:
		logger.info("Writing CSV: %s", path)
		self.dataset_to_dataframe(
			dataset_id=dataset_id,
			filter=filter,
			limit=limit,
			columns=columns,
			column_renames=column_renames
			).write_csv(
				file=path,
				include_header=include_header,
				separator=separator,
				line_terminator=line_terminator,
				quote_char=quote_char)

	def dataset_to_parquet_file(self,
							path: Path,
							dataset_id: str,
							filter: dict[str, Any] = {},
							limit: int | None = None,
							columns: list[str] = ["*"],
							column_renames: dict[str, str] | None = None,
							compression: ParquetCompression = "zstd") -> None:
		logger.info("Writing Parquet: %s", path)
		self.dataset_to_dataframe(
			dataset_id=dataset_id,
			filter=filter,
			limit=limit,
			columns=columns,
			column_renames=column_renames
			).write_parquet(
				file=path,
				compression=compression)

	def get_dataset_details_url(self, dataset_id: str) -> str:
		return f"https://{self._tenant.get_secret_value()}.domo.com/datasources/{dataset_id}/details/"