#!/usr/bin/env python3
## PYTHON VERSION MUST BE 3.7 OR HIGHER

# Extract tankopedia data in WG API JSON format from Blitz app files (Android APK unzipped)

from os.path import isfile, isdir, dirname, realpath, expanduser, join as join_path
from typing import Optional
from configparser import ConfigParser
from collections import OrderedDict
from asyncio import set_event_loop_policy, run, create_task, get_event_loop_policy

import aiofiles 				# type: ignore
import xmltodict				# type: ignore
import sys, argparse, json, os, inspect, asyncio, re, logging, time, configparser
import logging

sys.path.insert(0, dirname(dirname(realpath(__file__))))

from blitzutils import EnumNation, EnumVehicleTypeInt
from pyutils import MultilevelFormatter

# logging.getLogger("asyncio").setLevel(logging.DEBUG)
logger 	= logging.getLogger()
error	= logger.error
message = logger.warning
verbose = logger.info
debug	= logger.debug

FILE_CONFIG 	= 'blitzstats.ini'

BLITZAPP_STRINGS='Data/Strings/en.yaml'
BLITZAPP_VEHICLES_DIR='Data/XML/item_defs/vehicles/'
BLITZAPP_VEHICLE_FILE='list.xml'

# wg : WG | None = None

## main() -------------------------------------------------------------
async def main() -> None:
	global logger, error, debug, verbose, message
	# set the directory for the script
	# os.chdir(os.path.dirname(sys.argv[0]))

	## Read config
	BLITZAPP_FOLDER = '.'
	_PKG_NAME	= 'blitzreplays'
	CONFIG 		= _PKG_NAME + '.ini'
	LOG 		= _PKG_NAME + '.log'
	config 		: Optional[ConfigParser] = None
	CONFIG_FILE : Optional[str] 		= None

	CONFIG  = 'blitzstats.ini'
	CONFIG_FILES: list[str] = [
					'./' + CONFIG,
		 			dirname(realpath(__file__)) + '/' + CONFIG,
		 			'~/.' + CONFIG,
					'~/.config/' + CONFIG,
					f'~/.config/{_PKG_NAME}/config',
					'~/.config/blitzstats.ini',
					'~/.config/blitzstats/config'
				]
	for fn in [ expanduser(f) for f in CONFIG_FILES ] :
		if isfile(fn):
			CONFIG_FILE=fn			
			verbose(f'config file: {CONFIG_FILE}')
	if CONFIG_FILE is None:
		error('config file not found in: ' + ', '.join(CONFIG_FILES))

	parser = argparse.ArgumentParser(description='Extract Tankopedia data from Blitz game files')
	arggroup_verbosity = parser.add_mutually_exclusive_group()
	arggroup_verbosity.add_argument('--debug', '-d', dest='LOG_LEVEL', action='store_const', 
									const=logging.DEBUG, help='Debug mode')
	arggroup_verbosity.add_argument('--verbose', '-v', dest='LOG_LEVEL', action='store_const', 
									const=logging.INFO, help='Verbose mode')
	arggroup_verbosity.add_argument('--silent', '-s', dest='LOG_LEVEL', action='store_const', 
									const=logging.CRITICAL, help='Silent mode')
	parser.add_argument('--log', type=str, nargs='?', default=None, const=f"{LOG}", 
						help='Enable file logging')	
	parser.add_argument('--config', type=str, default=CONFIG_FILE, metavar='CONFIG', 
						help='Read config from CONFIG')
	parser.set_defaults(LOG_LEVEL=logging.WARNING)

	args, argv = parser.parse_known_args()

	# setup logging
	logger.setLevel(args.LOG_LEVEL)
	logger_conf: dict[int, str] = { 
		logging.INFO: 		'%(message)s',
		logging.WARNING: 	'%(message)s',
		# logging.ERROR: 		'%(levelname)s: %(message)s'
	}
	MultilevelFormatter.setLevels(logger, fmts=logger_conf, 
									fmt='%(levelname)s: %(funcName)s(): %(message)s', 
									log_file=args.log)
	error 		= logger.error
	message		= logger.warning
	verbose		= logger.info
	debug		= logger.debug

	if args.config is not None and isfile(args.config):
		debug(f'Reading config from {args.config}')
		config = ConfigParser()
		config.read(args.config)
		if 'TANKOPEDIA' in config:
			configOptions 	= config['TANKOPEDIA']
			BLITZAPP_FOLDER = configOptions.get('blitz_app_dir', BLITZAPP_FOLDER)
	else:
		debug("No config file found")		
	# Parse command args
	parser.add_argument('-h', '--help', action='store_true',  
							help='Show help')
	parser.add_argument('blitz_app_dir', type=str, nargs='?', metavar="BLITZAPP_FOLDER", 
						default=BLITZAPP_FOLDER, help='Base dir of the Blitz App files')
	parser.add_argument('tanks', type=str, default='tanks.json', nargs='?', 
						metavar="TANKS_FILE", help='File to write Tankopedia')
	parser.add_argument('maps', type=str, default='maps.json', nargs='?', 
						metavar='MAPS_FILE', help='File to write map names')
	
		
	args = parser.parse_args(args=argv)

	tasks = []
	for nation in EnumNation:
		tasks.append(asyncio.create_task(extract_tanks(args.blitz_app_dir, nation)))

	tanklist = []
	for tanklist_tmp in await asyncio.gather(*tasks):
		tanklist.extend(tanklist_tmp)
	
	tank_strs, map_strs = await read_user_strs(args.blitz_app_dir)

	json_data = None
	userStrs = {}
	tanks = {}
	if os.path.exists(args.tanks):
		try:
			async with aiofiles.open(args.tanks) as infile:
				json_data = json.loads(await infile.read())
				userStrs = json_data['userStr']
				tanks = json_data['data']
		except Exception as err:
			error(f' error reading file {args.tanks}: {err}')

	async with aiofiles.open(args.tanks, 'w', encoding="utf8") as outfile:
		new_tanks, new_userStrs = await convert_tank_names(tanklist, tank_strs)
		# merge old and new tankopedia
		tanks.update(new_tanks)
		userStrs.update(new_userStrs) 
		tankopedia : OrderedDict[str, str| int | dict ]= OrderedDict()
		tankopedia['status'] = 'ok'
		tankopedia['meta'] = { "count":  len(tanks) }
		tankopedia['data'] = sort_dict(tanks, number=True)
		tankopedia['userStr'] = sort_dict(userStrs)
		message(f"New tankopedia '{args.tanks}' contains {len(tanks)} tanks")
		message(f"New tankopedia '{args.tanks}' contains {len(userStrs)} tanks strings")
		await outfile.write(json.dumps(tankopedia, ensure_ascii=False, indent=4, sort_keys=False))
	
	if args.maps is not None:
		maps = {}
		if os.path.exists(args.maps):
			try:
				async with aiofiles.open(args.maps) as infile:
					maps = json.loads(await infile.read())
			except Exception as err:
				error(f'Unexpected error when reading file: {args.maps} : {err}')
		# merge old and new map data
		maps.update(map_strs)
		async with aiofiles.open(args.maps, 'w', encoding="utf8") as outfile:
			message(f"New maps file '{args.maps}' contains {len(maps)} maps")
			await outfile.write(json.dumps(maps, ensure_ascii=False, indent=4, sort_keys=True))

	return None
	
async def extract_tanks(blitz_app_dir : str, nation: EnumNation):
	"""Extract tanks from BLITZAPP_VEHICLE_FILE for a nation"""
	tanks : list[dict[str, bool | int | str]] = list()
	# WG has changed the location of Data directory - at least in steam client
	if isdir(join_path(blitz_app_dir, 'assets')):
		blitz_app_dir = join_path(blitz_app_dir, 'assets')
	list_xml_file = join_path(blitz_app_dir, 
								BLITZAPP_VEHICLES_DIR,
								nation.name ,
								BLITZAPP_VEHICLE_FILE)
	if not isfile(list_xml_file): 
		print('ERROR: cannot open ' + list_xml_file)
		return None
	debug(f'Opening file: {list_xml_file} (Nation: {nation})')
	async with aiofiles.open(list_xml_file, 'r', encoding="utf8") as f:
		try: 
			tankList = xmltodict.parse(await f.read())
			for data in tankList['root'].keys():
				tank_xml = tankList['root'][data]
				tank : dict[str, bool | int | str]= dict()
				tank['is_premium'] = issubclass(type(tank_xml['price']), dict)
				tank['nation']  = nation.name
				tank['tank_id'] = get_tank_id(nation, int(tank_xml['id']))
				tank['tier']    = int(tank_xml['level'])
				tank['type']    = get_tank_type(tank_xml['tags'])
				tank['userStr'] = tank_xml['userString']
				#debug('Reading tank string: ' + tank['userStr'], force=True)
				tanks.append(tank)
		except Exception as err:
			error(err)
			sys.exit(2)
	return tanks

async def read_user_strs(blitz_app_dir : str) -> tuple[dict, dict]:
	"""Read user strings to convert map and tank names"""
	tank_strs = {}
	map_strs = {}
	filename = join_path(blitz_app_dir, BLITZAPP_STRINGS)
	debug('Opening file: ' + filename + ' for reading UserStrings')
	try:
		async with aiofiles.open(filename, 'r', encoding="utf8") as f:
			p_tank = re.compile('^"(#\\w+?_vehicles:.+?)": "(.+)"$')
			p_map = re.compile('^"#maps:(.+?):.+?: "(.+?)"$')
			
			async for l in f:
				m = p_tank.match(l)
				if m is not None: 
					tank_strs[m.group(1)] = m.group(2)
				
				m = p_map.match(l)
				if m is not None and m.group(2) != 'Macragge':                    
					map_strs[m.group(1)] = m.group(2)   
	
	except Exception as err:
		error(err)
		sys.exit(1)

	return tank_strs, map_strs
	
async def convert_tank_names(tanklist : list, tank_strs: dict) -> tuple[dict, dict]:
	"""Convert tank names for Tankopedia"""
	tankopedia = {}
	userStrs = {}

	debug(f'tank_strs:')
	for key, value in tank_strs.items():
		debug(f'{key}: {value}')
	debug('---------')
	try:
		for tank in tanklist:
			try:
				debug(f'tank: {tank}')
				if tank['userStr'] in tank_strs:
					tank['name'] = tank_strs[tank['userStr']]
				else:
					tank['name'] = tank['userStr'].split(':')[1]
				tank.pop('userStr', None)
				tank_tmp = OrderedDict()
				for key in sorted(tank.keys()):
					tank_tmp[key] = tank[key]
				tankopedia[str(tank['tank_id'])] = tank_tmp
			except:
				error(f'Could not process tank: {tank}')

		for tank_str in tank_strs:
			skip = False
			key = tank_str.split(':')[1]
			debug('Tank string: ' + key + ' = ' + tank_strs[tank_str])
			re_strs = [r'^Chassis_', r'^Turret_', r'^_', r'_short$' ]
			for re_str in re_strs:
				p = re.compile(re_str)
				if p.match(key):
					skip = True
					break
			if skip:
				continue
			
			userStrs[key] = tank_strs[tank_str]

		# sorting
		tankopedia_sorted = OrderedDict()
		for tank_id in sorted(tankopedia.keys(), key=int):
			tankopedia_sorted[str(tank_id)] = tankopedia[str(tank_id)]

		userStrs_sorted = OrderedDict()
		for userStr in sorted(userStrs.keys()):
			userStrs_sorted[userStr] = userStrs[userStr]
		# debug('Tank strings: ' + str(len(userStrs_sorted)))

	except Exception as err:
		error(err)
		sys.exit(1)

	return tankopedia_sorted, userStrs_sorted


def get_tank_id(nation: EnumNation, tank_id : int) -> int:
	return (tank_id << 8) + (nation.value << 4) + 1 


def get_tank_type(tagstr : str):
	tags = tagstr.split(' ')
	for t_type in wg.TANK_TYPE:
		if tags[0] == t_type:
			return t_type
	return None

### main()
if __name__ == "__main__":
	# To avoid 'Event loop is closed' RuntimeError due to compatibility issue with aiohttp
	if sys.platform.startswith("win") and sys.version_info >= (3, 8):
		try:
			from asyncio import WindowsSelectorEventLoopPolicy
		except ImportError:
			pass
		else:
			if not isinstance(get_event_loop_policy(), WindowsSelectorEventLoopPolicy):
				set_event_loop_policy(WindowsSelectorEventLoopPolicy())
	run(main())
