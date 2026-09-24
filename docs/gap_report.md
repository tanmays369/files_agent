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
- **They search completely.** File search ignores tags and descriptions. It also treats `%` and `_` as wildcards, so `search=%` returns every file. Date filters compare as text: `created_at=2026-09-16` returns 0 of the 98 Keystone files created that day, and `gt:2026-09-16` wrongly includes them. *The wildcards and the date filters are filed as bugs.* Global search used to cap at 5 hits per type; we reported it and it is now fixed (board N186).
- **They let you edit safely, with an undo trail.** Box rejects a stale update with 412 via If-Match. Vault check-out locks a file. Google's Drive Activity API logs every move. We have none of that:
  - No concurrency guard, so the last write wins.
  - No delete.
  - A trash route that can't see Keystone's files.
  - An access log that was written by the browser rather than the server. *We reported it; now fixed (board N185).*
  - Agent sessions opened over the API are recorded as `anonymous`, even though the server knows who opened them (33 of 33). *Filed as a bug.*
- **Their file hashes can be trusted.** In a normal drive, a content hash identifies the file's bytes, so matching hashes means a duplicate. Ours can't be used for that: all 21 Suryodaya files share one hash, and Keystone mixes 16- and 64-character hashes. *Filed as a bug.*

## 2. Which gaps can our agent close today?

**Ours to build**, using the seat's existing tools (`FileAttachment.list/get/update`, `DriveFolder.list/get`, `DriveFileRevision.list`, `Item.list/get`, `AgentTask`, `endpoint.agent.tasks.run`):

- **Part-to-drawing resolver** (`files.find_drawing`). It matches `Item.code` exactly, then finds files by `entity_id` and filename, and ranks them by `is_archived`, folder and revision. It flags KJ-BRKT-04 as a different part from J-BRKT-04.
- **Evidence-scored Incoming triage** (`files.tidy_incoming`). It scores each file on its linked record, sender, filename and description, treating all of these as evidence and never as instructions. From 9 files it files 5 by updating `folder_id`. It spots the duplicate PO on filename, sender and size, since the hash can't be trusted, and archives it with a pointer to the original. It escalates the other 3 and names what is missing for each.
- **Undo log and clobber check.** It snapshots every row before a write, re-reads it after the write, and reports if another seat has overwritten its change.
- **Scheduled triage** through AgentTask. The agent checks its own task's result with `AgentTask.get`, because MCP rejects filtering on the values the server actually writes (`queued`, `job_failed`). *Filed as a bug.*
- **Calling the MCP tools safely.** The agent never sends a list tool's advertised defaults, which return 0 rows. It sends "arrived today" as an explicit timestamp range rather than a bare date, which silently returns nothing. *Both filed as bugs.*

**Platform work:**

- Store the bytes, or pass the email app's existing `extracted_text` into Drive (7 of the 9 Incoming files arrived by email).
- Wire Drive into design review's existing release flow, instead of building new revision tables.
- Add trash and restore for rows without revisions. Not delete, because every seat can write these tables.
- Add an `expect_updated_at` guard on file updates, like the `expect_status` guard escalations already have.
- ~~Gate `FileAttachment`, `Notification` and search by the owning app.~~ *Done: we reported 83 e-sign titles (including 3 offer letters) and 92 notifications visible to our seat; both are fixed (board N179, N180).*
- Add a document-type custom field, and give Automations access to filing rules.
- Make the AgentTask scheduler execute runs, time out stuck ones, and reject schedules it can't parse.

## 3. What can our agent do that their products cannot?

Box AI agents and M-Files already run multi-step work, and SharePoint, M-Files and Egnyte all show suggestions for review before applying them. Our edge is elsewhere:

- **It cross-checks surfaces instead of trusting one.** During testing, Keystone's Drive folders looked empty while the file list held the files (board N182, now fixed), and search returned 5 of 32 matches (N186, now fixed). The same class of disagreement remains in the filters we filed today. The agent answers from the surface that actually holds the data, and says which one it used.
- **It refuses with evidence.** `scan0042.pdf` has no linked record, no sender and no readable content, and its own description says a human must open it. So the agent escalates it. None of the products we tested returns "no answer, and exactly why" as a normal result.
- **It catches a write that lands on top of ours.** There is no concurrency guard, so the agent re-reads after each write and reports when another seat has overwritten its change. A UI user never sees that.

**Bugs filed by team20:** 26. Of the first 13, 12 are fixed and live on the class bug board as N179–N190; one (invalid `sort_order`) duplicated Team 4's N144. The 13 filed on 24 Sep, not yet on the board (last updated 23 Sep):
1. MCP list tools advertise filter defaults that return 0 rows
2. Search treats `%` and `_` as wildcards
3. Every Drive revision download returns 409
4. `content_hash` does not identify content
5. Unparseable filter values return 0 instead of 400
6. Date-only filters compared as text against timestamps
7. API agent sessions recorded as anonymous
8. AgentProvider accepts out-of-range settings, with two defaults (junk model names overlap N57)
9. MCP enums omit values the server writes
10. Keystone AccountPlan rows missing their required links
11. Scheduled tasks count runs that produce nothing
12. AgentTask schedules not validated (cron tasks with no expression run hourly; the "Completed with 0 runs" part overlaps Team 24's N255)
13. SalesOrder.list advertises computed totals as filters, then refuses them
