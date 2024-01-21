# blitz-replays

Set of command line tools to upload and analyze WoT Blitz replays.

## Status

- [x] `blitz-data`:
  - [x] `tankopedia`: Extraction of Tankopedia from game files or WG API
  - [x] `maps`: Extraction of maps from game files
- [x] `blitz-replays`:
  - [x] `upload`: Replay upload
  - [x] `analyze`: Replay analysis: First functional WIP version
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

  CLI app to extract WoT Blitz tankopedia and maps for other tools

Options:
  -v, --verbose         verbose logging
  --debug               debug logging
  --force / --no-force  Overwrite instead of updating data
  --config FILE         read config from FILE  [default:
                        /home/jarno/.config/blitzstats/config]
  --log FILE            log to FILE
  --install-completion  Install completion for the current shell.
  --show-completion     Show completion for the current shell, to copy it or
                        customize the installation.
  --help                Show this message and exit.

Commands:
  maps        extract maps data into a JSON file
  tankopedia  extract tankopedia as JSON file for other tools

```
### `blitz-data tankopedia` usage

```
Usage: blitz-data tankopedia [OPTIONS] COMMAND [ARGS]...

  extract tankopedia as JSON file for other tools

Options:
  --outfile FILE  Write Tankopedia to FILE
  --help          Show this message and exit.

Commands:
  app   extract Tankopedia from Blitz game files
  file  Read tankopedia from a file
  wg    get Tankopedia from WG API

```
### `blitz-data tankopedia wg` usage

```
Usage: blitz-data tankopedia wg [OPTIONS]

  get Tankopedia from WG API

Options:
  --wg-app-id TEXT                WG app ID
  --wg-region [ru|eu|com|asia|china|BOTS]
                                  WG API region (default: eu)
  --wg-rate-limit FLOAT           WG API rate limit, default=10/sec
  --help                          Show this message and exit.

```
### `blitz-data tankopedia app` usage

```
Usage: blitz-data tankopedia app [OPTIONS] [BLITZ_APP_DIR]

  extract Tankopedia from Blitz game files

Arguments:
  [BLITZ_APP_DIR]  Blitz game files directory

Options:
  --wg-app-id TEXT           WG app ID
  --wg-region [eu|asia|com]  WG API region
  --help                     Show this message and exit.

```
### `blitz-data maps` usage

```
Usage: blitz-data maps [OPTIONS] COMMAND [ARGS]...

  extract maps data into a JSON file

Options:
  --outfile FILE  Write maps to FILE
  --help          Show this message and exit.

Commands:
  app   Read maps data from game files
  file  Read maps data from a JSON file
  list  list maps from a JSON file

```
### `blitz-data maps app` usage

```
Usage: blitz-data maps app [OPTIONS] [BLITZ_APP_DIR]

  Read maps data from game files

Arguments:
  [BLITZ_APP_DIR]  Blitz game files directory

Options:
  --help  Show this message and exit.

```
## `blitz-replays` usage

```
Usage: blitz-replays [OPTIONS] COMMAND [ARGS]...

  CLI app to upload WoT Blitz replays

Options:
  -v, --verbose         verbose logging
  --debug               debug logging
  --force / --no-force  Overwrite instead of updating data
  --config FILE         read config from FILE  [default:
                        /home/jarno/.config/blitzstats/config]
  --log FILE            log to FILE
  --tankopedia FILE     tankopedia JSON file
  --maps FILE           maps JSON file
  --install-completion  Install completion for the current shell.
  --show-completion     Show completion for the current shell, to copy it or
                        customize the installation.
  --help                Show this message and exit.

Commands:
  analyze  analyze replays
  upload   upload replays to https://WoTinspector.com

```
### `blitz-replays upload` usage

```
Usage: blitz-replays upload [OPTIONS] REPLAYS...

  upload replays to https://WoTinspector.com

Arguments:
  REPLAYS...  replays to upload  [required]

Options:
  --force                   force upload even JSON file exists
  --private / --no-private  upload replays as private without listing those
                            publicly (default=False)
  --wi-rate-limit FLOAT     rate-limit for WoTinspector.com
  --wi-auth-token TEXT      authentication token for WoTinsepctor.com
  --help                    Show this message and exit.

```
### `blitz-replays analyze files` usage

```
Usage: blitz-replays analyze files [OPTIONS] REPLAYS...

  analyze replays from JSON files

Arguments:
  REPLAYS...  replays to upload  [required]

Options:
  --wg-app-id TEXT                WG app ID
  --wg-region [ru|eu|com|asia|china|BOTS]
                                  WG API region (default: eu)
  --wg-rate-limit FLOAT           WG API rate limit, default=10/sec
  --help                          Show this message and exit.

```

