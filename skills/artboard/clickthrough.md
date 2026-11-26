# Click-throughs

A click-through shows a flow in the product's real look, one state at a time. The app
renders in a frame at its real size. The reviewer clicks the controls in the frame to go
from step to step. A side panel lists the steps, says what to click next, says what is new
in each step, and shows the open questions.

The kit gives the frame, the steps, the moves between them, the side panel, the checks and
the screenshots. The app's rendering stays the app's own: its markup, its CSS and its class
names, captured from the running app.

For an example, see `examples/tool-library/3-Borrow-click-through.html` in the repository.
`artboards status` prints where the repository is.

## When to use it

Use a click-through when the reviewer must click through a flow to understand it, and a
wireframe does not show enough. This is usual when a change goes across several screens of
a product that people already use. The reviewer then sees the change in screens that they
know, with buttons that look like the real buttons.

Use a lo-fi board first when the order of the steps is not agreed. Use a hi-fi artboard
when the question is the look of one screen.

## Data

Capture only the screens and the data that the user names as safe to show, such as a demo
account with synthetic data. The local app can hold real customer data, and a snapshot keeps
every word and every image on the page.

Before the first capture, ask the user which account and which data to use. Do not capture
from a page that shows other data. Remove data from a snapshot that the user did not name.

## Procedure

1. **Steps.** List the steps: one line for each state that the reviewer sees. Mark each step
   that changes the product. Send the list to the user, and get a yes before you capture.
2. **Capture.** Start the app. For each screen, run `artboards capture` (see
   [Capture](#capture)). Save the snapshots in `$DIR/screens/`. The review queue does not list
   the files in that folder.
3. **Compose.** Run `artboards compose <snapshots> -o $DIR/<n>-<Name>.html --title "<title>"`.
   Give the snapshots in step order, and put a screen with no dialog open first. The command
   writes one step for each snapshot, and the CSS of all of them once.
4. **States.** Edit the markup of each step into the state that the step shows (see
   [Edit a state](#edit-a-state)). Add steps for the states that the app does not have.
5. **Moves.** Put `data-go="<step id>"` on each control that goes to another step.
6. **Panel.** Write the hint, the "What is new" text, the notes and the open questions of
   each step.
7. **Check.** Run `artboards check` until it shows 0 errors. Read the warnings, and fix the
   ones that are real.
8. **Look.** Run `artboards shot <file> --all-steps -o $DIR/shots`. Open each PNG and look at it.
   Compare each captured screen with the PNG that capture saved next to its snapshot.
9. **Hand over.** Give the user the URL, the list of steps and the open questions. Set the
   state to `open` while questions remain. To point at one step, add `#step=<id>` to the URL.

## The file

A click-through is one HTML file. It loads the kit from the server by absolute path:

```html
<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Borrow a tool, click-through</title>
<link rel="stylesheet" href="/_kit/clickthrough.css">
<script src="/_kit/clickthrough.js"></script>
</head>
<body>
<ct-flow name="Borrow a tool this weekend" width="390" height="844">
  <ct-intro><p>Click the controls in the phone.</p></ct-intro>

  <template ct-head>
    <ct-html lang="en"></ct-html>
    <ct-body class="app"></ct-body>
    <style>/* the app's CSS, from the snapshots */</style>
  </template>

  <ct-step id="1" name="Search results">
    <ct-hint>Click <ct-control>Cordless drill 18V</ct-control>.</ct-hint>
    <ct-new>Nothing yet. This is search today.</ct-new>
    <template>
      <!-- the app's markup for this state -->
      <div class="row" data-go="2">Cordless drill 18V</div>
    </template>
  </ct-step>

  <ct-step id="2" name="Tool page" new>
    ...
  </ct-step>
</ct-flow>
</body>
</html>
```

The app renders in an iframe of the size that `width` and `height` give. The app's CSS, its
media queries and its `vh` units see that size, also when the window is narrow and the kit
shows the frame smaller. The kit's CSS and the app's CSS do not meet.

## Tags

The kit tags hold the steps and the panel text. Everything inside a step's `<template>` is the
app's markup.

| Tag | Attributes and content | Example |
| --- | --- | --- |
| `ct-flow` | `name`, `width`, `height` (the frame in px; default 1440 by 900). Holds the other tags | `<ct-flow name="Borrow a tool" width="1440" height="900">` |
| `ct-intro` | HTML for the top of the panel. Directly inside `ct-flow` | `<ct-intro><p>Click the controls in the frame.</p></ct-intro>` |
| `ct-step` | `id`, `name`, `new` (the step changes the product), `branch` (indented in the list), `base` (see [Overlays](#overlays)). Holds the panel tags and one `<template>` | `<ct-step id="3b" name="A booked day" branch new base="2">` |
| `ct-hint` | What to click next, as an instruction | `<ct-hint>Click <ct-control>Borrow</ct-control>.</ct-hint>` |
| `ct-control` | Inside `ct-hint`: the name of a control in the step. A ring marks that control | `<ct-control>Request to borrow</ct-control>` |
| `ct-new` | "What is new" in this step: 1 or 2 sentences | `<ct-new>Borrow has dates before the member taps anything.</ct-new>` |
| `ct-note` | An optional note under "What is new" | `<ct-note>The toast stays for 4 seconds.</ct-note>` |
| `ct-question` | An open question, shown in red. One tag for each question | `<ct-question>Does the owner approve each request?</ct-question>` |
| `ct-html` | Inside `<template ct-head>`: its attributes go on the app's `<html>` | `<ct-html class="dark" lang="en"></ct-html>` |
| `ct-body` | Inside `<template ct-head>`: its attributes go on the app's `<body>` | `<ct-body class="font-sans antialiased"></ct-body>` |

Four attributes go on elements in the app's markup:

| Attribute | Effect |
| --- | --- |
| `data-go="<id>"` | A click on the element goes to that step |
| `data-control="<name>"` | The name that a `ct-control` uses for the element. Use it on a control with no text, such as a table row or an icon |
| `data-scroll-top`, `data-scroll-left` | The kit scrolls the element this far, in px. Capture writes them for each scrolled element |
| `data-top-layer="popover"` or `"modal"` | The kit opens the element as a popover, or as a modal dialog. Capture writes it for each open popover and modal dialog |

The name of a control is its `data-control`, else its `aria-label`, else its `title`, else its
text. The case and the spaces do not matter. When two controls have the name, the ring marks
the last one. A step's markup comes after the markup of its base step, so a control in a
dialog wins over a control with the same name under the dialog.

The `<html>` and `<body>` attributes in `<template ct-head>` apply to every step. When the
app's CSS follows the color scheme of the system, the frame follows it too, as the app does.
To shoot the dark look, add `--dark` to `artboards shot`.

## Moves

- A click on an element with `data-go` goes to that step. The element can be anything: a
  button, a link, a table row or a tab.
- A link without `data-go` does nothing, so a click cannot leave the click-through. A form does
  not submit.
- **J** goes to the next step in the list, and **K** goes to the step before. The keys do
  nothing while the reviewer types in a field.
- The URL holds the step: `#step=3b`. Use it in review notes and in `artboards shot`.

Every step must be reachable by clicks from the first step. Every step except the last
must have a move to another step. A branch step usually goes back to the main path.

## Edit a state

The composed file holds each captured screen as it was. Change it into the state of the step:

- Keep the app's elements and class names. Copy an element from the same screen and change
  its text, so the app's CSS applies to it.
- Remove the parts of a screen that the step does not need, such as long lists. Keep enough
  rows to show the pattern.
- For a part that the app does not have, add the CSS in one `<style>` element at the end of the
  head template. Give its classes a prefix that the app does not use, such as `ct-x-`.
- Do not add scripts. The kit shows each step as static markup.

When a state needs a click in the app to reach, such as an open menu or a filled form,
capture it with `--before`. Do not draw it by hand.

### Overlays

A dialog, a menu, a popover or a toast shows over a screen. Make it a step with
`base="<id>"`, where the id names the step of the screen under it. Put only the overlay in the
template. The kit shows the markup of the base step, and then the markup of the step.

To get the markup of an overlay, capture the screen with the overlay open. The overlay is
usually the last element of the body in the snapshot.

## Capture

`artboards capture <url> -o <file>` opens the page in headless Chromium and saves it as one
HTML file. It also saves a PNG of the page next to the file.

The snapshot keeps:

- the markup, after the app's scripts drew it
- the CSS of every stylesheet, in order
- the images, the fonts and the SVG sprites, as data URLs
- the values of the fields, the checked boxes and the scroll offsets of scroll boxes
- the open popovers and modal dialogs
- each canvas, as a picture

The snapshot drops each script, each event handler and each iframe. It does not keep the
scroll offset of the page itself: capture prints a warning when the page is scrolled. A file
bigger than 5 MB stays a link, and capture prints a warning for it.

`artboards compose` gives every step the `<html>` and `<body>` attributes of the first
snapshot. An open dialog can change these attributes, for example to stop clicks on the
page. Compose prints a warning when a snapshot has other attributes.

| Option | Effect |
| --- | --- |
| `--viewport 1440x900` | The page size. Use the same size as the frame |
| `--selector main` | Capture only this element, not the whole body |
| `--wait-for <selector>` | Wait until this element shows |
| `--wait <ms>` | Wait this long before the capture |
| `--cookie name=value` | Send a cookie to each path of the page's site. Repeat it for more cookies |
| `--header "Name: value"` | Send a header with every request, such as a token |
| `--before <script.py>` | Run a Python file after the page loads, with `page` set to the Playwright page |
| `--dark` | Use the dark color scheme |

To sign in, use a cookie, a header or a `--before` script. A script can also click the app into
the state to capture:

```python
page.get_by_role("tab", name="Review").click()
page.get_by_role("button", name="Sign off").click()
page.wait_for_timeout(300)
```

## Rules that the check does not catch

- Write each hint as one instruction. Name each control that the reviewer can click next.
- Keep "What is new" to 1 or 2 sentences. Write what changes for the user, not how it is
  built.
- Put each point that is not decided in a `ct-question`. Do not decide it in the markup.
- Use the copy of the product. Use the words that the screens use for a thing.
- Do not let a step show data that the user did not name as safe to show.

## What the check finds

`artboards check` opens the click-through in a headless browser. It reads every step, and it
shows each step in a hidden frame to measure it. Fix every error.

| Code | Level | Cause |
| --- | --- | --- |
| `unknown-tag` | error | A `ct-` tag that the kit does not have, such as `ct-hnit` |
| `misplaced-tag` | error | A kit tag in the wrong place, such as a `ct-question` outside a step, or a kit tag inside a step's template |
| `missing-id` | error | A step has no `id` |
| `duplicate-id` | error | Two steps have the same `id` |
| `missing-step` | error | A `data-go` or a `base` names no step |
| `base-loop` | error | The `base` attributes go round in a loop |
| `unreached-step` | error | No chain of moves from the first step leads to the step |
| `dead-end` | error | A step that is not the last has no move to another step |
| `missing-control` | error | A `ct-control` names a control that the step does not have |
| `console-error` | error | The page has a script error, or a file did not load |
| `kit-error` | error | The kit failed while it read the file |
| `no-hint` | warn | A step that is not the last has no hint |
| `frame-overflow` | warn | The content of a step is bigger than the frame. The message names the elements that stick out |
| `open-questions` | info | The number of open questions |
