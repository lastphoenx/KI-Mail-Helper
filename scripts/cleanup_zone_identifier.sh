#!/bin/bash

# Script to delete all *Zone.Identifier files recursively

PROJECT_DIR="/home/thomas/projects/KI-Mail-Helper"

if [ ! -d "$PROJECT_DIR" ]; then
    echo "Error: Directory $PROJECT_DIR does not exist"
    exit 1
fi

echo "Searching for *Zone.Identifier files in $PROJECT_DIR..."

# Find and delete all *Zone.Identifier files
find "$PROJECT_DIR" -type f -name "*Zone.Identifier" -delete -print

echo "Cleanup complete!"
