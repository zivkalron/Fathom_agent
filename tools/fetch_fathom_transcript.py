#!/usr/bin/env python3
"""
Fetch transcript from Fathom API.

This tool retrieves the full transcript for a given Fathom recording ID.
It handles authentication, rate limiting, and error cases deterministically.

Usage:
    python fetch_fathom_transcript.py <recording_id>

Example:
    python fetch_fathom_transcript.py abc123def456

Environment Variables:
    FATHOM_API_KEY: Your Fathom API key (required)

Output:
    Writes transcript to .tmp/transcript_{recording_id}.json
    Returns: JSON structure with recording metadata and transcript
"""

import os
import sys
import json
import requests
from pathlib import Path
from typing import Dict, Any, Optional
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Constants
FATHOM_API_BASE = "https://api.fathom.ai/external/v1"
FATHOM_API_KEY = os.getenv("FATHOM_API_KEY")
OUTPUT_DIR = Path(".tmp")


class FathomAPIError(Exception):
    """Custom exception for Fathom API errors."""
    pass


def validate_environment() -> None:
    """Validate required environment variables are set."""
    if not FATHOM_API_KEY:
        raise EnvironmentError(
            "FATHOM_API_KEY not found. Please set it in your .env file.\n"
            "Get your API key from: https://app.fathom.video/settings/integrations"
        )


def fetch_transcript(recording_id: str) -> Dict[str, Any]:
    """
    Fetch transcript from Fathom API for the given recording ID.

    Args:
        recording_id: The Fathom recording ID

    Returns:
        Dict containing the transcript and metadata

    Raises:
        FathomAPIError: If the API request fails
    """
    url = f"{FATHOM_API_BASE}/recordings/{recording_id}/transcript"

    headers = {
        "X-Api-Key": FATHOM_API_KEY,
        "Accept": "application/json"
    }

    try:
        print(f"Fetching transcript for recording: {recording_id}")
        response = requests.get(url, headers=headers, timeout=30)

        # Handle different response codes
        if response.status_code == 200:
            data = response.json()
            print(f"✓ Successfully fetched transcript ({len(data.get('transcript', []))} segments)")
            return data

        elif response.status_code == 401:
            raise FathomAPIError(
                "Authentication failed. Please check your FATHOM_API_KEY in .env"
            )

        elif response.status_code == 404:
            raise FathomAPIError(
                f"Recording {recording_id} not found. Please verify the recording ID."
            )

        elif response.status_code == 429:
            raise FathomAPIError(
                "Rate limit exceeded. Please wait and try again later."
            )

        else:
            raise FathomAPIError(
                f"API request failed with status {response.status_code}: {response.text}"
            )

    except requests.exceptions.Timeout:
        raise FathomAPIError("Request timed out. Please check your internet connection.")

    except requests.exceptions.ConnectionError:
        raise FathomAPIError("Connection error. Please check your internet connection.")

    except json.JSONDecodeError:
        raise FathomAPIError("Invalid JSON response from API")


def save_transcript(recording_id: str, data: Dict[str, Any]) -> Path:
    """
    Save transcript data to a JSON file in .tmp directory.

    Args:
        recording_id: The recording ID
        data: The transcript data to save

    Returns:
        Path to the saved file
    """
    # Ensure output directory exists
    OUTPUT_DIR.mkdir(exist_ok=True)

    # Create output file path
    output_file = OUTPUT_DIR / f"transcript_{recording_id}.json"

    # Write data
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

    print(f"✓ Transcript saved to: {output_file}")
    return output_file


def get_recording_metadata(data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Extract key metadata from the transcript response.

    Args:
        data: The full transcript response

    Returns:
        Dict with key metadata fields
    """
    return {
        "recording_id": data.get("recording_id"),
        "title": data.get("title", "Untitled Meeting"),
        "date": data.get("date"),
        "duration_seconds": data.get("duration"),
        "participants": data.get("participants", []),
        "transcript_segments": len(data.get("transcript", [])),
    }


def main():
    """Main execution function."""
    # Check for recording ID argument
    if len(sys.argv) != 2:
        print("Usage: python fetch_fathom_transcript.py <recording_id>")
        print("\nExample:")
        print("  python fetch_fathom_transcript.py abc123def456")
        sys.exit(1)

    recording_id = sys.argv[1]

    try:
        # Validate environment
        validate_environment()

        # Fetch transcript
        data = fetch_transcript(recording_id)

        # Save to file
        output_file = save_transcript(recording_id, data)

        # Display metadata
        metadata = get_recording_metadata(data)
        print("\n" + "="*50)
        print("RECORDING METADATA")
        print("="*50)
        for key, value in metadata.items():
            print(f"{key}: {value}")
        print("="*50)

        # Success
        print(f"\n✓ SUCCESS: Transcript ready for processing at {output_file}")
        return 0

    except EnvironmentError as e:
        print(f"\n✗ ENVIRONMENT ERROR: {e}", file=sys.stderr)
        return 1

    except FathomAPIError as e:
        print(f"\n✗ API ERROR: {e}", file=sys.stderr)
        return 1

    except Exception as e:
        print(f"\n✗ UNEXPECTED ERROR: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
