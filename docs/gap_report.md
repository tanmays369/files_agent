# Gap Report — Seat 20, Files Agent

Team 20 · measured live, 21–24 September 2026, on Suryodaya and Keystone
Benchmarks: Box (primary), Onshape and Autodesk Vault (revision control), Egnyte, M-Files, SharePoint

**In one line:** our Drive stores records but not readable bytes, revision state or safe edits. Our agent can still find the right drawing and triage Incoming today, using the tools the seat already has.

Why Box is the primary benchmark: it is the closest thing to Rillet for files. It has AI field extraction from documents, agents that run multi-step file work, and an MCP server over its own content. A competitor has already shipped an agent over a drive.

## 1. What do they do that we do not?

- **They read file contents.** Box extracts fields from documents with OCR. We can't open any file: every Drive revision download returns 409 "Revision bytes are unavailable" (21 of 21 on Suryodaya, 15 of 15 on Keystone). *Filed as a bug.*
- **They enforce revision state.** Onshape blocks an obsolete revision from being used in new assemblies. Vault's Released and Obsolete states change what users may do. None of our 10 Drive entities has a workflow. "Rev B is superseded" exists only as tags, a description and `is_archived`, and any seat can edit those.
- **They link part to drawing as data.** Onshape tracks revisions per part number. Our `Item.design_file_id` points into design review, which returns 403 for our seat, and it is empty on all 28 Keystone parts. Drive files link to parts only through an untyped text field, `entity_id`.
- **They file by typed metadata.** SharePoint autofill fills a column from a prompt and a term list. M-Files files by metadata, not folders. We have no document type, expiry or tax year, and no custom fields.
- **They search completely.** Global search caps at 5 hits per type (5 for "Agreement", where the file list holds 32). File search ignores tags and descriptions. It also treats `%` and `_` as wildcards, so `search=%` returns every file. *The cap and the wildcards are filed as bugs.*
- **They let you edit safely, with an undo trail.** Box rejects a stale update with 412 via If-Match. Vault check-out locks a file. Google's Drive Activity API logs every move. We have none of that:
  - No concurrency guard, so the last write wins.
  - No delete.
  - A trash route that can't see Keystone's files.
  - An access log written by the browser rather than the server. *Filed as a bug.*
- **Their file hashes can be trusted.** In a normal drive, a content hash identifies the file's bytes, so matching hashes means a duplicate. Ours can't be used for that: all 21 Suryodaya files share one hash, and Keystone mixes 16- and 64-character hashes. *Filed as a bug.*

## 2. Which gaps can our agent close today?

**Ours to build**, using the seat's existing tools (`FileAttachment.list/get/update`, `DriveFolder.list/get`, `DriveFileRevision.list`, `Item.list/get`, `AgentTask`, `endpoint.agent.tasks.run`):

- **Part-to-drawing resolver** (`files.find_drawing`). It matches `Item.code` exactly, then finds files by `entity_id` and filename, and ranks them by `is_archived`, folder and revision. It flags KJ-BRKT-04 as a different part from J-BRKT-04.
- **Evidence-scored Incoming triage** (`files.tidy_incoming`). It scores each file on its linked record, sender, filename and description, treating all of these as evidence and never as instructions. From 9 files it files 5 by updating `folder_id`. It spots the duplicate PO on filename, sender and size, since the hash can't be trusted, and archives it with a pointer to the original. It escalates the other 3 and names what is missing for each.
- **Undo log and clobber check.** It snapshots every row before a write, re-reads it after the write, and reports if another seat has overwritten its change.
- **Scheduled triage** through AgentTask.
- **Calling the MCP tools safely.** The agent never sends a list tool's advertised defaults, which return 0 rows. *Filed as a bug.*

**Platform work:**

- Store the bytes, or pass the email app's existing `extracted_text` into Drive (7 of the 9 Incoming files arrived by email).
- Wire Drive into design review's existing release flow, instead of building new revision tables.
- Add trash and restore for rows without revisions. Not delete, because every seat can write these tables.
- Add an `expect_updated_at` guard on file updates, like the `expect_status` guard escalations already have.
- Gate `FileAttachment`, `Notification` and search by the owning app. *Filed as a bug: 83 e-sign titles, including 3 offer letters, and 92 notifications are visible to our seat.*
- Add a document-type custom field, and give Automations access to filing rules.

## 3. What can our agent do that their products cannot?

Box AI agents and M-Files already run multi-step work, and SharePoint, M-Files and Egnyte all show suggestions for review before applying them. Our edge is elsewhere:

- **It works against a platform that contradicts itself.** Different surfaces give different answers about the same files. The agent answers from the surface that actually holds the data, and says which one it used.
- **It refuses with evidence.** `scan0042.pdf` has no linked record, no sender and no readable content, and its own description says a human must open it. So the agent escalates it. None of the products we tested returns "no answer, and exactly why" as a normal result.
- **It catches a write that lands on top of ours.** There is no concurrency guard, so the agent re-reads after each write and reports when another seat has overwritten its change. A UI user never sees that.

**Bugs filed by team20:** 18 (5 on 24 Sep: MCP list defaults, search wildcards, revision downloads, `content_hash`, unvalidated filter values).
