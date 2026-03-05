# Configuration

FluidKit is configured via a `fluidkit.config.json` file in your project root. This file is created automatically when you run `fluidkit init`.

## Default configuration

```json
{
  "entry": "src/app.py",
  "host": "0.0.0.0",
  "backend_port": 8000,
  "frontend_port": 5173,
  "schema_output": "src/lib/fluidkit",
  "watch_pattern": "src/**/*.py"
}
```

## Options

| Option | Type | Default | Description |
|---|---|---|---|
| `entry` | `string` | `"src/app.py"` | Path to your python app entry point |
| `host` | `string` | `"0.0.0.0"` | Host address for the backend server |
| `backend_port` | `int` | `8000` | Port for the python FastAPI backend |
| `frontend_port` | `int` | `5173` | Port for the Vite dev server |
| `schema_output` | `string` | `"src/lib/fluidkit"` | Directory where FluidKit writes its runtime TypeScript files |
| `watch_pattern` | `string` | `"src/**/*.py"` | Glob pattern for HMR file watching |

## Precedence

CLI flags → `fluidkit.config.json` → defaults.

For example, running `fluidkit dev --backend-port 9000` will use port `9000` regardless of what's in the config file.

## Schema output

The `schema_output` directory contains FluidKit's generated runtime TypeScript files. A `$fluidkit` alias is automatically added to your `svelte.config.js` pointing to this directory. If you change `schema_output`, the alias is updated on the next `fluidkit dev` or `fluidkit build`.
