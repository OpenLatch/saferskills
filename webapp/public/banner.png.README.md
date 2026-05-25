Generate the real `banner.png` from the Gemini Nanobanana prompt in
`.local/.brainstorms/foundation/plan/03-ci-cd-and-ops.md` § Banner image.
Drop it here at `webapp/public/banner.png` (1280×640 PNG, sRGB).

Used as:
- The README hero image at the repo root
- The GitHub social preview (uploaded via `gh api -X PUT /repos/.../properties/...`)
- The OpenGraph + Twitter card image (referenced from `webapp/src/layouts/Base.astro`)
