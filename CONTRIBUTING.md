# Contributing

This file is for people who change the tool. To use it, see the [README](README.md).

## Commands

| Command | Effect |
| --- | --- |
| `artboards doctor` | Installs the Python packages and Chromium, checks the example board, and prints the server status |
| `artboards init "<title>"` | Creates the group for the current checkout, or resumes it, and prints the group folder |
| `artboards list` | Prints one line for each group: active or closed, key, title, and the count of artboards in each state |
| `artboards status` | Prints the data folder, the kit folder, and whether the server answers |
| `artboards serve` | Runs the server in the foreground |
| `artboards archive <key>` | Closes a group by hand |
| `artboards activate <key>` | Opens a closed group again, and keeps tidy from closing it |
| `artboards tidy [--dry-run]` | Closes and removes groups by the tidy rules. `--dry-run` prints the actions and changes nothing |
| `artboards guide [lofi\|hifi\|clickthrough]` | Prints the tag reference for the lo-fi kit, or the hi-fi or click-through guide |
| `artboards check <file>...` | Opens each artboard in a headless browser and prints its problems. Exits with 1 if there is an error |
| `artboards shot <file>[#journey=N] [--dark] [--width W] [-o out.png]` | Saves a full-page PNG. The default width is 1600 |
| `artboards shot <file>[#step=ID] [--all-steps] [-o out]` | For a click-through: saves a PNG at the size that shows the frame at 100%. `--all-steps` saves one PNG for each step, in the folder that `-o` names |
| `artboards capture <url> -o <file> [options]` | Saves one state of a running app as a self-contained HTML snapshot, and a PNG next to it. `skills/artboard/clickthrough.md` lists the options |
| `artboards compose <snapshot>... -o <file> [--title T] [--add]` | Writes a click-through with one step for each snapshot. `--add` appends the steps to a click-through |
| `artboards export <file> [-o out.html]` | Writes one self-contained HTML file with the kit inlined, to send to someone |
| `artboards test [args]` | Runs the tests |

Two environment variables change the defaults:

| Variable | Default |
| --- | --- |
| `ARTBOARDS_HOME` | `~/.local/share/artboards` |
| `ARTBOARDS_PORT` | `8899` |

## How it works

1. `artboards init` makes a group folder in the data folder. The name of the folder is the
   key: `<session>--<title>--<hash>`. The session is the name of the checkout, so two
   worktrees of one repo get different groups. The command writes `meta.json` with the
   checkout, the repo, the branch and the time.
2. The agent writes artboards into the folder, and lists them in `meta.json` with a title,
   a state and a note.
3. A lo-fi board loads `/_kit/lofi.css` and `/_kit/lofi.js`. The kit turns the `wf-` tags
   into wireframes, lays out the regions on a grid, routes the arrows, and builds the
   journey panel. It also gives `window.wf.problems()`, a list of the problems that it
   found.

   A click-through loads `/_kit/clickthrough.css` and `/_kit/clickthrough.js`. The kit
   shows the app's markup for one step at a time in an iframe of the frame size, builds the
   step panel, and goes to a step on a click on a `data-go` element. `window.ct.problems()`
   returns a promise: the kit shows each step in a hidden iframe to measure it.
4. `artboards check` opens the file in Chromium with Playwright. It sends `/_kit/`
   requests to the `kit` folder, so the check works without the server. For a lo-fi
   board, it waits for `wf.ready` and reads `wf.problems()`. For a click-through, it waits
   for `ct.ready` and reads `ct.problems()`. For a hi-fi artboard, it runs generic checks:
   script errors, dark-only tokens, a transparent body, and text overflow.
5. `artboards serve` serves the data folder and the kit on `127.0.0.1`. It makes the
   review queue (`/`) and the history (`/history`) from `meta.json` on each request. The
   **Archive** and **Reopen** buttons post to `/_api/archive/<key>` and `/_api/reopen/<key>`.
   The server accepts a post only when its `Origin` header is the server itself.
6. The server runs tidy at start and then every hour. Tidy closes an active group on the
   first rule that matches:
   1. `pr-merged`: a pull request from the group's branch merged after the group was
      created. Tidy asks `gh`. If `gh` is missing or fails, tidy skips the rule.
   2. `all-agreed`: each artboard is `agreed` or `dropped`.
   3. `idle`: no artboard file changed for 7 days.

   `artboards activate` sets `keep`, and then tidy skips rules 1 and 2 for that group.
   Tidy also removes a symlinked group whose target is gone, and an empty group older
   than 1 day. It deletes nothing else.

## Develop

| File | Contents |
| --- | --- |
| `bin/artboards` | The command. It finds `uv`, sets up the environment, and runs the package |
| `src/artboards/paths.py` | The data folder, the port, and the folders of the repo |
| `src/artboards/meta.py` | Reads and writes `meta.json`, makes the group key, reads the git checkout |
| `src/artboards/index.py` | The review queue and the history pages |
| `src/artboards/tidy.py` | The tidy rules |
| `src/artboards/server.py` | The HTTP server |
| `src/artboards/browser.py` | Playwright: `check`, `shot`, `export`, and the browser test in `doctor` |
| `src/artboards/capture.py` | Playwright: `capture`, a self-contained snapshot of a running app |
| `src/artboards/compose.py` | `compose`: a click-through from snapshots |
| `src/artboards/cli.py` | The command-line interface |
| `kit/lofi.js`, `kit/lofi.css` | The lo-fi kit |
| `kit/reference.md` | The tag reference that `artboards guide lofi` prints |
| `kit/clickthrough.js`, `kit/clickthrough.css` | The click-through kit |
| `skills/artboard/SKILL.md` | The skill for agents |
| `skills/artboard/lofi.md`, `hifi.md`, `clickthrough.md` | The guide for each mode. `clickthrough.md` is also the tag reference of the click-through kit |
| `examples/tool-library/` | The example group |
| `tests/fixtures/` | Boards and click-throughs that each break one check |

To add a tag to the lo-fi kit:

1. Add the tag to the registry in `kit/lofi.js`.
2. Add a line for it to `kit/reference.md`. A test compares the tags in the two files, and
   fails if they are different.
3. Use the tag in `tests/fixtures/lofi-clean.html`, so the check tests cover it.

To add a tag to the click-through kit:

1. Add the tag to `TAGS` and `PARENT` in `kit/clickthrough.js`.
2. Add a row for it to the tag table in `skills/artboard/clickthrough.md`. A test compares
   the tags in the two files.
3. Use the tag in `tests/fixtures/ct-clean.html`.

To add a check to a kit, give it a code in kebab case, and add it to `wf.problems()` or
`ct.problems()`. Add a fixture `tests/fixtures/lofi-<code>.html` or
`tests/fixtures/ct-<code>.html` that causes only that code. Then add the code to the list in
`tests/test_browser.py` or `tests/test_clickthrough.py`.

Run `artboards test` before you commit.

## Licenses of the dependencies

This project uses the MIT license. It uses these projects, which have their own licenses:

| Project | License | How it is used |
| --- | --- | --- |
| [Playwright](https://github.com/microsoft/playwright-python) | Apache-2.0 | Python dependency. It downloads Chromium |
| [IBM Plex Mono](https://github.com/IBM/plex) | SIL Open Font License | Loaded from Google Fonts by the review queue page |
