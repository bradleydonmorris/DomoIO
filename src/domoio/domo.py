import duckdb
import httpx
import csv
import io
from typing import Self, Any, AsyncIterable, Iterable, Union
from pathlib import Path
from pydantic import SecretStr
import pandas as pd
import polars as pl


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
	_access_method: str | None = None
	_base_url: str | None = None
	_auth_header_name: SecretStr | None = None
	_auth_header_value: SecretStr | None = None

	def __init__(self,
		access_method: str | None = None,
		base_url: str | None = None,
		auth_header_name: SecretStr | None = None,
		auth_header_value: SecretStr | None = None
	) -> None:
		self._access_method = access_method
		self._base_url = base_url
		self._auth_header_name = auth_header_name
		self._auth_header_value = auth_header_value

	@classmethod
	def use_access_token(cls, client_id: SecretStr | str, client_secret: SecretStr | str) -> Self | None:
		if not client_id or not client_secret:
			raise ValueError("client_id and client_secret must be provided")
		if isinstance(client_id, SecretStr):
			client_id = client_id.get_secret_value()
		if isinstance(client_secret, SecretStr):
			client_secret = client_secret.get_secret_value()
		response: httpx.Response = httpx.get(
			"https://api.domo.com/oauth/token",
			params={"grant_type": "client_credentials", "scope": "data"},
			auth=(client_id, client_secret),
		)
		response.raise_for_status()
		if response:
			response_json = response.json()
			access_token = response_json.get("access_token", None)
			if not access_token:
				raise ValueError("Unable to authenticate")
			return cls(
				access_method="AccessToken",
				base_url="https://api.domo.com",
				auth_header_name=SecretStr(secret_value="Authorization"),
				auth_header_value=SecretStr(secret_value=f"Bearer {access_token}")
			)
		return None

	@classmethod
	def use_developer_token(cls, tenant: SecretStr | str, developer_token: SecretStr | str) -> Self | None:
		if not tenant or not developer_token:
			raise ValueError("tenant and developer_token must be provided")
		if isinstance(tenant, SecretStr):
			tenant = tenant.get_secret_value()
		if isinstance(developer_token, SecretStr):
			developer_token = developer_token.get_secret_value()
		print("HERE", f"https://{tenant}.domo.com")
		return cls(
			access_method="DeveloperToken",
			base_url=f"https://{tenant}.domo.com",
			auth_header_name=SecretStr(secret_value="X-DOMO-Developer-Token"),
			auth_header_value=SecretStr(secret_value=developer_token)
		)

	def _join_url(self, *segments: str) -> str:
		return "/".join([s.removeprefix("/").removesuffix("/") for s in segments])

	def _get(self,
			api_path: str,
			headers: dict | None = None,
			params: dict | None = None,
			content_type: str = "application/json",
			accepts: str = "application/json") -> httpx.Response:
		headers: dict = {} if not headers else headers
		if headers.get("Accept") != accepts:
			headers.update({ "Accept": accepts })
		if headers.get("Content-Type") != content_type:
			headers.update({ "Content-Type": content_type })
		if headers.get(self._auth_header_name.get_secret_value()) != self._auth_header_value.get_secret_value():
			headers.update({ self._auth_header_name.get_secret_value(): self._auth_header_value.get_secret_value() })
		return httpx.get(
			url=self._join_url(self._base_url, api_path),
			params=params,
			headers=headers
		)

	def _post(self,
			api_path: str,
			headers: dict | None = None,
			params: dict | None = None,
			content_type: str = "application/json",
			accepts: str = "application/json",
			content: Union[str, bytes, Iterable[bytes], AsyncIterable[bytes]] | None = None,
			json: Any | None = None) -> httpx.Response:
		headers: dict = {} if not headers else headers
		if headers.get("Accept") != accepts:
			headers.update({ "Accept": accepts })
		if headers.get("Content-Type") != content_type:
			headers.update({ "Content-Type": content_type })
		if headers.get(self._auth_header_name.get_secret_value()) != self._auth_header_value.get_secret_value():
			headers.update({ self._auth_header_name.get_secret_value(): self._auth_header_value.get_secret_value() })
		return httpx.post(
			url=self._join_url(self._base_url, api_path),
			params=params,
			headers=headers,
			content=content,
			json=json
		)

	def _put(self,
			api_path: str,
			headers: dict | None = None,
			params: dict | None = None,
			content_type: str = "application/json",
			accepts: str = "application/json",
			content: Union[str, bytes, Iterable[bytes], AsyncIterable[bytes]] | None = None,
			json: Any | None = None) -> httpx.Response:
		headers: dict = {} if not headers else headers
		if headers.get("Accept") != accepts:
			headers.update({ "Accept": accepts })
		if headers.get("Content-Type") != content_type:
			headers.update({ "Content-Type": content_type })
		if headers.get(self._auth_header_name.get_secret_value()) != self._auth_header_value.get_secret_value():
			headers.update({ self._auth_header_name.get_secret_value(): self._auth_header_value.get_secret_value() })
		return httpx.put(
			url=self._join_url(self._base_url, api_path),
			params=params,
			headers=headers,
			content=content,
			json=json
		)

	def _delete(self,
			api_path: str,
			headers: dict | None = None,
			params: dict | None = None,
			content_type: str = "application/json",
			accepts: str = "application/json") -> httpx.Response:
		headers: dict = {} if not headers else headers
		if headers.get("Accept") != accepts:
			headers.update({ "Accept": accepts })
		if headers.get("Content-Type") != content_type:
			headers.update({ "Content-Type": content_type })
		if headers.get(self._auth_header_name.get_secret_value()) != self._auth_header_value.get_secret_value():
			headers.update({ self._auth_header_name.get_secret_value(): self._auth_header_value.get_secret_value() })
		return httpx.delete(
			url=self._join_url(self._base_url, api_path),
			params=params,
			headers=headers
		)

	def _duckdb_type_to_domo_type(self, data_type: str) -> str:
		return self._duckdb_type_map.get(data_type.upper().split("(")[0].strip(), "STRING")

	def _parquet_to_csv_bytes(parquet_path: Path) -> bytes:
		data_frame: pd.DataFrame = duckdb.sql(f"SELECT * FROM read_parquet('{parquet_path}')").df()
		buffer = io.StringIO()
		data_frame.to_csv(buffer, index=False, quoting=csv.QUOTE_NONNUMERIC)
		return buffer.getvalue().encode("utf-8")

	def _delete_stream(self, stream_id: int) -> None:
		response = self._delete(api_path=f"/v1/streams/{stream_id}")
		response.raise_for_status()

	def _create_stream(self,
		dataset_id: str,
		update_method: str,
	) -> int:
		response: httpx.Response = self._post(
			api_path="/v1/streams",
			json={
				"dataSet": {"id": dataset_id},
				"updateMethod": update_method,
			})
		response.raise_for_status()
		stream_id: int = response.json()["id"]
		return stream_id

	def _get_or_create_stream(self,
		dataset_id: str,
		update_method: str,
	) -> int:
		response: httpx.Response = self._get(
			api_path="/v1/streams/search",
			params={"q": dataset_id, "fields": "all"},
		)
		response.raise_for_status()
		streams: list[dict] = response.json()
		for stream in streams:
			if stream.get("dataSet", {}).get("id") != dataset_id:
				continue
			stream_id: int = stream["id"]
			existing_method: str = stream.get("updateMethod", "")
			if existing_method == update_method:
				return stream_id
			self._delete_stream(stream_id=stream_id)
			return self._create_stream(dataset_id=dataset_id, update_method=update_method)

	def _create_execution(self, stream_id: int) -> int:
		response: httpx.Response = self._post(api_path=f"/v1/streams/{stream_id}/executions")
		response.raise_for_status()
		execution_id: int = response.json()["id"]
		return execution_id

	def _upload_part(self,
		stream_id: int,
		execution_id: int,
		part_number: int,
		csv_bytes: bytes,
	) -> None:
		response: httpx.Response = self._put(
			api_path=f"/v1/streams/{stream_id}/executions/{execution_id}/part/{part_number}",
			content_type="text/csv",
			content=csv_bytes
		)
		response.raise_for_status()

	def _commit_execution(self,
		stream_id: int,
		execution_id: int,
	) -> None:
		response: httpx.Response = httpx.put(api_path=f"/v1/streams/{stream_id}/executions/{execution_id}/commit")
		response.raise_for_status()

	def _abort_execution(self,
		stream_id: int,
		execution_id: int,
	) -> None:
		response: httpx.Response = httpx.put(api_path=f"/v1/streams/{stream_id}/executions/{execution_id}/abort")
		response.raise_for_status()

	def _run_stream_upsert(self,
		csv_bytes: bytes,
		dataset_id: str,
		chunk_size_mb: int = 50,
	) -> None:
		if not self.dataset_exists(dataset_id=dataset_id):
			raise ValueError("Data Set does not exist")
		chunk_size = chunk_size_mb * 1024 * 1024
		stream_id = self._get_or_create_stream(dataset_id, "UPSERT")
		execution_id = self._create_execution(stream_id)
		try:
			parts = [
				csv_bytes[i : i + chunk_size]
				for i in range(0, len(csv_bytes), chunk_size)
			]
			for part_number, part in enumerate(parts, start=1):
				self._upload_part(stream_id, execution_id, part_number, part)
			self._commit_execution(stream_id, execution_id)
		except Exception:
			self._abort_execution(stream_id, execution_id)
			raise

	def _run_stream_replace(self,
		csv_bytes: bytes,
		dataset_id: str,
		chunk_size_mb: int = 50,
	) -> None:
		if not self.dataset_exists(dataset_id=dataset_id):
			raise ValueError("Data Set does not exist")
		chunk_size = chunk_size_mb * 1024 * 1024
		stream_id = self._get_or_create_stream(dataset_id, "REPLACE")
		execution_id = self._create_execution(stream_id)
		try:
			parts = [
				csv_bytes[i : i + chunk_size]
				for i in range(0, len(csv_bytes), chunk_size)
			]
			for part_number, part in enumerate(parts, start=1):
				self._upload_part(stream_id, execution_id, part_number, part)
			self._commit_execution(stream_id, execution_id)
		except Exception:
			self._abort_execution(stream_id, execution_id)
			raise


	def get_datasets(self,
		name_filter: str | None = None,
		order_by: str = "name",
		cutoff: int | None = None
	) -> list[dict]:
		datasets: list[dict] = []
		limit = cutoff if cutoff is not None and cutoff <= 50 else 50
		offset = 0
		params: dict = {
			"limit": limit,
			"offset": offset,
			"orderBy": order_by,
			"fields": "id,name,rowCount,columnCount,owner,createdAt,updatedAt,type",
		}
		if name_filter:
			params["namePart"] = name_filter
		while True:
			params["offset"] = offset
			response = self._get(api_path="api/data/v3/datasources", params=params)
			response.raise_for_status()
			page = response.json().get("dataSources", [])
			if not page:
				break
			if name_filter is not None:
				datasets.extend([item for item in page if name_filter in item["name"]])
			else:
				datasets.extend([item for item in page])
			offset += len(page)
			if len(page) < limit:
				break
			if cutoff is not None and offset >= cutoff:
				break
		return datasets

	def get_columns_from_parquet(self, parquet_path: Path) -> list[dict[str, str]]:
		return [
			{"name": row[0], "type": self._duckdb_type_to_domo_type(row[1])}
			for row in duckdb.sql(f"DESCRIBE SELECT * FROM read_parquet('{parquet_path}')").fetchall()
		]

	def get_columns_from_dataset(self, dataset_id: str) -> list[dict[str, str]]:
		response: httpx.Response = self._get(api_path=f"/v1/datasets/{dataset_id}")
		response.raise_for_status()
		return [
			{"name": col["name"], "type": col["type"]}
			for col in response.json()["schema"]["columns"]
		]

	def get_dataset_id_by_name(self,
		dataset_name: str,
		exact_match: bool = True) -> str | None:
		response: httpx.Response = self._get(
			api_path="/v1/datasets",
			params={
				"namePart": dataset_name,
				"fields": "id,name",
				"limit": 50,
				"offset": 0,
			}
		)
		response.raise_for_status()
		datasets: list[dict] = response.json()
		if not exact_match:
			return datasets[0]["id"] if datasets else None
		matches = [ds for ds in datasets if ds["name"] == dataset_name]
		match len(matches):
			case 0:
				return None
			case 1:
				return matches[0]["id"]
			case _:
				ids = [ds["id"] for ds in matches]
				raise ValueError(
					f"Found {len(matches)} datasets named '{dataset_name}': {ids}"
				)

	def dataset_exists(self,
		dataset_id: str | None = None,
		dataset_name: str | None = None,
	) -> bool:
		exists: bool = False
		match (dataset_id, dataset_name):
			case (None, None) | (_, _) if dataset_id and dataset_name:
				raise ValueError("Provide exactly one of dataset_id or dataset_name.")
			case (str(), None):
				response: httpx.Response = self._get(api_path=f"/v1/datasets/{dataset_id}")
				exists = response.status_code == 200
			case (None, str()):
				exists = self.get_dataset_id_by_name(dataset_name) is not None
		return exists

	def create_dataset(self,
		dataset_name: str,
		dataset_description: str | None,
		columns: list[dict[str, str]],
	) -> str:
		if self.dataset_exists(dataset_name=dataset_name):
			raise ValueError("Data Set already exists")
		response: httpx.Response = self._post(
			api_path="/v1/datasets",
			json={
				"name": dataset_name,
				"description": dataset_description or "",
				"schema": {
					"columns": columns,
				},
			}
		)
		response.raise_for_status()
		dataset_id: str = response.json()["id"]
		return dataset_id

	def delete_dataset(self, dataset_id: str) -> None:
		if not self.dataset_exists(dataset_id=dataset_id):
			raise ValueError("Data Set does not exist")
		response = self._delete(api_path=f"/v1/datasets/{dataset_id}")
		if response.status_code == 404:
			return False
		response.raise_for_status()
		return True		

	def truncate_dataset(self,
		dataset_id: str,
		chunk_size_mb: int = 50) -> None:
		if not self.dataset_exists(dataset_id=dataset_id):
			raise ValueError("Data Set does not exist")
		columns = self.get_columns_from_dataset(dataset_id=dataset_id)
		csv_bytes = ",".join(col["name"] for col in columns).encode("utf-8")
		self._run_stream_replace(csv_bytes=csv_bytes, dataset_id=dataset_id, chunk_size_mb=chunk_size_mb)

	def upsert_parquet(self,
		parquet_path: Path,
		dataset_id: str,
		chunk_size_mb: int = 50,
	) -> None:
		self._run_stream_upsert(csv_bytes=self._parquet_to_csv_bytes(parquet_path), dataset_id=dataset_id, chunk_size_mb=chunk_size_mb)

	def upsert_csv(self,
		csv_path: Path,
		dataset_id: str,
		chunk_size_mb: int = 50,
	) -> None:
		self._run_stream_upsert(csv_bytes=csv_path.read_bytes(), dataset_id=dataset_id, chunk_size_mb=chunk_size_mb)

	def upsert_polars(self,
		data_frame: pl.DataFrame,
		dataset_id: str,
		chunk_size_mb: int = 50
	) -> None:
		buffer = io.BytesIO()
		data_frame.write_csv(buffer)
		self._run_stream_upsert(csv_bytes=buffer.getvalue(), dataset_id=dataset_id, chunk_size_mb=chunk_size_mb)

	def replace_parquet(self,
		parquet_path: Path,
		dataset_id: str,
		chunk_size_mb: int = 50,
	) -> None:
		self._run_stream_replace(csv_bytes=self._parquet_to_csv_bytes(parquet_path), dataset_id=dataset_id, chunk_size_mb=chunk_size_mb)

	def replace_csv(self,
		csv_path: Path,
		dataset_id: str,
		chunk_size_mb: int = 50,
	) -> None:
		self._run_stream_replace(csv_bytes=csv_path.read_bytes(), dataset_id=dataset_id, chunk_size_mb=chunk_size_mb)

	def replace_polars(self,
		data_frame: pl.DataFrame,
		dataset_id: str,
		chunk_size_mb: int = 50
	) -> None:
		buffer = io.BytesIO()
		data_frame.write_csv(buffer)
		self._run_stream_replace(csv_bytes=buffer.getvalue(), dataset_id=dataset_id, chunk_size_mb=chunk_size_mb)
