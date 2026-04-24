#!/bin/bash
# Switch between environment profiles.
#
# Usage:
#   ./env.sh dev     # PaperBroker, keyword analyzer
#   ./env.sh llm     # PaperBroker, LLM analyzer
#   ./env.sh live    # Real broker, real money
#   ./env.sh         # Show current profile

set -e

PROFILES="dev llm live"

if [ -z "$1" ]; then
    if [ -L .env ] || [ -f .env ]; then
        current=$(head -1 .env | grep "^#" | sed 's/^# //' || echo "unknown")
        echo "Current: $current"
        echo ""
    fi
    echo "Available profiles:"
    for p in $PROFILES; do
        desc=$(head -1 ".env.$p" 2>/dev/null | sed 's/^# //' || echo "missing")
        echo "  $p  — $desc"
    done
    echo ""
    echo "Usage: ./env.sh <profile>"
    exit 0
fi

if [ ! -f ".env.$1" ]; then
    echo "Profile '.env.$1' not found."
    echo "Available: $PROFILES"
    exit 1
fi

cp ".env.$1" .env
echo "Switched to: $1"
head -1 ".env.$1" | sed 's/^# /  /'
