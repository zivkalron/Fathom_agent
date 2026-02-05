# Fathom Meeting Automation Agent

A reliable AI agent system for processing Fathom meeting recordings, built on the **WAT architecture** (Workflows, Agents, Tools) that separates probabilistic AI reasoning from deterministic execution.

## What This System Does

Automatically processes Fathom video meetings to:
1. **Fetch transcripts** from Fathom API (`https://api.fathom.ai/external/v1`)
2. **Generate AI summaries** using Google Gemini 2.5 Flash (in Hebrew)
3. **Extract action items** with owners, priorities, and due dates
4. **Log to Airtable** with relational structure for searchability

## Architecture Overview

### The Three Layers

1. **Workflows** (`workflows/`)
   - Markdown-based Standard Operating Procedures (SOPs)
   - Define objectives, inputs, tools, outputs, and edge cases
   - Written in plain language for clarity and maintainability

2. **Agents** (AI Coordination Layer)
   - Intelligent orchestration and decision-making
   - Reads workflows, executes tools in sequence
   - Handles failures gracefully and asks clarifying questions

3. **Tools** (`tools/`)
   - Python scripts for deterministic execution
   - Handle API calls, data transformations, file operations
   - Consistent, testable, and fast

## Why This Architecture?

When AI handles every step directly, accuracy compounds: 5 steps at 90% each = 59% success rate. By offloading execution to deterministic scripts, the system maintains reliability while leveraging AI for orchestration and reasoning.

## Directory Structure

```
.
├── workflows/          # Markdown SOPs defining what to do and how
├── tools/             # Python scripts for deterministic execution
├── .tmp/              # Temporary files (regenerated as needed)
├── .env               # API keys and environment variables (gitignored)
├── credentials.json   # Google OAuth credentials (gitignored)
├── token.json         # Google OAuth token (gitignored)
├── CLAUDE.md          # Agent instructions and framework documentation
└── README.md          # This file
```

## Setup

1. **Clone the repository**
   ```bash
   git clone <your-repo-url>
   cd <project-directory>
   ```

2. **Set up Python environment**
   ```bash
   python3 -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   pip3 install -r requirements.txt
   ```

3. **Configure environment variables**
   ```bash
   cp .env.example .env
   # Edit .env and add your API keys
   ```

4. **Set up Google OAuth (if needed)**
   - Place your `credentials.json` in the project root
   - Run a tool that requires Google authentication to generate `token.json`

## Usage

### Quick Start

```bash
# Process a single meeting
python3 tools/process_meeting.py <RECORDING_ID>
```

**Getting Recording IDs:**
```bash
# List your recent meetings
curl -H "X-Api-Key: YOUR_FATHOM_API_KEY" \
  "https://api.fathom.ai/external/v1/meetings?limit=5"
```

**Note**: Use the `recording_id` field from the API, not the browser URL's call ID.

### Detailed Setup

See [SETUP.md](SETUP.md) for complete setup instructions including:
- API key configuration
- Airtable base structure
- Testing individual tools
- Troubleshooting

### Available Workflows

1. **Process Fathom Meeting** (`workflows/process_fathom_meeting.md`)
   - Full pipeline: fetch → summarize → log to Airtable
   - Processing time: ~30-40 seconds per meeting
   - Output: Hebrew summaries with action items

## The Self-Improvement Loop

1. Identify what broke
2. Fix the tool
3. Verify the fix works
4. Update the workflow with the new approach
5. Move on with a more robust system

## Development Principles

- **Deliverables** go to cloud services (Google Sheets, Slides, etc.)
- **Intermediates** are temporary and regenerated as needed
- Everything in `.tmp/` is disposable
- Never store secrets outside `.env`
- Check for existing tools before building new ones
- Keep workflows current as you learn

## Contributing

When adding new functionality:

1. Create or identify the relevant workflow in `workflows/`
2. Build deterministic tools in `tools/`
3. Update workflows with learnings and edge cases
4. Test thoroughly before committing

## License

[Add your license here]
