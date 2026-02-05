#!/usr/bin/env python3
"""
Summarize meeting transcript using Google Gemini 1.5 Flash.

This tool takes a Fathom transcript and generates:
1. A professional summary of the meeting
2. An array of actionable tasks with owners and priorities

Uses Pydantic for structured output validation (Zod-like schema).

Usage:
    python summarize_with_gemini.py <transcript_file>

Example:
    python summarize_with_gemini.py .tmp/transcript_abc123.json

Environment Variables:
    GOOGLE_GEMINI_API_KEY: Your Google AI Studio API key (required)

Output:
    Writes summary to .tmp/summary_{recording_id}.json
    Returns: Structured JSON with summary and tasks
"""

import os
import sys
import json
import google.generativeai as genai
from pathlib import Path
from typing import List, Optional
from datetime import datetime
from pydantic import BaseModel, Field, ValidationError
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Constants
GEMINI_API_KEY = os.getenv("GOOGLE_GEMINI_API_KEY")
GEMINI_MODEL = "gemini-2.5-flash"
OUTPUT_DIR = Path(".tmp")


# ============================================================================
# STRUCTURED OUTPUT SCHEMAS (Zod-like validation using Pydantic)
# ============================================================================

class Task(BaseModel):
    """Schema for an actionable task extracted from the meeting."""
    title: str = Field(..., description="Clear, actionable task title")
    description: str = Field(..., description="Detailed description of what needs to be done")
    owner: Optional[str] = Field(None, description="Person assigned to the task")
    priority: str = Field(..., description="Priority level: High, Medium, or Low")
    due_date: Optional[str] = Field(None, description="Due date if mentioned (YYYY-MM-DD format)")
    context: str = Field(..., description="Relevant context or discussion from the meeting")

    class Config:
        json_schema_extra = {
            "example": {
                "title": "Review Q4 budget proposal",
                "description": "Review the updated budget proposal and provide feedback on marketing allocation",
                "owner": "Sarah Chen",
                "priority": "High",
                "due_date": "2024-03-15",
                "context": "Discussed during budget review section"
            }
        }


class Topic(BaseModel):
    """Schema for a meeting topic."""
    title: str = Field(..., description="Topic title in Hebrew")
    description: str = Field(..., description="1-3 sentences about the topic in Hebrew")


class MeetingSummary(BaseModel):
    """Schema for the complete meeting summary output - in Hebrew."""
    meeting_title: str = Field(..., description="Meeting title in Hebrew")
    meeting_purpose: str = Field(..., description="Short sentence describing meeting purpose in Hebrew")
    key_takeaways: List[str] = Field(
        ...,
        min_items=1,
        description="Important insights or decisions as bullet points in Hebrew"
    )
    topics: List[Topic] = Field(
        default_factory=list,
        description="Main topics discussed with descriptions in Hebrew"
    )
    action_items: List[Task] = Field(
        default_factory=list,
        description="Actionable tasks extracted from the meeting in Hebrew"
    )
    participants_mentioned: List[str] = Field(
        default_factory=list,
        description="Names of participants mentioned in the discussion"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "meeting_title": "סקירת תקציב רבעון 4",
                "meeting_purpose": "לבחון את ביצועי התקציב ברבעון 4 ולתכנן הקצאת משאבים",
                "key_takeaways": [
                    "התקציב ברבעון 4 נמוך ב-5% מהיעד",
                    "צוות השיווק ביקש כ headcount נוסף"
                ],
                "topics": [
                    {
                        "title": "ביצועי תקציב",
                        "description": "הצוות סקר את ביצועי תקציב רבעון 4 ודן בהקצאת משאבים ליוזמות הקרובות"
                    }
                ],
                "action_items": [],
                "participants_mentioned": ["Sarah Chen", "Mike Rodriguez"]
            }
        }


class GeminiAPIError(Exception):
    """Custom exception for Gemini API errors."""
    pass


# ============================================================================
# CORE FUNCTIONS
# ============================================================================

def validate_environment() -> None:
    """Validate required environment variables are set."""
    if not GEMINI_API_KEY:
        raise EnvironmentError(
            "GOOGLE_GEMINI_API_KEY not found. Please set it in your .env file.\n"
            "Get your API key from: https://aistudio.google.com/app/apikey"
        )


def load_transcript(file_path: Path) -> dict:
    """
    Load transcript JSON file.

    Args:
        file_path: Path to the transcript JSON file

    Returns:
        Dict containing the transcript data

    Raises:
        FileNotFoundError: If the file doesn't exist
        json.JSONDecodeError: If the file isn't valid JSON
    """
    if not file_path.exists():
        raise FileNotFoundError(f"Transcript file not found: {file_path}")

    with open(file_path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    print(f"✓ Loaded transcript from {file_path}")
    return data


def format_transcript_for_gemini(data: dict) -> str:
    """
    Format transcript data into a readable text for Gemini.

    Args:
        data: The transcript data from Fathom

    Returns:
        Formatted transcript string
    """
    # Extract metadata
    title = data.get('title', 'Untitled Meeting')
    date = data.get('date', 'Unknown date')
    participants = data.get('participants', [])

    # Build formatted text
    lines = [
        f"MEETING: {title}",
        f"DATE: {date}",
        f"PARTICIPANTS: {', '.join(participants) if participants else 'Not specified'}",
        "",
        "TRANSCRIPT:",
        "=" * 80,
        ""
    ]

    # Add transcript segments
    transcript = data.get('transcript', [])
    for segment in transcript:
        speaker = segment.get('speaker', 'Unknown')
        text = segment.get('text', '')
        timestamp = segment.get('timestamp', '')
        lines.append(f"[{timestamp}] {speaker}: {text}")

    return "\n".join(lines)


def create_prompt(transcript_text: str) -> str:
    """
    Create the prompt for Gemini with Hebrew output instructions.

    Args:
        transcript_text: The formatted transcript

    Returns:
        Complete prompt string in Hebrew
    """
    prompt = f"""You are Convobot — a professional meeting & conversation summarizer.

Your job is to turn raw, messy, or unstructured conversation transcripts into clear and concise summaries — written in **Hebrew only**.
The tone should be natural, professional, and easy to read — as if written by a human native speaker.

{transcript_text}

🧠 Behavior Guidelines:
- Never translate or explain — output must always be written natively in Hebrew
- Focus on signal, not noise: remove chit-chat, filler, and irrelevant side talk
- Keep the language fluent, clear, and professional — no slang, no formal bureaucracy
- Structure the summary for someone who wasn't in the meeting and needs to quickly understand what happened and what's next
- Don't mention the transcript or that you're summarizing — just write the summary directly, like a human would

Return your analysis as valid JSON with the following structure (all text fields in Hebrew):

{{
  "meeting_title": "כותרת מקצועית של הפגישה בעברית",
  "meeting_purpose": "משפט קצר המתאר את תכלית הפגישה",
  "key_takeaways": [
    "תובנה או החלטה חשובה 1",
    "תובנה או החלטה חשובה 2"
  ],
  "topics": [
    {{
      "title": "כותרת הנושא",
      "description": "1-3 משפטים על הנושא"
    }}
  ],
  "action_items": [
    {{
      "title": "כותרת המשימה בעברית",
      "description": "תיאור מפורט של מה צריך לעשות",
      "owner": "שם האחראי או null",
      "priority": "High|Medium|Low",
      "due_date": "YYYY-MM-DD או null",
      "context": "הקשר רלוונטי מהפגישה"
    }}
  ],
  "participants_mentioned": ["רשימת שמות המשתתפים"]
}}

CRITICAL: Return ONLY valid JSON, no markdown code blocks or formatting. All text content must be in Hebrew except for: owner names, dates, and priority levels.
"""
    return prompt


def call_gemini(prompt: str) -> dict:
    """
    Call Gemini API to generate structured summary.

    Args:
        prompt: The complete prompt

    Returns:
        Dict with the structured response

    Raises:
        GeminiAPIError: If the API call fails
    """
    try:
        # Configure Gemini
        genai.configure(api_key=GEMINI_API_KEY)

        # Initialize model
        model = genai.GenerativeModel(GEMINI_MODEL)

        print(f"Calling Gemini {GEMINI_MODEL}...")

        # Generate content
        response = model.generate_content(
            prompt,
            generation_config={
                "temperature": 0.2,  # Low temperature for more deterministic output
                "top_p": 0.8,
                "top_k": 40,
                "max_output_tokens": 8192,
            }
        )

        # Extract text
        if not response.text:
            raise GeminiAPIError("Empty response from Gemini")

        print("✓ Received response from Gemini")

        # Parse JSON
        # Remove markdown code blocks if present
        response_text = response.text.strip()
        if response_text.startswith("```json"):
            response_text = response_text[7:]
        if response_text.startswith("```"):
            response_text = response_text[3:]
        if response_text.endswith("```"):
            response_text = response_text[:-3]
        response_text = response_text.strip()

        result = json.loads(response_text)
        return result

    except json.JSONDecodeError as e:
        raise GeminiAPIError(f"Failed to parse Gemini response as JSON: {e}\nResponse: {response.text[:500]}")

    except Exception as e:
        raise GeminiAPIError(f"Gemini API call failed: {e}")


def validate_with_pydantic(data: dict) -> MeetingSummary:
    """
    Validate the Gemini response against our Pydantic schema.

    Args:
        data: The raw response from Gemini

    Returns:
        Validated MeetingSummary object

    Raises:
        ValidationError: If the data doesn't match the schema
    """
    try:
        summary = MeetingSummary(**data)
        print("✓ Response validated against schema")
        return summary
    except ValidationError as e:
        print("✗ Validation errors found:")
        for error in e.errors():
            print(f"  - {error['loc']}: {error['msg']}")
        raise


def save_summary(recording_id: str, summary: MeetingSummary) -> Path:
    """
    Save validated summary to JSON file.

    Args:
        recording_id: The recording ID
        summary: Validated MeetingSummary object

    Returns:
        Path to the saved file
    """
    # Ensure output directory exists
    OUTPUT_DIR.mkdir(exist_ok=True)

    # Create output file path
    output_file = OUTPUT_DIR / f"summary_{recording_id}.json"

    # Write data (use model_dump for Pydantic v2)
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(summary.model_dump(), f, indent=2, ensure_ascii=False)

    print(f"✓ Summary saved to: {output_file}")
    return output_file


def display_summary(summary: MeetingSummary) -> None:
    """Display a formatted summary to the console."""
    print("\n" + "="*80)
    print("MEETING SUMMARY")
    print("="*80)
    print(f"\nTitle: {summary.meeting_title}")
    # print(f"Sentiment: {summary.meeting_sentiment}")  # Field removed from schema
    print(f"\nPurpose:\n{summary.meeting_purpose}")
    print(f"\nKey Takeaways ({len(summary.key_takeaways)}):")
    for i, point in enumerate(summary.key_takeaways, 1):
        print(f"  {i}. {point}")

    if summary.topics:
        print(f"\nTopics Discussed ({len(summary.topics)}):")
        for i, topic in enumerate(summary.topics, 1):
            print(f"  {i}. {topic.title}: {topic.description}")

    print(f"\nAction Items ({len(summary.action_items)}):")
    if summary.action_items:
        for i, task in enumerate(summary.action_items, 1):
            owner_str = f" [@{task.owner}]" if task.owner else ""
            due_str = f" (Due: {task.due_date})" if task.due_date else ""
            print(f"  {i}. [{task.priority}] {task.title}{owner_str}{due_str}")
            print(f"     {task.description}")
    else:
        print("  No action items identified")

    # Tags field removed from schema
    # if summary.tags:
    #     print(f"\nTags: {', '.join(summary.tags)}")
    print("="*80)


def main():
    """Main execution function."""
    # Check for transcript file argument
    if len(sys.argv) != 2:
        print("Usage: python summarize_with_gemini.py <transcript_file>")
        print("\nExample:")
        print("  python summarize_with_gemini.py .tmp/transcript_abc123.json")
        sys.exit(1)

    transcript_file = Path(sys.argv[1])

    try:
        # Validate environment
        validate_environment()

        # Load transcript
        transcript_data = load_transcript(transcript_file)

        # Extract recording ID from filename
        recording_id = transcript_file.stem.replace("transcript_", "")

        # Format transcript for Gemini
        transcript_text = format_transcript_for_gemini(transcript_data)

        # Create prompt
        prompt = create_prompt(transcript_text)

        # Call Gemini
        response = call_gemini(prompt)

        # Validate with Pydantic
        summary = validate_with_pydantic(response)

        # Save summary
        output_file = save_summary(recording_id, summary)

        # Display summary
        display_summary(summary)

        # Success
        print(f"\n✓ SUCCESS: Summary ready at {output_file}")
        return 0

    except EnvironmentError as e:
        print(f"\n✗ ENVIRONMENT ERROR: {e}", file=sys.stderr)
        return 1

    except FileNotFoundError as e:
        print(f"\n✗ FILE ERROR: {e}", file=sys.stderr)
        return 1

    except GeminiAPIError as e:
        print(f"\n✗ API ERROR: {e}", file=sys.stderr)
        return 1

    except ValidationError as e:
        print(f"\n✗ VALIDATION ERROR: Schema validation failed", file=sys.stderr)
        return 1

    except Exception as e:
        print(f"\n✗ UNEXPECTED ERROR: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
