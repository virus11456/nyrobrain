# Datasources

This folder contains endpoint schemas for all available data providers. Each file is named `{PROVIDER}_endpoints.json` and contains a JSON array of available endpoints.

## Topic Format

To subscribe to a datasource in ADRS, you must form a **topic** string:

```
{PROVIDER}|{ENDPOINT}?{PARAMETERS}
```

- **PROVIDER** — The filename prefix (e.g., `flow_endpoints.json` → `flow`).
- **ENDPOINT** — The `path` value from the endpoint object (strip the leading `/` if present).
- **PARAMETERS** — Query string built from the `parameters` object. Each key becomes a query parameter joined with `&`.

### Examples

From `flow_endpoints.json`:

```
flow|options/gamma-exposure?exchange=deribit&currency=BTC&interval=1h
flow|options/binance-volatility-index?currency=BTC&interval=1h
```

From `amberdata_endpoints.json`:

```
amberdata|derivatives/analytics/instruments/most-traded?exchange=deribit&currency=BTC&timeInterval=hour
```

From `okx_endpoints.json`:

```
okx|candle?interval=1h&symbol=BTC-USDT
```

From `cybotrade_endpoints.json` (no parameters):

```
cybotrade|data-alert
```

## Parameter Types

Parameters come in two forms:

### Enumerated values

The parameter is an array of allowed values. Pick one per query.

```json
"exchange": ["deribit", "okex", "bybit"]
```

### Free-form values

The parameter is an object with `type` and `required` fields. You must supply an appropriate value.

```json
"product": { "type": "string", "required": true }
```

## How to Choose Parameters

1. Open the `{PROVIDER}_endpoints.json` file for the provider you need.
2. Find the endpoint whose `path` matches the data you want.
3. For each key in `parameters`:
   - If the value is an **array**, pick one of the listed values.
   - If the value is an **object** with `type`, supply a value of that type (e.g., a trading pair symbol).
4. If `parameters` is empty (`{}`), the topic has no query string — use `{PROVIDER}|{ENDPOINT}` with no `?`.
5. Assemble the topic: `{PROVIDER}|{path}?{key1}={value1}&{key2}={value2}`.
