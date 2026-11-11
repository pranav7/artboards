# Lo-fi journey boards

A journey board is one canvas of rough wireframes. Screens sit in numbered regions,
labelled arrows join them, and a side panel lists the user journeys. When the reviewer
moves the pointer over a journey, the board shows that path and fades the rest.

Use a board to agree two things before anyone draws a real screen: the journeys, and
what each screen shows.

## Procedure

1. **Problem.** From the conversation, write 2 to 4 sentences: who the user is, what goes
   wrong for them today, and why the change matters now.
2. **Journeys.** Write 4 to 10 journeys. Make each one a short phrase that starts with a
   verb, in the user's words: "Return a tool". Send the list to the user, and get a yes
   before you draw.
3. **Regions and screens.** List the parts of the product that the change touches. These
   are the regions. List the screens in each region. Put `new` on each screen that does
   not exist yet.
4. **Draw.** Run `artboards guide lofi` for the tags and their attributes. Then write the
   board:
   - Use real copy everywhere: real names, real numbers, real button labels. Do not use
     placeholder text.
   - Give each screen one primary button.
   - Put each point that is not decided in a `wf-question`. Do not decide it silently.
   - Write a `wf-prose` section for each region. Say why the region works the way it does.
5. **Options.** When there are two real ways to do the work, draw two boards ("Option A"
   and "Option B"). Do not draw one board that shows both.
6. **Check.** Run `artboards check` until it shows 0 errors. Read the warnings, and fix
   the ones that are real.
7. **Look.** Run `artboards shot` on the board. Run it again with `#journey=N` for two of
   the journeys. Open the PNGs and look at them. A clean check does not mean a clean
   layout: render the board wide (`--width 2400`) and look at close-ups of each decision
   and of each place where arrows meet.
8. **Hand over.** Give the user the URL, the list of journeys, and the open questions. Set
   the state to `open` while questions remain.
9. **After agreement.** Set the state to `agreed`. Then draw hi-fi artboards for the
   screens where the look matters (see [hifi.md](hifi.md)). Name each one after the lo-fi
   screen that it details, and put the screen id in its note.

## The board file

A board loads the kit from the server by absolute path:

```html
<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Borrow flow</title>
<link rel="stylesheet" href="/_kit/lofi.css">
<script src="/_kit/lofi.js"></script>
</head>
<body>
<wf-board name="Tool library - Option A">
  ...
</wf-board>
</body>
</html>
```

For a complete board, see `examples/tool-library/1-Tool-library.html` in the repository.

## Rules that the check does not catch

- Use `name`, not `title`, on every tag. The `title` attribute shows a browser tooltip.
- Write every list attribute with commas: `items="Home, Search, Borrowed"`.
- Make each id unique across the whole board.
- Do not set pixel positions. Put screens on the grid of their region with `col` and
  `row`.
- The kit draws a link between regions that are not next to each other as two short stubs.
  Give a link `stub` yourself when it jumps far or runs backward inside or between
  neighbouring regions. A full arrow that crosses most of a region shares lanes with other
  arrows. Two stubs ("to Target" and "from Source") stay short.
- A control inside a screen, such as a button in a modal, can only leave sideways. When the
  target is above or below, the arrow loops around the side of the screen. Draw the link
  from the screen instead: its bottom edge to the next screen's top edge is a short
  straight arrow.
- Keep the name of a decision short: about 3 words, such as "Papers found?". A long
  question does not fit the diamond.
- Keep notes out of the path of arrows. A `wf-note` sits under its screen, so an arrow that
  leaves the bottom of that screen runs through the text. Leave from the side, or put the
  note on the other side with `col` and `row`.
- A decision has four corners. When more than two arrows meet at it, give each its own
  corner with `exit` and `enter`.
- Keep the board grayscale. The kit uses blue for the journey highlight and red for open
  questions. Do not add other colours.

## What the check finds

`artboards check` opens the board in a headless browser and prints each problem with
its level. Fix every error. The message names the element:

```
error  link home-search -> serach: no element has id "serach"
```

| Code | Level | Cause |
| --- | --- | --- |
| `unknown-tag` | error | A `wf-` tag that the kit does not have, such as `wf-buton` |
| `misplaced-tag` | error | A region, link, journey, prose, problem or summary that is not directly inside `wf-board` |
| `duplicate-id` | error | Two elements have the same id |
| `missing-id` | error | A link, a journey step, a `for` or a prose `region` names no element |
| `no-link` | error | Two neighbouring journey steps have no link between them |
| `ambiguous-step` | error | Two links join a pair of steps, and the step does not name one with `@` |
| `cell-taken` | error | Two items in one region have the same `col` and `row` |
| `overlap` | error | Two screens overlap |
| `overflow` | error | Text is too long for its part or its screen, or the name of a decision spills out of its diamond |
| `arrow-crosses-screen` | error | An arrow goes through a screen that is not one of its ends |
| `arrow-crosses-note` | error | An arrow goes through a note or a question |
| `arrow-overlap` | error | Two arrows run along the same lane, so they look like one arrow |
| `console-error` | error | The page has a script error |
| `kit-error` | error | The kit failed while it drew the board |
| `arrow-crosses-arrow` | warn | Two arrows cross. Some crossings cannot be avoided; look at each one |
| `label-overlap` | warn | An arrow label covers another label or a note |
| `unreached-screen` | warn | No link goes to or from a screen |
| `screen-not-in-journey` | warn | No journey uses a screen |
| `two-primaries` | warn | A screen has more than one primary button |
| `open-questions` | info | The number of open questions |
