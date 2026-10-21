#!/usr/bin/env python
import sys
import subprocess
import os

def run_tests():
    os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    
    result = subprocess.run([
        sys.executable, "-m", "pytest", 
        "tests/", 
        "-v", 
        "--tb=short",
        "-x"
    ], capture_output=True, text=True)
    
    print(result.stdout)
    if result.stderr:
        print(result.stderr, file=sys.stderr)
    
    return result.returncode

if __name__ == "__main__":
    sys.exit(run_tests())