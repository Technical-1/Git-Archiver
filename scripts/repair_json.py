#!/usr/bin/env python3
"""
Repair corrupted cloned_repos.json file
This script attempts to extract all valid repository entries from a corrupted JSON file
and creates a new, valid JSON file with the salvaged data.
"""

import os
import json
import re

CORRUPT_FILE = "cloned_repos.json"
OUTPUT_FILE = "cloned_repos_fixed.json"

def repair_json():
    """Repair corrupted JSON file by extracting valid entries"""
    print(f"Reading corrupted file: {CORRUPT_FILE}")
    
    # Read the entire file as text
    try:
        with open(CORRUPT_FILE, 'r', encoding='utf-8') as file:
            content = file.read()
    except Exception as e:
        print(f"Error reading file: {e}")
        return False
    
    # Pattern to match repository entries
    pattern = r'"(https://github\.com/[^"]+\.git)"\s*:\s*{([^{}]|{[^{}]*})*?}'
    matches = re.findall(pattern, content)
    
    if not matches:
        print("No repository entries found in the corrupted file")
        return False
    
    print(f"Found {len(matches)} potential repository entries")
    
    # Create a new dictionary to store valid entries
    repos = {}
    
    # Process each match
    for match in matches:
        try:
            repo_url = match[0]
            repo_data_str = "{" + match[1] + "}"
            # Try to parse the JSON for this entry
            try:
                repo_data = json.loads(repo_data_str)
                repos[repo_url] = repo_data
            except json.JSONDecodeError:
                # If that fails, create a minimal valid entry
                print(f"Creating basic entry for: {repo_url}")
                repos[repo_url] = {
                    "last_cloned": "",
                    "last_updated": "",
                    "local_path": f"data/{repo_url.split('/')[-1]}",
                    "online_description": "",
                    "status": "pending"
                }
        except Exception as e:
            print(f"Error processing {repo_url}: {e}")
    
    print(f"Successfully extracted {len(repos)} repository entries")
    
    # Write the repaired data to a new file
    try:
        with open(OUTPUT_FILE, 'w', encoding='utf-8') as file:
            json.dump(repos, file, indent=2)
        print(f"Repaired JSON written to: {OUTPUT_FILE}")
        return True
    except Exception as e:
        print(f"Error writing repaired file: {e}")
        return False

if __name__ == "__main__":
    success = repair_json()
    if success:
        print("JSON repair completed successfully")
    else:
        print("JSON repair failed") 