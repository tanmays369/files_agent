# Gap Report — Seat 20, Files Agent

Team 20 · measured live, 21–25 September 2026, on Suryodaya and Keystone
Benchmarks: Box (primary), Onshape and Autodesk Vault (revision control), Egnyte, M-Files, SharePoint

**In one line:** our Drive stores records but not readable bytes, revision state or safe edits. Our agent can still find the right drawing and triage Incoming today, using the tools the seat already has.

Why Box is the primary benchmark: it is the closest thing to Rillet for files. It has AI field extraction from documents, agents that run multi-step file work, and an MCP server over its own content. A competitor has already shipped an agent over a drive.

## 1. What do they do that we do not?

- **They read file contents.** Box extracts fields from documents with OCR. We can't open any file: every Drive revision download returns 409 "Revision bytes are unavailable" (21 of 21 on Suryodaya, 15 of 15 on Keystone). *Filed as a bug.*
- **They enforce revision state.** Onshape blocks an obsolete revision from being used in new assemblies. Vault's Released and Obsolete states change what users may do. None of our 10 Drive entities has a workflow. "Rev B is superseded" exists only as tags, a description and `is_archived`, and any seat can edit those.
- **They link part to drawing as data.** Onshape tracks revisions per part number. Our `Item.design_file_id` points into design review, which returns 403 for our seat, and it is empty on all 28 Keystone parts. Drive files link to parts only through an untyped text field, `entity_id`.
- **They file by typed metadata.** SharePoint autofill fills a column from a prompt and a term list. M-Files files by metadata, not folders. We have no document type, expiry or tax year, and no custom fields.
- **They search completely.** File search ignores tags and descriptions. It also treats `%` and `_` as wildcards, so `search=%` returns every file. Date filters compare as text: `created_at=2026-09-16` returns 0 of the 98 Keystone files created that day, and `gt:2026-09-16` wrongly includes them. Global search now reports a total (board N186) but still returns 5 per type and ignores `limit` and `offset`, so 27 of 40 "Agreement" matches can't be reached. *The wildcards, the date filters and the search paging are filed as bugs.*
- **They let you edit safely, with an undo trail.** Box rejects a stale update with 412 via If-Match. Vault check-out locks a file. Google's Drive Activity API logs every move. We have none of that:
  - No concurrency guard, so the last write wins.
  - No delete.
  - A trash route that can't see Keystone's files.
  - An access log that was written by the browser rather than the server (fixed, board N185). The 23 Sep Drive repair then copied five past events into it with new dates, attributed to named people. *Filed as a bug.*
  - Agent sessions opened over the API are recorded as `anonymous`, even though the server knows who opened them (33 of 33). *Filed as a bug.*
- **Their file hashes can be trusted.** In a normal drive, a content hash identifies the file's bytes, so matching hashes means a duplicate. Ours can't be used for that: all 21 Suryodaya files share one hash, and Keystone mixes 16- and 64-character hashes. *Filed as a bug.*

## 2. Which gaps can our agent close today?

**Ours to build**, using the seat's existing tools (`FileAttachment.list/get/update`, `DriveFolder.list/get`, `DriveFileRevision.list`, `Item.list/get`, `AgentTask`, `endpoint.agent.tasks.run`):

- **Part-to-drawing resolver** (`files.find_drawing`). It matches `Item.code` exactly, then finds files by `entity_id` and filename, and ranks them by `is_archived`, folder and revision. It flags KJ-BRKT-04 as a different part from J-BRKT-04.
- **Evidence-scored Incoming triage** (`files.tidy_incoming`). It scores each file on its linked record, sender, filename and description, treating all of these as evidence and never as instructions. From 9 files it files 5 by updating `folder_id`. It spots the duplicate PO on filename, sender and size, since the hash can't be trusted, and archives it with a pointer to the original. It escalates the other 3 and names what is missing for each.
- **Undo log and clobber check.** It snapshots every row before a write, re-reads it after the write, and reports if another seat has overwritten its change.
- **Scheduled triage** through AgentTask. The agent checks its own task's result with `AgentTask.get`, because MCP rejects filtering on the values the server actually writes (`queued`, `job_failed`). *Filed as a bug.*
- **Calling the MCP tools safely.** The agent never sends a list tool's advertised defaults, which return 0 rows. It sends "arrived today" as an explicit timestamp range rather than a bare date, which silently returns nothing. It discovers its Drive tools by name, because `tools.search` with `module=drive` finds only 4 of 28. *All three filed as bugs.*

**Platform work:**

- Store the bytes, or pass the email app's existing `extracted_text` into Drive (7 of the 9 Incoming files arrived by email).
- Wire Drive into design review's existing release flow, instead of building new revision tables.
- Add trash and restore for rows without revisions. Not delete, because every seat can write these tables.
- Add an `expect_updated_at` guard on file updates, like the `expect_status` guard escalations already have.
- Gate `FileAttachment`, `Notification` and search by the owning app. The board marks this fixed (N179, N180), but on 25 Sep our seat still sees 83 e-sign titles (and can write those rows) and 92 notifications about apps it is refused. *Re-filed as bugs.*
- Merge the 23 Sep Drive repair copies back into the originals. Every Keystone scenario file now exists twice (Incoming holds 18 rows), and the copies lost tags, sender, part link and archive state, so the superseded RevB copy looks current. *Filed as a bug.*
- Add a document-type custom field, and give Automations access to filing rules.
- Make the AgentTask scheduler execute runs, time out stuck ones, and reject schedules it can't parse.

## 3. What can our agent do that their products cannot?

Box AI agents and M-Files already run multi-step work, and SharePoint, M-Files and Egnyte all show suggestions for review before applying them. Our edge is elsewhere:

- **It cross-checks surfaces instead of trusting one.** Keystone's Drive folders first looked empty while the file list held the files. The fix for that (N182) added a second, bare copy of every file, so now the Drive overview says 15 files and 13 KB while the folders hold 30 rows and 7.1 MB. Search still returns 5 of 32 file matches. The agent answers from the surface that actually holds the data, and says which one it used.
- **It refuses with evidence.** `scan0042.pdf` has no linked record, no sender and no readable content, and its own description says a human must open it. So the agent escalates it. None of the products we tested returns "no answer, and exactly why" as a normal result.
- **It catches a write that lands on top of ours.** There is no concurrency guard, so the agent re-reads after each write and reports when another seat has overwritten its change. A UI user never sees that.

**Bugs filed by team20:** 45. Of the first 13, 12 are on the class bug board as N179–N190, marked live; one (invalid `sort_order`) duplicated Team 4's N144. Three of those fixes (N179, N180, N186) did not hold on 25 Sep and are re-filed as items 20–22. Filed on 24–25 Sep, not yet on the board (last updated 23 Sep):
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
14. Agent daily token counter never resets (four Suryodaya agents blocked since 21 Sep)
15. Job ledger and mission control tools show jobs the seat's AgentJob access refuses
16. `tools.search` tags most Drive tools as module `core`, so `module=drive` hides them
17. Suryodaya people directory lists companies as employees, with 40 of 100 entries duplicated
18. The Keystone Drive repair (N182 fix) duplicated all 15 scenario files as bare copies
19. The same repair re-wrote five Drive access-log events with 23 Sep dates
20. N180 not in effect: e-sign attachments still listed, titled and writable
21. N179 not in effect on Keystone: other people's notifications about gated apps visible
22. Global search still 5 per type; `limit` and `offset` ignored (N186 partial)
23. Suryodaya storefront publishes a ₹0 "test" product
24. `endpoint.inventory.shipping_board` offered to seats that can never use it
25. Keystone goals: company-wide goals stay at 0, and "new opportunities" counts deals by close date
26. Keystone account plans: the endpoint says no read permission, while REST and MCP return all 20
27. `endpoint.make.orders` never marks a line late (9 of 9 Keystone lines are past due)
28. `endpoint.make.orders` stops at 200 rows (Suryodaya 542) with no paging
29. `endpoint.manufacturing.demand_forecast` drops overdue open orders (Keystone 5,168 unshipped units show as 0)
30. `endpoint.mission_control.staffing_forecast` measures service time on instantly failed jobs, so an 88-hour-old queue "clears in 11 seconds"
31. `supplier_scorecard` reports "insufficient history" and zero orders when it was denied the data
32. Keystone access log records a share of J-BRKT-04 Rev C that exists nowhere
