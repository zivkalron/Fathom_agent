#!/usr/bin/env bash
# setup_webhook.sh — Register the Fathom webhook endpoint (one-time).
#
# Run this AFTER deploying to Vercel.  The response includes a "secret"
# value that must be stored as FATHOM_WEBHOOK_SECRET in your Vercel
# environment variables.
#
# Usage:
#   export FATHOM_API_KEY="your_key_here"
#   bash setup_webhook.sh
#
# Or source your .env first (if it uses export):
#   source .env && bash setup_webhook.sh

set -euo pipefail

# ---------------------------------------------------------------------------
# CONFIGURATION — edit VERCEL_URL before running
# ---------------------------------------------------------------------------
VERCEL_URL="https://fathom-agent.vercel.app"
# ---------------------------------------------------------------------------

FATHOM_API="https://api.fathom.ai/external/v1"

if [[ -z "${FATHOM_API_KEY:-}" ]]; then
    echo "ERROR: FATHOM_API_KEY is not set."
    echo "  Run:  export FATHOM_API_KEY=your_key"
    exit 1
fi

DESTINATION="${VERCEL_URL}/api/webhook"

echo "Registering Fathom webhook..."
echo "  Destination: ${DESTINATION}"
echo ""

RESPONSE=$(curl -s -w "\n%{http_code}" \
  -X POST "${FATHOM_API}/webhooks" \
  -H "X-Api-Key: ${FATHOM_API_KEY}" \
  -H "Content-Type: application/json" \
  -d "{
    \"destination_url\": \"${DESTINATION}\",
    \"triggered_for\": [\"my_recordings\"],
    \"include_transcript\": true,
    \"include_summary\": false,
    \"include_action_items\": false
  }")

HTTP_CODE=$(echo "$RESPONSE" | tail -n1)
BODY=$(echo "$RESPONSE" | sed '$d')

if [[ "$HTTP_CODE" != "200" && "$HTTP_CODE" != "201" ]]; then
    echo "ERROR: Fathom returned HTTP ${HTTP_CODE}"
    echo "${BODY}"
    exit 1
fi

echo "SUCCESS — webhook registered."
echo ""
echo "Response:"
echo "${BODY}" | python3 -m json.tool 2>/dev/null || echo "${BODY}"
echo ""
echo "============================================================"
echo "NEXT STEP: Copy the 'secret' field from the response above"
echo "and add it to your Vercel environment variables:"
echo ""
echo "  Vercel Dashboard → Settings → Environment Variables"
echo "  Name:  FATHOM_WEBHOOK_SECRET"
echo "  Value: (the secret value from the response)"
echo "============================================================"
