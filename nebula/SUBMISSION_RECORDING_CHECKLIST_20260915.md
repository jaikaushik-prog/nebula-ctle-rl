# Nebula recording and submission checklist

Deadline: **15 September 2026, 11:00 PM**. Plan around IST as the workspace timezone; the organiser email did not specify a timezone. Aim to have the package ready by **8:00 PM**, preserving a three-hour buffer. The owner records, reviews and sends the submission.

## Fill before submission

Team name: ________________________________________________

College name: ______________________________________________

| Member | Full name | Contact number | Email ID |
|---|---|---|---|
| 1 | ____________________ | ____________________ | ____________________ |
| 2 | ____________________ | ____________________ | ____________________ |
| 3 | ____________________ | ____________________ | ____________________ |

## Rehearse once

- [ ] Open `output/docx/Nebula_Final_Demo_Script_20260915.docx` and `output/pdf/Nebula_Final_Submission_12p_20260915.pdf`. The script also exists as `nebula/SUBMISSION_FINAL_DEMO_SCRIPT_20260915.md`.
- [ ] Open the existing local app at `http://127.0.0.1:8765`. Avoid launching another server if this one works.
- [ ] If the app is unavailable, start it from the repository root with `py -3.13 -m nebula.web --port 8765 --run-root nebula/product_demo/submission_runs_20260914 --no-browser`, then open `http://127.0.0.1:8765`. This durable saved run has all 617 original registered file hashes verified; it does not require regeneration.
- [ ] Select the completed 3 dB / 1.9 GHz physical run `ab981d69dac840e9820155d7e46e14dc`. Check measured 3.910115 dB / 2.131144 GHz and 315/315 model conditions before rehearsing.
- [ ] Visit Design Explorer, Design PVT, Compare circuits and Run files. In Compare circuits choose the physical run as Circuit A; confirm eye overlay and margin-envelope modes load.
- [ ] Expand the separate 9 dB / 1.9 GHz transistor checkpoint. Keep its identity distinct from the selected generated CTLE.
- [ ] Keep report pages 2, 3, 4, 8, 9, 10 and 12 easy to reach. The saved automation receipt on page 10 describes an earlier 9 dB adaptive run, not the selected 3 dB physical run.
- [ ] Read the 608-word narration at a comfortable pace and include pauses for the clicks. The 5:40 cues are a plan, not a measured video duration; rehearse to finish within the owner's chosen 5-6 minutes.
- [ ] If over six minutes, shorten pauses and omit the extra Sizing/Specs clicks. Preserve the distinction between modeled and physical results and the final scope statements.

## Record

- [ ] Plug in power, close unrelated windows, silence notifications and move personal information off screen.
- [ ] Use a desktop viewport similar to the reviewed 1440 x 1000 or 1280 x 900 layouts. Record at a resolution where circuit values and result labels are readable. No organiser resolution/codec rule was supplied.
- [ ] Make a 10-second microphone test. Play it back and check level, clarity and absence of clipping before the full take.
- [ ] State that the walkthrough uses saved completed evidence. Open New target to show input, then close it; do not imply a fresh optimization ran during the take.
- [ ] Follow the six scenes in order. Pause after clicks. If a sentence goes wrong, stop briefly and repeat it so it can be trimmed.
- [ ] Do not read filenames, run IDs or hash strings aloud. Use them for verification and show the report's artifact guide when needed.
- [ ] Save the original recording before editing. Suggested final filename: `Nebula_Final_Demo_20260915.mp4`. This is a proposed filename; no video has been created or reviewed by producing this checklist.

## Review the actual export

- [ ] Play the exported file from beginning to end, including the final seconds.
- [ ] Verify audible speech, screen/text readability, useful cursor movement, correct sequence and no accidental private content.
- [ ] Check actual duration is 5-6 minutes, or explicitly choose a different duration if needed. The organiser supplied no maximum duration.
- [ ] Check the saved-run labels remain visible and the 3 dB physical, 9 dB adaptive receipt and 9 dB integrated checkpoint are not confused.
- [ ] Confirm the report shown is the final 12-page file, and all spoken numbers agree with it.
- [ ] Verify the final file opens after copying to the submission location. Record its full path and size below.

Video file path: ____________________________________________________

Duration: ____________________    File size: ____________________

Reviewed by: ____________________    Review time: ____________________

## Prepare the sendable package

- [ ] Fill team/college/member/contact information and rebuild or fill the report cover as appropriate. Recheck its page count and readability afterward.
- [ ] Include the final **10-12 total page** report and the reviewed project demo video. The 25-page detailed edition is preserved background, not the page-compliant submission.
- [ ] Use `nebula/SUBMISSION_EMAIL_DRAFT_20260915.md`. Recipient: `nebula@asteralabs.com`; subject: `Nebula – Final Submission`.
- [ ] Attach the final PDF and video, or use a video link only after confirming the recipient can access it. The supplied email specified no attachment-size limit or required link service.
- [ ] If using a link, test it from a signed-out/private browser and make sure it points to the final reviewed file. Do not upload PDKs, copyrighted references, organiser handouts or private contact sheets to the public repository.
- [ ] Owner reviews the exact recipients, subject, attachments/link and member details, then sends before the deadline. Save the sent-message confirmation and attachment/link identities.

Submission sent at: ____________________

Report filename: `Nebula_Final_Submission_12p_20260915.pdf`

Video filename or accessible link: ___________________________________
