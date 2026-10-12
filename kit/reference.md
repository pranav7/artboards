# Lo-fi kit tag reference

A board is one HTML file. Load the kit in `<head>`:

```html
<link rel="stylesheet" href="/_kit/lofi.css"><script src="/_kit/lofi.js"></script>
```

Rules:

- `name` sets the visible name of a tag. Do not use `title`.
- List attributes are comma-separated: `items="Home, Search, More"`.
- Ids are unique across the whole board.
- No pixel positions. Screens sit on a grid with `col` and `row`.
- Write real copy. One `primary` button per screen.
- An attribute with no value (`new`, `back`, `primary`) is on when present.

## Board structure

These go directly inside `wf-board`, except screens, decisions, notes and questions, which go inside a `wf-region`.

| Tag | Attributes | Example |
| --- | --- | --- |
| `wf-board` | `name` | `<wf-board name="Tool library, option A">` |
| `wf-summary` | text: the summary paragraph at the top of the panel | `<wf-summary>Members find a tool by distance first.</wf-summary>` |
| `wf-problem` | HTML: who, what goes wrong today, why now | `<wf-problem><p>Nobody knows which tools are free.</p></wf-problem>` |
| `wf-journey` | `name`, `steps` (screen or decision ids in order; `id@link-id` picks the link to arrive by) | `<wf-journey name="Return a tool" steps="borrowed, return, borrowed"></wf-journey>` |
| `wf-region` | `id`, `name`; holds screens, decisions, notes, questions | `<wf-region id="find" name="Finding a tool">` |
| `wf-screen` | `id`, `name`, `device` (`phone`, `tablet`, `desktop`), `col`, `row`, `new` | `<wf-screen id="home" device="phone" name="Home tab" col="1" row="1">` |
| `wf-decision` | `id`, `name` (the question), `col`, `row` | `<wf-decision id="free" name="Free on those dates?" col="1" row="1"></wf-decision>` |
| `wf-link` | `from`, `to` (any id: screen, decision or element in a screen), `label`, `id`, `exit`, `enter` (`left`, `right`, `top`, `bottom`), `stub` (`stub` forces two short stubs, `stub="false"` forces a full line) | `<wf-link id="home-type" from="home-search" to="search" label="type"></wf-link>` |
| `wf-note` | `for` (a screen or decision id), or `col` and `row` | `<wf-note for="home">Sorted by walking distance.</wf-note>` |
| `wf-question` | `for`, or `col` and `row`; an open question, shown in red and listed in the panel | `<wf-question for="sent">Does the lender approve each request?</wf-question>` |
| `wf-prose` | `region` (a region id); HTML that says why, shown in the panel | `<wf-prose region="find"><p>Search comes first because...</p></wf-prose>` |

Links between regions that are not next to each other draw as two short stubs: "label to Target" at the source and "from Source" at the target. Hover a stub to light both ends; click it to go to the other end.

## Inside a screen

Plain `h1`, `h2`, `p` and `small` inside a screen get kit styles.

| Tag | Attributes | Example |
| --- | --- | --- |
| `wf-header` | `name`, `back` | `<wf-header back name="Cordless drill"></wf-header>` |
| `wf-tabbar` | `items`, `active` | `<wf-tabbar items="Home, Search, Profile" active="Home"></wf-tabbar>` |
| `wf-sidebar` | `items`, `active`; desktop only, sits on the left | `<wf-sidebar items="Tools, Loans, Members" active="Loans"></wf-sidebar>` |
| `wf-tabs` | `items`, `active` | `<wf-tabs items="List, Map" active="List"></wf-tabs>` |
| `wf-menu` | `items` | `<wf-menu items="My tools, Notifications, Help"></wf-menu>` |
| `wf-list` | holds `wf-row` | `<wf-list><wf-row name="Tile saw"></wf-row></wf-list>` |
| `wf-row` | `name`, `meta`, `avatar`, `thumb`; children show at the end | `<wf-row thumb name="Tile saw" meta="Ana Lopes, due Fri"><wf-badge>Due</wf-badge></wf-row>` |
| `wf-card` | `name`; holds anything | `<wf-card name="Return by Sunday"><small>Step ladder</small></wf-card>` |
| `wf-cols` | holds children side by side, equal widths | `<wf-cols><wf-stat label="Lent" value="12"></wf-stat><wf-stat label="Borrowed" value="7"></wf-stat></wf-cols>` |
| `wf-avatar` | `name` | `<wf-avatar name="Priya Shah"></wf-avatar>` |
| `wf-image` | `label`, `tall` | `<wf-image tall label="map with 6 pins"></wf-image>` |
| `wf-chart` | `kind` (`line`, `bar`) | `<wf-chart kind="bar"></wf-chart>` |
| `wf-stat` | `label`, `value` | `<wf-stat label="Loans" value="23"></wf-stat>` |
| `wf-table` | text lines; `\|` between cells; the first line is the header; a cell that starts with `~` is struck out | `<wf-table>Sat \| Sun \| Mon` + new line + `19 \| ~20 \| 21</wf-table>` |
| `wf-badge` | text | `<wf-badge>Free</wf-badge>` |
| `wf-empty` | text | `<wf-empty>No loans yet</wf-empty>` |
| `wf-input` | `label`, `value`, `placeholder` | `<wf-input label="Name" placeholder="Your name"></wf-input>` |
| `wf-search` | `value`, `placeholder` | `<wf-search placeholder="Search tools"></wf-search>` |
| `wf-select` | `label`, `value` | `<wf-select label="From" value="Sat 19 Oct"></wf-select>` |
| `wf-textarea` | `label`, `value`, `placeholder` | `<wf-textarea label="Note for Tom" placeholder="Anything Tom should know"></wf-textarea>` |
| `wf-check` | `checked`; text | `<wf-check checked>Remind me the day before</wf-check>` |
| `wf-radio` | `checked`; text | `<wf-radio checked>The next free weekend</wf-radio>` |
| `wf-toggle` | `on`; text | `<wf-toggle on>Tell me when it is free</wf-toggle>` |
| `wf-button` | `primary`; text | `<wf-button primary>Borrow</wf-button>` |
| `wf-modal` | `name`; holds anything; shows over the screen | `<wf-modal name="Cancel the loan?"><wf-button primary>Cancel loan</wf-button></wf-modal>` |
| `wf-sheet` | `name`; holds anything; slides up from the bottom | `<wf-sheet name="Pick a time"><wf-radio checked>9 am</wf-radio></wf-sheet>` |
| `wf-toast` | text | `<wf-toast>Request sent</wf-toast>` |

## Checks

`artboards check board.html` lists problems, one per line, with a level, a code and a message. The lo-fi guide (`skills/artboard/lofi.md`) explains each code. The toolbar shows a red count when there are any; click it to list them in the browser console.
