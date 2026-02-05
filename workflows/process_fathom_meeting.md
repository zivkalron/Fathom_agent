# Workflow: Process Fathom Meeting

## Objective

Automatically ingest Fathom video transcripts, generate AI-powered summaries, extract actionable tasks, and log everything to Airtable for searchability and task management.

## Prerequisites

### Required API Keys
- **Fathom API Key**: Get from https://app.fathom.video/settings/integrations
- **Google Gemini API Key**: Get from https://aistudio.google.com/app/apikey
- **Airtable Personal Access Token**: Get from https://airtable.com/create/tokens
- **Airtable Base ID**: Found in your Airtable base URL

### Airtable Base Structure

**Meetings Table** (required fields):
- `Recording ID` (Single line text) - Unique identifier from Fathom
- `Title` (Single line text) - Meeting title
- `Date` (Date) - Meeting date
- `Executive Summary` (Long text) - AI-generated summary
- `Key Points` (Long text) - Bullet points of main topics
- `Decisions Made` (Long text) - Explicit decisions
- `Participants` (Single line text) - Comma-separated names
- `Sentiment` (Single select: Positive/Neutral/Negative/Mixed)
- `Tags` (Single line text) - Comma-separated tags
- `Task Count` (Number) - Number of action items
- `Status` (Single select) - Processing status
- `Tasks` (Link to Tasks table) - Linked task records

**Tasks Table** (required fields):
- `Title` (Single line text) - Task title
- `Description` (Long text) - Detailed description
- `Owner` (Single line text) - Assigned person
- `Priority` (Single select: High/Medium/Low)
- `Status` (Single select: To Do/In Progress/Done)
- `Due Date` (Date) - Optional deadline
- `Context` (Long text) - Meeting context
- `Meeting` (Link to Meetings table) - Parent meeting record

## Inputs

- **Recording ID**: The Fathom API recording ID (numeric, e.g., `119611450`)
  - **Note**: Browser URL shows a different "call ID" - use the API's `recording_id` field instead
  - Get recording IDs via API: `curl -H "X-Api-Key: YOUR_KEY" "https://api.fathom.ai/external/v1/meetings?limit=5"`
  - The API response includes both `url` (browser link) and `recording_id` (API identifier)

## Tools Used

1. `tools/fetch_fathom_transcript.py` - Fetches transcript from Fathom API
2. `tools/summarize_with_gemini.py` - Generates structured summary with Gemini
3. `tools/log_to_airtable.py` - Logs meeting and tasks to Airtable

## Process Flow

### Step 1: Fetch Transcript

```bash
python3 tools/fetch_fathom_transcript.py <recording_id>
```

**What it does:**
- Calls Fathom API: `https://api.fathom.ai/external/v1/recordings/{id}/transcript`
- Uses `X-Api-Key` header for authentication (not Bearer token)
- Fetches full transcript with timestamps and speakers
- Saves to `.tmp/transcript_{recording_id}.json`

**Success criteria:**
- ✓ Returns 200 status code
- ✓ JSON file created in `.tmp/`
- ✓ Contains transcript segments with speaker labels

**Error handling:**
- **401 Unauthorized**: Check FATHOM_API_KEY in .env
- **404 Not Found**: Verify recording ID is correct (use API `recording_id`, not browser call ID)
- **429 Rate Limited**: Wait and retry (Fathom limit: 60 requests/minute per user)
- **Network errors**: Check internet connection

### Step 2: Generate Summary

```bash
python3 tools/summarize_with_gemini.py .tmp/transcript_{recording_id}.json
```

**What it does:**
- Loads transcript JSON
- Formats for Gemini 2.5 Flash (model: `gemini-2.5-flash`)
- Generates structured Hebrew summary using Pydantic schema validation
- Extracts action items with owners, priorities, due dates
- Saves to `.tmp/summary_{recording_id}.json`
- Max output tokens: 8192 (to handle long Hebrew summaries)

**Success criteria:**
- ✓ Valid JSON response from Gemini
- ✓ Passes Pydantic schema validation
- ✓ Contains meeting_title, meeting_purpose, key_takeaways, topics, action_items
- ✓ All action items have title, description, priority
- ✓ All text content in Hebrew (except names, dates, priority levels)

**Error handling:**
- **Empty response**: Check API key and quota
- **JSON parse error**: Retry (Gemini sometimes adds markdown)
- **Validation error**: Review schema requirements
- **Rate limit**: Free tier has limits, wait or upgrade

**Schema validation ensures:**
- Meeting title and purpose are present
- Key takeaways: At least 1 item
- Tasks include all required fields (title, description, priority)
- Priority is High/Medium/Low
- Dates in YYYY-MM-DD format (optional)
- Owner names (optional)

### Step 3: Log to Airtable

```bash
python3 tools/log_to_airtable.py .tmp/summary_{recording_id}.json .tmp/transcript_{recording_id}.json
```

**What it does:**
1. Creates meeting record in Meetings table
2. Creates individual task records in Tasks table
3. Links tasks to parent meeting (relational structure)
4. Returns record IDs for verification

**Success criteria:**
- ✓ Meeting record created with unique Recording ID
- ✓ All tasks created and linked to meeting
- ✓ Relational links established
- ✓ Returns meeting_record_id and task_record_ids

**Error handling:**
- **Authentication failed**: Check AIRTABLE_API_KEY permissions
- **Base not found**: Verify AIRTABLE_BASE_ID
- **Table not found**: Check table names match .env config
- **Field mismatch**: Ensure Airtable fields match expected schema
- **Duplicate recording ID**: Meeting already processed

### Step 4: Cleanup (Optional)

```bash
# Keep intermediate files for debugging
# Or clean up after successful logging:
rm .tmp/transcript_{recording_id}.json
rm .tmp/summary_{recording_id}.json
```

## Complete End-to-End Example

```bash
# 1. Set recording ID
RECORDING_ID="abc123def456"

# 2. Fetch transcript
python tools/fetch_fathom_transcript.py $RECORDING_ID

# 3. Generate summary
python tools/summarize_with_gemini.py .tmp/transcript_$RECORDING_ID.json

# 4. Log to Airtable
python tools/log_to_airtable.py .tmp/summary_$RECORDING_ID.json

# 5. Success! Check Airtable for your data
```

## Output

**In Airtable:**
- New meeting record in Meetings table with full metadata
- Individual task records in Tasks table
- Tasks linked to parent meeting for easy navigation

**Local files (in `.tmp/`):**
- `transcript_{recording_id}.json` - Raw transcript from Fathom
- `summary_{recording_id}.json` - Structured summary with tasks

## Edge Cases & Gotchas

### Fathom API
- **Free tier limit**: 100 API calls per day
- **Transcript not ready**: Wait a few minutes after recording ends
- **No transcript**: Check if transcription is enabled for the meeting

### Gemini API
- **Response format**: Sometimes includes markdown code blocks (handled by tool)
- **Token limits**: Very long meetings may hit limits (use chunking if needed)
- **Temperature setting**: Set to 0.2 for deterministic output
- **Free tier**: 15 requests per minute, 1500 per day

### Airtable API
- **Rate limits**: 5 requests/second per base
- **Record ID format**: Always use brackets for linked records: `[record_id]`
- **Field types matter**: Ensure Single Select options exist before writing
- **Bidirectional linking**: May be automatic depending on base config

## Performance Notes

- **Step 1 (Fetch)**: ~2-5 seconds
- **Step 2 (Summarize)**: ~5-15 seconds (depends on transcript length)
- **Step 3 (Log)**: ~2-5 seconds (depends on number of tasks)
- **Total**: ~10-25 seconds per meeting

## Future Enhancements

- [ ] Batch processing multiple recordings
- [ ] Webhook integration for automatic processing
- [ ] Email notifications on task creation
- [ ] Slack integration for task assignments
- [ ] Sentiment analysis trends over time
- [ ] Custom prompt templates per meeting type
- [ ] Audio file attachment storage
- [ ] Meeting series tracking (recurring meetings)

## Learnings & Updates

**2024-01-XX**: Initial workflow created
- All three tools working independently
- Pydantic validation prevents bad data reaching Airtable
- Relational structure requires meeting created first, then tasks

**2026-02-05**: Fixed "No attendees" bug in Attendees Emails field
- **Root cause**: `format_attendees()` looked for a top-level `participants` key in the transcript response. That key does not exist. The Fathom `/recordings/{id}/transcript` endpoint only returns `{ "transcript": [...] }` — no top-level participant list.
- **Actual structure**: Attendee info is embedded per-segment inside `transcript[].speaker`, with `display_name` and `matched_calendar_invitee_email` (nullable). Emails are matched by Fathom against calendar invitee data and may be null for unmatched speakers.
- **Fix**: Rewrote `format_attendees()` to iterate over transcript segments, deduplicate by `display_name`, and prefer `matched_calendar_invitee_email` when available, falling back to the name.
