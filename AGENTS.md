# Public package workspace

This directory contains only reusable Skill instructions, helpers, blank templates and synthetic examples. Keep personal identities, chat excerpts, mail, transcripts, credentials, local absolute paths and thread IDs outside the repository.

Use synthetic fixtures and temporary directories for tests. Packaging work must not operate live messaging apps or send messages. Do not create a remote, push, publish, or modify another installation unless the user explicitly requests it.

Keep the Skill self-contained. Host agents provide Computer Use, models, session coordination and scheduling; this repository does not implement an agent service. Update documentation when helper paths or configuration contracts change.
