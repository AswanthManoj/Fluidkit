# core/config.py
"""
FluidKit Configuration Management

Handles loading, validation, and default generation for fluid.config.json
supporting both full-stack and normal flow configurations.
"""

import json
from pathlib import Path
from dataclasses import dataclass, field
from typing import Dict, Any, Optional, Literal


@dataclass
class OutputConfig:
    """Output configuration for generated files."""
    strategy: Literal["mirror", "co-locate"] = "mirror"
    location: str = ".fluidkit"


@dataclass
class BackendConfig:
    """Backend server configuration."""
    port: int = 8000
    host: str = "localhost"


@dataclass
class EnvironmentConfig:
    """Single environment configuration."""
    mode: Literal["unified", "separate"] = "separate"
    apiUrl: str = "http://localhost:8000"


@dataclass
class FluidKitConfig:
    """Complete FluidKit configuration."""
    framework: Optional[str] = None
    output: OutputConfig = field(default_factory=OutputConfig)
    backend: BackendConfig = field(default_factory=BackendConfig)
    environments: Dict[str, EnvironmentConfig] = field(default_factory=dict)
    
    def __post_init__(self):
        """Initialize default environments if none provided."""
        if not self.environments:
            self.environments = {
                "development": EnvironmentConfig(
                    mode="separate",
                    apiUrl=f"http://{self.backend.host}:{self.backend.port}"
                ),
                "production": EnvironmentConfig(
                    mode="separate", 
                    apiUrl="https://api.example.com"  # User should override this
                )
            }
    
    @property
    def is_fullstack_config(self) -> bool:
        """Check if this is a full-stack configuration (has framework)."""
        return self.framework is not None
    
    @property
    def should_generate_proxy(self) -> bool:
        """Check if proxy files should be generated."""
        if not self.is_fullstack_config:
            return False
        
        # Generate proxy if any environment uses unified mode
        return any(
            env.mode == "unified" 
            for env in self.environments.values()
        )
    
    def get_environment(self, env_name: str = "development") -> EnvironmentConfig:
        """Get configuration for specific environment."""
        return self.environments.get(env_name, self.environments["development"])
    
    def get_runtime_location(self, project_root: str) -> str:
        """Get absolute path for runtime.ts location."""
        return str(Path(project_root) / self.output.location / "runtime.ts")


def load_fluidkit_config(project_root: Optional[str] = None) -> FluidKitConfig:
    """
    Load FluidKit configuration from fluid.config.json or create default.
    
    Args:
        project_root: Project root directory (defaults to current directory)
        
    Returns:
        FluidKitConfig object with loaded or default configuration
    """
    if project_root is None:
        project_root = str(Path.cwd())
    
    config_path = Path(project_root) / "fluid.config.json"
    
    if config_path.exists():
        return _load_config_from_file(config_path)
    else:
        return _create_default_config(project_root, config_path)


def _load_config_from_file(config_path: Path) -> FluidKitConfig:
    """Load configuration from existing file."""
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            config_data = json.load(f)
        
        # Validate and convert to config object
        validated_config = _validate_and_convert_config(config_data)
        
        print(f"✓ Loaded FluidKit config from {config_path}")
        return validated_config
        
    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid JSON in {config_path}: {e}")
    except Exception as e:
        raise ValueError(f"Failed to load config from {config_path}: {e}")


def _create_default_config(project_root: str, config_path: Path) -> FluidKitConfig:
    """Create default configuration and save to file."""
    default_config = FluidKitConfig()
    
    # Save default config to file
    _save_config_to_file(default_config, config_path)
    
    print(f"✓ Created default FluidKit config at {config_path}")
    return default_config


def _validate_and_convert_config(config_data: Dict[str, Any]) -> FluidKitConfig:
    """Validate and convert raw config data to FluidKitConfig object."""
    
    # Extract and validate output config
    output_data = config_data.get("output", {})
    output_config = OutputConfig(
        strategy=output_data.get("strategy", "mirror"),
        location=output_data.get("location", ".fluidkit")
    )
    
    # Validate strategy
    if output_config.strategy not in ["mirror", "co-locate"]:
        raise ValueError(f"Invalid output strategy: {output_config.strategy}")
    
    # Extract and validate backend config
    backend_data = config_data.get("backend", {})
    backend_config = BackendConfig(
        port=backend_data.get("port", 8000),
        host=backend_data.get("host", "localhost")
    )
    
    # Extract and validate environments
    environments_data = config_data.get("environments", {})
    environments = {}
    
    for env_name, env_data in environments_data.items():
        mode = env_data.get("mode", "separate")
        if mode not in ["unified", "separate"]:
            raise ValueError(f"Invalid mode '{mode}' for environment '{env_name}'")
        
        environments[env_name] = EnvironmentConfig(
            mode=mode,
            apiUrl=env_data.get("apiUrl", "http://localhost:8000")
        )
    
    # Create final config
    config = FluidKitConfig(
        framework=config_data.get("framework"),
        output=output_config,
        backend=backend_config,
        environments=environments
    )
    
    return config


def _save_config_to_file(config: FluidKitConfig, config_path: Path):
    """Save configuration to JSON file."""
    config_dict = _config_to_dict(config)
    
    # Ensure directory exists
    config_path.parent.mkdir(parents=True, exist_ok=True)
    
    with open(config_path, 'w', encoding='utf-8') as f:
        json.dump(config_dict, f, indent=2, ensure_ascii=False)


def _config_to_dict(config: FluidKitConfig) -> Dict[str, Any]:
    """Convert FluidKitConfig to dictionary for JSON serialization."""
    config_dict = {
        "output": {
            "strategy": config.output.strategy,
            "location": config.output.location
        },
        "backend": {
            "port": config.backend.port,
            "host": config.backend.host
        },
        "environments": {}
    }
    
    # Add framework if present (full-stack config)
    if config.framework:
        config_dict["framework"] = config.framework
    
    # Add environments
    for env_name, env_config in config.environments.items():
        config_dict["environments"][env_name] = {
            "mode": env_config.mode,
            "apiUrl": env_config.apiUrl
        }
    
    return config_dict


def update_config_framework(
    project_root: str, 
    framework: str,
    framework_defaults: Optional[Dict[str, Any]] = None
) -> FluidKitConfig:
    """
    Update configuration to add framework and apply framework-specific defaults.
    
    Used by CLI when creating full-stack projects.
    """
    config = load_fluidkit_config(project_root)
    config.framework = framework
    
    # Apply framework-specific defaults if provided
    if framework_defaults:
        if "output" in framework_defaults:
            if "location" in framework_defaults["output"]:
                config.output.location = framework_defaults["output"]["location"]
        
        if "environments" in framework_defaults:
            for env_name, env_defaults in framework_defaults["environments"].items():
                if env_name in config.environments:
                    if "mode" in env_defaults:
                        config.environments[env_name].mode = env_defaults["mode"]
                    if "apiUrl" in env_defaults:
                        config.environments[env_name].apiUrl = env_defaults["apiUrl"]
    
    # Save updated config
    config_path = Path(project_root) / "fluid.config.json"
    _save_config_to_file(config, config_path)
    
    return config


# === TESTING HELPERS === #

def test_config_management():
    """Test configuration loading and validation."""
    import tempfile
    import shutil
    
    print("=== TESTING CONFIG MANAGEMENT ===")
    
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        
        # Test 1: Create default config
        print("\n1. Testing default config creation:")
        config = load_fluidkit_config(str(temp_path))
        print(f"   Framework: {config.framework}")
        print(f"   Strategy: {config.output.strategy}")
        print(f"   Location: {config.output.location}")
        print(f"   Is fullstack: {config.is_fullstack_config}")
        print(f"   Should generate proxy: {config.should_generate_proxy}")
        
        # Test 2: Load existing config
        print("\n2. Testing config loading:")
        config2 = load_fluidkit_config(str(temp_path))
        assert config2.output.strategy == config.output.strategy
        print("   ✓ Config loaded successfully")
        
        # Test 3: Full-stack config update
        print("\n3. Testing framework update:")
        fullstack_config = update_config_framework(
            str(temp_path), 
            "sveltekit",
            {
                "output": {"location": "src/lib/.fluidkit"},
                "environments": {
                    "development": {"mode": "unified", "apiUrl": "/api"}
                }
            }
        )
        print(f"   Framework: {fullstack_config.framework}")
        print(f"   Location: {fullstack_config.output.location}")
        print(f"   Dev mode: {fullstack_config.environments['development'].mode}")
        print(f"   Is fullstack: {fullstack_config.is_fullstack_config}")
        print(f"   Should generate proxy: {fullstack_config.should_generate_proxy}")
        
        # Test 4: Invalid config handling
        print("\n4. Testing validation:")
        invalid_config_path = temp_path / "invalid.config.json"
        with open(invalid_config_path, 'w') as f:
            json.dump({"output": {"strategy": "invalid"}}, f)
        
        try:
            _load_config_from_file(invalid_config_path)
            assert False, "Should have failed validation"
        except ValueError as e:
            print(f"   ✓ Validation caught error: {e}")
    
    print("\n✅ All config management tests passed!")


if __name__ == "__main__":
    test_config_management()
