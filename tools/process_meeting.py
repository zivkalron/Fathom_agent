#!/usr/bin/env python3
"""
Master orchestration script for meeting automation.

Runs the complete WAT pipeline:
1. Fetch transcript from Fathom
2. Summarize with Gemini
3. Log to Airtable

Usage:
    python process_meeting.py <recording_id>

Example:
    python process_meeting.py abc123def456

Options:
    --keep-files    Keep intermediate JSON files after completion
    --skip-airtable Skip Airtable logging (useful for testing)

Environment Variables:
    See .env.example for all required API keys
"""

import sys
import subprocess
import argparse
from pathlib import Path
from datetime import datetime


class ProcessingError(Exception):
    """Custom exception for processing errors."""
    pass


def print_header(text: str) -> None:
    """Print a formatted header."""
    print("\n" + "="*80)
    print(f" {text}")
    print("="*80 + "\n")


def print_step(step_num: int, total: int, description: str) -> None:
    """Print a formatted step header."""
    print(f"\n[STEP {step_num}/{total}] {description}")
    print("-" * 60)


def run_tool(script_name: str, args: list) -> int:
    """
    Run a tool script and return the exit code.

    Args:
        script_name: Name of the Python script to run
        args: List of arguments to pass to the script

    Returns:
        Exit code from the script

    Raises:
        ProcessingError: If the script fails
    """
    script_path = Path(__file__).parent / script_name
    cmd = ["python3", str(script_path)] + args

    print(f"Running: {' '.join(cmd)}\n")

    result = subprocess.run(cmd, capture_output=False)

    if result.returncode != 0:
        raise ProcessingError(f"{script_name} failed with exit code {result.returncode}")

    return result.returncode


def cleanup_files(recording_id: str) -> None:
    """
    Clean up intermediate files.

    Args:
        recording_id: The recording ID
    """
    transcript_file = Path(".tmp") / f"transcript_{recording_id}.json"
    summary_file = Path(".tmp") / f"summary_{recording_id}.json"

    files_removed = []

    if transcript_file.exists():
        transcript_file.unlink()
        files_removed.append(str(transcript_file))

    if summary_file.exists():
        summary_file.unlink()
        files_removed.append(str(summary_file))

    if files_removed:
        print("\n✓ Cleaned up intermediate files:")
        for file in files_removed:
            print(f"  - {file}")


def main():
    """Main execution function."""
    # Parse arguments
    parser = argparse.ArgumentParser(
        description="Process Fathom meeting: fetch, summarize, and log to Airtable"
    )
    parser.add_argument(
        "recording_id",
        help="Fathom recording ID"
    )
    parser.add_argument(
        "--keep-files",
        action="store_true",
        help="Keep intermediate JSON files after completion"
    )
    parser.add_argument(
        "--skip-airtable",
        action="store_true",
        help="Skip Airtable logging (useful for testing)"
    )

    args = parser.parse_args()
    recording_id = args.recording_id

    # Display start message
    print_header("MEETING AUTOMATION PIPELINE")
    print(f"Recording ID: {recording_id}")
    print(f"Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    start_time = datetime.now()

    try:
        # =====================================================================
        # STEP 1: Fetch Transcript
        # =====================================================================
        print_step(1, 3, "Fetching transcript from Fathom")

        run_tool("fetch_fathom_transcript.py", [recording_id])

        transcript_file = Path(".tmp") / f"transcript_{recording_id}.json"
        if not transcript_file.exists():
            raise ProcessingError("Transcript file was not created")

        # =====================================================================
        # STEP 2: Generate Summary
        # =====================================================================
        print_step(2, 3, "Generating AI summary with Gemini")

        run_tool("summarize_with_gemini.py", [str(transcript_file)])

        summary_file = Path(".tmp") / f"summary_{recording_id}.json"
        if not summary_file.exists():
            raise ProcessingError("Summary file was not created")

        # =====================================================================
        # STEP 3: Log to Airtable
        # =====================================================================
        if not args.skip_airtable:
            print_step(3, 3, "Logging to Airtable")

            run_tool("log_to_airtable.py", [str(summary_file), str(transcript_file)])
        else:
            print_step(3, 3, "Skipping Airtable (--skip-airtable flag set)")
            print(f"Summary available at: {summary_file}")

        # =====================================================================
        # CLEANUP
        # =====================================================================
        if not args.keep_files:
            cleanup_files(recording_id)
        else:
            print("\n✓ Keeping intermediate files (--keep-files flag set)")
            print(f"  - {transcript_file}")
            print(f"  - {summary_file}")

        # =====================================================================
        # SUCCESS
        # =====================================================================
        end_time = datetime.now()
        duration = (end_time - start_time).total_seconds()

        print_header("PIPELINE COMPLETE")
        print(f"✓ Recording {recording_id} processed successfully")
        print(f"✓ Total duration: {duration:.1f} seconds")

        if not args.skip_airtable:
            print("\n✓ Meeting and tasks logged to Airtable")
            print("  Check your Airtable base for the new records")
        else:
            print(f"\n✓ Summary saved to: {summary_file}")
            print("  Run log_to_airtable.py manually when ready")

        print("\n" + "="*80)

        return 0

    except ProcessingError as e:
        print(f"\n✗ PIPELINE FAILED: {e}", file=sys.stderr)
        print("\nPartial results may be available in .tmp/", file=sys.stderr)
        return 1

    except KeyboardInterrupt:
        print("\n\n✗ Pipeline interrupted by user", file=sys.stderr)
        return 130

    except Exception as e:
        print(f"\n✗ UNEXPECTED ERROR: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
