#!/usr/bin/env python3
"""Commit pending changes to git."""

import subprocess
import sys

def run_command(cmd, check=True):
    """Run a command and return the result."""
    print(f"Running: {' '.join(cmd)}")
    try:
        result = subprocess.run(cmd, check=check, capture_output=True, text=True, cwd='/home/dad/Projects/sentinel-desktop')
        if result.stdout:
            print(result.stdout)
        if result.stderr:
            print(result.stderr, file=sys.stderr)
        return result
    except subprocess.CalledProcessError as e:
        print(f"Command failed with exit code {e.returncode}", file=sys.stderr)
        if e.stdout:
            print("STDOUT:", e.stdout)
        if e.stderr:
            print("STDERR:", e.stderr)
        raise

def main():
    """Commit all pending changes."""
    # Stage all changes
    print("Staging all changes...")
    run_command(['git', 'add', '-A'])

    # Create commit message
    commit_msg = """feat: add v3.1.0 features - API enhancements, GUI improvements, and testing infrastructure

- Add comprehensive test runner scripts (run_tests.sh, run_tests_no_timeout.sh)
- Add application verification script (verify_app.py)
- Enhance API server with new endpoints and functionality
- Update core modules: app_profiles, command_palette, forensic_log, llm_client
- Improve plugin loader, screenshot handling, and tool schemas
- Enhance UI Automation actions and GUI components
- Update project configuration and documentation

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>
"""

    # Commit
    print("Creating commit...")
    run_command(['git', 'commit', '-m', commit_msg])

    # Show status
    print("\nGit status after commit:")
    run_command(['git', 'status'])

    print("\nLatest commit:")
    run_command(['git', 'log', '-1', '--stat'])

    print("\n✅ Changes committed successfully!")

if __name__ == '__main__':
    main()
