import config


class LocationError(Exception):
    pass


class LocationExecutionError(LocationError):
    pass


class LocationOutputError(LocationError):
    pass


async def get_geocode_data(location, session=None):
    if not session:
        raise LocationExecutionError('aiohttp session required.')

    url = 'http://api.positionstack.com/v1/forward'
    params = {'query': location, 'access_key': config.positionstack_api_key, 'limit': 1}
    async with session.get(url, params=params) as resp:
        if resp.status != 200:
            raise LocationOutputError(f'API responded with {resp.status}')
        geocode_data = await resp.json()
    if geocode_data.get('error'):
        msg = geocode_data['error']['message']
        if geocode_data['error']['code'] == 'validation_error':
            msg = geocode_data['error']['context']['query'][0]['message']
        raise LocationOutputError(msg)

    if not geocode_data['data']:
        raise LocationOutputError('Address/Location not found.')

    return geocode_data['data']['results'][0]


async def get_timezone_data(location=None, latitude=None, longitude=None, session=None):
    if not session:
        raise LocationExecutionError('aiohttp session required.')

    if not (latitude and longitude):
        if not location:
            raise LocationExecutionError('Location or latitude and longitude not found.')
        geocode_data = await get_geocode_data(location, session=session)
        latitude = geocode_data['latitude']
        longitude = geocode_data['longitude']
    url = 'https://api.ipgeolocation.io/timezone'
    params = {'apikey': config.ip_geolocation_api_key, 'lat': latitude, 'long': longitude}
    async with session.get(url, params=params) as resp:
        if resp.status != 200:
            raise LocationOutputError(f'API responded with {resp.status}')
        timezone_data = await resp.json()
    if timezone_data.get('message'):
        raise LocationOutputError(timezone_data['message'])

    return timezone_data


def wind_degrees_to_direction(degrees):
    # http://snowfence.umn.edu/Components/winddirectionanddegreeswithouttable3.htm
    if not isinstance(degrees, (int, float)):
        raise LocationExecutionError('Degrees must be a number.')
    if not (0 <= degrees <= 360):
        raise LocationExecutionError('Degrees must be between 0 and 360.')
    if degrees <= 11.25 or 348.75 <= degrees:
        return 'N'
    if 11.25 <= degrees <= 33.75:
        return "NNE"
    if 33.75 <= degrees <= 56.25:
        return "NE"
    if 56.25 <= degrees <= 78.75:
        return "ENE"
    if 78.75 <= degrees <= 101.25:
        return 'E'
    if 101.25 <= degrees <= 123.75:
        return "ESE"
    if 123.75 <= degrees <= 146.25:
        return "SE"
    if 146.25 <= degrees <= 168.75:
        return "SSE"
    if 168.75 <= degrees <= 191.25:
        return 'S'
    if 191.25 <= degrees <= 213.75:
        return "SSW"
    if 213.75 <= degrees <= 236.25:
        return "SW"
    if 236.25 <= degrees <= 258.75:
        return "WSW"
    if 258.75 <= degrees <= 281.25:
        return 'W'
    if 281.25 <= degrees <= 303.75:
        return "WNW"
    if 303.75 <= degrees <= 326.25:
        return "NW"
    if 326.25 <= degrees <= 348.75:
        return "NNW"
