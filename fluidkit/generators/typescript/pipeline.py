# v2/generators/pipeline.py

"""
FluidKit V2 Generation Pipeline

Orchestrates import generation, interface generation, and fetch wrapper generation
into complete TypeScript files with proper import statements.
"""

from pathlib import Path
from typing import Dict, List, Union

from fluidkit.core.config import FluidKitConfig
from fluidkit.core.schema import FluidKitApp, RouteNode, ModelNode
from fluidkit.core.constants import FluidKitRuntime, GenerationPaths
from fluidkit.generators.typescript.interfaces import generate_interface
from fluidkit.generators.typescript.clients import generate_fetch_wrapper
from fluidkit.generators.typescript.imports import ImportContext, generate_imports_for_file


def generate_typescript_files(
    fluid_app: FluidKitApp,
    config: FluidKitConfig,
    **runtime_config
) -> Dict[str, str]:
    """
    Generate complete TypeScript files from FluidKitApp using configuration.
    
    Args:
        fluid_app: Complete FluidKit app model
        config: FluidKit configuration object
        **runtime_config: Override runtime function names (for advanced use)
        
    Returns:
        Dict mapping file_path -> generated_content
    """
    # Set runtime defaults (can be overridden)
    runtime_config.setdefault('api_result_type', 'ApiResult')
    runtime_config.setdefault('get_base_url_fn', 'getBaseUrl')
    runtime_config.setdefault('handle_response_fn', 'handleResponse')

    project_root = fluid_app.metadata.get('project_root', str(Path.cwd().resolve()))
    
    # Group nodes by their generated file locations
    files_to_generate = _group_nodes_by_generated_files(fluid_app, config, project_root)
    
    generated_files = {}
    
    # Generate TypeScript content files
    for ts_file_path, file_content in files_to_generate.items():
        content = _generate_file_content(
            file_content, 
            config, 
            project_root, 
            fluid_app,
            **runtime_config
        )
        
        if content.strip():
            generated_files[ts_file_path] = content
    
    # Generate FluidKit runtime
    runtime_path = _get_runtime_file_path(config, project_root)
    generated_files[runtime_path] = _generate_fluidkit_runtime(config)
    
    # Generate proxy files for framework flow
    if config.should_generate_proxy:
        proxy_files = _generate_proxy_files(config, project_root)
        generated_files.update(proxy_files)
    
    return generated_files


def _group_nodes_by_generated_files(
    fluid_app: FluidKitApp, 
    config: FluidKitConfig,
    project_root: str
) -> Dict[str, Dict[str, List[Union[RouteNode, ModelNode]]]]:
    """Group models and routes by their generated TypeScript file locations."""
    files_content = {}
    
    # Group models
    for model in fluid_app.models:
        ts_file_path = _get_generated_file_path(model.location, config, project_root)
        
        if ts_file_path not in files_content:
            files_content[ts_file_path] = {"models": [], "routes": []}
        files_content[ts_file_path]["models"].append(model)
    
    # Group routes
    for route in fluid_app.routes:
        ts_file_path = _get_generated_file_path(route.location, config, project_root)
        
        if ts_file_path not in files_content:
            files_content[ts_file_path] = {"models": [], "routes": []}
        files_content[ts_file_path]["routes"].append(route)
    
    return files_content


def _generate_file_content(
    file_content: Dict[str, List[Union[RouteNode, ModelNode]]],
    config: FluidKitConfig,
    project_root: str,
    fluid_app: FluidKitApp,
    **runtime_config
) -> str:
    """Generate complete TypeScript file content."""
    models = file_content["models"]
    routes = file_content["routes"]
    
    if not models and not routes:
        return ""
    
    all_nodes = models + routes
    source_location = all_nodes[0].location
    
    context = ImportContext(
        config=config,
        project_root=project_root,
        source_location=source_location,
    )
    
    needs_runtime = len(routes) > 0
    
    sections = []
    
    # Generate imports
    imports = generate_imports_for_file(
        nodes=all_nodes,
        context=context,
        fluid_app=fluid_app,
        needs_runtime=needs_runtime,
        **runtime_config
    )
    if imports:
        sections.append(imports)
    
    # Generate interfaces
    if models:
        interface_sections = []
        for model in models:
            interface_content = generate_interface(model)
            if interface_content:
                interface_sections.append(interface_content)
        if interface_sections:
            sections.append("\n\n".join(interface_sections))
    
    # Generate fetch wrappers
    if routes:
        fetch_sections = []
        for route in routes:
            fetch_content = generate_fetch_wrapper(route, **runtime_config)
            if fetch_content:
                fetch_sections.append(fetch_content)
        if fetch_sections:
            sections.append("\n\n".join(fetch_sections))
    
    return "\n\n".join(sections)


def _get_generated_file_path(location, config: FluidKitConfig, project_root: str) -> str:
    """Convert ModuleLocation to generated TypeScript file path using config."""
    if not location.file_path:
        raise ValueError(f"ModuleLocation {location.module_path} has no file_path")
    
    project_root_path = Path(project_root).resolve()
    py_file_path = Path(location.file_path).resolve()
    
    if config.output.strategy == "co-locate":
        return str(py_file_path.with_suffix('.ts'))
    elif config.output.strategy == "mirror":
        try:
            relative_to_project = py_file_path.relative_to(project_root_path)
            mirror_path = project_root_path / config.output.location / relative_to_project.with_suffix('.ts')
            return str(mirror_path)
        except ValueError:
            # Fallback if file is outside project
            return str(py_file_path.with_suffix('.ts'))
    else:
        raise ValueError(f"Unknown strategy: {config.output.strategy}")


def _get_runtime_file_path(config: FluidKitConfig, project_root: str) -> str:
    """Get the runtime.ts file path based on configuration."""
    runtime_dir = Path(project_root) / config.output.location
    return str(runtime_dir / "runtime.ts")


def _generate_fluidkit_runtime(config: FluidKitConfig) -> str:
    """Generate environment-aware FluidKit TypeScript runtime."""
    
    # Generate getBaseUrl function based on flow type
    if config.is_fullstack_config:
        base_url_fn = _generate_framework_aware_base_url(config)
    else:
        base_url_fn = _generate_normal_flow_base_url(config)
    
    return f'''/**
 * FluidKit Runtime Utilities
 * Auto-generated TypeScript utilities for FluidKit fetch wrappers
 */

export interface ApiResult<T = any> {{
  data?: T;
  error?: string;
  status: number;
  success: boolean;
}}

{base_url_fn}

export async function handleResponse<T = any>(response: Response): Promise<ApiResult<T>> {{
  const status = response.status;
  const success = response.ok;
  
  if (!success) {{
    let error: string;
    try {{
      const errorBody = await response.json();
      error = errorBody.detail || errorBody.message || response.statusText;
    }} catch {{
      error = response.statusText || `HTTP ${{status}}`;
    }}
    return {{ error, status, success: false }};
  }}
  
  try {{
    const responseData = await response.json();
    return {{ data: responseData, status, success: true }};
  }} catch (e) {{
    return {{ 
      error: 'Failed to parse response JSON', 
      status, 
      success: false 
    }};
  }}
}}'''


def _generate_framework_aware_base_url(config: FluidKitConfig) -> str:
    """Generate getBaseUrl for framework flow with environment awareness."""
    dev_env = config.get_environment("development")
    prod_env = config.get_environment("production")
    
    # Check if we need client/server detection
    has_unified_mode = any(
        env.mode == "unified" 
        for env in config.environments.values()
    )
    
    if has_unified_mode:
        # Framework flow with proxy detection
        return f'''export function getBaseUrl(): string {{
  // Detect if running in browser (client) vs server
  if (typeof window !== 'undefined') {{
    // Browser environment - use proxy routes
    return '{dev_env.apiUrl}';
  }}
  
  // Server environment - direct communication
  return 'http://{config.backend.host}:{config.backend.port}';
}}'''
    else:
        # Framework flow but all separate mode
        return f'''export function getBaseUrl(): string {{
  // Production build - direct communication
  return '{prod_env.apiUrl}';
}}'''


def _generate_normal_flow_base_url(config: FluidKitConfig) -> str:
    """Generate getBaseUrl for normal flow (simple URL switching)."""
    dev_env = config.get_environment("development")
    prod_env = config.get_environment("production")
    
    return f'''export function getBaseUrl(): string {{
  // Simple development/production URL switching
  // Update this for production builds
  return '{dev_env.apiUrl}';
}}'''


def _generate_proxy_files(config: FluidKitConfig, project_root: str) -> Dict[str, str]:
    """Generate framework-specific proxy files for unified mode."""
    proxy_files = {}
    
    # Only generate proxy for environments that use unified mode
    for env_name, env_config in config.environments.items():
        if env_config.mode == "unified":
            if config.framework == "sveltekit":
                proxy_files.update(_generate_sveltekit_proxy(env_config, project_root, config))
            elif config.framework == "nextjs":
                proxy_files.update(_generate_nextjs_proxy(env_config, project_root, config))
            # Add other frameworks as needed
    
    return proxy_files


def _generate_sveltekit_proxy(env_config, project_root: str, config: FluidKitConfig) -> Dict[str, str]:
    """Generate SvelteKit API proxy route."""
    # Extract API path from URL (e.g., "/api" -> "api")
    api_path = env_config.apiUrl.lstrip('/')
    
    # Generate proxy route path
    proxy_route_path = Path(project_root) / "src" / "routes" / api_path / "[...path]" / "+server.ts"
    
    proxy_content = f'''import type {{ RequestHandler }} from './$types';

const FASTAPI_URL = 'http://{config.backend.host}:{config.backend.port}';

export const GET: RequestHandler = async ({{ params, url, request }}) => {{
  const apiPath = params.path;
  const searchParams = url.searchParams.toString();
  const fullUrl = `${{FASTAPI_URL}}/${{apiPath}}${{searchParams ? `?${{searchParams}}` : ''}}`;
  
  const response = await fetch(fullUrl, {{
    method: 'GET',
    headers: {{
      'content-type': request.headers.get('content-type') || '',
      'authorization': request.headers.get('authorization') || '',
    }}
  }});
  
  return response;
}};

export const POST: RequestHandler = async ({{ params, request }}) => {{
  const apiPath = params.path;
  const fullUrl = `${{FASTAPI_URL}}/${{apiPath}}`;
  
  const response = await fetch(fullUrl, {{
    method: 'POST',
    headers: {{
      'content-type': request.headers.get('content-type') || '',
      'authorization': request.headers.get('authorization') || '',
    }},
    body: await request.text()
  }});
  
  return response;
}};

export const PUT: RequestHandler = async ({{ params, request }}) => {{
  const apiPath = params.path;
  const fullUrl = `${{FASTAPI_URL}}/${{apiPath}}`;
  
  const response = await fetch(fullUrl, {{
    method: 'PUT',
    headers: {{
      'content-type': request.headers.get('content-type') || '',
      'authorization': request.headers.get('authorization') || '',
    }},
    body: await request.text()
  }});
  
  return response;
}};

export const DELETE: RequestHandler = async ({{ params, request }}) => {{
  const apiPath = params.path;
  const fullUrl = `${{FASTAPI_URL}}/${{apiPath}}`;
  
  const response = await fetch(fullUrl, {{
    method: 'DELETE',
    headers: {{
      'content-type': request.headers.get('content-type') || '',
      'authorization': request.headers.get('authorization') || '',
    }}
  }});
  
  return response;
}};

export const PATCH: RequestHandler = async ({{ params, request }}) => {{
  const apiPath = params.path;
  const fullUrl = `${{FASTAPI_URL}}/${{apiPath}}`;
  
  const response = await fetch(fullUrl, {{
    method: 'PATCH',
    headers: {{
      'content-type': request.headers.get('content-type') || '',
      'authorization': request.headers.get('authorization') || '',
    }},
    body: await request.text()
  }});
  
  return response;
}};'''

    return {str(proxy_route_path): proxy_content}


def _generate_nextjs_proxy(env_config, project_root: str, config: FluidKitConfig) -> Dict[str, str]:
    """Generate Next.js API proxy route."""
    # Extract API path from URL
    api_path = env_config.apiUrl.lstrip('/')
    
    # Generate proxy route path for Next.js App Router
    proxy_route_path = Path(project_root) / "app" / api_path / "[...path]" / "route.ts"
    
    proxy_content = f'''import {{ NextRequest }} from 'next/server';

const FASTAPI_URL = 'http://{config.backend.host}:{config.backend.port}';

export async function GET(request: NextRequest, {{ params }}: {{ params: {{ path: string[] }} }}) {{
  const apiPath = params.path.join('/');
  const searchParams = request.nextUrl.searchParams.toString();
  const fullUrl = `${{FASTAPI_URL}}/${{apiPath}}${{searchParams ? `?${{searchParams}}` : ''}}`;
  
  const response = await fetch(fullUrl, {{
    method: 'GET',
    headers: {{
      'content-type': request.headers.get('content-type') || '',
      'authorization': request.headers.get('authorization') || '',
    }}
  }});
  
  return response;
}}

export async function POST(request: NextRequest, {{ params }}: {{ params: {{ path: string[] }} }}) {{
  const apiPath = params.path.join('/');
  const fullUrl = `${{FASTAPI_URL}}/${{apiPath}}`;
  
  const response = await fetch(fullUrl, {{
    method: 'POST',
    headers: {{
      'content-type': request.headers.get('content-type') || '',
      'authorization': request.headers.get('authorization') || '',
    }},
    body: await request.text()
  }});
  
  return response;
}}

export async function PUT(request: NextRequest, {{ params }}: {{ params: {{ path: string[] }} }}) {{
  const apiPath = params.path.join('/');
  const fullUrl = `${{FASTAPI_URL}}/${{apiPath}}`;
  
  const response = await fetch(fullUrl, {{
    method: 'PUT',
    headers: {{
      'content-type': request.headers.get('content-type') || '',
      'authorization': request.headers.get('authorization') || '',
    }},
    body: await request.text()
  }});
  
  return response;
}}

export async function DELETE(request: NextRequest, {{ params }}: {{ params: {{ path: string[] }} }}) {{
  const apiPath = params.path.join('/');
  const fullUrl = `${{FASTAPI_URL}}/${{apiPath}}`;
  
  const response = await fetch(fullUrl, {{
    method: 'DELETE',
    headers: {{
      'content-type': request.headers.get('content-type') || '',
      'authorization': request.headers.get('authorization') || '',
    }}
  }});
  
  return response;
}}

export async function PATCH(request: NextRequest, {{ params }}: {{ params: {{ path: string[] }} }}) {{
  const apiPath = params.path.join('/');
  const fullUrl = `${{FASTAPI_URL}}/${{apiPath}}`;
  
  const response = await fetch(fullUrl, {{
    method: 'PATCH',
    headers: {{
      'content-type': request.headers.get('content-type') || '',
      'authorization': request.headers.get('authorization') || '',
    }},
    body: await request.text()
  }});
  
  return response;
}}'''

    return {str(proxy_route_path): proxy_content}


# === TESTING HELPERS === #

def test_config_driven_generation():
    """Test the config-driven generation pipeline."""
    try:
        from tests.sample.app import app
        from fluidkit.core.integrator import integrate
        
        print("=== TESTING CONFIG-DRIVEN GENERATION ===")
        
        # Test normal flow
        print("\n1. Testing normal flow generation:")
        fluid_app, files = integrate(app)
        
        print(f"Generated {len(files)} files:")
        for file_path in sorted(files.keys()):
            print(f"  📄 {Path(file_path).name}")
        
        # Test runtime content
        runtime_files = [f for f in files.keys() if 'runtime.ts' in f]
        if runtime_files:
            print("\n2. Runtime content preview:")
            runtime_content = files[runtime_files[0]]
            lines = runtime_content.split('\n')
            for i, line in enumerate(lines[:15]):
                print(f"   {i+1:2d}: {line}")
            if len(lines) > 15:
                print(f"       ... ({len(lines)-15} more lines)")
        
        print("\n✅ Config-driven generation test passed!")
        
    except ImportError:
        print("❌ Could not import test app")
    except Exception as e:
        print(f"❌ Test failed: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    test_config_driven_generation()
