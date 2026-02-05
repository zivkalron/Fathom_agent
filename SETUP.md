# Fathom Meeting Automation - Setup Guide

Complete setup instructions for the WAT-based meeting automation agent.

## Overview

This system automatically processes Fathom meeting recordings:
1. Fetches transcripts via Fathom API (https://api.fathom.ai/external/v1)
2. Generates AI summaries using Google Gemini 2.5 Flash
3. Extracts actionable tasks with structured validation
4. Logs everything to Airtable with relational structure

## Step 1: System Requirements

- Python 3.8 or higher
- pip (Python package manager)
- Internet connection
- Active accounts for:
  - Fathom (free tier works)
  - Google AI Studio (Gemini API)
  - Airtable (free tier works)

## Step 2: Install Dependencies

```bash
# Create and activate virtual environment (recommended)
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install required packages
pip3 install -r requirements.txt
```

Expected packages:
- `python-dotenv` - Environment variable management
- `requests` - HTTP requests
- `google-generativeai` - Gemini API client
- `pyairtable` - Airtable API client
- `pydantic` - Data validation

## Step 3: Get API Keys

### 3.1 Fathom API Key

1. Go to https://app.fathom.video/settings/integrations
2. Find the "API Access" section
3. Click "Generate API Key"
4. Copy the key

**Important Notes:**
- API endpoint: `https://api.fathom.ai/external/v1`
- Authentication: Uses `X-Api-Key` header (not Bearer token)
- Rate limit: 60 requests per minute per user
- Free tier includes reasonable API access for testing

### 3.2 Google Gemini API Key

1. Go to https://aistudio.google.com/app/apikey
2. Click "Create API Key"
3. Select or create a Google Cloud project
4. Copy the API key

**Note**: Free tier includes 15 requests/minute, 1500/day.

### 3.3 Airtable Personal Access Token

1. Go to https://airtable.com/create/tokens
2. Click "Create new token"
3. Name it: "Fathom Meeting Automation"
4. Add scopes:
   - `data.records:read`
   - `data.records:write`
   - `schema.bases:read`
5. Add access to your base
6. Click "Create token"
7. Copy the token (starts with `pat...`)

### 3.4 Airtable Base ID

1. Open your Airtable base
2. Look at the URL: `https://airtable.com/{BASE_ID}/...`
3. Copy the base ID (starts with `app...`)

## Step 4: Configure Airtable Base

Create two tables with the following structure:

### Meetings Table

| Field Name | Field Type | Options |
|------------|------------|---------|
| Recording ID | Single line text | |
| Title | Single line text | |
| Date | Date | |
| Executive Summary | Long text | |
| Key Points | Long text | |
| Decisions Made | Long text | |
| Participants | Single line text | |
| Sentiment | Single select | Positive, Neutral, Negative, Mixed |
| Tags | Single line text | |
| Task Count | Number | Integer |
| Status | Single select | Processed, Failed |
| Tasks | Link to another record | Link to Tasks table |

### Tasks Table

| Field Name | Field Type | Options |
|------------|------------|---------|
| Title | Single line text | |
| Description | Long text | |
| Owner | Single line text | |
| Priority | Single select | High, Medium, Low |
| Status | Single select | To Do, In Progress, Done |
| Due Date | Date | |
| Context | Long text | |
| Meeting | Link to another record | Link to Meetings table |

**Important**:
- Enable bidirectional linking between Meetings and Tasks
- The table names must match what's in your .env (default: "Meetings" and "Tasks")

## Step 5: Configure Environment Variables

```bash
# Copy the example file
cp .env.example .env

# Edit .env with your actual values
nano .env  # or use your preferred editor
```

Fill in your `.env` file:

```bash
# Fathom API
FATHOM_API_KEY=fathom_your_key_here

# Google Gemini API
GOOGLE_GEMINI_API_KEY=your_gemini_key_here

# Airtable Configuration
AIRTABLE_API_KEY=patyour_key_here
AIRTABLE_BASE_ID=appyour_base_id_here

# Table names (adjust if you named them differently)
AIRTABLE_MEETINGS_TABLE=Meetings
AIRTABLE_TASKS_TABLE=Tasks
```

**Security Note**: Never commit `.env` to version control. It's already in `.gitignore`.

## Step 6: Get Recording ID

**IMPORTANT: Browser URL vs API Recording ID**

The browser URL format differs from the API recording ID:
- **Browser URL**: `https://fathom.video/calls/554468783` (call ID: numeric)
- **API Recording ID**: `119611450` (different numeric ID used by API)

**To get the correct recording ID:**

```bash
# List your recent meetings to find recording IDs
curl -H "X-Api-Key: YOUR_FATHOM_API_KEY" \
  "https://api.fathom.ai/external/v1/meetings?limit=5"
```

The response will show both:
- `"url"`: Browser URL with call ID
- `"recording_id"`: Numeric ID to use with the API

**Use the `recording_id` field for all API operations.**

## Step 7: Test Individual Tools

Test each tool independently before running the full pipeline.

### Test 1: Fetch Transcript

```bash
python3 tools/fetch_fathom_transcript.py YOUR_RECORDING_ID
```

**Expected output:**
```
✓ Successfully fetched transcript (X segments)
✓ Transcript saved to: .tmp/transcript_YOUR_RECORDING_ID.json
✓ SUCCESS: Transcript ready for processing
```

### Test 2: Generate Summary

```bash
python3 tools/summarize_with_gemini.py .tmp/transcript_YOUR_RECORDING_ID.json
```

**Expected output:**
```
✓ Loaded transcript
✓ Calling Gemini gemini-1.5-flash...
✓ Received response from Gemini
✓ Response validated against schema
✓ Summary saved to: .tmp/summary_YOUR_RECORDING_ID.json
✓ SUCCESS: Summary ready
```

### Test 3: Log to Airtable

```bash
python3 tools/log_to_airtable.py .tmp/summary_YOUR_RECORDING_ID.json .tmp/transcript_YOUR_RECORDING_ID.json
```

**Expected output:**
```
✓ Connected to Airtable base
✓ Meeting record created: recXXXXXXXXXXXXXX
✓ Created X task records
✓ SUCCESS: Data logged to Airtable
```

## Step 8: Run Full Pipeline

Once individual tools work, run the complete pipeline:

```bash
python3 tools/process_meeting.py YOUR_RECORDING_ID
```

**Expected output:**
```
================================================================================
 MEETING AUTOMATION PIPELINE
================================================================================

Recording ID: YOUR_RECORDING_ID
Started: 2024-XX-XX HH:MM:SS

[STEP 1/3] Fetching transcript from Fathom
------------------------------------------------------------
✓ Successfully fetched transcript

[STEP 2/3] Generating AI summary with Gemini
------------------------------------------------------------
✓ Summary generated

[STEP 3/3] Logging to Airtable
------------------------------------------------------------
✓ Data logged

================================================================================
 PIPELINE COMPLETE
================================================================================
✓ Recording YOUR_RECORDING_ID processed successfully
✓ Total duration: XX.X seconds
✓ Meeting and tasks logged to Airtable
```

### Pipeline Options

```bash
# Keep intermediate files for debugging
python3 tools/process_meeting.py YOUR_RECORDING_ID --keep-files

# Skip Airtable (test summarization only)
python3 tools/process_meeting.py YOUR_RECORDING_ID --skip-airtable
```

## Troubleshooting

### Environment Errors

**Error**: `FATHOM_API_KEY not found`
- **Solution**: Check `.env` file exists and contains the key
- Ensure no spaces around `=` in `.env`

**Error**: `Failed to connect to Airtable`
- **Solution**: Verify AIRTABLE_API_KEY has correct scopes
- Check AIRTABLE_BASE_ID is correct

### API Errors

**Error**: `401 Unauthorized (Fathom)`
- **Solution**: Regenerate API key in Fathom settings

**Error**: `404 Not Found (Fathom)`
- **Solution**: Verify recording ID is correct
- Check recording has finished processing in Fathom

**Error**: `429 Rate Limited`
- **Solution**: Wait before retrying
- Fathom free: 100/day
- Gemini free: 15/min, 1500/day

### Validation Errors

**Error**: `Schema validation failed`
- **Solution**: Gemini response didn't match expected structure
- Check `--keep-files` to see actual response
- May need to adjust prompt in `summarize_with_gemini.py`

**Error**: `Field mismatch (Airtable)`
- **Solution**: Airtable fields don't match expected schema
- Review "Step 4: Configure Airtable Base" above
- Ensure field names and types match exactly

### Connection Errors

**Error**: `Request timed out`
- **Solution**: Check internet connection
- Increase timeout in tool script if needed

## Usage Tips

1. **Batch Processing**: Process multiple meetings by looping:
   ```bash
   for id in 119611450 119612000 119613000; do
     python3 tools/process_meeting.py $id
     sleep 5  # Rate limit buffer
   done
   ```

2. **Debugging**: Use `--keep-files` to inspect intermediate JSON:
   ```bash
   python3 tools/process_meeting.py ID --keep-files
   cat .tmp/summary_ID.json | jq .
   ```

3. **Testing**: Use `--skip-airtable` when testing summarization:
   ```bash
   python3 tools/process_meeting.py ID --skip-airtable
   ```

4. **Workflow Reference**: See [workflows/process_fathom_meeting.md](workflows/process_fathom_meeting.md) for detailed process documentation

## Next Steps

1. Process your first meeting end-to-end
2. Review the output in Airtable
3. Adjust Gemini prompt if needed (in `summarize_with_gemini.py`)
4. Set up automation (webhooks, cron jobs, etc.)
5. Explore additional features (see workflow doc)

## Getting Help

- **Project Issues**: Review [workflows/process_fathom_meeting.md](workflows/process_fathom_meeting.md)
- **WAT Framework**: See [CLAUDE.md](CLAUDE.md) for architecture details
- **Tool Documentation**: Each tool has detailed docstrings at the top of the file

## Success Checklist

- [ ] Python 3.8+ installed
- [ ] Dependencies installed from requirements.txt
- [ ] All API keys obtained and configured
- [ ] Airtable base created with correct structure
- [ ] .env file configured with all keys
- [ ] Individual tools tested successfully
- [ ] Full pipeline run successfully
- [ ] Meeting and tasks visible in Airtable

Once all items are checked, you're ready for production use!
