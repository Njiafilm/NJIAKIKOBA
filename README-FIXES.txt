NJIAKIKOBA — UPDATED BUILD

Fixes included:
- Registration code normalized to NK-0001, NK-0002, ...
- Tanzania phone input accepts +255..., 0..., 6..., and 7... and stores canonical 255XXXXXXXXX.
- Certificate page added so “Ona Cheti Chako” no longer hits missing-template/server error.
- Developer access is not linked or named in public UI; /developer-room remains private.
- Developer Room includes group upgrade (up to 9,999 members), group WhatsApp links, and safe software/hardware diagnostic commands.
- Each group has its own WhatsApp Group URL field; public group chat only opens that group’s link.
- Back button added across pages.
- Password show/hide added to authentication forms and Developer payment settings.
- Select boxes are styled for easier tapping/selection on mobile.
- Existing safe repair center remains non-arbitrary: it never exec()s generated code.

Deployment:
- Install requirements.txt.
- Set SECRET_KEY and DEVELOPER_PASSWORD_HASH in production.
- Set DATABASE_PATH to a persistent database path if using SQLite, or adapt db() for PostgreSQL.
- Set payment/Jitsi environment variables as required.

- Homepage mobile hero layout/contrast repair: hero image remains the first full-width visual, hero text/login content stays below it with readable dark/gold styling, and horizontal overflow is prevented.
