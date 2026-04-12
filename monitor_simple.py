#!/usr/bin/env python3
"""Real-time monitoring dashboard for AI Research System"""
import requests
import time
import os
import sys
from datetime import datetime

API_KEY = "kV7jQ_8mX2pL9wN4sR6tU1yZ3aB5cD7eF9gH"
BASE_URL = "http://127.0.0.1:8000"
HEADERS = {"api-key": API_KEY, "Content-Type": "application/json"}

def clear_screen():
    os.system('cls' if os.name == 'nt' else 'clear')

def get_stats():
    try:
        resp = requests.get(f'{BASE_URL}/stats', headers=HEADERS, timeout=5)
        if resp.status_code == 200:
            return resp.json()
    except:
        pass
    return None

def get_health():
    try:
        resp = requests.get(f'{BASE_URL}/health', timeout=5)
        if resp.status_code == 200:
            return resp.json()
    except:
        pass
    return None

def display_dashboard():
    while True:
        clear_screen()

        print("=" * 70)
        print("  AI RESEARCH SYSTEM - REAL-TIME MONITOR")
        print("=" * 70)
        print(f"Updated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print()

        # Health Check
        health = get_health()
        if health:
            print("[SERVER STATUS]")
            print(f"  Status: {health.get('status', 'unknown').upper()}")
            print(f"  Workers Alive: {health.get('workers_alive', 0)}/3")
            print(f"  Queue Depth: {health.get('queue_depth', 0)} items")
            print()
        else:
            print("[ERROR] Cannot connect to server on port 8000")
            print("Starting in 3 seconds...")
            time.sleep(3)
            continue

        # Stats
        stats = get_stats()
        if stats:
            print("[KNOWLEDGE BASE]")
            knowledge = stats.get('knowledge', {})
            print(f"  Total Entries: {knowledge.get('total_entries', 0)}")
            print(f"  Total Nodes: {knowledge.get('total_nodes', 0)}")
            print(f"  Total Links: {knowledge.get('total_links', 0)}")
            print(f"  Avg Confidence: {knowledge.get('avg_confidence', 0.0):.2f}")
            print()

            print("[RESEARCH JOBS]")
            jobs = stats.get('jobs', {})
            print(f"  Pending:   {jobs.get('pending', 0):2d}")
            print(f"  Running:   {jobs.get('running', 0):2d}")
            print(f"  Completed: {jobs.get('completed', 0):2d}")
            print(f"  Failed:    {jobs.get('failed', 0):2d}")
            print(f"  Total:     {jobs.get('total', 0):2d}")
            print()

        print("[INSTRUCTIONS]")
        print("  POST /research/start - Start new investigation")
        print("  GET  /health        - Server health check")
        print("  GET  /stats         - Full statistics (requires api-key)")
        print()
        print("  Press Ctrl+C to exit, auto-refresh every 5 seconds...")
        print("=" * 70)

        try:
            time.sleep(5)
        except KeyboardInterrupt:
            print("\n\nMonitoring stopped.")
            break

if __name__ == "__main__":
    try:
        display_dashboard()
    except KeyboardInterrupt:
        print("\n\nMonitor terminated.")
        sys.exit(0)
