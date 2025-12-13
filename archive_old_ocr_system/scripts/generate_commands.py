#!/usr/bin/env python3
"""
Generate pipeline commands from a file mapping CSV.

This helps you manage the metadata for files where filenames are unreliable.
"""

import csv
from pathlib import Path

def generate_command(row):
    """Generate a pipeline command for a file."""
    filename = row['filename']
    ep1 = row.get('actual_ep1_title', '')
    ep2 = row.get('actual_ep2_title', '')
    notes = row.get('notes', '')
    
    if not filename:
        return None
    
    # Determine if it's 1 or 2 episodes
    has_ep2 = bool(ep2.strip())
    
    # Build the command
    flags = ['--assume-two'] if has_ep2 else ['--num-episodes 1']
    flags.append('--no-split')  # dry run first
    flags.append('--titles-file titles.txt')
    
    if ep1 or ep2:
        if has_ep2:
            manual = f'--manual-titles "1={ep1},2={ep2}"'
        else:
            manual = f'--manual-titles "1={ep1}"'
        flags.append(manual)
    
    cmd = f'.venv/bin/python pipeline.py "{filename}" {" ".join(flags)}'
    
    return f"""
# {notes}
# File: {filename}
{cmd}
"""

if __name__ == '__main__':
    csv_file = Path('file_mapping.csv')
    
    if not csv_file.exists():
        print("file_mapping.csv not found")
        exit(1)
    
    print("# Generated pipeline commands")
    print("# Copy and paste commands below to test\n")
    
    with open(csv_file) as f:
        reader = csv.DictReader(f)
        for row in reader:
            cmd = generate_command(row)
            if cmd:
                print(cmd)
