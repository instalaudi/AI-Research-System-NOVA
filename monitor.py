#!/usr/bin/env python3
"""
Real-time monitoring script for AI Research System
Shows progress of research tasks and knowledge growth
"""

import asyncio
import sys
import os
from datetime import datetime, timedelta
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent / "backend"))

from core.database import SessionLocal, ResearchJob, KnowledgeEntry, KnowledgeNode
from sqlalchemy import func

def clear_screen():
    """Clear terminal screen"""
    os.system('cls' if os.name == 'nt' else 'clear')

def format_time_ago(dt):
    """Format timedelta as human-readable"""
    if not dt:
        return "N/A"
    diff = datetime.utcnow() - dt
    if diff.total_seconds() < 60:
        return f"{int(diff.total_seconds())}s ago"
    elif diff.total_seconds() < 3600:
        return f"{int(diff.total_seconds() // 60)}m ago"
    else:
        return f"{int(diff.total_seconds() // 3600)}h ago"

def get_stats():
    """Fetch current statistics from database"""
    db = SessionLocal()
    try:
        # Job statistics
        total_jobs = db.query(ResearchJob).count()
        pending_jobs = db.query(ResearchJob).filter(ResearchJob.status == "pending").count()
        running_jobs = db.query(ResearchJob).filter(ResearchJob.status == "running").count()
        completed_jobs = db.query(ResearchJob).filter(ResearchJob.status == "completed").count()
        failed_jobs = db.query(ResearchJob).filter(ResearchJob.status == "failed").count()

        # Knowledge statistics
        total_entries = db.query(KnowledgeEntry).count()
        total_nodes = db.query(KnowledgeNode).count()
        avg_confidence = db.query(func.avg(KnowledgeEntry.confidence_score)).scalar() or 0

        # Recent jobs (last 10)
        recent_jobs = db.query(ResearchJob).\
            order_by(ResearchJob.id.desc()).limit(10).all()

        # Jobs created in last hour
        one_hour_ago = datetime.utcnow() - timedelta(hours=1)
        jobs_last_hour = db.query(ResearchJob).\
            filter(ResearchJob.last_heartbeat > one_hour_ago).count()

        return {
            'total_jobs': total_jobs,
            'pending': pending_jobs,
            'running': running_jobs,
            'completed': completed_jobs,
            'failed': failed_jobs,
            'total_entries': total_entries,
            'total_nodes': total_nodes,
            'avg_confidence': round(avg_confidence, 2),
            'recent_jobs': recent_jobs,
            'jobs_last_hour': jobs_last_hour
        }
    finally:
        db.close()

def display_dashboard(stats):
    """Display real-time dashboard"""
    clear_screen()

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print("=" * 80)
    print(f"AI RESEARCH SYSTEM - MONITORING DASHBOARD | {now}")
    print("=" * 80)
    print()

    # Job Summary
    print("RESEARCH JOBS STATUS")
    print("-" * 80)
    print(f"  Total Jobs:     {stats['total_jobs']:3d}")
    print(f"  Pending:        {stats['pending']:3d}  ⏳")
    print(f"  Running:        {stats['running']:3d}  ▶️")
    print(f"  Completed:      {stats['completed']:3d}  ✅")
    print(f"  Failed:         {stats['failed']:3d}  ❌")
    print(f"  Jobs (last 1h): {stats['jobs_last_hour']:3d}  📊")
    print()

    # Knowledge Statistics
    print("KNOWLEDGE BASE GROWTH")
    print("-" * 80)
    print(f"  Total Entries:  {stats['total_entries']:3d}  📚")
    print(f"  Knowledge Nodes:{stats['total_nodes']:3d}  🔗")
    print(f"  Avg Confidence: {stats['avg_confidence']:5.2f}/1.0  ⭐")
    print()

    # Recent Jobs
    print("RECENT JOBS (Last 10)")
    print("-" * 80)
    print(f"{'ID':>4} {'Status':<12} {'Stage':<20} {'Topic':<30} {'Updated':<10}")
    print("-" * 80)

    for job in stats['recent_jobs']:
        status_icon = {
            'pending': '⏳',
            'running': '▶️',
            'completed': '✅',
            'failed': '❌'
        }.get(job.status, '❓')

        topic_short = job.topic[:28] if len(job.topic) > 28 else job.topic
        updated = format_time_ago(job.last_heartbeat)

        print(f"{job.id:>4} {status_icon} {job.status:<10} {job.stage:<20} {topic_short:<30} {updated:<10}")

    print()
    print("=" * 80)
    print("Press Ctrl+C to exit. Updates every 5 seconds...")
    print("=" * 80)

async def monitor_loop():
    """Continuous monitoring loop"""
    try:
        while True:
            stats = get_stats()
            display_dashboard(stats)

            # Wait before next update
            await asyncio.sleep(5)
    except (KeyboardInterrupt, asyncio.CancelledError):
        pass

def main():
    """Entry point"""
    print("[Monitor] Starting Real-time Dashboard...")
    print("[Monitor] Connecting to database...")

    try:
        # Test database connection
        db = SessionLocal()
        db.close()
        print("[Monitor] Database connected ✓")
        print("[Monitor] Initializing dashboard...\n")
    except Exception as e:
        print(f"[ERROR] Cannot connect to database: {e}")
        sys.exit(1)

    # Start monitoring
    try:
        asyncio.run(monitor_loop())
    except KeyboardInterrupt:
        pass

    print("\n[Monitor] Stopped by user. Goodbye! 👋")

if __name__ == "__main__":
    main()
