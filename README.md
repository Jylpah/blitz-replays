# blitz-replays

Set of command line tools to upload and analyze WoT Blitz replays.

## Status

- [x] `blitz-data`:
  - [x] `tankopedia`: Extraction of Tankopedia from game files or WG API
  - [x] `maps`: Extraction of maps from game files
- [x] `blitz-replays`:
  - [x] `upload`: Replay upload
  - [ ] `analyze`: Replay analysis. Please use old [blitz-tools](../blitz-tools/)
  - [ ] `parse`: Parsing replays client-side

## Install 

You need [Python 3.11](https://python.org/) or later installed. 

```
pip install --upgrade git+https://github.com/Jylpah/blitz-replays.git
```

## Upgrade

```
pip install --upgrade git+https://github.com/Jylpah/blitz-replays.git
```


## `blitz-data` usage

```
Usage: blitz-data [OPTIONS] COMMAND [ARGS]...

  CLI tool extract WoT Blitz metadata for other tools

Options:
  --normal       default verbosity
  --verbose      verbose logging
  --debug        debug logging
  --config PATH  read config from file (default:
                 /home/jarno/.config/blitzstats/config)
  --log PATH     log to FILE
  --help         Show this message and exit.

Commands:
  maps        extract maps data into a JSON file
  tankopedia  extract tankopedia as JSON file for other tools

```
### `blitz-data tankopedia` usage

```
Usage: blitz-data tankopedia [OPTIONS] COMMAND [ARGS]...

  extract tankopedia as JSON file for other tools

Options:
  -f, --force     Overwrite Tankopedia instead of updating it
  --outfile PATH  Write Tankopedia to file (default: tanks.json)
  --help          Show this message and exit.

Commands:
  app   extract Tankopedia from Blitz game files
  file  read Tankopedia from a JSON file
  wg    get Tankopedia from WG API

```
### `blitz-data tankopedia wg` usage

```
Usage: blitz-data tankopedia wg [OPTIONS]

  get Tankopedia from WG API

Options:
  --wg-app-id TEXT           WG app ID
  --wg-region [eu|asia|com]  Default WG API region
  --help                     Show this message and exit.

```
### `blitz-data tankopedia app` usage

```
Usage: blitz-data tankopedia app [OPTIONS] [BLITZ_APP_DIR]

  extract Tankopedia from Blitz game files

Options:
  --wg-app-id TEXT           WG app ID
  --wg-region [eu|asia|com]  WG API region (default: eu)
  --help                     Show this message and exit.

```
### `blitz-data maps` usage

```
Usage: blitz-data maps [OPTIONS] COMMAND [ARGS]...

  extract maps data into a JSON file

Options:
  -f, --force     Overwrite maps data instead of updating it
  --outfile PATH  Write maps to file (default: maps.json)
  --help          Show this message and exit.

Commands:
  app   read maps data from Blitz game files
  file  read maps data from a JSON file

```
### `blitz-data maps app` usage

```
Usage: blitz-data maps app [OPTIONS] [BLITZ_APP_DIR]

  read maps data from Blitz game files

Options:
  --wg-app-id TEXT           WG app ID
  --wg-region [eu|asia|com]  WG API region (default: eu)
  --help                     Show this message and exit.

```
## `blitz-replays` usage

```
Usage: blitz-replays [OPTIONS] COMMAND [ARGS]...

  CLI tool upload WoT Blitz Replays to WoTinspector.com

Options:
  --normal               default verbosity
  --verbose              verbose logging
  --debug                debug logging
  --config PATH          read config from file (default:
                         /home/jarno/.config/blitzstats/config)
  --log PATH             log to FILE
  --wi-rate-limit FLOAT  rate-limit for WoTinspector.com
  --wi-auth_token TEXT   authentication token for WoTinsepctor.com
  --tankopedia TEXT      tankopedia JSON file
  --maps TEXT            maps JSON file
  --help                 Show this message and exit.

Commands:
  upload

```
### `blitz-replays upload` usage

```
Usage: blitz-replays upload [OPTIONS] [REPLAYS]...

Options:
  --json                 fetch replay JSON files for analysis (default=False)
  --uploaded_by INTEGER  WG account_id of the uploader
  --private              upload replays as private without listing those
                         publicly (default=False)
  --help                 Show this message and exit.

```


### `blitz-data tankopedia` usage

```
Usage: blitz-data tankopedia [OPTIONS] COMMAND [ARGS]...

  extract tankopedia as JSON file for other tools

Options:
  -f, --force     Overwrite Tankopedia instead of updating it
  --outfile PATH  Write Tankopedia to file (default: tanks.json)
  --help          Show this message and exit.

Commands:
  app   extract Tankopedia from Blitz game files
  file  read Tankopedia from a JSON file
  wg    get Tankopedia from WG API

```


### `blitz-data maps` usage

```
Usage: blitz-data maps [OPTIONS] COMMAND [ARGS]...

  extract maps data into a JSON file

Options:
  -f, --force     Overwrite maps data instead of updating it
  --outfile PATH  Write maps to file (default: maps.json)
  --help          Show this message and exit.

Commands:
  app   read maps data from Blitz game files
  file  read maps data from a JSON file

```


### `blitz-replays` usage

```
Usage: blitz-replays [OPTIONS] COMMAND [ARGS]...

  CLI tool upload WoT Blitz Replays to WoTinspector.com

Options:
  --normal               default verbosity
  --verbose              verbose logging
  --debug                debug logging
  --config PATH          read config from file (default:
                         /home/jarno/.config/blitzstats/config)
  --log PATH             log to FILE
  --wi-rate-limit FLOAT  rate-limit for WoTinspector.com
  --wi-auth_token TEXT   authentication token for WoTinsepctor.com
  --tankopedia TEXT      tankopedia JSON file
  --maps TEXT            maps JSON file
  --help                 Show this message and exit.

Commands:
  upload

```


### `blitz-replays upload` usage

```
Usage: blitz-replays upload [OPTIONS] [REPLAYS]...

Options:
  --json                 fetch replay JSON files for analysis (default=False)
  --uploaded_by INTEGER  WG account_id of the uploader
  --private              upload replays as private without listing those
                         publicly (default=False)
  --help                 Show this message and exit.

```

