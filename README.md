# FluidKit

<div align="center">
  <img src="https://azure-deliberate-dog-514.mypinata.cloud/ipfs/bafkreiay74jzankyzj2zh4zemmpidafbsrcr4hwjxnl5e3qk32xyi6t3hi" alt="FluidKit Logo" width="125">
</div>

**Automatic TypeScript client generation for FastAPI through runtime introspection. Get tRPC-like developer experience with full-stack type safety across Python and TypeScript.** 

```bash
pip install fluidkit
```

```python
# Add to your existing FastAPI app
import fluidkit
fluidkit.integrate(app)
```

**That's it.** FluidKit automatically generates TypeScript clients with complete type safety.


---
## Core Concept

FluidKit **introspects your FastAPI application at runtime** and generates TypeScript clients with complete type safety. Eliminate manual API client maintenance, keep frontend and backend perfectly synchronized, and get instant IDE autocomplete for your entire Python API surface.

**Two Development Flows:**

1. **Client Generation**: Pure TypeScript client generation for any project
2. **Full-Stack Integration**: Unified development with modern frontend frameworks through local proxy communication


## Generation Example
**Your FastAPI code**
```python
from pydantic import BaseModel
from fastapi import FastAPI, Query

app = FastAPI()

class User(BaseModel):
    id: int
    name: str
    email: str

@app.get("/users/{user_id}")
async def get_user(user_id: int, include_profile: bool = Query(False)) -> User:
    """Get user by ID"""
    return User(id=user_id, name="John", email="john@example.com")

import fluidkit
fluidkit.integrate(app)
```


**Auto-generated typescript output**
```typescript
export interface User {
  id: number;
  name: string;
  email: string;
}

/**
 * Get user by ID
 *
 * @param user_id
 * @param include_profile
 * @param options - Additional fetch options
 */
export const get_user = async (
  user_id: number, 
  include_profile?: boolean, 
  options?: RequestInit
): Promise<ApiResult<User>> => {
  let url = `${getBaseUrl()}/users/${user_id}`;

  const searchParams = new URLSearchParams();
  if (include_profile !== undefined) {
    searchParams.set('include_profile', String(include_profile));
  }
  if (searchParams.toString()) {
    url += `?${searchParams.toString()}`;
  }

  const requestOptions: RequestInit = {
    method: 'GET',
    headers: options?.headers,
    ...options
  };

  const response = await fetch(url, requestOptions);
  return handleResponse(response);
};
```


---
## Auto-Discovery

FluidKit can automatically discover and bind APIRouters from files matching configurable patterns. This enables **co-location** where your API logic sits next to your frontend routes, eliminating manual router imports and keeping related code together.

**Create discoverable API files:**
```python
# routes/users/_api.py  OR  routes/users/users.api.py
from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter(prefix="/users")

class User(BaseModel):
    id: int
    name: str

@router.get("/{user_id}")
async def get_user(user_id: int) -> User:
    return User(id=user_id, name="John")
```

**SvelteKit-style folder structuring for fullstack development**
```python
# routes/users/[id]/profile.api.py - Dynamic parameters
from fastapi import APIRouter

router = APIRouter()

@router.get("/details")
async def get_profile(id: int):  # ✅ 'id' parameter required
    return {"user_id": id, "profile": "details"}

# routes/files/[...path]/handler.api.py - Rest parameters  
@router.get("/download")
async def download_file(path: str):  # ✅ 'path' parameter required
    return {"file_path": path}
```

**Enable auto-discovery:**
```json
{
  "autoDiscovery": {
    "enabled": true,
    "filePatterns": ["_*.py", "*.*.py"]
  }
}
```

**Folder Structure → FastAPI Route Translation:**

| Folder Structure | Generated Route | Required Parameters |
|------------------|-----------------|-------------------|
| `routes/users/_api.py` | `/users/*` | None |
| `routes/users/[id]/profile.api.py` | `/users/{id}/*` | `id` |
| `routes/files/[...path]/handler.api.py` | `/files/{path:path}/*` | `path` |
| `routes/(admin)/users/manage.api.py` | `/users/*` | None (groups ignored) |

**Supported patterns:**
1. Auto discovered files:
  - `_api.py`, `_routes.py` (underscore prefix `_*.py`)
  - `user.api.py`, `admin.service.py` (any dot pattern `*.*.py`)
2. Valid folder naming patterns:
  - `[id]`, `[userId]` (dynamic parameters)
  - `[...path]`, `[...file]` (rest parameters)
  - `(admin)`, `(app)` (route groups - organize without affecting URLs)

**Benefits:**
- ✅ **Zero boilerplate** - No manual router imports
- ✅ **File co-location** - Place API files next to your frontend routes
- ✅ **Parameter validation** - FluidKit ensures path parameters match function signatures
- ✅ **Framework-style routing** - SvelteKit/Next.js conventions for Python
- ✅ **Predictable routing** - Same behavior as manual `app.include_router()`

> **Note:** FluidKit validates that functions in parameterized folders (e.g., `[id]`) include the required parameters in their signatures. Missing parameters will raise clear validation errors during startup.

---
##  Full-Stack Development
Inspired by [Next.js server actions](https://nextjs.org/docs/14/app/building-your-application/data-fetching/server-actions-and-mutations) and [Svelte's remote functions proposal](https://github.com/sveltejs/kit/discussions/13897), FluidKit enables cross-language full-stack development without restrictions.

**Example with SvelteKit**

```typescript
// +page.server.ts - Server-side data loading
import { getUser, createOrder } from '$lib/api/users';

export const load = async () => {
  const user = await getUser(123); // Direct FastAPI call
  return { user: user.data };
};
```

```typescript
// +page.svelte - Client-side interactions  
<script lang="ts">
import { updateProfile } from '$lib/api/users';

async function handleUpdate() {
  const result = await updateProfile(data); // Proxied through SvelteKit into FastAPI
}
</script>

<!-- Markup here -->
<div>...</div>
```

The same generated client works seamlessly in both server (direct FastAPI communication) and browser (proxied) environments. By detecting where its been executed and using appropriate baseurl.


---
## Configuration

FluidKit behavior is controlled by `fluid.config.json`:

```json
{
  "framework": null,                 // "sveltekit" | "nextjs" for full-stack
  "target": "development",           // Which environment to build for
  "output": {
    "strategy": "mirror",            // File placement strategy
    "location": ".fluidkit"          // FluidKit output directory (runtime.ts, etc.)
  },
  "backend": {
    "host": "localhost",             // FastAPI server host
    "port": 8000                     // FastAPI server port
  },
  "environments": {
    "development": {
      "mode": "unified",             // Same codebase vs separate repos
      "apiUrl": "/api"               // API base URL for this environment
    },
    "production": {
      "mode": "separate",
      "apiUrl": "https://api.example.com"
    }
  },

  "include": [                       // Auto-discovery scan paths
    "src/**/*.py",
    "lib/**/*.py"
  ],
  "exclude": [                       // Exclude patterns
    "**/__pycache__/**",
    "**/*.test.py"
  ],
  "autoDiscovery": {
    "enabled": false,                // Enable +*.py auto-discovery
    "filePattern": "+*.py"           // File pattern to scan
  },
}
```

**Configuration Reference:**

| Field | Values | Description |
|-------|--------|-------------|
| `target` | `"development"` \| `"production"` | Which environment to build for |
| `output.strategy` | `"mirror"` \| `"co-locate"` | Where to place generated client files |
| `output.location` | `".fluidkit"` \| `"src/lib"` | Directory for runtime.ts and mirror structure |
| `mode` | `"unified"` \| `"separate"` | Same codebase vs separate frontend/backend repos |
| `framework` | `"sveltekit"` \| `"nextjs"` | Enable full-stack integration |
| `include` | `["src/**/*.py"]` | Paths to scan for auto-discovery |
| `exclude` | `["**/*.test.py"]` | Patterns to exclude from scanning |
| `autoDiscovery.enabled` | `true` \| `false` | Enable `+*.py` auto-discovery |
| `autoDiscovery.filePattern` | `"+*.py"` | File pattern for auto-discovery |


**Mode Explanation:**
- **`"unified"`**: Frontend and backend in same codebase (full-stack apps)
- **`"separate"`**: Generated code can be copied to separate frontend repo

**Generation Strategies:**

```python
# Your Python project structure
src/
├── routes/
│   ├── users.py       # @app.get("/users")
│   └── orders.py      # @app.get("/orders") 
└── models/
    └── user.py        # class User(BaseModel)
```

**Co-locate Strategy** (`"strategy": "co-locate"`):
```
src/
├── routes/
│   ├── users.py
│   ├── users.ts       # ✅ Generated next to Python file
│   ├── orders.py
│   └── orders.ts      # ✅ Generated next to Python file
└── models/
    ├── user.py
    └── user.ts        # ✅ Generated next to Python file

.fluidkit/             # ✅ FluidKit utilities
└── runtime.ts
```

**Mirror Strategy** (`"strategy": "mirror"`):
```
src/                   # Your Python code (unchanged)
├── routes/
│   ├── users.py
│   └── orders.py
└── models/
    └── user.py

.fluidkit/             # ✅ Complete generated structure
├── runtime.ts         # ✅ FluidKit utilities
├── routes/
│   ├── users.ts
│   └── orders.ts
└── models/
    └── user.ts
```

**Full-stack projects** add framework integration:
```json
{
  "target": "development",
  "framework": "sveltekit",          // Enable framework integration
  "environments": {
    "development": {
      "mode": "unified",             // Same codebase with proxy support
      "apiUrl": "/api"
    }
  }
}
```

This auto-generates proxy routes and environment-aware runtime utilities.


---
## Language Extensibility

FluidKit generates an **intermediate representation (IR)** from FastAPI introspection, enabling client generation for multiple languages possible in the future:

- ✅ **TypeScript** (current)
- 🚧 **Python** (planned)
- 🚧 **JavaScript with JSDoc** (planned)  
- 🚧 **Go** (planned)

## Quick Start

**Basic Integration:**
```python
import fluidkit
from fastapi import FastAPI

app = FastAPI()

# Your existing routes...

# Generate TypeScript clients
fluidkit.integrate(app)
```

**Full-Stack Integration:**
```python
# First, create fluid.config.json with framework: "sveltekit"
fluidkit.integrate(app)  # Auto-generates proxy routes + clients
```

**Generated Structure:**
```
.fluidkit/
├── runtime.ts           # Environment-aware utilities
└── api/
    ├── users.ts         # Generated from /api/users routes
    └── orders.ts        # Generated from /api/orders routes

# Framework flow also generates:
src/routes/api/[...path]/+server.ts  # SvelteKit proxy
```

## Key Features

- **Runtime Introspection**: No AST parsing, uses FastAPI's own dependency system
- **Complete Type Safety**: Preserves Pydantic models, validation constraints, and return types
- **Environment Aware**: Same client code works in server and browser contexts
- **Framework Agnostic**: Adapts to SvelteKit, Next.js, and other frameworks
- **Zero Configuration**: Works out of the box, configure only when needed

**The result**: Full Python ecosystem access in JavaScript projects with complete IDE support and type safety.
