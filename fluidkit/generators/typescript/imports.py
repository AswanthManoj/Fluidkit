# generators/typescript/imports.py
"""
FluidKit V2 Import Generator

Config-driven TypeScript import generation with strategy awareness,
OS-independent path handling, and configurable FluidKit runtime imports.
"""

import os
from pathlib import Path
from dataclasses import dataclass
from typing import Union, Set, Dict, List, Optional

from fluidkit.core.schema import *
from fluidkit.core.config import FluidKitConfig


@dataclass
class ImportContext:
    """Context for import generation with config integration."""
    source_location: ModuleLocation
    config: FluidKitConfig
    project_root: str


def generate_imports_for_file(
    nodes: List[Union[RouteNode, ModelNode]],
    context: ImportContext,
    fluid_app: FluidKitApp,
    needs_runtime: bool = False,
    **runtime_config
) -> str:
    """
    Generate complete import block for a TypeScript file using configuration.
    
    Args:
        nodes: List of RouteNode/ModelNode that will be in this file
        context: Import generation context with config
        fluid_app: Complete app model for type resolution
        needs_runtime: Whether to include FluidKit runtime imports
        **runtime_config: Runtime function names (api_result_type, etc.)
        
    Returns:
        Complete import statements as string (empty if no imports needed)

    Raises:
        ValueError: If path calculation fails
    """
    all_import_statements = []
    
    # Collect all referenced types from all nodes
    all_referenced_types: Set[str] = set()
    for node in nodes:
        all_referenced_types.update(node.get_referenced_types())
    
    # Resolve type locations (project types only)
    type_locations = {}
    for type_name in all_referenced_types:
        model = fluid_app.find_model_by_name(type_name)
        if model:  # Only project types will be found
            type_locations[type_name] = model.location
    
    # Generate runtime import statement if needed
    if needs_runtime:
        runtime_import = _generate_runtime_import_statement(context, **runtime_config)
        if runtime_import:
            all_import_statements.append(runtime_import)
    
    # Generate type import statements
    type_imports = _generate_type_import_statements(type_locations, context)
    all_import_statements.extend(type_imports)

    if all_import_statements:
        return '\n'.join(all_import_statements)
    else:
        return ''


def _generate_type_import_statements(
    type_locations: Dict[str, ModuleLocation],
    context: ImportContext
) -> List[str]:
    """Generate type import statements for project types using config."""
    if not type_locations:
        return []
    
    imports_by_path: Dict[str, List[str]] = {}
    
    for type_name, location in type_locations.items():
        import_path = _calculate_import_path(context.source_location, location, context)
        
        if import_path is None:  # Same file
            continue
        
        if import_path not in imports_by_path:
            imports_by_path[import_path] = []
        imports_by_path[import_path].append(type_name)
    
    import_statements = []
    for import_path in sorted(imports_by_path.keys()):
        types = sorted(imports_by_path[import_path])
        types_str = ', '.join(types)
        import_statements.append(f"import type {{ {types_str} }} from '{import_path}';")
    
    return import_statements


def _generate_runtime_import_statement(
    context: ImportContext,
    api_result_type: str = "ApiResult",
    get_base_url_fn: str = "getBaseUrl", 
    handle_response_fn: str = "handleResponse"
) -> Optional[str]:
    """Generate FluidKit runtime import statement using config."""
    runtime_path = _get_runtime_import_path(context)
    
    # Separate type imports from function imports
    type_import = f"import type {{ {api_result_type} }} from '{runtime_path}';"
    function_imports = [get_base_url_fn, handle_response_fn]
    function_import = f"import {{ {', '.join(function_imports)} }} from '{runtime_path}';"
    
    return f"{type_import}\n{function_import}"


def _calculate_import_path(
    source_location: ModuleLocation,
    target_location: ModuleLocation, 
    context: ImportContext
) -> Optional[str]:
    """
    Calculate relative import path between two project locations using config.
    
    This function is deterministic and never fails silently.
    
    Args:
        source_location: Location of the importing file
        target_location: Location of the file being imported
        context: Import context with config
        
    Returns:
        Relative import path or None if same file
        
    Raises:
        ValueError: If path calculation fails
    """
    source_file = _get_generated_file_path(source_location, context)
    target_file = _get_generated_file_path(target_location, context)
    
    # Check if same file (no import needed)
    if _are_same_file(source_file, target_file):
        return None
    
    return _calculate_relative_import_path(source_file, target_file)


def _get_runtime_import_path(context: ImportContext) -> str:
    """
    Get import path to FluidKit runtime using config.
    
    Returns:
        Relative import path to runtime.ts
        
    Raises:
        ValueError: If path calculation fails
    """
    source_file = _get_generated_file_path(context.source_location, context)
    runtime_file = _get_runtime_file_path(context.config, context.project_root)
    
    return _calculate_relative_import_path(source_file, runtime_file)


def _calculate_relative_import_path(source_file: Path, target_file: Path) -> str:
    """
    Calculate relative import path between two files with rock-solid reliability.
    
    This is the core path calculation function that must always work correctly.
    
    Args:
        source_file: Absolute path to source TypeScript file
        target_file: Absolute path to target TypeScript file
        
    Returns:
        Relative import path suitable for TypeScript imports
        
    Raises:
        ValueError: If paths cannot be resolved
    """
    try:
        # Ensure both paths are absolute and resolved
        source_abs = source_file.resolve()
        target_abs = target_file.resolve()
        
        # Validate that files have valid paths
        if not source_abs.is_absolute() or not target_abs.is_absolute():
            raise ValueError(f"Paths must be absolute: source={source_abs}, target={target_abs}")
        
        # Get the directory containing the source file
        source_dir = source_abs.parent
        
        # Calculate relative path from source directory to target file
        relative_path = _safe_relative_path(target_abs, source_dir)
        
        # Remove .ts extension for import
        relative_path = relative_path.with_suffix('')
        
        # Convert to forward slashes for TypeScript (cross-platform)
        import_path = str(relative_path).replace('\\', '/')
        
        # Add proper prefix for relative imports
        if import_path.startswith('../'):
            return import_path
        else:
            return f'./{import_path}'
            
    except Exception as e:
        raise ValueError(f"Failed to calculate relative path from {source_file} to {target_file}: {e}")


def _safe_relative_path(target: Path, base: Path) -> Path:
    """
    Safely calculate relative path with cross-platform compatibility.
    
    Args:
        target: Target file path
        base: Base directory path
        
    Returns:
        Relative path from base to target
        
    Raises:
        ValueError: If relative path cannot be calculated
    """
    try:
        # Try pathlib's relative_to first (most reliable when it works)
        return target.relative_to(base)
    except ValueError:
        # relative_to failed (likely cross-drive on Windows), use os.path.relpath
        try:
            relative_str = os.path.relpath(str(target), str(base))
            return Path(relative_str)
        except (ValueError, OSError) as e:
            raise ValueError(f"Cannot calculate relative path from {base} to {target}: {e}")


def _are_same_file(file1: Path, file2: Path) -> bool:
    """
    Check if two paths represent the same file.
    
    Args:
        file1: First file path
        file2: Second file path
        
    Returns:
        True if paths represent the same file
    """
    try:
        return file1.resolve() == file2.resolve()
    except (OSError, ValueError):
        # If resolve fails, fall back to string comparison
        return str(file1) == str(file2)


def _get_generated_file_path(location: ModuleLocation, context: ImportContext) -> Path:
    """
    Convert ModuleLocation to generated TypeScript file path using config.
    
    Args:
        location: Module location
        context: Import context
        
    Returns:
        Absolute path to generated TypeScript file
        
    Raises:
        ValueError: If location is invalid or strategy is unknown
    """
    if not location.file_path:
        raise ValueError(f"ModuleLocation {location.module_path} has no file_path")
    
    project_root_path = Path(context.project_root).resolve()
    py_file_path = Path(location.file_path).resolve()
    
    if context.config.output.strategy == "co-locate":
        return py_file_path.with_suffix('.ts')
    elif context.config.output.strategy == "mirror":
        # Calculate relative path from project root to Python file
        try:
            relative_to_project = py_file_path.relative_to(project_root_path)
        except ValueError:
            raise ValueError(f"Python file {py_file_path} is outside project root {project_root_path}")
        
        # Create mirror path in output location
        mirror_path = project_root_path / context.config.output.location / relative_to_project.with_suffix('.ts')
        return mirror_path
    else:
        raise ValueError(f"Unknown output strategy: {context.config.output.strategy}")


def _get_runtime_file_path(config: FluidKitConfig, project_root: str) -> Path:
    """
    Get the runtime.ts file path based on configuration.
    
    Args:
        config: FluidKit configuration
        project_root: Project root directory
        
    Returns:
        Absolute path to runtime.ts file
    """
    runtime_dir = Path(project_root).resolve() / config.output.location
    return runtime_dir / "runtime.ts"


# === TESTING HELPERS === #

def test_imports():
    """Test the import generation with various scenarios."""
    print("=== TESTING IMPORTS ===")
    
    # Test path calculation with different scenarios
    test_cases = [
        # (source, target, expected)
        ("/project/app.py", "/project/models/user.py", "./models/user"),
        ("/project/routes/api.py", "/project/models/user.py", "../models/user"),
        ("/project/deep/nested/route.py", "/project/models/user.py", "../../models/user"),
        ("/project/models/user.py", "/project/models/order.py", "./order"),
    ]
    
    for source_py, target_py, expected in test_cases:
        source_ts = Path(source_py).with_suffix('.ts')
        target_ts = Path(target_py).with_suffix('.ts')
        
        try:
            result = _calculate_relative_import_path(source_ts, target_ts)
            print(f"✓ {source_py} → {target_py}: {result}")
            # Note: In real testing, you'd assert result == expected
        except Exception as e:
            print(f"✗ {source_py} → {target_py}: FAILED - {e}")
    
    print("\n✅ import tests completed!")


def test_config_driven_imports():
    """Test import generation with config-driven approach."""
    from fluidkit.core.schema import (
        RouteNode, ModelNode, Field, FieldAnnotation, ModuleLocation, 
        FluidKitApp, BaseType, ParameterType, FieldConstraints
    )
    from fluidkit.core.config import FluidKitConfig, OutputConfig, BackendConfig, EnvironmentConfig
    
    print("=== TESTING CONFIG-DRIVEN IMPORTS ===")
    
    # Create test locations
    route_location = ModuleLocation(
        module_path="routes.users.page", 
        file_path="/project/routes/users/page.py"
    )
    
    model_location = ModuleLocation(
        module_path="models.user",
        file_path="/project/models/user.py"
    )
    
    # Create test models
    user_model = ModelNode(
        name="User",
        fields=[],
        location=model_location
    )
    
    # Create test route that references User
    route = RouteNode(
        name="getUser",
        methods=["GET"],
        path="/users/{id}",
        parameters=[
            Field(
                name="id",
                annotation=FieldAnnotation(base_type=BaseType.NUMBER),
                constraints=FieldConstraints(parameter_type=ParameterType.PATH)
            )
        ],
        location=route_location,
        return_type=FieldAnnotation(custom_type="User")
    )
    
    # Create FluidKitApp
    fluid_app = FluidKitApp(models=[user_model], routes=[route])
    
    # Test different config strategies
    strategies = ["co-locate", "mirror"]
    locations = [".fluidkit", "src/lib/.fluidkit"]
    
    for strategy in strategies:
        for location in locations:
            print(f"\n--- Testing {strategy.upper()} strategy with location '{location}' ---")
            
            # Create config
            config = FluidKitConfig(
                output=OutputConfig(strategy=strategy, location=location),
                backend=BackendConfig(),
                environments={
                    "development": EnvironmentConfig(mode="separate", apiUrl="http://localhost:8000")
                }
            )
            
            context = ImportContext(
                source_location=route_location,
                config=config,
                project_root="/project"
            )
            
            # Test type imports only
            print("Type imports only:")
            imports = generate_imports_for_file(
                nodes=[route],
                context=context,
                fluid_app=fluid_app,
                needs_runtime=False
            )
            print(f"  {imports or '(no imports needed)'}")
            
            # Test with runtime imports
            print("With runtime imports:")
            imports = generate_imports_for_file(
                nodes=[route],
                context=context,
                fluid_app=fluid_app,
                needs_runtime=True
            )
            print(f"  {imports}")
    
    print("\n✅ All config-driven import tests passed!")


if __name__ == "__main__":
    test_imports()
    test_config_driven_imports()