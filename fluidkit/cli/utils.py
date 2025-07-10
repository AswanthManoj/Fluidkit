# fluidkit/cli/utils.py
"""
Shared utilities for FluidKit CLI
"""

import shutil
import subprocess
import platform
import sys
from pathlib import Path


def check_command_exists(command: str) -> bool:
    """Check if a command exists in PATH."""
    return shutil.which(command) is not None


def get_command_version(command: str) -> str:
    """Get version of a command safely."""
    try:
        # Try with shell=True on Windows for better compatibility
        shell = platform.system().lower() == "windows"
        
        result = subprocess.run(
            [command, "--version"], 
            capture_output=True, 
            text=True, 
            timeout=10,
            shell=shell
        )
        if result.returncode == 0:
            version = result.stdout.strip().split()[0]
            return version.lstrip('v')
        return "unknown"
    except (subprocess.TimeoutExpired, subprocess.SubprocessError, FileNotFoundError):
        return "unknown"


def run_command(command: list, cwd: Path = None, timeout: int = 300) -> bool:
    """Run a command and return success status with proper error handling."""
    try:
        # Use shell=True on Windows for better npm/npx compatibility
        shell = platform.system().lower() == "windows"
        
        result = subprocess.run(
            command,
            cwd=cwd,
            stdin=sys.stdin,
            stdout=sys.stdout,
            stderr=sys.stderr,
            timeout=timeout,
            shell=shell
        )
        return result.returncode == 0
    except subprocess.TimeoutExpired:
        print(f"❌ Command timed out: {' '.join(command)}")
        return False
    except KeyboardInterrupt:
        print("\n❌ Command cancelled")
        return False
    except FileNotFoundError as e:
        print(f"❌ Command not found: {' '.join(command)}")
        print(f"   Error: {e}")
        return False
    except subprocess.SubprocessError as e:
        print(f"❌ Command failed: {' '.join(command)}")
        print(f"   Error: {e}")
        return False


def confirm(message: str) -> bool:
    """Get user confirmation."""
    while True:
        response = input(f"{message} [y/N]: ").strip().lower()
        if response in ['y', 'yes']:
            return True
        elif response in ['n', 'no', '']:
            return False
        else:
            print("Please enter 'y' for yes or 'n' for no.")


def ensure_nodejs():
    """Ensure Node.js is available with better diagnostics."""
    print("  🔍 Checking Node.js installation...")
    
    # Check individual commands
    has_node = check_command_exists("node")
    has_npm = check_command_exists("npm")
    has_npx = check_command_exists("npx")
    
    print(f"     node: {'✅' if has_node else '❌'}")
    print(f"     npm:  {'✅' if has_npm else '❌'}")
    print(f"     npx:  {'✅' if has_npx else '❌'}")
    
    if not (has_node and has_npm and has_npx):
        print("  ❌ Node.js/npm/npx not fully available")
        print("  💡 Please install Node.js from: https://nodejs.org/")
        print("     Then restart your terminal and try again.")
        return False
    
    # Get versions with better error handling
    node_version = get_command_version("node")
    npm_version = get_command_version("npm")
    
    if node_version == "unknown" or npm_version == "unknown":
        print("  ⚠️  Node.js detected but version check failed")
        print("     This might indicate PATH or permission issues")
        
        # Test a simple command
        print("  🔧 Testing npm command...")
        if test_npm_command():
            print("     ✅ npm command works")
        else:
            print("     ❌ npm command failed")
            print("     💡 Try restarting your terminal or reinstalling Node.js")
            return False
    
    print(f"  ✅ Node.js {node_version} and npm {npm_version}")
    return True


def test_npm_command() -> bool:
    """Test if npm command actually works."""
    try:
        shell = platform.system().lower() == "windows"
        result = subprocess.run(
            ["npm", "--version"], 
            capture_output=True, 
            text=True, 
            timeout=10,
            shell=shell
        )
        return result.returncode == 0
    except:
        return False


def create_file(file_path: Path, content: str):
    """Create a file with content, ensuring directory exists."""
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_text(content, encoding='utf-8')


def update_json_file(file_path: Path, updates: dict):
    """Update a JSON file with new values."""
    import json
    
    if file_path.exists():
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
    else:
        data = {}
    
    # Deep merge updates
    def merge_dict(base, updates):
        for key, value in updates.items():
            if key in base and isinstance(base[key], dict) and isinstance(value, dict):
                merge_dict(base[key], value)
            else:
                base[key] = value
    
    merge_dict(data, updates)
    
    with open(file_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

def file_exists_with_content(file_path: Path, content_check: str = None) -> bool:
    """Check if file exists and optionally contains specific content."""
    if not file_path.exists():
        return False
    
    if content_check:
        try:
            return content_check in file_path.read_text()
        except Exception:
            return False
    
    return True
