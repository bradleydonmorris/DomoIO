# DomoIO

A Python library for interacting with the [Domo](https://www.domo.com) API. Supports uploading, replacing, appending, querying, and exporting datasets using either OAuth client credentials or a developer token.

## Requirements

- Python >= 3.14
- A Domo instance (tenant)
- A Domo developer token ([generate one here](https://developer.domo.com/portal/1845fc11bbe5d-api-authentication))
- A Domo OAuth client ID and secret ([create one here](https://developer.domo.com/portal/1845fc11bbe5d-api-authentication)) with the `data` scope

## Installation

```bash
uv pip install -e .
```

## Authentication

`Domo` requires all four credentials at construction time. Operations that read or search datasets use the developer token against your instance domain. Operations that write data (create, import, delete) use the OAuth access token against `api.domo.com`.

```python
from domoio.domo import Domo

domo = Domo(
    tenant="your-tenant",
    developer_token="your-developer-token",
    client_id="your-client-id",
    client_secret="your-client-secret",
)
```

### Using a `.env` file

```dotenv
DOMO_TENANT=your-tenant
DOMO_DEV_TOKEN=your-developer-token
DOMO_CLIENT_ID=your-client-id
DOMO_CLIENT_SECRET=your-client-secret
```

```python
import os
from dotenv import load_dotenv
from domoio.domo import Domo

load_dotenv()

domo = Domo(
    tenant=os.getenv("DOMO_TENANT"),
    developer_token=os.getenv("DOMO_DEV_TOKEN"),
    client_id=os.getenv("DOMO_CLIENT_ID"),
    client_secret=os.getenv("DOMO_CLIENT_SECRET"),
)
```

## Usage

### Look up a dataset

```python
# Find a dataset ID by name (exact match)
dataset_id = domo.get_dataset_id_by_name("My Dataset")

# Find the first dataset whose name contains the search string
dataset_id = domo.get_dataset_id_by_name("My Dataset", exact_match=False)

# Check whether a dataset exists
exists = domo.dataset_exists(dataset_name="My Dataset")
exists = domo.dataset_exists(dataset_id="abc123")

# List datasets matching a name pattern
datasets = domo.get_datasets(name_like="Sales")

# Get column definitions from an existing dataset
columns = domo.get_columns_from_dataset(dataset_id)

# Get the Domo UI details URL for a dataset
url = domo.get_dataset_details_url(dataset_id)
```

### Create a dataset

```python
from pathlib import Path

columns = domo.get_columns_from_parquet(Path("data.parquet"))
# or: domo.get_columns_from_csv(Path("data.csv"))

dataset_id = domo.create_dataset(
    dataset_name="My Dataset",
    dataset_description="Created via DomoIO",
    columns=columns,
)
```

### Import data

#### Replace (full overwrite)

```python
domo.replace_parquet(dataset_id, Path("data.parquet"))
domo.replace_csv(dataset_id, Path("data.csv"))
domo.replace_polars(dataset_id, df)   # df is a polars.DataFrame
```

#### Append

```python
domo.append_parquet(dataset_id, Path("data.parquet"))
domo.append_csv(dataset_id, Path("data.csv"))
domo.append_polars(dataset_id, df)
```

#### Truncate

```python
domo.truncate_dataset(dataset_id)
```

### Query a dataset

```python
# Get raw query result dict
result = domo.query_dataset(
    dataset_id,
    columns=["OrderID", "Amount", "Status"],
    filter={"Status": "Shipped"},
    limit=1000,
)

# Get row count (with optional filter)
count = domo.query_dataset_row_count(dataset_id, filter={"Status": "Shipped"})
```

### Export a dataset

```python
# To a Polars DataFrame
df = domo.dataset_to_dataframe(
    dataset_id,
    columns=["OrderID", "Amount"],
    filter={"Status": "Shipped"},
    limit=5000,
    column_renames={"OrderID": "order_id", "Amount": "amount"},
)

# To a CSV file
domo.dataset_to_csv_file(
    path=Path("output.csv"),
    dataset_id=dataset_id,
    filter={"Status": "Shipped"},
)

# To a Parquet file
domo.dataset_to_parquet_file(
    path=Path("output.parquet"),
    dataset_id=dataset_id,
    compression="zstd",  # lz4 | uncompressed | snappy | gzip | brotli | zstd
)
```

### Delete a dataset

```python
deleted = domo.delete_dataset(dataset_id)
```

## Logging

DomoIO uses a standard `logging.getLogger(__name__)` logger under the `domoio.domo` name with a `NullHandler` by default. Configure it in your application to see output:

```python
import logging
logging.basicConfig(level=logging.DEBUG)
```

Key log levels used:
- `DEBUG` — API calls, dataset lookups, row counts
- `INFO` — create, import, replace, append, delete, export operations
- `WARNING` — non-fatal conditions (e.g. deleting a dataset that does not exist)
- `ERROR` — authentication failures, duplicate dataset names
