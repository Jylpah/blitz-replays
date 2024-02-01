[![Python package](https://github.com/Jylpah/blitz-replays/actions/workflows/python-app.yml/badge.svg)](https://github.com/Jylpah/blitz-replays/actions/workflows/python-app.yml)  [![codecov](https://codecov.io/gh/Jylpah/blitz-replays/graph/badge.svg?token=CCJCGS112S)](https://codecov.io/gh/Jylpah/blitz-replays)

# blitz-replays

Set of command line tools to upload and analyze WoT Blitz replays. 

* `blitz-replays`: upload and analyze Blitz replays
* `blitz-data`: extract updated game metadata (maps and tankopedia) for `blitz-replays` 

## Example

```
% blitz-replays analyze files 2023-12-25
Reading replays |████████████████████████████████████████| 65 in 0.5s (129.37/s)
Fetching player stats |████████████████████████████████████████✗︎ (!) 781/775 [101%] in 1.5s (542.47/s)

TOTAL
     Battles  WR        DPB    KPB    Spot  Top tier      DR  Surv%    Allies WR    Enemies WR
-----  ---------  ------  -----  -----  ------  ----------  ----  -------  -----------  ------------
Total         65  63.08%   1836   1.23    1.54  46%         1.59  55%      51.3%        51.5%

BATTLE RESULT
    Battles  WR         DPB    KPB    Spot  Top tier      DR  Surv%    Allies WR    Enemies WR
----  ---------  -------  -----  -----  ------  ----------  ----  -------  -----------  ------------
Loss         24  0.00%     1716   1       1.42  50%         1.07  8%       50.6%        51.7%
Win          41  100.00%   1906   1.37    1.61  44%         2.13  83%      51.6%        51.3%

BATTLE CLASS
         Battles  WR         DPB    KPB    Spot  Top tier      DR  Surv%    Allies WR    Enemies WR
---------  ---------  -------  -----  -----  ------  ----------  ----  -------  -----------  ------------
-                 36  33.33%    1514   0.78    1.42  44%         1.07  22%      50.9%        51.9%
1st Class          1  100.00%   3537   4       2     100%        2.23  100%     47.3%        50.4%
2nd Class          9  100.00%   2841   2.22    2.44  56%         2.69  100%     51.1%        50.0%
3rd Class         18  100.00%   1807   1.33    1.33  44%         2.69  94%      52.4%        51.5%
Mastery            1  100.00%   3203   4       1     0%          2.89  100%     47.3%        50.1%
```

# Status

Works and tested on Windows, Mac and Linux. Requires [Python 3.11](https://python.org/) or later. 

### blitz-replays

- [x] `upload`: Replay upload to [replays.wotinspector.com](https://replays.wotinspector.com)
- [x] `analyze`: Replay analysis fully functional
- [ ] `parse`: Parsing replays client-side

### blitz-data:

- [x] `tankopedia`: Extraction of Tankopedia from game files or WG API
- [x] `maps`: Extraction of maps from game files

## TODO

- [ ] API cache for `blitz-replays analyze` to make consequtive analysis faster. Especially useful for `--stats-type tank | tier` which use a different (an 100x slower) API endpoint than `--stats-type player` 
- [ ] `parse`: Parsing replays client-side. This is a bigger task. Let's see when I can find time for this. 

### Done

- [x] Export reports to a tab-separated text file that can be opened with Excel for further analysis with `blitz-replays analyze --export`
- [x] Support for custom report/field config with `blitz-replays analyze --analyze-config` 
- [x] Help texts for field metric types, filter types and ~~field formats~~ for `blitz-replays analyze info`

# Install 

You need [Python 3.11](https://python.org/) or later installed. 

```
pip install git+https://github.com/Jylpah/blitz-replays.git
```

## Upgrade

```
pip install --upgrade git+https://github.com/Jylpah/blitz-replays.git
```

## Configuration

`blitz-replays analyze` provides a set of reports (tables) and fields (columns) by default. You can add your own reports and fields with `--analyze-config YOUR_CONFIG_FILE.toml`. The analyze config is a [TOML 1.0](https://toml.io/) format file. See examples and inspiration from the [in-built config file](https://github.com/Jylpah/blitz-replays/blob/main/src/blitzreplays/replays/config.toml).

# Usage

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
### `blitz-replays analyze` usage

```
Usage: blitz-replays analyze [OPTIONS] COMMAND [ARGS]...

  analyze replays

Options:
  --analyze-config TEXT           TOML config file for 'analyze' reports
  --stats-type [player|tier|tank]
                                  stats to use for player stats
  --fields TEXT                   set report fields, combine field modes with
                                  '+'
  --reports TEXT                  reports to create. use '+' to add extra
                                  reports
  --player INTEGER                player to analyze (WG account_id), default:
                                  player who recorded the replay
  --help                          Show this message and exit.

Commands:
  files  analyze replays from JSON files
  info   Information of available for analysis

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
  --export / --no-export          export reports to a Tab-delimited text file
                                  [default: no-export]
  --export-fn PATH                file to export to  [default: export.txt]
  --help                          Show this message and exit.

```
### `blitz-replays analyze info` usage

```
Usage: blitz-replays analyze info [OPTIONS] COMMAND [ARGS]...

  Information of available for analysis

Options:
  --help  Show this message and exit.

Commands:
  fields   List configured report fields
  filters  List available player filters
  metrics  List available field types / metrics
  replay   List available fields in replays
  reports  List configured reports

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

