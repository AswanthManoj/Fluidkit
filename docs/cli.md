# CLI

FluidKit provides a single CLI entry point for scaffolding, development, building, and managing Node.js tooling — all without requiring a system Node.js installation.

## init

```bash
fluidkit init              # scaffold in current directory
fluidkit init my-app       # create folder and scaffold inside it
```

Creates a new SvelteKit project with FluidKit wired in. This runs `sv create` under the hood, installs dependencies, copies template files, and patches `svelte.config.js` and `vite.config.ts` with the required settings.

The scaffolded project includes a working demo app you can run immediately with `fluidkit dev`.

## dev

```bash
fluidkit dev
```

Starts the FastAPI backend and Vite dev server together. Python changes are picked up instantly via hot module reloading, and generated `.remote.ts` files update automatically on save.

| Flag | Description |
|---|---|
| `--host TEXT` | Override bind address (default: `0.0.0.0`) |
| `--backend-port INT` | Override backend port (default: `8000`) |
| `--frontend-port INT` | Override frontend port (default: `5173`) |
| `--no-hmr` | Disable hot module reloading, restart on change instead |

## build

```bash
fluidkit build
```

Runs codegen, starts the backend server, and then runs `npm run build`. The backend must be running during the build for prerender to work.

| Flag | Description |
|---|---|
| `--backend-port INT` | Override backend port (default: `8000`) |

## preview

```bash
fluidkit preview
```

Previews the production build locally. Starts both the FastAPI backend and the Vite preview server.

| Flag | Description |
|---|---|
| `--backend-port INT` | Override backend port (default: `8000`) |
| `--frontend-port INT` | Override frontend port (default: `5173`) |

## install

```bash
fluidkit install tailwindcss         # npm install tailwindcss
fluidkit install -D prettier         # npm install --save-dev prettier
```

Shorthand for `npm install`. The `-D` / `--save-dev` flag installs as a dev dependency.

## npm

```bash
fluidkit npm run build
fluidkit npm install
fluidkit npm audit
```

Passthrough to npm. Any arguments after `npm` are forwarded directly.

## npx

```bash
fluidkit npx sv add tailwindcss
fluidkit npx prisma generate
```

Passthrough to npx. Any arguments after `npx` are forwarded directly.

## node

```bash
fluidkit node scripts/seed.js
fluidkit node --version
```

Passthrough to node. Any arguments after `node` are forwarded directly.

## Flag precedence

CLI flags override `fluidkit.config.json`, which overrides defaults. See [Configuration](config.md) for the config file reference.
