# Stage 4 — Continued Build

All frontend pages are complete (primary screen from stage 2, plus any extended pages from stage 3).

## 0. Deploy frontend (recommend first)

Before asking about further development, recommend deploying the frontend so the user can preview and share a live version.

Branch the recommendation on the user's Verdent surface (read from the `Verdent surface` field in the environment info):

### If `Verdent surface: desktop-app`

Recommend Vercel in simple words:

> "All frontend pages are ready. Would you like to deploy them online? I recommend deploying with Vercel."

Only after the user explicitly confirms they want to start deployment, deploy the project to Vercel directly. Do not list step-by-step GitHub/Vercel UI instructions — execute the deployment directly.

### If `Verdent surface: cloud-web` (cloud agents)

Do not recommend Vercel. Point the user to the built-in Publish flow in plain words:

> "All frontend pages are ready. To deploy them online, start the project, then click **Publish** in the top-right corner."

Do not run a Vercel deployment, do not connect GitHub, do not list extra UI steps. The Publish button is the deployment path on cloud-web.

### If the surface is unknown or any other value

Default to the `desktop-app` Vercel recommendation above.

### If the user skips

Proceed directly to the next question.

---

After deployment (or skip), ask whether they want to continue with further development:

> "Do you want to continue with the next steps — backend features, testing, and further development?"

- **Yes** → proceed with the sections below.
- **No** → stop here. The product is frontend-complete; end the workflow.

The user is a product builder. Keep wording simple and tied to outcomes. Do not say "stage 4" or use engineering jargon without a plain-language version.

## 1. Drive development from approved designs and spec

From here on, drive every decision from **all approved comps, generated image assets, and the product spec image** (if one was produced in stage 3).

- Match the product type the comps show. Mobile-app comps → build a mobile app. Website comps → build a website. Do not switch product types mid-build.
- If a non-system font appears in the comps, find the closest match on `https://fonts.google.com/` and reference that font.
- Use the corresponding SVG for icons (from HF mode) or hand-author SVG inline for standard fidelity.

## 2. Simple vs complex projects

**Simple projects with no spec image:** proceed directly with backend features based on the approved frontend and user direction.

**Complex projects with a spec image confirmed in stage 3:**
1. The frontend is already restored. **Automatically open the frontend preview** and confirm with the user that what they see matches what they approved.
2. Only after that confirmation, start backend work.

## 3. Frontend-complete handoff

When the visual frontend is complete, do not just say "done". Run the local preview, give the user the preview address, and summarize in plain words:

- Pages/screens restored.
- Motion and interaction states added.
- Responsive widths checked.
- Key generated assets wired in.
- Code checks already run.

Then ask what they want next with concrete options:

- "I can test this page for you now."
- "I can continue with the product features behind the page."
- "If you want to show it to others, I can help you publish / deploy it."

Never click Publish, open the cloud deployment flow, connect GitHub, deploy to cloud, connect paid services, or expose a public URL without explicit user confirmation.

## 4. Translate the spec into concrete tasks

Re-read the product spec image. Translate every item in the spec into a concrete development task. Common categories:

- Auth
- Data model
- API endpoints
- Payments
- Admin
- Real-time
- Notifications
- Queue / pipeline
- Role permissions

Show the task list to the user and confirm:
- **Priority** — what matters most.
- **MVP scope** — what's in version one.
- **What to do first.**
- **What to defer.**

Do not default to implementing everything at once.

## 5. Read the user's technical background

Before asking the user to make any technical decision, read the cues:

- **Clearly a technical developer:** confirm relevant tech choices with them (framework, database, auth provider, etc.).
- **Not a developer, or background unclear:** **do not** ask the user to make technical choices. Pick sensible defaults yourself, explain in plain words what you picked and why one sentence each. Builders hire AI to make these calls; making them choose burns trust.

## 6. After every completed task, return to the spec

For each implemented feature:
1. Check the corresponding bullet in the spec image.
2. Show the user which approved item this feature matches.
3. Explain in simple words what was built.
4. Ask whether it matches what the user expected.
5. Make the confirmation easy: "this matches what I approved" / "tweak this".

After each larger module is finished (when there is a spec image):
- Mark the completed product logic as **done** on the spec image (visually annotate it).
- Update the full spec view so it shows everything completed so far.
- Show the updated spec image or HTML view to the user.
- Use this as the running progress checkpoint — what's done, what's left.

If the user asks for module time estimates, estimate **AI development time**, not human team development time. Be explicit about that distinction so they can plan correctly.

## 7. Wrap-up sequence (ask in order, after development is complete)

### Analytics
Ask whether the user wants analytics instrumentation. Recommend **PostHog** when appropriate. Walk through setup in plain, step-by-step language.

### Testing
Ask whether testing is needed. If yes, run the right checks for the project — code quality checks plus tools like **Playwright** when appropriate. Explain the testing plan in simple words.

### Deployment
If the user did not deploy earlier (skipped in step 0), ask again whether they want to deploy now. Use the same surface-aware guidance from step 0 — Vercel for `desktop-app`, the top-right **Publish** button for `cloud-web`.

For very large requirements, keep checking in throughout the process — confirm direction often, do not let the build drift away from what the user approved.

## Common mistakes

| Mistake | Why it fails | Fix |
|---|---|---|
| Switching product type mid-build (mobile design → website) | Discards the user's approved direction. | Match the product type the comps show. |
| Asking a non-developer to choose a database / framework | Burns trust; they hired AI to make these calls. | Pick sensible defaults; explain plainly. |
| Implementing the entire spec in one shot | User cannot course-correct; rework is expensive. | Confirm priority and MVP scope first. |
| Skipping the post-task spec check-in | User loses sight of progress against what they approved. | After every feature, point to the spec item it satisfies. |
| Estimating in human-team time | Misleads a solo builder about timelines. | Estimate AI development time; say so explicitly. |
| Skipping the frontend preview confirmation before backend | Backend gets built on top of a frontend the user hasn't approved. | Open preview, confirm, then proceed. |
| Saying "done" after frontend restoration with no next step | User does not know whether to test, continue, or publish. | Offer testing, continued build, or publish/deploy options. |
| Publishing or deploying without confirmation | Public exposure and paid-service actions require user control. | Ask explicitly before clicking Publish, deploying, or connecting services. |
