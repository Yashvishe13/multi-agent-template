---
name: filesystem
description: Navigate and inspect files and directories. List directory contents, find files by name or pattern, read file contents, check file sizes, and explore project structure. Use when you need to discover what files exist, locate specific files, or read file contents.
---

# Filesystem Navigation Guide

## IMPORTANT: Read This First

1. All commands run in a bash shell. Use standard Unix tools.
2. Always start from the working directory — don't assume paths.
3. For large files, read only what you need (head/tail/grep).
4. Check if a file exists before trying to read it.

## List Directory Contents

```bash
# Current directory
ls

# With details (size, permissions, date)
ls -la

# Specific directory
ls -la path/to/dir

# Recursive listing (tree-like)
find . -type f | head -50

# Only directories
ls -d */

# Only files (no directories)
find . -maxdepth 1 -type f
```

## Find Files

```bash
# Find by exact name
find . -name "config.yaml"

# Find by pattern (wildcard)
find . -name "*.py"
find . -name "*.md"

# Find by pattern, case-insensitive
find . -iname "*.json"

# Find in specific directory
find src/ -name "*.ts"

# Find files modified in last 24 hours
find . -type f -mtime -1

# Find files larger than 1MB
find . -type f -size +1M

# Find and list with details
find . -name "*.py" -exec ls -la {} \;
```

## Read File Contents

```bash
# Read entire file (small files only)
cat filename.txt

# First N lines
head -20 filename.txt

# Last N lines
tail -20 filename.txt

# Specific line range (lines 10-20)
sed -n '10,20p' filename.txt

# Count lines in file
wc -l filename.txt

# Check if file exists
test -f filename.txt && echo "exists" || echo "not found"
```

## Search File Contents

```bash
# Search for text in files
grep -r "search_term" .

# Search in specific file types
grep -r "search_term" --include="*.py" .

# Search with line numbers
grep -rn "search_term" .

# Search case-insensitive
grep -ri "search_term" .

# Search for whole word only
grep -rw "function_name" .

# Show surrounding context (3 lines before/after)
grep -rn -B 3 -A 3 "search_term" .
```

## Project Structure Overview

```bash
# Quick project overview — directory tree (2 levels deep)
find . -maxdepth 2 -type d | sort

# File count by extension
find . -type f | sed 's/.*\.//' | sort | uniq -c | sort -rn | head -20

# Total file count
find . -type f | wc -l

# Show directory sizes
du -sh */

# Show largest files
find . -type f -exec du -h {} + | sort -rh | head -20
```

## Check File Info

```bash
# File type
file filename.txt

# File size (human readable)
du -h filename.txt

# File permissions and ownership
ls -la filename.txt

# Last modification time
stat filename.txt
```

## Quick Reference

| Task | Command |
|------|---------|
| List files | `ls -la` |
| Find by name | `find . -name "*.py"` |
| Read file | `cat file` or `head -20 file` |
| Search in files | `grep -rn "term" .` |
| Check exists | `test -f file && echo yes` |
| Directory tree | `find . -maxdepth 2 -type d` |
| File sizes | `du -sh *` |
| File count | `find . -type f \| wc -l` |
