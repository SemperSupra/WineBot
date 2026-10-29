# WineBot actual ObserverService legacy API regression witness (read-only)
Base: exact committed synthetic consolidated regression baseline 9a564b32cfcc22b40e01b56ba10250efe379e0be.
This independent workcell runs the eight unchanged, historical actual-service unit tests. They predate the new internal observer receipt interface and the owner factory does not accept the new kwargs. Expected failing tests are intentionally retained as FIRST FAILURES and are NOT justification to relax owner/source admission.
No production source, process command, binary, arbitrary application, data, control, image or artifact modification. Public $0 GHA read-only CPU runner; record precise tests, failed assertions and counts. No auto-restart, merge, release or owner-gate promotion.
