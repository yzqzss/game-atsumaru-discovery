import datetime
import itertools
import json
import os
import pyjsparser
import re
import sys
import tempfile
import time
import urllib.parse

if not os.path.isdir('./ticket'):
    os.mkdir('./ticket')
if not os.path.isdir('./warc'):
    os.mkdir('./warc')

get_headers = {
    'Cache-Control': 'no-cache',
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/114.0',
    'X-Frontend-Id': '39',
    'X-Frontend-Version': '3.464.0',
    'Origin': 'https://game.nicovideo.jp',
    'Referer': 'https://game.nicovideo.jp/',
}

post_headers = {
    'Cache-Control': 'no-cache',
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/114.0',
    'X-Frontend-Id': '39',
    'X-Frontend-Version': '3.464.0',
    'X-Request-With': 'https://game.nicovideo.jp',
    'Origin': 'https://game.nicovideo.jp',
    'Referer': 'https://game.nicovideo.jp/',
}

resource_root = 'https://resource.game.nicovideo.jp/'

if not os.path.isfile('data/public.txt') or not os.path.isfile('data/key_valid.txt'):
    exit('Please check public and unlisted game_ids at first.')

if not os.path.isfile('data/catagory.json'):
    exit('Please categorize games at first.')

games = []

with open('data/public.txt', 'r') as r, open('data/key_valid.txt', 'r') as rk:
    for line in itertools.chain(r.readlines(), rk.readlines()):
        match = re.search(r'^https://game\.nicovideo\.jp/atsumaru/games/gm([1-9][0-9]*)(?:\?key=([0-9a-f]{12}))?$', line.strip())
        assert isinstance(match, re.Match), line.strip()
        games.append((int(match[1]), match[2]))

with open('data/catagory.json', 'r') as r:
    framework_games = json.load(r)

games = list(filter(lambda item: item[0] in framework_games['RPGMakerMZ'], games))
games.sort()

if len(sys.argv) >= 3 and re.search('^[0-9]+$', sys.argv[1]) and re.search('^[0-9]+$', sys.argv[2]):
    games = list(filter(lambda item: int(sys.argv[1]) <= item[0] <= int(sys.argv[2]), games))
    if len(games):
        print(f'Fetching gm{games[0][0]} ~ gm{games[-1][0]}')
elif len(sys.argv) >= 2 and re.search('^[0-9]+$', sys.argv[1]):
    games = list(filter(lambda item: item[0] == int(sys.argv[1]), games))
    if len(games):
        print(f'Fetching gm{games[0][0]}')

for game_id, key in games:
    timestamp_suffix = '' and f'_{int(time.time()*1E6)}'
    try:
        if key is None:
            ticket_url = f'https://api.game.nicovideo.jp/v1/rpgtkool/games/gm{game_id}/play-tickets.json?sandbox=0&wipAccessKey'
        else:
            ticket_url = f'https://api.game.nicovideo.jp/v1/rpgtkool/games/gm{game_id}/play-tickets.json?sandbox=0&wipAccessKey={key}'
        os.system(f'curl -X POST -A "User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/114.0" \
                -H "X-Frontend-Id: 39" -H "X-Frontend-Version: 3.464.0" -H "X-Request-With: https://game.nicovideo.jp" \
                -H "Origin: https://game.nicovideo.jp" -H "Referer: https://game.nicovideo.jp/" -F "=" \
                -c "ticket/gm{game_id}_cookie.txt" -o ticket/gm{game_id}_ticket.json "{ticket_url}"')

        assert os.path.isfile(f'ticket/gm{game_id}_cookie.txt')
        cookie_jar = []
        with open(f'ticket/gm{game_id}_cookie.txt', 'r') as r:
            for line in r.readlines():
                fields = line.strip().split('\t')
                if len(fields) == 7:
                    cookie_jar.append(f'{fields[5]}={fields[6]}')
            cookie_argument = f'--header="Cookie: {"; ".join(cookie_jar)}"'

        assert os.path.isfile(f'ticket/gm{game_id}_ticket.json')
        with open(f'ticket/gm{game_id}_ticket.json', 'r') as r:
            ticket = json.load(r)
            game_path = ticket['data']['path'].lstrip('/')
            game_url = ticket['data']['gameUrl']

        temp_dir = tempfile.TemporaryDirectory()
        temp_urllist = os.path.join(temp_dir.name, 'temp_urllist')

        os.system(f'wget --execute="robots=off" --no-verbose --force-directories --no-host-directories \
                --header="Host: resource.game.nicovideo.jp" --header="User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/114.0" \
                {cookie_argument} \
                --load-cookies=ticket/gm{game_id}_cookie.txt --keep-session-cookies \
                --warc-file=warc/gm{game_id}{timestamp_suffix} --no-warc-compression --no-warc-keep-log \
                --recursive --level=inf --no-parent {game_url}')

        # Step 1: Load main scripts

        discovered_urls = []
        step_urls = []
        script_urls = []

        assert os.path.isfile(os.path.join(game_path, 'js/main.js')), 'js/main.js'
        with open(os.path.join(game_path, 'js/main.js'), 'r', encoding='utf-8-sig') as r, open(os.path.join(game_path, 'js/main.js'), 'r', encoding='shift-jis') as rs:
            try: content = r.read()
            except UnicodeDecodeError: content = rs.read()
            # ClassDeclaration is not supported by ECMA 5.1.
            content = '\n'.join(content.split('\n')[:20])
            try:
                body = pyjsparser.parse(content)['body']
            except pyjsparser.pyjsparserdata.JsSyntaxError:
                raise AssertionError('js/main.js')
            for node in filter(lambda node: node['type'] == 'VariableDeclaration'
                            and node['kind'] == 'const'
                            and len(node['declarations']) == 1
                            and node['declarations'][0]['id']['type'] == 'Identifier'
                            and node['declarations'][0]['id']['name'] == 'scriptUrls', body):
                assert node['declarations'][0]['init']['type'] == 'ArrayExpression', 'js/main.js'
                for element in node['declarations'][0]['init']['elements']:
                    script_urls.append(element['value'])
            for node in filter(lambda node: node['type'] == 'VariableDeclaration'
                            and node['kind'] == 'const'
                            and len(node['declarations']) == 1
                            and node['declarations'][0]['id']['type'] == 'Identifier'
                            and node['declarations'][0]['id']['name'] == 'effekseerWasmUrl', body):
                assert node['declarations'][0]['init']['type'] == 'Literal', 'js/main.js'
                script_urls.append(node['declarations'][0]['init']['value'])

        for script_url in sorted(set(script_urls)):
            step_urls.append(os.path.join(resource_root, game_path, script_url))

        with open(temp_urllist, 'w') as w:
            for url in step_urls: print(url, file=w)
        os.system(f'wget --execute="robots=off" --no-verbose --input-file={temp_urllist} --force-directories --no-host-directories \
                --header="Host: resource.game.nicovideo.jp" --header="User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/114.0" \
                {cookie_argument} \
                --load-cookies=ticket/gm{game_id}_cookie.txt --keep-session-cookies \
                --warc-file=warc/gm{game_id}_1{timestamp_suffix} --no-warc-compression --no-warc-keep-log \
                --recursive --level=inf --no-parent')

        # Step 2: General settings

        discovered_urls.extend(step_urls)
        step_urls = []

        assert os.path.isfile(os.path.join(game_path, 'js/rmmz_core.js')), 'js/rmmz_core.js'
        with open(os.path.join(game_path, 'js/rmmz_core.js'), 'r', encoding='utf-8-sig') as r, open(os.path.join(game_path, 'js/rmmz_core.js'), 'r', encoding='shift-jis') as rs:
            try: content = r.read()
            except UnicodeDecodeError: content = rs.read()
            assert content.find('Utils.setEncryptionInfo = function(hasImages, hasAudio, key) {') >= 0

        audio_path = 'audio/'

        assert os.path.isfile(os.path.join(game_path, 'js/rmmz_managers.js')), 'js/rmmz_managers.js'
        with open(os.path.join(game_path, 'js/rmmz_managers.js'), 'r', encoding='utf-8-sig') as r, open(os.path.join(game_path, 'js/rmmz_managers.js'), 'r', encoding='shift-jis') as rs:
            try: content = r.read()
            except UnicodeDecodeError: content = rs.read()
            assert content.find('const url = "data/" + src;') >= 0, 'js/rmmz_managers.js'
            database_array_re = re.search(r'(DataManager\._databaseFiles = \[[^\[\]]+\];)', content)
            assert database_array_re, 'js/rmmz_managers.js'
            body = pyjsparser.parse(database_array_re[1])['body']
            # DataManager._databaseFiles = [{ name: "$dataActors", src: "Actors.json" },];
            for node in filter(lambda node: node['type'] == 'ExpressionStatement'
                            and node['expression']['type'] == 'AssignmentExpression'
                            and node['expression']['operator'] == '='
                            and node['expression']['left']['type'] == 'MemberExpression'
                            and node['expression']['left']['object']['type'] == 'Identifier'
                            and node['expression']['left']['object']['name'] == 'DataManager'
                            and node['expression']['left']['property']['type'] == 'Identifier'
                            and node['expression']['left']['property']['name'] == '_databaseFiles', body):
                assert node['expression']['right']['type'] == 'ArrayExpression', 'js/rmmz_managers.js'
                for database_file in node['expression']['right']['elements']:
                    assert database_file['type'] == 'ObjectExpression'
                    database_file_src = list(filter(lambda node: node['key']['type'] == 'Identifier' and node['key']['name'] == 'src', database_file["properties"]))[0]['value']['value']
                    # DataManager.loadDatabase = function() {}
                    step_urls.append(os.path.join(resource_root, game_path, f'data/{database_file_src}'))
            # AudioManager._path = "audio/";
            audio_path_re = re.search(r'(AudioManager\._path = "[^"]+";)', content)
            assert audio_path_re, 'js/rmmz_managers.js'
            body = pyjsparser.parse(audio_path_re[1])['body']
            for node in filter(lambda node: node['type'] == 'ExpressionStatement'
                            and node['expression']['type'] == 'AssignmentExpression'
                            and node['expression']['operator'] == '='
                            and node['expression']['left']['type'] == 'MemberExpression'
                            and node['expression']['left']['object']['type'] == 'Identifier'
                            and node['expression']['left']['object']['name'] == 'AudioManager'
                            and node['expression']['left']['property']['type'] == 'Identifier'
                            and node['expression']['left']['property']['name'] == '_path', body):
                assert node['expression']['right']['type'] == 'Literal', 'js/rmmz_managers.js'
                audio_path = node['expression']['right']['value']
            assert content.find('return "js/plugins/" + Utils.encodeURI(filename) + ".js";') >= 0, 'js/rmmz_managers.js'

        if os.path.isfile('data/MZ_plugins.json'):
            with open('data/MZ_plugins.json', 'r') as r:
                glob_plugins = json.load(r)
        else:
            glob_plugins = {}

        assert os.path.isfile(os.path.join(game_path, 'js/plugins.js')), 'js/plugins.js'
        with open(os.path.join(game_path, 'js/plugins.js'), 'r', encoding='utf-8-sig') as r, open(os.path.join(game_path, 'js/plugins.js'), 'r', encoding='shift-jis') as rs:
            try: content = r.read()
            except UnicodeDecodeError: content = rs.read()
            body = pyjsparser.parse(content)['body']
            assert len(body) == 2, 'js/plugins.js'
            for node in filter(lambda node: node['type'] == 'VariableDeclaration', body):
                assert len(node['declarations']) == 1, 'js/plugins.js'
                assert node['declarations'][0]['id']['name'] == '$plugins', 'js/plugins.js'
                assert node['declarations'][0]['init']['type'] == 'ArrayExpression', 'js/plugins.js'
                for plugin in node['declarations'][0]['init']['elements']:
                    assert plugin['type'] == 'ObjectExpression', 'js/plugins.js'
                    plugin_name = list(filter(lambda node: node['key']['value'] == 'name', plugin["properties"]))[0]['value']['value']
                    step_urls.append(os.path.join(resource_root, game_path, f'js/plugins/{plugin_name}.js'))
                    if plugin_name in glob_plugins.keys():
                        glob_plugins[plugin_name] = sorted(list(set([*glob_plugins[plugin_name], game_id])))
                    else:
                        glob_plugins[plugin_name] = [game_id]

        with open('data/MZ_plugins.json', 'w') as w:
            json.dump(glob_plugins, w)

        with open(temp_urllist, 'w') as w:
            for url in step_urls: print(url, file=w)
        os.system(f'wget --execute="robots=off" --no-verbose --input-file={temp_urllist} --force-directories --no-host-directories \
                --header="Host: resource.game.nicovideo.jp" --header="User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/114.0" \
                {cookie_argument} \
                --load-cookies=ticket/gm{game_id}_cookie.txt --keep-session-cookies \
                --warc-file=warc/gm{game_id}_2{timestamp_suffix} --no-warc-compression --no-warc-keep-log \
                --recursive --level=inf --no-parent')

        # Step 3: Map settings

        discovered_urls.extend(step_urls)
        step_urls = []

        assert os.path.isfile(os.path.join(game_path, 'data/MapInfos.json')), 'data/MapInfos.json'
        with open(os.path.join(game_path, 'data/MapInfos.json'), 'r', encoding='utf-8-sig') as r:
            data_mapinfo = json.load(r)
            for _map in data_mapinfo:
                if _map is not None:
                    assert isinstance(_map.get('id'), int), 'data/MapInfos.json'
                    # DataManager.loadMapData = function(mapId) {}
                    step_urls.append(os.path.join(resource_root, game_path, f'data/Map{_map["id"]:03}.json'))

        with open(temp_urllist, 'w') as w:
            for url in step_urls: print(url, file=w)
        os.system(f'wget --execute="robots=off" --no-verbose --input-file={temp_urllist} --force-directories --no-host-directories \
                --header="Host: resource.game.nicovideo.jp" --header="User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/114.0" \
                {cookie_argument} \
                --load-cookies=ticket/gm{game_id}_cookie.txt --keep-session-cookies \
                --warc-file=warc/gm{game_id}_3{timestamp_suffix} --no-warc-compression --no-warc-keep-log \
                --recursive --level=inf --no-parent')

        # Step 4: Resources

        discovered_urls.extend(step_urls)
        step_urls = []
        resource_urls = [
            'img/system/Balloon.png',
            'img/system/ButtonSet.png',
            'img/system/GameOver.png',
            'img/system/IconSet.png',
            'img/system/Loading.png',
            'img/system/Shadow1.png',
            'img/system/Shadow2.png',
            'img/system/States.png',
            'img/system/System.png',
            'img/system/Weapons1.png',
            'img/system/Weapons2.png',
            'img/system/Weapons3.png',
            'img/system/Window.png',
        ]

        audio_names = set()
        movie_names = set()

        effect_names = set()
        battleback1_names = set()
        battleback2_names = set()
        enemy_names = set()
        character_names = set()
        face_names = set()
        actor_names = set()
        parallax_names = set()
        picture_names = set()
        tileset_names = set()

        def parse_commandlist(eventlist):
            for child in eventlist:
                # Show Text
                if child['code'] in [101]: face_names.add(child['parameters'][0])
                # Change Battle BGM
                if child['code'] in [132]: audio_names.add(('bgm', child['parameters'][0]['name']))
                # Change Victory ME, Change Defeat ME
                elif child['code'] in [133, 139]: audio_names.add(('me', child['parameters'][0]['name']))
                # Change Vehicle BGM
                elif child['code'] in [140]: audio_names.add(('bgm', child['parameters'][1]['name']))
                # Set Movement Route
                elif child['code'] in [205]:
                    for command in child['parameters'][1]['list']:
                        # ROUTE_CHANGE_IMAGE
                        if command['code'] == 41:
                            character_names.add(command['parameters'][0])
                # Show Picture
                elif child['code'] in [231]: picture_names.add(child['parameters'][1])
                # Play BGM
                elif child['code'] in [241]: audio_names.add(('bgm', child['parameters'][0]['name']))
                # Play BGS
                elif child['code'] in [245]: audio_names.add(('bgs', child['parameters'][0]['name']))
                # Play ME
                elif child['code'] in [249]: audio_names.add(('me', child['parameters'][0]['name']))
                # Play SE
                elif child['code'] in [250]: audio_names.add(('se', child['parameters'][0]['name']))
                # Play Movie
                elif child['code'] in [261]: movie_names.add(child['parameters'][0])
                # Change Battle Background
                elif child['code'] in [283]:
                    battleback1_names.add(child["parameters"][0])
                    battleback2_names.add(child["parameters"][1])
                # Change Parallax
                elif child['code'] in [284]: parallax_names.add(child['parameters'][0])
                # Change Actor Images
                elif child['code'] in [322]:
                    character_names.add(child['parameters'][1])
                    face_names.add(child['parameters'][3])
                    actor_names.add(child['parameters'][5])
                # Change Vehicle Image
                elif child['code'] in [323]:
                    character_names.add(child['parameters'][1])
                # Script
                elif child['code'] in [355]:
                    # print('script', child['parameters'])
                    pass
                # Plugin Command MV (deprecated)
                elif child['code'] in [356]:
                    # print('plugin-event-MV', child['parameters'])
                    pass
                # Plugin Command
                elif child['code'] in [357]:
                    # print('plugin-event', child['parameters'])
                    pass

        assert os.path.isfile(os.path.join(game_path, 'data/Actors.json')), 'data/Actors.json'
        with open(os.path.join(game_path, 'data/Actors.json'), 'r', encoding='utf-8-sig') as r:
            data_actor = json.load(r)
            for actor in data_actor:
                if actor is not None:
                    if 'characterName' in actor.keys():
                        character_names.add(actor['characterName'])
                    if 'faceName' in actor.keys():
                        face_names.add(actor['faceName'])
                    if 'battlerName' in actor.keys():
                        actor_names.add(actor['battlerName'])
                    if 'effectName' in actor.keys():
                        effect_names.add(actor['effectName'])
                    if 'timing' in actor.keys():
                        for timing in actor['timings']:
                            if timing['se'] is not None:
                                audio_names.add(('se', timing['se']['name']))

        assert os.path.isfile(os.path.join(game_path, 'data/Animations.json')), 'data/Animations.json'
        with open(os.path.join(game_path, 'data/Animations.json'), 'r', encoding='utf-8-sig') as r:
            data_animation = json.load(r)
            for animation in data_animation:
                if animation is not None:
                    if 'effectName' in animation.keys():
                        effect_names.add(animation['effectName'])
                    if 'soundTimings' in animation.keys():
                        for timing in animation['soundTimings']:
                            if timing['se'] is not None:
                                audio_names.add(('se', timing['se']['name']))
                    if 'timings' in animation.keys():
                        for timing in animation['timings']:
                            if timing['se'] is not None:
                                audio_names.add(('se', timing['se']['name']))

        assert os.path.isfile(os.path.join(game_path, 'data/CommonEvents.json')), 'data/CommonEvents.json'
        with open(os.path.join(game_path, 'data/CommonEvents.json'), 'r', encoding='utf-8-sig') as r:
            data_commonevents = json.load(r)
            for event in data_commonevents:
                if event is not None:
                    assert isinstance(event['list'], list)
                    parse_commandlist(event['list'])

        assert os.path.isfile(os.path.join(game_path, 'data/Enemies.json')), 'data/Enemies.json'
        with open(os.path.join(game_path, 'data/Enemies.json'), 'r', encoding='utf-8-sig') as r:
            data_enemies = json.load(r)
            for enemy in data_enemies:
                if enemy is not None:
                    enemy_names.add(enemy['battlerName'])

        assert os.path.isfile(os.path.join(game_path, 'data/Tilesets.json')), 'data/Tilesets.json'
        with open(os.path.join(game_path, 'data/Tilesets.json'), 'r', encoding='utf-8-sig') as r:
            data_tileset = json.load(r)
            for tileset in data_tileset:
                if tileset is not None:
                    assert 'tilesetNames' in tileset.keys(), 'data/Tilesets.json'
                    assert isinstance(tileset['tilesetNames'], list), 'data/Tilesets.json'
                    for tileset_name in tileset['tilesetNames']:
                        tileset_names.add(tileset_name)

        with open(os.path.join(game_path, 'data/MapInfos.json'), 'r', encoding='utf-8-sig') as r:
            data_mapinfo = json.load(r)
            for _map in data_mapinfo:
                if _map is not None:
                    map_path = os.path.join(game_path, f'data/Map{_map["id"]:03}.json')
                    assert os.path.isfile(map_path), 'data/MapInfos.json'
                    with open(map_path, 'r', encoding='utf-8-sig') as rm:
                        data_map = json.load(rm)
                        audio_names.add(('bgm', data_map['bgm']['name']))
                        audio_names.add(('bgm', data_map['bgs']['name']))
                        for event in data_map['events']:
                            if event is not None:
                                for page in event['pages']:
                                    character_names.add(page['image']['characterName'])
                                    parse_commandlist(page['list'])

        Decrypter = {}

        assert os.path.isfile(os.path.join(game_path, 'data/System.json')), 'data/System.json'
        with open(os.path.join(game_path, 'data/System.json'), 'r', encoding='utf-8-sig') as r:
            data_system = json.load(r)
            assert set(data_system.keys()).issuperset(set([
                'advanced',
                'airship', 'boat', 'ship',
                'battlerName', 'battleback1Name', 'battleback2Name',
                'battleBgm', 'titleBgm',
                'defeatMe', 'gameoverMe', 'victoryMe',
                'sounds',
                'gameTitle', 'title1Name', 'title2Name',
            ])), 'data/System.json'
            # Scene_Boot.prototype.setEncryptionInfo
            # Utils.setEncryptionInfo
            if 'encryptionKey' in data_system.keys():
                assert set(data_system.keys()).issuperset(set(['hasEncryptedImages', 'hasEncryptedAudio'])), 'data/System.json'
                assert re.search(r'^[0-9a-f]{32}$', data_system['encryptionKey']), 'data/System.json'
                assert isinstance(data_system['hasEncryptedImages'], bool) and isinstance(data_system['hasEncryptedAudio'], bool), 'data/System.json'
                Decrypter.update({ 'hasEncryptedImages': data_system['hasEncryptedImages'], 'hasEncryptedAudio': data_system['hasEncryptedAudio'] })
            for font in ['mainFontFilename', 'numberFontFilename']:
                # FontManager.load
                # FontManager.makeUrl
                if len(data_system["advanced"][font]) >= 1:
                    resource_urls.append(f'fonts/{data_system["advanced"][font]}')
            for vehicle in ['airship', 'boat', 'ship']:
                if data_system[vehicle]['bgm'] is not None:
                    audio_names.add(('bgm', data_system[vehicle]['bgm']['name']))
            actor_names.add(data_system['battlerName'])
            battleback1_names.add(data_system['battleback1Name'])
            battleback2_names.add(data_system['battleback2Name'])
            for bgm in ['battleBgm', 'titleBgm']:
                audio_names.add(('bgm', data_system[bgm]['name']))
            for me in ['defeatMe', 'gameoverMe', 'victoryMe']:
                audio_names.add(('me', data_system[me]['name']))
            for se in data_system['sounds']:
                audio_names.add(('se', se['name']))
            if len(data_system['title1Name']) >= 1:
                # ImageManager.loadTitle1
                resource_urls.append(f'img/titles1/{data_system["title1Name"]}.png')
            if len(data_system['title2Name']) >= 1:
                # ImageManager.loadTitle2
                resource_urls.append(f'img/titles2/{data_system["title2Name"]}.png')

        assert os.path.isfile(os.path.join(game_path, 'js/rmmz_managers.js')), 'js/rmmz_managers.js'
        with open(os.path.join(game_path, 'js/rmmz_managers.js'), 'r', encoding='utf-8-sig') as r, open(os.path.join(game_path, 'js/rmmz_managers.js'), 'r', encoding='shift-jis') as rs:
            try: content = r.read()
            except UnicodeDecodeError: content = rs.read()
            for filename in re.findall(r"Graphics\.setLoadingImage\('([^']+)'\)", content):
                resource_urls.append(filename)

        assert os.path.isfile(os.path.join(game_path, 'js/rmmz_scenes.js')), 'js/rmmz_scenes.js'
        with open(os.path.join(game_path, 'js/rmmz_scenes.js'), 'r', encoding='utf-8-sig') as r, open(os.path.join(game_path, 'js/rmmz_scenes.js'), 'r', encoding='shift-jis') as rs:
            try: content = r.read()
            except UnicodeDecodeError: content = rs.read()
            for filename in re.findall(r"ImageManager\.(?:load|reserve|request)System\((?:\'|\")([^']+)(?:\'|\")\)", content):
                # ImageManager.loadSystem
                resource_urls.append(f'img/system/{filename}.png')

        for folder, name in sorted(audio_names):
            # AudioManager.playBgm
            # AudioManager.playBgs
            # AudioManager.playMe
            # AudioManager.playSe
            if len(name) >= 1:
                if Decrypter.get('hasEncryptedAudio') == True:
                    # WebAudio.prototype._realUrl
                    resource_urls.append(os.path.join(audio_path, f'{folder}/{name}.ogg_'))
                # AudioManager.audioFileExt
                resource_urls.append(os.path.join(audio_path, f'{folder}/{name}.ogg'))

        for movie_name in sorted(movie_names):
            if len(movie_name) >= 1:
                # Graphics.playVideo
                resource_urls.append(f'movies/{movie_name}.webm')
                resource_urls.append(f'movies/{movie_name}.mp4')

        for effect_name in sorted(effect_names):
            if len(effect_name) >= 1:
                # EffectManager.load
                # EffectManager.makeUrl
                resource_urls.append(f'effects/{effect_name}.efkefc')
        for battleback1_name in sorted(battleback1_names):
            if len(battleback1_name) >= 1:
                # ImageManager.loadBattleback1
                resource_urls.append(f'img/battlebacks1/{battleback1_name}.png')
        for battleback2_name in sorted(battleback2_names):
            if len(battleback2_name) >= 1:
                # ImageManager.loadBattleback2
                resource_urls.append(f'img/battlebacks2/{battleback2_name}.png')
        for enemy_name in sorted(enemy_names):
            if len(enemy_name) >= 1:
                # ImageManager.loadEnemy
                resource_urls.append(f'img/enemies/{enemy_name}.png')
                # ImageManager.loadSvEnemy
                resource_urls.append(f'img/sv_enemies/{enemy_name}.png')
        for character_name in sorted(character_names):
            if len(character_name) >= 1:
                # ImageManager.loadCharacter
                resource_urls.append(f'img/characters/{character_name}.png')
        for face_name in sorted(face_names):
            if len(face_name) >= 1:
                # ImageManager.loadFace
                resource_urls.append(f'img/faces/{face_name}.png')
        for actor_name in sorted(actor_names):
            if len(actor_name) >= 1:
                # ImageManager.loadSvActor
                resource_urls.append(f'img/sv_actors/{actor_name}.png')
        for parallax_name in sorted(parallax_names):
            if len(parallax_name) >= 1:
                # ImageManager.loadParallax
                resource_urls.append(f'img/parallaxes/{parallax_name}.png')
        for picture_name in sorted(picture_names):
            if len(picture_name) >= 1:
                # ImageManager.loadPicture
                resource_urls.append(f'img/pictures/{picture_name}.png')
        for tileset_name in sorted(tileset_names):
            if len(tileset_name) >= 1:
                # ImageManager.loadTileset
                resource_urls.append(f'img/tilesets/{tileset_name}.png')

        for script_url in sorted(set(resource_urls)):
            if re.search(r'\.png$', script_url) and Decrypter.get('hasEncryptedImages') == True:
                step_urls.append(os.path.join(resource_root, game_path, urllib.parse.quote(script_url + '_', safe='/')))
            step_urls.append(os.path.join(resource_root, game_path, urllib.parse.quote(script_url, safe='/')))

        with open(temp_urllist, 'w') as w:
            for url in step_urls: print(url, file=w)
        os.system(f'wget --execute="robots=off" --no-verbose --input-file={temp_urllist} --force-directories --no-host-directories \
                --header="Host: resource.game.nicovideo.jp" --header="User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/114.0" \
                {cookie_argument} \
                --load-cookies=ticket/gm{game_id}_cookie.txt --keep-session-cookies \
                --warc-file=warc/gm{game_id}_4{timestamp_suffix} --no-warc-compression --no-warc-keep-log \
                --recursive --level=inf --no-parent --timeout=10')

        discovered_urls.extend(step_urls)
        step_urls = []

        with open(f'data/iterate/urls_gm{game_id}.txt', 'w') as w:
            for url in discovered_urls:
                print(url, file=w)

        temp_dir.cleanup()

    except AssertionError as ex:
        if temp_dir: temp_dir.cleanup()
        now_string = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        print(f'{now_string} gm{game_id} (MZ) failed. {ex.args}')
        with open(f'data/iterate.txt', 'a') as a:
            print(f'{now_string} gm{game_id:05d} (MZ) failed. {ex.args}', file=a)