#!/usr/bin/env python3
"""
Create a fresh, valid cloned_repos.json file with sample repositories
to start with a clean slate for the application.
"""

import json
import os

# Sample repository data
SAMPLE_REPOS = {
    "https://github.com/microsoft/vscode.git": {
        "last_cloned": "",
        "last_updated": "",
        "local_path": "data/vscode.git",
        "online_description": "Visual Studio Code",
        "status": "pending"
    },
    "https://github.com/python/cpython.git": {
        "last_cloned": "",
        "last_updated": "",
        "local_path": "data/cpython.git",
        "online_description": "The Python programming language",
        "status": "pending"
    },
    "https://github.com/pytorch/pytorch.git": {
        "last_cloned": "",
        "last_updated": "",
        "local_path": "data/pytorch.git",
        "online_description": "PyTorch: Tensors and Dynamic neural networks in Python",
        "status": "pending"
    }
}

def create_fresh_json():
    """Create a fresh, valid JSON file with sample repository data"""
    # Output file
    json_path = "cloned_repos.json"
    
    print(f"Creating fresh {json_path} file with {len(SAMPLE_REPOS)} sample repositories")
    
    # Create data directory if it doesn't exist
    os.makedirs("data", exist_ok=True)
    
    # Write the JSON file
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(SAMPLE_REPOS, f, indent=2, ensure_ascii=False)
    
    # Verify the file was created successfully
    file_size = os.path.getsize(json_path)
    print(f"Successfully created {json_path} ({file_size} bytes)")
    
    # Validate the JSON by reading it back
    try:
        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        print(f"Validation successful: read {len(data)} repositories")
    except Exception as e:
        print(f"ERROR: Failed to validate JSON file: {e}")

if __name__ == "__main__":
    create_fresh_json() 