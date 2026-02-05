# Setup and Configuration Changes

This document summarizes all fixes and updates made during the initial setup and testing phase.

## Date: 2026-02-04

### Issues Discovered and Fixed

#### 1. Fathom API Configuration (CRITICAL)

**Problem:**
- Code used incorrect API endpoint: `https://api.fathom.video/v1`
- Code used wrong authentication: `Authorization: Bearer` header

**Solution:**
- ✅ Updated API base URL to: `https://api.fathom.ai/external/v1`
- ✅ Changed authentication to: `X-Api-Key` header
- ✅ Updated rate limit documentation: 60 requests/minute (not 100/day)

**Files Modified:**
- `tools/fetch_fathom_transcript.py` (lines 34, 69)

#### 2. Recording ID Format (IMPORTANT)

**Problem:**
- Browser URLs show "call IDs" (e.g., `554468783` from `/calls/` path)
- API requires different "recording IDs" (e.g., `119611450`)
- Documentation didn't explain this difference

**Solution:**
- ✅ Documented the ID format difference in SETUP.md
- ✅ Added instructions to get recording IDs via API
- ✅ Updated all examples to use correct recording ID format

**Command to get recording IDs:**
```bash
curl -H "X-Api-Key: YOUR_KEY" "https://api.fathom.ai/external/v1/meetings?limit=5"
```

#### 3. Gemini Model Version (BREAKING)

**Problem:**
- Code used outdated model: `gemini-1.5-flash` (no longer available)
- Error: 404 model not found

**Solution:**
- ✅ Updated to: `gemini-2.5-flash`
- ✅ Increased output tokens: 2048 → 8192 (for longer Hebrew summaries)
- ✅ Fixed display function to match updated schema

**Files Modified:**
- `tools/summarize_with_gemini.py` (lines 40, 284, 370-392)

#### 4. Python Version References

**Problem:**
- Orchestrator script called `python` which doesn't exist on macOS
- Should use `python3` explicitly

**Solution:**
- ✅ Updated all tool invocations to use `python3`
- ✅ Updated all documentation examples to use `python3`

**Files Modified:**
- `tools/process_meeting.py` (line 64)
- `SETUP.md` (all examples)
- `workflows/process_fathom_meeting.md` (all examples)
- `README.md` (all examples)

#### 5. Schema Mismatch in Display Function

**Problem:**
- Display function tried to access deprecated fields:
  - `meeting_sentiment` (removed)
  - `executive_summary` (renamed to `meeting_purpose`)
  - `key_points` (renamed to `key_takeaways`)
  - `decisions_made` (removed)
  - `tags` (removed)

**Solution:**
- ✅ Updated display function to match current Pydantic schema
- ✅ Aligned with Hebrew output structure

**Files Modified:**
- `tools/summarize_with_gemini.py` (lines 365-395)

### Documentation Updates

#### Files Updated:
1. **SETUP.md**
   - Corrected API endpoint and authentication
   - Added recording ID format explanation
   - Updated all commands to use `python3`
   - Added curl command to fetch recording IDs
   - Updated rate limit information

2. **workflows/process_fathom_meeting.md**
   - Corrected Fathom API endpoint
   - Updated Gemini model version (2.5 Flash)
   - Added recording ID format notes
   - Fixed all command examples
   - Updated schema validation notes

3. **README.md**
   - Added project-specific description
   - Added quick start section
   - Updated Python commands to use `python3`
   - Added recording ID retrieval instructions

4. **.env.example**
   - Added API endpoint information
   - Added authentication method notes
   - Added rate limit information
   - Added required scopes for Airtable

### Testing Results

#### Full Pipeline Test (Recording ID: 119611450)

**✅ All Steps Successful:**
- Step 1: Fetched transcript (403 segments) - 3s
- Step 2: Generated AI summary in Hebrew - 28s
- Step 3: Logged to Airtable (1 meeting + 7 tasks) - 8s

**Total Time:** 39 seconds

**Output:**
- Meeting: "סקירת תהליך ודרישות נתונים למערכת פיננסית"
- Tasks: 7 action items with Hebrew titles, descriptions, and context
- All with proper priority levels (High/Medium/Low)
- All linked correctly in Airtable

### API Endpoint Reference

| Service | Endpoint | Authentication | Rate Limit |
|---------|----------|----------------|------------|
| Fathom | `https://api.fathom.ai/external/v1` | `X-Api-Key: {key}` | 60 req/min |
| Gemini | Google AI SDK | API Key | 15 req/min, 1500/day |
| Airtable | `https://api.airtable.com` | Bearer Token | 5 req/sec |

### Configuration Summary

**Required Environment Variables:**
```bash
FATHOM_API_KEY=<your_key>
GOOGLE_GEMINI_API_KEY=<your_key>
AIRTABLE_API_KEY=pat<your_token>
AIRTABLE_BASE_ID=app<your_base_id>
AIRTABLE_MEETINGS_TABLE=Meetings
AIRTABLE_TASKS_TABLE=Tasks
```

**Airtable Required Scopes:**
- `data.records:read`
- `data.records:write`
- `schema.bases:read`

### Known Limitations

1. **Recording ID Discovery**:
   - Manual API call required to get recording IDs
   - Future enhancement: Create helper tool to list recent meetings

2. **Language Output**:
   - System outputs Hebrew by default
   - To change: Edit prompt in `tools/summarize_with_gemini.py`

3. **Python 3.9**:
   - Works but deprecated for Google libraries
   - Consider upgrading to Python 3.10+ for continued support

### Next Steps

1. **Automation**: Set up Fathom webhooks for automatic processing
2. **Helper Tool**: Create `list_meetings.py` to easily get recording IDs
3. **URL Parser**: Add tool to accept browser URLs and convert to recording IDs
4. **Batch Processing**: Test with multiple meetings to validate consistency

### System Status: ✅ Production Ready

All critical bugs fixed, documentation updated, and full pipeline tested successfully.
