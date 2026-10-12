---
name: artboard
description: Design a feature, a flow or a screen as local HTML artboards that the user reviews on localhost, in rounds. Two modes - lo-fi journey boards (rough wireframes, user journeys, user flows) and hi-fi artboards (one screen in the product's real look). Use when the user wants to design or redesign a feature, a flow or a screen, asks for wireframes, mockups, a user journey or a user flow, wants to agree how a screen looks, or wants to review designs by reloading a localhost URL.
---

# Artboards

An artboard is one HTML file. A group is one folder of artboards plus a `meta.json` file.
The `artboards` command makes groups, checks and screenshots the files, and serves every
group at `http://localhost:8899/`. The reviewer opens the URL, reloads it after each
round, and sends back notes or annotated screenshots.

The `artboards` command must be on `PATH`. If it is not, see
https://github.com/pranav7/artboards. Run `artboards -h` for the commands.

## Choose the mode

- **Lo-fi.** Use it first when the work adds or changes a flow: more than one screen,
  or an order of steps that is not agreed. One board shows grayscale wireframes in
  numbered regions, joined by arrows, with the user journeys in a side panel.
- **Hi-fi.** Use it when the flow is agreed and the question is how a screen looks.
  Draw one self-contained HTML file for each screen or state, in the product's real look.

The usual path: a lo-fi board, agreed, then hi-fi artboards in the same group for the
screens where the look matters.

Before you draw, read the guide for the mode. Read only that guide:

- Lo-fi: [lofi.md](lofi.md)
- Hi-fi: [hifi.md](hifi.md)

## The loop

1. From inside the project checkout, create the group, or resume it with the same title:
   `DIR=$(artboards init "<title>")`. The command prints the group folder.
2. Draw the artboard in `$DIR`. Add it to the `artboards` list in `$DIR/meta.json`.
3. Run `artboards check $DIR/<file>`. Fix each error, and run the check again until it
   shows 0 errors.
4. Run `artboards shot $DIR/<file>`. Open the PNG and look at it. A clean check does not
   prove that the drawing is correct.
5. Run `artboards status`. If the server is down, start `artboards serve` in the
   background.
6. Fetch `http://localhost:8899/<key>/<file>` and confirm that it returns 200. Then give
   that URL to the user. The key is the name of the group folder.
7. Do the review rounds. After each round, update the state and the note of each
   artboard in `meta.json`.
8. When the work is done, the server closes the group by itself (a merged pull request,
   all agreed, or 7 days with no change). To close it now, run `artboards archive <key>`.

## meta.json

`init` writes the fields about the checkout. You write the `artboards` list. The order
of the list is the order on the review page.

```json
{
  "artboards": [
    {"file": "1-Borrow.html", "title": "1 - borrow flow, journey board",
     "state": "open", "note": "Two open questions: who approves a request, and how long a waitlist place holds."}
  ]
}
```

## States

| State | Meaning |
| --- | --- |
| `agreed` | The reviewer accepted it. |
| `pending` | It waits for review. |
| `open` | It has a question that the reviewer must settle. Say the question in the note. |
| `dropped` | A newer artboard replaces it. The review page hides it. The file stays on disk. |

When a new artboard replaces a draft, mark the draft `dropped`. Do not leave it `pending`.

## Workers

- Give each artboard file to one worker. Never put two workers on one file.
- Only the lead edits `meta.json`. A worker reports its title and note to the lead.
- Give the worker the exact copy and controls, and the mode guide to read.

## Durable copy

The data folder (`~/.local/share/artboards`) is not a place to keep a design. If the
project has a docs folder, keep the artboards there, and make the group folder a symlink
to that folder:

```bash
mv "$DIR" docs/borrow-flow/artboards
ln -s "$PWD/docs/borrow-flow/artboards" "$DIR"
```

## Other skills

If you have a design skill, use it for visual direction in hi-fi mode. If you have a
writing skill, use it for every word on the artboard. The reviewer reads the copy as
part of the design.
