# fluidkit/cli/commands/create.py
"""
FluidKit Create Command - Fullstack project creation
"""

import os
import json
from pathlib import Path

from ..utils import (
    ensure_nodejs, run_command, create_file, 
    check_command_exists
)


class CreateCommand:
    """Handle fullstack project creation."""
    
    @staticmethod
    def add_arguments(parser):
        """Add create command arguments."""
        parser.add_argument(
            'project_name', 
            help='Name of the project to create'
        )
    
    @staticmethod
    def execute(args):
        """Execute create command."""
        project_name = args.project_name
        
        print(f"🚀 Creating fullstack project: {project_name}")
        print()
        
        # Validate project name
        if not CreateCommand._is_valid_project_name(project_name):
            raise ValueError(f"Invalid project name: {project_name}")
        
        # Check if directory already exists
        if Path(project_name).exists():
            raise ValueError(f"Directory {project_name} already exists")
        
        # Step 1: Check dependencies
        CreateCommand._check_dependencies()
        
        # Step 2: Create SvelteKit project
        CreateCommand._create_sveltekit_project(project_name)
        
        # Step 3: Setup Python environment
        CreateCommand._setup_python_environment(project_name)
        
        # Step 4: Configure FluidKit basics
        CreateCommand._configure_fluidkit_basics(project_name)
        
        # Step 5: Show success message
        CreateCommand._show_success_message(project_name)
    
    @staticmethod
    def _is_valid_project_name(name: str) -> bool:
        """Validate project name."""
        if not name or name.startswith('-') or name.startswith('.'):
            return False
        
        # Check for invalid characters
        invalid_chars = set('<>:"/\\|?*')
        if any(char in invalid_chars for char in name):
            return False
        
        return True
    
    @staticmethod
    def _check_dependencies():
        """Check required dependencies."""
        print("📋 Checking dependencies...")
        
        # Check Node.js
        if not ensure_nodejs():
            raise RuntimeError("Node.js is required for SvelteKit projects")
        
        # Check uv (should be available since it's bundled with fluidkit)
        if not check_command_exists("uv"):
            raise RuntimeError("uv not found (should be bundled with FluidKit)")
        
        print("  ✅ All dependencies available")
    
    @staticmethod
    def _create_sveltekit_project(project_name: str):
        """Create SvelteKit project using npx sv create (minimal template)."""
        print("🎨 Creating SvelteKit project...")
        
        # Always use minimal template
        command = ["npx", "sv", "create", project_name, "--template", "minimal"]
        
        print(f"  📦 Running: {' '.join(command)}")
        
        if not run_command(command):
            raise RuntimeError("Failed to create SvelteKit project")
        
        # Verify project was created
        project_path = Path(project_name)
        if not project_path.exists():
            raise RuntimeError(f"Project directory {project_name} was not created")
        
        print("  ✅ SvelteKit project created")
    
    @staticmethod
    def _setup_python_environment(project_name: str):
        """Setup Python environment using uv (simple approach)."""
        print("🐍 Setting up Python environment...")
        
        project_path = Path(project_name).resolve()
        
        # Simple uv init - let it use whatever Python is available
        if not run_command(["uv", "init"], cwd=project_path):
            raise RuntimeError("Failed to initialize uv project")
        
        # Add FluidKit dependency
        if not run_command(["uv", "add", "fluidkit"], cwd=project_path):
            current_dir = Path.cwd().resolve()
            if "fluidkit" in str(current_dir).lower():
                raise RuntimeError(
                    "Failed to add FluidKit dependency. "
                    "You appear to be inside the FluidKit workspace. "
                    "Please run this command from outside the FluidKit directory."
                )
            else:
                raise RuntimeError("Failed to add FluidKit dependency")
        
        print("  ✅ Python environment ready")
    
    @staticmethod
    def _configure_fluidkit_basics(project_name: str):
        """Configure basic FluidKit setup (non-destructive, no structure assumptions)."""
        print("⚡ Configuring FluidKit basics...")
        
        project_path = Path(project_name)
        
        # Create fluid.config.json (only if it doesn't exist)
        CreateCommand._create_fluid_config(project_path)
        
        # Add basic npm scripts (non-destructive)
        CreateCommand._add_npm_scripts(project_path)
        
        print("  ✅ FluidKit basics configured")
    
    @staticmethod
    def _create_fluid_config(project_path: Path):
        """Create fluid.config.json (only if it doesn't exist)."""
        config_path = project_path / "fluid.config.json"
        
        if config_path.exists():
            print("  ⚠️  fluid.config.json already exists, skipping")
            return
        
        config = {
            "framework": "sveltekit",
            "output": {
                "strategy": "mirror",
                "location": "src/lib/.fluidkit"
            },
            "backend": {
                "port": 8000,
                "host": "localhost"
            },
            "environments": {
                "development": {
                    "mode": "unified",
                    "apiUrl": "/api"
                },
                "production": {
                    "mode": "separate",
                    "apiUrl": "https://api.example.com"
                }
            }
        }
        
        create_file(config_path, json.dumps(config, indent=2))
        print("  ✅ Created fluid.config.json")
    
    @staticmethod
    def _add_npm_scripts(project_path: Path):
        """Add basic FluidKit scripts to package.json (non-destructive)."""
        package_json_path = project_path / "package.json"
        
        if not package_json_path.exists():
            print("  ⚠️  package.json not found, skipping script addition")
            return
        
        # Read existing package.json
        with open(package_json_path, 'r', encoding='utf-8') as f:
            package_data = json.load(f)
        
        # Add minimal scripts (no assumptions about backend structure)
        scripts = package_data.setdefault("scripts", {})
        
        # Only add a generate script for now
        new_scripts = {
            "fluidkit:generate": "uv run python -c 'from fluidkit.core.integrator import integrate; print(\"TODO: Setup your FastAPI app first\")'"
        }
        
        added_scripts = []
        for script_name, script_command in new_scripts.items():
            if script_name not in scripts:
                scripts[script_name] = script_command
                added_scripts.append(script_name)
        
        # Write back package.json
        with open(package_json_path, 'w', encoding='utf-8') as f:
            json.dump(package_data, f, indent=2, ensure_ascii=False)
        
        if added_scripts:
            print(f"  ✅ Added npm scripts: {', '.join(added_scripts)}")
        else:
            print("  ℹ️  All npm scripts already exist")
    
    @staticmethod
    def _show_success_message(project_name: str):
        """Show final success message."""
        print()
        print("🎉 FluidKit project created successfully!")
        print()
        print("🚀 Next steps:")
        print(f"   cd {project_name}")
        print("   npm install")
        print()
        print("💡 To run your app:")
        print("   Terminal 1 (Frontend):")
        print("     npm run dev")
        print()
        print("   Terminal 2 (Backend):")
        print("     uv run uvicorn main:app --reload")
        print()
        print("   Then visit: http://localhost:5173")
        