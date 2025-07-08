"""
FluidKit V2 App Integration

Config-driven integration API for FluidKit with FastAPI applications with multi-language support.
Orchestrates route collection, model discovery, and optional code generation supporting both normal flow
(client generation only) and full-stack flow (framework + proxying).
"""

import logging
from pathlib import Path
from fastapi import FastAPI
from fastapi.routing import APIRoute
from typing import List, Dict, Tuple, Optional

from fluidkit.introspection.routes import route_to_node
from fluidkit.introspection.models import discover_models_from_routes
from fluidkit.core.config import load_fluidkit_config, FluidKitConfig
from fluidkit.core.schema import FluidKitApp, RouteNode, LanguageType


logger = logging.getLogger(__name__)


def integrate(
    app: FastAPI,
    lang: Optional[str] = None,  # Default to typescript when None
    config_path: Optional[str] = None,
    project_root: Optional[str] = None,
    verbose: bool = False,
    **options
) -> Tuple[FluidKitApp, Dict[str, str]]:
    """
    Integrate FluidKit with FastAPI app using configuration-driven approach.
    
    Args:
        app: FastAPI application instance
        lang: Target language for code generation (defaults to "typescript")
        config_path: Path to fluid.config.json (auto-detected if None)
        project_root: Project root directory (defaults to current directory)
        verbose: Enable detailed logging
        **options: Additional options for backward compatibility
        
    Returns:
        (FluidKitApp, generated_files_dict)
    """
    if verbose:
        logging.basicConfig(level=logging.DEBUG, format='%(levelname)s: %(message)s')
    
    # Determine project root
    if project_root is None:
        project_root = str(Path.cwd().resolve())
    else:
        project_root = str(Path(project_root).resolve())
    
    # Load FluidKit configuration
    config = load_fluidkit_config(project_root)
    
    # Override config with explicit parameters (backward compatibility)
    if 'strategy' in options:
        config.output.strategy = options['strategy']
    
    if verbose:
        logger.info("Starting FluidKit integration")
        logger.debug(f"Project root: {project_root}")
        logger.debug(f"Config framework: {config.framework}")
        logger.debug(f"Output strategy: {config.output.strategy}")
        logger.debug(f"Output location: {config.output.location}")
    
    # Collect and convert routes
    api_routes = _collect_fastapi_routes(app)
    route_nodes = _convert_routes_to_nodes(api_routes)
    
    # Discover models (project types only)
    model_nodes = discover_models_from_routes(route_nodes, project_root)
    
    # Build FluidKitApp
    fluid_app = FluidKitApp(
        models=model_nodes,
        routes=route_nodes,
        app_instance=app,
        metadata={
            'project_root': project_root,
            'config': config,
            **options
        }
    )
    
    if verbose:
        logger.info(f"Introspection complete: {len(route_nodes)} routes, {len(model_nodes)} models")
    
    # Generate client code
    target_lang = lang or "typescript"
    normalized_lang = _normalize_language(target_lang)
    
    if normalized_lang == LanguageType.TYPESCRIPT:
        generated_files = _generate_and_write_typescript(fluid_app, config, verbose, **options)
        
        if not verbose:
            file_count = len(generated_files)
            flow_type = "full-stack" if config.is_fullstack_config else "normal"
            print(f"FluidKit: Generated {file_count} TypeScript files ({flow_type} flow)")
        
        return fluid_app, generated_files
    
    else:
        raise NotImplementedError(f"Language '{lang}' not yet supported. Currently supported: typescript")


def _generate_and_write_typescript(
    fluid_app: FluidKitApp, 
    config: FluidKitConfig,
    verbose: bool,
    **options
) -> Dict[str, str]:
    """Generate TypeScript files using configuration settings."""
    from fluidkit.generators.typescript.pipeline import generate_typescript_files
    
    # Pass config to generation pipeline
    generated_files = generate_typescript_files(
        fluid_app=fluid_app,
        config=config,
        **options
    )
    
    _write_generated_files(generated_files, verbose)
    return generated_files


def _write_generated_files(generated_files: Dict[str, str], verbose: bool):
    """Write generated files to disk with auto-generated headers."""
    for file_path, content in generated_files.items():
        try:
            file_path_obj = Path(file_path)
            file_path_obj.parent.mkdir(parents=True, exist_ok=True)
            
            header = _get_file_header(file_path_obj.suffix)
            final_content = header + content
            
            with open(file_path_obj, 'w', encoding='utf-8') as f:
                f.write(final_content)
            
            if verbose:
                logger.debug(f"Generated: {file_path}")
            
        except Exception as e:
            error_msg = f"Failed to write {file_path}: {e}"
            if verbose:
                logger.error(error_msg)
            else:
                print(f"❌ {error_msg}")


def _get_file_header(file_extension: str) -> str:
    """Get auto-generated file header based on file type."""
    if file_extension == '.ts':
        return '''/**
 * Auto-generated by FluidKit from FastAPI routes and models - DO NOT EDIT
 * Changes will be overwritten on regeneration.
 */

'''
    elif file_extension == '.py':
        return '''"""
Auto-generated by FluidKit from FastAPI routes and models - DO NOT EDIT
Changes will be overwritten on regeneration.
"""

'''
    else:
        return '''/**
 * Auto-generated by FluidKit from FastAPI routes and models - DO NOT EDIT
 * Changes will be overwritten on regeneration.
 */

'''


def _normalize_language(lang: str) -> LanguageType:
    """Normalize language string to LanguageType enum."""
    lang_lower = lang.lower()
    
    if lang_lower in ["ts", "typescript"]:
        return LanguageType.TYPESCRIPT
    else:
        valid_langs = ["ts", "typescript"]
        raise ValueError(f"Unsupported language '{lang}'. Supported: {', '.join(valid_langs)}")


def _collect_fastapi_routes(app: FastAPI) -> List[APIRoute]:
    """Collect user-defined API routes from FastAPI app."""
    user_routes = []
    
    for route in app.routes:
        if isinstance(route, APIRoute) and _is_user_defined_route(route):
            user_routes.append(route)
    
    return user_routes


def _convert_routes_to_nodes(api_routes: List[APIRoute]) -> List[RouteNode]:
    """Convert FastAPI APIRoute objects to RouteNode objects."""
    route_nodes = []
    
    for route in api_routes:
        try:
            route_node = route_to_node(route)
            if route_node:
                route_nodes.append(route_node)
        except Exception as e:
            logger.warning(f"Failed to convert route {route.path}: {e}")
            continue
    
    return route_nodes


def _is_user_defined_route(route: APIRoute) -> bool:
    """Determine if route is user-defined using module-based filtering."""
    endpoint = route.endpoint
    
    if (not endpoint or not callable(endpoint) or 
        not hasattr(endpoint, '__name__') or endpoint.__name__ == '<lambda>' or
        not hasattr(endpoint, '__module__') or not route.methods):
        return False
    
    endpoint_module = endpoint.__module__
    system_prefixes = ('fastapi.', 'starlette.')
    
    if any(endpoint_module.startswith(prefix) for prefix in system_prefixes):
        return False
    
    valid_methods = {'GET', 'POST', 'PUT', 'DELETE', 'PATCH', 'HEAD', 'OPTIONS', 'TRACE'}
    if not any(method in valid_methods for method in route.methods):
        return False
    
    if hasattr(endpoint, 'app') and hasattr(endpoint, '__call__'):
        return False
    
    return True


# === CONVENIENCE FUNCTIONS === #

def introspect_only(app: FastAPI, project_root: Optional[str] = None, **options) -> FluidKitApp:
    """Convenience function for introspection only (no code generation)."""
    if project_root is None:
        project_root = str(Path.cwd().resolve())
    
    # Load config for consistency
    config = load_fluidkit_config(project_root)
    
    api_routes = _collect_fastapi_routes(app)
    route_nodes = _convert_routes_to_nodes(api_routes)
    model_nodes = discover_models_from_routes(route_nodes, project_root)
    
    fluid_app = FluidKitApp(
        models=model_nodes,
        routes=route_nodes,
        app_instance=app,
        metadata={'project_root': project_root, 'config': config, **options}
    )
    
    flow_type = "full-stack" if config.is_fullstack_config else "normal"
    print(f"FluidKit: Introspected {len(route_nodes)} routes, {len(model_nodes)} models ({flow_type} flow)")
    return fluid_app


def generate_only(
    app: FastAPI, 
    project_root: Optional[str] = None, 
    **options
) -> Dict[str, str]:
    """Convenience function to generate files without writing to disk."""
    from fluidkit.generators.typescript.pipeline import generate_typescript_files
    
    if project_root is None:
        project_root = str(Path.cwd().resolve())
    
    # Load config for generation settings
    config = load_fluidkit_config(project_root)
    
    api_routes = _collect_fastapi_routes(app)
    route_nodes = _convert_routes_to_nodes(api_routes)
    model_nodes = discover_models_from_routes(route_nodes, project_root)
    
    fluid_app = FluidKitApp(
        models=model_nodes,
        routes=route_nodes,
        app_instance=app,
        metadata={'project_root': project_root, 'config': config, **options}
    )
    
    generated_files = generate_typescript_files(
        fluid_app=fluid_app,
        config=config,
        **options
    )
    
    flow_type = "full-stack" if config.is_fullstack_config else "normal"
    print(f"FluidKit: Generated {len(generated_files)} TypeScript files ({flow_type} flow) - not written to disk")
    return generated_files


# === TESTING FUNCTION === #

def test_integration():
    """Test the updated integration with config system."""
    try:
        from tests.sample.app import app
        
        print("=== FLUIDKIT CONFIG-DRIVEN INTEGRATION TEST ===")
        
        # Test 1: Normal flow (default config creation)
        print("\n1. Normal flow integration:")
        fluid_app, files = integrate(app)
        
        # Test 2: Custom project root
        print("\n2. Custom project root:")
        import tempfile
        with tempfile.TemporaryDirectory() as temp_dir:
            fluid_app, files = integrate(app, project_root=temp_dir)
        
        # Test 3: Introspection only
        print("\n3. Introspection only:")
        fluid_app = introspect_only(app)
        
        # Test 4: Generate only (don't write)
        print("\n4. Generate only (no file writing):")
        files = generate_only(app)
        
        print("\n✅ All integration tests passed!")
        
    except ImportError:
        print("❌ Could not import test app - ensure test files exist")
    except Exception as e:
        print(f"❌ Test failed: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    test_integration()
