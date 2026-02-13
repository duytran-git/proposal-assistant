# Proposal Assistant — User Guide

A Slack bot that turns your meeting transcripts into a Deal Analysis document and a Proposal Deck, all saved to Google Drive.

---

## What You Need

- Access to the Slack channel where the bot is installed
- A meeting transcript file (`.md`, `.txt`, or `.docx`)
- Optionally: a web URL with additional context about the client

---

## Step 1: Start a Deal Analysis

1. Open the Slack channel where the bot is active.
2. Attach your transcript file (drag and drop, or click the **+** button).
3. In the message field, type **Analyse** (with a capital A).
4. Send the message.

You can also paste a web URL in the same message for extra context. For example:

> **Analyse**
> https://example.com/client-info

The bot will reply with "Analyzing transcript..." — this usually takes about 30–60 seconds.

### What you'll get

- A **Deal Analysis** Google Doc saved in your client's Drive folder
- A link to view the document
- A list of any **missing information** the bot couldn't find in your transcript (e.g. budget, timeline)
- Three buttons: **Yes**, **No**, and **Regenerate**

---

## Step 2: Review the Deal Analysis

Open the Google Doc link and review the Deal Analysis. It covers:

- Opportunity snapshot
- Problem and impact
- Current vs. desired state
- Buying dynamics
- Renessai fit assessment
- Proof points and next actions

Check the "Missing information" list — if something important is missing, you may want to update the transcript and regenerate.

---

## Step 3: Choose What to Do Next

You have three options:

### Option A: Create the Proposal Deck

Click **Yes**. The bot will generate a 12-slide Google Slides proposal deck based on the Deal Analysis. This takes about 1–2 minutes. You'll receive a link to the deck when it's ready.

### Option B: Stop Here

Click **No**. The Deal Analysis stays in Google Drive, but no proposal deck is created. The workflow ends.

### Option C: Regenerate the Deal Analysis

Click **Regenerate**. The bot creates a new version of the Deal Analysis (v2, v3, etc.) as a separate document. The original version is kept for reference. You'll get the same review options again.

---

## Alternative: Skip Deal Analysis and Go Straight to a Proposal

If you already have a Deal Analysis document (`.md`, `.txt`, or `.docx`), you can skip the analysis step:

1. Attach your Deal Analysis file.
2. Type **Propose** in the message.
3. Send the message.

The bot will use your uploaded document to generate the Proposal Deck directly.

---

## Where Are My Files?

All generated documents are saved to Google Drive under:

```
Clients / {Client Name} /
├── Meetings/          ← your uploaded transcripts
├── Analyse here/      ← Deal Analysis documents
├── Proposals/         ← Proposal Decks
└── References/        ← supporting materials
```

The client name is extracted from your transcript filename. Documents are shared with all members of the Slack channel.

---

## Tips

- **File naming:** Name your transcript with the client name for better organization (e.g. `acme-corp-discovery-call.txt`).
- **Multiple transcripts:** You can attach more than one file in a single message. The bot will merge them.
- **English only:** The bot currently supports English transcripts only.
- **Stay in the thread:** All bot replies appear in the same Slack thread. Reply within the thread to keep the conversation organized.

---

## Troubleshooting

| Problem | What to do |
|---------|-----------|
| Bot doesn't respond | Make sure you typed **Analyse** (capital A) with a file attached |
| "Transcript file appears empty or invalid" | Check that your file is not empty and is `.md`, `.txt`, or `.docx` |
| "Lost track. Please start over" | Start a new message with **Analyse** and your transcript |
| "AI service temporarily unavailable" | Wait a moment and try again |
| "Failed to create proposal deck" | Click **Yes** again, or start over with **Analyse** |
