# fluidkit/cli/main.py
"""
FluidKit CLI - Clean and extensible command interface
"""

import sys
import argparse
from pathlib import Path

from .commands.create import CreateCommand


def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        prog='fluidkit',
        description='FluidKit - Fullstack Python framework with TypeScript generation'
    )
    
    subparsers = parser.add_subparsers(dest='command', help='Available commands')
    
    # Create command
    create_parser = subparsers.add_parser('create', help='Create a new fullstack project')
    CreateCommand.add_arguments(create_parser)
    
    # Parse arguments
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        return
    
    try:
        if args.command == 'create':
            CreateCommand.execute(args)
        else:
            print(f"Unknown command: {args.command}")
            sys.exit(1)
            
    except KeyboardInterrupt:
        print("\n❌ Operation cancelled")
        sys.exit(1)
    except Exception as e:
        print(f"❌ Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
