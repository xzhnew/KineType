# Third-party notices

Kinetype is licensed under **GPL-3.0-only**. See `LICENSE` for the complete text.

## Why GPL-3.0-only (and not MIT / non-commercial)

The browser build (`web-ui/dist/`) compiles **WinUIonWeb 0.1.0** into the
delivered JavaScript. WinUIonWeb is licensed **GPL-3.0-only**, so the combined
work must also be distributed under GPL-3.0-only. GPL-3.0 explicitly **allows
commercial use** and forbids adding extra restrictions such as
"non-commercial only". If non-commercial distribution were mandatory,
WinUIonWeb would have to be replaced with an MIT-compatible UI library or a
separate licence obtained from its author.

The upstream project is <https://github.com/Furry-Xiyi/WinUIonWeb>; its full
licence text is included at `licenses/winuionweb-GPL-3.0.txt`.

## Bundled / runtime packages

| Package | Version | Licence | Role |
| --- | --- | --- | --- |
| winuionweb | 0.1.0 | GPL-3.0-only | WinUI 3 style component library |
| Vue | 3.5.x | MIT | UI runtime |
| mp4-muxer | 5.2.x | MIT | MP4 muxing in the browser |

## Build-time packages

`@vitejs/plugin-vue`, `@vitejs/plugin-legacy`, `vite` and `terser` are MIT
licensed and are not shipped in the runtime bundle.

## Fonts

No Microsoft font files are included. Segoe Fluent Icons is referenced by local
family name only; the visitor's browser uses a copy already installed on their
device. Do not add font files to this repository.
