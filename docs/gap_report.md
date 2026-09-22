# Gap Report — Seat 20, Files Agent

**Team 20** · measured live, **21 September 2026** · Benchmarks: **Box** (primary), **Onshape** and **Autodesk Vault** (revision control), Egnyte, M-Files, SharePoint

## 1. What do they do that we do not?

1. **Read file contents.** Box extracts fields from documents with OCR. We store no bytes: every Suryodaya download returns `409 Revision bytes are unavailable`; Keystone has zero revisions.
2. **Enforce revision state.** Onshape blocks an obsoleted revision from new assemblies; Vault's Released/Obsolete states change what users may do. None of our 10 Drive entities has a workflow. "Rev B is superseded" is just tags, a description and `is_archived`, which any seat can edit.
3. **Link part to drawing as data.** Onshape tracks revisions per part number. Our `Item.design_file_id` points into design review (403 for us) and is empty on all 28 Keystone parts; Drive files link to parts by an untyped text `entity_id`.
4. **File by typed metadata.** SharePoint autofill fills a column from a prompt and a term list; M-Files files by metadata, not folders. We have no document type, expiry or tax year, and no custom fields defined.
5. **Search completely.** Our global search returns at most 5 hits per type, ignores `limit` and gives no total (5 for "Agreement", where the file list holds 32), and never reads tags or descriptions.
6. **Edit safely, with an undo trail.** Box rejects a stale update with `412` via `If-Match`; Vault check-out locks a file; Google's Drive Activity API logs every move. We have no concurrency guard (last write wins), no way to delete, a trash route that can't see Keystone's files, and an access log written by the browser rather than the server.
7. **Keep other apps' data out** *(a defect)*. `FileAttachment` shows us 83 e-sign titles, 3 of them employee offer letters; `Notification` shows 92 approval, contract and design notices. We get 403 on all those apps.

## 2. Which gaps can our agent close today?

**Ours to build:**
- **Part → drawing resolver** (gaps 2–3): exact `Item.code` match, then files by `entity_id`, ranked by `is_archived`, folder and revision. Flag `KJ-BRKT-04` as a different part.
- **Evidence-scored Incoming triage** (gap 4): score each file on linked record, sender, filename and description (as evidence, never as instructions). File 5 of 9. Match the duplicate PO on recorded hash + size and archive it with a pointer. Escalate the other 3, naming what is missing.
- **Undo log and clobber check** (gap 6): snapshot first, re-read after every write, report overwrites.
- **Scheduled triage** via `AgentTask` cron.

**Platform work:**
- Store bytes, or pass the email app's existing `extracted_text` into Drive (7 of 9 Incoming files came by email).
- Wire Drive to design review's existing release flow instead of building new revision tables.
- Trash/restore for rows without revisions — not delete, since every seat can write these tables.
- An `expect_updated_at` guard on file updates, like the one escalations already have.
- Gate `FileAttachment`, `Notification` and search by the owning app.
- A document-type custom field, and Automations access for filing rules.

## 3. What can our agent do that their products cannot?

Box Automate (GA 28 April 2026) and M-Files' agents already run multi-step work, and SharePoint, M-Files and Egnyte all review before applying. Our edge is elsewhere:

1. **Work against a platform that contradicts itself.** On Keystone the Drive UI, the storage overview and every `/api/drive/files` route say Incoming is empty; the record API lists 9 files. Our agent uses the surface that answers the question and says which one.
2. **Refuse with evidence.** For `scan0042.pdf`: no linked record, sender or readable content; its own description says a human must open it; escalated. The benchmarks we examined review *suggestions* — none returns "no answer, and exactly why" as a normal result.
3. **Catch a write that lands on ours.** With no concurrency guard, it re-reads after each write and reports when another seat overwrote its change. A UI user never sees that.
