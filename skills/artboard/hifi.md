# Hi-fi artboards

A hi-fi artboard shows one screen, or one state of a screen, in the product's real look.
Use it after the flow is agreed, to agree how the screen looks.

For an example, see `examples/tool-library/2-Tool-page.html` in the repository.
`artboards status` prints where the repository is.

## Before you draw

- Read the product's real design tokens and components: colours, type sizes, spacing,
  radii, icons and the main controls. Draw with them. Do not make up a new look for a
  product that has one.
- Draw at the real width of the screen: 390px for a phone, the real pane width for a
  desktop app.
- If a lo-fi board exists, read the screen that you detail. Use its copy, and keep its
  open questions open.

## The file

- One self-contained HTML file for each screen or state. Name it in reading order:
  `2-Tool-page.html`, `3-Tool-page-out.html`.
- No build step, no framework, and no external assets. A font stylesheet from Google
  Fonts is the one exception. Draw icons and images with inline SVG or CSS.
- Define every colour as a token on a bare `:root`. Define the same tokens again inside
  `@media (prefers-color-scheme: dark)`. A token that is defined only in the dark block
  shows the wrong colour in light mode, and the check reports it as `dark-only-token`.
- Give `body` an explicit background from a token. A transparent body takes the colour
  of the page that contains it. The check reports it as `transparent-body`.
- Do not put double quotes inside a `style` attribute. Font names are the usual cause.
  Write `font-family: 'SF Pro Text', sans-serif`.

## The layout of an artboard

1. A heading and one paragraph of context: which screen, which state, and the width.
2. When you change an existing screen: "Today" and "Proposed", side by side or one above
   the other. Draw "Today" from the real product, not from memory.
3. Numbered callouts on the "Proposed" drawing, in one accent colour. Each number
   matches a numbered note next to or under the drawing. A note says what changed and
   why, in one or two sentences.
4. Optional: a short line on what stays the same.

For a new screen, draw only "Proposed".

## Checklist for each artboard

Keep a short list of checks for each artboard, and run them with `grep` after each pass.
The check and the screenshot do not find a wrong word. Typical checks:

- Each word that the reviewer retired appears zero times.
- Each label that must appear is present the expected number of times.
- Each button that shows only an icon has an `aria-label` and a `title`.
- Controls in one row have the same explicit height and `box-sizing: border-box`.
- No em dash appears in the file.

## Before you hand over

1. Run `artboards check <file>` until it shows 0 errors.
2. Run `artboards shot <file>` and `artboards shot <file> --dark`.
3. Open both PNGs and look at them. Fix what looks wrong, and do steps 1 and 2 again.

## When an artboard changes

When the reviewer changes the artboard that is the specification for some content, each
other artboard that shows the same content is stale. Find those artboards, and update
them or mark them `dropped`. Do not wait for the reviewer to find them.

When you hand the design to the people who build it, refer to artboards by path. Say
which artboard is the specification for each behaviour, so a reader knows which file is
correct when two artboards disagree.
