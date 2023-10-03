# blitz-replays

Command line tool to upload and analyze WoT Blitz replays.

## Status

- [x] `blitzdata.py`:
  - [x] `tankopedia`: Extraction of Tankopedia from game files or WG API
  - [x] `maps`: Extraction of maps from game files
- [ ] `blitzreplays.py`:
  - [x] `upload`: Replay upload
  - [ ] `analyze`: Replay analysis. Please use old [blitz-tools](../blitz-tools/)
  - [ ] `parse`: Parsing replays client-side

## Install 

You need [Python 3.11](https://python.org/) or later installed. 

```
pip install git+https://github.com/Jylpah/blitz-replays.git
```

## Upgrade

```
pip install --upgrade git+https://github.com/Jylpah/blitz-replays.git
```

## Usage

### `blitzreplays.py` Commands

```
% blitzreplays.py --help
Usage: blitzreplays.py [OPTIONS] COMMAND [ARGS]...

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

#### `blitzreplays.py upload`

```
% ./blitzreplays.py upload --help
Usage: blitzreplays.py upload [OPTIONS] [REPLAYS]...

Options:
  --json                 fetch replay JSON files for analysis (default=False)
  --uploaded_by INTEGER  WG account_id of the uploader
  --private              upload replays as private without listing those
                         publicly (default=False)
  --help                 Show this message and exit.
```

## `blitzdata.py` Commands

```
# TBD
```
