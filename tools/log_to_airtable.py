#!/usr/bin/env python3
"""
Log meeting summary to Airtable with relational structure.

This tool handles the complete Airtable logging workflow:
1. Create a meeting record in the Meetings table
2. Create individual task records in the Tasks table
3. Link tasks to the parent meeting record

Uses pyairtable for deterministic API operations.

Usage:
    python log_to_airtable.py <summary_file>

Example:
    python log_to_airtable.py .tmp/summary_abc123.json

Environment Variables:
    AIRTABLE_API_KEY: Your Airtable Personal Access Token (required)
    AIRTABLE_BASE_ID: Your Airtable base ID (required)
    AIRTABLE_MEETINGS_TABLE: Name of Meetings table (default: "Meetings")
    AIRTABLE_TASKS_TABLE: Name of Tasks table (default: "Tasks")

Output:
    Creates records in Airtable and returns record IDs
"""

import os
import sys
import json
from pathlib import Path
from typing import Dict, List, Any, Optional
from datetime import datetime
from pyairtable import Api
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Constants
AIRTABLE_API_KEY = os.getenv("AIRTABLE_API_KEY")
AIRTABLE_BASE_ID = os.getenv("AIRTABLE_BASE_ID")
AIRTABLE_MEETINGS_TABLE = os.getenv("AIRTABLE_MEETINGS_TABLE", "Meetings")
AIRTABLE_TASKS_TABLE = os.getenv("AIRTABLE_TASKS_TABLE", "Tasks")


class AirtableError(Exception):
    """Custom exception for Airtable operations."""
    pass


# ============================================================================
# VALIDATION & SETUP
# ============================================================================

def validate_environment() -> None:
    """Validate required environment variables are set."""
    missing = []

    if not AIRTABLE_API_KEY:
        missing.append("AIRTABLE_API_KEY")
    if not AIRTABLE_BASE_ID:
        missing.append("AIRTABLE_BASE_ID")

    if missing:
        raise EnvironmentError(
            f"Missing required environment variables: {', '.join(missing)}\n"
            "Please set them in your .env file.\n"
            "Get your Personal Access Token from: https://airtable.com/create/tokens"
        )


def load_summary(file_path: Path) -> dict:
    """
    Load summary JSON file.

    Args:
        file_path: Path to the summary JSON file

    Returns:
        Dict containing the summary data

    Raises:
        FileNotFoundError: If the file doesn't exist
        json.JSONDecodeError: If the file isn't valid JSON
    """
    if not file_path.exists():
        raise FileNotFoundError(f"Summary file not found: {file_path}")

    with open(file_path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    print(f"✓ Loaded summary from {file_path}")
    return data


# ============================================================================
# HELPER FUNCTIONS (Production-Hardened)
# ============================================================================

def format_attendees(transcript_data: dict) -> str:
    """
    Extract attendee emails from Fathom transcript speaker data.

    Fathom's transcript endpoint embeds participant info per-segment:
        transcript[].speaker.display_name
        transcript[].speaker.matched_calendar_invitee_email  (nullable)

    Deduplicates by display_name, preferring email when available.

    Args:
        transcript_data: The transcript data from Fathom

    Returns:
        Comma-separated string of attendee emails/names
    """
    seen = {}  # display_name -> email or name
    for segment in transcript_data.get("transcript", []):
        speaker = segment.get("speaker", {})
        name = speaker.get("display_name", "Unknown")
        email = speaker.get("matched_calendar_invitee_email")
        # Keep the email if we find one; don't downgrade to name if already set
        if name not in seen or email:
            seen[name] = email or name

    attendees = list(seen.values())
    return ", ".join(attendees) if attendees else "No attendees"


def format_plain_transcript(transcript_data: dict) -> str:
    """
    Format transcript as plain text without timestamps.

    Args:
        transcript_data: The transcript data from Fathom

    Returns:
        Plain text transcript with speaker labels
    """
    transcript = transcript_data.get("transcript", [])
    lines = []
    for segment in transcript:
        speaker_obj = segment.get("speaker", {})
        speaker = speaker_obj.get("display_name", "Unknown") if isinstance(speaker_obj, dict) else str(speaker_obj)
        text = segment.get("text", "")
        lines.append(f"{speaker}: {text}")

    return "\n\n".join(lines)


def format_hebrew_summary(summary: dict) -> str:
    """
    Format Hebrew summary as rich text with sections.
    Handles RTL (right-to-left) by keeping English characters on separate lines.

    Args:
        summary: The meeting summary from Gemini

    Returns:
        Formatted Hebrew summary with proper RTL handling
    """
    sections = []

    # Meeting Purpose
    sections.append(f"**תכלית הפגישה:** {summary.get('meeting_purpose', '')}")

    # Key Takeaways
    if summary.get('key_takeaways'):
        sections.append("\n**מסקנות עיקריות:**")
        for item in summary['key_takeaways']:
            sections.append(f"• {item}")

    # Topics
    if summary.get('topics'):
        sections.append("\n**נושאים:**")
        for topic in summary['topics']:
            sections.append(f"\n**{topic['title']}**\n{topic['description']}")

    # Action Items
    if summary.get('action_items'):
        sections.append("\n**פעולות:**")
        for task in summary['action_items']:
            # RTL Fix: Put English characters on their own line to prevent garbling
            task_line = f"• {task['title']}"
            if task.get('owner'):
                task_line += f"\n  אחראי: {task['owner']}"  # "Responsible:" in Hebrew
            if task.get('due_date'):
                task_line += f"\n  מועד: {task['due_date']}"  # "Deadline:" in Hebrew
            sections.append(task_line)

    return "\n".join(sections)


def map_priority_to_p_format(priority: str) -> str:
    """
    Map High/Medium/Low to P1/P2/P3 format.

    Args:
        priority: Priority string from Gemini

    Returns:
        P1, P2, or P3
    """
    mapping = {
        "High": "P1",
        "Medium": "P2",
        "Low": "P3"
    }
    return mapping.get(priority.strip(), "P2")  # Strip whitespace for safety


def normalize_status(status: str) -> str:
    """
    Ensure status string exactly matches Airtable Select field options.
    Case-sensitive and character-sensitive.

    Args:
        status: Status string to normalize

    Returns:
        Valid Airtable status: "To-Do", "In Progress", or "Done"
    """
    # Strip whitespace and normalize to exact Airtable options
    normalized = status.strip()

    # Valid statuses in user's Airtable
    valid_statuses = ["To-Do", "In Progress", "Done"]

    if normalized in valid_statuses:
        return normalized

    # Fallback mapping for common variations
    fallback_mapping = {
        "to do": "To-Do",
        "todo": "To-Do",
        "To Do": "To-Do",
        "in progress": "In Progress",
        "inprogress": "In Progress",
        "done": "Done",
        "completed": "Done"
    }

    return fallback_mapping.get(normalized.lower(), "To-Do")


# ============================================================================
# AIRTABLE OPERATIONS
# ============================================================================

def initialize_airtable() -> tuple:
    """
    Initialize Airtable API connection and return table objects.

    Returns:
        Tuple of (meetings_table, tasks_table)

    Raises:
        AirtableError: If connection fails
    """
    try:
        api = Api(AIRTABLE_API_KEY)
        meetings_table = api.table(AIRTABLE_BASE_ID, AIRTABLE_MEETINGS_TABLE)
        tasks_table = api.table(AIRTABLE_BASE_ID, AIRTABLE_TASKS_TABLE)

        print(f"✓ Connected to Airtable base: {AIRTABLE_BASE_ID}")
        return meetings_table, tasks_table

    except Exception as e:
        raise AirtableError(f"Failed to connect to Airtable: {e}")


def create_meeting_record(
    meetings_table,
    summary: dict,
    transcript_data: dict,
    recording_id: str
) -> str:
    """
    Create a meeting record in the Meetings table.

    Args:
        meetings_table: The Airtable Meetings table object
        summary: The meeting summary dict
        transcript_data: The raw transcript data from Fathom
        recording_id: The Fathom recording ID

    Returns:
        The Airtable record ID for the created meeting

    Raises:
        AirtableError: If record creation fails
    """
    # Prepare meeting record fields (matching user's Airtable structure)
    fields = {
        "Call Name": summary.get("meeting_title", "פגישה ללא שם"),  # "Meeting without name" in Hebrew
        "Date/Time": datetime.now().strftime("%Y-%m-%d"),
        "Attendees Emails": format_attendees(transcript_data),
        "Fathom URL": f"https://app.fathom.video/recordings/{recording_id}",
        "Raw Transcript": format_plain_transcript(transcript_data),
        "Professional Summary": format_hebrew_summary(summary),
        "Status": "Completed"
    }

    try:
        print(f"Creating meeting record: {fields['Call Name']}")
        record = meetings_table.create(fields)
        meeting_record_id = record['id']
        print(f"✓ Meeting record created: {meeting_record_id}")
        return meeting_record_id

    except Exception as e:
        raise AirtableError(f"Failed to create meeting record: {e}")


def create_task_records(
    tasks_table,
    action_items: List[dict],
    meeting_record_id: str,
    meeting_title: str
) -> List[str]:
    """
    Create task records in the Tasks table and link them to the meeting.

    Args:
        tasks_table: The Airtable Tasks table object
        action_items: List of action items from the summary
        meeting_record_id: The parent meeting's Airtable record ID
        meeting_title: The meeting title for reference

    Returns:
        List of created task record IDs

    Raises:
        AirtableError: If task creation fails
    """
    if not action_items:
        print("No action items to create")
        return []

    task_record_ids = []

    print(f"\nCreating {len(action_items)} task records...")

    for i, task in enumerate(action_items, 1):
        # Map to user's Airtable field structure
        fields = {
            "Task Description": task.get("title", "משימה ללא כותרת"),  # Hebrew: "Task without title"
            "Priority": map_priority_to_p_format(task.get("priority", "Medium")),
            "Status": normalize_status("To-Do"),
            "Source Meeting": [meeting_record_id],  # Link to parent meeting
        }

        # Add due date if present
        if task.get("due_date"):
            fields["Due Date"] = task["due_date"]

        try:
            record = tasks_table.create(fields)
            task_record_id = record['id']
            task_record_ids.append(task_record_id)
            print(f"  {i}. ✓ Created task: {fields['Task Description']} [{task_record_id}]")

        except Exception as e:
            print(f"  {i}. ✗ Failed to create task '{fields['Task Description']}': {e}")
            # Continue with other tasks even if one fails
            continue

    print(f"✓ Created {len(task_record_ids)}/{len(action_items)} task records")
    return task_record_ids


def update_meeting_with_tasks(
    meetings_table,
    meeting_record_id: str,
    task_record_ids: List[str]
) -> None:
    """
    Update the meeting record to link all task records.

    Note: This may not be necessary if your Airtable base has automatic
    bidirectional linking configured. Include this if needed.

    Args:
        meetings_table: The Airtable Meetings table object
        meeting_record_id: The meeting's record ID
        task_record_ids: List of task record IDs to link
    """
    if not task_record_ids:
        return

    try:
        # Only update if you have a "Tasks" linked field in the Meetings table
        meetings_table.update(meeting_record_id, {
            "Tasks": task_record_ids
        })
        print(f"✓ Linked {len(task_record_ids)} tasks to meeting record")

    except Exception as e:
        # This might fail if the field doesn't exist or is auto-linked
        print(f"Note: Could not update meeting->tasks link (may be automatic): {e}")


# ============================================================================
# MAIN EXECUTION
# ============================================================================

def display_results(
    meeting_record_id: str,
    task_record_ids: List[str],
    summary: dict
) -> None:
    """Display a summary of what was created in Airtable."""
    print("\n" + "="*80)
    print("AIRTABLE LOGGING COMPLETE")
    print("="*80)
    print(f"\nMeeting: {summary.get('meeting_title', 'Untitled')}")
    print(f"  Record ID: {meeting_record_id}")
    print(f"  Sentiment: {summary.get('meeting_sentiment', 'N/A')}")
    print(f"  Key Points: {len(summary.get('key_points', []))}")
    print(f"  Decisions: {len(summary.get('decisions_made', []))}")

    print(f"\nTasks Created: {len(task_record_ids)}")
    if task_record_ids:
        for i, task_id in enumerate(task_record_ids, 1):
            task = summary['action_items'][i-1]
            print(f"  {i}. {task['title']} [{task['priority']}] - {task_id}")

    print("\n" + "="*80)


def main(summary_file: Optional[Path] = None, transcript_file: Optional[Path] = None):
    """Main execution function."""
    # Check for required arguments if not provided
    if summary_file is None or transcript_file is None:
        if len(sys.argv) != 3:
            print("Usage: python log_to_airtable.py <summary_file> <transcript_file>")
            print("\nExample:")
            print("  python log_to_airtable.py .tmp/summary_abc123.json .tmp/transcript_abc123.json")
            sys.exit(1)
        summary_file = Path(sys.argv[1])
        transcript_file = Path(sys.argv[2])

    try:
        # Validate environment
        validate_environment()

        # Load summary and transcript
        summary = load_summary(summary_file)
        transcript_data = load_summary(transcript_file)  # Reuse load_summary for consistency

        # Extract recording ID from filename
        recording_id = summary_file.stem.replace("summary_", "")

        # Initialize Airtable
        meetings_table, tasks_table = initialize_airtable()

        # Create meeting record (now with transcript data)
        meeting_record_id = create_meeting_record(
            meetings_table,
            summary,
            transcript_data,
            recording_id
        )

        # Create task records
        task_record_ids = create_task_records(
            tasks_table,
            summary.get('action_items', []),
            meeting_record_id,
            summary.get('meeting_title', 'Untitled Meeting')
        )

        # Optional: Update meeting with task links (if bidirectional linking not automatic)
        # update_meeting_with_tasks(meetings_table, meeting_record_id, task_record_ids)

        # Display results
        display_results(meeting_record_id, task_record_ids, summary)

        # Success
        print(f"\n✓ SUCCESS: Data logged to Airtable")
        print(f"Meeting ID: {meeting_record_id}")
        print(f"Tasks Created: {len(task_record_ids)}")

        return 0

    except EnvironmentError as e:
        print(f"\n✗ ENVIRONMENT ERROR: {e}", file=sys.stderr)
        return 1

    except FileNotFoundError as e:
        print(f"\n✗ FILE ERROR: {e}", file=sys.stderr)
        return 1

    except AirtableError as e:
        print(f"\n✗ AIRTABLE ERROR: {e}", file=sys.stderr)
        return 1

    except Exception as e:
        print(f"\n✗ UNEXPECTED ERROR: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
